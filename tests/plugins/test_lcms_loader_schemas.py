"""Verify LCMS loader blocks use file_browser with multi-file path schema.

Regression test for issue #525: all LCMS load blocks should use
``ui_widget: file_browser`` with ``type: ["string", "array"]`` path
config, matching the LoadImage pattern.
"""

from __future__ import annotations

import pytest

try:
    from scieasy_blocks_lcms.io.load_mid_table import LoadMIDTable
    from scieasy_blocks_lcms.io.load_mzml_files import LoadMzMLFiles
    from scieasy_blocks_lcms.io.load_peak_table import LoadPeakTable
    from scieasy_blocks_lcms.io.load_sample_metadata import LoadSampleMetadata

    HAS_LCMS = True
except ImportError:
    HAS_LCMS = False

pytestmark = pytest.mark.skipif(not HAS_LCMS, reason="scieasy_blocks_lcms not installed")


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
