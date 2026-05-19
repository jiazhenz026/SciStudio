"""Tests for ``LoadData`` -- ADR-028 Addendum 1 §C5/§C9 (T-TRK-007).

Covers:

* :class:`LoadData` instantiates with each of the six ``core_type``
  enum values and the dynamic ``output_ports`` mechanism returns the
  correct accepted-types per enum value.
* End-to-end load round-trip via ``tmp_path`` for every core type
  (CSV / JSON / TSV / Parquet -> DataFrame, .npy / .npz -> Array,
  single-column CSV -> Series, .txt / .md -> Text, .bin -> Artifact,
  JSON manifest -> CompositeData).
* ``allow_pickle=False`` rejects ``.pkl`` / ``.pickle`` paths with a
  clear ``ValueError``.
* ``allow_pickle=True`` reads pickle files and emits a WARNING-level
  log entry before doing so.
* The dispatch ``core_type`` value is validated; unknown enum values
  raise ``ValueError`` from :meth:`LoadData.load`.
* :meth:`LoadData.save` always raises ``NotImplementedError`` (loader
  is input-only; ``SaveData`` is the symmetric egress block).
"""

from __future__ import annotations

import json
import logging
import pickle
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scieasy.blocks.io import LoadData
from scieasy.blocks.io.loaders.load_data import _CORE_TYPE_MAP
from scieasy.core.types.array import Array
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.composite import CompositeData
from scieasy.core.types.dataframe import DataFrame
from scieasy.core.types.series import Series
from scieasy.core.types.text import Text

# ---------------------------------------------------------------------------
# Instantiation + dynamic-port contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("core_type", list(_CORE_TYPE_MAP.keys()))
def test_load_data_instantiates_with_each_core_type(core_type: str) -> None:
    """LoadData must accept every value in the ``_CORE_TYPE_MAP`` enum."""
    block = LoadData(config={"params": {"core_type": core_type, "path": "/tmp/x"}})
    assert block.config.get("core_type") == core_type
    # ``LoadData`` direction is "input" so save() always raises.
    assert block.direction == "input"


@pytest.mark.parametrize(
    ("core_type", "expected_cls"),
    [
        ("Array", Array),
        ("DataFrame", DataFrame),
        ("Series", Series),
        ("Text", Text),
        ("Artifact", Artifact),
        ("CompositeData", CompositeData),
    ],
)
def test_get_effective_output_ports_returns_correct_type(core_type: str, expected_cls: type) -> None:
    """``get_effective_output_ports`` must derive port type from ``core_type``."""
    block = LoadData(config={"params": {"core_type": core_type, "path": "/tmp/x"}})
    ports = block.get_effective_output_ports()
    assert len(ports) == 1
    assert ports[0].name == "data"
    assert ports[0].accepted_types == [expected_cls]


def test_dynamic_ports_classvar_shape() -> None:
    """The ``dynamic_ports`` ClassVar must follow the Addendum 1 D1 schema."""
    dp = LoadData.dynamic_ports
    assert dp is not None
    assert dp["source_config_key"] == "core_type"
    mapping = dp["output_port_mapping"]["data"]
    assert set(mapping.keys()) == set(_CORE_TYPE_MAP.keys())
    for type_name in _CORE_TYPE_MAP:
        assert mapping[type_name] == [type_name]


def test_load_data_in_io_blocks_namespace() -> None:
    """LoadData must be importable from ``scieasy.blocks.io``."""
    from scieasy.blocks.io import IOBlock
    from scieasy.blocks.io import LoadData as Reexported

    assert Reexported is LoadData
    assert issubclass(LoadData, IOBlock)


# ---------------------------------------------------------------------------
# DataFrame loaders
# ---------------------------------------------------------------------------


def test_load_csv_to_dataframe(tmp_path: Path) -> None:
    """CSV files round-trip into a DataFrame whose pyarrow Table reflects content."""
    csv_path = tmp_path / "table.csv"
    csv_path.write_text("a,b,c\n1,2,3\n4,5,6\n7,8,9\n")
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(csv_path)}})

    df = block.load(block.config)

    assert isinstance(df, DataFrame)
    assert df.columns == ["a", "b", "c"]
    assert df.row_count == 3
    # Phase 1 _load_dataframe_with_persist persists to arrow storage.
    # Verify data is accessible via storage_ref or get_in_memory_data().
    table = df.get_in_memory_data()
    assert isinstance(table, pa.Table)
    assert table.column("a").to_pylist() == [1, 4, 7]


