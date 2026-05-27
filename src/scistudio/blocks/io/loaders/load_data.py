"""LoadData -- dynamic-port core IO loader (ADR-028 Addendum 1, ADR-043).

Canonical core IO loader block per ADR-028 Addendum 1 §C5 (hardcoded
``_CORE_TYPE_MAP``) and §C9 (private module-level dispatch functions
instead of helper classes). ADR-043 / spec ``adr-043-package-migration``
FR-001 / FR-003 added the explicit :class:`FormatCapability` records on
:attr:`LoadData.format_capabilities`; format dispatch is derived from
those records via :func:`_legacy_extension_map` and held in
:data:`_LOAD_EXTENSION_MAP`.

Module-level helpers were extracted to private sibling modules per
issue #1459 (Phase 2 of #1427) so this file stays under the 750-LOC
god-file threshold. Path D satisfies §C9 verbatim: every extracted
sibling contains only ``_underscore`` module-level functions, no
classes.

- :mod:`scistudio.blocks.io.loaders._capability` — ``FormatCapability``
  declarations, ``_LOAD_EXTENSION_MAP``, ``_resolve_format``.
- :mod:`scistudio.blocks.io.loaders._helpers` — ``_resolve_path``,
  ``_check_pickle_allowed``, ``_CORE_TYPE_MAP``, ``_TEXT_FORMAT_MAP``,
  ``_MIME_GUESS``.

The helper symbols are re-imported below so legacy callers that do
``from scistudio.blocks.io.loaders.load_data import _LOAD_CAPABILITIES``
(test code, mostly) continue to work without change. The load side has
no streaming sibling: pyarrow readers already operate batch-by-batch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.io.capabilities import FormatCapability
from scistudio.blocks.io.io_block import IOBlock

# Re-exports from the private sibling modules. The unused-import noqa
# tags are intentional: legacy callers import these names directly from
# :mod:`scistudio.blocks.io.loaders.load_data`, so they must remain
# present at this module's top level.
from scistudio.blocks.io.loaders._capability import (
    _LOAD_CAPABILITIES,
    _LOAD_EXTENSION_MAP,
    _PICKLE_NOTE,  # noqa: F401  re-export for backward compat
    _legacy_extension_map,  # noqa: F401  re-export for backward compat
    _load_capability,  # noqa: F401  re-export for backward compat
    _resolve_format,
    _supported_load_extensions,
)
from scistudio.blocks.io.loaders._helpers import (
    _CORE_TYPE_MAP,
    _LOGGER,  # noqa: F401  re-export for backward compat
    _MIME_GUESS,
    _TEXT_FORMAT_MAP,
    _check_pickle_allowed,
    _resolve_path,
)
from scistudio.core.meta.framework import FrameworkMeta
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text


def _source_framework(path: Path) -> FrameworkMeta:
    """Return framework metadata that preserves the boundary source path."""

    return FrameworkMeta(source=str(path))


class LoadData(IOBlock):
    """Dynamic-port core IO loader covering the six core ``DataObject`` types.

    The block exposes a single output port ``data`` whose ``accepted_types``
    are computed from the ``core_type`` config field via
    :meth:`get_effective_output_ports`. The ``dynamic_ports`` ClassVar is
    the static descriptor that the API and frontend consume to render the
    enum-driven port-color UI.

    See ADR-028 Addendum 1 §C5 / §C9 and the implementation standards doc
    T-TRK-007 (lines 1243-1446) for the full contract.
    """

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "load_data"
    name: ClassVar[str] = "Load"
    description: ClassVar[str] = (
        "Load a single core DataObject (Array, DataFrame, Series, Text, "
        "Artifact, or CompositeData) from a file. The output port type "
        "follows the configured core_type."
    )
    subcategory: ClassVar[str] = "io"

    # ADR-043 / spec ``adr-043-package-migration`` FR-001 / FR-003:
    # explicit per-(type, format) capability records. Replaces the
    # legacy ``supported_extensions`` ClassVar which has been removed.
    # The capability id convention follows spec FR-015:
    # ``core.{lower(type)}.{format_id}.load``. Pickle records carry
    # ``notes="requires allow_pickle=True"``; the runtime gate is
    # enforced by :func:`_check_pickle_allowed`. Extension dispatch is
    # derived from these records at module load time via
    # :data:`_LOAD_EXTENSION_MAP`.
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = _LOAD_CAPABILITIES

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[DataObject]),
    ]

    dynamic_ports: ClassVar[dict[str, Any] | None] = {
        "source_config_key": "core_type",
        "output_port_mapping": {
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
        },
        "required": ["core_type"],
    }

    def _detect_format(self, path: Path) -> str | None:
        """Resolve *path* to a stable format id via the capability map.

        ADR-043 / spec FR-003: the legacy ``supported_extensions``
        ClassVar has been removed; the per-instance ``_detect_format``
        now consults :data:`_LOAD_EXTENSION_MAP`, which is derived from
        :attr:`format_capabilities` at module load time. Compound-suffix
        matching mirrors :meth:`IOBlock._detect_format`.
        """

        if not _LOAD_EXTENSION_MAP:
            return None
        suffixes = [s.lower() for s in path.suffixes]
        for start in range(len(suffixes)):
            candidate = "".join(suffixes[start:])
            if candidate in _LOAD_EXTENSION_MAP:
                return _LOAD_EXTENSION_MAP[candidate]
        return None

    def get_effective_output_ports(self) -> list[OutputPort]:
        """Return the per-instance output port for the configured ``core_type``.

        Reads ``self.config["core_type"]`` (defaulting to ``"DataFrame"``)
        and returns a single ``OutputPort`` whose ``accepted_types`` is
        ``[_CORE_TYPE_MAP[core_type]]``. Unknown enum values fall back to
        ``DataFrame`` so the validator never sees a malformed port; the
        run-time ``load()`` call still raises ``ValueError`` for unknown
        enum values, so the frontend can show the error path.

        When ``config["path"]`` is a list, the output port is annotated with
        ``is_collection=True`` to signal to the frontend and runtime that the
        block produces a Collection rather than a bare DataObject.
        """
        type_name = self.config.get("core_type", "DataFrame")
        cls = _CORE_TYPE_MAP.get(type_name)
        if cls is None:
            from scistudio.blocks.io._unified_dispatch import resolve_type_class

            cls = resolve_type_class(str(type_name)) or DataObject
        is_multi = isinstance(self.config.get("path"), list)
        return [OutputPort(name="data", accepted_types=[cls], is_collection=is_multi)]

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Dispatch to one of the six private ``_load_*`` functions.

        ADR-031 D4: ``output_dir`` is passed through from :meth:`IOBlock.run`.
        Loaders that produce tabular data use :meth:`persist_table` to
        write to arrow storage. Array/npy loaders use the simple path
        (base class auto-flush handles persistence). Artifact and Text
        loaders are exempt.

        The selected function is determined by ``config["core_type"]``;
        unknown values raise ``ValueError`` rather than silently picking
        a default.

        When ``config["path"]`` is a list of strings, each file is loaded
        individually and the results are packed into a homogeneous
        :class:`Collection`. All files in a multi-path list must produce the
        same ``core_type``; the Collection ``item_type`` is derived from the
        configured ``core_type``.

        When ``config["path"]`` is a single string, the pre-existing single-
        object return behavior is preserved.
        """
        type_name = config.get("core_type", "DataFrame")
        if type_name not in _CORE_TYPE_MAP:
            from scistudio.blocks.io._unified_dispatch import delegate_load, resolve_type_class

            if resolve_type_class(str(type_name)) is None:
                raise ValueError(f"Unknown core_type: {type_name}")

            return delegate_load(config=config, output_dir=output_dir, core_type=str(type_name))

        # ADR-031: dispatch table. Functions that don't need output_dir
        # are wrapped with lambdas to accept and ignore the parameter,
        # keeping a uniform (config, output_dir) call signature.
        # ADR-043 FR-003: ``self`` is threaded into ``_load_text`` so the
        # capability-backed format dispatch resolves through the active
        # block instance.
        dispatch: dict[str, Any] = {
            "Array": self._load_array_with_persist,
            "DataFrame": self._load_dataframe_with_persist,
            "Series": self._load_series_with_persist,
            "Text": lambda cfg, od: _load_text(cfg, block=self),
            "Artifact": lambda cfg, od: _load_artifact(cfg),
            "CompositeData": self._load_composite_with_persist,
        }
        if type_name not in dispatch:
            raise ValueError(f"Unknown core_type: {type_name}")

        raw_path = config.get("path")
        if isinstance(raw_path, list):
            # Multi-path: load each file and return a Collection.
            loader = dispatch[type_name]
            item_cls = _CORE_TYPE_MAP[type_name]
            shared_params: dict[str, Any] = {"core_type": type_name}
            allow_pickle = config.get("allow_pickle")
            if allow_pickle is not None:
                shared_params["allow_pickle"] = allow_pickle
            items: list[DataObject] = []
            for single_path in raw_path:
                single_config = BlockConfig(params={**shared_params, "path": str(single_path)})
                items.append(loader(single_config, output_dir))
            return Collection(items=items, item_type=item_cls)

        result: DataObject = dispatch[type_name](config, output_dir)
        return result

    def _load_array_with_persist(self, config: BlockConfig, output_dir: str) -> Array:
        """Load Array and persist to zarr storage.

        ADR-031 Addendum 1: uses :meth:`persist_array` to write the numpy
        array to storage and returns a reference-only Array.
        """
        arr_obj = _load_array(config, block=self)
        # If the array already has a storage_ref (e.g. zarr source), skip persist.
        if arr_obj.storage_ref is not None:
            return arr_obj
        # If in-memory data is present, persist it.
        data = getattr(arr_obj, "_data", None)
        if data is not None and output_dir:
            ref = self.persist_array(data, tuple(data.shape), data.dtype, output_dir)
            arr_obj._storage_ref = ref  # type: ignore[attr-defined]
            del arr_obj._data  # type: ignore[attr-defined]
        return arr_obj

    def _load_dataframe_with_persist(self, config: BlockConfig, output_dir: str) -> DataFrame:
        """Load DataFrame and persist to arrow storage.

        ADR-031 D4: uses :meth:`persist_table` to write the arrow table
        to storage and returns a reference-only DataFrame.
        """
        df = _load_dataframe(config, block=self)
        # If the dataframe has an in-memory table, persist it.
        table = getattr(df, "_arrow_table", None)
        if table is not None and output_dir:
            ref = self.persist_table(table, output_dir)
            df._storage_ref = ref
            # Clean up in-memory reference (the data is now in storage)
            del df._arrow_table  # type: ignore[attr-defined]
        return df

    def _load_series_with_persist(self, config: BlockConfig, output_dir: str) -> Series:
        """Load Series and persist to arrow storage.

        ADR-031: fixes the payload-loss bug where ``_load_series`` returned
        a Series with no data. Now writes the underlying arrow table to
        storage via :meth:`persist_table`.
        """
        return _load_series(config, self, output_dir)

    def _load_composite_with_persist(self, config: BlockConfig, output_dir: str) -> CompositeData:
        """Load CompositeData, passing output_dir for slot persistence."""
        return _load_composite_data(config, self, output_dir)

    def save(self, obj: DataObject | Any, config: BlockConfig) -> None:
        """``LoadData`` is input-only; ``save()`` always raises.

        Per ADR-028 Addendum 1 §C9 the loader and saver are separate
        concrete classes; the egress concrete class is ``SaveData``
        (T-TRK-008).
        """
        raise NotImplementedError("LoadData is input-only; use SaveData")


