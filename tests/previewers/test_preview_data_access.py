"""Bounded data-access tests (ADR-048 FR-009 / FR-010 / SC-004)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from scistudio.core.storage.ref import StorageReference
from scistudio.previewers.data_access import PreviewDataAccess


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
    assert page.truncated is True


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


def test_series_points_decimate() -> None:
    access = PreviewDataAccess(series_points=10)
    ref = StorageReference(backend="filesystem", path="/x", format="bin")
    result = access.series_points(ref, {"values": list(range(1000))})
    assert len(result.points) <= 10
    assert result.total == 1000
    assert result.truncated is True


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


def test_array_plane_does_not_materialize_full_zarr(monkeypatch, tmp_path: Path) -> None:
    """SC-004: a large array preview reads ONE bounded plane, never the whole array.

    The fake Zarr handle records every index access. A bounded ``array_plane``
    must NOT use the full-array ``handle[...]`` slice on a handle that exposes
    a ``.shape`` (the real-array contract); it must index a single plane.
    """
    import sys
    import types

    accesses: list[object] = []

    class _FakeZarrArray:
        shape = (50, 512, 512)  # 50 planes; full read would be ~13M floats
        dtype = "float32"

        def __getitem__(self, key: object) -> np.ndarray:
            accesses.append(key)
            # Return a 2-D plane regardless; the test asserts on the SELECTOR,
            # not the data, to prove no full ``[...]`` materialization happened.
            return np.zeros((512, 512), dtype=np.float32)

    fake_zarr = types.ModuleType("zarr")
    fake_zarr.Array = _FakeZarrArray  # type: ignore[attr-defined]
    fake_zarr.open = lambda path, mode="r": _FakeZarrArray()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "zarr", fake_zarr)

    zarr_path = tmp_path / "big.zarr"
    zarr_path.mkdir()
    ref = StorageReference(
        backend="zarr",
        path=str(zarr_path),
        format="zarr",
        metadata={"axes": ["z", "y", "x"], "shape": [50, 512, 512]},
    )
    access = PreviewDataAccess(max_dim=256)
    plane = access.array_plane(ref, slice_index=3)

    assert plane.shape == [50, 512, 512]
    assert plane.slice_axis_name == "z"
    assert plane.slice_axis_size == 50
    assert plane.slice_index == 3
    # The single read selector picked plane index 3 along axis 0 — NOT a full
    # ``Ellipsis`` / ``slice(None)`` materialization of all 50 planes.
    assert accesses, "expected exactly one bounded plane read"
    selector = accesses[0]
    assert selector is not Ellipsis
    assert isinstance(selector, tuple)
    assert selector[0] == 3  # bounded to the requested z-plane
    # Downsampled to <= max_dim on the longest side.
    assert len(plane.matrix) <= 256
    assert all(len(row) <= 256 for row in plane.matrix)


def test_array_tile_bounds_dimensions(monkeypatch, tmp_path: Path) -> None:
    import sys
    import types

    class _FakeZarrArray:
        shape = (1024, 1024)
        dtype = "float32"

        def __getitem__(self, key: object) -> np.ndarray:
            return np.arange(1024 * 1024, dtype=np.float32).reshape(1024, 1024)

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


def test_artifact_metadata_no_data_uri_for_large_file(tmp_path: Path) -> None:
    path = tmp_path / "big.png"
    path.write_bytes(b"x" * 4096)
    ref = StorageReference(backend="filesystem", path=str(path), format="png")
    access = PreviewDataAccess(max_bytes=1024)
    info = access.artifact_metadata(ref)
    assert info.size_bytes == 4096
    assert info.data_uri is None  # too large to inline
    assert info.mime_type == "image/png"


def test_dataframe_page_caps_page_size(tmp_path: Path) -> None:
    ref = _csv(tmp_path, 10)
    access = PreviewDataAccess(max_rows=5)
    page = access.dataframe_page(ref, page_size=100)
    assert page.page_size == 5
