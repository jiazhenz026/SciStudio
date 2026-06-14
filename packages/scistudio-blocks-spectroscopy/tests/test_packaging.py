"""Packaging + wiring contract tests for scistudio-blocks-spectroscopy.

These tests run against the skeleton (no algorithm bodies). They assert the
stable shared interface: block roster, types, previewers, entry points, and
that every block passes the BlockTestHarness contract check.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

import scistudio_blocks_spectroscopy as pkg

from scistudio.blocks.base.package_info import PackageInfo
from scistudio.testing import BlockTestHarness

EXPECTED_BLOCK_NAMES = sorted(
    [
        # utilities (9)
        "LoadSpectrum",
        "SaveSpectrum",
        "LoadSpectralDataset",
        "SaveSpectralDataset",
        "SpectrumToSpectralDataset",
        "SpectralDatasetToSpectrum",
        "FilterSpectralDataset",
        "MergeSpectralDataset",
        "AttachFeaturesToSpectralDataset",
        # preprocessing (7)
        "CropSpectrumRange",
        "ShiftSpectralAxis",
        "BaselineCorrection",
        "SmoothSpectrum",
        "AlignAndResampleSpectra",
        "NormalizeSpectrum",
        "SubtractPeakComponent",
        # feature_extraction (5)
        "ExtractIntensity",
        "CalculateAUC",
        "CalculateCentroid",
        "CalculateRatio",
        "FindPeaks",
        # peak_fitting (1)
        "FitPeak",
        # reference_correction (2)
        "SubtractReferenceSpectrum",
        "DivideByReferenceSpectrum",
        # library_matching (1)
        "MatchSpectralLibrary",
        # unmixing (1)
        "SpectralUnmixing",
    ]
)


def _pyproject() -> dict:
    path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_get_blocks_returns_26_unique_blocks() -> None:
    blocks = pkg.get_blocks()
    assert len(blocks) == 26
    assert sorted(b.__name__ for b in blocks) == EXPECTED_BLOCK_NAMES
    type_names = {cast("str", getattr(b, "type_name", b.__name__)) for b in blocks}
    assert len(type_names) == len(blocks), "block type_name values must be unique"


def test_get_types_returns_spectrum_and_dataset() -> None:
    assert [t.__name__ for t in pkg.get_types()] == ["Spectrum", "SpectralDataset"]


def test_get_package_info_metadata() -> None:
    info = pkg.get_package_info()
    assert isinstance(info, PackageInfo)
    assert info.name == "scistudio-blocks-spectroscopy"
    assert info.author == "SciStudio Contributors"
    assert info.version == "0.1.0"


def test_get_block_package_pairs_info_and_blocks() -> None:
    info, blocks = pkg.get_block_package()
    assert info == pkg.get_package_info()
    assert blocks == pkg.get_blocks()


def test_version_constant_matches_pyproject() -> None:
    assert pkg.__version__ == _pyproject()["project"]["version"]


def test_pyproject_declares_three_entry_points() -> None:
    project = _pyproject()["project"]
    eps = project["entry-points"]
    assert eps["scistudio.blocks"]["spectroscopy"] == "scistudio_blocks_spectroscopy:get_block_package"
    assert eps["scistudio.types"]["spectroscopy"] == "scistudio_blocks_spectroscopy:get_types"
    assert eps["scistudio.previewers"]["spectroscopy"] == "scistudio_blocks_spectroscopy.previewers:get_previewers"


def test_pyproject_lists_runtime_dependencies() -> None:
    deps = set(_pyproject()["project"]["dependencies"])
    assert "scistudio>=0.2.1" in deps
    assert {"numpy>=1.24", "scipy>=1.11", "pandas>=2.2", "pyarrow>=15", "pydantic>=2.0"}.issubset(deps)


def test_every_block_passes_contract_validation() -> None:
    for cls in pkg.get_blocks():
        errors = BlockTestHarness(cls).validate_block()
        assert not errors, f"{cls.__name__}: {errors}"