# ---------------------------------------------------------------------------
# Module-level private dispatch functions (NOT helper classes per Addendum 1).
# Each function takes the validated ``BlockConfig`` and returns a fully
# constructed core ``DataObject``. Failure modes raise descriptive
# ``ValueError`` / ``FileNotFoundError`` so the calling block surfaces a
# clear error to the workflow runtime instead of silently degrading.
# ---------------------------------------------------------------------------


def _load_array(config: BlockConfig, block: LoadData | None = None) -> Array:
    """Load Array from .npy / .npz / .zarr / .parquet (single column) / .pkl.

    .npy and .npz are loaded via :func:`numpy.load`. .zarr stores create a
    metadata-only :class:`Array` with a :class:`StorageReference` so the
    actual chunked data stays lazy. Single-column .parquet falls back to
    pyarrow. Pickle support honours :func:`_check_pickle_allowed`.

    ADR-043 / spec FR-003: format dispatch is routed through
    :func:`_resolve_format` which derives the extension -> format_id
    mapping from :attr:`LoadData.format_capabilities`.
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: array source not found: {path}")

    # Resolve format via the LoadData capability map (ADR-043 FR-003).
    fmt = _resolve_format(path, block)

    if _check_pickle_allowed(path, config):
        import pickle

        with path.open("rb") as fh:
            obj = pickle.load(fh)
        if isinstance(obj, Array):
            return obj
        import numpy as np

        arr = np.asarray(obj)
        result = Array(
            axes=[f"axis_{i}" for i in range(arr.ndim)],
            shape=tuple(arr.shape),
            dtype=str(arr.dtype),
            framework=_source_framework(path),
        )
        result._data = arr  # type: ignore[attr-defined]
        return result

    if fmt == "npy":
        import numpy as np

        arr = np.load(path)
        result = Array(
            axes=[f"axis_{i}" for i in range(arr.ndim)],
            shape=tuple(arr.shape),
            dtype=str(arr.dtype),
            framework=_source_framework(path),
        )
        result._data = arr  # type: ignore[attr-defined]
        return result

    if fmt == "npz":
        import numpy as np

        with np.load(path) as npz:
            keys = list(npz.keys())
            if not keys:
                raise ValueError(f"LoadData: .npz archive is empty: {path}")
            arr = npz[keys[0]]
        result = Array(
            axes=[f"axis_{i}" for i in range(arr.ndim)],
            shape=tuple(arr.shape),
            dtype=str(arr.dtype),
            framework=_source_framework(path),
        )
        result._data = arr  # type: ignore[attr-defined]
        return result

    if fmt == "zarr" or (path.is_dir() and ((path / ".zgroup").exists() or (path / ".zarray").exists())):
        # Build a metadata-only Array with a StorageReference; chunked data
        # stays lazy and is materialised by ZarrBackend on access.
        from scistudio.core.storage.ref import StorageReference

        ref = StorageReference(backend="zarr", path=str(path), format="zarr")
        # Try to read shape/dtype from .zarray sidecar if present.
        zarray_path = path / ".zarray"
        shape: tuple[int, ...] | None = None
        dtype: str | None = None
        if zarray_path.exists():
            try:
                meta = json.loads(zarray_path.read_text(encoding="utf-8"))
                shape = tuple(meta.get("shape", []))
                dtype = str(meta.get("dtype")) if meta.get("dtype") is not None else None
            except (json.JSONDecodeError, OSError) as exc:
                raise ValueError(f"LoadData: cannot parse .zarray metadata at {zarray_path}: {exc}") from exc
        ndim = len(shape) if shape is not None else 0
        return Array(
            axes=[f"axis_{i}" for i in range(ndim)],
            shape=shape,
            dtype=dtype,
            framework=_source_framework(path),
            storage_ref=ref,
        )

    if fmt == "parquet":
        import pyarrow.parquet as pq

        table = pq.read_table(str(path))
        if table.num_columns != 1:
            raise ValueError(
                f"LoadData(core_type='Array') expects a single-column .parquet file, "
                f"got {table.num_columns} columns in {path}"
            )
        arr = table.column(0).to_numpy()
        result = Array(
            axes=[f"axis_{i}" for i in range(arr.ndim)],
            shape=tuple(arr.shape),
            dtype=str(arr.dtype),
            framework=_source_framework(path),
        )
        result._data = arr  # type: ignore[attr-defined]
        return result

    raise ValueError(
        f"LoadData(core_type='Array') does not support extension {path.suffix.lower()!r}. "
        f"Supported extensions: {list(_supported_load_extensions())} "
        f"(.pkl/.pickle require allow_pickle=True)."
    )


def _load_dataframe(config: BlockConfig, block: LoadData | None = None) -> DataFrame:
    """Load DataFrame from .csv / .tsv / .parquet / .json / .pkl / .pickle.

    Uses pyarrow for columnar formats (CSV / Parquet) and pyarrow's JSON
    reader for record-oriented JSON. Pickle is gated via
    :func:`_check_pickle_allowed` and uses :mod:`pickle` from the stdlib
    rather than pulling in pandas (which is not a core dependency).

    The constructed :class:`DataFrame` carries the underlying pyarrow
    Table on the ``_arrow_table`` attribute (matching the deleted
    csv_adapter / parquet_adapter convention) so downstream blocks can
    materialise data without re-parsing the file.

    ADR-043 / spec FR-003: format dispatch is routed through
    :func:`_resolve_format` which derives the extension -> format_id
    mapping from :attr:`LoadData.format_capabilities`.
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: dataframe source not found: {path}")

    fmt = _resolve_format(path, block)

    if _check_pickle_allowed(path, config):
        import pickle

        with path.open("rb") as fh:
            obj = pickle.load(fh)
        if isinstance(obj, DataFrame):
            return obj
        raise ValueError(
            f"LoadData(core_type='DataFrame'): pickle at {path} unpickled to "
            f"{type(obj).__name__}, expected scistudio.core.types.dataframe.DataFrame"
        )

    if fmt in {"csv", "tsv"}:
        import pyarrow.csv as pcsv

        delimiter = "\t" if fmt == "tsv" else ","
        parse_opts = pcsv.ParseOptions(delimiter=delimiter)
        table = pcsv.read_csv(str(path), parse_options=parse_opts)
        df = DataFrame(
            columns=list(table.column_names),
            row_count=int(table.num_rows),
            framework=_source_framework(path),
        )
        df._arrow_table = table  # type: ignore[attr-defined]
        return df

    if fmt == "parquet":
        import pyarrow.parquet as pq

        table = pq.read_table(str(path))
        df = DataFrame(
            columns=list(table.column_names),
            row_count=int(table.num_rows),
            framework=_source_framework(path),
        )
        df._arrow_table = table  # type: ignore[attr-defined]
        return df

    if fmt == "json":
        # pyarrow.json expects newline-delimited JSON records. For the
        # common "single JSON document containing a list of records" or
        # "single JSON document containing a {column: [values]} dict"
        # shapes we round-trip via the stdlib json module so we don't
        # take a hard dependency on pandas.
        import pyarrow as pa

        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            # records orientation
            table = pa.Table.from_pylist(raw)
        elif isinstance(raw, dict):
            # columns orientation
            table = pa.Table.from_pydict(raw)
        else:
            raise ValueError(
                f"LoadData(core_type='DataFrame'): JSON at {path} must be a list of records "
                f"or a dict of columns, got {type(raw).__name__}"
            )
        df = DataFrame(
            columns=list(table.column_names),
            row_count=int(table.num_rows),
            framework=_source_framework(path),
        )
        df._arrow_table = table  # type: ignore[attr-defined]
        return df

    raise ValueError(
        f"LoadData(core_type='DataFrame') does not support extension {path.suffix.lower()!r}. "
        f"Supported extensions: {list(_supported_load_extensions())} "
        f"(.pkl/.pickle require allow_pickle=True)."
    )