def test_load_tsv_to_dataframe(tmp_path: Path) -> None:
    """TSV files use the tab delimiter via the same dataframe loader."""
    tsv_path = tmp_path / "table.tsv"
    tsv_path.write_text("a\tb\n1\t2\n3\t4\n")
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(tsv_path)}})

    df = block.load(block.config)

    assert df.columns == ["a", "b"]
    assert df.row_count == 2


def test_load_json_records_to_dataframe(tmp_path: Path) -> None:
    """Record-oriented JSON loads into a DataFrame via pyarrow.from_pylist."""
    json_path = tmp_path / "records.json"
    json_path.write_text(json.dumps([{"x": 1, "y": "a"}, {"x": 2, "y": "b"}]))
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(json_path)}})

    df = block.load(block.config)

    assert set(df.columns or []) == {"x", "y"}
    assert df.row_count == 2


def test_load_json_columns_to_dataframe(tmp_path: Path) -> None:
    """Column-oriented JSON dict loads via pyarrow.from_pydict."""
    json_path = tmp_path / "columns.json"
    json_path.write_text(json.dumps({"x": [1, 2, 3], "y": ["a", "b", "c"]}))
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(json_path)}})

    df = block.load(block.config)

    assert set(df.columns or []) == {"x", "y"}
    assert df.row_count == 3


def test_load_parquet_to_dataframe(tmp_path: Path) -> None:
    """Parquet round-trips through the same loader path."""
    table = pa.table({"col_a": [10, 20, 30], "col_b": ["p", "q", "r"]})
    parquet_path = tmp_path / "table.parquet"
    pq.write_table(table, str(parquet_path))

    block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(parquet_path)}})
    df = block.load(block.config)

    assert df.columns == ["col_a", "col_b"]
    assert df.row_count == 3


def test_load_dataframe_unsupported_extension_raises(tmp_path: Path) -> None:
    """Unknown extensions must raise a descriptive ValueError, not silently ignore."""
    p = tmp_path / "data.xyz"
    p.write_text("garbage")
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(p)}})

    with pytest.raises(ValueError, match="does not support extension"):
        block.load(block.config)


# ---------------------------------------------------------------------------
# Array loaders
# ---------------------------------------------------------------------------


def test_load_npy_to_array(tmp_path: Path) -> None:
    """.npy files load into an Array carrying the underlying numpy data."""
    arr = np.arange(12, dtype=np.int32).reshape(3, 4)
    npy_path = tmp_path / "data.npy"
    np.save(npy_path, arr)

    block = LoadData(config={"params": {"core_type": "Array", "path": str(npy_path)}})
    loaded = block.load(block.config)

    assert isinstance(loaded, Array)
    assert loaded.shape == (3, 4)
    assert loaded.dtype == "int32"
    np.testing.assert_array_equal(np.asarray(loaded), arr)


def test_load_npz_to_array_picks_first_member(tmp_path: Path) -> None:
    """.npz archives load the first stored array (single-array convention)."""
    arr = np.array([1.0, 2.0, 3.0])
    npz_path = tmp_path / "data.npz"
    np.savez(npz_path, signal=arr)

    block = LoadData(config={"params": {"core_type": "Array", "path": str(npz_path)}})
    loaded = block.load(block.config)

    assert isinstance(loaded, Array)
    assert loaded.shape == (3,)
    np.testing.assert_array_equal(np.asarray(loaded), arr)


def test_load_array_from_single_column_parquet(tmp_path: Path) -> None:
    """Single-column .parquet maps to a 1D Array."""
    table = pa.table({"signal": [1.0, 2.0, 3.0, 4.0]})
    parquet_path = tmp_path / "signal.parquet"
    pq.write_table(table, str(parquet_path))

    block = LoadData(config={"params": {"core_type": "Array", "path": str(parquet_path)}})
    arr = block.load(block.config)

    assert isinstance(arr, Array)
    assert arr.shape == (4,)


