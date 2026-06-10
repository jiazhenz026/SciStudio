"""Tests for ProcessBlock — merge two DataFrames, split operations."""

from __future__ import annotations

from typing import ClassVar

import pyarrow as pa
import pytest

from scistudio.blocks.process.builtins.merge import MergeBlock
from scistudio.blocks.process.builtins.split import SplitBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame


def _make_df(data: dict) -> DataFrame:
    """Helper: create a DataFrame with an Arrow table attached."""
    table = pa.table(data)
    df = DataFrame(columns=table.column_names, row_count=table.num_rows)
    df._arrow_table = table  # type: ignore[attr-defined]
    return df


class TestMergeBlock:
    """MergeBlock — concatenation of two DataFrames."""

    def test_concat_two_tables(self) -> None:
        left = _make_df({"a": [1, 2], "b": [3, 4]})
        right = _make_df({"a": [5, 6], "b": [7, 8]})

        block = MergeBlock(config={"params": {"how": "concat"}})
        result = block.run({"left": left, "right": right}, block.config)

        merged_col = result["merged"]
        assert isinstance(merged_col, Collection)
        merged = merged_col[0]
        assert isinstance(merged, DataFrame)
        assert merged.row_count == 4
        assert merged.columns == ["a", "b"]

    def test_state_transitions(self) -> None:
        """A default-configured MergeBlock concatenates its two inputs (#1541).

        Previously this test ran the block and asserted nothing, so a reader
        grepping "state_transitions" saw green while the block contract was
        untested. Assert the real output contract.
        """
        left = _make_df({"x": [1]})
        right = _make_df({"x": [2]})

        block = MergeBlock()

        result = block.run({"left": left, "right": right}, block.config)

        merged_col = result["merged"]
        assert isinstance(merged_col, Collection)
        merged = merged_col[0]
        assert isinstance(merged, DataFrame)
        assert merged.row_count == 2
        assert merged.columns == ["x"]


class TestSplitBlock:
    """SplitBlock — head, ratio, filter modes."""

    def test_head_mode(self) -> None:
        data = _make_df({"val": list(range(10))})
        block = SplitBlock(config={"params": {"mode": "head", "n": 3}})
        result = block.run({"data": data}, block.config)

        out_col = result["out"]
        assert isinstance(out_col, Collection)
        assert out_col[0].row_count == 3

    def test_ratio_mode(self) -> None:
        data = _make_df({"val": list(range(10))})
        block = SplitBlock(config={"params": {"mode": "ratio", "ratio": 0.7}})
        result = block.run({"data": data}, block.config)

        assert result["out"][0].row_count == 7
        assert result["remainder"][0].row_count == 3

    def test_filter_mode(self) -> None:
        data = _make_df({"name": ["alice", "bob", "alice"], "score": [10, 20, 30]})
        block = SplitBlock(config={"params": {"mode": "filter", "column": "name", "value": "alice"}})
        result = block.run({"data": data}, block.config)

        out_col = result["out"]
        assert out_col[0].row_count == 2

    def test_unknown_mode_raises(self) -> None:
        data = _make_df({"x": [1]})
        block = SplitBlock(config={"params": {"mode": "unknown"}})
        with pytest.raises(ValueError, match="Unknown split mode"):
            block.run({"data": data}, block.config)


class TestMergeBlockCollection:
    """ADR-020: MergeBlock with Collection-wrapped inputs."""

    def test_concat_collection_inputs(self) -> None:
        """MergeBlock should unpack Collection inputs and pack output."""
        from scistudio.core.types.collection import Collection

        left = _make_df({"a": [1, 2], "b": [3, 4]})
        right = _make_df({"a": [5, 6], "b": [7, 8]})

        left_col = Collection([left], item_type=DataFrame)
        right_col = Collection([right], item_type=DataFrame)

        block = MergeBlock(config={"params": {"how": "concat"}})
        result = block.run({"left": left_col, "right": right_col}, block.config)

        merged_col = result["merged"]
        assert isinstance(merged_col, Collection)
        assert merged_col[0].row_count == 4

    def test_mixed_raw_and_collection(self) -> None:
        """MergeBlock should handle mix of raw and Collection inputs."""
        from scistudio.core.types.collection import Collection

        left = _make_df({"x": [1]})
        right_col = Collection([_make_df({"x": [2]})], item_type=DataFrame)

        block = MergeBlock(config={"params": {"how": "concat"}})
        result = block.run({"left": left, "right": right_col}, block.config)

        assert result["merged"][0].row_count == 2


