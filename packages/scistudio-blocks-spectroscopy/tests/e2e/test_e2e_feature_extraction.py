"""End-to-end workflow tests for the 5 feature-extraction blocks (US7, FR-082..FR-094).

Each block accepts ``Collection[Spectrum]`` and emits ONE flat feature
``DataFrame`` keyed by ``spectrum_id`` with a ``status`` column. Tests assert the
measured features against analytic ground truth and exercise the degenerate /
boundary cases (empty range, flat spectrum, missing peaks, single point).
"""

from __future__ import annotations

from typing import Any

import fixtures as fx
import numpy as np
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.blocks.feature_extraction import (
    CalculateAUC,
    CalculateCentroid,
    CalculateRatio,
    ExtractIntensity,
    FindPeaks,
)
from scistudio_blocks_spectroscopy.types import Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.testing import BlockTestHarness


def _cfg(**params: object) -> BlockConfig:
    return BlockConfig(params=dict(params))


def _coll(*spectra: Spectrum) -> Collection:
    return Collection(list(spectra), item_type=Spectrum)


def _features(out: dict) -> Any:
    coll = out["features"]
    frame = next(iter(coll))
    assert isinstance(frame, DataFrame)
    return _support.dataframe_pandas(frame)


@pytest.mark.parametrize(
    "block_cls",
    [ExtractIntensity, CalculateAUC, CalculateCentroid, CalculateRatio, FindPeaks],
)
def test_block_validates(block_cls: type) -> None:
    assert not BlockTestHarness(block_cls).validate_block()


# ---------------------------------------------------------------------------
# ExtractIntensity (FR-088)
# ---------------------------------------------------------------------------


def test_extract_intensity_at_coordinate() -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="e1", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    out = ExtractIntensity().run({"spectra": _coll(spec)}, _cfg(target_coordinate=500.0))
    df = _features(out)
    assert list(df["spectrum_id"]) == ["e1"]
    assert df.iloc[0]["status"] == "ok"
    # Peak height at center == amplitude (5.0) within grid resolution.
    assert abs(float(df.iloc[0]["intensity"]) - 5.0) < 0.05
    assert abs(float(df.iloc[0]["measured_coordinate"]) - 500.0) < 1.0


def test_extract_intensity_one_row_per_spectrum() -> None:
    specs, _ = fx.make_collection(n=3)
    out = ExtractIntensity().run({"spectra": _support.spectra_collection(specs)}, _cfg(target_coordinate=500.0))
    df = _features(out)
    assert len(df) == 3
    assert list(df["spectrum_id"]) == ["spec_0", "spec_1", "spec_2"]


def test_extract_intensity_empty_spectrum_status() -> None:
    spec = _support.build_spectrum([], [], spectrum_id="empty")
    out = ExtractIntensity().run({"spectra": _coll(spec)}, _cfg(target_coordinate=500.0))
    df = _features(out)
    assert df.iloc[0]["status"] == "empty_spectrum"
    assert df.iloc[0]["intensity"] is None


def test_extract_intensity_range_max_reducer() -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="e2", peaks=(fx.PeakSpec("gaussian", 7.0, 500.0, 8.0),))
    out = ExtractIntensity().run({"spectra": _coll(spec)}, _cfg(lambda_min=480.0, lambda_max=520.0, reducer="max"))
    df = _features(out)
    assert abs(float(df.iloc[0]["intensity"]) - 7.0) < 0.05


# ---------------------------------------------------------------------------
# CalculateAUC (FR-089): area under the curve over a range
# ---------------------------------------------------------------------------


def test_auc_matches_analytic_gaussian_area() -> None:
    # Integrate a gaussian over a wide window ~ analytic area amp*sigma*sqrt(2pi).
    peak = fx.PeakSpec("gaussian", amplitude=5.0, center=500.0, sigma=8.0)
    spec, _ground = fx.make_peak_spectrum(spectrum_id="auc1", peaks=(peak,))
    out = CalculateAUC().run({"spectra": _coll(spec)}, _cfg(lambda_min=440.0, lambda_max=560.0))
    df = _features(out)
    assert df.iloc[0]["status"] == "ok"
    assert abs(float(df.iloc[0]["auc"]) - peak.area) < 0.5


def test_auc_empty_range_reports_status() -> None:
    spec, _ = fx.make_peak_spectrum()
    out = CalculateAUC().run({"spectra": _coll(spec)}, _cfg(lambda_min=2000.0, lambda_max=3000.0))
    df = _features(out)
    assert df.iloc[0]["status"] == "range_has_fewer_than_two_points"
    assert df.iloc[0]["auc"] is None


def test_auc_two_point_spectrum() -> None:
    spec = _support.build_spectrum([500.0, 510.0], [2.0, 4.0], spectrum_id="two")
    out = CalculateAUC().run({"spectra": _coll(spec)}, _cfg())
    df = _features(out)
    # Trapezoid of [2,4] over width 10 == 30.
    assert abs(float(df.iloc[0]["auc"]) - 30.0) < 1e-9


# ---------------------------------------------------------------------------
# CalculateCentroid (FR-090)
# ---------------------------------------------------------------------------


