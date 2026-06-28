"""LoadData -- the built-in loader that reads core data objects from files.

:class:`LoadData` is one block that can load any of the six core data types
(Array, DataFrame, Series, Text, Artifact, CompositeData). Its ``core_type``
setting picks the type, which also retypes (and recolours) the single output
port. The actual file-reading work lives in small private ``_load_*`` functions
in this module; which format is read for a given extension is derived from
:attr:`LoadData.format_capabilities`.

Security — opening a pickle file can run arbitrary code
-------------------------------------------------------
``.pkl`` / ``.pickle`` inputs are read with :func:`pickle.load`, which
**executes whatever code is embedded in the file**. Because the ``allow_pickle``
opt-in is stored in the block config (and saved into the workflow file), a shared
or untrusted workflow that turns ``allow_pickle`` on and points at a crafted
``.pkl`` can run code on the machine of whoever opens the project and presses
Run. Loading a pickle therefore defaults to a hard refusal: it only happens when
the user explicitly enables ``allow_pickle``, and a loud ``WARNING`` is logged
each time so the run is auditable. Only load ``.pkl`` files you trust.
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
    _TEXT_FORMAT_MAP,
    _check_pickle_allowed,
    _read_xlsx_sheets,
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


def _is_xlsx_path(path: Any) -> bool:
    """True when *path* points at an Excel ``.xlsx`` file (#1810)."""

    return str(path).lower().endswith(".xlsx")


class LoadData(IOBlock):
    """Load one of the six core data types from a file (the built-in "Load" block).

    A single loader block that reads an :class:`Array`, :class:`DataFrame`,
    :class:`Series`, :class:`Text`, :class:`Artifact`, or :class:`CompositeData`
    from disk. The ``core_type`` config field chooses which type to produce, and
    the single ``data`` output port is retyped to match (so the canvas shows the
    right port colour). When ``path`` is a list of files — or points at a
    multi-sheet ``.xlsx`` — the block emits a :class:`Collection` instead of a
    single object.

    Ports: no input port (a loader reads from ``path``); one output port
    ``data``. Config: ``core_type`` (required; one of the six type names) and the
    inherited ``path``. Supported file formats depend on ``core_type`` and are
    declared in :attr:`format_capabilities` — for example CSV / TSV / Parquet /
    JSON for tabular types, NPY / NPZ / Zarr for arrays, and plain-text formats
    for Text. ``.pkl`` / ``.pickle`` is read only when ``allow_pickle`` is
    explicitly enabled (see the security note in this module's docstring).
    """

    direction: ClassVar[str] = "input"
    """Fixed to ``"input"`` — LoadData is a loader."""
    type_name: ClassVar[str] = "load_data"
    """Stable registry identifier for this block type."""
    name: ClassVar[str] = "Load"
    """Display name shown in the UI block library."""
    description: ClassVar[str] = (
        "Load a single core DataObject (Array, DataFrame, Series, Text, "
        "Artifact, or CompositeData) from a file. The output port type "
        "follows the configured core_type."
    )
    """One-line description shown in the UI."""
    subcategory: ClassVar[str] = "io"
    """Block-library subcategory this block is grouped under."""

    # Capability id convention: ``core.{lower(type)}.{format_id}.load``. Pickle
    # records carry ``notes="requires allow_pickle=True"``; the runtime gate is
    # ``_check_pickle_allowed``. Extension dispatch is derived from these records
    # at module load time via ``_LOAD_EXTENSION_MAP``.
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = _LOAD_CAPABILITIES
    """The (type, format) pairs this loader can read, as :class:`FormatCapability`
    records. Extension-based format dispatch is derived from these."""

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[DataObject]),
    ]
    """Static output ports. The single ``data`` port is retyped per instance by
    :meth:`get_effective_output_ports` from the chosen ``core_type``."""

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
    """Descriptor the API and frontend read to recolour the output port live as
    the user changes ``core_type``."""

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "core_type": {
                "type": "string",
                "enum": list(_CORE_TYPE_MAP.keys()),
                "default": "DataFrame",
                "ui_priority": 0,
            },
            # ``path`` is inherited from the IOBlock base class via MRO merge.
        },
        "required": ["core_type"],
    }
    """JSON-schema for the block config: ``core_type`` (enum, required) plus the
    inherited ``path`` field."""

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
        """Return the output port retyped to the configured ``core_type``.

        Reads ``self.config["core_type"]`` (defaulting to ``"DataFrame"``) and
        returns a single ``data`` output port whose accepted type is the matching
        core type. An unknown value falls back to ``DataFrame`` so the workflow
        validator never sees a malformed port; the actual :meth:`load` call still
        raises for an unknown type, so the error surfaces at run time. When
        ``path`` is a list, or the source is a multi-sheet ``.xlsx``, the port is
        marked as producing a :class:`Collection`.

        Returns:
            A one-element list holding the effective ``data`` output port.
        """
        type_name = self.config.get("core_type", "DataFrame")
        cls = _CORE_TYPE_MAP.get(type_name)
        if cls is None:
            from scistudio.blocks.io._unified_dispatch import resolve_type_class

            cls = resolve_type_class(str(type_name)) or DataObject
        # #1810: a multi-path list is always a Collection; an .xlsx source is
        # also always a Collection (one DataFrame/Series per sheet), so the port
        # statically declares is_collection=True for it even on a single path.
        raw_path = self.config.get("path")
        path_list = raw_path if isinstance(raw_path, list) else ([raw_path] if raw_path else [])
        is_multi = isinstance(raw_path, list)
        is_xlsx = type_name in {"DataFrame", "Series"} and any(_is_xlsx_path(p) for p in path_list)
        return [OutputPort(name="data", accepted_types=[cls], is_collection=is_multi or is_xlsx)]

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Read the configured file(s) for the chosen ``core_type``.

        Routes to the right reader based on ``config["core_type"]``; an unknown
        value raises :class:`ValueError` rather than silently guessing. Tabular
        types stream their table to storage; Array, Artifact, and Text take the
        simpler in-memory path.

        When ``path`` is a single string, returns one object. When ``path`` is a
        list of files — or a single ``.xlsx`` with multiple sheets — each file or
        sheet is read and the results are packed into a homogeneous
        :class:`Collection` whose item type matches ``core_type``.

        Args:
            config: Block config; reads ``core_type`` and ``path`` (and the
                optional ``allow_pickle`` opt-in).
            output_dir: Directory tabular readers stream their storage into,
                passed through from :meth:`IOBlock.run`.

        Returns:
            A single :class:`DataObject`, or a :class:`Collection` for multi-file
            or multi-sheet sources.

        Raises:
            ValueError: if ``core_type`` is not a recognised type.
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
        path_list = raw_path if isinstance(raw_path, list) else [raw_path]
        is_multi = isinstance(raw_path, list)
        # #1810: a DataFrame/Series .xlsx source fans out into one object per
        # sheet. Across a multi-path list, every sheet of every file is
        # flattened into one Collection (engine stays unchanged — item strategy
        # is the block's responsibility per ADR-020).
        xlsx_active = type_name in {"DataFrame", "Series"} and any(_is_xlsx_path(p) for p in path_list)

        if is_multi or xlsx_active:
            loader = dispatch[type_name]
            item_cls = _CORE_TYPE_MAP[type_name]
            shared_params: dict[str, Any] = {"core_type": type_name}
            allow_pickle = config.get("allow_pickle")
            if allow_pickle is not None:
                shared_params["allow_pickle"] = allow_pickle
            items: list[DataObject] = []
            for single_path in path_list:
                single_config = BlockConfig(params={**shared_params, "path": str(single_path)})
                if xlsx_active and _is_xlsx_path(single_path):
                    items.extend(self._load_xlsx_objects(single_config, output_dir, type_name))
                else:
                    items.append(loader(single_config, output_dir))
            return Collection(items=items, item_type=item_cls)

        result: DataObject = dispatch[type_name](config, output_dir)
        return result

    def _load_xlsx_objects(self, config: BlockConfig, output_dir: str, type_name: str) -> list[DataObject]:
        """Load one DataFrame/Series per sheet of an .xlsx workbook (#1810).

        Each sheet becomes its own DataObject carrying ``framework.source`` (the
        workbook path — shared by all of that file's sheets so the saver can
        regroup them) and ``user['sheet_name']`` (so the sheet name is visible
        and the saver can re-name sheets on round-trip). Each sheet's table is
        persisted to its own ``storage_ref`` via :meth:`persist_table`.
        """
        path = _resolve_path(config)
        if not path.exists():
            raise FileNotFoundError(f"LoadData: {type_name} source not found: {path}")
        framework = _source_framework(path)
        objects: list[DataObject] = []
        for sheet_name, table in _read_xlsx_sheets(path):
            # ``sheet_name`` is the structural identity (drives save grouping /
            # sheet naming); ``display_name`` is the generic presentation hook
            # (#1810 interim, #1812 convention) so same-file/different-sheet
            # items don't collide in DataRouter / preview lists.
            user = {"sheet_name": sheet_name, "display_name": f"{path.name} — {sheet_name}"}
            storage_ref = self.persist_table(table, output_dir) if output_dir else None
            if type_name == "Series":
                if table.num_columns != 1:
                    raise ValueError(
                        f"LoadData(core_type='Series'): sheet {sheet_name!r} in {path} has "
                        f"{table.num_columns} columns, expected a single-column Series sheet."
                    )
                objects.append(
                    Series(
                        index_name=None,
                        value_name=table.column_names[0],
                        length=int(table.num_rows),
                        framework=framework,
                        user=user,
                        storage_ref=storage_ref,
                        data=None if storage_ref is not None else table,
                    )
                )
            else:
                df = DataFrame(
                    columns=list(table.column_names),
                    row_count=int(table.num_rows),
                    framework=framework,
                    user=user,
                    storage_ref=storage_ref,
                )
                # Mirror _load_dataframe: carry the table on ``_arrow_table`` when
                # not persisted; the persisted case reads back via storage_ref.
                if storage_ref is None:
                    df._arrow_table = table  # type: ignore[attr-defined]
                objects.append(df)
        if not objects:
            raise ValueError(f"LoadData: .xlsx workbook {path} contains no sheets.")
        return objects

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
        """``LoadData`` is input-only; :meth:`save` always raises.

        Loading and saving are separate blocks. Use ``SaveData`` to write files.

        Raises:
            NotImplementedError: always.
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
        # SECURITY (#1545 / BUG-10): pickle.load EXECUTES ARBITRARY CODE in
        # the byte stream. We only reach here when the workflow explicitly
        # set allow_pickle=True; _check_pickle_allowed already raised
        # otherwise and logged a loud WARNING. A shared/untrusted workflow
        # enabling allow_pickle is a remote-code-execution vector — only
        # load .pkl files you trust. See the module docstring.
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

    if fmt == "zarr" or (
        path.is_dir() and ((path / "zarr.json").exists() or (path / ".zgroup").exists() or (path / ".zarray").exists())
    ):
        # Build a metadata-only Array with a StorageReference; chunked data
        # stays lazy and is materialised by ZarrBackend on access.
        from scistudio.core.storage.ref import StorageReference

        ref = StorageReference(backend="zarr", path=str(path), format="zarr")
        # FIND-D (#1740): read shape/dtype/axes via the zarr public API rather
        # than hand-parsing a zarr-2.x ``.zarray`` sidecar. zarr 3.x writes
        # ``zarr.json``, so the old sidecar probe always missed and the Array
        # came back with ``shape=None`` / ``axes=[]``. ``zarr.open_array`` reads
        # both zarr-2.x and 3.x stores; ``axes`` is persisted as a store
        # attribute by SaveData, with a positional fallback for older stores.
        shape: tuple[int, ...] | None = None
        dtype: str | None = None
        axes: list[str] | None = None
        try:
            import zarr

            zarr_arr = zarr.open_array(str(path), mode="r")
            shape = tuple(int(d) for d in zarr_arr.shape)
            dtype = str(zarr_arr.dtype)
            stored_axes = zarr_arr.attrs.get("axes")
            if stored_axes is not None:
                axes = [str(a) for a in stored_axes]
        except Exception:
            # Metadata is best-effort here: the data itself still materialises
            # lazily via ZarrBackend on access even if this header read fails.
            shape = None
        ndim = len(shape) if shape is not None else 0
        if axes is None:
            axes = [f"axis_{i}" for i in range(ndim)]
        return Array(
            axes=axes,
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
        # SECURITY (#1545 / BUG-10): pickle.load EXECUTES ARBITRARY CODE.
        # Reached only on an explicit allow_pickle=True opt-in (the gate
        # raised + warned otherwise). See the module docstring.
        import pickle

        with path.open("rb") as fh:
            obj = pickle.load(fh)
        if isinstance(obj, DataFrame):
            return obj
        # FIND-B (#1740): the pickle saver dumps the in-memory payload (a
        # ``pyarrow.Table``), not the wrapped DataFrame. Re-wrap a bare Table
        # the same way the csv/parquet paths do — mirroring the Array pickle
        # path, which also re-wraps its raw ndarray payload.
        import pyarrow as pa

        if isinstance(obj, pa.Table):
            df = DataFrame(
                columns=list(obj.column_names),
                row_count=int(obj.num_rows),
                framework=_source_framework(path),
            )
            df._arrow_table = obj  # type: ignore[attr-defined]
            return df
        raise ValueError(
            f"LoadData(core_type='DataFrame'): pickle at {path} unpickled to "
            f"{type(obj).__name__}, expected a DataFrame or a pyarrow.Table"
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
        # SECURITY (#1545 / BUG-10): pickle.load EXECUTES ARBITRARY CODE.
        # Reached only on an explicit allow_pickle=True opt-in (the gate
        # raised + warned otherwise). See the module docstring.
        import pickle

        with path.open("rb") as fh:
            obj = pickle.load(fh)
        if isinstance(obj, Series):
            return obj
        # FIND-B (#1740): the pickle saver dumps the in-memory payload (a
        # single-column ``pyarrow.Table``), not the wrapped Series. Re-wrap a
        # bare Table, mirroring the csv/parquet path (single column required).
        import pyarrow as pa

        if isinstance(obj, pa.Table):
            if obj.num_columns != 1:
                raise ValueError(
                    f"LoadData(core_type='Series'): pickled table at {path} has "
                    f"{obj.num_columns} columns, expected a single-column Series payload"
                )
            return Series(
                index_name=None,
                value_name=obj.column_names[0],
                length=obj.num_rows,
                framework=_source_framework(path),
                data=obj,
            )
        raise ValueError(
            f"LoadData(core_type='Series'): pickle at {path} unpickled to "
            f"{type(obj).__name__}, expected a Series or a pyarrow.Table"
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
        # Direct in-process calls without output_dir still carry the transient
        # table so smoke harnesses and unit tests do not observe an empty Series.
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
            data=None if storage_ref is not None else table,
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
    """Load opaque Artifact from any file (raw bytes + filename).

    Mirrors the deleted ``generic_adapter.read()``: builds an
    :class:`Artifact` whose ``file_path`` points at the source file and
    ``description`` defaults to the file name. If a sidecar
    ``<path>.meta.json`` is present, its keys are merged onto the user
    metadata dict (so callers can attach format-specific descriptors
    without subclassing :class:`Artifact`).

    ADR-052 §7.2: ``mime_type`` is left ``None`` — it is non-load-bearing
    (only feeds a provenance sidecar; dispatch keys off extension->format-id,
    not MIME) and core must not infer types from extensions.
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: artifact source not found: {path}")

    artifact = Artifact(
        file_path=path,
        mime_type=None,
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