def _load_series(config: BlockConfig, block: Any = None, output_dir: str = "") -> Series:
    """Load Series from .csv / .tsv (single column) / .parquet / .pkl.

    ADR-031: fixes the payload-loss bug. The underlying arrow table is
    now persisted to storage via ``block.persist_table()`` and the
    resulting :class:`Series` carries a ``storage_ref``.

    Delegates the heavy lifting to :func:`_load_dataframe` for tabular
    formats and then asserts a single column. Pickle is gated via
    :func:`_check_pickle_allowed` and uses :mod:`pickle` from the stdlib
    rather than pulling in pandas.
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: series source not found: {path}")

    detector = block if isinstance(block, LoadData) else None
    fmt = _resolve_format(path, detector)

    if _check_pickle_allowed(path, config):
        import pickle

        with path.open("rb") as fh:
            obj = pickle.load(fh)
        if isinstance(obj, Series):
            return obj
        raise ValueError(
            f"LoadData(core_type='Series'): pickle at {path} unpickled to "
            f"{type(obj).__name__}, expected scistudio.core.types.series.Series"
        )

    if fmt in {"csv", "tsv", "parquet"}:
        # Reuse the dataframe loader and assert a single column.
        df = _load_dataframe(config, block=detector)
        if df.columns is None or len(df.columns) != 1:
            raise ValueError(
                f"LoadData(core_type='Series') expects a single-column tabular file, "
                f"got {len(df.columns) if df.columns else 0} columns in {path}"
            )
        # ADR-031: persist the arrow table to storage to fix payload loss.
        table = getattr(df, "_arrow_table", None)
        storage_ref = None
        if table is not None and block is not None and output_dir:
            storage_ref = block.persist_table(table, output_dir)
        return Series(
            index_name=None,
            value_name=df.columns[0],
            length=df.row_count,
            framework=_source_framework(path),
            storage_ref=storage_ref,
        )

    raise ValueError(
        f"LoadData(core_type='Series') does not support extension {path.suffix.lower()!r}. "
        f"Supported extensions: {list(_supported_load_extensions())} "
        f"(.pkl/.pickle require allow_pickle=True)."
    )


def _load_text(config: BlockConfig, block: LoadData | None = None) -> Text:
    """Load Text from .txt / .md / .markdown / .html / .htm / .xml / .log / .yaml / .yml / .toml.

    Reads the file via :meth:`pathlib.Path.read_text` (UTF-8) and infers
    the ``format`` field from the extension via :data:`_TEXT_FORMAT_MAP`.

    ADR-043 / spec FR-003: gate the suffix membership check against
    :attr:`LoadData.format_capabilities` (via ``_detect_format`` ->
    :data:`_LOAD_EXTENSION_MAP`) so the capability declarations remain
    the single source of truth, and tie the error message to
    :func:`_supported_load_extensions`.
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: text source not found: {path}")

    detector = block if isinstance(block, LoadData) else None
    fmt = _resolve_format(path, detector)
    suffix = path.suffix.lower()

    # ``_detect_format`` reports any registered extension; for Text we also
    # require the suffix to live in the text-specific format map (so e.g.
    # a path with ``.npy`` cannot squeeze through as Text).
    if fmt != "text" or suffix not in _TEXT_FORMAT_MAP:
        raise ValueError(
            f"LoadData(core_type='Text') does not support extension {suffix!r}. "
            f"Supported extensions: {list(_supported_load_extensions())}; "
            f"Text-specific subset: {sorted(_TEXT_FORMAT_MAP.keys())}."
        )

    content = path.read_text(encoding="utf-8")
    return Text(
        content=content,
        format=_TEXT_FORMAT_MAP[suffix],
        encoding="utf-8",
        framework=_source_framework(path),
    )


