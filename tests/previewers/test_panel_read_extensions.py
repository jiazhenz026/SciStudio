"""Panel reads preserve source data and enforce budgets against storage itself."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scistudio.core.storage.ref import StorageReference
from scistudio.previewers.data_access import CollectionSample, PreviewDataAccess, SeriesPoints, TextChunk


class SlicedArray:
    """A lazy storage double that refuses unbounded plane materialization."""

    def __init__(self, values: np.ndarray, max_cells: int) -> None:
        self.values, self.shape, self.dtype = values, values.shape, values.dtype
        self.max_cells = max_cells
        self.keys: list[Any] = []

    def __getitem__(self, key: Any) -> np.ndarray:
        self.keys.append(key)
        result = self.values[key]
        assert result.size <= self.max_cells, f"unbounded storage read: {key}"
        return result


def array_reader(
    monkeypatch: pytest.MonkeyPatch, values: np.ndarray, *, max_cells: int = 65536, **limits: Any
) -> tuple[PreviewDataAccess, StorageReference, SlicedArray]:
    access = PreviewDataAccess(**limits)
    handle = SlicedArray(values, max_cells)
    monkeypatch.setattr(access, "_open_array_handle", lambda ref: (handle, list(handle.shape), str(handle.dtype)))
    ref = StorageReference(backend="zarr", path="/authorized/data.zarr")
    return access, ref, handle


def test_large_plane_is_never_sampled_and_reports_full_extent(monkeypatch: pytest.MonkeyPatch) -> None:
    """#2460: a plane too large for one read carries no stand-in values, only geometry and extent."""
    source = np.ones((513, 769), dtype=">f4")
    source[1, 1], source[1, 2] = -12345, 98765
    source[0, 0] = np.nan
    access, ref, handle = array_reader(monkeypatch, source, max_tile=16)
    result = access.panel_array_plane(ref)
    assert result.values.shape == (0, 0)
    assert result.metadata["vmin"] == -12345
    assert result.metadata["vmax"] == 98765
    assert result.metadata["source_shape"] == [513, 769]
    assert (result.metadata["height"], result.metadata["width"], result.metadata["tile_size"]) == (513, 769, 16)
    assert result.metadata["source_dtype"] == ">f4"
    assert result.metadata["truncated"] and not result.metadata["complete"]
    for key in ("sampled", "decimation", "strides"):
        assert key not in result.metadata
    # No read in the extent scan skipped a cell: every key is a contiguous window.
    for key in handle.keys:
        assert all(isinstance(part, slice) and part.step is None for part in key)
    # Every cell is reachable, exactly, through tiles.
    rebuilt = np.empty(source.shape, dtype="<f4")
    for y in range(0, 513, 16):
        for x in range(0, 769, 16):
            tile = access.panel_array_tile(ref, y0=y, x0=x, height=16, width=16)
            rebuilt[y : y + tile.values.shape[0], x : x + tile.values.shape[1]] = tile.values
    np.testing.assert_array_equal(rebuilt, source)


def test_plane_that_fits_one_read_is_complete_and_exact(monkeypatch: pytest.MonkeyPatch) -> None:
    source = np.arange(12 * 16, dtype=">f4").reshape(12, 16)
    source[0, 0] = np.nan
    access, ref, _ = array_reader(monkeypatch, source, max_tile=16)
    result = access.panel_array_plane(ref)
    assert result.metadata["complete"] and not result.metadata["truncated"]
    assert result.metadata["dtype"] == "<f4"
    restored = np.frombuffer(result.to_bytes(), dtype="<f4").reshape(result.metadata["shape"])
    np.testing.assert_array_equal(restored, source)
    encoded = result.to_json()
    # NaN is conveyed distinctly as the sentinel "NaN", never erased to null (#1886 E).
    assert encoded["values"][0][0] == "NaN"
    json.dumps(encoded, allow_nan=False)


def test_tile_slices_storage_and_transposes_named_axes(monkeypatch: pytest.MonkeyPatch) -> None:
    source = np.arange(7 * 1000 * 1200, dtype=np.int16).reshape(7, 1000, 1200)
    access, ref, handle = array_reader(monkeypatch, source, max_cells=30, max_tile=8)
    ref.metadata = {"axes": ["z", "x", "y"]}
    result = access.panel_array_tile(ref, axis_indices={0: 3}, y0=40, x0=70, height=5, width=6)
    assert handle.keys == [(3, slice(70, 76), slice(40, 45))]
    np.testing.assert_array_equal(result.values, source[3, 70:76, 40:45].T)
    assert result.metadata["shape"] == [5, 6]
    assert result.metadata["dtype"] == "<i2"
    assert result.metadata["complete"]
    assert "sampled" not in result.metadata


