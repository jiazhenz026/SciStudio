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
    _REPO_ROOT / "packages" / "scistudio-blocks-imaging" / "src",
    _REPO_ROOT / "packages" / "scistudio-blocks-lcms" / "src",
):
    sys.path.insert(0, str(_package_src))


def test_adr043_package_pilot_capabilities_are_explicit() -> None:
    from scistudio_blocks_imaging.io.load_image import LoadImage
    from scistudio_blocks_imaging.io.save_image import SaveImage
    from scistudio_blocks_lcms.io.load_mzml_files import LoadMzMLFiles
    from scistudio_blocks_lcms.io.load_peak_table import LoadPeakTable
    from scistudio_blocks_lcms.io.save_table import SaveTable

    capabilities = [
        *LoadImage.get_format_capabilities(),
        *SaveImage.get_format_capabilities(),
        *LoadMzMLFiles.get_format_capabilities(),
        *LoadPeakTable.get_format_capabilities(),
        *SaveTable.get_format_capabilities(),
    ]
    ids = {capability.id for capability in capabilities}

    assert "scistudio-blocks-imaging.image.tiff.load" in ids
    assert "scistudio-blocks-imaging.image.zarr.save" in ids
    assert "scistudio-blocks-lcms.ms_raw.mzml.load" in ids
    assert "scistudio-blocks-lcms.peak_table.csv.load" in ids
    assert "scistudio-blocks-lcms.table.xlsx.save" in ids
    assert all(not capability.is_synthesized for capability in capabilities)


# ---------------------------------------------------------------------------
# ADR-050 canvas-node-readability — all-four-package registry contract (#1698)
#
# The square node + BottomPanel refactor must render package-provided blocks
# from imaging, spectroscopy, LCMS, AND SRS through the package -> registry ->
# API contract without package source edits. The pilot test above covers
# imaging + LCMS capability metadata directly from the classes; the tests below
# go through the live BlockRegistry (the real entry-point path) to prove
# spectroscopy and SRS resolve with the node-contract metadata intact, so all
# four domains named in FR-033 / SC-011 are exercised in this root test file.
#
# Spec: docs/specs/adr-050-canvas-node-readability.md FR-030/FR-033, SC-011.
# ---------------------------------------------------------------------------


def test_adr050_all_four_packages_resolve_through_registry() -> None:
    """FR-033/SC-011: imaging, spectroscopy, LCMS, and SRS blocks resolve via registry.

    Each package registers via its ``scistudio.blocks`` entry point; the
    representative block must come back from a scanned registry with the package
    name and base_category that the square node mark + palette grouping read.
    """
    from scistudio.blocks.registry import BlockRegistry

    registry = BlockRegistry()
    registry.scan()
    specs_by_type = {spec.type_name: spec for spec in registry.all_specs().values()}

    expected = {
        "imaging.axis_merge": "scistudio-blocks-imaging",
        "spectroscopy.find_peaks": "scistudio-blocks-spectroscopy",
        "lcms.pool_size_normalize": "scistudio-blocks-lcms",
        "srs.pca": "scistudio-blocks-srs",
    }
    for type_name, package_name in expected.items():
        assert type_name in specs_by_type, f"{type_name} not resolved through the registry"
        spec = specs_by_type[type_name]
        assert spec.package_name == package_name
        # base_category drives the square-node block-kind mark (FR-028).
        assert spec.base_category in {"io", "process", "code", "app", "ai", "subworkflow"}
        # typed ports survive for canvas rendering (FR-030).
        assert [*spec.input_ports, *spec.output_ports], f"{type_name} lost all ports"


def test_adr050_spectroscopy_io_capabilities_resolve_through_registry() -> None:
    """FR-030/SC-011: a spectroscopy IO block keeps format_capabilities via the registry.

    Spectroscopy has no capability assertions in the imaging/LCMS pilot above;
    this proves the spectroscopy loader still advertises its format capabilities
    after the node refactor, so BottomPanel capability selection works for the
    spectroscopy domain too.
    """
    from scistudio.blocks.registry import BlockRegistry

    registry = BlockRegistry()
    registry.scan()
    spec = next(
        (s for s in registry.all_specs().values() if s.type_name == "spectroscopy.load_spectrum"),
        None,
    )
    assert spec is not None, "spectroscopy.load_spectrum not registered"
    assert spec.format_capabilities, "spectroscopy.load_spectrum lost its format_capabilities"
    assert all(not capability.is_synthesized for capability in spec.format_capabilities)
