"""Tests for LazyList and CodeBlock auto-unpack/repack — ADR-020-Add4."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scistudio.blocks.code.lazy_list import _ITEM_COUNT_WARNING_THRESHOLD, LazyList
from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


def _make_item(label: str) -> DataObject:
    """Create a DataObject whose to_memory() returns *label*.

    #1725: data access is ``item.to_memory()`` directly — ADR-031 removed
    ``ViewProxy`` / ``DataObject.view()``, so there is no ``view()`` indirection.
    """
    obj = DataObject()
    obj.to_memory = MagicMock(return_value=label)  # type: ignore[method-assign]
    return obj


def _make_collection(n: int) -> Collection:
    """Create a Collection of *n* mock DataObjects."""
    items = [_make_item(f"item-{i}") for i in range(n)]
    return Collection(items)


# -- LazyList construction -----------------------------------------------------


class TestLazyListInit:
    def test_stores_collection_reference(self) -> None:
        """LazyList stores the Collection without loading items."""
        coll = _make_collection(3)
        ll = LazyList(coll)
        # No to_memory() calls during construction — items not loaded.
        for item in coll:
            item.to_memory.assert_not_called()
        assert len(ll) == 3

    def test_repr(self) -> None:
        """LazyList repr shows length."""
        coll = _make_collection(5)
        ll = LazyList(coll)
        assert "LazyList(length=5)" in repr(ll)


# -- LazyList __len__ ----------------------------------------------------------


class TestLazyListLen:
    def test_len_returns_count_without_loading(self) -> None:
        """len(lazy_list) returns the count without materialising any items."""
        coll = _make_collection(4)
        ll = LazyList(coll)
        assert len(ll) == 4
        # Verify no data was loaded.
        for item in coll:
            item.to_memory.assert_not_called()

    def test_len_empty_collection(self) -> None:
        """len(lazy_list) returns 0 for an empty Collection."""
        coll = Collection([], item_type=DataObject)
        ll = LazyList(coll)
        assert len(ll) == 0


# -- LazyList __iter__ ---------------------------------------------------------


class TestLazyListIter:
    def test_iter_yields_all_items(self) -> None:
        """Iteration yields materialised items in order."""
        coll = _make_collection(3)
        ll = LazyList(coll)
        results = list(ll)
        assert results == ["item-0", "item-1", "item-2"]

    def test_iter_loads_items_lazily(self) -> None:
        """Iteration calls to_memory() for each item."""
        coll = _make_collection(3)
        ll = LazyList(coll)
        items_list = list(coll)

        iterator = iter(ll)
        # Before iterating, nothing loaded.
        for item in items_list:
            item.to_memory.assert_not_called()

        # After yielding first item, only first is loaded.
        first = next(iterator)
        assert first == "item-0"
        items_list[0].to_memory.assert_called_once()
        items_list[1].to_memory.assert_not_called()

        # After yielding second, second is loaded.
        second = next(iterator)
        assert second == "item-1"
        items_list[1].to_memory.assert_called_once()
        items_list[2].to_memory.assert_not_called()

    def test_iter_empty(self) -> None:
        """Iteration over empty LazyList yields nothing."""
        coll = Collection([], item_type=DataObject)
        ll = LazyList(coll)
        assert list(ll) == []


# -- LazyList __getitem__ ------------------------------------------------------


class TestLazyListGetItem:
    def test_int_index(self) -> None:
        """Integer index loads only the requested item."""
        coll = _make_collection(3)
        ll = LazyList(coll)
        items_list = list(coll)

        result = ll[1]
        assert result == "item-1"
        # Only item 1 was loaded.
        items_list[0].to_memory.assert_not_called()
        items_list[1].to_memory.assert_called_once()
        items_list[2].to_memory.assert_not_called()

    def test_negative_index(self) -> None:
        """Negative index loads the correct item."""
        coll = _make_collection(3)
        ll = LazyList(coll)
        result = ll[-1]
        assert result == "item-2"

    def test_index_out_of_range(self) -> None:
        """Out-of-range index raises IndexError."""
        coll = _make_collection(2)
        ll = LazyList(coll)
        with pytest.raises(IndexError, match="out of range"):
            ll[5]

    def test_negative_index_out_of_range(self) -> None:
        """Out-of-range negative index raises IndexError."""
        coll = _make_collection(2)
        ll = LazyList(coll)
        with pytest.raises(IndexError, match="out of range"):
            ll[-5]

    def test_slice_returns_list(self) -> None:
        """Slice returns a plain list of materialised items."""
        coll = _make_collection(5)
        ll = LazyList(coll)
        result = ll[1:4]
        assert isinstance(result, list)
        assert result == ["item-1", "item-2", "item-3"]

    def test_slice_step(self) -> None:
        """Slice with step returns correct items."""
        coll = _make_collection(6)
        ll = LazyList(coll)
        result = ll[0:6:2]
        assert result == ["item-0", "item-2", "item-4"]

    def test_empty_slice(self) -> None:
        """Empty slice returns empty list."""
        coll = _make_collection(3)
        ll = LazyList(coll)
        result = ll[5:10]
        assert result == []


# -- LazyList to_list ----------------------------------------------------------


class TestLazyListToList:
    def test_to_list_returns_all(self) -> None:
        """to_list() materialises all items into a plain list."""
        coll = _make_collection(3)
        ll = LazyList(coll)
        result = ll.to_list()
        assert result == ["item-0", "item-1", "item-2"]
        assert isinstance(result, list)

    def test_to_list_warns_for_large_collection(self) -> None:
        """to_list() emits ResourceWarning for large collections."""
        n = _ITEM_COUNT_WARNING_THRESHOLD + 1
        coll = _make_collection(n)
        ll = LazyList(coll)
        with pytest.warns(ResourceWarning, match="loading.*items into memory"):
            ll.to_list()

    def test_to_list_no_warning_for_small_collection(self) -> None:
        """to_list() does NOT warn for collections below the threshold."""
        coll = _make_collection(3)
        ll = LazyList(coll)
        # If a ResourceWarning were emitted, this would NOT raise.
        # We verify no warnings by checking no ResourceWarning is raised.
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error", ResourceWarning)
            result = ll.to_list()
        assert len(result) == 3

    def test_to_list_empty(self) -> None:
        """to_list() on empty LazyList returns empty list."""
        coll = Collection([], item_type=DataObject)
        ll = LazyList(coll)
        assert ll.to_list() == []


# -- CodeBlock auto-unpack/repack ----------------------------------------------


class TestCodeBlockUnpackInputs:
    def test_single_item_collection_unwraps(self) -> None:
        """Collection with length=1 is unpacked to a single native object."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        coll = _make_collection(1)
        result = block._unpack_inputs({"data": coll})
        assert result["data"] == "item-0"

    def test_multi_item_collection_becomes_lazy_list(self) -> None:
        """Collection with length>1 is wrapped in a LazyList."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        coll = _make_collection(3)
        result = block._unpack_inputs({"data": coll})
        assert isinstance(result["data"], LazyList)
        assert len(result["data"]) == 3

    def test_non_collection_passthrough(self) -> None:
        """Non-Collection values pass through unchanged."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        result = block._unpack_inputs({"threshold": 0.5, "name": "test"})
        assert result == {"threshold": 0.5, "name": "test"}

    def test_mixed_inputs(self) -> None:
        """Mix of Collection and non-Collection inputs."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        coll = _make_collection(2)
        result = block._unpack_inputs({"data": coll, "threshold": 0.5})
        assert isinstance(result["data"], LazyList)
        assert result["threshold"] == 0.5

    def test_empty_inputs(self) -> None:
        """Empty inputs dict passes through."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        result = block._unpack_inputs({})
        assert result == {}


