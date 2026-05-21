"""Edge case tests for CompositeStore and StorageReference."""

from __future__ import annotations

import pytest

from scistudio.core.storage.composite_store import CompositeStore
from scistudio.core.storage.ref import StorageReference


class TestCompositeStoreEdgeCases:
    """CompositeStore — error paths."""

    def test_unknown_backend_raises(self) -> None:
        store = CompositeStore()
        with pytest.raises(ValueError, match="Unknown backend"):
            store._get_backend_for("nonexistent_backend")

    def test_write_non_dict_raises(self, tmp_path: pytest.TempPathFactory) -> None:
        store = CompositeStore()
        ref = StorageReference(backend="composite", path=str(tmp_path / "comp"))  # type: ignore[operator]
        with pytest.raises(TypeError, match="expects a dict"):
            store.write("not a dict", ref)


class TestStorageReference:
    """StorageReference — dataclass creation."""

    def test_creation_with_defaults(self) -> None:
        ref = StorageReference(backend="zarr", path="/tmp/test.zarr")
        assert ref.backend == "zarr"
        assert ref.path == "/tmp/test.zarr"
        assert ref.format is None
        assert ref.metadata is None

    def test_creation_with_all_fields(self) -> None:
        ref = StorageReference(
            backend="arrow",
            path="/tmp/data.parquet",
            format="parquet",
            metadata={"columns": ["a", "b"]},
        )
        assert ref.backend == "arrow"
        assert ref.format == "parquet"
        assert ref.metadata == {"columns": ["a", "b"]}
