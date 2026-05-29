"""SaveData — dynamic-port core IO saver (ADR-028 Addendum 1 §C5/§C9, ADR-043).

The :class:`SaveData` block is the canonical core IO **output** block:
one block class with a ``core_type`` enum that drives a per-instance
``InputPort`` accepted-types override via
:meth:`SaveData.get_effective_input_ports`, and a small dispatch
table that routes :meth:`SaveData.save` to one of six module-level
private ``_save_*`` functions per ADR-028 Addendum 1 §C9 (private
functions, **not** helper classes).

The six private functions absorb the write logic from the deleted
``csv_adapter.py``, ``parquet_adapter.py``, ``zarr_adapter.py``, and
``generic_adapter.py``. ``allow_pickle`` gating happens inside each
``_save_*`` whenever the file extension is ``.pkl`` or ``.pickle`` —
the default is ``False`` and a write to a pickle file fails loudly
unless the user explicitly opts in. When pickle is enabled an explicit
security warning is logged at ``WARNING`` level.

This block is symmetric with :class:`scistudio.blocks.io.loaders.LoadData`
(T-TRK-007). The two blocks share the same ``_CORE_TYPE_MAP`` /
``config_schema`` shape; the only differences are ``direction``,
``input_ports`` vs ``output_ports``, and ``input_port_mapping`` vs
``output_port_mapping`` in the ``dynamic_ports`` declaration.

ADR-043 / spec ``adr-043-package-migration`` FR-002 / FR-003:
``SaveData`` now declares explicit ``FormatCapability`` records via
``format_capabilities`` (mirror of ``LoadData.format_capabilities`` with
``direction="save"``). The legacy ``supported_extensions`` ClassVar has
been removed; format dispatch is derived from the capability
declarations via :func:`_legacy_save_extension_map`. Each save
capability is paired with its load sibling via ``roundtrip_group``.

Module layout (Path D, issue #1459, Phase 2 of #1427)
-----------------------------------------------------

The module-level helper functions that used to live in this file were
extracted to private sibling modules per ADR-028 Addendum 1 §C9
("private functions, not helper classes" — Path D satisfies this
verbatim because the new siblings contain *only* module-level
``_underscore`` functions, no classes):

- :mod:`scistudio.blocks.io.savers._capability` — ``FormatCapability``
  declarations, ``_SAVE_EXTENSION_MAP``, ``_resolve_save_format``.
- :mod:`scistudio.blocks.io.savers._helpers` — ``_require_path``,
  ``_check_pickle_gate``, ``_unwrap_for_save``, ``_CORE_TYPE_MAP``,
  and the small per-format coercion helpers shared by the dispatch
  functions.
- :mod:`scistudio.blocks.io.savers._streaming` — row-group / zero
  materialisation export paths used by ``_save_array`` and
  ``_save_dataframe`` (ADR-031 Phase 3).

The helper symbols are re-imported at module level below so legacy
callers that do ``from scistudio.blocks.io.savers.save_data import
_SAVE_CAPABILITIES`` (test code, mostly) continue to work without
change.
"""

from __future__ import annotations

import json
import pickle
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.blocks.io.io_block import IOBlock

# Re-exports from the private sibling modules. The unused-import noqa
# tags are intentional: legacy callers import these names directly from
# :mod:`scistudio.blocks.io.savers.save_data`, so they must remain
# present at this module's top level.
from scistudio.blocks.io.savers._capability import (
    _PICKLE_NOTE,  # noqa: F401  re-export for backward compat
    _SAVE_CAPABILITIES,
    _SAVE_EXTENSION_MAP,
    _ensure_save_target_available,
    _legacy_save_extension_map,  # noqa: F401  re-export for backward compat
    _resolve_save_format,  # noqa: F401  re-export for backward compat
    _resolve_save_path_and_format,
    _save_capability,  # noqa: F401  re-export for backward compat
    _supported_save_extensions,
)
from scistudio.blocks.io.savers._helpers import (
    _CORE_TYPE_MAP,
    _PICKLE_EXTENSIONS,  # noqa: F401  re-export for backward compat
    _check_pickle_gate,
    _dataframe_to_arrow_table,
    _require_path,
    _resolve_core_type_name,
    _slot_path_for,
    _unwrap_for_save,
    logger,  # noqa: F401  re-export for backward compat
)
from scistudio.blocks.io.savers._streaming import (
    _streaming_save_dataframe_csv,
    _streaming_save_dataframe_parquet,
    _zarr_store_copy,
)
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text


