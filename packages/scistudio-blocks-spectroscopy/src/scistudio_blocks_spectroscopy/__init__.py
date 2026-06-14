"""SciStudio spectroscopy package metadata and public exports."""

from __future__ import annotations

from scistudio.blocks.base.package_info import PackageInfo
from scistudio_blocks_spectroscopy.blocks.feature_extraction import (
    CalculateAUC,
    CalculateCentroid,
    CalculateRatio,
    ExtractIntensity,
    FindPeaks,
)
from scistudio_blocks_spectroscopy.blocks.library_matching import MatchSpectralLibrary
from scistudio_blocks_spectroscopy.blocks.peak_fitting import FitPeak
from scistudio_blocks_spectroscopy.blocks.preprocessing import (
    AlignAndResampleSpectra,
    BaselineCorrection,
    CropSpectrumRange,
    NormalizeSpectrum,
    ShiftSpectralAxis,
    SmoothSpectrum,
    SubtractPeakComponent,
)
from scistudio_blocks_spectroscopy.blocks.reference_correction import (
    DivideByReferenceSpectrum,
    SubtractReferenceSpectrum,
)
from scistudio_blocks_spectroscopy.blocks.unmixing import SpectralUnmixing
from scistudio_blocks_spectroscopy.blocks.utilities import (
    AttachFeaturesToSpectralDataset,
    FilterSpectralDataset,
    LoadSpectralDataset,
    LoadSpectrum,
    MergeSpectralDataset,
    SaveSpectralDataset,
    SaveSpectrum,
    SpectralDatasetToSpectrum,
    SpectrumToSpectralDataset,
)
from scistudio_blocks_spectroscopy.previewers import get_previewers
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

__version__ = "0.1.0.dev0"

_SPECTROSCOPY_TYPES: tuple[type, ...] = (Spectrum, SpectralDataset)
_SPECTROSCOPY_BLOCKS: tuple[type, ...] = (
    LoadSpectrum,
    SaveSpectrum,
    LoadSpectralDataset,
    SaveSpectralDataset,
    SpectrumToSpectralDataset,
    SpectralDatasetToSpectrum,
    FilterSpectralDataset,
    MergeSpectralDataset,
    AttachFeaturesToSpectralDataset,
    CropSpectrumRange,
    ShiftSpectralAxis,
    BaselineCorrection,
    SmoothSpectrum,
    AlignAndResampleSpectra,
    NormalizeSpectrum,
    SubtractPeakComponent,
    ExtractIntensity,
    CalculateAUC,
    CalculateCentroid,
    CalculateRatio,
    FindPeaks,
    FitPeak,
    SubtractReferenceSpectrum,
    DivideByReferenceSpectrum,
    MatchSpectralLibrary,
    SpectralUnmixing,
)


def get_package_info() -> PackageInfo:
    """Return package metadata for the block registry."""

    return PackageInfo(
        name="scistudio-blocks-spectroscopy",
        description="General 1-D spectroscopy blocks for SciStudio workflows.",
        author="SciStudio Contributors",
        version=__version__,
    )


def get_types() -> list[type]:
    """Return the package's exported public data types."""

    return list(_SPECTROSCOPY_TYPES)


def get_blocks() -> list[type]:
    """Return the package's exported public block classes."""

    return list(_SPECTROSCOPY_BLOCKS)


def get_block_package() -> tuple[PackageInfo, list[type]]:
    """Return package metadata and blocks for ``scistudio.blocks``."""

    return get_package_info(), get_blocks()


__all__ = [
    "AlignAndResampleSpectra",
    "AttachFeaturesToSpectralDataset",
    "BaselineCorrection",
    "CalculateAUC",
    "CalculateCentroid",
    "CalculateRatio",
    "CropSpectrumRange",
    "DivideByReferenceSpectrum",
    "ExtractIntensity",
    "FilterSpectralDataset",
    "FindPeaks",
    "FitPeak",
    "LoadSpectralDataset",
    "LoadSpectrum",
    "MatchSpectralLibrary",
    "MergeSpectralDataset",
    "NormalizeSpectrum",
    "SaveSpectralDataset",
    "SaveSpectrum",
    "ShiftSpectralAxis",
    "SmoothSpectrum",
    "SpectralDataset",
    "SpectralDatasetToSpectrum",
    "SpectralUnmixing",
    "Spectrum",
    "SpectrumToSpectralDataset",
    "SubtractPeakComponent",
    "SubtractReferenceSpectrum",
    "__version__",
    "get_block_package",
    "get_blocks",
    "get_package_info",
    "get_previewers",
    "get_types",
]
