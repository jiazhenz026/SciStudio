from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from scieasy_blocks_lcms.io.load_peak_table import LoadPeakTable
from scieasy_blocks_lcms.types import PeakTable

from scieasy.blocks.base.config import BlockConfig
from scieasy.core.types.collection import Collection


def _elmaven_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "compound": ["glucose", "lactate"],
            "formula": ["C6H12O6", "C3H6O3"],
            "medMz": [179.0561, 89.0244],
            "medRt": [5.2, 3.1],
        }
    )


def test_load_csv_elmaven(tmp_path: Path) -> None:
    path = tmp_path / "peaks.csv"
    _elmaven_df().to_csv(path, index=False)

    result = LoadPeakTable().load(BlockConfig(params={"path": str(path)}))
    assert isinstance(result, Collection)
    assert isinstance(result[0], PeakTable)
    assert result[0].meta.source == "ElMAVEN"
    assert result[0].row_count == 2


def test_load_tsv_elmaven(tmp_path: Path) -> None:
    path = tmp_path / "peaks.tsv"
    _elmaven_df().to_csv(path, sep="\t", index=False)

    result = LoadPeakTable().load(BlockConfig(params={"path": str(path)}))
    assert result[0].columns == ["compound", "formula", "medMz", "medRt"]


def test_load_xlsx_named_sheet(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    path = tmp_path / "peaks.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"ignore": [1]}).to_excel(writer, sheet_name="ignore", index=False)
        _elmaven_df().to_excel(writer, sheet_name="peak_table", index=False)

    result = LoadPeakTable().load(BlockConfig(params={"path": str(path), "sheet_name": "peak_table"}))
    assert result[0].meta.source == "ElMAVEN"


def test_source_auto_detects_mzmine_and_xcms(tmp_path: Path) -> None:
    mzmine_path = tmp_path / "mzmine.csv"
    pd.DataFrame({"row ID": [1], "row m/z": [100.0], "row retention time": [5.0]}).to_csv(mzmine_path, index=False)
    xcms_path = tmp_path / "xcms.csv"
    pd.DataFrame({"mzmed": [100.0], "rtmed": [5.0], "mzmin": [99.5], "mzmax": [100.5]}).to_csv(xcms_path, index=False)

    assert LoadPeakTable().load(BlockConfig(params={"path": str(mzmine_path)}))[0].meta.source == "MZmine"
    assert LoadPeakTable().load(BlockConfig(params={"path": str(xcms_path)}))[0].meta.source == "XCMS"


def test_load_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LoadPeakTable().load(BlockConfig(params={"path": str(tmp_path / "missing.csv")}))


def test_load_raises_on_empty_table(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    pd.DataFrame(columns=["compound", "medMz"]).to_csv(path, index=False)

    with pytest.raises(ValueError):
        LoadPeakTable().load(BlockConfig(params={"path": str(path)}))


def test_output_meta_polarity_optional(tmp_path: Path) -> None:
    path = tmp_path / "peaks.csv"
    _elmaven_df().to_csv(path, index=False)

    result = LoadPeakTable().load(BlockConfig(params={"path": str(path), "polarity": "-"}))
    assert result[0].meta.polarity == "-"
