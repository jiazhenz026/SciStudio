from __future__ import annotations

import math

import pytest
from _test_support import install_type_shim

install_type_shim()

from _test_support import make_spectral_dataset, make_spectrum, spectrum_collection, table_rows  # noqa: E402
from scistudio_blocks_spectroscopy.blocks.feature_extraction import (  # noqa: E402
    CalculateAUC,
    CalculateCentroid,
    CalculateRatio,
    ExtractIntensity,
    FindPeaks,
)

from scistudio.core.types.collection import Collection  # noqa: E402
from scistudio.core.types.dataframe import DataFrame  # noqa: E402
from scistudio.testing import BlockTestHarness  # noqa: E402


@pytest.mark.parametrize(
    "block_cls",
    [ExtractIntensity, CalculateAUC, CalculateCentroid, CalculateRatio, FindPeaks],
)
def test_feature_block_contracts(block_cls: type) -> None:
    errors = BlockTestHarness(block_cls).validate_block()
    assert not errors, errors


def test_extract_intensity_interpolates_target_coordinate() -> None:
    spectrum = make_spectrum("s1", [0.0, 10.0], [1.0, 3.0])
    block = ExtractIntensity(config={"params": {"target_lambda": 5.0, "interpolation": "linear"}})

    result = block.run({"spectra": spectrum_collection(spectrum)}, block.config)

    rows = table_rows(result["features"])
    assert rows == [
        {
            "spectrum_id": "s1",
            "measured_lambda": 5.0,
            "intensity": 2.0,
            "status": "success",
        }
    ]
    assert isinstance(result["features"], Collection)
    assert result["features"].item_type is DataFrame


def test_extract_intensity_reports_missing_coordinate_without_interpolation() -> None:
    spectrum = make_spectrum("s1", [0.0, 10.0], [1.0, 3.0])
    block = ExtractIntensity(config={"params": {"target_lambda": 5.0, "interpolation": "none"}})

    rows = table_rows(block.run({"spectra": spectrum_collection(spectrum)}, block.config)["features"])

    assert rows[0]["status"] == "missing_coordinate"
    assert rows[0]["intensity"] is None


def test_calculate_auc_uses_interpolated_integration_window() -> None:
    spectrum = make_spectrum("s1", [0.0, 5.0, 10.0], [0.0, 10.0, 0.0])
    block = CalculateAUC(config={"params": {"lambda_min": 2.5, "lambda_max": 7.5}})

    rows = table_rows(block.run({"spectra": spectrum_collection(spectrum)}, block.config)["features"])

    assert rows[0]["status"] == "success"
    assert math.isclose(rows[0]["auc"], 37.5)


def test_calculate_auc_reports_empty_range() -> None:
    spectrum = make_spectrum("s1", [0.0, 1.0], [2.0, 2.0])
    block = CalculateAUC(config={"params": {"lambda_min": 10.0, "lambda_max": 20.0}})

    rows = table_rows(block.run({"spectra": spectrum_collection(spectrum)}, block.config)["features"])

    assert rows[0]["status"] == "empty_range"
    assert rows[0]["auc"] is None


def test_calculate_centroid_reports_unusable_denominator_for_flat_zero_signal() -> None:
    spectrum = make_spectrum("s1", [0.0, 1.0, 2.0], [0.0, 0.0, 0.0])
    block = CalculateCentroid(config={"params": {"lambda_min": 0.0, "lambda_max": 2.0}})

    rows = table_rows(block.run({"spectra": spectrum_collection(spectrum)}, block.config)["features"])

    assert rows[0]["status"] == "unusable_denominator"
    assert rows[0]["centroid_lambda"] is None


def test_calculate_centroid_computes_weighted_center() -> None:
    spectrum = make_spectrum("s1", [0.0, 5.0, 10.0], [0.0, 10.0, 0.0])
    block = CalculateCentroid(config={"params": {"lambda_min": 0.0, "lambda_max": 10.0}})

    rows = table_rows(block.run({"spectra": spectrum_collection(spectrum)}, block.config)["features"])

    assert rows[0]["status"] == "success"
    assert math.isclose(rows[0]["centroid_lambda"], 5.0)


def test_calculate_ratio_reports_zero_denominator() -> None:
    spectrum = make_spectrum("s1", [0.0, 5.0, 10.0], [0.0, 4.0, 8.0])
    block = CalculateRatio(config={"params": {"numerator_peak": 10.0, "denominator_peak": 0.0}})

    rows = table_rows(block.run({"spectra": spectrum_collection(spectrum)}, block.config)["features"])

    assert rows[0]["status"] == "zero_denominator"
    assert rows[0]["ratio"] is None
    assert rows[0]["numerator_intensity"] == 8.0
    assert rows[0]["denominator_intensity"] == 0.0


def test_find_peaks_selects_highest_peak_inside_bounds() -> None:
    spectrum = make_spectrum("s1", [0, 1, 2, 3, 4], [0, 2, 0, 3, 0])
    block = FindPeaks(config={"params": {"lambda_min": 0.0, "lambda_max": 2.5}})

    rows = table_rows(block.run({"spectra": spectrum_collection(spectrum)}, block.config)["features"])

    assert rows[0]["status"] == "success"
    assert rows[0]["peak_lambda"] == 1.0
    assert rows[0]["peak_intensity"] == 2.0
    assert rows[0]["peak_count"] == 1


def test_find_peaks_reports_no_peaks_for_flat_spectrum() -> None:
    spectrum = make_spectrum("flat", [0, 1, 2, 3], [5, 5, 5, 5])
    block = FindPeaks()

    rows = table_rows(block.run({"spectra": spectrum_collection(spectrum)}, block.config)["features"])

    assert rows[0]["status"] == "no_peaks"
    assert rows[0]["peak_lambda"] is None


def test_feature_blocks_reject_spectral_dataset_direct_input() -> None:
    block = ExtractIntensity(config={"params": {"target_lambda": 1.0}})

    with pytest.raises(TypeError, match="Collection\\[Spectrum\\]"):
        block.run({"spectra": make_spectral_dataset()}, block.config)  # type: ignore[arg-type]
