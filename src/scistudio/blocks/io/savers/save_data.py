"""SaveData -- the built-in saver that writes core data objects to files.

:class:`SaveData` is one block that can write any of the six core data types
(Array, DataFrame, Series, Text, Artifact, CompositeData). Its ``core_type``
setting picks the type, which also retypes the single ``data`` input port. The
actual file-writing work lives in small private ``_save_*`` functions in this
module; which format is written for a given extension is derived from
:attr:`SaveData.format_capabilities`. It is the write-side counterpart of
:class:`scistudio.blocks.io.loaders.LoadData`.

Security — writing (and later loading) a pickle file can run arbitrary code
---------------------------------------------------------------------------
``.pkl`` / ``.pickle`` output is written with :mod:`pickle`. Saving itself is
safe, but the matching load step runs whatever code is embedded in the file, so
a shared workflow that enables ``allow_pickle`` becomes a way to run code on
whoever later opens it. Pickle output therefore defaults to a hard refusal: it
only happens when the user explicitly enables ``allow_pickle``, and a loud
``WARNING`` is logged each time. Prefer a non-pickle format unless you control
both ends.
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
    _write_table_to_xlsx,
    _write_tables_to_xlsx,
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
from scistudio.utils.atomic_io import (
    atomic_path,
    atomic_replace_dir,
    atomic_write_bytes,
    atomic_write_text,
    atomic_writer,
)


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


def _sheet_name_of(obj: DataObject) -> str | None:
    """Return the round-trip Excel sheet name recorded at load (#1810).

    The loader stores the originating sheet name in ``user['sheet_name']`` so a
    saved workbook can reproduce it. Returns ``None`` for objects that never
    came from an .xlsx sheet.
    """
    user = getattr(obj, "user", None)
    name = user.get("sheet_name") if isinstance(user, dict) else None
    return str(name) if name else None


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


def _collection_targets_xlsx(collection: Collection, config: BlockConfig) -> bool:
    """True when a DataFrame/Series Collection should be saved as .xlsx (#1810).

    A Collection targets xlsx when the configured ``filename`` ends in ``.xlsx``,
    or — when no filename is configured — when the items carry an .xlsx source
    (the load → save round-trip case). DataFrame/Series only.
    """
    if collection.item_type not in (DataFrame, Series):
        return False
    configured = config.get("filename")
    if isinstance(configured, str) and configured.strip():
        return configured.strip().lower().endswith(".xlsx")
    for item in collection:
        _stem, name = _source_file_stem(item)
        if name.lower().endswith(".xlsx"):
            return True
    return False


def _save_collection_xlsx(collection: Collection, config: BlockConfig) -> None:
    """Save a DataFrame/Series Collection to .xlsx, grouping by source workbook (#1810).

    Items are grouped by their originating workbook (``framework.source`` stem):
    each distinct source file becomes one multi-sheet workbook (sheets named by
    ``user['sheet_name']``); every item with no source is written into ONE
    workbook named by the configured ``filename`` (owner decision). This makes
    the load → save round-trip reproduce the original file ↔ sheet grouping.
    """
    items = list(collection)
    if not items:
        raise ValueError("SaveData received an empty Collection; nothing to save.")
    output_dir = _require_path(config)
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError("SaveData received a multi-item Collection; config.path must be a folder path.")
    output_dir.mkdir(parents=True, exist_ok=True)
    configured = config.get("filename")
    if configured is not None and not isinstance(configured, str):
        raise ValueError(f"SaveData: config['filename'] must be a string or omitted, got {type(configured).__name__}")
    configured_stem = Path(configured.strip()).stem if isinstance(configured, str) and configured.strip() else ""

    # Group by the FULL source path, preserving first-seen order (P1-2): two
    # distinct workbooks that share a basename (``/run1/exp.xlsx`` and
    # ``/run2/exp.xlsx``) must stay separate, so the directory cannot be
    # stripped from the grouping key. The empty-source group ("" key) bundles
    # every source-less item into one configured-filename workbook.
    groups: dict[str, list[DataObject]] = {}
    for item in items:
        source = str(getattr(item.framework, "source", "") or "")
        key = source if source.lower().endswith(".xlsx") else ""
        groups.setdefault(key, []).append(item)

    used_names: set[str] = set()
    for key, members in groups.items():
        base_stem = Path(key).stem if key else configured_stem
        if not base_stem:
            raise ValueError(
                "SaveData cannot name an .xlsx workbook for source-less Collection items: "
                "set the Save block filename field."
            )
        # Disambiguate output filenames when distinct source paths share a
        # basename (e.g. run1/exp.xlsx vs run2/exp.xlsx -> exp.xlsx, exp-2.xlsx).
        stem = base_stem
        counter = 2
        while f"{stem}.xlsx".casefold() in used_names:
            stem = f"{base_stem}-{counter}"
            counter += 1
        used_names.add(f"{stem}.xlsx".casefold())
        named_tables = [
            (_sheet_name_of(item) or f"Sheet{idx}", _dataframe_to_arrow_table_for(item))
            for idx, item in enumerate(members, start=1)
        ]
        dest = output_dir / f"{stem}.xlsx"
        with atomic_path(dest) as tmp:
            _write_tables_to_xlsx(named_tables, tmp)


def _dataframe_to_arrow_table_for(item: DataObject) -> Any:
    """Return the Arrow table for a DataFrame or single-column Series item."""
    if isinstance(item, Series):
        import pyarrow as pa

        raw = item.get_in_memory_data()
        column_name = item.value_name or "value"
        return raw if isinstance(raw, pa.Table) else pa.table({column_name: pa.array(raw)})
    assert isinstance(item, DataFrame), f"Expected DataFrame, got {type(item).__name__}"
    return _dataframe_to_arrow_table(item)


def _delegate_save_collection(
    collection: Collection,
    *,
    target_cls: type[DataObject],
    config: BlockConfig,
    core_type: str,
) -> None:
    """Save a multi-item Collection of a package-registered type, one file per item.

    The package/custom ``core_type`` save path (e.g. ``Image`` from the imaging
    plugin) previously rejected any Collection input, so a block that emits a
    Collection of package-typed objects (e.g. the Fiji interactive block →
    core ``Save``) failed with "requires a single DataObject input" and the
    downstream blocks never received the saved outputs. This mirrors
    :func:`_save_collection` for the delegated path: validate item types, treat
    ``config.path`` as a folder, and write one file per item, delegating each to
    the owning package saver via :func:`delegate_save`.
    """
    from scistudio.blocks.io._unified_dispatch import _effective_params, delegate_save

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
    # Carry the user's effective config (format/capability/etc.) — the worker
    # builds ``BlockConfig(**config)`` so real config lives in pydantic extras,
    # not ``config.params`` (see ``_effective_params``).
    base_params = _effective_params(config)
    configured = base_params.get("filename")
    if configured is not None and not isinstance(configured, str):
        raise ValueError(f"SaveData: config['filename'] must be a string or omitted, got {type(configured).__name__}")
    for idx, item in enumerate(items, start=1):
        item_name = _collection_item_filename(configured if isinstance(configured, str) else None, item, index=idx)
        params = dict(base_params)
        # Set the FULL per-item path (folder/filename.ext). The delegated saver
        # capability is selected by the path extension (see ``selected_capability``
        # / ``_path_extension``), so a bare folder path would fail to resolve a
        # saver for the package type. ``_collection_item_filename`` carries the
        # source filename's extension.
        params["path"] = str(output_dir / item_name)
        params.pop("filename", None)
        delegate_save(obj=item, config=BlockConfig(params=params), core_type=core_type)


def _selected_package_save_capability(config: BlockConfig) -> str | None:
    raw = config.get("capability_id")
    if not isinstance(raw, str) or not raw.strip():
        return None
    capability_id = raw.strip()
    core_capability_ids = {capability.id for capability in _SAVE_CAPABILITIES}
    return None if capability_id in core_capability_ids else capability_id


class SaveData(IOBlock):
    """Write one of the six core data types to a file (the built-in "Save" block).

    A single saver block that writes an :class:`Array`, :class:`DataFrame`,
    :class:`Series`, :class:`Text`, :class:`Artifact`, or :class:`CompositeData`
    to disk. The ``core_type`` config field chooses which type to accept, and the
    single ``data`` input port is retyped to match. A multi-item
    :class:`Collection` is written as one file per item under the configured
    folder (DataFrame/Series collections from a multi-sheet ``.xlsx`` are
    regrouped back into multi-sheet workbooks).

    Ports: one input port ``data`` (required); no output port (the written path
    is returned as a receipt, not a typed port). Config: ``core_type`` (required),
    optional ``filename`` and ``overwrite``, and the inherited ``path``. Supported
    formats depend on ``core_type`` and are declared in
    :attr:`format_capabilities` — for example CSV / TSV / Parquet / JSON / XLSX
    for tabular types and NPY / NPZ / Zarr for arrays. ``.pkl`` / ``.pickle`` is
    written only when ``allow_pickle`` is explicitly enabled (see this module's
    security note).

    This is the write-side counterpart of
    :class:`scistudio.blocks.io.loaders.LoadData`.
    """

    direction: ClassVar[str] = "output"
    """Fixed to ``"output"`` — SaveData is a saver."""
    type_name: ClassVar[str] = "save_data"
    """Stable registry identifier for this block type."""
    name: ClassVar[str] = "Save"
    """Display name shown in the UI block library."""
    description: ClassVar[str] = (
        "Save a core DataObject (Array / DataFrame / Series / Text / Artifact / CompositeData) to disk."
    )
    """One-line description shown in the UI."""
    subcategory: ClassVar[str] = "io"
    """Block-library subcategory this block is grouped under."""

    # Capability id convention: ``core.{lower(type)}.{format_id}.save``. Each save
    # capability is paired with its load sibling via ``roundtrip_group``. Pickle
    # records carry ``notes="requires allow_pickle=True"``; the runtime gate is
    # ``_check_pickle_gate``. Extension dispatch is derived from these records at
    # module load time via ``_SAVE_EXTENSION_MAP``.
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = _SAVE_CAPABILITIES
    """The (type, format) pairs this saver can write, as :class:`FormatCapability`
    records. Extension-based format dispatch is derived from these."""

    # The ``data`` input port's accepted_types is a placeholder ``[DataObject]``
    # here; the per-instance override in :meth:`get_effective_input_ports`
    # tightens it to the core type chosen via ``config['core_type']``.
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject], required=True),
    ]
    """Static input ports. The single ``data`` port is retyped per instance by
    :meth:`get_effective_input_ports` from the chosen ``core_type``."""
    output_ports: ClassVar[list[OutputPort]] = []
    """Empty — SaveData is a sink. The written path comes back as a ``"path"``
    receipt from :meth:`IOBlock.run`, not as a typed output port."""

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
    """Descriptor the API and frontend read to recolour the input port live as the
    user changes ``core_type``."""

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
            # ``path`` is inherited from the IOBlock base class via MRO merge;
            # direction-aware post-processing switches it to a directory browser.
        },
        "required": ["core_type"],
    }
    """JSON-schema for the block config: ``core_type`` (enum, required),
    ``filename``, ``overwrite``, plus the inherited ``path`` field."""

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
        """Return the input port retyped to the configured ``core_type``.

        Reads ``self.config['core_type']`` and tightens the ``data`` input port's
        accepted type to the matching core type. An unknown value falls back to
        :class:`DataFrame` (the documented default).

        Returns:
            A one-element list holding the effective ``data`` input port.
        """
        type_name = self.config.get("core_type", "DataFrame")
        cls = _CORE_TYPE_MAP.get(type_name)
        if cls is None:
            from scistudio.blocks.io._unified_dispatch import resolve_type_class

            cls = resolve_type_class(str(type_name)) or DataFrame
        return [InputPort(name="data", accepted_types=[cls], required=True)]

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """``SaveData`` is output-only; :meth:`load` always raises.

        Use :class:`scistudio.blocks.io.loaders.LoadData` to read files.

        Raises:
            NotImplementedError: always.
        """
        raise NotImplementedError("SaveData is output-only; use LoadData for input.")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Write *obj* using the writer for the configured ``core_type``.

        ``obj`` may be a single :class:`DataObject` or a homogeneous
        :class:`Collection` whose items match ``core_type``. A multi-item
        Collection is written as one file per item under the configured folder;
        DataFrame/Series collections destined for ``.xlsx`` are regrouped into
        multi-sheet workbooks instead.

        Args:
            obj: The object or Collection to write.
            config: Block config; reads ``core_type``, ``path``, ``filename``,
                and the optional ``allow_pickle`` opt-in.

        Raises:
            ValueError: if ``core_type`` is unknown, or a package capability is
                selected with a multi-item Collection input.
        """
        type_name = config.get("core_type", "DataFrame")
        if type_name not in _CORE_TYPE_MAP:
            from scistudio.blocks.io._unified_dispatch import delegate_save, resolve_type_class

            resolved_cls = resolve_type_class(str(type_name))
            if resolved_cls is None:
                raise ValueError(f"Unknown core_type {type_name!r}; expected a registered DataObject type.")
            # A multi-item Collection of the package type is written one file per
            # item (mirrors the core-type path); a single-item Collection or bare
            # object is unwrapped and delegated. The engine wraps block outputs in
            # Collections (ADR-020), so the input here is normally a Collection.
            if isinstance(obj, Collection) and len(obj) > 1:
                _delegate_save_collection(obj, target_cls=resolved_cls, config=config, core_type=str(type_name))
                return
            unwrapped = _unwrap_for_save(obj, resolved_cls)
            delegate_save(obj=unwrapped, config=config, core_type=str(type_name))
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
        if isinstance(obj, Collection):
            # #1810: xlsx Collections regroup by source workbook into multi-sheet
            # files instead of the one-file-per-item default. This runs for ANY
            # length (P1-1): a single-sheet workbook loads as a length-one
            # Collection, and unwrapping it to a bare DataFrame would resolve the
            # folder path to the default CSV format and silently drop .xlsx.
            if _collection_targets_xlsx(obj, config):
                _save_collection_xlsx(obj, config)
                return
            if len(obj) > 1:
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
        # SECURITY (#1545 / BUG-10): pickle is opt-in (allow_pickle=True).
        # The reciprocal LoadData.pickle path executes arbitrary code on
        # load, so a shared workflow that enables allow_pickle can run code
        # on the opener's machine. _check_pickle_gate already raised unless
        # the user opted in and logged a loud WARNING; we only reach here
        # for an explicit opt-in.
        data = obj.get_in_memory_data()
        # BUG-2 (#1516): atomic temp+fsync+os.replace so a crash mid-dump
        # leaves any prior artifact intact instead of a truncated .pkl.
        with atomic_writer(path, mode="wb") as fh:
            pickle.dump(data, fh)
        return

    if fmt == "npy":
        import numpy as np

        data = obj.get_in_memory_data()
        # BUG-2 (#1516): np.save writes directly to the path and would
        # truncate a prior artifact on a crash; serialise to a buffer and
        # write atomically. np.save appends ".npy" when missing, so target
        # the buffer (which never rewrites the suffix) and keep ``path``.
        import io as _io

        buf = _io.BytesIO()
        np.save(buf, np.asarray(data))
        atomic_write_bytes(path, buf.getvalue())
        return

    if fmt == "npz":
        import numpy as np

        data = obj.get_in_memory_data()
        # BUG-2 (#1516): same atomic-buffer pattern as .npy.
        import io as _io

        buf = _io.BytesIO()
        np.savez(buf, data=np.asarray(data))
        atomic_write_bytes(path, buf.getvalue())
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
        # BUG-2 (#1516): a zarr store is a *directory* tree; build it in a
        # temp sibling dir and atomically swap it into place so a crash
        # mid-copy never leaves a half-written store at ``path``.
        ref = getattr(obj, "_storage_ref", None)
        if ref is not None and ref.backend == "zarr":
            with atomic_replace_dir(path) as tmp_dir:
                _zarr_store_copy(ref.path, str(tmp_dir))
            return

        import numpy as np

        data = obj.get_in_memory_data()
        arr = np.asarray(data)
        with atomic_replace_dir(path) as tmp_dir:
            # FIND-D (#1740): persist axis labels as a store attribute so
            # ``LoadData`` can restore ``Array.axes`` on reload. The previous
            # ``zarr.save`` wrote no attrs, so reloaded arrays lost their axes
            # (and their shape, because the loader's sidecar probe also missed).
            z = zarr.open_array(str(tmp_dir), mode="w", shape=arr.shape, dtype=arr.dtype)
            z[:] = arr
            z.attrs["axes"] = [str(a) for a in getattr(obj, "axes", []) or []]
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
        # BUG-2 (#1516): write parquet via the atomic context manager.
        with atomic_writer(path, mode="wb") as fh:
            pq.write_table(table, fh)
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
        # SECURITY (#1545 / BUG-10): pickle is opt-in; the LoadData pickle
        # path executes arbitrary code on load. _check_pickle_gate logged a
        # loud WARNING and only returns True for an explicit opt-in.
        data = obj.get_in_memory_data()
        # BUG-2 (#1516): atomic write so a crash mid-dump keeps the prior
        # artifact intact.
        with atomic_writer(path, mode="wb") as fh:
            pickle.dump(data, fh)
        return

    # ADR-031 Phase 3: streaming paths for CSV/TSV/Parquet when
    # the source is arrow-backed.
    # BUG-2 (#1516): the streaming exporters write directly by path; wrap
    # each in atomic_path so the chunked write lands on a temp sibling and
    # only atomically replaces ``path`` once the full file is durable.
    if fmt == "csv":
        with atomic_path(path) as tmp:
            _streaming_save_dataframe_csv(obj, tmp, delimiter=",")
        return

    if fmt == "tsv":
        with atomic_path(path) as tmp:
            _streaming_save_dataframe_csv(obj, tmp, delimiter="\t")
        return

    if fmt == "parquet":
        with atomic_path(path) as tmp:
            _streaming_save_dataframe_parquet(obj, tmp)
        return

    if fmt == "json":
        # JSON export requires full materialisation — json.dump needs
        # the complete record list.
        table = _dataframe_to_arrow_table(obj)
        records = table.to_pylist()
        # BUG-2 (#1516): atomic JSON write.
        with atomic_writer(path, mode="w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
        return

    if fmt == "xlsx":
        # #1810: a single DataFrame -> single sheet. The sheet name is the
        # round-trip ``user['sheet_name']`` when present, else "Sheet1".
        table = _dataframe_to_arrow_table(obj)
        sheet_name = _sheet_name_of(obj) or "Sheet1"
        with atomic_path(path) as tmp:
            _write_table_to_xlsx(table, tmp, sheet_name)
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
        # SECURITY (#1545 / BUG-10): pickle is opt-in; LoadData unpickling
        # executes arbitrary code. _check_pickle_gate already logged a loud
        # WARNING and only returns True for an explicit opt-in.
        data = obj.get_in_memory_data()
        # BUG-2 (#1516): atomic write.
        with atomic_writer(path, mode="wb") as fh:
            pickle.dump(data, fh)
        return

    import pyarrow as pa

    raw = obj.get_in_memory_data()
    column_name = obj.value_name or "value"
    # ``raw`` is whatever the underlying storage returns — most commonly
    # a list, numpy array, or pyarrow Table. ``pa.array`` handles list /
    # numpy; an existing Table is passed through verbatim.
    table = raw if isinstance(raw, pa.Table) else pa.table({column_name: pa.array(raw)})

    # BUG-2 (#1516): pyarrow writers take a path/handle; route every format
    # through the atomic helpers so a crash mid-write keeps the prior file.
    if fmt == "csv":
        import pyarrow.csv as pcsv

        with atomic_path(path) as tmp:
            pcsv.write_csv(table, str(tmp))
        return

    if fmt == "tsv":
        import pyarrow.csv as pcsv

        with atomic_path(path) as tmp:
            pcsv.write_csv(
                table,
                str(tmp),
                write_options=pcsv.WriteOptions(delimiter="\t"),
            )
        return

    if fmt == "parquet":
        import pyarrow.parquet as pq

        with atomic_writer(path, mode="wb") as fh:
            pq.write_table(table, fh)
        return

    if fmt == "json":
        records = table.to_pylist()
        with atomic_writer(path, mode="w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2)
        return

    if fmt == "xlsx":
        # #1810: Series -> single-column single sheet.
        sheet_name = _sheet_name_of(obj) or "Sheet1"
        with atomic_path(path) as tmp:
            _write_table_to_xlsx(table, tmp, sheet_name)
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
    # BUG-2 (#1516): atomic text write so an overwrite crash keeps the old
    # file readable instead of truncating it.
    atomic_write_text(path, obj.content, encoding=encoding)


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

    # BUG-2 (#1516): every artifact byte/string write goes through the
    # atomic helpers so a crash mid-write leaves any prior artifact intact.
    if obj.file_path is not None and Path(obj.file_path).exists():
        # shutil.copy2 writes directly into the destination; copy into a
        # temp sibling and atomically replace.
        with atomic_path(path) as tmp:
            shutil.copy2(str(obj.file_path), str(tmp))
    else:
        data = obj.get_in_memory_data()
        if isinstance(data, str):
            atomic_write_text(path, data, encoding="utf-8")
        elif isinstance(data, bytes):
            atomic_write_bytes(path, data)
        else:
            raise ValueError(
                f"Cannot save Artifact: get_in_memory_data() returned {type(data).__name__}, expected bytes or str."
            )

    sidecar = path.with_suffix(path.suffix + ".meta.json")
    atomic_write_text(
        sidecar,
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
            # FIND-A (#1740): the manifest key must match what LoadData reads.
            # ``_load_composite_data`` reads ``"path"`` (its documented schema);
            # writing ``"file"`` here made every composite ``.json`` reload fail.
            "path": str(Path(slots_dir.name) / slot_filename),
        }

    manifest = {
        "version": 1,
        "kind": "CompositeData",
        "slots": manifest_slots,
    }
    # BUG-2 (#1516): atomic manifest write. Per-slot files are written by
    # the recursive _save_* dispatch above, each of which is itself atomic.
    atomic_write_text(
        path,
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
