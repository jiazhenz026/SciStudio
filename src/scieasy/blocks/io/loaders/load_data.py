"""LoadData -- dynamic-port core IO loader (ADR-028 Addendum 1).

This module implements the canonical core IO loader block per
ADR-028 Addendum 1 §C5 (hardcoded ``_CORE_TYPE_MAP``) and §C9 (private
module-level dispatch functions instead of helper classes).

The class body is the canonical implementation skeleton from
``docs/specs/phase11-implementation-standards.md`` lines 1292-1413; the
six private ``_load_*`` functions absorb the logic that previously
lived in ``src/scieasy/blocks/io/adapters/{csv,parquet,zarr,generic}_adapter.py``
(deleted in T-TRK-004 / PR #319).

The ``allow_pickle`` opt-in flag controls whether ``.pkl`` / ``.pickle``
files can be loaded. The default is ``False``; passing
``allow_pickle=True`` causes a WARNING-level log entry before the load
proceeds. This mirrors NumPy's policy for the same security risk.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import OutputPort
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.types.array import Array
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.core.types.composite import CompositeData
from scieasy.core.types.dataframe import DataFrame
from scieasy.core.types.series import Series
from scieasy.core.types.text import Text

_LOGGER = logging.getLogger(__name__)


_CORE_TYPE_MAP: dict[str, type[DataObject]] = {
    "Array": Array,
    "DataFrame": DataFrame,
    "Series": Series,
    "Text": Text,
    "Artifact": Artifact,
    "CompositeData": CompositeData,
}


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
            "allow_pickle": {
                "type": "boolean",
                "default": False,
                "ui_priority": 2,
            },
        },
        "required": ["core_type"],
    }

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
        cls = _CORE_TYPE_MAP.get(type_name, DataFrame)
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

        # ADR-031: dispatch table. Functions that don't need output_dir
        # are wrapped with lambdas to accept and ignore the parameter,
        # keeping a uniform (config, output_dir) call signature.
        dispatch: dict[str, Any] = {
            "Array": self._load_array_with_persist,
            "DataFrame": self._load_dataframe_with_persist,
            "Series": self._load_series_with_persist,
            "Text": lambda cfg, od: _load_text(cfg),
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
        arr_obj = _load_array(config)
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
        df = _load_dataframe(config)
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


def _resolve_path(config: BlockConfig) -> Path:
    """Pull the validated ``path`` field off ``config`` as a :class:`Path`.

    Raises ``ValueError`` if no path was supplied; the JSON schema also
    enforces this on the API side, but we double-check at runtime so the
    failure mode is identical regardless of the call site.
    """
    raw = config.get("path")
    if raw is None:
        raise ValueError("LoadData requires a 'path' config field")
    return Path(str(raw))


def _check_pickle_allowed(path: Path, config: BlockConfig) -> bool:
    """Return ``True`` if the path is a pickle file and pickle is allowed.

    Returns ``False`` for non-pickle paths (so the caller can fall through
    to its default branch). Raises ``ValueError`` when the path IS a
    pickle file but ``allow_pickle`` is not set, with an explicit security
    message. Logs a WARNING when ``allow_pickle=True`` is honoured.
    """
    suffix = path.suffix.lower()
    if suffix not in {".pkl", ".pickle"}:
        return False
    if not bool(config.get("allow_pickle", False)):
        raise ValueError(
            f"Refusing to load pickle file {path.name!r}: pickle deserialisation "
            f"can execute arbitrary code. Set allow_pickle=True on the LoadData "
            f"config if you trust the source."
        )
    _LOGGER.warning(
        "LoadData: loading pickle file %s with allow_pickle=True. "
        "Pickle files can execute arbitrary code; only load files from trusted sources.",
        path,
    )
    return True


def _load_array(config: BlockConfig) -> Array:
    """Load Array from .npy / .npz / .zarr / .parquet (single column) / .pkl.

    .npy and .npz are loaded via :func:`numpy.load`. .zarr stores create a
    metadata-only :class:`Array` with a :class:`StorageReference` so the
    actual chunked data stays lazy. Single-column .parquet falls back to
    pyarrow. Pickle support honours :func:`_check_pickle_allowed`.
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: array source not found: {path}")

    suffix = path.suffix.lower()

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
        )
        result._data = arr  # type: ignore[attr-defined]
        return result

    if suffix == ".npy":
        import numpy as np

        arr = np.load(path)
        result = Array(
            axes=[f"axis_{i}" for i in range(arr.ndim)],
            shape=tuple(arr.shape),
            dtype=str(arr.dtype),
        )
        result._data = arr  # type: ignore[attr-defined]
        return result

    if suffix == ".npz":
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
        )
        result._data = arr  # type: ignore[attr-defined]
        return result

    if suffix == ".zarr" or (path.is_dir() and ((path / ".zgroup").exists() or (path / ".zarray").exists())):
        # Build a metadata-only Array with a StorageReference; chunked data
        # stays lazy and is materialised by ZarrBackend on access.
        from scieasy.core.storage.ref import StorageReference

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
            storage_ref=ref,
        )

    if suffix in {".parquet", ".pq"}:
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
        )
        result._data = arr  # type: ignore[attr-defined]
        return result

    raise ValueError(
        f"LoadData(core_type='Array') does not support extension {suffix!r}. "
        f"Supported: .npy, .npz, .zarr, .parquet, .pq, .pkl/.pickle (with allow_pickle=True)."
    )


