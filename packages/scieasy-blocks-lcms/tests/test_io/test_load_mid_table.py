from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from scieasy_blocks_lcms.io.load_mid_table import LoadMIDTable
from scieasy_blocks_lcms.types import MIDTable

from scieasy.blocks.base.config import BlockConfig


def _mid_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Compound": ["glucose", "glucose", "glucose"],
            "C13": [0, 1, 2],
            "H2": [0, 0, 0],
            "UL0": [0.20, 0.05, 0.10],
            "UL3": [0.19, 0.06, 0.11],
            "UL2": [0.21, 0.05, 0.09],
            "UL1": [0.18, 0.07, 0.08],
            "SE3": [0.80, 0.04, 0.05],
        }
    )


def test_load_csv_long_format(tmp_path: Path) -> None:
    path = tmp_path / "mid.csv"
    _mid_df().to_csv(path, index=False)

    result = LoadMIDTable().load(BlockConfig(params={"path": str(path)}))
    assert isinstance(result[0], MIDTable)
    assert result[0].meta.tracer_atoms == ["C13"]
    assert result[0].meta.sample_columns == ["UL0", "UL3", "UL2", "UL1", "SE3"]
    assert result[0].meta.corrected is True


def test_load_xlsx_with_sheet_name(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    path = tmp_path / "mid.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"ignore": [1]}).to_excel(writer, sheet_name="ignore", index=False)
        _mid_df().to_excel(writer, sheet_name="mid_table", index=False)

    result = LoadMIDTable().load(BlockConfig(params={"path": str(path), "sheet_name": "mid_table"}))
    assert result[0].meta.sample_columns[0] == "UL0"


def test_multi_tracer_c13_h2(tmp_path: Path) -> None:
    path = tmp_path / "mid.csv"
    _mid_df().to_csv(path, index=False)

    result = LoadMIDTable().load(BlockConfig(params={"path": str(path), "tracer_atoms": ["C13", "H2"]}))
    assert result[0].meta.tracer_atoms == ["C13", "H2"]
    assert "H2" not in result[0].meta.sample_columns


def test_load_raises_on_missing_compound_column(tmp_path: Path) -> None:
    path = tmp_path / "mid.csv"
    pd.DataFrame({"C13": [0], "S1": [1.0]}).to_csv(path, index=False)

    with pytest.raises(ValueError):
        LoadMIDTable().load(BlockConfig(params={"path": str(path)}))
