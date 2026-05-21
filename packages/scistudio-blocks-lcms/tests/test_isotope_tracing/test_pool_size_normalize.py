"""Tests for T-LCMS-012 PoolSizeNormalize."""

from __future__ import annotations

import pytest
from scistudio_blocks_lcms.isotope_tracing.pool_size_normalize import PoolSizeNormalize
from scistudio_blocks_lcms.types import PeakTable

from scistudio.blocks.base.config import BlockConfig


def _pd():
    return pytest.importorskip("pandas")


def _make_peak_table(frame) -> PeakTable:
    table = PeakTable(
        columns=list(frame.columns),
        row_count=len(frame),
        meta=PeakTable.Meta(source="ElMAVEN", polarity="+"),
    )
    table._data = frame
    return table


def test_internal_standard_normalization() -> None:
    pd = _pd()
    peak = _make_peak_table(
        pd.DataFrame(
            {
                "compound": ["IS", "glucose", "IS", "glucose"],
                "sample_id": ["S1", "S1", "S2", "S2"],
                "intensity": [10.0, 50.0, 20.0, 100.0],
            }
        )
    )
    result = PoolSizeNormalize().process_item(
        peak,
        BlockConfig(params={"method": "IS", "reference_compound": "IS"}),
    )
    out = result._data
    glucose = out.loc[out["compound"] == "glucose", "intensity"].tolist()
    assert glucose == pytest.approx([5.0, 5.0])


def test_tic_and_median_normalization() -> None:
    pd = _pd()
    peak = _make_peak_table(
        pd.DataFrame(
            {
                "compound": ["a", "b", "a", "b"],
                "sample_id": ["S1", "S1", "S2", "S2"],
                "intensity": [2.0, 6.0, 4.0, 12.0],
            }
        )
    )
    tic = PoolSizeNormalize().process_item(peak, BlockConfig(params={"method": "TIC"}))._data
    median = PoolSizeNormalize().process_item(peak, BlockConfig(params={"method": "median"}))._data
    assert tic.loc[(tic["compound"] == "a") & (tic["sample_id"] == "S1"), "intensity"].iloc[0] == pytest.approx(0.25)
    assert median.loc[(median["compound"] == "b") & (median["sample_id"] == "S2"), "intensity"].iloc[
        0
    ] == pytest.approx(12.0 / 8.0)


def test_is_requires_reference_compound_and_preserves_type_meta() -> None:
    pd = _pd()
    peak = _make_peak_table(pd.DataFrame({"compound": ["a"], "sample_id": ["S1"], "intensity": [1.0]}))
    with pytest.raises(ValueError, match="reference_compound"):
        PoolSizeNormalize().process_item(peak, BlockConfig(params={"method": "IS"}))
    with pytest.raises(ValueError, match="reference compound"):
        PoolSizeNormalize().process_item(peak, BlockConfig(params={"method": "IS", "reference_compound": "IS"}))

    result = PoolSizeNormalize().process_item(peak, BlockConfig(params={"method": "TIC"}))
    assert isinstance(result, PeakTable)
    assert result.meta == peak.meta
