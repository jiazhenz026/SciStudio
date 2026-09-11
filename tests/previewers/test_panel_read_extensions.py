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


def test_plane_extrema_include_unsampled_cells_in_bounded_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    source = np.ones((513, 769), dtype=">f4")
    source[1, 1], source[1, 2] = -12345, 98765  # neither is sampled
    source[0, 0] = np.nan
    access, ref, handle = array_reader(monkeypatch, source, max_dim=16)
    result = access.panel_array_plane(ref)
    assert result.values.shape == (16, 16)
    assert result.metadata["vmin"] == -12345
    assert result.metadata["vmax"] == 98765
    assert result.metadata["source_shape"] == [513, 769]
    assert result.metadata["source_dtype"] == ">f4"
    assert result.metadata["dtype"] == "<f4"
    assert result.metadata["sampled"] and result.metadata["truncated"] and not result.metadata["complete"]
    assert len(handle.keys) > 2  # sampled read and tiled full-plane extent scan
    restored = np.frombuffer(result.to_bytes(), dtype="<f4").reshape(result.metadata["shape"])
    np.testing.assert_array_equal(restored, source[::33, ::49])
    encoded = result.to_json()
    assert encoded["values"][0][0] is None
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
    assert not result.metadata["sampled"]


def test_tile_flags_nonfinite_and_invalid_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    source = np.ones((50, 50), dtype=np.float64)
    source[0, 0], source[0, 1] = np.inf, -np.inf
    access, ref, handle = array_reader(monkeypatch, source, max_cells=16, max_tile=4)
    result = access.panel_array_tile(ref, height=8, width=9)
    assert result.metadata["truncated"] and not result.metadata["complete"]
    assert result.to_json()["values"][0][:2] == [None, None]
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


def test_series_decimation_is_explicit_and_preserves_legacy_defaults(tmp_path: Path) -> None:
    path = tmp_path / "series.parquet"
    values = [float(i) for i in range(10001)]
    values[7] = float("nan")
    pq.write_table(pa.table({"time": np.arange(len(values)), "signal": values}), path, row_group_size=37)
    ref = StorageReference(backend="arrow", path=str(path))
    access = PreviewDataAccess(series_points=31)
    meta = {"index_name": "time", "value_name": "signal"}
    legacy = access.series_points(ref, meta)
    assert len(legacy.points) == 10000 and not legacy.truncated
    result = access.panel_series_points(ref, meta, max_points=11)
    assert result.metadata["nonnumeric"] == 1
    assert result.metadata["decimation"] == "uniform-index"
    assert result.metadata["sampled"] and not result.metadata["complete"]
    assert result.values.shape == (11, 2)
    assert result.values[0].tolist() == [0, 0]
    assert result.values[-1].tolist() == [10000, 10000]
    np.testing.assert_array_equal(np.frombuffer(result.to_bytes(), dtype="<f8").reshape(-1, 2), result.values)


def test_series_cap_and_indexed_values() -> None:
    access = PreviewDataAccess(max_bytes=64)
    ref = StorageReference(backend="filesystem", path="/nonexistent")
    result = access.panel_series_points(ref, {"values": list(range(100))}, max_points=1000)
    assert result.values.shape == (4, 2)
    assert result.values[:, 0].tolist() == [0, 33, 66, 99]
    with pytest.raises(ValueError, match="positive"):
        access.series_points(ref, {}, max_points=0)


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


def test_table_xy_streams_projected_columns_and_bounded_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "table.parquet"
    pq.write_table(pa.table({"time": list(range(1000)), "signal": list(range(1000)), "unused": ["x"] * 1000}), path)
    real_parquet_file = pq.ParquetFile
    batches = []

    class ObservedParquet:
        def __init__(self, source: Any) -> None:
            self.inner = real_parquet_file(source)
            self.schema_arrow = self.inner.schema_arrow
            self.metadata = self.inner.metadata

        def iter_batches(self, *, batch_size: int, columns: list[str]) -> Any:
            assert batch_size <= 17
            assert columns == ["time", "signal"]
            for batch in self.inner.iter_batches(batch_size=batch_size, columns=columns):
                batches.append(batch.num_rows)
                yield batch

    monkeypatch.setattr(pq, "ParquetFile", ObservedParquet)
    ref = StorageReference(backend="arrow", path=str(path))
    result = PreviewDataAccess(series_points=17).panel_table_xy(ref, max_points=12)
    assert len(batches) > 1 and sum(batches) == 1000
    assert result.values.shape == (12, 2)
    assert result.metadata["x_column"] == "time"
    assert result.metadata["y_column"] == "signal"
    assert result.metadata["sampled"]
    assert result.values[-1].tolist() == [999, 999]


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
