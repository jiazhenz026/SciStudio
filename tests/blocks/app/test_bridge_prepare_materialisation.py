"""Tests for ``FileExchangeBridge.prepare`` type-dispatched materialisation.

Covers the test plan from ``docs/planning/phase-minus-1-bugfix-plan.md``
§3 (issue #1080):

- Minimal AppBlock subclass (no ``run`` override): DataFrame input is
  materialised as a real CSV file, NOT a JSON-stringified blob.
- Numpy-backed Array input is materialised as a real ``.npy`` file.
- Collection input writes one file per item under ``inputs/<key>/``.
- Scalar inputs (``str``, ``int``, ``float``, ``bool``) keep the
  legacy JSON-scalar manifest entry.
- ``manifest.json`` per-port entries record
  ``{type, path, extension, format}`` for DataObject inputs.

ADR-028 §D8: the bridge now routes DataObject materialisation through
``scieasy.engine.materialisation.materialise_to_file`` which consults
``BlockRegistry.find_saver`` (#1077) and prefers a pass-through link
via ``scieasy.utils.fs.mount_pathlike`` when the source file already
matches the target extension.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from scieasy.blocks.app.bridge import FileExchangeBridge
from scieasy.blocks.io.loaders.load_data import LoadData
from scieasy.blocks.io.savers.save_data import SaveData
from scieasy.blocks.registry import BlockRegistry, _spec_from_class
from scieasy.core.types.array import Array
from scieasy.core.types.collection import Collection
from scieasy.core.types.dataframe import DataFrame

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_with_core_io() -> BlockRegistry:
    """Isolated :class:`BlockRegistry` containing :class:`LoadData` + :class:`SaveData`.

    Mirrors the helper from ``tests/engine/test_materialisation.py``: tests
    that exercise the bridge's DataObject branch need a registry where the
    core IO blocks are reachable via ``find_saver`` / ``find_loader``
    without depending on entry-point discovery.
    """
    reg = BlockRegistry()
    reg._register_spec(_spec_from_class(LoadData, source="test"))
    reg._register_spec(_spec_from_class(SaveData, source="test"))
    return reg


def _make_dataframe(table: pa.Table) -> DataFrame:
    """Build a :class:`DataFrame` whose in-memory ``_transient_data`` is *table*."""
    df = DataFrame(columns=list(table.column_names), row_count=table.num_rows)
    df._transient_data = table
    return df


def _make_array(np_arr: np.ndarray) -> Array:
    """Build an :class:`Array` whose in-memory ``_transient_data`` is *np_arr*."""
    arr = Array(
        axes=[f"axis_{i}" for i in range(np_arr.ndim)],
        shape=tuple(np_arr.shape),
        dtype=str(np_arr.dtype),
    )
    arr._transient_data = np_arr
    return arr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dataframe_input_creates_csv_file(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """DataFrame input → real ``.csv`` file (NOT a JSON-stringified blob)."""
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
    # Verify it's a real CSV with the expected header, NOT a JSON blob.
    # The SaveData CSV writer quotes string headers ("a","b"), so we
    # strip surrounding double-quotes before comparing.
    content = csv_path.read_text(encoding="utf-8")
    header_cols = [c.strip('"') for c in content.splitlines()[0].split(",")]
    assert header_cols == ["a", "b"]
    # It must not start with a JSON object/list marker (the legacy bug).
    assert not content.lstrip().startswith(("{", "["))


def test_array_input_creates_real_array_file(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """Numpy-backed Array input → real ``.npy`` (or saver-default) file.

    Stands in for the planning-doc "numpy-backed Image input → real image
    file" bullet. After ADR-027 D2, the core ``Image`` class was removed;
    the bridge code path is identical for any Array subclass (Image lives
    in the imaging plugin), so this test covers the Array dispatch.
    """
    np_arr = np.arange(12, dtype=np.int64).reshape(3, 4)
    arr = _make_array(np_arr)

    bridge = FileExchangeBridge()
    bridge.prepare({"img": arr}, tmp_path, registry=registry_with_core_io)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    entry = manifest["img"]
    assert entry["type"] == "Array"
    # SaveData declares ``.npy`` first in its supported_extensions map for
    # Array, so it is the default saver-picked extension.
    assert entry["extension"] == ".npy"
    assert entry["format"] == "npy"

    out_path = Path(entry["path"])
    assert out_path.exists()
    # Verify the bytes round-trip: load the file and compare.
    restored = np.load(out_path)
    np.testing.assert_array_equal(restored, np_arr)


def test_collection_input_creates_one_file_per_item(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """Collection input → one materialised file per item under ``inputs/<key>/``."""
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
    """Scalar inputs (``str``, ``int``, ``float``, ``bool``) keep the JSON-scalar path."""
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

    # The legacy scalar branch must NOT create files under inputs/.
    inputs_dir = tmp_path / "inputs"
    assert inputs_dir.exists()
    assert list(inputs_dir.iterdir()) == []


def test_manifest_records_typed_entries(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """Per-port manifest entries record ``{type, path, extension, format}``.

    Combines DataObject + Collection + scalar + bytes in one prepare call
    and verifies the manifest schema for each branch.
    """
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

    # DataObject entry: must carry all four fields.
    df_entry = manifest["table"]
    assert set(df_entry.keys()) >= {"type", "path", "extension", "format"}
    assert df_entry["type"] == "DataFrame"
    assert df_entry["extension"] == ".csv"
    assert df_entry["format"] == "csv"

    # Collection entry: items carry the same four fields.
    coll_entry = manifest["frames"]
    assert coll_entry["type"] == "collection"
    assert coll_entry["item_type"] == "Array"
    item = coll_entry["items"][0]
    assert set(item.keys()) >= {"type", "path", "extension", "format"}
    assert item["type"] == "Array"
    assert item["extension"] == ".npy"

    # Scalar entry: untouched (no path/extension/format).
    assert manifest["threshold"] == {"type": "scalar", "value": 0.5}

    # Bytes entry: now also records extension/format for symmetry.
    blob_entry = manifest["blob"]
    assert blob_entry["type"] == "file"
    assert blob_entry["extension"] == ".bin"
    assert blob_entry["format"] == "binary"
    assert Path(blob_entry["path"]).read_bytes() == b"\x00\x01"


# ---------------------------------------------------------------------------
# Codex review follow-ups (PR #1117)
# ---------------------------------------------------------------------------


def test_default_extension_only_matches_exact_core_type_name() -> None:
    """Codex P1: ``_default_extension_for_obj`` must NOT walk the MRO.

    The MRO-walking implementation would force ``.npy`` on every Array
    subclass (a plugin ``Image`` whose saver declares ``.tif`` / ``.zarr``,
    a plugin ``Mask`` whose saver declares ``.png``, etc.). The exact-name
    lookup returns ``None`` for any subclass so the materialiser falls
    back to the saver-declared default. This avoids the worst case where
    a plugin type's saver does not support ``.npy`` and the forced
    extension would raise ``LookupError``.
    """
    from scieasy.blocks.app.bridge import _default_extension_for_obj

    class PluginArray(Array):
        pass

    # ADR-027 D1 requires axes for Array; the helper only inspects
    # ``type(obj).__name__`` so any valid Array instance works.
    plugin_arr = PluginArray(axes=["y", "x"], shape=(1, 1), dtype="uint8")
    base_arr = Array(axes=["y", "x"], shape=(1, 1), dtype="uint8")

    assert _default_extension_for_obj(plugin_arr) is None, (
        "plugin Array subclass must NOT receive a forced core extension; "
        "the materialiser must be free to defer to the plugin saver's default"
    )
    assert _default_extension_for_obj(base_arr) == ".npy"


def test_empty_collection_preserves_declared_item_type(tmp_path: Path, registry_with_core_io: BlockRegistry) -> None:
    """Codex P2: empty Collection's manifest entry must preserve the
    declared ``item_type`` instead of dropping to ``"mixed"``.

    ``Collection([], item_type=DataFrame)`` is a valid typed payload
    (ADR-020 Add6 requires ``item_type`` when items is empty); the
    bridge must surface it in the manifest so downstream consumers can
    keep handling the typed-but-empty case correctly.
    """
    empty = Collection([], item_type=DataFrame)

    bridge = FileExchangeBridge()
    bridge.prepare({"frames": empty}, tmp_path, registry=registry_with_core_io)

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    entry = manifest["frames"]
    assert entry["type"] == "collection"
    assert entry["item_type"] == "DataFrame", (
        f"empty Collection with declared item_type must surface that name, got {entry['item_type']!r}"
    )
    assert entry["items"] == []