class TestSplitBlockCollection:
    """ADR-020: SplitBlock with Collection-wrapped inputs."""

    def test_head_collection_input(self) -> None:
        from scistudio.core.types.collection import Collection

        data = _make_df({"val": list(range(10))})
        data_col = Collection([data], item_type=DataFrame)

        block = SplitBlock(config={"params": {"mode": "head", "n": 3}})
        result = block.run({"data": data_col}, block.config)

        out_col = result["out"]
        assert isinstance(out_col, Collection)
        assert out_col[0].row_count == 3

    def test_ratio_collection_input(self) -> None:
        from scistudio.core.types.collection import Collection

        data = _make_df({"val": list(range(10))})
        data_col = Collection([data], item_type=DataFrame)

        block = SplitBlock(config={"params": {"mode": "ratio", "ratio": 0.5}})
        result = block.run({"data": data_col}, block.config)

        assert result["out"][0].row_count == 5
        assert result["remainder"][0].row_count == 5


class TestProcessBlockOutputTypeInference:
    """Regression tests for #876 — ProcessBlock output Collection type inference.

    Before #876: ProcessBlock.run() pinned the output Collection's item_type
    to the input Collection's item_type. When process_item returned a parent
    type (valid by Liskov; valid by the bidirectional port-type check from
    #601), Collection.__init__'s strict isinstance check raised TypeError.

    After #876: output item_type is inferred from the actual results, so
    parent-typed outputs round-trip cleanly. Empty results still preserve
    the input type label so downstream port checks have a meaningful type.
    """

    def test_parent_type_output_accepted(self) -> None:
        """process_item returning a parent type must not raise TypeError."""
        from scistudio.blocks.base.ports import InputPort, OutputPort
        from scistudio.blocks.process.process_block import ProcessBlock
        from scistudio.core.types.base import DataObject
        from scistudio.core.types.collection import Collection

        class Parent(DataObject):
            pass

        class Child(Parent):
            pass

        class _DowncastBlock(ProcessBlock):
            type_name = "_test.downcast"
            input_ports: ClassVar = [InputPort(name="data", accepted_types=[Parent])]
            output_ports: ClassVar = [OutputPort(name="out", accepted_types=[Parent])]

            def process_item(self, item, config, state=None):  # type: ignore[no-untyped-def]
                # Return a parent-type instance from a child-type input.
                return Parent()

        block = _DowncastBlock()
        result = block.run({"data": Collection([Child(), Child()], item_type=Child)}, block.config)

        assert isinstance(result["out"], Collection)
        # item_type follows the actual results, not the input.
        assert result["out"].item_type is Parent
        assert result["out"].length == 2

    def test_empty_input_preserves_input_type(self) -> None:
        """Empty input Collection -> empty output Collection with same item_type label.

        Exercises the fallback branch: when results list is empty after
        iteration (because the input itself was empty), the output Collection
        carries primary.item_type so downstream port checks remain meaningful.
        """
        from scistudio.blocks.base.ports import InputPort, OutputPort
        from scistudio.blocks.process.process_block import ProcessBlock
        from scistudio.core.types.base import DataObject
        from scistudio.core.types.collection import Collection

        class Parent(DataObject):
            pass

        class Child(Parent):
            pass

        class _PassthroughBlock(ProcessBlock):
            type_name = "_test.passthrough"
            input_ports: ClassVar = [InputPort(name="data", accepted_types=[Parent])]
            output_ports: ClassVar = [OutputPort(name="out", accepted_types=[Parent])]

            def process_item(self, item, config, state=None):  # type: ignore[no-untyped-def]
                return item

        block = _PassthroughBlock()
        result = block.run({"data": Collection([], item_type=Child)}, block.config)

        assert isinstance(result["out"], Collection)
        assert result["out"].length == 0
        assert result["out"].item_type is Child  # input type preserved