def test_load_array_multi_column_parquet_rejected(tmp_path: Path) -> None:
    """Array loader must reject multi-column parquet (use DataFrame instead)."""
    table = pa.table({"a": [1, 2], "b": [3, 4]})
    parquet_path = tmp_path / "multi.parquet"
    pq.write_table(table, str(parquet_path))

    block = LoadData(config={"params": {"core_type": "Array", "path": str(parquet_path)}})
    with pytest.raises(ValueError, match=r"single-column \.parquet"):
        block.load(block.config)


def test_load_array_unsupported_extension_raises(tmp_path: Path) -> None:
    """Unknown extension paths surface a descriptive ValueError."""
    p = tmp_path / "data.weird"
    p.write_text("garbage")
    block = LoadData(config={"params": {"core_type": "Array", "path": str(p)}})

    with pytest.raises(ValueError, match="does not support extension"):
        block.load(block.config)


# ---------------------------------------------------------------------------
# Series loader
# ---------------------------------------------------------------------------


def test_load_single_column_csv_to_series(tmp_path: Path) -> None:
    """Single-column CSV maps to a Series with the column name as value_name."""
    csv_path = tmp_path / "signal.csv"
    csv_path.write_text("intensity\n10\n20\n30\n")

    block = LoadData(config={"params": {"core_type": "Series", "path": str(csv_path)}})
    s = block.load(block.config)

    assert isinstance(s, Series)
    assert s.value_name == "intensity"
    assert s.length == 3


def test_load_multi_column_csv_as_series_rejected(tmp_path: Path) -> None:
    """Series loader rejects multi-column CSV with a clear error."""
    csv_path = tmp_path / "multi.csv"
    csv_path.write_text("a,b\n1,2\n")

    block = LoadData(config={"params": {"core_type": "Series", "path": str(csv_path)}})
    with pytest.raises(ValueError, match="single-column tabular file"):
        block.load(block.config)


# ---------------------------------------------------------------------------
# Text loader
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("suffix", "expected_format"),
    [
        (".txt", "plain"),
        (".log", "plain"),
        (".md", "markdown"),
        (".html", "html"),
        (".xml", "xml"),
        (".yaml", "yaml"),
        (".yml", "yaml"),
        (".toml", "toml"),
    ],
)
def test_load_txt_to_text(tmp_path: Path, suffix: str, expected_format: str) -> None:
    """Each text-family extension maps to the right ``format`` field."""
    p = tmp_path / f"file{suffix}"
    p.write_text("hello world", encoding="utf-8")

    block = LoadData(config={"params": {"core_type": "Text", "path": str(p)}})
    t = block.load(block.config)

    assert isinstance(t, Text)
    assert t.content == "hello world"
    assert t.format == expected_format
    assert t.encoding == "utf-8"


def test_load_text_unsupported_extension_raises(tmp_path: Path) -> None:
    """Non-text extensions must raise rather than silently coerce."""
    p = tmp_path / "data.bin"
    p.write_bytes(b"\x00\x01\x02")
    block = LoadData(config={"params": {"core_type": "Text", "path": str(p)}})

    with pytest.raises(ValueError, match="does not support extension"):
        block.load(block.config)


# ---------------------------------------------------------------------------
# Artifact loader
# ---------------------------------------------------------------------------


def test_load_artifact_from_bin(tmp_path: Path) -> None:
    """Generic .bin files become Artifacts with mime + filename + path."""
    bin_path = tmp_path / "blob.bin"
    bin_path.write_bytes(b"\x01\x02\x03\x04")

    block = LoadData(config={"params": {"core_type": "Artifact", "path": str(bin_path)}})
    art = block.load(block.config)

    assert isinstance(art, Artifact)
    assert art.file_path == bin_path
    assert art.mime_type == "application/octet-stream"
    assert art.description == "blob.bin"


