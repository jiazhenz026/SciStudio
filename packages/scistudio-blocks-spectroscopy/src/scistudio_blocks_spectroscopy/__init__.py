"""SciStudio spectroscopy plugin package metadata and public exports.

Registers, via three entry points (``scistudio.blocks`` / ``scistudio.types`` /
``scistudio.previewers``):

- 26 block classes (9 utilities, 7 preprocessing, 5 feature extraction, 1 peak
  fitting, 2 reference correction, 1 library matching, 1 unmixing);
- 2 data types (:class:`Spectrum`, :class:`SpectralDataset`);
- 2 previewers (Spectrum, SpectralDataset).

``get_previewers`` is re-exported here so the monorepo dev-mode discovery seam
finds it at the top level.
"""

from __future__ import annotations

from scistudio.blocks.base.package_info import PackageInfo
from scistudio_blocks_spectroscopy.blocks import BLOCKS as _SPECTROSCOPY_BLOCKS
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
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum, get_types

__version__ = "0.1.0"

_SPECTROSCOPY_TYPES: tuple[type, ...] = (Spectrum, SpectralDataset)


def get_package_info() -> PackageInfo:
    """Return package metadata for the ``scistudio.blocks`` registry."""
    return PackageInfo(
        name="scistudio-blocks-spectroscopy",
        description="General 1-D spectroscopy blocks (Raman, FTIR, UV-Vis, fluorescence, NIR) for SciStudio.",
        author="SciStudio Contributors",
        version=__version__,
    )


def get_blocks() -> list[type]:
    """Return the spectroscopy plugin's exported concrete block classes."""
    return list(_SPECTROSCOPY_BLOCKS)


def get_block_package() -> tuple[PackageInfo, list[type]]:
    """Return package metadata and block classes for ``scistudio.blocks``."""
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