class TestCodeBlockRepackOutputs:
    def test_single_dataobject_wrapped(self) -> None:
        """Single DataObject output is wrapped in a length-1 Collection."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        obj = Array(axes=["y", "x"], shape=(10, 10), dtype="uint8")
        result = block._repack_outputs({"result": obj})
        assert isinstance(result["result"], Collection)
        assert len(result["result"]) == 1
        assert result["result"][0] is obj

    def test_list_of_dataobjects_wrapped(self) -> None:
        """List of DataObjects is wrapped in a Collection."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        objs = [Array(axes=["y", "x"], shape=(i, i), dtype="uint8") for i in range(1, 4)]
        result = block._repack_outputs({"result": objs})
        assert isinstance(result["result"], Collection)
        assert len(result["result"]) == 3

    def test_non_dataobject_passthrough(self) -> None:
        """Non-DataObject values pass through unchanged."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        result = block._repack_outputs({"count": 42, "name": "test"})
        assert result == {"count": 42, "name": "test"}

    def test_empty_list_passthrough(self) -> None:
        """Empty list passes through (cannot infer item_type)."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        result = block._repack_outputs({"result": []})
        assert result["result"] == []

    def test_mixed_outputs(self) -> None:
        """Mix of DataObject and non-DataObject outputs."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock()
        obj = Array(axes=["y", "x"], shape=(10, 10), dtype="uint8")
        result = block._repack_outputs({"result": obj, "status": "ok"})
        assert isinstance(result["result"], Collection)
        assert result["status"] == "ok"


class TestCodeBlockRunIntegration:
    """CodeBlock.run() is now implemented — verify it dispatches to runners."""

    def test_run_inline_python(self) -> None:
        """run() rejects inline Python instead of silently treating it as v2."""
        from scistudio.blocks.code.code_block import CodeBlock, CodeBlockMigrationError

        block = CodeBlock(config={"params": {"script": "result = 42"}})
        with pytest.raises(CodeBlockMigrationError, match="Inline CodeBlock configs"):
            block.run({}, block.config)

    def test_run_inline_with_inputs(self) -> None:
        """run() rejects inline scripts even when legacy inputs are supplied."""
        from scistudio.blocks.code.code_block import CodeBlock, CodeBlockMigrationError

        block = CodeBlock(config={"params": {"script": "output = data * 2"}})
        with pytest.raises(CodeBlockMigrationError, match="Inline CodeBlock configs"):
            block.run({"data": 10}, block.config)

    def test_run_missing_script_raises(self) -> None:
        """run() with no script raises ValueError."""
        from scistudio.blocks.code.code_block import CodeBlock

        block = CodeBlock(config={"params": {}})
        with pytest.raises(ValueError, match="script"):
            block.run({}, block.config)
