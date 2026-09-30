"""Bounded data-access tests (ADR-048 FR-009 / FR-010 / SC-004)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from scistudio.core.storage.ref import StorageReference
from scistudio.panels.data_access import PreviewDataAccess


def _csv(tmp_path: Path, rows: int) -> StorageReference:
    header = "idx,val\n"
    body = "".join(f"{i},{i * 2}\n" for i in range(rows))
    path = tmp_path / "t.csv"
    path.write_text(header + body, encoding="utf-8")
    return StorageReference(backend="filesystem", path=str(path), format="csv")


def test_dataframe_page_bounds_rows(tmp_path: Path) -> None:
    ref = _csv(tmp_path, 1000)
    access = PreviewDataAccess(max_rows=200)
    page = access.dataframe_page(ref, page=1, page_size=99999)
    # page_size is capped at the row budget.
    assert page.page_size == 200
    assert len(page.rows) == 200
    assert page.total_rows == 1000
    # #1920: a bounded page is not "truncated" — every row stays reachable by
    # paging. The page carries no truncation flag; reachability is total_pages.
    assert page.total_pages == 5
    assert not hasattr(page, "truncated")


def test_dataframe_page_sort(tmp_path: Path) -> None:
    ref = _csv(tmp_path, 50)
    access = PreviewDataAccess()
    page = access.dataframe_page(ref, sort_by="val", sort_dir="desc")
    assert page.sort_by == "val"
    assert page.sort_dir == "desc"
    assert page.rows[0]["val"] == 98  # max val = (49 * 2)


def test_text_chunk_bounds_bytes(tmp_path: Path) -> None:
    path = tmp_path / "big.txt"
    path.write_text("x" * 10000, encoding="utf-8")
    ref = StorageReference(backend="filesystem", path=str(path), format="txt")
    access = PreviewDataAccess(text_chars=100)
    chunk = access.text_chunk(ref)
    assert len(chunk.content) == 100
    assert chunk.truncated is True
    assert chunk.total_bytes == 10000


def test_collection_sample_bounds_items() -> None:
    access = PreviewDataAccess(max_items=3)
    items = [{"data_ref": f"d{i}", "type_name": "Image"} for i in range(20)]
    sample = access.collection_sample(count=20, item_type="Image", items=items)
    assert len(sample.items) == 3
    assert sample.count == 20
    assert sample.sampled is True


def test_composite_slots_inventory_only() -> None:
    access = PreviewDataAccess()
    slots = access.composite_slots({"slots": {"raster": "Array", "obs": "DataFrame"}})
    assert slots.slots == {"raster": "Array", "obs": "DataFrame"}


def test_composite_slots_read_the_type_from_a_recorded_slot_envelope() -> None:
    """A slot recorded as a wire envelope reports its type, not the envelope.

    The serializer writes each slot as ``{backend, path, format, metadata}`` with
    the type in ``metadata.type_chain``. Stringifying that mapping put a whole
    JSON blob on screen as the slot's "type" and matched no previewer, so opening
    the slot failed to route.
    """
    access = PreviewDataAccess()
    slots = access.composite_slots(
        {
            "slots": {
                "image": {
                    "backend": "zarr",
                    "path": "/p/image/data.zarr",
                    "format": None,
                    "metadata": {"type_chain": ["DataObject", "Array"], "framework": {}},
                },
                "measurements": {
                    "backend": "arrow",
                    "path": "/p/measurements/data.parquet",
                    "format": "parquet",
                    "metadata": {"type_chain": ["DataObject", "DataFrame"]},
                },
                "notes": "Text",
            }
        }
    )
    assert slots.slots == {"image": "Array", "measurements": "DataFrame", "notes": "Text"}
    for name, type_name in slots.slots.items():
        assert "{" not in type_name, f"{name} leaked a mapping as its type"


def test_composite_slots_report_no_type_when_the_record_carries_none() -> None:
    # A bare storage descriptor has no type to report; an empty name is honest
    # and lets the caller resolve the type from the slot itself.
    access = PreviewDataAccess()
    slots = access.composite_slots({"slots": {"raw": {"backend": "filesystem", "path": "/p/raw"}}})
    assert slots.slots == {"raw": ""}


def _write_composite(tmp_path: Path) -> StorageReference:
    """Persist a real two-slot composite via the core CompositeStore."""
    from scistudio.core.storage.composite_store import CompositeStore

    table = pa.table({"a": [1, 2, 3], "b": [4, 5, 6]})
    return CompositeStore().write(
        {"index": ("arrow", table)},
        StorageReference(backend="composite", path=str(tmp_path / "comp")),
    )


def test_composite_slot_ref_resolves_slot_from_manifest(tmp_path: Path) -> None:
    # #1830 / ADR-052 §8.5: resolve a composite slot's typed ref from the core
    # manifest — no StorageReference construction in author code.
    access = PreviewDataAccess()
    ref = _write_composite(tmp_path)

    slot_ref = access.composite_slot_ref(ref, "index")
    assert slot_ref is not None
    assert slot_ref.backend == "arrow"
    assert slot_ref.format == "parquet"
    assert slot_ref.path.endswith("index/data.parquet")

    # The resolved ref feeds the existing bounded readers end-to-end.
    page = access.dataframe_page(slot_ref, page=1, page_size=10)
    assert page.total_rows == 3
    assert "a" in page.columns


def test_composite_slot_ref_missing_slot_returns_none(tmp_path: Path) -> None:
    access = PreviewDataAccess()
    ref = _write_composite(tmp_path)
    assert access.composite_slot_ref(ref, "nope") is None


def test_composite_slot_ref_missing_manifest_returns_none(tmp_path: Path) -> None:
    access = PreviewDataAccess()
    ref = StorageReference(backend="composite", path=str(tmp_path / "absent"))
    assert access.composite_slot_ref(ref, "index") is None


def test_composite_slot_ref_corrupt_manifest_raises(tmp_path: Path) -> None:
    from scistudio.core.storage.errors import StorageReferenceInvalidError

    base = tmp_path / "broken"
    base.mkdir()
    (base / "manifest.json").write_text("{not json", encoding="utf-8")
    access = PreviewDataAccess()
    ref = StorageReference(backend="composite", path=str(base))
    with pytest.raises(StorageReferenceInvalidError):
        access.composite_slot_ref(ref, "index")


def test_array_tile_bounds_dimensions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sys
    import types

    class _FakeZarrArray:
        shape = (1024, 1024)
        dtype = "float32"

        def __getitem__(self, key: object) -> np.ndarray:
            return np.arange(1024 * 1024, dtype=np.float32).reshape(1024, 1024)[key]

    fake_zarr = types.ModuleType("zarr")
    fake_zarr.Array = _FakeZarrArray  # type: ignore[attr-defined]
    fake_zarr.open = lambda path, mode="r": _FakeZarrArray()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zarr", fake_zarr)

    zarr_path = tmp_path / "tile.zarr"
    zarr_path.mkdir()
    ref = StorageReference(backend="zarr", path=str(zarr_path), format="zarr")
    access = PreviewDataAccess(max_tile=64)
    tile = access.array_tile(ref, y0=0, x0=0, height=500, width=500)
    # Tile dimensions capped at the tile budget.
    assert tile.height == 64
    assert tile.width == 64
    assert len(tile.matrix) == 64
    assert len(tile.matrix[0]) == 64


def test_dataframe_page_caps_page_size(tmp_path: Path) -> None:
    ref = _csv(tmp_path, 10)
    access = PreviewDataAccess(max_rows=5)
    page = access.dataframe_page(ref, page_size=100)
    assert page.page_size == 5


def test_table_cells_are_json_safe_and_keep_missing_values_visible() -> None:
    """A cell JSON has no literal for must not take the whole page down.

    A table holding NaN or a timestamp column used to fail to serialise, so the
    preview reported "Out of range float values are not JSON compliant" instead
    of showing the data. Non-finite numbers keep the sentinel spelling the array
    reads use, so a missing measurement stays visible (#1886 item E).
    """
    import datetime
    import decimal
    import json

    from scistudio.panels.data_access import _json_safe_value

    assert _json_safe_value(float("nan")) == "NaN"
    assert _json_safe_value(float("inf")) == "Infinity"
    assert _json_safe_value(float("-inf")) == "-Infinity"
    assert _json_safe_value(1.5) == 1.5
    assert _json_safe_value(datetime.datetime(2026, 9, 11, 23, 4, 33)) == "2026-09-11T23:04:33"
    assert _json_safe_value(datetime.date(2026, 9, 11)) == "2026-09-11"
    assert _json_safe_value(decimal.Decimal("1.25")) == "1.25"
    assert _json_safe_value(b"\x00\x01") == "AAE="
    # Nested containers are covered too, and the result is strict-JSON encodable.
    json.dumps(_json_safe_value({"a": [float("nan"), datetime.date(2026, 1, 1)]}), allow_nan=False)
