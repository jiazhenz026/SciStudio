from __future__ import annotations

import numpy as np
import pyarrow as pa
import pytest
from scistudio_blocks_spectroscopy.blocks.preprocessing import (
    ALIGNMENT_METHODS,
    BASELINE_METHODS,
    NORMALIZATION_METHODS,
    PEAK_COMPONENT_MODELS,
    SMOOTHING_METHODS,
    AlignAndResampleSpectra,
    BaselineCorrection,
    CropSpectrumRange,
    NormalizeSpectrum,
    ShiftSpectralAxis,
    SmoothSpectrum,
    SubtractPeakComponent,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame


def _spectrum(
    spectrum_id: str,
    lambda_values: list[float] | np.ndarray,
    intensities: list[float] | np.ndarray,
) -> Spectrum:
    lambda_arr = np.asarray(lambda_values, dtype=np.float64)
    intensity_arr = np.asarray(intensities, dtype=np.float64)
    table = pa.table(
        {
            "lambda": pa.array(lambda_arr, type=pa.float64()),
            "intensity": pa.array(intensity_arr, type=pa.float64()),
        }
    )
    return Spectrum(
        length=len(lambda_arr),
        meta=Spectrum.Meta(
            spectrum_id=spectrum_id,
            lambda_unit="cm^-1",
            intensity_unit="a.u.",
            lambda_kind="raman_shift",
            modality="raman",
            source_file=f"{spectrum_id}.txt",
        ),
        user={"spectrum_id": spectrum_id, "batch": "A"},
        data=table,
    )


def _collection(*spectra: Spectrum) -> Collection:
    return Collection(list(spectra), item_type=Spectrum)


def _arrays(spectrum: Spectrum) -> tuple[np.ndarray, np.ndarray]:
    table = spectrum.get_in_memory_data()
    assert isinstance(table, pa.Table)
    return (
        table.column("lambda").combine_chunks().to_numpy(zero_copy_only=False),
        table.column("intensity").combine_chunks().to_numpy(zero_copy_only=False),
    )


def _table(df: DataFrame) -> pa.Table:
    table = df.get_in_memory_data()
    assert isinstance(table, pa.Table)
    return table


def test_preprocessing_block_contracts_reject_spectral_dataset() -> None:
    blocks = [
        CropSpectrumRange,
        ShiftSpectralAxis,
        BaselineCorrection,
        SmoothSpectrum,
        AlignAndResampleSpectra,
        NormalizeSpectrum,
        SubtractPeakComponent,
    ]
    for block_cls in blocks:
        accepted = block_cls.input_ports[0].accepted_types
        assert accepted == [Spectrum]
        assert SpectralDataset not in accepted
        with pytest.raises(ValueError, match=r"SpectralDataset|expected"):
            block_cls().validate({"spectra": SpectralDataset()})


def test_method_enums_match_spec() -> None:
    assert BASELINE_METHODS == ("polynomial", "asls", "arpls", "airpls")
    assert SMOOTHING_METHODS == ("savitzky_golay", "moving_average", "gaussian", "median")
    assert ALIGNMENT_METHODS == ("none", "peak_fit", "cross_correlation")
    assert NORMALIZATION_METHODS == ("max", "minmax")
    assert PEAK_COMPONENT_MODELS == ("gaussian", "lorentzian", "voigt")
    assert "min" not in NormalizeSpectrum.config_schema["properties"]["method"]["enum"]


def test_crop_and_shift_preserve_identity_order_metadata_and_intensities() -> None:
    first = _spectrum("s1", [5, 1, 3, 3], [50, 10, 30, 31])
    second = _spectrum("s2", [0, 2, 4], [1, 2, 3])
    cropped = CropSpectrumRange().run(
        {"spectra": _collection(first, second)},
        BlockConfig(params={"lambda_min": 2.0, "lambda_max": 3.0}),
    )["cropped"]
    assert [item.meta.spectrum_id for item in cropped] == ["s1", "s2"]
    np.testing.assert_array_equal(_arrays(cropped[0])[0], np.array([3.0, 3.0]))
    np.testing.assert_array_equal(_arrays(cropped[0])[1], np.array([30.0, 31.0]))
    np.testing.assert_array_equal(_arrays(cropped[1])[0], np.array([2.0]))
    assert cropped[0].meta == first.meta
    assert cropped[0].user == first.user

    shifted = ShiftSpectralAxis().run({"spectra": first}, BlockConfig(params={"shift": -1.5}))["shifted"]
    assert len(shifted) == 1
    np.testing.assert_array_equal(_arrays(shifted[0])[0], np.array([3.5, -0.5, 1.5, 1.5]))
    np.testing.assert_array_equal(_arrays(shifted[0])[1], np.array([50.0, 10.0, 30.0, 31.0]))


def test_crop_empty_range_returns_empty_spectrum() -> None:
    result = CropSpectrumRange().run(
        {"spectra": _collection(_spectrum("s1", [1, 2], [3, 4]))},
        BlockConfig(params={"lambda_min": 10.0, "lambda_max": 20.0}),
    )["cropped"][0]
    lambda_values, intensities = _arrays(result)
    assert lambda_values.size == 0
    assert intensities.size == 0
    assert result.meta.spectrum_id == "s1"


@pytest.mark.parametrize("method", SMOOTHING_METHODS)
def test_smoothing_handles_small_windows_duplicates_and_preserves_grid(method: str) -> None:
    spectrum = _spectrum("s1", [4, 1, 2, 2, 3], [9, 1, 4, 5, 7])
    result = SmoothSpectrum().run(
        {"spectra": _collection(spectrum)},
        BlockConfig(params={"method": method, "window": 2, "polyorder": 1, "sigma": 0.75}),
    )["smoothed"][0]
    lambda_values, intensities = _arrays(result)
    np.testing.assert_array_equal(lambda_values, np.array([4.0, 1.0, 2.0, 2.0, 3.0]))
    assert intensities.shape == (5,)
    assert np.all(np.isfinite(intensities))
    assert result.meta.spectrum_id == "s1"


def test_normalize_handles_zero_norms_without_nan() -> None:
    spectrum = _spectrum("zero", [1, 2, 3], [0, 0, 0])
    for method in NORMALIZATION_METHODS:
        result = NormalizeSpectrum().run({"spectra": _collection(spectrum)}, BlockConfig(params={"method": method}))[
            "normalized"
        ][0]
        np.testing.assert_array_equal(_arrays(result)[1], np.zeros(3))


@pytest.mark.parametrize("method", BASELINE_METHODS)
def test_baseline_correction_outputs_curves_and_diagnostics(method: str) -> None:
    lambda_values = np.linspace(0, 10, 25)
    baseline = 2.0 + 0.1 * lambda_values
    peak = 5.0 * np.exp(-0.5 * ((lambda_values - 5.0) / 0.6) ** 2)
    spectrum = _spectrum("s1", lambda_values, baseline + peak)
    result = BaselineCorrection().run(
        {"spectra": _collection(spectrum)},
        BlockConfig(params={"method": method, "polynomial_order": 1, "max_iterations": 8, "lambda_smoothness": 100.0}),
    )
    assert set(result) == {"corrected", "baseline", "fit_diagnostics"}
    assert len(result["corrected"]) == 1
    assert len(result["baseline"]) == 1
    np.testing.assert_array_equal(_arrays(result["baseline"][0])[0], lambda_values)
    diagnostics = _table(result["fit_diagnostics"]).to_pydict()
    assert diagnostics["spectrum_id"] == ["s1"]
    assert diagnostics["method"] == [method]
    assert diagnostics["status"][0] in {"ok", "empty_input", "no_finite_points"}
    assert isinstance(diagnostics["converged"][0], bool)


def test_align_and_resample_supports_range_step_and_cross_correlation() -> None:
    target = np.linspace(-2, 2, 9)
    reference = _spectrum("ref", target, np.exp(-0.5 * (target / 0.4) ** 2))
    shifted_lambda = target + 1.0
    shifted = _spectrum("sample", shifted_lambda, np.exp(-0.5 * ((shifted_lambda - 1.0) / 0.4) ** 2))
    result = AlignAndResampleSpectra().run(
        {"spectra": _collection(reference, shifted)},
        BlockConfig(
            params={
                "alignment_method": "cross_correlation",
                "target_grid_mode": "range_step",
                "lambda_min": -2.0,
                "lambda_max": 2.0,
                "step": 0.5,
                "reference_index": 0,
            }
        ),
    )
    assert set(result) == {"aligned", "fit_curves", "fit_diagnostics"}
    assert len(result["aligned"]) == 2
    np.testing.assert_array_equal(_arrays(result["aligned"][0])[0], target)
    np.testing.assert_allclose(_arrays(result["aligned"][0])[1], _arrays(result["aligned"][1])[1], atol=0.2)
    diagnostics = _table(result["fit_diagnostics"]).to_pydict()
    assert diagnostics["alignment_method"] == ["cross_correlation", "cross_correlation"]
    assert abs(diagnostics["applied_shift"][1] - 1.0) <= 0.5


def test_align_peak_fit_emits_fit_curve_collection_even_for_single_spectrum() -> None:
    lambda_values = np.linspace(-2, 2, 9)
    spectrum = _spectrum("single", lambda_values, np.exp(-0.5 * (lambda_values / 0.5) ** 2))
    result = AlignAndResampleSpectra().run(
        {"spectra": spectrum},
        BlockConfig(params={"alignment_method": "peak_fit", "target_grid_mode": "first_spectrum"}),
    )
    assert len(result["aligned"]) == 1
    assert len(result["fit_curves"]) == 1
    assert np.max(_arrays(result["fit_curves"][0])[1]) > 0.0
    diagnostics = _table(result["fit_diagnostics"]).to_pydict()
    assert diagnostics["status"] == ["ok"]


@pytest.mark.parametrize("model", PEAK_COMPONENT_MODELS)
def test_subtract_peak_component_outputs_component_and_fwhm(model: str) -> None:
    lambda_values = np.linspace(-4, 4, 41)
    component = 3.0 * np.exp(-0.5 * (lambda_values / 0.7) ** 2)
    spectrum = _spectrum("s1", lambda_values, component + 1.0)
    result = SubtractPeakComponent().run(
        {"spectra": _collection(spectrum)},
        BlockConfig(params={"model": model, "center": 0.0, "width": 0.7, "eta": 0.4}),
    )
    assert set(result) == {"corrected", "component", "fit_diagnostics"}
    assert len(result["corrected"]) == 1
    assert len(result["component"]) == 1
    assert np.max(_arrays(result["corrected"][0])[1]) < np.max(_arrays(spectrum)[1])
    diagnostics = _table(result["fit_diagnostics"]).to_pydict()
    assert diagnostics["model"] == [model]
    assert diagnostics["fwhm"][0] > 0.0
    assert diagnostics["area"][0] > 0.0
