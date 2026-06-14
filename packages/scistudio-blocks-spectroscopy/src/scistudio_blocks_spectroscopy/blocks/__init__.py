"""Spectroscopy block exports."""

from __future__ import annotations

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
    "SpectralDatasetToSpectrum",
    "SpectralUnmixing",
    "SpectrumToSpectralDataset",
    "SubtractPeakComponent",
    "SubtractReferenceSpectrum",
]
