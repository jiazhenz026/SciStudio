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
"""

from __future__ import annotations

import json
import logging
import pickle
import shutil
from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

logger = logging.getLogger(__name__)


# ADR-028 Addendum 1 §C5: hardcoded six core types. The keys are the
# string enum values exposed in ``config_schema['properties']['core_type']
# ['enum']``; the values are the concrete :class:`DataObject` subclasses
# used by :meth:`SaveData.get_effective_input_ports` to update the
# accepted-types of the ``data`` input port.
_CORE_TYPE_MAP: dict[str, type[DataObject]] = {
    "Array": Array,
    "DataFrame": DataFrame,
    "Series": Series,
    "Text": Text,
    "Artifact": Artifact,
    "CompositeData": CompositeData,
}


# Pickle file extensions that require explicit ``allow_pickle=True``
# opt-in. Treated case-insensitively.
_PICKLE_EXTENSIONS: frozenset[str] = frozenset({".pkl", ".pickle"})


# ---------------------------------------------------------------------------
# ADR-043 / spec ``adr-043-package-migration`` FR-002:
# explicit ``FormatCapability`` declarations for the SaveData six-core-type
# matrix. Capability id convention: ``core.{lower(type)}.{format_id}.save``.
# Each capability is paired with its load sibling (declared in
# ``scistudio.blocks.io.loaders.load_data``) via
# ``roundtrip_group=core.{type}.{format}``.
# ---------------------------------------------------------------------------


_PICKLE_NOTE: str = "requires allow_pickle=True"


def _save_capability(
    *,
    data_type: type[DataObject],
    type_name: str,
    format_id: str,
    extensions: tuple[str, ...],
    label: str,
    handler: str,
    notes: str | None = None,
) -> FormatCapability:
    """Build a single save-direction :class:`FormatCapability` record.

    The capability id follows the spec FR-015 convention
    ``core.{lower(type)}.{format_id}.save`` and the roundtrip group
    mirrors the matching load capability so the registry can pair
    load+save handlers via :attr:`FormatCapability.roundtrip_group`.

    Core IO records are declared ``is_default=False`` so installed
    package-specific savers (e.g. the LCMS package's
    ``scistudio-blocks-lcms.table.csv.save`` for ``(DataFrame, .csv)``)
    keep ownership of the default slot for their specialised data types
    without triggering a registration-time conflict. When no package
    declares a default for a given ``(data_type, extension)`` slot, the
    registry returns the unique non-default core capability normally per
    :meth:`BlockRegistry.find_saver_capability`.
    """

    lower_type = type_name.lower()
    return FormatCapability(
        id=f"core.{lower_type}.{format_id}.save",
        direction="save",
        data_type=data_type,
        format_id=format_id,
        extensions=extensions,
        label=label,
        block_type="SaveData",
        handler=handler,
        is_default=False,
        roundtrip_group=f"core.{lower_type}.{format_id}",
        metadata_fidelity=MetadataFidelity(level="pixel_only", notes=notes),
        is_synthesized=False,
    )


_SAVE_CAPABILITIES: tuple[FormatCapability, ...] = (
    # ----- Array -----------------------------------------------------------
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="npy",
        extensions=(".npy",),
        label="NumPy NPY",
        handler="save",
    ),
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="npz",
        extensions=(".npz",),
        label="NumPy NPZ",
        handler="save",
    ),
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="zarr",
        extensions=(".zarr",),
        label="Zarr",
        handler="save",
    ),
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet",
        handler="save",
    ),
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle",
        handler="save",
        notes=_PICKLE_NOTE,
    ),
    # ----- DataFrame -------------------------------------------------------
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="csv",
        extensions=(".csv",),
        label="CSV",
        handler="save",
    ),
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV",
        handler="save",
    ),
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet",
        handler="save",
    ),
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="json",
        extensions=(".json",),
        label="JSON",
        handler="save",
    ),
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle",
        handler="save",
        notes=_PICKLE_NOTE,
    ),
    # ----- Series ----------------------------------------------------------
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="csv",
        extensions=(".csv",),
        label="CSV",
        handler="save",
    ),
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV",
        handler="save",
    ),
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet",
        handler="save",
    ),
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="json",
        extensions=(".json",),
        label="JSON",
        handler="save",
    ),
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle",
        handler="save",
        notes=_PICKLE_NOTE,
    ),
    # ----- Text ------------------------------------------------------------
    # ``.markdown`` and ``.htm`` are accepted by ``_save_text`` (see the
    # Text-specific superset in that function) but were missing from the
    # registry-visible capability declaration, so ``find_saver_capability``
    # could not discover SaveData for those extensions (#1110).
    _save_capability(
        data_type=Text,
        type_name="Text",
        format_id="text",
        extensions=(
            ".txt",
            ".log",
            ".md",
            ".markdown",
            ".html",
            ".htm",
            ".xml",
            ".yaml",
            ".yml",
            ".toml",
        ),
        label="Text",
        handler="save",
    ),
    # Text + .json is a legacy save-only extension: ``_save_text`` writes
    # JSON files happily (just dumps ``obj.content``) but LoadData's Text
    # capability intentionally excludes ``.json`` because ``_load_text``
    # does not parse JSON. Declared as a separate capability record with
    # ``format_id="json"`` so ``find_saver_capability(Text, '.json')``
    # resolves to a Text saver without conflicting with the Text +
    # ``.json`` -> ``"text"`` mapping at the extension-map layer. Mirrors
    # the Series + json save-only legacy branch and the P1 Codex-review
    # finding on PR #1300.
    _save_capability(
        data_type=Text,
        type_name="Text",
        format_id="json",
        extensions=(".json",),
        label="Text as JSON",
        handler="save",
    ),
    # ----- Artifact (opaque catch-all saver) ------------------------------
    # ``_save_artifact`` accepts any extension at runtime — it copies bytes
    # to the configured path. The capability records below cover the
    # canonical MIME-mapped extensions AND every extension the typed core
    # savers claim, so the AppBlock wildcard-port flow (which the binner
    # maps to Artifact) can resolve a saver for the legacy
    # supported-extension union without falling through to the
    # registry's polymorphic fallback. Mirror of the corresponding
    # ``Artifact``-as-opaque-loader records on the ``LoadData`` side.
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="binary",
        extensions=(".bin", ".dat"),
        label="Binary",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="pdf",
        extensions=(".pdf",),
        label="PDF",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="png",
        extensions=(".png",),
        label="PNG",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="jpeg",
        extensions=(".jpg", ".jpeg"),
        label="JPEG",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="tiff",
        extensions=(".tif", ".tiff"),
        label="TIFF",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="csv",
        extensions=(".csv",),
        label="CSV (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="json",
        extensions=(".json",),
        label="JSON (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="npy",
        extensions=(".npy",),
        label="NumPy NPY (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="npz",
        extensions=(".npz",),
        label="NumPy NPZ (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="zarr",
        extensions=(".zarr",),
        label="Zarr (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="text",
        extensions=(
            ".txt",
            ".log",
            ".md",
            ".markdown",
            ".html",
            ".htm",
            ".xml",
            ".yaml",
            ".yml",
            ".toml",
        ),
        label="Text (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle (opaque)",
        handler="save",
        notes=_PICKLE_NOTE,
    ),
    # ----- CompositeData ---------------------------------------------------
    _save_capability(
        data_type=CompositeData,
        type_name="CompositeData",
        format_id="json",
        extensions=(".json",),
        label="Composite manifest (JSON)",
        handler="save",
    ),
)


def _legacy_save_extension_map(
    capabilities: tuple[FormatCapability, ...],
) -> dict[str, str]:
    """Derive a legacy ``extension -> format_id`` mapping from capabilities.

    Mirror of :func:`scistudio.blocks.io.loaders.load_data._legacy_extension_map`.
    The same extension may appear on multiple types (e.g. ``.parquet`` on
    Array, DataFrame, Series) but the ``format_id`` is identical across
    types, so the dict is well-defined. Conflicting format_id values
    raise :class:`RuntimeError` to surface misconfiguration.
    """

    mapping: dict[str, str] = {}
    for capability in capabilities:
        for extension in capability.extensions:
            normalized = extension.lower()
            existing = mapping.get(normalized)
            if existing is not None and existing != capability.format_id:
                raise RuntimeError(
                    f"SaveData format_capabilities declare conflicting format_id "
                    f"for extension {normalized!r}: {existing!r} vs {capability.format_id!r}"
                )
            mapping[normalized] = capability.format_id
    return mapping


_SAVE_EXTENSION_MAP: dict[str, str] = _legacy_save_extension_map(_SAVE_CAPABILITIES)


def _supported_save_extensions() -> tuple[str, ...]:
    """Return the sorted tuple of every extension declared by SaveData.

    Replaces the legacy ``sorted(SaveData.supported_extensions.keys())``
    call sites in user-facing error messages.
    """

    return tuple(sorted(_SAVE_EXTENSION_MAP.keys()))


def _resolve_save_format(path: Path) -> str | None:
    """Resolve a path's format identifier from the SaveData capability map.

    ADR-043 / spec FR-003: format dispatch is now derived from explicit
    :attr:`SaveData.format_capabilities` rather than the deleted
    ``supported_extensions`` ClassVar. Compound-suffix-first,
    case-insensitive lookup matching :meth:`IOBlock._detect_format`
    semantics.
    """

    if not _SAVE_EXTENSION_MAP:
        return None
    suffixes = [s.lower() for s in path.suffixes]
    for start in range(len(suffixes)):
        candidate = "".join(suffixes[start:])
        if candidate in _SAVE_EXTENSION_MAP:
            return _SAVE_EXTENSION_MAP[candidate]
    return None


def _require_path(config: BlockConfig) -> Path:
    """Return the configured ``path`` as a :class:`Path` or raise.

    Centralised so each ``_save_*`` function can fail loudly with the
    same message instead of duplicating the validation.
    """
    raw = config.get("path")
    if raw is None or raw == "":
        raise ValueError("SaveData requires a non-empty 'path' in config.params.")
    path = Path(str(raw))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _check_pickle_gate(path: Path, config: BlockConfig) -> bool:
    """Return ``True`` if *path* is a pickle file.

    Raises :class:`ValueError` if the file extension is ``.pkl`` /
    ``.pickle`` and ``allow_pickle`` is not explicitly ``True``. When
    pickle is enabled, an explicit security warning is logged at
    ``WARNING`` level so the user can audit the workflow run.
    """
    if path.suffix.lower() not in _PICKLE_EXTENSIONS:
        return False
    if not bool(config.get("allow_pickle", False)):
        raise ValueError(
            f"Refusing to write pickle file {path.name!r}: pickle is opt-in for "
            "security reasons. Set 'allow_pickle': True in the block config to "
            "enable pickle writes."
        )
    logger.warning(
        "SaveData: writing pickle file %r — pickle files can execute arbitrary "
        "code on load and should only be used with trusted data.",
        str(path),
    )
    return True


# ---------------------------------------------------------------------------
# ADR-031 Phase 3 (Task 18): Streaming export helpers
# ---------------------------------------------------------------------------


def _zarr_store_copy(src_path: str, dst_path: str) -> None:
    """Copy a zarr store from *src_path* to *dst_path* without materialisation.

    Uses ``shutil.copytree`` for a file-level copy of the zarr directory
    store. This copies the compressed chunks directly, avoiding any
    decompression/recompression round-trip.
    """
    dst = Path(dst_path)
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src_path, dst_path)


def _streaming_save_dataframe_csv(obj: DataObject, path: Path, delimiter: str = ",") -> None:
    """Stream a storage-backed DataFrame to CSV/TSV via row-group batches.

    Reads from the arrow backend in chunks and writes each batch to the
    output file, avoiding full materialisation of the entire table.
    """
    import pyarrow.csv as pcsv

    ref = getattr(obj, "_storage_ref", None)
    if ref is None or ref.backend != "arrow":
        # Fallback: full materialisation
        table = _dataframe_to_arrow_table(obj)  # type: ignore[arg-type]
        pcsv.write_csv(
            table,
            str(path),
            write_options=pcsv.WriteOptions(delimiter=delimiter),
        )
        return

    from scistudio.core.storage.arrow_backend import ArrowBackend

    backend = ArrowBackend()
    # Write header from first chunk, then append remaining chunks
    first_chunk = True
    with open(str(path), "wb") as fh:
        for chunk_table in backend.iter_chunks(ref, chunk_size=65536):
            pcsv.write_csv(
                chunk_table,
                fh,
                write_options=pcsv.WriteOptions(
                    delimiter=delimiter,
                    include_header=first_chunk,
                ),
            )
            first_chunk = False


def _streaming_save_dataframe_parquet(obj: DataObject, path: Path) -> None:
    """Stream a storage-backed DataFrame to Parquet via row-group batches.

    Reads from the arrow backend in chunks and writes each batch as a
    separate row group, avoiding full materialisation.
    """
    import pyarrow.parquet as pq

    ref = getattr(obj, "_storage_ref", None)
    if ref is None or ref.backend != "arrow":
        # Fallback: full materialisation
        table = _dataframe_to_arrow_table(obj)  # type: ignore[arg-type]
        pq.write_table(table, str(path))
        return

    from scistudio.core.storage.arrow_backend import ArrowBackend

    backend = ArrowBackend()
    writer = None
    try:
        for chunk_table in backend.iter_chunks(ref, chunk_size=65536):
            if writer is None:
                writer = pq.ParquetWriter(str(path), chunk_table.schema)
            writer.write_table(chunk_table)
    finally:
        if writer is not None:
            writer.close()


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
            # ADR-030: ``path`` is inherited from IOBlock base class via MRO merge.
            # Direction-aware post-processing auto-switches to directory_browser.
            "allow_pickle": {
                "type": "boolean",
                "default": False,
                "ui_priority": 2,
            },
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
        cls = _CORE_TYPE_MAP.get(type_name, DataFrame)
        return [InputPort(name="data", accepted_types=[cls], required=True)]

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """SaveData is output-only — :meth:`load` raises.

        Use :class:`scistudio.blocks.io.loaders.LoadData` for the
        input-direction core IO block.
        """
        raise NotImplementedError("SaveData is output-only; use LoadData for input.")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Dispatch to the matching ``_save_*`` function based on ``core_type``.

        ``obj`` may be a bare :class:`DataObject` (the common case) or
        a single-item :class:`Collection` whose ``item_type`` matches
        the configured ``core_type``. Mixed-type Collections are
        explicitly out-of-scope per spec §j and raise
        :class:`ValueError`.
        """
        type_name = config.get("core_type", "DataFrame")
        if type_name not in _CORE_TYPE_MAP:
            raise ValueError(f"Unknown core_type {type_name!r}; expected one of {sorted(_CORE_TYPE_MAP.keys())}.")

        # Unwrap a single-item Collection so the dispatch functions
        # always see a bare DataObject. Mixed-type Collections are
        # rejected with an explicit ValueError per spec §j.
        target_cls = _CORE_TYPE_MAP[type_name]
        unwrapped = _unwrap_for_save(obj, target_cls)

        dispatch: dict[str, Any] = {
            "Array": _save_array,
            "DataFrame": _save_dataframe,
            "Series": _save_series,
            "Text": _save_text,
            "Artifact": _save_artifact,
            "CompositeData": _save_composite_data,
        }
        dispatch[type_name](unwrapped, config)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unwrap_for_save(
    obj: DataObject | Collection,
    target_cls: type[DataObject],
) -> DataObject:
    """Unwrap a single-item :class:`Collection` or return the bare object.

    Per spec §j, mixed-type Collections (where some item is not a
    ``target_cls`` instance) raise :class:`ValueError`. A Collection
    of all-``target_cls`` items with exactly one element is unwrapped
    transparently. A Collection of length > 1 also raises because the
    save dispatch functions write a single file at the configured path.
    """
    if isinstance(obj, Collection):
        items = list(obj)
        if not items:
            raise ValueError("SaveData received an empty Collection; nothing to save.")
        if len(items) > 1:
            raise ValueError(
                f"SaveData received a Collection of {len(items)} items; "
                "core SaveData writes one file at the configured path. "
                "Iterate over the Collection upstream and call SaveData per item."
            )
        only = items[0]
        if not isinstance(only, target_cls):
            raise ValueError(
                f"SaveData(core_type={target_cls.__name__}) received a "
                f"Collection item of type {type(only).__name__}; mixed-type "
                "Collections are out-of-scope per ADR-028 Addendum 1 §C9."
            )
        return only
    if not isinstance(obj, target_cls):
        raise ValueError(
            f"SaveData(core_type={target_cls.__name__}) received an instance of "
            f"{type(obj).__name__}; the input must be a {target_cls.__name__} "
            "instance (or a single-item Collection thereof)."
        )
    return obj


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
    fmt = _resolve_save_format(path)

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
        f"Supported extensions: {list(_supported_save_extensions())} "
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
    fmt = _resolve_save_format(path)

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
        f"Supported extensions: {list(_supported_save_extensions())} "
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
    fmt = _resolve_save_format(path)

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
        f"Supported extensions: {list(_supported_save_extensions())} "
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
            f"Supported extensions: {list(_supported_save_extensions())} "
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