def test_load_artifact_with_sidecar_metadata(tmp_path: Path) -> None:
    """A ``<file>.meta.json`` sidecar populates the Artifact ``user`` slot."""
    bin_path = tmp_path / "blob.bin"
    bin_path.write_bytes(b"data")
    sidecar = tmp_path / "blob.bin.meta.json"
    sidecar.write_text(json.dumps({"source": "instrument-A", "version": 7}))

    block = LoadData(config={"params": {"core_type": "Artifact", "path": str(bin_path)}})
    art = block.load(block.config)

    assert art.user["source"] == "instrument-A"
    assert art.user["version"] == 7


def test_load_artifact_invalid_sidecar_raises(tmp_path: Path) -> None:
    """A malformed sidecar raises ValueError instead of silently dropping it."""
    bin_path = tmp_path / "blob.bin"
    bin_path.write_bytes(b"data")
    sidecar = tmp_path / "blob.bin.meta.json"
    sidecar.write_text("{not valid json")

    block = LoadData(config={"params": {"core_type": "Artifact", "path": str(bin_path)}})
    with pytest.raises(ValueError, match="cannot parse artifact sidecar"):
        block.load(block.config)


# ---------------------------------------------------------------------------
# CompositeData loader
# ---------------------------------------------------------------------------


def test_load_composite_data_from_manifest(tmp_path: Path) -> None:
    """A JSON manifest assembles a CompositeData from heterogeneous slot files."""
    csv_path = tmp_path / "table.csv"
    csv_path.write_text("a,b\n1,2\n3,4\n")
    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("hello composite", encoding="utf-8")
    npy_path = tmp_path / "signal.npy"
    np.save(npy_path, np.array([1, 2, 3]))

    manifest_path = tmp_path / "bundle.json"
    manifest_path.write_text(
        json.dumps(
            {
                "slots": {
                    "table": {"core_type": "DataFrame", "path": "table.csv"},
                    "notes": {"core_type": "Text", "path": "notes.txt"},
                    "signal": {"core_type": "Array", "path": "signal.npy"},
                }
            }
        )
    )

    block = LoadData(config={"params": {"core_type": "CompositeData", "path": str(manifest_path)}})
    composite = block.load(block.config)

    assert isinstance(composite, CompositeData)
    assert set(composite.slot_names) == {"table", "notes", "signal"}
    assert isinstance(composite.get("table"), DataFrame)
    assert isinstance(composite.get("notes"), Text)
    assert isinstance(composite.get("signal"), Array)
    assert composite.get("notes").content == "hello composite"


def test_load_composite_data_rejects_nested_composite(tmp_path: Path) -> None:
    """Composite slots may not themselves be CompositeData (no recursion)."""
    inner = tmp_path / "inner.json"
    inner.write_text("{}")
    manifest = tmp_path / "outer.json"
    manifest.write_text(json.dumps({"slots": {"nested": {"core_type": "CompositeData", "path": str(inner)}}}))

    block = LoadData(config={"params": {"core_type": "CompositeData", "path": str(manifest)}})
    with pytest.raises(ValueError, match="may not themselves be CompositeData"):
        block.load(block.config)


def test_load_composite_data_rejects_non_json_manifest(tmp_path: Path) -> None:
    """Composite manifests must be .json -- other extensions raise."""
    p = tmp_path / "manifest.yaml"
    p.write_text("slots: {}")
    block = LoadData(config={"params": {"core_type": "CompositeData", "path": str(p)}})

    with pytest.raises(ValueError, match=r"requires a \.json manifest"):
        block.load(block.config)


def test_load_composite_data_malformed_manifest_raises(tmp_path: Path) -> None:
    """Manifests that aren't JSON objects raise descriptively."""
    p = tmp_path / "bad.json"
    p.write_text(json.dumps([1, 2, 3]))
    block = LoadData(config={"params": {"core_type": "CompositeData", "path": str(p)}})

    with pytest.raises(ValueError, match="composite manifest must be a JSON object"):
        block.load(block.config)


# ---------------------------------------------------------------------------
# allow_pickle gating
# ---------------------------------------------------------------------------


def test_allow_pickle_false_rejects_pkl(tmp_path: Path) -> None:
    """``.pkl`` paths must raise when ``allow_pickle`` is unset/false (default)."""
    df = DataFrame(columns=["a"], row_count=1)
    pkl_path = tmp_path / "obj.pkl"
    with pkl_path.open("wb") as fh:
        pickle.dump(df, fh)

    block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(pkl_path)}})
    with pytest.raises(ValueError, match="Refusing to load pickle"):
        block.load(block.config)


