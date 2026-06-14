"""End-to-end tests for SpectralUnmixing (US9, FR-104..FR-112).

Builds known endmember references and a known linear mixture, runs the block,
and asserts the recovered mixing coefficients match the truth; covers the three
methods, deterministic collision-free component column naming, the per-sample
fit_quality rows, and the default ERROR-on-grid-mismatch boundary.
"""

from __future__ import annotations

from typing import Any

import fixtures as fx
import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.unmixing import SpectralUnmixing

from scistudio.blocks.base.config import BlockConfig
from scistudio.testing import BlockTestHarness


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _frame(out: dict, port: str) -> Any:
    return _support.dataframe_pandas(next(iter(out[port])))


def _components(coefficients: Any) -> list[str]:
    return [c for c in coefficients.columns if c not in ("spectrum_id", "method")]


def test_block_validates() -> None:
    assert not BlockTestHarness(SpectralUnmixing).validate_block()


def test_unmixing_recovers_known_coefficients_least_squares() -> None:
    refs = fx.make_reference_spectra(labels=("compA", "compB", "compC"))
    coeffs = [0.2, 0.3, 0.5]
    mixture = fx.make_mixture(refs, coeffs, spectrum_id="mix1")

    out = SpectralUnmixing().run(
        {"spectra": _support.spectra_collection([mixture]), "references": _support.spectra_collection(refs)},
        _cfg(method="least_squares"),
    )
    assert set(out) == {"coefficients", "fit_quality"}
    coefficients = _frame(out, "coefficients")
    cols = _components(coefficients)
    assert cols == ["compA", "compB", "compC"]
    recovered = [float(coefficients.iloc[0][c]) for c in cols]
    assert np.allclose(recovered, coeffs, atol=1e-6)

    quality = _frame(out, "fit_quality")
    assert {"spectrum_id", "method", "status", "residual_norm", "rmse", "n_components"} <= set(quality.columns)
    assert int(quality.iloc[0]["n_components"]) == 3
    assert quality.iloc[0]["status"] == "success"
    assert float(quality.iloc[0]["rmse"]) < 1e-6


def test_unmixing_nnls_non_negative() -> None:
    pytest.importorskip("scipy")
    refs = fx.make_reference_spectra(labels=("compA", "compB", "compC"))
    coeffs = [0.5, 0.0, 0.5]
    mixture = fx.make_mixture(refs, coeffs, spectrum_id="mix1")
    out = SpectralUnmixing().run(
        {"spectra": _support.spectra_collection([mixture]), "references": _support.spectra_collection(refs)},
        _cfg(method="non_negative_least_squares"),
    )
    coefficients = _frame(out, "coefficients")
    recovered = np.asarray([float(coefficients.iloc[0][c]) for c in _components(coefficients)])
    assert (recovered >= -1e-9).all()
    assert np.allclose(recovered, coeffs, atol=1e-6)


def test_unmixing_sum_to_one_constraint() -> None:
    pytest.importorskip("scipy")
    refs = fx.make_reference_spectra(labels=("compA", "compB", "compC"))
    mixture = fx.make_mixture(refs, [0.2, 0.3, 0.5], spectrum_id="mix1")
    out = SpectralUnmixing().run(
        {"spectra": _support.spectra_collection([mixture]), "references": _support.spectra_collection(refs)},
        _cfg(method="sum_to_one_non_negative_least_squares"),
    )
    coefficients = _frame(out, "coefficients")
    total = sum(float(coefficients.iloc[0][c]) for c in _components(coefficients))
    assert abs(total - 1.0) < 1e-3


def test_unmixing_label_collision_deterministic_dedup() -> None:
    # Two references sharing the same spectrum_id -> collision-free, deterministic
    # column names (suffix-deduped), no overwrite.
    lam = fx.DEFAULT_GRID
    ref1 = _support.build_spectrum(lam, fx.gaussian(lam, 5.0, 470.0, 9.0), spectrum_id="endmember A")
    ref2 = _support.build_spectrum(lam, fx.gaussian(lam, 5.0, 540.0, 9.0), spectrum_id="endmember A")
    sample = _support.build_spectrum(lam, np.ones_like(lam), spectrum_id="mix1")
    out = SpectralUnmixing().run(
        {"spectra": _support.spectra_collection([sample]), "references": _support.spectra_collection([ref1, ref2])},
        _cfg(method="least_squares", component_label_source="spectrum_id"),
    )
    coefficients = _frame(out, "coefficients")
    cols = _components(coefficients)
    assert cols == ["endmember_A", "endmember_A_1"]  # sanitised + deduped
    assert "spectrum_id" not in cols and "method" not in cols


def test_unmixing_errors_on_grid_mismatch_by_default() -> None:
    refs = fx.make_reference_spectra(labels=("compA", "compB"))
    shifted = _support.build_spectrum(fx.DEFAULT_GRID + 1000.0, np.ones_like(fx.DEFAULT_GRID), spectrum_id="compB")
    sample = _support.build_spectrum(fx.DEFAULT_GRID, np.ones_like(fx.DEFAULT_GRID), spectrum_id="mix1")
    with pytest.raises(ValueError, match="grids differ"):
        SpectralUnmixing().run(
            {
                "spectra": _support.spectra_collection([sample]),
                "references": _support.spectra_collection([refs[0], shifted]),
            },
            _cfg(method="least_squares"),
        )


def test_unmixing_zero_references_reports_failed() -> None:
    sample = _support.build_spectrum(fx.DEFAULT_GRID, np.ones_like(fx.DEFAULT_GRID), spectrum_id="mix1")
    with pytest.raises(ValueError):
        # Empty references collection -> coerce_spectra raises an empty-input error.
        SpectralUnmixing().run(
            {
                "spectra": _support.spectra_collection([sample]),
                "references": _support.spectra_collection([]),
            },
            _cfg(method="least_squares"),
        )


def test_unmixing_multiple_samples_one_row_each() -> None:
    refs = fx.make_reference_spectra(labels=("compA", "compB", "compC"))
    m1 = fx.make_mixture(refs, [0.2, 0.3, 0.5], spectrum_id="m1")
    m2 = fx.make_mixture(refs, [0.6, 0.1, 0.3], spectrum_id="m2")
    out = SpectralUnmixing().run(
        {"spectra": _support.spectra_collection([m1, m2]), "references": _support.spectra_collection(refs)},
        _cfg(method="least_squares"),
    )
    coefficients = _frame(out, "coefficients")
    assert list(coefficients["spectrum_id"]) == ["m1", "m2"]
    assert np.allclose([float(coefficients.iloc[0][c]) for c in _components(coefficients)], [0.2, 0.3, 0.5], atol=1e-6)
    assert np.allclose([float(coefficients.iloc[1][c]) for c in _components(coefficients)], [0.6, 0.1, 0.3], atol=1e-6)