# ---------------------------------------------------------------------------
# Internal helpers shared by the dispatch functions
# ---------------------------------------------------------------------------


def _dataframe_to_arrow_table(obj: DataFrame) -> Any:
    """Coerce a :class:`DataFrame` into a :class:`pyarrow.Table`.

    ADR-031 D6: always routes through ``get_in_memory_data()`` ->
    ``to_memory()`` -> storage backend read. The former ``_arrow_table``
    backdoor is removed.
    """
    import pyarrow as pa

    raw = obj.get_in_memory_data()
    if isinstance(raw, pa.Table):
        return raw
    if isinstance(raw, dict):
        return pa.table(raw)
    if isinstance(raw, list):
        return pa.Table.from_pylist(raw)
    raise ValueError(
        f"Cannot convert DataFrame in-memory data of type {type(raw).__name__} "
        "to a pyarrow.Table; expected pa.Table, dict, or list of records."
    )


def _resolve_core_type_name(obj: DataObject) -> str | None:
    """Map a :class:`DataObject` instance to its core-type enum name.

    Returns ``None`` if *obj* is not an instance of any of the six
    supported core types. Order matters here: more specific types
    (``Array``, ``CompositeData``) come before the base ``DataObject``
    fallback.
    """
    for type_name, cls in _CORE_TYPE_MAP.items():
        if isinstance(obj, cls):
            return type_name
    return None


def _slot_path_for(
    type_name: str,
    slots_dir: Path,
    slot_name: str,
) -> tuple[str, Path]:
    """Return ``(filename, full_path)`` for a CompositeData slot file.

    The default extension per type mirrors the most common round-trip
    format used by tests: ``.csv`` for DataFrame / Series, ``.npy``
    for Array, ``.txt`` for Text, ``.bin`` for Artifact, ``.json`` for
    nested CompositeData.
    """
    default_ext = {
        "Array": ".npy",
        "DataFrame": ".csv",
        "Series": ".csv",
        "Text": ".txt",
        "Artifact": ".bin",
        "CompositeData": ".json",
    }[type_name]
    filename = f"{slot_name}{default_ext}"
    return filename, slots_dir / filename


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