def _source_file_stem(obj: DataObject) -> tuple[str, str]:
    if isinstance(obj, Artifact) and obj.file_path is not None:
        source_name = Path(obj.file_path).name
    else:
        source = getattr(obj.framework, "source", "")
        source_name = Path(source).name if isinstance(source, str) and source else ""
    if not source_name:
        return type(obj).__name__.lower(), ""
    source_path = Path(source_name)
    return source_path.stem or source_path.name, source_path.name


def _collection_item_filename(
    configured: str | None,
    item: DataObject,
    *,
    index: int,
) -> str:
    _stem, name = _source_file_stem(item)
    if configured and configured.strip():
        path = Path(configured.strip()).name
        candidate = Path(path)
        return f"{candidate.stem}-{index}{candidate.suffix}" if candidate.suffix else f"{path}-{index}"
    if name:
        return name
    raise ValueError(
        "SaveData cannot name collection items because no source filename is available. "
        "Set the Save block filename field."
    )


def _save_collection(
    collection: Collection,
    *,
    target_cls: type[DataObject],
    dispatch_fn: Callable[[DataObject, BlockConfig], None],
    config: BlockConfig,
) -> None:
    items = list(collection)
    if not items:
        raise ValueError("SaveData received an empty Collection; nothing to save.")
    for item in items:
        if not isinstance(item, target_cls):
            raise ValueError(
                f"SaveData(core_type={target_cls.__name__}) received a "
                f"Collection item of type {type(item).__name__}; all items must match the configured core_type."
            )
    output_dir = _require_path(config)
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("SaveData received a multi-item Collection; config.path must be a folder path.")
    output_dir.mkdir(parents=True, exist_ok=True)
    configured = config.get("filename")
    if configured is not None and not isinstance(configured, str):
        raise ValueError(f"SaveData: config['filename'] must be a string or omitted, got {type(configured).__name__}")
    for idx, item in enumerate(items, start=1):
        params = dict(config.params)
        params["path"] = str(output_dir)
        params["filename"] = _collection_item_filename(configured, item, index=idx)
        item_config = BlockConfig(params=params)
        dispatch_fn(item, item_config)


def _selected_package_save_capability(config: BlockConfig) -> str | None:
    raw = config.get("capability_id")
    if not isinstance(raw, str) or not raw.strip():
        return None
    capability_id = raw.strip()
    core_capability_ids = {capability.id for capability in _SAVE_CAPABILITIES}
    return None if capability_id in core_capability_ids else capability_id