def test_tile_flags_nonfinite_and_invalid_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    source = np.ones((50, 50), dtype=np.float64)
    source[0, 0], source[0, 1] = np.inf, -np.inf
    access, ref, handle = array_reader(monkeypatch, source, max_cells=16, max_tile=4)
    result = access.panel_array_tile(ref, height=8, width=9)
    assert result.metadata["truncated"] and not result.metadata["complete"]
    # +inf and -inf are conveyed as distinct sentinels, not both flattened to null.
    assert result.to_json()["values"][0][:2] == ["Infinity", "-Infinity"]
    assert np.isinf(np.frombuffer(result.to_bytes(), dtype="<f8")[:2]).all()
    before = len(handle.keys)
    for kwargs in [{"y0": -1}, {"x0": 51}, {"height": -1}, {"axis_indices": {0: 1}}]:
        with pytest.raises(ValueError):
            access.panel_array_tile(ref, **kwargs)
    assert len(handle.keys) == before


@pytest.mark.parametrize("shape", [(), (9,), (0,), (2, 0), (0, 2)])
def test_empty_scalar_and_vector_numeric_shapes(monkeypatch: pytest.MonkeyPatch, shape: tuple[int, ...]) -> None:
    source = np.zeros(shape, dtype=np.uint16)
    access, ref, _ = array_reader(monkeypatch, source)
    result = access.panel_array_plane(ref)
    assert result.values.ndim == 2
    assert result.metadata["vmin"] == (0 if source.size else None)
    assert result.metadata["vmax"] == (0 if source.size else None)
    assert len(result.to_bytes()) == result.values.size * 2


def test_array_byte_budget_rejected_before_tile_storage_read(monkeypatch: pytest.MonkeyPatch) -> None:
    access, ref, handle = array_reader(monkeypatch, np.ones((10, 10)), max_bytes=32)
    with pytest.raises(ValueError, match="byte budget"):
        access.panel_array_tile(ref, height=10, width=10)
    assert not handle.keys
    plane = access.panel_array_plane(ref)
    assert plane.values.nbytes <= 32


def test_series_pages_return_every_exact_row_in_source_order(tmp_path: Path) -> None:
    """#2460: following next_offset reaches every row; nothing is decimated or dropped."""
    path = tmp_path / "series.parquet"
    values = [float(i) for i in range(10001)]
    values[7] = float("nan")
    values[9000] = float("-inf")
    pq.write_table(pa.table({"time": np.arange(len(values)) * 0.25, "signal": values}), path, row_group_size=37)
    ref = StorageReference(backend="arrow", path=str(path))
    access = PreviewDataAccess()
    meta = {"index_name": "time", "value_name": "signal"}
    legacy = access.series_points(ref, meta)
    assert len(legacy.points) == 9999 and not legacy.truncated
    pages, offset = [], 0
    while offset is not None:
        page = access.panel_series_points(ref, meta, offset=offset, limit=1024)
        assert page.metadata["offset"] == offset and page.metadata["total"] == 10001
        assert page.metadata["truncated"] is (page.metadata["next_offset"] is not None)
        assert page.metadata["complete"] is (page.metadata["next_offset"] is None)
        for key in ("sampled", "decimation", "source_indices", "nonfinite_positions_complete"):
            assert key not in page.metadata
        pages.append(page)
        offset = page.metadata["next_offset"]
    assert len(pages) == 10
    rows = np.concatenate([page.values for page in pages])
    np.testing.assert_array_equal(rows[:, 0], np.arange(10001) * 0.25)
    np.testing.assert_array_equal(rows[:, 1], np.asarray(values))
    assert sum(page.metadata["nonnumeric"] for page in pages) == 2
    np.testing.assert_array_equal(np.frombuffer(pages[0].to_bytes(), dtype="<f8").reshape(-1, 2), pages[0].values)
    # Non-finite values stay in place, as distinct JSON sentinels.
    assert pages[0].to_json()["values"][7] == [1.75, "NaN"]


def test_series_window_over_in_memory_values_and_invalid_windows() -> None:
    access = PreviewDataAccess()
    ref = StorageReference(backend="filesystem", path="/nonexistent")
    result = access.panel_series_points(ref, {"values": [3, None, "x", 4.5]}, offset=1, limit=2)
    assert result.values[:, 0].tolist() == [1.0, 2.0]
    assert np.isnan(result.values[:, 1]).all()
    assert result.metadata["next_offset"] == 3 and result.metadata["nonnumeric"] == 2
    last = access.panel_series_points(ref, {"values": [3, None, "x", 4.5]}, offset=3, limit=2)
    assert last.values.tolist() == [[3.0, 4.5]] and last.metadata["complete"]
    for kwargs in ({"offset": -1, "limit": 1}, {"offset": 0, "limit": 0}, {"offset": 9, "limit": 1}):
        with pytest.raises(ValueError):
            access.panel_series_points(ref, {"values": [1, 2]}, **kwargs)
    with pytest.raises(ValueError, match="budget"):
        PreviewDataAccess(max_bytes=64).panel_series_points(ref, {"values": list(range(100))}, limit=100)