def test_centroid_of_symmetric_gaussian_at_center() -> None:
    spec, _ = fx.make_peak_spectrum(spectrum_id="c1", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    out = CalculateCentroid().run({"spectra": _coll(spec)}, _cfg(lambda_min=460.0, lambda_max=540.0))
    df = _features(out)
    assert df.iloc[0]["status"] == "ok"
    assert abs(float(df.iloc[0]["centroid_lambda"]) - 500.0) < 0.5


def test_centroid_empty_range_status() -> None:
    spec, _ = fx.make_peak_spectrum()
    out = CalculateCentroid().run({"spectra": _coll(spec)}, _cfg(lambda_min=2000.0, lambda_max=3000.0))
    df = _features(out)
    assert df.iloc[0]["status"] == "range_has_no_points"


def test_centroid_zero_intensity_denominator_status() -> None:
    spec = _support.build_spectrum(fx.DEFAULT_GRID, np.zeros_like(fx.DEFAULT_GRID), spectrum_id="zero")
    out = CalculateCentroid().run({"spectra": _coll(spec)}, _cfg(lambda_min=460.0, lambda_max=540.0))
    df = _features(out)
    assert df.iloc[0]["status"] == "zero_intensity_denominator"
    assert df.iloc[0]["centroid_lambda"] is None


# ---------------------------------------------------------------------------
# CalculateRatio (FR-091, FR-092): peak-to-peak ratio
# ---------------------------------------------------------------------------


def test_ratio_of_two_known_peaks() -> None:
    spec, _ground = fx.make_two_peak_spectrum(spectrum_id="r1", amp_a=6.0, center_a=470.0, amp_b=3.0, center_b=540.0)
    out = CalculateRatio().run(
        {"spectra": _coll(spec)},
        _cfg(
            numerator_peak={"coordinate": 470.0},
            denominator_peak={"coordinate": 540.0},
        ),
    )
    df = _features(out)
    assert df.iloc[0]["status"] == "ok"
    # True ratio is amp_a/amp_b == 2.0 (peaks well separated, minimal overlap).
    assert abs(float(df.iloc[0]["ratio"]) - 2.0) < 0.05


def test_ratio_zero_denominator_status() -> None:
    # Denominator coordinate sits in an exactly-zero region of the spectrum.
    lam = fx.DEFAULT_GRID
    inten = fx.gaussian(lam, 5.0, 470.0, 6.0)
    inten[np.argmin(np.abs(lam - 540.0))] = 0.0  # force an exact zero at the denom coord
    spec = _support.build_spectrum(lam, inten, spectrum_id="r2")
    out = CalculateRatio().run(
        {"spectra": _coll(spec)},
        _cfg(numerator_peak={"coordinate": 470.0}, denominator_peak={"coordinate": 540.0}),
    )
    df = _features(out)
    assert df.iloc[0]["status"] == "denominator_zero_or_unusable"
    assert df.iloc[0]["ratio"] is None


def test_ratio_window_reducer_peaks() -> None:
    spec, _ = fx.make_two_peak_spectrum(spectrum_id="r3", amp_a=8.0, center_a=470.0, amp_b=4.0, center_b=540.0)
    out = CalculateRatio().run(
        {"spectra": _coll(spec)},
        _cfg(
            numerator_peak={"lambda_min": 460.0, "lambda_max": 480.0, "reducer": "max"},
            denominator_peak={"lambda_min": 530.0, "lambda_max": 550.0, "reducer": "max"},
        ),
    )
    df = _features(out)
    assert abs(float(df.iloc[0]["ratio"]) - 2.0) < 0.1


# ---------------------------------------------------------------------------
# FindPeaks (FR-093)
# ---------------------------------------------------------------------------


def test_find_peaks_locates_known_center() -> None:
    pytest.importorskip("scipy")
    spec, _ = fx.make_peak_spectrum(spectrum_id="fp1", peaks=(fx.PeakSpec("gaussian", 5.0, 500.0, 8.0),))
    out = FindPeaks().run({"spectra": _coll(spec)}, _cfg(prominence=1.0))
    df = _features(out)
    assert df.iloc[0]["status"] == "ok"
    assert abs(float(df.iloc[0]["peak_coordinate"]) - 500.0) < 1.0


def test_find_peaks_none_found_status() -> None:
    pytest.importorskip("scipy")
    # Monotonic ramp has no interior peak.
    spec = _support.build_spectrum(fx.DEFAULT_GRID, np.linspace(0.0, 10.0, fx.DEFAULT_GRID.size), spectrum_id="ramp")
    out = FindPeaks().run({"spectra": _coll(spec)}, _cfg(prominence=1.0))
    df = _features(out)
    assert df.iloc[0]["status"] == "no_peaks_found"


def test_find_peaks_short_range_status() -> None:
    pytest.importorskip("scipy")
    spec, _ = fx.make_peak_spectrum()
    out = FindPeaks().run({"spectra": _coll(spec)}, _cfg(lambda_min=499.0, lambda_max=499.4))
    df = _features(out)
    assert df.iloc[0]["status"] == "range_has_fewer_than_three_points"
