"""Integration tests for FilterCollection expression mode (T-TRK-012)."""

from __future__ import annotations

from typing import Any

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.blocks.process.builtins.filter_collection import FilterCollection
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection


class Image(Array):
    """Local 2D Array stand-in (mirrors tests/blocks/test_collection_blocks.py)."""

    def __init__(
        self,
        *,
        shape: tuple[int, ...] | None = None,
        ndim: int | None = None,
        dtype: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(axes=["y", "x"], shape=shape, dtype=dtype, **kwargs)


def _make_images(n: int) -> list[Image]:
    return [
        Image(
            shape=(i, i),
            ndim=2,
            dtype="uint8",
            user={"index": i, "tag": "even" if i % 2 == 0 else "odd"},
        )
        for i in range(1, n + 1)
    ]


def _run(block: FilterCollection, col: Collection) -> Collection:
    block.transition(BlockState.READY)
    return block.run({"input": col}, block.config)["output"]


class TestFilterCollectionExpression:
    def test_filter_by_index(self) -> None:
        col = Collection(_make_images(6), item_type=Image)
        block = FilterCollection(config={"params": {"expression": "index < 3"}})
        result = _run(block, col)
        assert len(result) == 3
        assert result.item_type is Image

    def test_filter_by_user_key(self) -> None:
        col = Collection(_make_images(5), item_type=Image)
        block = FilterCollection(config={"params": {"expression": "user['index'] == 3"}})
        result = _run(block, col)
        assert len(result) == 1
        assert result[0].user["index"] == 3

    def test_filter_by_in_list(self) -> None:
        col = Collection(_make_images(5), item_type=Image)
        block = FilterCollection(config={"params": {"expression": "user['tag'] in ['even']"}})
        result = _run(block, col)
        assert all(item.user["tag"] == "even" for item in result)
        assert len(result) == 2

    def test_filter_combined_boolean(self) -> None:
        col = Collection(_make_images(6), item_type=Image)
        block = FilterCollection(config={"params": {"expression": "user['tag'] == 'odd' and index >= 2"}})
        result = _run(block, col)
        # Odd-tagged items have user['index'] in {1, 3, 5}. Positional
        # index >= 2 means the 3rd, 4th, 5th, 6th items (indices 2..5).
        assert [item.user["index"] for item in result] == [3, 5]

    def test_filter_len_whitelisted(self) -> None:
        images = [
            Image(shape=(1, 1), ndim=2, dtype="uint8", user={"tags": ["a"]}),
            Image(shape=(2, 2), ndim=2, dtype="uint8", user={"tags": ["a", "b"]}),
            Image(shape=(3, 3), ndim=2, dtype="uint8", user={"tags": []}),
        ]
        col = Collection(images, item_type=Image)
        block = FilterCollection(config={"params": {"expression": "len(user['tags']) >= 1"}})
        result = _run(block, col)
        assert len(result) == 2

    def test_framework_slot_available(self) -> None:
        col = Collection(_make_images(2), item_type=Image)
        # ``framework`` is a FrameworkMeta instance with an ``id`` str.
        # Smoke test: accessing it via the expression must not crash.
        block = FilterCollection(config={"params": {"expression": "len(framework.object_id) > 0"}})
        result = _run(block, col)
        assert len(result) == 2

    def test_empty_collection_passes_through(self) -> None:
        col = Collection([], item_type=Image)
        block = FilterCollection(config={"params": {"expression": "index < 10"}})
        result = _run(block, col)
        assert isinstance(result, Collection)
        assert len(result) == 0
        assert result.item_type is Image

    def test_rejects_forbidden_expression_at_run(self) -> None:
        col = Collection(_make_images(2), item_type=Image)
        block = FilterCollection(config={"params": {"expression": "__import__('os')"}})
        block.transition(BlockState.READY)
        with pytest.raises(ValueError, match="forbidden construct"):
            block.run({"input": col}, block.config)

    def test_rejects_arbitrary_call(self) -> None:
        col = Collection(_make_images(2), item_type=Image)
        block = FilterCollection(config={"params": {"expression": "print('x')"}})
        block.transition(BlockState.READY)
        with pytest.raises(ValueError, match="forbidden construct"):
            block.run({"input": col}, block.config)

    def test_expression_and_predicate_key_mutually_exclusive(self) -> None:
        col = Collection(_make_images(2), item_type=Image)
        block = FilterCollection(
            config={
                "params": {
                    "expression": "index < 1",
                    "predicate_key": "index",
                    "predicate_value": 1,
                }
            }
        )
        block.transition(BlockState.READY)
        with pytest.raises(ValueError, match="not both"):
            block.run({"input": col}, block.config)

    def test_expression_must_be_string(self) -> None:
        col = Collection(_make_images(2), item_type=Image)
        block = FilterCollection(config={"params": {"expression": 123}})
        block.transition(BlockState.READY)
        with pytest.raises(ValueError, match="must be a str"):
            block.run({"input": col}, block.config)

    def test_legacy_predicate_key_still_works(self) -> None:
        col = Collection(_make_images(3), item_type=Image)
        block = FilterCollection(config={"params": {"predicate_key": "index", "predicate_value": 2}})
        result = _run(block, col)
        assert len(result) == 1
        assert result[0].user["index"] == 2
