"""Tests for ``FileExchangeBridge.prepare`` type-dispatched materialisation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from scistudio.blocks.app.bridge import FileExchangeBridge
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.blocks.registry import BlockRegistry, _spec_from_class
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame


@pytest.fixture
def registry_with_core_io() -> BlockRegistry:
    """Isolated registry containing the core IO blocks."""
    reg = BlockRegistry()
    reg._register_spec(_spec_from_class(LoadData, source="test"))
    reg._register_spec(_spec_from_class(SaveData, source="test"))
    return reg


def _make_dataframe(table: pa.Table) -> DataFrame:
    df = DataFrame(columns=list(table.column_names), row_count=table.num_rows)
    df._transient_data = table
    return df


def _make_array(np_arr: np.ndarray) -> Array:
    arr = Array(
        axes=[f"axis_{i}" for i in range(np_arr.ndim)],
        shape=tuple(np_arr.shape),
        dtype=str(np_arr.dtype),
    )
    arr._transient_data = np_arr
    return arr


def test_dataframe_input_creates_csv_file(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """DataFrame input should materialise to CSV, not lossy JSON."""
    table = pa.table({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    df = _make_dataframe(table)

    bridge = FileExchangeBridge()
    bridge.prepare({"data": df}, tmp_path, registry=registry_with_core_io)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    entry = manifest["data"]
    assert entry["type"] == "DataFrame"
    assert entry["extension"] == ".csv"
    assert entry["format"] == "csv"

    csv_path = Path(entry["path"])
    assert csv_path.exists()
    content = csv_path.read_text(encoding="utf-8")
    header_cols = [c.strip('"') for c in content.splitlines()[0].split(",")]
    assert header_cols == ["a", "b"]
    assert not content.lstrip().startswith(("{", "["))


def test_array_input_creates_real_array_file(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """Array input should materialise to a real binary array file."""
    np_arr = np.arange(12, dtype=np.int64).reshape(3, 4)
    arr = _make_array(np_arr)

    bridge = FileExchangeBridge()
    bridge.prepare({"img": arr}, tmp_path, registry=registry_with_core_io)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    entry = manifest["img"]
    assert entry["type"] == "Array"
    assert entry["extension"] == ".npy"
    assert entry["format"] == "npy"

    out_path = Path(entry["path"])
    assert out_path.exists()
    restored = np.load(out_path)
    np.testing.assert_array_equal(restored, np_arr)


def test_collection_input_creates_one_file_per_item(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """Collection items should each be materialised from their payloads."""
    items = [
        _make_array(np.arange(6, dtype=np.int32).reshape(2, 3)),
        _make_array(np.arange(8, dtype=np.int32).reshape(2, 4)),
    ]
    collection = Collection(items)

    bridge = FileExchangeBridge()
    bridge.prepare({"frames": collection}, tmp_path, registry=registry_with_core_io)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    entry = manifest["frames"]
    assert entry["type"] == "collection"
    assert entry["item_type"] == "Array"
    assert len(entry["items"]) == 2

    for i, item_entry in enumerate(entry["items"]):
        assert item_entry["type"] == "Array"
        assert item_entry["extension"] == ".npy"
        assert item_entry["format"] == "npy"
        item_path = Path(item_entry["path"])
        assert item_path.exists()
        assert item_path.parent == tmp_path / "inputs" / "frames"
        assert item_path.stem == f"item_{i:04d}"


def test_scalar_input_still_uses_json(tmp_path: Path) -> None:
    """Scalar inputs keep the legacy manifest path."""
    bridge = FileExchangeBridge()
    bridge.prepare(
        {"threshold": 0.5, "name": "test", "count": 7, "flag": True},
        tmp_path,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["threshold"] == {"type": "scalar", "value": 0.5}
    assert manifest["name"] == {"type": "scalar", "value": "test"}
    assert manifest["count"] == {"type": "scalar", "value": 7}
    assert manifest["flag"] == {"type": "scalar", "value": True}

    inputs_dir = tmp_path / "inputs"
    assert inputs_dir.exists()
    assert list(inputs_dir.iterdir()) == []


def test_manifest_records_typed_entries(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """Manifest entries should include type/path/extension/format metadata."""
    table = pa.table({"x": [10, 20]})
    df = _make_dataframe(table)
    items = [_make_array(np.zeros((1, 1), dtype=np.uint8))]
    collection = Collection(items)

    bridge = FileExchangeBridge()
    bridge.prepare(
        {
            "table": df,
            "frames": collection,
            "threshold": 0.5,
            "blob": b"\x00\x01",
        },
        tmp_path,
        registry=registry_with_core_io,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text())

    df_entry = manifest["table"]
    assert set(df_entry.keys()) >= {"type", "path", "extension", "format"}
    assert df_entry["type"] == "DataFrame"
    assert df_entry["extension"] == ".csv"
    assert df_entry["format"] == "csv"

    coll_entry = manifest["frames"]
    assert coll_entry["type"] == "collection"
    assert coll_entry["item_type"] == "Array"
    item = coll_entry["items"][0]
    assert set(item.keys()) >= {"type", "path", "extension", "format"}
    assert item["type"] == "Array"
    assert item["extension"] == ".npy"

    assert manifest["threshold"] == {"type": "scalar", "value": 0.5}

    blob_entry = manifest["blob"]
    assert blob_entry["type"] == "file"
    assert blob_entry["extension"] == ".bin"
    assert blob_entry["format"] == "binary"
    assert Path(blob_entry["path"]).read_bytes() == b"\x00\x01"


def test_default_extension_only_matches_exact_core_type_name() -> None:
    """Plugin subclasses should not be forced onto a core extension."""
    from scistudio.blocks.app.bridge import _default_extension_for_obj

    class PluginArray(Array):
        pass

    plugin_arr = PluginArray(axes=["y", "x"], shape=(1, 1), dtype="uint8")
    base_arr = Array(axes=["y", "x"], shape=(1, 1), dtype="uint8")

    assert _default_extension_for_obj(plugin_arr) is None
    assert _default_extension_for_obj(base_arr) == ".npy"


def test_empty_collection_preserves_declared_item_type(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """Empty typed Collections should preserve their declared item_type."""
    empty = Collection([], item_type=DataFrame)

    bridge = FileExchangeBridge()
    bridge.prepare({"frames": empty}, tmp_path, registry=registry_with_core_io)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    entry = manifest["frames"]
    assert entry["type"] == "collection"
    assert entry["item_type"] == "DataFrame"
    assert entry["items"] == []
