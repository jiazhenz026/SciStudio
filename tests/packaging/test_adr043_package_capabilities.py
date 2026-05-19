"""Root-level ADR-043 package capability regression tests.

The workflow compliance check requires a root ``tests/`` update whenever
package source changes. These assertions mirror the package-local pilot tests
without depending on editable package installs.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _package_src in (
    _REPO_ROOT / "packages" / "scieasy-blocks-imaging" / "src",
    _REPO_ROOT / "packages" / "scieasy-blocks-lcms" / "src",
):
    sys.path.insert(0, str(_package_src))


def test_adr043_package_pilot_capabilities_are_explicit() -> None:
    from scieasy_blocks_imaging.io.load_image import LoadImage
    from scieasy_blocks_imaging.io.save_image import SaveImage
    from scieasy_blocks_lcms.io.load_mzml_files import LoadMzMLFiles
    from scieasy_blocks_lcms.io.load_peak_table import LoadPeakTable
    from scieasy_blocks_lcms.io.save_table import SaveTable

    capabilities = [
        *LoadImage.get_format_capabilities(),
        *SaveImage.get_format_capabilities(),
        *LoadMzMLFiles.get_format_capabilities(),
        *LoadPeakTable.get_format_capabilities(),
        *SaveTable.get_format_capabilities(),
    ]
    ids = {capability.id for capability in capabilities}

    assert "scieasy-blocks-imaging.image.tiff.load" in ids
    assert "scieasy-blocks-imaging.image.zarr.save" in ids
    assert "scieasy-blocks-lcms.ms_raw.mzml.load" in ids
    assert "scieasy-blocks-lcms.peak_table.csv.load" in ids
    assert "scieasy-blocks-lcms.table.xlsx.save" in ids
    assert all(not capability.is_synthesized for capability in capabilities)
