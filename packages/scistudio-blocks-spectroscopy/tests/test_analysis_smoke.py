"""Smoke tests for the analysis block group (FR-095..FR-126).

Covers the reference-correction blocks (:class:`SubtractReferenceSpectrum`,
:class:`DivideByReferenceSpectrum`), the library-matching block
(:class:`MatchSpectralLibrary`), and the unmixing block
(:class:`SpectralUnmixing`). Each test builds synthetic inputs via ``_support``,
runs the block, and asserts the declared output ports, item counts, key numeric
results, and status columns.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyarrow as pa
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.library_matching import MatchSpectralLibrary
from scistudio_blocks_spectroscopy.blocks.reference_correction import (
    DivideByReferenceSpectrum,
    SubtractReferenceSpectrum,
)
from scistudio_blocks_spectroscopy.blocks.unmixing import SpectralUnmixing
from scistudio_blocks_spectroscopy.types import (
    INTENSITY_COLUMN,
    LAMBDA_COLUMN,
    SPECTRUM_ID_COLUMN,
    SpectralDataset,
    Spectrum,
)

from scistudio.blocks.base.config import BlockConfig
from scistudio.testing import BlockTestHarness

_LAMBDA = np.linspace(400.0, 410.0, 11)


def _spectrum(intensity: np.ndarray, spectrum_id: str, meta: Spectrum.Meta | None = None) -> Spectrum:
    return _support.build_spectrum(_LAMBDA, np.asarray(intensity, dtype=float), spectrum_id=spectrum_id, meta=meta)


def _config(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _inputs(**ports: Any) -> dict[str, Any]:
    """Build a block ``run`` input map (run() coerces bare DataObjects per contract)."""
    return dict(ports)


def _frame(collection: Any) -> Any:
    return _support.dataframe_pandas(next(iter(collection)))


# ---------------------------------------------------------------------------
# Contract validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "block_cls",
    [SubtractReferenceSpectrum, DivideByReferenceSpectrum, MatchSpectralLibrary, SpectralUnmixing],
)
def test_blocks_pass_contract_validation(block_cls: type) -> None:
    assert not BlockTestHarness(block_cls).validate_block()


# ---------------------------------------------------------------------------
# Reference correction
# ---------------------------------------------------------------------------


def test_subtract_reference_preserves_identity_and_subtracts() -> None:
    s1 = _spectrum(np.full(11, 5.0), "s1")
    s2 = _spectrum(np.full(11, 8.0), "s2")
    reference = _spectrum(np.full(11, 2.0), "ref")

    outputs = SubtractReferenceSpectrum().run(
        _inputs(spectra=_support.spectra_collection([s1, s2]), reference=reference),
        _config(reference_grid_policy="error"),
    )

    assert set(outputs) == {"corrected"}
    corrected = list(outputs["corrected"])
    assert [spec.spectrum_id for spec in corrected] == ["s1", "s2"]

    lam0, inten0 = _support.spectrum_arrays(corrected[0])
    _, inten1 = _support.spectrum_arrays(corrected[1])
    assert np.allclose(lam0, _LAMBDA)  # FR-099 grid preserved
    assert np.allclose(inten0, 3.0)  # FR-100 sample - reference
    assert np.allclose(inten1, 6.0)


def test_subtract_reference_errors_on_grid_mismatch() -> None:
    sample = _spectrum(np.full(11, 5.0), "s1")
    shifted_reference = _support.build_spectrum(_LAMBDA + 50.0, np.full(11, 2.0), spectrum_id="ref")

    with pytest.raises(ValueError, match="grids differ"):
        SubtractReferenceSpectrum().run(
            _inputs(spectra=_support.spectra_collection([sample]), reference=shifted_reference),
            _config(reference_grid_policy="error"),
        )


def test_divide_reference_errors_on_zero_by_default() -> None:
    sample = _spectrum(np.full(11, 5.0), "s1")
    reference = _spectrum(np.concatenate([[0.0], np.full(10, 2.0)]), "ref")

    with pytest.raises(ValueError, match="zero"):
        DivideByReferenceSpectrum().run(
            _inputs(spectra=_support.spectra_collection([sample]), reference=reference),
            _config(reference_grid_policy="error", zero_policy="error"),
        )


def test_divide_reference_nan_policy_marks_zero_coords() -> None:
    sample = _spectrum(np.full(11, 5.0), "s1")
    reference = _spectrum(np.concatenate([[0.0], np.full(10, 2.0)]), "ref")

    outputs = DivideByReferenceSpectrum().run(
        _inputs(spectra=_support.spectra_collection([sample]), reference=reference),
        _config(reference_grid_policy="error", zero_policy="nan"),
    )

    corrected = list(outputs["corrected"])
    assert len(corrected) == 1
    _, intensity = _support.spectrum_arrays(corrected[0])
    assert np.isnan(intensity[0])
    assert np.allclose(intensity[1:], 2.5)  # FR-101 sample / reference


# ---------------------------------------------------------------------------
# Library matching
# ---------------------------------------------------------------------------


def _library(entries: list[tuple[str, np.ndarray]]) -> SpectralDataset:
    spectrum_ids: list[str] = []
    lambdas: list[float] = []
    intensities: list[float] = []
    for spectrum_id, intensity in entries:
        spectrum_ids.extend([spectrum_id] * len(_LAMBDA))
        lambdas.extend(_LAMBDA.tolist())
        intensities.extend(np.asarray(intensity, dtype=float).tolist())
    spectra_table = pa.table({SPECTRUM_ID_COLUMN: spectrum_ids, LAMBDA_COLUMN: lambdas, INTENSITY_COLUMN: intensities})
    index_table = pa.table({SPECTRUM_ID_COLUMN: [entry[0] for entry in entries]})
    return _support.build_spectral_dataset(
        index_table,
        spectra_table,
        meta=SpectralDataset.Meta(lambda_unit="nm", intensity_unit="au"),
    )


def test_match_ranks_top_k_with_rank_one_best() -> None:
    ramp = np.linspace(1.0, 11.0, 11)
    flat = np.full(11, 5.0)
    library = _library([("libA", ramp), ("libB", flat)])
    query = _spectrum(ramp * 2.0, "q1", meta=Spectrum.Meta(lambda_unit="nm", intensity_unit="au"))

    outputs = MatchSpectralLibrary().run(
        _inputs(spectra=_support.spectra_collection([query]), library=library),
        _config(method="cosine_similarity", top_k=2),
    )

    assert set(outputs) == {"matches"}
    frame = _frame(outputs["matches"])
    assert {"spectrum_id", "library_spectrum_id", "method", "rank", "score", "status"} <= set(frame.columns)
    assert len(frame) == 2
    best = frame.sort_values("rank").iloc[0]
    assert int(best["rank"]) == 1
    assert best["library_spectrum_id"] == "libA"  # FR-125 rank 1 == best
    assert best["status"] == "success"


def test_match_distance_method_ranks_smallest_distance_first() -> None:
    ramp = np.linspace(1.0, 11.0, 11)
    flat = np.full(11, 5.0)
    library = _library([("libA", ramp), ("libB", flat)])
    query = _spectrum(ramp, "q1")

    outputs = MatchSpectralLibrary().run(
        _inputs(spectra=_support.spectra_collection([query]), library=library),
        _config(method="euclidean_distance", top_k=2),
    )

    frame = _frame(outputs["matches"]).sort_values("rank")
    assert frame.iloc[0]["library_spectrum_id"] == "libA"  # exact match -> distance 0, rank 1
    assert float(frame.iloc[0]["score"]) <= float(frame.iloc[1]["score"])


def test_match_errors_status_on_incompatible_grid() -> None:
    library = _library([("libA", np.linspace(1.0, 11.0, 11))])
    query = _support.build_spectrum(_LAMBDA + 1000.0, np.linspace(1.0, 11.0, 11), spectrum_id="q_bad")

    outputs = MatchSpectralLibrary().run(
        _inputs(spectra=_support.spectra_collection([query]), library=library),
        _config(method="cosine_similarity", top_k=1),
    )

    frame = _frame(outputs["matches"])
    assert (frame["status"] == "incompatible_grid").all()  # FR-126 no silent interpolation


# ---------------------------------------------------------------------------
# Unmixing
# ---------------------------------------------------------------------------


def _unmix_references() -> tuple[Spectrum, Spectrum]:
    ref1 = _spectrum(np.sin(_LAMBDA / 3.0) + 2.0, "endmember A")
    ref2 = _spectrum(np.cos(_LAMBDA / 2.0) + 2.0, "endmember A")  # duplicate id -> collision test
    return ref1, ref2


def test_unmixing_wide_coefficients_and_fit_quality() -> None:
    ref1, ref2 = _unmix_references()
    _, r1 = _support.spectrum_arrays(ref1)
    _, r2 = _support.spectrum_arrays(ref2)
    sample = _spectrum(0.3 * r1 + 0.7 * r2, "mix1")

    outputs = SpectralUnmixing().run(
        _inputs(
            spectra=_support.spectra_collection([sample]),
            references=_support.spectra_collection([ref1, ref2]),
        ),
        _config(method="least_squares"),
    )

    assert set(outputs) == {"coefficients", "fit_quality"}
    coefficients = _frame(outputs["coefficients"])
    quality = _frame(outputs["fit_quality"])

    # Wide coefficients: one row per sample, spectrum_id + method + one column per reference.
    assert len(coefficients) == 1
    assert "spectrum_id" in coefficients.columns and "method" in coefficients.columns
    component_columns = [c for c in coefficients.columns if c not in ("spectrum_id", "method")]
    assert len(component_columns) == 2
    values = sorted(float(coefficients.iloc[0][c]) for c in component_columns)
    assert np.allclose(values, [0.3, 0.7], atol=1e-6)

    # Fit quality: one row per sample with the required columns.
    assert len(quality) == 1
    assert {"spectrum_id", "method", "status", "residual_norm", "rmse", "n_components"} <= set(quality.columns)
    row = quality.iloc[0]
    assert int(row["n_components"]) == 2
    assert row["status"] == "success"
    assert float(row["rmse"]) < 1e-6


def test_unmixing_collision_free_columns() -> None:
    ref1, ref2 = _unmix_references()  # both carry spectrum_id "endmember A"
    sample = _spectrum(np.full(11, 1.0), "mix1")

    outputs = SpectralUnmixing().run(
        _inputs(
            spectra=_support.spectra_collection([sample]),
            references=_support.spectra_collection([ref1, ref2]),
        ),
        _config(method="least_squares", component_label_source="spectrum_id"),
    )

    coefficients = _frame(outputs["coefficients"])
    component_columns = [c for c in coefficients.columns if c not in ("spectrum_id", "method")]
    # Table-safe (space sanitised) and collision-free (suffix-deduped).
    assert component_columns == ["endmember_A", "endmember_A_1"]
    assert "spectrum_id" not in component_columns


def test_unmixing_non_negative_least_squares() -> None:
    pytest.importorskip("scipy")
    ref1, ref2 = _unmix_references()
    _, r1 = _support.spectrum_arrays(ref1)
    _, r2 = _support.spectrum_arrays(ref2)
    sample = _spectrum(0.3 * r1 + 0.7 * r2, "mix1")

    outputs = SpectralUnmixing().run(
        _inputs(
            spectra=_support.spectra_collection([sample]),
            references=_support.spectra_collection([ref1, ref2]),
        ),
        _config(method="non_negative_least_squares"),
    )

    coefficients = _frame(outputs["coefficients"])
    component_columns = [c for c in coefficients.columns if c not in ("spectrum_id", "method")]
    values = np.asarray([float(coefficients.iloc[0][c]) for c in component_columns])
    assert (values >= -1e-9).all()
    assert np.allclose(sorted(values), [0.3, 0.7], atol=1e-6)


def test_unmixing_sum_to_one_constraint() -> None:
    pytest.importorskip("scipy")
    ref1, ref2 = _unmix_references()
    _, r1 = _support.spectrum_arrays(ref1)
    _, r2 = _support.spectrum_arrays(ref2)
    sample = _spectrum(0.3 * r1 + 0.7 * r2, "mix1")

    outputs = SpectralUnmixing().run(
        _inputs(
            spectra=_support.spectra_collection([sample]),
            references=_support.spectra_collection([ref1, ref2]),
        ),
        _config(method="sum_to_one_non_negative_least_squares"),
    )

    coefficients = _frame(outputs["coefficients"])
    component_columns = [c for c in coefficients.columns if c not in ("spectrum_id", "method")]
    total = sum(float(coefficients.iloc[0][c]) for c in component_columns)
    assert abs(total - 1.0) < 1e-3


def test_unmixing_errors_on_grid_mismatch_by_default() -> None:
    ref1, _ = _unmix_references()
    shifted_reference = _support.build_spectrum(_LAMBDA + 1000.0, np.full(11, 1.0), spectrum_id="ref2")
    sample = _spectrum(np.full(11, 1.0), "mix1")

    with pytest.raises(ValueError, match="grids differ"):
        SpectralUnmixing().run(
            _inputs(
                spectra=_support.spectra_collection([sample]),
                references=_support.spectra_collection([ref1, shifted_reference]),
            ),
            _config(method="least_squares"),
        )
