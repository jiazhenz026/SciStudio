"""Tests for StorageReference path normalization (#53)."""

from __future__ import annotations

from scistudio.core.storage.ref import StorageReference


class TestStorageReferencePathNormalization:
    """Verify that StorageReference normalizes paths to POSIX format."""

    def test_backslash_converted(self) -> None:
        ref = StorageReference(backend="zarr", path="C:\\Users\\test\\data.zarr")
        assert ref.path == "C:/Users/test/data.zarr"

    def test_mixed_separators(self) -> None:
        ref = StorageReference(backend="arrow", path="data/parquet\\table.parquet")
        assert ref.path == "data/parquet/table.parquet"

    def test_unc_path(self) -> None:
        ref = StorageReference(backend="filesystem", path="\\\\server\\share\\file.txt")
        assert ref.path == "//server/share/file.txt"

    def test_posix_unchanged(self) -> None:
        ref = StorageReference(backend="zarr", path="data/zarr/img_001")
        assert ref.path == "data/zarr/img_001"

    def test_metadata_preserved(self) -> None:
        ref = StorageReference(backend="zarr", path="C:\\data\\test", metadata={"key": "val"})
        assert ref.path == "C:/data/test"
        assert ref.metadata == {"key": "val"}
