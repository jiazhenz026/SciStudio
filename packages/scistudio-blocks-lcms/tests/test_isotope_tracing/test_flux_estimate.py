"""Tests for T-LCMS-011 FluxEstimate."""

from __future__ import annotations

import pytest
from scistudio_blocks_lcms.isotope_tracing.flux_estimate import FluxEstimate
from scistudio_blocks_lcms.types import MIDTable, PeakTable, SampleMetadata

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def _pd():
    return pytest.importorskip("pandas")


def _make_mid_table(frame, sample_columns: list[str]) -> MIDTable:
    table = MIDTable(
        columns=list(frame.columns),
        row_count=len(frame),
        meta=MIDTable.Meta(tracer_atoms=["C13"], sample_columns=sample_columns),
    )
    table._data = frame
    return table


def _make_sample_metadata(frame) -> SampleMetadata:
    table = SampleMetadata(
        columns=list(frame.columns),
        row_count=len(frame),
        meta=SampleMetadata.Meta(sample_id_column="sample_id"),
    )
    table._data = frame
    return table


def _make_peak_table(frame) -> PeakTable:
    table = PeakTable(
        columns=list(frame.columns),
        row_count=len(frame),
        meta=PeakTable.Meta(source="ElMAVEN", polarity="+"),
    )
    table._data = frame
    return table


def test_flux_without_pool_size_uses_unit_pool_size() -> None:
    pd = _pd()
    mid = _make_mid_table(
        pd.DataFrame(
            {
                "Compound": ["glucose", "glucose"],
                "C13": [0, 1],
                "S0": [1.0, 0.0],
                "S1": [0.5, 0.5],
                "S2": [0.0, 1.0],
            }
        ),
        ["S0", "S1", "S2"],
    )
    meta = _make_sample_metadata(pd.DataFrame({"sample_id": ["S0", "S1", "S2"], "time_hours": [0.0, 1.0, 2.0]}))
    result = FluxEstimate().run(
        {
            "mid_table": Collection(items=[mid], item_type=MIDTable),
            "sample_metadata": Collection(items=[meta], item_type=SampleMetadata),
        },
        BlockConfig(params={"time_points_column": "time_hours"}),
    )
    out = result["flux"][0]._data
    assert out.loc[0, "labeling_rate"] == pytest.approx(0.5)
    assert out.loc[0, "pool_size"] == pytest.approx(1.0)
    assert out.loc[0, "estimated_flux"] == pytest.approx(0.5)
    # linregress output columns
    assert "intercept" in out.columns
    assert "r_squared" in out.columns
    assert "p_value" in out.columns
    assert "stderr" in out.columns
    assert out.loc[0, "r_squared"] == pytest.approx(1.0)


def test_flux_with_pool_size_table() -> None:
    pd = _pd()
    mid = _make_mid_table(
        pd.DataFrame(
            {
                "Compound": ["glucose", "glucose"],
                "C13": [0, 1],
                "S0": [1.0, 0.0],
                "S1": [0.5, 0.5],
                "S2": [0.0, 1.0],
            }
        ),
        ["S0", "S1", "S2"],
    )
    meta = _make_sample_metadata(pd.DataFrame({"sample_id": ["S0", "S1", "S2"], "time_hours": [0.0, 1.0, 2.0]}))
    peak = _make_peak_table(
        pd.DataFrame(
            {
                "compound": ["glucose", "glucose", "glucose"],
                "sample_id": ["S0", "S1", "S2"],
                "intensity": [10.0, 20.0, 30.0],
            }
        )
    )
    result = FluxEstimate().run(
        {
            "mid_table": Collection(items=[mid], item_type=MIDTable),
            "sample_metadata": Collection(items=[meta], item_type=SampleMetadata),
            "pool_size_table": Collection(items=[peak], item_type=PeakTable),
        },
        BlockConfig(params={"time_points_column": "time_hours"}),
    )
    out = result["flux"][0]._data
    assert out.loc[0, "pool_size"] == pytest.approx(20.0)
    assert out.loc[0, "estimated_flux"] == pytest.approx(10.0)


def test_missing_time_column_raises() -> None:
    pd = _pd()
    mid = _make_mid_table(pd.DataFrame({"Compound": ["g"], "C13": [0], "S0": [1.0]}), ["S0"])
    meta = _make_sample_metadata(pd.DataFrame({"sample_id": ["S0"]}))
    with pytest.raises(ValueError, match="time column"):
        FluxEstimate().run(
            {
                "mid_table": Collection(items=[mid], item_type=MIDTable),
                "sample_metadata": Collection(items=[meta], item_type=SampleMetadata),
            },
            BlockConfig(params={"time_points_column": "time_hours"}),
        )


def test_requires_two_distinct_timepoints() -> None:
    pd = _pd()
    mid = _make_mid_table(
        pd.DataFrame({"Compound": ["g", "g"], "C13": [0, 1], "S0": [1.0, 0.0], "S1": [0.5, 0.5]}),
        ["S0", "S1"],
    )
    meta = _make_sample_metadata(pd.DataFrame({"sample_id": ["S0", "S1"], "time_hours": [0.0, 0.0]}))
    with pytest.raises(ValueError, match="two distinct timepoints"):
        FluxEstimate().run(
            {
                "mid_table": Collection(items=[mid], item_type=MIDTable),
                "sample_metadata": Collection(items=[meta], item_type=SampleMetadata),
            },
            BlockConfig(params={"time_points_column": "time_hours"}),
        )


def test_docstring_mentions_not_a_replacement() -> None:
    assert "NOT a replacement for full 13C-MFA" in FluxEstimate.__doc__
