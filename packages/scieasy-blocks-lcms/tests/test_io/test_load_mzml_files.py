from __future__ import annotations

from pathlib import Path

import pytest
from scieasy_blocks_lcms.io.load_mzml_files import LoadMzMLFiles
from scieasy_blocks_lcms.types import MSRawFile

from scieasy.blocks.base.config import BlockConfig
from scieasy.core.types.collection import Collection


def _write_mzml(path: Path, *, positive: bool = True) -> None:
    polarity_accession = "MS:1000130" if positive else "MS:1000129"
    path.write_text(
        f"""
<mzML>
  <run startTimeStamp="2026-04-08T01:02:03Z">
    <instrumentConfiguration id="IC1" name="Q Exactive HF" />
    <cvParam accession="{polarity_accession}" />
  </run>
</mzML>
""".strip(),
        encoding="utf-8",
    )


def test_load_single_mzml_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.mzML"
    _write_mzml(path)

    result = LoadMzMLFiles().load(BlockConfig(params={"path": str(path)}))
    assert isinstance(result, Collection)
    assert len(result) == 1
    item = result[0]
    assert isinstance(item, MSRawFile)
    assert item.meta.format == "mzML"
    assert item.meta.polarity == "+"
    assert item.meta.instrument == "Q Exactive HF"
    assert item.meta.sample_id == "sample"


def test_load_multiple_mzml_files(tmp_path: Path) -> None:
    path_a = tmp_path / "a.mzML"
    path_b = tmp_path / "b.mzML"
    _write_mzml(path_a, positive=True)
    _write_mzml(path_b, positive=False)

    result = LoadMzMLFiles().load(BlockConfig(params={"path": [str(path_a), str(path_b)]}))
    assert isinstance(result, Collection)
    assert len(result) == 2
    assert result[0].meta.polarity == "+"
    assert result[1].meta.polarity == "-"


def test_load_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        LoadMzMLFiles().load(BlockConfig(params={"path": str(tmp_path / "missing.mzML")}))


def test_load_raw_file_records_path_only(tmp_path: Path) -> None:
    raw_path = tmp_path / "sample.raw"
    raw_path.write_bytes(b"RAW")

    result = LoadMzMLFiles().load(BlockConfig(params={"path": str(raw_path)}))
    assert result[0].file_path == raw_path
    assert result[0].meta.format == "raw"
    assert result[0].meta.instrument is None


def test_load_d_folder_records_path_only(tmp_path: Path) -> None:
    d_path = tmp_path / "sample.d"
    d_path.mkdir()

    result = LoadMzMLFiles().load(BlockConfig(params={"path": str(d_path)}))
    assert result[0].file_path == d_path
    assert result[0].meta.format == "d"


def test_load_invalid_path_raises_value_error() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        LoadMzMLFiles().load(BlockConfig(params={"path": ""}))


def test_config_schema_uses_file_browser() -> None:
    schema = LoadMzMLFiles.config_schema
    path_prop = schema["properties"]["path"]
    assert path_prop["ui_widget"] == "file_browser"
    assert path_prop["type"] == ["string", "array"]
    assert path_prop["items"] == {"type": "string"}
