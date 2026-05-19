from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from scieasy_blocks_lcms.io.load_sample_metadata import LoadSampleMetadata
from scieasy_blocks_lcms.types import SampleMetadata

from scieasy.blocks.base.config import BlockConfig


def _sample_metadata_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": ["S1", "S2"],
            "group": ["UL", "SE"],
            "time_hours": [0, 24],
        }
    )


def test_load_csv_sample_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sample_metadata.csv"
    _sample_metadata_df().to_csv(path, index=False)

    result = LoadSampleMetadata().load(BlockConfig(params={"path": str(path)}))
    assert isinstance(result[0], SampleMetadata)
    assert result[0].meta.sample_id_column == "sample_id"


def test_load_tsv_sample_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sample_metadata.tsv"
    _sample_metadata_df().to_csv(path, sep="\t", index=False)

    result = LoadSampleMetadata().load(BlockConfig(params={"path": str(path)}))
    assert result[0].columns == ["sample_id", "group", "time_hours"]


def test_custom_sample_id_column(tmp_path: Path) -> None:
    path = tmp_path / "sample_metadata.csv"
    df = _sample_metadata_df().rename(columns={"sample_id": "sample"})
    df.to_csv(path, index=False)

    result = LoadSampleMetadata().load(BlockConfig(params={"path": str(path), "sample_id_column": "sample"}))
    assert result[0].meta.sample_id_column == "sample"


def test_raises_on_missing_sample_id_column(tmp_path: Path) -> None:
    path = tmp_path / "sample_metadata.csv"
    pd.DataFrame({"group": ["UL"]}).to_csv(path, index=False)

    with pytest.raises(ValueError):
        LoadSampleMetadata().load(BlockConfig(params={"path": str(path)}))
