"""Foundation type + support-helper tests (skeleton-safe)."""

from __future__ import annotations

import numpy as np
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series


def test_spectrum_is_series_with_canonical_names() -> None:
    spec = Spectrum()
    assert isinstance(spec, Series)
    assert spec.index_name == "lambda"
    assert spec.value_name == "intensity"


def test_spectrum_meta_required_fields_exist() -> None:
    fields = set(Spectrum.Meta.model_fields)
    assert {"lambda_unit", "intensity_unit", "lambda_kind", "modality"}.issubset(fields)


def test_spectral_dataset_two_slots() -> None:
    assert issubclass(SpectralDataset, CompositeData)
    assert SpectralDataset.expected_slots == {"index": DataFrame, "spectra": DataFrame}


def test_spectral_dataset_meta_fields_exist() -> None:
    fields = set(SpectralDataset.Meta.model_fields)
    assert {
        "dataset_name",
        "dataset_role",
        "lambda_unit",
        "intensity_unit",
        "modality",
        "schema_version",
    }.issubset(fields)


def test_build_and_read_spectrum_roundtrip() -> None:
    spec = _support.build_spectrum([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    lam, inten = _support.spectrum_arrays(spec)
    assert np.allclose(lam, [1.0, 2.0, 3.0])
    assert np.allclose(inten, [10.0, 20.0, 30.0])
    assert spec.length == 3


def test_derive_spectrum_replaces_intensity_keeps_grid() -> None:
    spec = _support.build_spectrum([1.0, 2.0], [5.0, 6.0])
    derived = _support.derive_spectrum(spec, intensity_values=[7.0, 8.0])
    lam, inten = _support.spectrum_arrays(derived)
    assert np.allclose(lam, [1.0, 2.0])
    assert np.allclose(inten, [7.0, 8.0])


def test_spectra_collection_handles_empty() -> None:
    empty = _support.spectra_collection([])
    assert empty.item_type is Spectrum
    assert len(empty) == 0


def test_dataframe_collection_wraps_single_table() -> None:
    df = _support.dataframe_from_rows([{"spectrum_id": "a", "auc": 1.0}])
    coll = _support.dataframe_collection(df)
    assert coll.item_type is DataFrame
    assert len(coll) == 1
