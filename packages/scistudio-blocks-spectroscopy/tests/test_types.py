from __future__ import annotations

import pandas as pd
import pytest
import scistudio_blocks_spectroscopy as spectroscopy
from helpers import dataset_meta, make_dataset, make_spectrum, spectrum_meta
from scistudio_blocks_spectroscopy._tables import dataframe_from_pandas
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series


def test_package_exports_exact_public_types_and_blocks() -> None:
    assert spectroscopy.get_types() == [Spectrum, SpectralDataset]
    assert [block.__name__ for block in spectroscopy.get_blocks()] == [
        "LoadSpectrum",
        "SaveSpectrum",
        "LoadSpectralDataset",
        "SaveSpectralDataset",
        "SpectrumToSpectralDataset",
        "SpectralDatasetToSpectrum",
        "FilterSpectralDataset",
        "MergeSpectralDataset",
        "AttachFeaturesToSpectralDataset",
        "CropSpectrumRange",
        "ShiftSpectralAxis",
        "BaselineCorrection",
        "SmoothSpectrum",
        "AlignAndResampleSpectra",
        "NormalizeSpectrum",
        "SubtractPeakComponent",
        "ExtractIntensity",
        "CalculateAUC",
        "CalculateCentroid",
        "CalculateRatio",
        "FindPeaks",
        "FitPeak",
        "SubtractReferenceSpectrum",
        "DivideByReferenceSpectrum",
        "MatchSpectralLibrary",
        "SpectralUnmixing",
    ]
    assert not hasattr(spectroscopy, "SpectralLibrary")
    assert not hasattr(spectroscopy, "FeatureTable")


def test_spectrum_is_canonical_series_without_type_level_io_extensions() -> None:
    spectrum = make_spectrum()

    assert isinstance(spectrum, Series)
    assert spectrum.index_name == "lambda"
    assert spectrum.value_name == "intensity"
    assert spectrum_meta(spectrum).lambda_unit == "cm^-1"
    assert not hasattr(Spectrum, "supported_extensions")

    with pytest.raises(ValueError, match="index_name='lambda'"):
        Spectrum(index_name="wavelength")
    with pytest.raises(ValueError, match="value_name='intensity'"):
        Spectrum(value_name="signal")


def test_spectral_dataset_slots_and_required_columns() -> None:
    dataset = make_dataset()

    assert isinstance(dataset, CompositeData)
    assert set(dataset.slots) == {"index", "spectra"}
    assert dataset.index.columns is not None
    assert dataset.index.columns[0] == "spectrum_id"
    assert dataset_meta(dataset).dataset_role == "experiment"
    assert not hasattr(SpectralDataset, "supported_extensions")

    with pytest.raises(ValueError, match="requires 'index' and 'spectra'"):
        SpectralDataset()
    with pytest.raises(ValueError, match="does not accept slots"):
        SpectralDataset(
            slots={
                "index": dataset.index,
                "spectra": dataset.spectra,
                "extra": dataset.index,
            }
        )


def test_spectral_dataset_validates_required_and_unique_ids() -> None:
    index_missing_id: DataFrame = dataframe_from_pandas(pd.DataFrame({"sample": ["a"]}))
    spectra: DataFrame = dataframe_from_pandas(
        pd.DataFrame({"spectrum_id": ["s1"], "lambda": [1.0], "intensity": [2.0]})
    )
    with pytest.raises(ValueError, match="'spectrum_id' column"):
        SpectralDataset(slots={"index": index_missing_id, "spectra": spectra})

    index: DataFrame = dataframe_from_pandas(pd.DataFrame({"spectrum_id": ["s1"]}))
    spectra_missing_intensity: DataFrame = dataframe_from_pandas(pd.DataFrame({"spectrum_id": ["s1"], "lambda": [1.0]}))
    with pytest.raises(ValueError, match="missing required columns"):
        SpectralDataset(slots={"index": index, "spectra": spectra_missing_intensity})

    duplicate_index: DataFrame = dataframe_from_pandas(pd.DataFrame({"spectrum_id": ["s1", "s1"]}))
    with pytest.raises(ValueError, match="must be unique"):
        SpectralDataset(slots={"index": duplicate_index, "spectra": spectra})
