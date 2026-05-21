"""Regression tests for #436: _auto_flush must recurse into CompositeData slots."""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import MagicMock, patch

from scistudio.blocks.base.block import Block
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData


class _StubDataObject(DataObject):
    """Minimal DataObject subclass for testing."""

    def save(self, path: str) -> None:
        # Simulate a successful save by setting storage_ref.
        from scistudio.core.storage.ref import StorageReference

        self.storage_ref = StorageReference(backend="local", path=path, format="stub")

    @classmethod
    def load(cls, path: str) -> _StubDataObject:
        return cls()


class _StubComposite(CompositeData):
    """CompositeData with one expected slot."""

    expected_slots: ClassVar[dict[str, type]] = {"raster": _StubDataObject}

    def save(self, path: str) -> None:
        """Minimal save that sets storage_ref (test stub)."""
        from scistudio.core.storage.ref import StorageReference

        self.storage_ref = StorageReference(backend="local", path=path, format="stub")


def test_auto_flush_recurses_into_composite_slots() -> None:
    """_auto_flush should flush unflushed slots inside CompositeData (#436)."""
    inner = _StubDataObject()
    assert inner.storage_ref is None

    composite = _StubComposite(slots={"raster": inner})
    assert composite._slots["raster"].storage_ref is None

    with (
        patch("scistudio.core.storage.flush_context.get_output_dir", return_value="/tmp/test_flush"),
        patch("scistudio.core.storage.backend_router.get_router") as mock_router,
    ):
        router_inst = MagicMock()
        router_inst.extension_for.return_value = ".dat"
        mock_router.return_value = router_inst

        Block._auto_flush(composite)

    # The inner slot should now have a storage_ref after recursive flush.
    assert composite._slots["raster"].storage_ref is not None


def test_auto_flush_skips_already_flushed_slots() -> None:
    """_auto_flush should skip slots that already have a storage_ref."""
    from scistudio.core.storage.ref import StorageReference

    inner = _StubDataObject()
    inner.storage_ref = StorageReference(backend="local", path="/already/flushed", format="stub")

    composite = _StubComposite(slots={"raster": inner})

    with (
        patch("scistudio.core.storage.flush_context.get_output_dir", return_value="/tmp/test_flush"),
        patch("scistudio.core.storage.backend_router.get_router") as mock_router,
    ):
        router_inst = MagicMock()
        router_inst.extension_for.return_value = ".dat"
        mock_router.return_value = router_inst

        Block._auto_flush(composite)

    # storage_ref should be unchanged.
    assert inner.storage_ref.path == "/already/flushed"
