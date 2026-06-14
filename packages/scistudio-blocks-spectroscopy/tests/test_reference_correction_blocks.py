from __future__ import annotations

import numpy as np
import pytest
from _test_support import install_type_shim

install_type_shim()

from _test_support import make_spectral_dataset, make_spectrum, spectrum_collection, spectrum_xy  # noqa: E402
from scistudio_blocks_spectroscopy.blocks.reference_correction import (  # noqa: E402
    DivideByReferenceSpectrum,
    SubtractReferenceSpectrum,
)

from scistudio.testing import BlockTestHarness  # noqa: E402


@pytest.mark.parametrize("block_cls", [SubtractReferenceSpectrum, DivideByReferenceSpectrum])
def test_reference_correction_block_contracts(block_cls: type) -> None:
    errors = BlockTestHarness(block_cls).validate_block()
    assert not errors, errors


def test_subtract_reference_preserves_identity_metadata_order_and_grid() -> None:
    sample1 = make_spectrum("s1", [0, 1, 2], [10, 20, 30], sample_label="a")
    sample2 = make_spectrum("s2", [0, 1, 2], [5, 7, 11], sample_label="b")
    reference = make_spectrum("ref", [0, 1, 2], [1, 2, 3])
    block = SubtractReferenceSpectrum()

    result = block.run(
        {"spectra": spectrum_collection(sample1, sample2), "reference": spectrum_collection(reference)},
        block.config,
    )

    corrected = result["corrected"]
    assert len(corrected) == 2
    assert corrected[0].user["spectrum_id"] == "s1"
    assert corrected[0].meta.sample_label == "a"
    assert corrected[1].user["spectrum_id"] == "s2"
    x0, y0 = spectrum_xy(corrected[0])
    x1, y1 = spectrum_xy(corrected[1])
    np.testing.assert_allclose(x0, [0, 1, 2])
    np.testing.assert_allclose(x1, [0, 1, 2])
    np.testing.assert_allclose(y0, [9, 18, 27])
    np.testing.assert_allclose(y1, [4, 5, 8])


def test_reference_grid_mismatch_fails_by_default() -> None:
    sample = make_spectrum("s1", [0, 1, 2], [10, 20, 30])
    reference = make_spectrum("ref", [0, 2], [1, 3])
    block = SubtractReferenceSpectrum()

    with pytest.raises(ValueError, match="lambda grids differ"):
        block.run({"spectra": spectrum_collection(sample), "reference": spectrum_collection(reference)}, block.config)


def test_subtract_reference_can_interpolate_reference_to_sample_grid() -> None:
    sample = make_spectrum("s1", [0, 1, 2], [10, 20, 30])
    reference = make_spectrum("ref", [0, 2], [2, 4])
    block = SubtractReferenceSpectrum(config={"params": {"reference_grid_policy": "interpolate_reference_to_sample"}})

    result = block.run(
        {"spectra": spectrum_collection(sample), "reference": spectrum_collection(reference)}, block.config
    )

    _x, y = spectrum_xy(result["corrected"][0])
    np.testing.assert_allclose(y, [8, 17, 26])


def test_divide_reference_applies_formula_on_same_grid() -> None:
    sample = make_spectrum("s1", [0, 1, 2], [10, 20, 30])
    reference = make_spectrum("ref", [0, 1, 2], [2, 4, 5])
    block = DivideByReferenceSpectrum()

    result = block.run(
        {"spectra": spectrum_collection(sample), "reference": spectrum_collection(reference)}, block.config
    )

    _x, y = spectrum_xy(result["corrected"][0])
    np.testing.assert_allclose(y, [5, 5, 6])


def test_divide_reference_zero_denominator_errors_by_default() -> None:
    sample = make_spectrum("s1", [0, 1, 2], [10, 20, 30])
    reference = make_spectrum("ref", [0, 1, 2], [2, 0, 5])
    block = DivideByReferenceSpectrum()

    with pytest.raises(ValueError, match="zero denominator"):
        block.run({"spectra": spectrum_collection(sample), "reference": spectrum_collection(reference)}, block.config)


def test_divide_reference_zero_denominator_policy_nan_is_explicit() -> None:
    sample = make_spectrum("s1", [0, 1, 2], [10, 20, 30])
    reference = make_spectrum("ref", [0, 1, 2], [2, 0, 5])
    block = DivideByReferenceSpectrum(config={"params": {"zero_denominator_policy": "nan"}})

    result = block.run(
        {"spectra": spectrum_collection(sample), "reference": spectrum_collection(reference)}, block.config
    )

    _x, y = spectrum_xy(result["corrected"][0])
    assert y[0] == 5
    assert np.isnan(y[1])
    assert y[2] == 6


def test_reference_correction_rejects_spectral_dataset_direct_input() -> None:
    reference = make_spectrum("ref", [0, 1], [1, 1])
    block = SubtractReferenceSpectrum()

    with pytest.raises(TypeError, match="Collection\\[Spectrum\\]"):
        block.run({"spectra": make_spectral_dataset(), "reference": spectrum_collection(reference)}, block.config)  # type: ignore[arg-type]
