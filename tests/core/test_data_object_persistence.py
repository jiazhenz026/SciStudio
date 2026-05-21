"""Tests for DataObject persistence — get_in_memory_data() and save()."""

from __future__ import annotations

import numpy as np
import pytest

from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.text import Text


class TestArrayGetInMemoryData:
    """Array.get_in_memory_data — returns numpy array from _data."""

    def test_array_get_in_memory_data(self) -> None:
        arr = Array(axes=["y", "x"], shape=(3, 3), dtype="float64")
        arr._data = np.ones((3, 3))
        result = arr.get_in_memory_data()
        assert isinstance(result, np.ndarray)
        assert result.shape == (3, 3)


class TestTextGetInMemoryData:
    """Text.get_in_memory_data — returns content string."""

    def test_text_get_in_memory_data(self) -> None:
        t = Text(content="hello world")
        result = t.get_in_memory_data()
        assert result == "hello world"


class TestBareDataObjectRaises:
    """DataObject.get_in_memory_data — raises ValueError without data."""

    def test_bare_dataobject_raises(self) -> None:
        obj = DataObject()
        with pytest.raises(ValueError, match="has no in-memory data"):
            obj.get_in_memory_data()


class TestSaveArrayToZarr:
    """Array.save — creates zarr store and sets storage_ref."""

    def test_save_array_to_zarr(self, tmp_path: object) -> None:
        import zarr

        arr = Array(axes=["y", "x"], shape=(4, 4), dtype="float32")
        arr._data = np.arange(16, dtype="float32").reshape(4, 4)

        target = (tmp_path / "test.zarr").as_posix()
        ref = arr.save(target)

        assert ref is not None
        assert ref.backend == "zarr"
        assert ref.path == target
        assert arr.storage_ref is not None
        assert arr.storage_ref.backend == "zarr"

        # Verify data was actually written
        z = zarr.open_array(target, mode="r")
        loaded = np.asarray(z)
        np.testing.assert_array_equal(loaded, arr._data)


class TestSaveIdempotency:
    """DataObject.save — subsequent calls are no-ops."""

    def test_save_is_idempotent(self, tmp_path: object) -> None:
        arr = Array(axes=["y", "x"], shape=(2, 2), dtype="float64")
        arr._data = np.ones((2, 2))

        target = (tmp_path / "idem.zarr").as_posix()
        ref1 = arr.save(target)
        ref2 = arr.save("/different/path.zarr")

        assert ref1 is ref2  # exact same object returned


class TestSaveDataFrameToArrow:
    """DataFrame.save — round-trip through ArrowBackend."""

    def test_save_dataframe_to_arrow(self, tmp_path: object) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        from scistudio.core.types.dataframe import DataFrame

        df = DataFrame(columns=["a", "b"], row_count=3)
        df._arrow_table = pa.table({"a": [1, 2, 3], "b": [4, 5, 6]})

        target = (tmp_path / "test.parquet").as_posix()
        ref = df.save(target)

        assert ref is not None
        assert ref.backend == "arrow"
        assert ref.path == target
        assert df.storage_ref is not None

        loaded = pq.read_table(target)
        assert loaded.column_names == ["a", "b"]
        assert loaded.num_rows == 3


class TestSaveTextToFilesystem:
    """Text.save — round-trip through FilesystemBackend."""

    def test_save_text_to_filesystem(self, tmp_path: object) -> None:
        from pathlib import Path

        t = Text(content="hello world")

        target = (tmp_path / "test.txt").as_posix()
        ref = t.save(target)

        assert ref is not None
        assert ref.backend == "filesystem"
        assert ref.path == target
        assert t.storage_ref is not None

        loaded = Path(target).read_text(encoding="utf-8")
        assert loaded == "hello world"


class TestWriteFromMemoryZarr:
    """ZarrBackend.write_from_memory — round-trip test."""

    def test_write_from_memory(self, tmp_path: object) -> None:
        import zarr

        from scistudio.core.storage.zarr_backend import ZarrBackend

        backend = ZarrBackend()
        data = np.arange(12, dtype="int32").reshape(3, 4)
        target = (tmp_path / "wfm.zarr").as_posix()

        ref = backend.write_from_memory(data, target)

        assert ref.backend == "zarr"
        assert ref.path == target
        loaded = np.asarray(zarr.open_array(target, mode="r"))
        np.testing.assert_array_equal(loaded, data)


class TestWriteFromMemoryArrow:
    """ArrowBackend.write_from_memory — round-trip test."""

    def test_write_from_memory(self, tmp_path: object) -> None:
        import pyarrow.parquet as pq

        from scistudio.core.storage.arrow_backend import ArrowBackend

        backend = ArrowBackend()
        data = {"x": [10, 20], "y": [30, 40]}
        target = (tmp_path / "wfm.parquet").as_posix()

        ref = backend.write_from_memory(data, target)

        assert ref.backend == "arrow"
        assert ref.path == target
        loaded = pq.read_table(target)
        assert loaded.column_names == ["x", "y"]
        assert loaded.num_rows == 2


class TestWriteFromMemoryFilesystem:
    """FilesystemBackend.write_from_memory — round-trip test."""

    def test_write_from_memory(self, tmp_path: object) -> None:
        from pathlib import Path

        from scistudio.core.storage.filesystem import FilesystemBackend

        backend = FilesystemBackend()
        target = (tmp_path / "wfm.txt").as_posix()

        ref = backend.write_from_memory("test content", target)

        assert ref.backend == "filesystem"
        assert ref.path == target
        loaded = Path(target).read_text(encoding="utf-8")
        assert loaded == "test content"
