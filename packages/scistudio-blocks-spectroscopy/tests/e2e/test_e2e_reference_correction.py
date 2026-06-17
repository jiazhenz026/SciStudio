"""End-to-end tests for the 2 reference-correction blocks (US8, FR-095..FR-103).

SubtractReferenceSpectrum / DivideByReferenceSpectrum operate on
``Collection[Spectrum]`` + one reference ``Spectrum``, preserve item
count/order/spectrum_id/grid (FR-099), default to ERROR on grid mismatch
(FR-102) and (for division) on reference zeros (FR-103). Tests assert the
analytic corrected intensities and exhaustively cover the policy boundaries.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.reference_correction import (
    DivideByReferenceSpectrum,
    SubtractReferenceSpectrum,
)
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.testing import BlockTestHarness

_GRID = np.linspace(400.0, 410.0, 11)


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _spec(intensity: Any, sid: str) -> Spectrum:
    return _support.build_spectrum(_GRID, np.asarray(intensity, dtype=float), spectrum_id=sid)


@pytest.mark.parametrize("block_cls", [SubtractReferenceSpectrum, DivideByReferenceSpectrum])
def test_block_validates(block_cls: type) -> None:
    assert not BlockTestHarness(block_cls).validate_block()


# ---------------------------------------------------------------------------
# Subtract
# ---------------------------------------------------------------------------


def test_subtract_reference_same_grid() -> None:
    s1 = _spec(np.full(11, 5.0), "s1")
    s2 = _spec(np.full(11, 8.0), "s2")
    ref = _spec(np.full(11, 2.0), "ref")
    out = SubtractReferenceSpectrum().run(
        {"spectra": _support.spectra_collection([s1, s2]), "reference": ref},
        _cfg(reference_grid_policy="error"),
    )
    assert set(out) == {"corrected"}
    corrected = list(out["corrected"])
    assert [c.spectrum_id for c in corrected] == ["s1", "s2"]  # order + id preserved
    lam0, c0 = _support.spectrum_arrays(corrected[0])
    _, c1 = _support.spectrum_arrays(corrected[1])
    assert np.allclose(lam0, _GRID)  # grid preserved (FR-099)
    assert np.allclose(c0, 3.0) and np.allclose(c1, 6.0)  # sample - reference


def test_subtract_errors_on_grid_mismatch_by_default() -> None:
    s1 = _spec(np.full(11, 5.0), "s1")
    shifted = _support.build_spectrum(_GRID + 50.0, np.full(11, 2.0), spectrum_id="ref")
    with pytest.raises(ValueError, match="grids differ"):
        SubtractReferenceSpectrum().run(
            {"spectra": _support.spectra_collection([s1]), "reference": shifted},
            _cfg(reference_grid_policy="error"),
        )


def test_subtract_interpolation_policy_resamples_reference() -> None:
    s1 = _spec(np.full(11, 5.0), "s1")
    # Reference on a denser grid covering the sample range, constant 2.0.
    dense = np.linspace(400.0, 410.0, 41)
    ref = _support.build_spectrum(dense, np.full(41, 2.0), spectrum_id="ref")
    out = SubtractReferenceSpectrum().run(
        {"spectra": _support.spectra_collection([s1]), "reference": ref},
        _cfg(reference_grid_policy="interpolate_reference_to_sample"),
    )
    _, corrected = _support.spectrum_arrays(next(iter(out["corrected"])))
    assert np.allclose(corrected, 3.0)


# ---------------------------------------------------------------------------
# Divide
# ---------------------------------------------------------------------------


def test_divide_reference_same_grid() -> None:
    sample = _spec(np.full(11, 6.0), "s1")
    ref = _spec(np.full(11, 2.0), "ref")
    out = DivideByReferenceSpectrum().run(
        {"spectra": _support.spectra_collection([sample]), "reference": ref},
        _cfg(reference_grid_policy="error", zero_policy="error"),
    )
    _, corrected = _support.spectrum_arrays(next(iter(out["corrected"])))
    assert np.allclose(corrected, 3.0)  # sample / reference


def test_divide_errors_on_zero_by_default() -> None:
    sample = _spec(np.full(11, 5.0), "s1")
    ref = _spec(np.concatenate([[0.0], np.full(10, 2.0)]), "ref")
    with pytest.raises(ValueError, match="zero"):
        DivideByReferenceSpectrum().run(
            {"spectra": _support.spectra_collection([sample]), "reference": ref},
            _cfg(reference_grid_policy="error", zero_policy="error"),
        )


def test_divide_nan_policy_marks_zero_coords() -> None:
    sample = _spec(np.full(11, 5.0), "s1")
    ref = _spec(np.concatenate([[0.0], np.full(10, 2.0)]), "ref")
    out = DivideByReferenceSpectrum().run(
        {"spectra": _support.spectra_collection([sample]), "reference": ref},
        _cfg(reference_grid_policy="error", zero_policy="nan"),
    )
    _, corrected = _support.spectrum_arrays(next(iter(out["corrected"])))
    assert np.isnan(corrected[0])
    assert np.allclose(corrected[1:], 2.5)


def test_divide_clip_policy_avoids_hard_error() -> None:
    # clip replaces zero denominators with the smallest positive float; the
    # quotient at the clipped coordinate becomes a huge value (inf for a large
    # numerator), but the block does not raise and the non-zero coords are exact.
    sample = _spec(np.full(11, 5.0), "s1")
    ref = _spec(np.concatenate([[0.0], np.full(10, 2.0)]), "ref")
    with np.errstate(over="ignore"):  # 5/tiny overflow is the behavior under test
        out = DivideByReferenceSpectrum().run(
            {"spectra": _support.spectra_collection([sample]), "reference": ref},
            _cfg(reference_grid_policy="error", zero_policy="clip"),
        )
    _, corrected = _support.spectrum_arrays(next(iter(out["corrected"])))
    assert corrected[0] > 1e30  # 5 / tiny -> astronomically large (or inf)
    assert not np.isnan(corrected[0])  # clip never produces NaN, unlike the nan policy
    assert np.allclose(corrected[1:], 2.5)


def test_divide_errors_on_grid_mismatch_by_default() -> None:
    sample = _spec(np.full(11, 5.0), "s1")
    shifted = _support.build_spectrum(_GRID + 1000.0, np.full(11, 2.0), spectrum_id="ref")
    with pytest.raises(ValueError, match="grids differ"):
        DivideByReferenceSpectrum().run(
            {"spectra": _support.spectra_collection([sample]), "reference": shifted},
            _cfg(reference_grid_policy="error", zero_policy="error"),
        )


def test_reference_correction_preserves_metadata_and_count() -> None:
    s1 = _support.build_spectrum(
        _GRID, np.full(11, 5.0), meta=Spectrum.Meta(lambda_unit="nm", modality="ftir"), spectrum_id="s1"
    )
    ref = _spec(np.full(11, 1.0), "ref")
    out = SubtractReferenceSpectrum().run(
        {"spectra": _support.spectra_collection([s1]), "reference": ref},
        _cfg(reference_grid_policy="error"),
    )
    corrected = next(iter(out["corrected"]))
    assert len(list(out["corrected"])) == 1
    assert isinstance(corrected.meta, Spectrum.Meta)
    assert corrected.meta.lambda_unit == "nm" and corrected.meta.modality == "ftir"
