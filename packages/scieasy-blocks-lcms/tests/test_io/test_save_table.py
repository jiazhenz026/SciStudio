from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from scieasy_blocks_lcms.io.save_table import SaveTable
from scieasy_blocks_lcms.types import MIDTable, PeakTable, SampleMetadata

from scieasy.blocks.base.config import BlockConfig
from scieasy.core.types.collection import Collection
from scieasy.core.types.dataframe import DataFrame


def _wrap(df: pd.DataFrame, cls: type[DataFrame]) -> Collection:
    if cls is PeakTable:
        item = PeakTable(
            columns=list(df.columns),
            row_count=len(df),
            schema={col: str(dtype) for col, dtype in df.dtypes.items()},
            meta=PeakTable.Meta(source="ElMAVEN"),
        )
    elif cls is MIDTable:
        item = MIDTable(
            columns=list(df.columns),
            row_count=len(df),
            schema={col: str(dtype) for col, dtype in df.dtypes.items()},
            meta=MIDTable.Meta(sample_columns=["S1"]),
        )
    elif cls is SampleMetadata:
        item = SampleMetadata(
            columns=list(df.columns),
            row_count=len(df),
            schema={col: str(dtype) for col, dtype in df.dtypes.items()},
            meta=SampleMetadata.Meta(sample_id_column="sample_id"),
        )
    else:
        item = DataFrame(
            columns=list(df.columns),
            row_count=len(df),
            schema={col: str(dtype) for col, dtype in df.dtypes.items()},
        )
    item.user["pandas_df"] = df.copy()
    return Collection(items=[item], item_type=cls)


def test_save_peak_table_csv(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "peak.csv"
    table = _wrap(pd.DataFrame({"compound": ["glucose"], "intensity": [1.0]}), PeakTable)

    SaveTable().save(table, BlockConfig(params={"path": str(path), "format": "csv"}))
    assert path.exists()
    assert "compound" in path.read_text(encoding="utf-8")


def test_save_sample_metadata_tsv(tmp_path: Path) -> None:
    path = tmp_path / "sample.tsv"
    table = _wrap(pd.DataFrame({"sample_id": ["S1"], "group": ["UL"]}), SampleMetadata)

    SaveTable().save(table, BlockConfig(params={"path": str(path), "format": "tsv"}))
    assert "\t" in path.read_text(encoding="utf-8")


def test_save_mid_table_xlsx(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    path = tmp_path / "mid.xlsx"
    table = _wrap(pd.DataFrame({"Compound": ["glucose"], "C13": [0], "S1": [1.0]}), MIDTable)

    SaveTable().save(table, BlockConfig(params={"path": str(path), "format": "xlsx"}))
    assert path.exists()


def test_save_index_flag_respected(tmp_path: Path) -> None:
    path = tmp_path / "generic.csv"
    table = _wrap(pd.DataFrame({"value": [1.0, 2.0]}), DataFrame)

    SaveTable().save(table, BlockConfig(params={"path": str(path), "format": "csv", "index": True}))
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith(",")


def test_save_raises_on_unknown_format(tmp_path: Path) -> None:
    path = tmp_path / "generic.unknown"
    table = _wrap(pd.DataFrame({"value": [1.0]}), DataFrame)

    with pytest.raises(ValueError):
        SaveTable().save(table, BlockConfig(params={"path": str(path), "format": "unknown"}))