def test_text_byte_offsets_preserve_utf8_across_windows(tmp_path: Path) -> None:
    source = "abc中文🙂 xyz" * 20
    path = tmp_path / "unicode.txt"
    path.write_text(source, encoding="utf-8")
    ref = StorageReference(backend="filesystem", path=str(path))
    access = PreviewDataAccess(text_chars=10)
    chunks, offset = [], 0
    while True:
        chunk = access.text_chunk(ref, offset=offset, length=999999)
        assert chunk.offset == offset and chunk.encoding == "utf-8"
        chunks.append(chunk.content)
        if chunk.next_offset is None:
            break
        assert offset < chunk.next_offset <= offset + 10
        offset = chunk.next_offset
    assert "".join(chunks) == source
    assert not chunk.truncated
    for kwargs in [{"offset": -1}, {"offset": path.stat().st_size + 1}, {"length": 0}]:
        with pytest.raises(ValueError):
            access.text_chunk(ref, **kwargs)


def test_collection_cursor_slices_only_requested_page() -> None:
    class Inventory(list):
        def __getitem__(self, key: Any) -> Any:
            assert isinstance(key, slice) and key.stop - key.start <= 3
            return super().__getitem__(key)

    items = Inventory([{"data_ref": str(i)} for i in range(8)])
    access = PreviewDataAccess(max_items=3)
    collected, cursor = [], None
    while True:
        page = access.collection_sample(count=8, item_type="Image", items=items, cursor=cursor, limit=999)
        collected.extend(page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert collected == items
    first = access.collection_sample(count=8, item_type=None, items=items, limit=3)
    with pytest.raises(ValueError, match="stale"):
        access.collection_sample(count=9, item_type=None, items=[*items, {}], cursor=first.next_cursor)
    with pytest.raises(ValueError, match="cursor"):
        access.collection_sample(count=8, item_type=None, items=items, cursor="nonsense")


def test_large_artifact_access_does_not_read_inline_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "large.pdf"
    with path.open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    ref = StorageReference(backend="filesystem", path=str(path))
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("large file must not load inline"))
    access = PreviewDataAccess(max_bytes=64)
    assert access.artifact_metadata(ref).data_uri is None
    assert access.artifact_file(ref) == path.resolve()


def test_legacy_result_positional_construction_is_unchanged() -> None:
    assert SeriesPoints([], 0, False, 2).nonnumeric == 2
    assert TextChunk("text", False, 4, "txt").language == "txt"
    assert CollectionSample(0, None, [], False).next_cursor is None


def test_table_xy_page_reads_only_its_row_groups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "table.parquet"
    table = pa.table({"time": list(range(1000)), "signal": [i * 2 for i in range(1000)], "unused": ["x"] * 1000})
    pq.write_table(table, path, row_group_size=100)
    real_read = pq.ParquetFile.read_row_group
    groups: list[int] = []

    def observed(self: Any, index: int, columns: Any = None, **kwargs: Any) -> Any:
        assert columns == ["time", "signal"]
        groups.append(index)
        return real_read(self, index, columns=columns, **kwargs)

    monkeypatch.setattr(pq.ParquetFile, "read_row_group", observed)
    ref = StorageReference(backend="arrow", path=str(path))
    result = PreviewDataAccess().panel_table_xy(ref, offset=250, limit=120)
    assert groups == [2, 3]
    assert result.values[:, 0].tolist() == list(range(250, 370))
    assert result.values[:, 1].tolist() == [i * 2 for i in range(250, 370)]
    assert result.metadata["x_column"] == "time"
    assert result.metadata["y_column"] == "signal"
    assert result.metadata["next_offset"] == 370 and result.metadata["truncated"]


def test_partial_legacy_collection_sample_has_no_unusable_cursor() -> None:
    page = PreviewDataAccess(max_items=2).collection_sample(
        count=100, item_type="Text", items=[{"data_ref": str(i)} for i in range(5)]
    )
    assert len(page.items) == 2 and page.sampled
    assert page.next_cursor is None


def test_plane_extrema_preserve_large_integer_precision(monkeypatch: pytest.MonkeyPatch) -> None:
    source = np.array([[2**63 + 1, 2**63 + 7]], dtype=np.uint64)
    access, ref, _ = array_reader(monkeypatch, source)
    result = access.panel_array_plane(ref)
    assert result.metadata["vmin"] == 2**63 + 1
    assert result.metadata["vmax"] == 2**63 + 7
    assert result.to_json()["values"] == [[2**63 + 1, 2**63 + 7]]
    assert np.frombuffer(result.to_bytes(), dtype="<u8").tolist() == [2**63 + 1, 2**63 + 7]