def _load_dataframe(config: BlockConfig) -> DataFrame:
    """Load DataFrame from .csv / .tsv / .parquet / .json / .pkl / .pickle.

    Uses pyarrow for columnar formats (CSV / Parquet) and pyarrow's JSON
    reader for record-oriented JSON. Pickle is gated via
    :func:`_check_pickle_allowed` and uses :mod:`pickle` from the stdlib
    rather than pulling in pandas (which is not a core dependency).

    The constructed :class:`DataFrame` carries the underlying pyarrow
    Table on the ``_arrow_table`` attribute (matching the deleted
    csv_adapter / parquet_adapter convention) so downstream blocks can
    materialise data without re-parsing the file.
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: dataframe source not found: {path}")

    suffix = path.suffix.lower()

    if _check_pickle_allowed(path, config):
        import pickle

        with path.open("rb") as fh:
            obj = pickle.load(fh)
        if isinstance(obj, DataFrame):
            return obj
        raise ValueError(
            f"LoadData(core_type='DataFrame'): pickle at {path} unpickled to "
            f"{type(obj).__name__}, expected scieasy.core.types.dataframe.DataFrame"
        )

    if suffix in {".csv", ".tsv"}:
        import pyarrow.csv as pcsv

        delimiter = "\t" if suffix == ".tsv" else ","
        parse_opts = pcsv.ParseOptions(delimiter=delimiter)
        table = pcsv.read_csv(str(path), parse_options=parse_opts)
        df = DataFrame(
            columns=list(table.column_names),
            row_count=int(table.num_rows),
        )
        df._arrow_table = table  # type: ignore[attr-defined]
        return df

    if suffix in {".parquet", ".pq"}:
        import pyarrow.parquet as pq

        table = pq.read_table(str(path))
        df = DataFrame(
            columns=list(table.column_names),
            row_count=int(table.num_rows),
        )
        df._arrow_table = table  # type: ignore[attr-defined]
        return df

    if suffix == ".json":
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
        )
        df._arrow_table = table  # type: ignore[attr-defined]
        return df

    raise ValueError(
        f"LoadData(core_type='DataFrame') does not support extension {suffix!r}. "
        f"Supported: .csv, .tsv, .parquet, .pq, .json, .pkl/.pickle (with allow_pickle=True)."
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

    suffix = path.suffix.lower()

    if _check_pickle_allowed(path, config):
        import pickle

        with path.open("rb") as fh:
            obj = pickle.load(fh)
        if isinstance(obj, Series):
            return obj
        raise ValueError(
            f"LoadData(core_type='Series'): pickle at {path} unpickled to "
            f"{type(obj).__name__}, expected scieasy.core.types.series.Series"
        )

    if suffix in {".csv", ".tsv", ".parquet", ".pq"}:
        # Reuse the dataframe loader and assert a single column.
        df = _load_dataframe(config)
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
            storage_ref=storage_ref,
        )

    raise ValueError(
        f"LoadData(core_type='Series') does not support extension {suffix!r}. "
        f"Supported: .csv, .tsv, .parquet, .pq, .pkl/.pickle (with allow_pickle=True)."
    )


_TEXT_FORMAT_MAP: dict[str, str] = {
    ".txt": "plain",
    ".log": "plain",
    ".md": "markdown",
    ".html": "html",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}


def _load_text(config: BlockConfig) -> Text:
    """Load Text from .txt / .md / .html / .xml / .log / .yaml / .yml / .toml.

    Reads the file via :meth:`pathlib.Path.read_text` (UTF-8) and infers
    the ``format`` field from the extension via :data:`_TEXT_FORMAT_MAP`.
    Unknown extensions still load (treated as ``"plain"``) -- this matches
    the spirit of the deleted ``generic_adapter`` and avoids surprising
    rejections.
    """
    path = _resolve_path(config)
    if not path.exists():
        raise FileNotFoundError(f"LoadData: text source not found: {path}")

    suffix = path.suffix.lower()
    if suffix not in _TEXT_FORMAT_MAP:
        raise ValueError(
            f"LoadData(core_type='Text') does not support extension {suffix!r}. "
            f"Supported: {sorted(_TEXT_FORMAT_MAP.keys())}."
        )

    content = path.read_text(encoding="utf-8")
    return Text(
        content=content,
        format=_TEXT_FORMAT_MAP[suffix],
        encoding="utf-8",
    )


_MIME_GUESS: dict[str, str] = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".pdf": "application/pdf",
    ".bin": "application/octet-stream",
    ".dat": "application/octet-stream",
}


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

    return CompositeData(slots=loaded_slots)
