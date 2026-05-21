"""Tests for Collection — ADR-020.

T-006 (ADR-027 D2) removed ``Image`` from core. This module keeps its
historical coverage by defining a local shim subclass that mimics the
pre-T-006 constructor surface (``shape=``, ``ndim=``, ``dtype=``). Full
migration is part of T-008.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from scistudio.core.storage.flush_context import clear, set_output_dir
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame


@pytest.fixture(autouse=True)
def _flush_context(tmp_path):
    """ADR-031 Addendum 1: auto_flush now hard-gates on output_dir."""
    set_output_dir(str(tmp_path))
    yield
    clear()


class Image(Array):
    """T-006 shim — plugin migration tracked by T-008."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})

    def __init__(
        self,
        *,
        shape: tuple[int, ...] | None = None,
        ndim: int | None = None,
        dtype: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(axes=["y", "x"], shape=shape, dtype=dtype, **kwargs)


# -- Construction and invariants -----------------------------------------------


class TestCollectionConstruction:
    def test_homogeneous_items(self) -> None:
        """Collection with same-typed items succeeds."""
        img1 = Image(shape=(10, 10), ndim=2, dtype="uint8")
        img2 = Image(shape=(20, 20), ndim=2, dtype="uint8")
        coll = Collection([img1, img2])
        assert coll.item_type is Image
        assert len(coll) == 2
        assert coll.length == 2

    def test_rejects_mixed_types(self) -> None:
        """Collection with different types raises TypeError."""
        img = Image(shape=(10, 10), ndim=2, dtype="uint8")
        df = DataFrame(columns=["a"], row_count=1)
        with pytest.raises(TypeError, match="homogeneous"):
            Collection([img, df])

    def test_single_item(self) -> None:
        """Single item creates Collection with length=1."""
        img = Image(shape=(5, 5), ndim=2, dtype="float32")
        coll = Collection([img])
        assert len(coll) == 1
        assert coll.item_type is Image

    def test_empty_with_item_type(self) -> None:
        """Empty Collection with explicit item_type succeeds."""
        coll = Collection([], item_type=Image)
        assert len(coll) == 0
        assert coll.item_type is Image

    def test_empty_without_item_type_raises(self) -> None:
        """Empty Collection without item_type raises TypeError (ADR-020-Add6)."""
        with pytest.raises(TypeError, match="item_type is required"):
            Collection([])

    def test_explicit_item_type_overrides(self) -> None:
        """Explicit item_type is used even when items are provided."""
        obj = DataObject()
        coll = Collection([obj], item_type=DataObject)
        assert coll.item_type is DataObject

    def test_item_type_immutable(self) -> None:
        """item_type cannot be changed after construction."""
        img = Image(shape=(10, 10), ndim=2, dtype="uint8")
        coll = Collection([img])
        with pytest.raises(AttributeError):
            coll.item_type = DataFrame  # type: ignore[misc]


# -- Protocols -----------------------------------------------------------------


class TestCollectionProtocols:
    def test_iter(self) -> None:
        """Collection supports iteration."""
        img1 = Image(shape=(1, 1), ndim=2, dtype="uint8")
        img2 = Image(shape=(2, 2), ndim=2, dtype="uint8")
        coll = Collection([img1, img2])
        items = list(coll)
        assert items == [img1, img2]

    def test_len(self) -> None:
        """Collection supports len()."""
        coll = Collection([], item_type=Image)
        assert len(coll) == 0

    def test_getitem_index(self) -> None:
        """Collection supports integer indexing."""
        img1 = Image(shape=(1, 1), ndim=2, dtype="uint8")
        img2 = Image(shape=(2, 2), ndim=2, dtype="uint8")
        coll = Collection([img1, img2])
        assert coll[0] is img1
        assert coll[1] is img2

    def test_getitem_slice(self) -> None:
        """Collection supports slice indexing."""
        imgs = [Image(shape=(i, i), ndim=2, dtype="uint8") for i in range(1, 4)]
        coll = Collection(imgs)
        sliced = coll[0:2]
        assert len(sliced) == 2
        assert sliced[0] is imgs[0]

    def test_getitem_negative_index(self) -> None:
        """Collection supports negative indexing."""
        img1 = Image(shape=(1, 1), ndim=2, dtype="uint8")
        img2 = Image(shape=(2, 2), ndim=2, dtype="uint8")
        coll = Collection([img1, img2])
        assert coll[-1] is img2

    def test_class_getitem(self) -> None:
        """Collection[Image] syntax works for type annotations."""
        alias = Collection[Image]
        assert alias is Collection

    def test_repr(self) -> None:
        """Collection has a readable repr."""
        img = Image(shape=(10, 10), ndim=2, dtype="uint8")
        coll = Collection([img])
        assert "Collection[Image](length=1)" in repr(coll)


# -- storage_refs --------------------------------------------------------------


class TestStorageRefs:
    def test_storage_refs_with_refs(self) -> None:
        """storage_refs extracts StorageReference from each item."""
        ref1 = StorageReference(backend="zarr", path="/a")
        ref2 = StorageReference(backend="zarr", path="/b")
        obj1 = DataObject(storage_ref=ref1)
        obj2 = DataObject(storage_ref=ref2)
        coll = Collection([obj1, obj2])
        refs = coll.storage_refs
        assert len(refs) == 2
        assert refs[0] is ref1
        assert refs[1] is ref2

    def test_storage_refs_without_refs(self) -> None:
        """storage_refs returns None entries for items without refs."""
        obj = DataObject()
        coll = Collection([obj])
        refs = coll.storage_refs
        assert refs == [None]


# -- Block utilities (pack/unpack) ---------------------------------------------


class TestBlockCollectionUtilities:
    def test_pack_creates_collection(self) -> None:
        """Block.pack() creates a Collection from items."""
        from scistudio.blocks.base.block import Block

        img1 = Image(shape=(1, 1), ndim=2, dtype="uint8")
        img2 = Image(shape=(2, 2), ndim=2, dtype="uint8")
        coll = Block.pack([img1, img2], item_type=Image)
        assert isinstance(coll, Collection)
        assert len(coll) == 2
        assert coll.item_type is Image

    def test_unpack_returns_list(self) -> None:
        """Block.unpack() returns a list of items."""
        from scistudio.blocks.base.block import Block

        img = Image(shape=(1, 1), ndim=2, dtype="uint8")
        coll = Collection([img])
        items = Block.unpack(coll)
        assert isinstance(items, list)
        assert items[0] is img

    def test_unpack_single_success(self) -> None:
        """Block.unpack_single() returns the single item."""
        from scistudio.blocks.base.block import Block

        img = Image(shape=(1, 1), ndim=2, dtype="uint8")
        coll = Collection([img])
        result = Block.unpack_single(coll)
        assert result is img

    def test_unpack_single_fails_for_multiple(self) -> None:
        """Block.unpack_single() raises ValueError for length != 1."""
        from scistudio.blocks.base.block import Block

        imgs = [Image(shape=(i, i), ndim=2, dtype="uint8") for i in range(1, 4)]
        coll = Collection(imgs)
        with pytest.raises(ValueError, match="single-item"):
            Block.unpack_single(coll)

    def test_pack_unpack_roundtrip(self) -> None:
        """pack() then unpack() returns original items."""
        from scistudio.blocks.base.block import Block

        imgs = [Image(shape=(i, i), ndim=2, dtype="uint8") for i in range(1, 4)]
        coll = Block.pack(imgs, item_type=Image)
        unpacked = Block.unpack(coll)
        assert len(unpacked) == 3
        for orig, unpk in zip(imgs, unpacked, strict=True):
            assert orig is unpk

    def test_map_items(self) -> None:
        """Block.map_items() applies function to each item."""
        from scistudio.blocks.base.block import Block

        imgs = [Image(shape=(i, i), ndim=2, dtype="uint8") for i in range(1, 4)]
        coll = Collection(imgs)

        def transform(item: DataObject) -> DataObject:
            return Image(shape=(99, 99), ndim=2, dtype="uint8")

        result = Block.map_items(transform, coll)
        assert isinstance(result, Collection)
        assert len(result) == 3
        assert result[0].shape == (99, 99)

    def test_auto_flush_passthrough(self) -> None:
        """_auto_flush returns object as-is when it has a storage_ref."""
        from scistudio.blocks.base.block import Block

        ref = StorageReference(backend="zarr", path="/test")
        obj = DataObject(storage_ref=ref)
        result = Block._auto_flush(obj)
        assert result is obj

    def test_auto_flush_no_ref_returns_as_is_without_context(self) -> None:
        """_auto_flush returns object as-is when output_dir not set."""
        from scistudio.blocks.base.block import Block

        clear()  # Remove the autouse fixture's output_dir
        obj = DataObject()
        result = Block._auto_flush(obj)
        assert result is obj


# -- Port Collection transparency ----------------------------------------------


class TestPortCollectionTransparency:
    def test_port_accepts_type_with_collection_instance(self) -> None:
        """port_accepts_type handles Collection instance check."""
        from scistudio.blocks.base.ports import InputPort, port_accepts_type

        port = InputPort(name="data", accepted_types=[Image])
        # Collection is not a type, it's an instance check — for type-based
        # checks, the caller passes the actual type, not the Collection.
        assert port_accepts_type(port, Image) is True
        assert port_accepts_type(port, DataFrame) is False

    def test_port_accepts_dataobject_base(self) -> None:
        """Port accepting DataObject accepts all subtypes."""
        from scistudio.blocks.base.ports import InputPort, port_accepts_type

        port = InputPort(name="data", accepted_types=[DataObject])
        assert port_accepts_type(port, Image) is True
        assert port_accepts_type(port, DataFrame) is True

    def test_port_empty_accepted_types(self) -> None:
        """Port with empty accepted_types accepts anything."""
        from scistudio.blocks.base.ports import InputPort, port_accepts_type

        port = InputPort(name="data", accepted_types=[])
        assert port_accepts_type(port, Image) is True
