"""Verify LCMS loader blocks use file_browser with multi-file path schema.

Regression test for issue #525: all LCMS load blocks should use
``ui_widget: file_browser`` with ``type: ["string", "array"]`` path
config, matching the LoadImage pattern.
"""

from __future__ import annotations

import pytest

try:
    from scistudio_blocks_lcms.io.load_mid_table import LoadMIDTable
    from scistudio_blocks_lcms.io.load_mzml_files import LoadMzMLFiles
    from scistudio_blocks_lcms.io.load_peak_table import LoadPeakTable
    from scistudio_blocks_lcms.io.load_sample_metadata import LoadSampleMetadata
    from scistudio_blocks_lcms.io.save_table import SaveTable

    HAS_LCMS = True
except ImportError:
    HAS_LCMS = False

pytestmark = pytest.mark.skipif(not HAS_LCMS, reason="scistudio_blocks_lcms not installed")


@pytest.mark.parametrize(
    "block_cls",
    [
        pytest.param("LoadMzMLFiles", id="LoadMzMLFiles"),
        pytest.param("LoadPeakTable", id="LoadPeakTable"),
        pytest.param("LoadMIDTable", id="LoadMIDTable"),
        pytest.param("LoadSampleMetadata", id="LoadSampleMetadata"),
    ],
)
def test_path_config_uses_file_browser(block_cls: str) -> None:
    cls_map = {
        "LoadMzMLFiles": LoadMzMLFiles,
        "LoadPeakTable": LoadPeakTable,
        "LoadMIDTable": LoadMIDTable,
        "LoadSampleMetadata": LoadSampleMetadata,
    }
    cls = cls_map[block_cls]
    path_prop = cls.config_schema["properties"]["path"]
    assert path_prop["ui_widget"] == "file_browser", f"{block_cls} should use file_browser"
    assert path_prop["type"] == ["string", "array"], f"{block_cls} should accept string or array"
    assert path_prop["items"] == {"type": "string"}, f"{block_cls} items should be string"


# ---------------------------------------------------------------------------
# #1076: LCMS loaders/savers declare supported_extensions per ADR-028 §D8.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block_cls,expected",
    [
        pytest.param(
            "LoadMzMLFiles",
            {".mzml": "mzML", ".mzxml": "mzXML", ".raw": "raw", ".d": "d"},
            id="LoadMzMLFiles",
        ),
        pytest.param(
            "LoadPeakTable",
            {".csv": "csv", ".tsv": "tsv", ".xlsx": "xlsx", ".xls": "xlsx"},
            id="LoadPeakTable",
        ),
        pytest.param(
            "LoadMIDTable",
            {".csv": "csv", ".tsv": "tsv", ".xlsx": "xlsx", ".xls": "xlsx"},
            id="LoadMIDTable",
        ),
        pytest.param(
            "LoadSampleMetadata",
            {".csv": "csv", ".tsv": "tsv", ".xlsx": "xlsx", ".xls": "xlsx"},
            id="LoadSampleMetadata",
        ),
        pytest.param(
            "SaveTable",
            {".csv": "csv", ".tsv": "tsv", ".xlsx": "xlsx"},
            id="SaveTable",
        ),
    ],
)
def test_supported_extensions_declared(block_cls: str, expected: dict[str, str]) -> None:
    """ADR-028 §D8 / #1076: every LCMS IO block declares ``supported_extensions``."""
    cls_map = {
        "LoadMzMLFiles": LoadMzMLFiles,
        "LoadPeakTable": LoadPeakTable,
        "LoadMIDTable": LoadMIDTable,
        "LoadSampleMetadata": LoadSampleMetadata,
        "SaveTable": SaveTable,
    }
    cls = cls_map[block_cls]
    assert cls.supported_extensions == expected


def test_save_table_format_enum_derived_from_supported_extensions() -> None:
    """#1076: SaveTable.config_schema['format']['enum'] is derived from
    ``supported_extensions`` so the writeable format list is single-sourced."""
    enum = SaveTable.config_schema["properties"]["format"]["enum"]
    assert enum == sorted(set(SaveTable.supported_extensions.values()))


def test_load_mzml_module_does_not_export_detect_format() -> None:
    """#1076: deletion-guard for the private module-level helper that was
    superseded by ``IOBlock._detect_format``."""
    from scistudio_blocks_lcms.io import load_mzml_files

    assert not hasattr(load_mzml_files, "_detect_format")
