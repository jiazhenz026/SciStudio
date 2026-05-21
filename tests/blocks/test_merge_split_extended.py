"""Extended tests for MergeBlock and SplitBlock — error paths and edge cases."""

from __future__ import annotations

import pyarrow as pa
import pytest

from scistudio.blocks.process.builtins.merge import MergeBlock
from scistudio.blocks.process.builtins.split import SplitBlock
from scistudio.core.types.dataframe import DataFrame


def _make_df(data: dict) -> DataFrame:
    """Helper to create a DataFrame with an Arrow table attached."""
    table = pa.table(data)
    df = DataFrame(columns=table.column_names, row_count=table.num_rows)
    df._arrow_table = table  # type: ignore[attr-defined]
    return df


class TestMergeBlockExtended:
    """MergeBlock — error paths and defaults."""

    def test_unsupported_join_raises(self) -> None:
        block = MergeBlock(config={"params": {"how": "inner"}})
        left = _make_df({"a": [1, 2]})
        right = _make_df({"a": [3, 4]})
        with pytest.raises(NotImplementedError, match="inner"):
            block.run({"left": left, "right": right}, block.config)

    def test_default_how_is_concat(self) -> None:
        block = MergeBlock()
        left = _make_df({"a": [1, 2]})
        right = _make_df({"a": [3, 4]})
        result = block.run({"left": left, "right": right}, block.config)
        assert result["merged"][0].row_count == 4

    def test_error_state_on_failure(self) -> None:
        block = MergeBlock(config={"params": {"how": "outer"}})
        left = _make_df({"a": [1]})
        right = _make_df({"a": [2]})
        with pytest.raises(NotImplementedError):
            block.run({"left": left, "right": right}, block.config)


class TestSplitBlockExtended:
    """SplitBlock — error paths and defaults."""

    def test_filter_missing_column_raises(self) -> None:
        block = SplitBlock(config={"params": {"mode": "filter", "value": "x"}})
        df = _make_df({"a": [1, 2, 3]})
        with pytest.raises((ValueError, KeyError)):
            block.run({"data": df}, block.config)

    def test_filter_missing_value_raises(self) -> None:
        block = SplitBlock(config={"params": {"mode": "filter", "column": "a"}})
        df = _make_df({"a": [1, 2, 3]})
        with pytest.raises((ValueError, KeyError)):
            block.run({"data": df}, block.config)

    def test_head_default_n(self) -> None:
        block = SplitBlock(config={"params": {"mode": "head"}})
        df = _make_df({"a": list(range(200))})
        result = block.run({"data": df}, block.config)
        assert result["out"][0].row_count == 100  # default n=100

    def test_ratio_default(self) -> None:
        block = SplitBlock(config={"params": {"mode": "ratio"}})
        df = _make_df({"a": list(range(100))})
        result = block.run({"data": df}, block.config)
        assert result["out"][0].row_count == 80  # default ratio=0.8
