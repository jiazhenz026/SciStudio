"""Tests for the MergeCollection block (ADR-021 / ADR-029).

The former collection filter/slice/split blocks were retired in favour of the
interactive DataRouter (#1781); MergeCollection remains as the variadic merge
primitive and lives in the ``routing`` subcategory.
"""

from __future__ import annotations

from typing import Any

import pytest

from scistudio.blocks.process.builtins.merge_collection import MergeCollection
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame

# ---------------------------------------------------------------------------
# Local test fixture.
#
# ADR-027 D2: core no longer ships ``Image``; this test uses a tiny
# Array subclass as a stand-in so Collection[Image] still has a distinct
# item_type to check against the block contracts.
# ---------------------------------------------------------------------------


class Image(Array):
    """Local 2D Array test fixture."""

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
    """Create *n* Image objects with distinct shapes and user metadata."""
    return [Image(shape=(i, i), ndim=2, dtype="uint8", user={"index": i}) for i in range(1, n + 1)]


def _variadic_config(n_ports: int) -> dict[str, Any]:
    """Config declaring *n_ports* variadic input ports named ``input_1..N``."""
    return {"input_ports": [{"name": f"input_{i}", "types": ["DataObject"]} for i in range(1, n_ports + 1)]}


class TestMergeCollectionMetadata:
    """Class-level contract: variadic input side, routing subcategory."""

    def test_subcategory_is_routing(self) -> None:
        assert MergeCollection.subcategory == "routing"

    def test_variadic_inputs(self) -> None:
        assert MergeCollection.variadic_inputs is True
        assert MergeCollection.min_input_ports == 2
        assert MergeCollection.max_input_ports == 8

    def test_single_output_port(self) -> None:
        assert [p.name for p in MergeCollection.output_ports] == ["output"]


class TestMergeCollectionRun:
    """MergeCollection — concatenate N same-typed Collections."""

    def test_merge_two_collections(self) -> None:
        col_a = Collection(_make_images(2), item_type=Image)
        col_b = Collection(_make_images(3), item_type=Image)

        block = MergeCollection()
        result = block.run({"input_1": col_a, "input_2": col_b}, block.config)

        merged = result["output"]
        assert isinstance(merged, Collection)
        assert len(merged) == 5
        assert merged.item_type is Image

    def test_merge_many_collections_in_port_order(self) -> None:
        col_1 = Collection(_make_images(1), item_type=Image)  # index 1
        col_2 = Collection(_make_images(2), item_type=Image)  # index 1,2
        col_3 = Collection(_make_images(3), item_type=Image)  # index 1,2,3

        block = MergeCollection(config=_variadic_config(3))
        result = block.run({"input_1": col_1, "input_2": col_2, "input_3": col_3}, block.config)

        merged = result["output"]
        assert len(merged) == 6
        # Concatenated in input-port order (col_1, then col_2, then col_3).
        assert [item.user["index"] for item in merged] == [1, 1, 2, 1, 2, 3]

    def test_type_mismatch_in_any_input_raises(self) -> None:
        """If any one input's item_type differs from the rest, error."""
        col_1 = Collection(_make_images(2), item_type=Image)
        col_2 = Collection(
            [DataFrame(columns=["a"]), DataFrame(columns=["b"])],
            item_type=DataFrame,
        )
        col_3 = Collection(_make_images(1), item_type=Image)

        block = MergeCollection(config=_variadic_config(3))
        with pytest.raises(TypeError, match="different item types"):
            block.run({"input_1": col_1, "input_2": col_2, "input_3": col_3}, block.config)

    def test_non_collection_input_raises(self) -> None:
        block = MergeCollection()
        with pytest.raises(TypeError, match="requires Collection inputs"):
            block.run({"input_1": "not_a_collection", "input_2": "neither"}, block.config)

    def test_no_inputs_raises(self) -> None:
        block = MergeCollection()
        with pytest.raises(ValueError, match="at least one connected input"):
            block.run({}, block.config)