def test_allow_pickle_false_rejects_pickle_extension(tmp_path: Path) -> None:
    """Same gating must cover the ``.pickle`` extension."""
    arr = Array(axes=["x"], shape=(1,), dtype="float64")
    pkl_path = tmp_path / "obj.pickle"
    with pkl_path.open("wb") as fh:
        pickle.dump(arr, fh)

    block = LoadData(config={"params": {"core_type": "Array", "path": str(pkl_path)}})
    with pytest.raises(ValueError, match="Refusing to load pickle"):
        block.load(block.config)


def test_allow_pickle_true_loads_pkl(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """When opted-in, pickle loads succeed AND emit a WARNING log entry."""
    original = DataFrame(columns=["a", "b"], row_count=2)
    pkl_path = tmp_path / "obj.pkl"
    with pkl_path.open("wb") as fh:
        pickle.dump(original, fh)

    block = LoadData(
        config={
            "params": {
                "core_type": "DataFrame",
                "path": str(pkl_path),
                "allow_pickle": True,
            }
        }
    )
    with caplog.at_level(logging.WARNING, logger="scieasy.blocks.io.loaders.load_data"):
        loaded = block.load(block.config)

    assert isinstance(loaded, DataFrame)
    assert loaded.columns == ["a", "b"]
    assert loaded.row_count == 2
    assert any("allow_pickle=True" in record.message and record.levelno == logging.WARNING for record in caplog.records)


def test_allow_pickle_true_series(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Same WARNING + load round-trip for Series pickle."""
    original = Series(value_name="signal", length=10)
    pkl_path = tmp_path / "obj.pkl"
    with pkl_path.open("wb") as fh:
        pickle.dump(original, fh)

    block = LoadData(
        config={
            "params": {
                "core_type": "Series",
                "path": str(pkl_path),
                "allow_pickle": True,
            }
        }
    )
    with caplog.at_level(logging.WARNING, logger="scieasy.blocks.io.loaders.load_data"):
        loaded = block.load(block.config)

    assert isinstance(loaded, Series)
    assert loaded.value_name == "signal"
    assert any("allow_pickle=True" in record.message and record.levelno == logging.WARNING for record in caplog.records)


# ---------------------------------------------------------------------------
# Misc dispatch contract
# ---------------------------------------------------------------------------


def test_load_unknown_core_type_raises() -> None:
    """``LoadData.load`` must reject ``core_type`` values not in the enum."""
    block = LoadData(config={"params": {"core_type": "FluorImage", "path": "/tmp/x"}})
    with pytest.raises(ValueError, match="Unknown core_type"):
        block.load(block.config)


def test_load_data_save_always_raises() -> None:
    """LoadData is input-only -- save() must always raise NotImplementedError."""
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": "/tmp/x"}})
    with pytest.raises(NotImplementedError, match="LoadData is input-only"):
        block.save(DataFrame(columns=["a"], row_count=0), block.config)


def test_load_missing_path_raises() -> None:
    """Calling load() without a path must raise ValueError, not return None."""
    block = LoadData(config={"params": {"core_type": "DataFrame"}})
    with pytest.raises(ValueError, match="requires a 'path'"):
        block.load(block.config)


def test_load_nonexistent_file_raises_filenotfounderror(tmp_path: Path) -> None:
    """Missing files surface as FileNotFoundError, not generic ValueError."""
    missing = tmp_path / "does_not_exist.csv"
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(missing)}})
    with pytest.raises(FileNotFoundError):
        block.load(block.config)


# ---------------------------------------------------------------------------
# Multi-file Collection support (#421)
# ---------------------------------------------------------------------------


def test_load_data_multi_path_returns_collection(tmp_path: Path) -> None:
    """A list of paths in config['path'] must return a Collection of DataObjects."""
    csv1 = tmp_path / "a.csv"
    csv2 = tmp_path / "b.csv"
    csv1.write_text("x\n1\n2\n")
    csv2.write_text("x\n3\n4\n")

    block = LoadData(config={"params": {"core_type": "DataFrame", "path": [str(csv1), str(csv2)]}})
    result = block.load(block.config)

    from scieasy.core.types.collection import Collection

    assert isinstance(result, Collection)
    assert len(result) == 2
    assert all(isinstance(item, DataFrame) for item in result)
    assert result.item_type is DataFrame


def test_load_data_multi_path_collection_preserves_contents(tmp_path: Path) -> None:
    """Each DataFrame in the Collection must correspond to the correct source file."""
    csv1 = tmp_path / "first.csv"
    csv2 = tmp_path / "second.csv"
    csv1.write_text("col\n10\n20\n")
    csv2.write_text("col\n30\n40\n50\n")

    block = LoadData(config={"params": {"core_type": "DataFrame", "path": [str(csv1), str(csv2)]}})
    result = block.load(block.config)

    assert result[0].row_count == 2
    assert result[1].row_count == 3


def test_load_data_multi_path_single_element_list(tmp_path: Path) -> None:
    """A single-element list still returns a Collection, not a bare DataObject."""
    csv1 = tmp_path / "only.csv"
    csv1.write_text("a\n1\n")

    block = LoadData(config={"params": {"core_type": "DataFrame", "path": [str(csv1)]}})
    result = block.load(block.config)

    from scieasy.core.types.collection import Collection

    assert isinstance(result, Collection)
    assert len(result) == 1


def test_load_data_multi_path_array(tmp_path: Path) -> None:
    """Multi-path works for Array core_type, returning Collection[Array]."""
    arr = np.arange(6, dtype=np.float32)
    npy1 = tmp_path / "s1.npy"
    npy2 = tmp_path / "s2.npy"
    np.save(npy1, arr)
    np.save(npy2, arr * 2)

    block = LoadData(config={"params": {"core_type": "Array", "path": [str(npy1), str(npy2)]}})
    result = block.load(block.config)

    assert result.item_type is Array
    assert len(result) == 2
    np.testing.assert_array_equal(np.asarray(result[0]), arr)
    np.testing.assert_array_equal(np.asarray(result[1]), arr * 2)


def test_load_data_multi_path_get_effective_output_ports_is_collection(tmp_path: Path) -> None:
    """get_effective_output_ports marks is_collection=True when path is a list."""
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": ["/tmp/a.csv", "/tmp/b.csv"]}})
    ports = block.get_effective_output_ports()
    assert ports[0].is_collection is True


def test_load_data_single_path_get_effective_output_ports_not_collection() -> None:
    """get_effective_output_ports marks is_collection=False for a single path string."""
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": "/tmp/a.csv"}})
    ports = block.get_effective_output_ports()
    assert ports[0].is_collection is False


def test_load_data_run_multi_path_wraps_collection_correctly(tmp_path: Path) -> None:
    """IOBlock.run() must not double-wrap a Collection returned from load()."""
    csv1 = tmp_path / "run1.csv"
    csv2 = tmp_path / "run2.csv"
    csv1.write_text("v\n1\n")
    csv2.write_text("v\n2\n")

    block = LoadData(config={"params": {"core_type": "DataFrame", "path": [str(csv1), str(csv2)]}})
    out = block.run(inputs={}, config=block.config)

    from scieasy.core.types.collection import Collection

    collection = out["data"]
    assert isinstance(collection, Collection)
    # The Collection from load() (length-2) must be returned directly,
    # not wrapped in another single-item Collection.
    assert len(collection) == 2


# ---------------------------------------------------------------------------
# Integration with framework run() dispatch (ADR-028 §D1)
# ---------------------------------------------------------------------------


def test_load_data_run_dispatches_to_load(tmp_path: Path) -> None:
    """The framework ``run()`` dispatch path must invoke ``load()`` for input direction."""
    csv_path = tmp_path / "x.csv"
    csv_path.write_text("a\n1\n2\n")
    block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(csv_path)}})

    out = block.run(inputs={}, config=block.config)

    assert "data" in out
    # IOBlock.run() wraps non-Collection results in a single-item Collection.
    collection = out["data"]
    assert collection.item_type is DataFrame
    assert len(collection) == 1
    assert isinstance(collection[0], DataFrame)