class SaveData(IOBlock):
    """Dynamic-port core IO **output** block (ADR-028 Addendum 1 §C5/§C9).

    A single block class that exposes the ``core_type`` enum to drive
    a per-instance ``InputPort.accepted_types`` override on the
    ``data`` input port. Dispatches :meth:`save` to one of six private
    module-level ``_save_*`` functions based on ``core_type``.

    See :class:`scistudio.blocks.io.loaders.LoadData` (T-TRK-007) for the
    symmetric input-direction block.
    """

    direction: ClassVar[str] = "output"
    type_name: ClassVar[str] = "save_data"
    name: ClassVar[str] = "Save"
    description: ClassVar[str] = (
        "Save a core DataObject (Array / DataFrame / Series / Text / Artifact / CompositeData) to disk."
    )
    subcategory: ClassVar[str] = "io"

    # ADR-043 / spec ``adr-043-package-migration`` FR-002 / FR-003:
    # explicit per-(type, format) capability records. Replaces the
    # legacy ``supported_extensions`` ClassVar which has been removed.
    # The capability id convention follows spec FR-015:
    # ``core.{lower(type)}.{format_id}.save``. Each save capability is
    # paired with its load sibling via ``roundtrip_group``. Pickle
    # records carry ``notes="requires allow_pickle=True"``; the runtime
    # gate is enforced by :func:`_check_pickle_gate`. Extension
    # dispatch is derived from these records at module load time via
    # :data:`_SAVE_EXTENSION_MAP`.
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = _SAVE_CAPABILITIES

    # The ``data`` input port's accepted_types is a placeholder
    # ``[DataObject]`` here. The per-instance override in
    # :meth:`get_effective_input_ports` tightens this to the specific
    # core type chosen via ``config['core_type']``.
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject], required=True),
    ]
    # SaveData has no output ports — it is a sink. The default
    # ``IOBlock.run`` returns the configured path under the ``"path"``
    # key for downstream consumers; that key is not exposed as a typed
    # ``OutputPort`` because it is a write receipt, not a DataObject.
    output_ports: ClassVar[list[OutputPort]] = []

    # ADR-028 Addendum 1 D1: declarative dynamic-port descriptor. Mirror
    # of :attr:`LoadData.dynamic_ports` but uses ``input_port_mapping``
    # (singular per-block: SaveData drives the single ``data`` input
    # port). The frontend ``computeEffectivePorts`` helper in T-TRK-009
    # must handle both keys.
    dynamic_ports: ClassVar[dict[str, Any] | None] = {
        "source_config_key": "core_type",
        "input_port_mapping": {
            "data": {
                "Array": ["Array"],
                "DataFrame": ["DataFrame"],
                "Series": ["Series"],
                "Text": ["Text"],
                "Artifact": ["Artifact"],
                "CompositeData": ["CompositeData"],
            },
        },
    }

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "core_type": {
                "type": "string",
                "enum": list(_CORE_TYPE_MAP.keys()),
                "default": "DataFrame",
                "ui_priority": 0,
            },
            "filename": {
                "type": "string",
                "title": "Filename",
                "default": "",
                "ui_priority": 2,
            },
            "overwrite": {
                "type": "boolean",
                "title": "Overwrite",
                "default": False,
                "ui_priority": 3,
            },
            # ADR-030: ``path`` is inherited from IOBlock base class via MRO merge.
            # Direction-aware post-processing auto-switches to directory_browser.
        },
        "required": ["core_type"],
    }

    def _detect_format(self, path: Path) -> str | None:
        """Resolve *path* to a stable format id via the capability map.

        ADR-043 / spec FR-003: the legacy ``supported_extensions``
        ClassVar has been removed; the per-instance ``_detect_format``
        now consults :data:`_SAVE_EXTENSION_MAP`, which is derived from
        :attr:`format_capabilities` at module load time. Compound-suffix
        matching mirrors :meth:`IOBlock._detect_format`.
        """

        if not _SAVE_EXTENSION_MAP:
            return None
        suffixes = [s.lower() for s in path.suffixes]
        for start in range(len(suffixes)):
            candidate = "".join(suffixes[start:])
            if candidate in _SAVE_EXTENSION_MAP:
                return _SAVE_EXTENSION_MAP[candidate]
        return None

    def get_effective_input_ports(self) -> list[InputPort]:
        """Return effective input ports tightened to the chosen ``core_type``.

        Reads ``self.config['core_type']`` and looks up the matching
        :class:`DataObject` subclass in :data:`_CORE_TYPE_MAP`; an
        unknown enum value falls back to :class:`DataFrame` (the
        documented default in :attr:`config_schema`).
        """
        type_name = self.config.get("core_type", "DataFrame")
        cls = _CORE_TYPE_MAP.get(type_name)
        if cls is None:
            from scistudio.blocks.io._unified_dispatch import resolve_type_class

            cls = resolve_type_class(str(type_name)) or DataFrame
        return [InputPort(name="data", accepted_types=[cls], required=True)]

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """SaveData is output-only — :meth:`load` raises.

        Use :class:`scistudio.blocks.io.loaders.LoadData` for the
        input-direction core IO block.
        """
        raise NotImplementedError("SaveData is output-only; use LoadData for input.")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Dispatch to the matching ``_save_*`` function based on ``core_type``.

        ``obj`` may be a bare :class:`DataObject` or a homogeneous
        :class:`Collection` whose items match the configured
        ``core_type``. Multi-item Collections are written as one file per
        item under the configured folder path.
        """
        type_name = config.get("core_type", "DataFrame")
        if type_name not in _CORE_TYPE_MAP:
            from scistudio.blocks.io._unified_dispatch import delegate_save, resolve_type_class

            if resolve_type_class(str(type_name)) is None:
                raise ValueError(f"Unknown core_type {type_name!r}; expected a registered DataObject type.")
            if isinstance(obj, Collection):
                raise ValueError(f"SaveData custom core_type {type_name!r} requires a single DataObject input.")

            delegate_save(obj=obj, config=config, core_type=str(type_name))
            return

        target_cls = _CORE_TYPE_MAP[type_name]
        if _selected_package_save_capability(config) is not None:
            from scistudio.blocks.io._unified_dispatch import delegate_save

            if isinstance(obj, Collection):
                raise ValueError(
                    f"SaveData package capability {config.get('capability_id')!r} requires a single DataObject input."
                )
            unwrapped = _unwrap_for_save(obj, target_cls)
            delegate_save(obj=unwrapped, config=config, core_type=str(type_name))
            return

        dispatch: dict[str, Any] = {
            "Array": _save_array,
            "DataFrame": _save_dataframe,
            "Series": _save_series,
            "Text": _save_text,
            "Artifact": _save_artifact,
            "CompositeData": _save_composite_data,
        }
        if isinstance(obj, Collection) and len(obj) > 1:
            _save_collection(obj, target_cls=target_cls, dispatch_fn=dispatch[type_name], config=config)
            return

        unwrapped = _unwrap_for_save(obj, target_cls)
        dispatch[type_name](unwrapped, config)


# ---------------------------------------------------------------------------
# Module-level private dispatch functions (NOT helper classes per
# ADR-028 Addendum 1 §C9).
# ---------------------------------------------------------------------------


def _save_array(obj: DataObject, config: BlockConfig) -> None:
    """Save :class:`Array` to ``.npy`` / ``.npz`` / ``.zarr`` / ``.parquet`` / ``.pkl``.

    ADR-031 Phase 3 (Task 18): streaming export paths are used when the
    source Array is storage-backed by zarr and the target format supports
    chunked writes. For zarr-to-zarr, ``shutil.copytree`` is used for
    zero-materialization copy. For formats that do not support chunked
    writes (``.npy``, ``.npz``), full materialization is still required.

    Pickle gating: ``.pkl`` / ``.pickle`` requires
    ``allow_pickle=True`` in the block config.
    """
    assert isinstance(obj, Array), f"Expected Array, got {type(obj).__name__}"
    path = _require_path(config)
    # ADR-043 FR-003: format dispatch through SaveData.format_capabilities.
    path, fmt = _resolve_save_path_and_format(path, Array, config, obj)
    _ensure_save_target_available(path, config)

    if _check_pickle_gate(path, config):
        data = obj.get_in_memory_data()
        with path.open("wb") as fh:
            pickle.dump(data, fh)
        return

    if fmt == "npy":
        import numpy as np

        data = obj.get_in_memory_data()
        np.save(str(path), np.asarray(data))
        return

    if fmt == "npz":
        import numpy as np

        data = obj.get_in_memory_data()
        np.savez(str(path), data=np.asarray(data))
        return

    if fmt == "zarr":
        try:
            import zarr  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - exercised when zarr missing
            raise ValueError(
                "Saving Array to .zarr requires the 'zarr' package; install it via `pip install zarr`."
            ) from exc

        # ADR-031 Phase 3: zarr-to-zarr streaming copy via store copy
        # when the source is zarr-backed. Zero materialization.
        ref = getattr(obj, "_storage_ref", None)
        if ref is not None and ref.backend == "zarr":
            _zarr_store_copy(ref.path, str(path))
            return

        import numpy as np

        data = obj.get_in_memory_data()
        arr = np.asarray(data)
        zarr.save(str(path), arr)  # type: ignore[arg-type]
        return

    if fmt == "parquet":
        # Single-column Parquet round-trip for 1D arrays. Multi-dim
        # arrays do not have a natural columnar form and are rejected
        # to avoid silent data loss.
        import numpy as np
        import pyarrow as pa
        import pyarrow.parquet as pq

        data = obj.get_in_memory_data()
        arr = np.asarray(data)
        if arr.ndim != 1:
            raise ValueError(
                f"Cannot save {arr.ndim}-D Array as single-column Parquet; "
                "only 1-D arrays are supported. Use .npy / .npz / .zarr for N-D."
            )
        table = pa.table({"value": arr})
        pq.write_table(table, str(path))
        return

    raise ValueError(
        f"Unsupported Array file extension {path.suffix.lower()!r}. "
        f"Supported extensions: {list(_supported_save_extensions(Array))} "
        f"(.pkl/.pickle require allow_pickle=True)."
    )


def _save_dataframe(obj: DataObject, config: BlockConfig) -> None:
    """Save :class:`DataFrame` to ``.csv`` / ``.tsv`` / ``.parquet`` / ``.json`` / ``.pkl``.

    ADR-031 Phase 3 (Task 18): for CSV, TSV, and Parquet formats, uses
    streaming export paths when the source DataFrame is storage-backed
    by the arrow backend. This avoids full materialisation for large
    tables. JSON export still requires full materialisation because
    ``json.dump`` needs the complete record list.
    """
    assert isinstance(obj, DataFrame), f"Expected DataFrame, got {type(obj).__name__}"
    path = _require_path(config)
    # ADR-043 FR-003: format dispatch through SaveData.format_capabilities.
    path, fmt = _resolve_save_path_and_format(path, DataFrame, config, obj)
    _ensure_save_target_available(path, config)

    if _check_pickle_gate(path, config):
        data = obj.get_in_memory_data()
        with path.open("wb") as fh:
            pickle.dump(data, fh)
        return

    # ADR-031 Phase 3: streaming paths for CSV/TSV/Parquet when
    # the source is arrow-backed.
    if fmt == "csv":
        _streaming_save_dataframe_csv(obj, path, delimiter=",")
        return

    if fmt == "tsv":
        _streaming_save_dataframe_csv(obj, path, delimiter="\t")
        return

    if fmt == "parquet":
        _streaming_save_dataframe_parquet(obj, path)
        return

    if fmt == "json":
        # JSON export requires full materialisation — json.dump needs
        # the complete record list.
        table = _dataframe_to_arrow_table(obj)
        records = table.to_pylist()
        with path.open("w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
        return

    raise ValueError(
        f"Unsupported DataFrame file extension {path.suffix.lower()!r}. "
        f"Supported extensions: {list(_supported_save_extensions(DataFrame))} "
        f"(.pkl/.pickle require allow_pickle=True)."
    )


def _save_series(obj: DataObject, config: BlockConfig) -> None:
    """Save :class:`Series` to ``.csv`` / ``.tsv`` / ``.parquet`` / ``.json`` / ``.pkl``.

    Internally converts the :class:`Series` to a single-column
    :class:`pyarrow.Table` and reuses the DataFrame write path. Column
    name is taken from :attr:`Series.value_name` (defaulting to
    ``"value"``).
    """
    assert isinstance(obj, Series), f"Expected Series, got {type(obj).__name__}"
    path = _require_path(config)
    # ADR-043 FR-003: format dispatch through SaveData.format_capabilities.
    path, fmt = _resolve_save_path_and_format(path, Series, config, obj)
    _ensure_save_target_available(path, config)

    if _check_pickle_gate(path, config):
        data = obj.get_in_memory_data()
        with path.open("wb") as fh:
            pickle.dump(data, fh)
        return

    import pyarrow as pa

    raw = obj.get_in_memory_data()
    column_name = obj.value_name or "value"
    # ``raw`` is whatever the underlying storage returns — most commonly
    # a list, numpy array, or pyarrow Table. ``pa.array`` handles list /
    # numpy; an existing Table is passed through verbatim.
    table = raw if isinstance(raw, pa.Table) else pa.table({column_name: pa.array(raw)})

    if fmt == "csv":
        import pyarrow.csv as pcsv

        pcsv.write_csv(table, str(path))
        return

    if fmt == "tsv":
        import pyarrow.csv as pcsv

        pcsv.write_csv(
            table,
            str(path),
            write_options=pcsv.WriteOptions(delimiter="\t"),
        )
        return

    if fmt == "parquet":
        import pyarrow.parquet as pq

        pq.write_table(table, str(path))
        return

    if fmt == "json":
        records = table.to_pylist()
        with path.open("w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
        return

    raise ValueError(
        f"Unsupported Series file extension {path.suffix.lower()!r}. "
        f"Supported extensions: {list(_supported_save_extensions(Series))} "
        f"(.pkl/.pickle require allow_pickle=True)."
    )


def _save_text(obj: DataObject, config: BlockConfig) -> None:
    """Save :class:`Text` to ``.txt`` / ``.md`` / ``.markdown`` / ``.html`` / ``.htm`` / ``.xml`` / ``.log`` / ``.yaml`` / ``.yml`` / ``.toml`` / ``.json``.

    The full content lives in :attr:`Text.content`; the file is
    written via :meth:`Path.write_text` with UTF-8 encoding (or the
    encoding declared on the :class:`Text` instance, if non-default).
    """
    assert isinstance(obj, Text), f"Expected Text, got {type(obj).__name__}"
    path = _require_path(config)
    path, _fmt = _resolve_save_path_and_format(path, Text, config, obj)
    _ensure_save_target_available(path, config)
    # ADR-043 FR-003: cross-check via the SaveData capability map (the
    # canonical registry-visible set). The internal ``supported`` frozenset
    # below is a permissive superset retained for backward compatibility
    # with callers that historically wrote ``.markdown`` / ``.htm``; the
    # registry-visible error message references the capability-derived
    # mapping so the user-facing supported list stays consistent across
    # blocks.
    suffix = path.suffix.lower()
    supported = {
        ".txt",
        ".md",
        ".markdown",
        ".html",
        ".htm",
        ".xml",
        ".log",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
    }
    if suffix not in supported:
        raise ValueError(
            f"Unsupported Text file extension {suffix!r}. "
            f"Supported extensions: {list(_supported_save_extensions(Text))} "
            f"(Text-specific superset: {sorted(supported)})."
        )

    if obj.content is None:
        raise ValueError("Cannot save Text with content=None; populate Text.content first.")

    encoding = obj.encoding or "utf-8"
    path.write_text(obj.content, encoding=encoding)


def _save_artifact(obj: DataObject, config: BlockConfig) -> None:
    """Save an opaque :class:`Artifact` (raw bytes + sidecar metadata).

    If the :class:`Artifact` carries an existing ``file_path``, the
    bytes are copied via :func:`shutil.copy2`. Otherwise the artifact's
    in-memory bytes (from :meth:`Artifact.get_in_memory_data`) are
    written directly. A JSON sidecar at ``<path>.meta.json`` records
    the ``mime_type`` / ``description`` / original ``file_path`` so a
    matching :func:`_load_artifact` can fully reconstruct the instance.
    """
    assert isinstance(obj, Artifact), f"Expected Artifact, got {type(obj).__name__}"
    path = _require_path(config)
    path, _fmt = _resolve_save_path_and_format(path, Artifact, config, obj)
    _ensure_save_target_available(path, config)

    if obj.file_path is not None and Path(obj.file_path).exists():
        shutil.copy2(str(obj.file_path), str(path))
    else:
        data = obj.get_in_memory_data()
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        elif isinstance(data, bytes):
            path.write_bytes(data)
        else:
            raise ValueError(
                f"Cannot save Artifact: get_in_memory_data() returned {type(data).__name__}, expected bytes or str."
            )

    sidecar = path.with_suffix(path.suffix + ".meta.json")
    sidecar.write_text(
        json.dumps(
            {
                "mime_type": obj.mime_type,
                "description": obj.description,
                "original_file_path": str(obj.file_path) if obj.file_path is not None else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _save_composite_data(obj: DataObject, config: BlockConfig) -> None:
    """Save :class:`CompositeData` as a JSON manifest + per-slot sidecar files.

    The manifest at the configured ``path`` describes the composite's
    slot names and the relative filenames where each slot was written.
    Each slot is dispatched recursively through the ``_save_*``
    family based on the slot value's runtime type. Slot files live in
    a sibling directory named ``<path.stem>_slots/``.
    """
    assert isinstance(obj, CompositeData), f"Expected CompositeData, got {type(obj).__name__}"
    path = _require_path(config)
    path, _fmt = _resolve_save_path_and_format(path, CompositeData, config, obj)
    _ensure_save_target_available(path, config)
    if path.suffix.lower() != ".json":
        raise ValueError(f"CompositeData manifest must use the .json extension, got {path.suffix!r}.")

    slots_dir = path.parent / f"{path.stem}_slots"
    slots_dir.mkdir(parents=True, exist_ok=True)

    manifest_slots: dict[str, dict[str, str]] = {}
    for slot_name in obj.slot_names:
        slot_obj = obj.get(slot_name)
        slot_type_name = _resolve_core_type_name(slot_obj)
        if slot_type_name is None:
            raise ValueError(
                f"CompositeData slot {slot_name!r} has unsupported type "
                f"{type(slot_obj).__name__}; only the six core types are "
                "supported by SaveData."
            )
        slot_filename, slot_path = _slot_path_for(slot_type_name, slots_dir, slot_name)

        # Recurse via the same dispatch table — build a per-slot config
        # that points at the per-slot file. allow_pickle is inherited
        # from the parent config so the user opt-in propagates.
        slot_config = BlockConfig(
            params={
                "core_type": slot_type_name,
                "path": str(slot_path),
                "allow_pickle": bool(config.get("allow_pickle", False)),
            }
        )
        _SLOT_DISPATCH[slot_type_name](slot_obj, slot_config)
        manifest_slots[slot_name] = {
            "core_type": slot_type_name,
            "file": str(Path(slots_dir.name) / slot_filename),
        }

    manifest = {
        "version": 1,
        "kind": "CompositeData",
        "slots": manifest_slots,
    }
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# Slot dispatch table — separate from the main dispatch so that
# :func:`_save_composite_data` can recurse without circular reference
# at module load time.
_SLOT_DISPATCH: dict[str, Any] = {
    "Array": _save_array,
    "DataFrame": _save_dataframe,
    "Series": _save_series,
    "Text": _save_text,
    "Artifact": _save_artifact,
    "CompositeData": _save_composite_data,
}