def _load_artifact(config: BlockConfig) -> Artifact:
    """Load opaque Artifact from any file (raw bytes + filename + mime).

    Mirrors the deleted ``generic_adapter.read()``: builds an
    :class:`Artifact` whose ``file_path`` points at the source file,
    ``mime_type`` is guessed from the extension, and ``description``
    defaults to the file name. If a sidecar ``<path>.meta.json`` is
    present, its keys are merged onto the user metadata dict (so callers
    can attach format-specific descriptors without subclassing
    :class:`Artifact`).
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: artifact source not found: {path}")

    mime = _MIME_GUESS.get(path.suffix.lower(), "application/octet-stream")
    artifact = Artifact(
        file_path=path,
        mime_type=mime,
        description=path.name,
        framework=_source_framework(path),
    )

    sidecar = path.with_suffix(path.suffix + ".meta.json")
    if sidecar.exists():
        try:
            sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"LoadData: cannot parse artifact sidecar {sidecar}: {exc}") from exc
        if isinstance(sidecar_data, dict):
            artifact._user.update(sidecar_data)

    return artifact


def _load_composite_data(config: BlockConfig, block: Any = None, output_dir: str = "") -> CompositeData:
    """Load CompositeData from a JSON manifest pointing at sidecar files.

    ADR-031: accepts ``block`` and ``output_dir`` so that slot loaders
    for DataFrame/Series types can persist data to storage.

    The manifest schema is::

        {
            "slots": {
                "<slot_name>": {
                    "core_type": "<one of _CORE_TYPE_MAP keys>",
                    "path": "<relative or absolute path>",
                    "allow_pickle": false   // optional, defaults to false
                },
                ...
            }
        }

    Each slot is loaded by recursing into the appropriate ``_load_*``
    function with a synthetic :class:`BlockConfig`. Relative slot paths
    are resolved against the manifest's parent directory so manifests
    are portable. Slot type ``CompositeData`` is rejected to prevent
    unbounded recursion (manifests pointing at manifests).
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: composite manifest not found: {path}")

    if path.suffix.lower() != ".json":
        raise ValueError(f"LoadData(core_type='CompositeData') requires a .json manifest, got {path.suffix!r} ({path})")

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"LoadData: cannot parse composite manifest {path}: {exc}") from exc

    if not isinstance(manifest, dict):
        raise ValueError(f"LoadData: composite manifest must be a JSON object, got {type(manifest).__name__}")

    slots_decl = manifest.get("slots", {})
    if not isinstance(slots_decl, dict):
        raise ValueError(f"LoadData: composite manifest 'slots' must be an object, got {type(slots_decl).__name__}")

    base_dir = path.parent
    loaded_slots: dict[str, DataObject] = {}
    inner_dispatch: dict[str, Any] = {
        "Array": _load_array,
        "DataFrame": _load_dataframe,
        "Series": lambda cfg: _load_series(cfg, block, output_dir),
        "Text": _load_text,
        "Artifact": _load_artifact,
    }

    for slot_name, slot_decl in slots_decl.items():
        if not isinstance(slot_decl, dict):
            raise ValueError(
                f"LoadData: composite manifest slot {slot_name!r} must be an object, got {type(slot_decl).__name__}"
            )
        slot_type = slot_decl.get("core_type")
        slot_path_raw = slot_decl.get("path")
        if slot_type is None or slot_path_raw is None:
            raise ValueError(f"LoadData: composite manifest slot {slot_name!r} must have 'core_type' and 'path' keys")
        if slot_type not in inner_dispatch:
            raise ValueError(
                f"LoadData: composite manifest slot {slot_name!r} has unsupported core_type {slot_type!r}. "
                f"Composite slots may not themselves be CompositeData."
            )

        slot_path = Path(str(slot_path_raw))
        if not slot_path.is_absolute():
            slot_path = base_dir / slot_path

        slot_config = BlockConfig(
            params={
                "core_type": slot_type,
                "path": str(slot_path),
                "allow_pickle": bool(slot_decl.get("allow_pickle", False)),
            }
        )
        slot_obj = inner_dispatch[slot_type](slot_config)
        # ADR-031: persist DataFrame slots to arrow storage.
        if slot_type == "DataFrame" and block is not None and output_dir:
            table = getattr(slot_obj, "_arrow_table", None)
            if table is not None:
                ref = block.persist_table(table, output_dir)
                slot_obj._storage_ref = ref
                del slot_obj._arrow_table  # type: ignore[attr-defined]
        loaded_slots[slot_name] = slot_obj

    return CompositeData(slots=loaded_slots, framework=_source_framework(path))