def test_numeric_read_conveys_all_three_nonfinite_kinds_distinctly() -> None:
    """#1886 E: NaN / +inf / -inf are three distinct sentinels, never one null."""
    from scistudio.previewers._read_arrays import numeric_read

    values = np.array([[np.nan, np.inf, -np.inf, 1.5]], dtype="<f8")
    encoded = numeric_read(values, {}, max_bytes=1024).to_json()["values"]
    assert encoded == [["NaN", "Infinity", "-Infinity", 1.5]]
    json.dumps(encoded, allow_nan=False)


def test_collection_page_paging_reaches_every_item_beyond_first_page() -> None:
    """#1886 B: dataframe-style page/page_size makes every item reachable."""
    items = [{"data_ref": str(i)} for i in range(250)]
    access = PreviewDataAccess(max_items=100)

    first = access.collection_sample(count=250, item_type="Image", items=items, page=1, page_size=100)
    assert (first.page, first.page_size, first.total_pages) == (1, 100, 3)
    assert first.count == 250 and first.sampled
    assert [it["data_ref"] for it in first.items] == [str(i) for i in range(100)]

    # A specific later page is directly reachable — item 150+ lives past page 1.
    third = access.collection_sample(count=250, item_type="Image", items=items, page=3, page_size=100)
    assert third.page == 3
    assert [it["data_ref"] for it in third.items] == [str(i) for i in range(200, 250)]

    # Paging 1..total_pages reaches the whole inventory, nothing silently capped.
    seen: list[str] = []
    for p in range(1, first.total_pages + 1):
        sample = access.collection_sample(count=250, item_type="Image", items=items, page=p, page_size=100)
        seen.extend(it["data_ref"] for it in sample.items)
    assert seen == [str(i) for i in range(250)]

    # page_size is capped at the item budget (still every item reachable by paging).
    capped = access.collection_sample(count=250, item_type="Image", items=items, page=1, page_size=999)
    assert capped.page_size == 100 and capped.total_pages == 3

    with pytest.raises(ValueError, match="either"):
        access.collection_sample(count=250, item_type=None, items=items, page=1, cursor="x")
    with pytest.raises(ValueError, match="inventory"):
        access.collection_sample(count=250, item_type=None, items=items[:5], page=1)
    with pytest.raises(ValueError, match="positive"):
        access.collection_sample(count=250, item_type=None, items=items, page=0)


def test_series_and_table_nonfinite_positions_surface_gaps(tmp_path: Path) -> None:
    """#1886 D: dropped non-finite points report *where* they were, not just how many."""
    access = PreviewDataAccess()
    ref = StorageReference(backend="filesystem", path="/nonexistent")
    series = access.series_points(ref, {"values": [1.0, float("nan"), 3.0, float("inf"), 5.0]})
    assert series.nonnumeric == 2
    assert series.nonfinite_positions == [1, 3]

    path = tmp_path / "xy.parquet"
    pq.write_table(pa.table({"x": [0.0, 1.0, float("nan"), 3.0], "y": [10.0, float("inf"), 12.0, 13.0]}), path)
    xy = access.table_xy_points(StorageReference(backend="arrow", path=str(path)), x_column="x", y_column="y")
    assert xy.nonnumeric == 2
    assert xy.nonfinite_positions == [1, 2]


def test_read_budget_is_20_mib_and_refuses_oversized_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1886 G: the transport budget is 20 MiB and an unfittable read is refused, not degraded."""
    from scistudio.panels.contexts import READ_BYTES
    from scistudio.previewers.data_access import DEFAULT_MAX_BYTES
    from scistudio.previewers.models import PreviewLimits

    assert DEFAULT_MAX_BYTES == 20 * 1024 * 1024
    assert READ_BYTES == 20 * 1024 * 1024
    assert PreviewLimits().max_bytes == 20 * 1024 * 1024

    # A native-resolution tile too large for one read is refused with an explicit
    # "too large" error, never a silent decimated/degraded stand-in.
    access, ref, handle = array_reader(monkeypatch, np.ones((4096, 4096), dtype="<f8"), max_cells=10**9, max_tile=4096)
    with pytest.raises(ValueError, match="budget"):
        access.panel_array_tile(ref, height=4096, width=4096)
    assert not handle.keys  # refused before touching storage

    # A native-resolution tile that fits the 20 MiB budget is served in full.
    fits = access.panel_array_tile(ref, height=512, width=512)
    assert fits.values.shape == (512, 512)
    assert fits.metadata["complete"]
