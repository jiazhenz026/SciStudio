from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pyarrow as pa
import pytest
from scistudio_blocks_spectroscopy import (
    AlignAndResampleSpectra,
    AttachFeaturesToSpectralDataset,
    BaselineCorrection,
    CalculateAUC,
    CalculateCentroid,
    CalculateRatio,
    CropSpectrumRange,
    DivideByReferenceSpectrum,
    ExtractIntensity,
    FilterSpectralDataset,
    FindPeaks,
    FitPeak,
    LoadSpectralDataset,
    LoadSpectrum,
    MatchSpectralLibrary,
    MergeSpectralDataset,
    NormalizeSpectrum,
    SaveSpectralDataset,
    SaveSpectrum,
    ShiftSpectralAxis,
    SmoothSpectrum,
    SpectralDataset,
    SpectralDatasetToSpectrum,
    SpectralUnmixing,
    Spectrum,
    SpectrumToSpectralDataset,
    SubtractPeakComponent,
    SubtractReferenceSpectrum,
)
from scistudio_blocks_spectroscopy._tables import dataframe_from_pandas, to_pandas_frame

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame

SPECTRUM_JSON_CAPABILITY = "scistudio-blocks-spectroscopy.spectrum.spectrum_json.save"
DATASET_JSON_CAPABILITY = "scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.save"


def _config(params: dict[str, Any] | None = None) -> BlockConfig:
    return BlockConfig(params=params or {})


def _write_spectrum_csv(
    path: Path,
    spectrum_id: str,
    lambdas: list[float],
    intensities: list[float],
    *,
    lambda_unit: str = "cm^-1",
    intensity_unit: str = "counts",
    modality: str = "raman",
    sample_label: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "spectrum_id": spectrum_id,
        "lambda_unit": lambda_unit,
        "intensity_unit": intensity_unit,
        "modality": modality,
        "sample_label": sample_label,
    }
    lines = [f"# {key}: {value}" for key, value in metadata.items() if value is not None]
    lines.append("lambda,intensity")
    lines.extend(f"{lambda_value},{intensity}" for lambda_value, intensity in zip(lambdas, intensities, strict=True))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _load_spectra(paths: list[Path]) -> Collection:
    loaded = LoadSpectrum().load(_config({"path": [str(path) for path in paths]}))
    assert isinstance(loaded, Collection)
    assert loaded.item_type is Spectrum
    assert len(loaded) == len(paths)
    return loaded


def _load_spectrum(
    tmp_path: Path,
    spectrum_id: str,
    lambdas: list[float],
    intensities: list[float],
    *,
    filename: str | None = None,
    lambda_unit: str = "cm^-1",
    intensity_unit: str = "counts",
    modality: str = "raman",
) -> Collection:
    source = _write_spectrum_csv(
        tmp_path / (filename or f"{spectrum_id}.csv"),
        spectrum_id,
        lambdas,
        intensities,
        lambda_unit=lambda_unit,
        intensity_unit=intensity_unit,
        modality=modality,
    )
    return _load_spectra([source])


def _dataset_index_frame(ids: list[str], *, materials: list[str] | None = None) -> pd.DataFrame:
    materials = materials or [f"material-{index + 1}" for index in range(len(ids))]
    return pd.DataFrame(
        {
            "spectrum_id": ids,
            "material": materials,
            "lambda_unit": ["cm^-1"] * len(ids),
            "intensity_unit": ["counts"] * len(ids),
            "modality": ["raman"] * len(ids),
        },
        columns=["spectrum_id", "material", "lambda_unit", "intensity_unit", "modality"],
    )


def _dataset_spectra_frame(ids: list[str], *, offset: float = 0.0) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for ordinal, spectrum_id in enumerate(ids):
        for lambda_value, intensity in zip([100.0, 101.0, 102.0], [1.0, 3.0, 2.0], strict=True):
            rows.append(
                {
                    "spectrum_id": spectrum_id,
                    "lambda": lambda_value,
                    "intensity": intensity + offset + float(ordinal),
                }
            )
    return pd.DataFrame(rows, columns=["spectrum_id", "lambda", "intensity"])


def _load_dataset(
    tmp_path: Path,
    label: str,
    *,
    ids: list[str],
    materials: list[str] | None = None,
    offset: float = 0.0,
) -> SpectralDataset:
    index = _dataset_index_frame(ids, materials=materials)
    spectra = _dataset_spectra_frame(ids, offset=offset)
    index_path = tmp_path / f"{label}.index.csv"
    spectra_path = tmp_path / f"{label}.spectra.csv"
    index.to_csv(index_path, index=False)
    spectra.to_csv(spectra_path, index=False)
    dataset = LoadSpectralDataset().load(
        _config(
            {
                "index_path": str(index_path),
                "spectra_path": str(spectra_path),
                "dataset_name": label,
            }
        )
    )
    assert isinstance(dataset, SpectralDataset)
    return dataset


def _empty_library_dataset() -> SpectralDataset:
    return SpectralDataset(
        slots={
            "index": dataframe_from_pandas(_dataset_index_frame([])),
            "spectra": dataframe_from_pandas(pd.DataFrame(columns=["spectrum_id", "lambda", "intensity"])),
        },
        meta=SpectralDataset.Meta(dataset_name="empty-library", lambda_unit="cm^-1", intensity_unit="counts"),
    )


def _dataset_collection(dataset: SpectralDataset) -> Collection:
    return Collection(items=[dataset], item_type=SpectralDataset)


def _dataframe_collection(frame: pd.DataFrame) -> Collection:
    return Collection(items=[dataframe_from_pandas(frame)], item_type=DataFrame)


def _spectrum_frame(spectrum: Spectrum) -> pd.DataFrame:
    data = spectrum.get_in_memory_data()
    if isinstance(data, pa.Table):
        frame = data.to_pandas()
    elif isinstance(data, pd.DataFrame):
        frame = data.copy()
    else:
        frame = pd.DataFrame(data)
    return frame[["lambda", "intensity"]].reset_index(drop=True)


def _dataframe_frame(table: DataFrame) -> pd.DataFrame:
    return to_pandas_frame(table).reset_index(drop=True)


def _save_dataframe_output(table: DataFrame, tmp_path: Path, label: str) -> pd.DataFrame:
    frame = _dataframe_frame(table)
    target = tmp_path / f"{label}.csv"
    frame.to_csv(target, index=False)
    assert target.read_text(encoding="utf-8").splitlines()[0] == ",".join(frame.columns)
    return pd.read_csv(target)


def _roundtrip_spectra(collection: Collection, tmp_path: Path, label: str) -> Collection:
    target = tmp_path / f"{label}.spectrum.json"
    if len(collection) == 1:
        SaveSpectrum().save(
            collection,
            _config({"path": str(target), "capability_id": SPECTRUM_JSON_CAPABILITY}),
        )
        reloaded = LoadSpectrum().load(_config({"path": str(target)}))
    else:
        target_dir = tmp_path / label
        SaveSpectrum().save(collection, _config({"path": str(target_dir), "format": "spectrum_json"}))
        reloaded = LoadSpectrum().load(_config({"path": str(target_dir)}))
    assert isinstance(reloaded, Collection)
    assert reloaded.item_type is Spectrum
    assert len(reloaded) == len(collection)
    return reloaded


def _roundtrip_dataset(dataset: SpectralDataset, tmp_path: Path, label: str) -> SpectralDataset:
    target = tmp_path / f"{label}.spectraldataset.json"
    SaveSpectralDataset().save(
        dataset,
        _config({"path": str(target), "capability_id": DATASET_JSON_CAPABILITY}),
    )
    assert target.is_file()
    assert target.with_suffix("").with_name(f"{target.with_suffix('').name}.index.csv").is_file()
    assert target.with_suffix("").with_name(f"{target.with_suffix('').name}.spectra.csv").is_file()
    reloaded = LoadSpectralDataset().load(_config({"path": str(target)}))
    assert isinstance(reloaded, SpectralDataset)
    return reloaded


def _assert_spectrum_meta(spectrum: Spectrum, spectrum_id: str) -> None:
    assert isinstance(spectrum.meta, Spectrum.Meta)
    assert spectrum.meta.lambda_unit == "cm^-1"
    assert spectrum.meta.intensity_unit == "counts"
    assert spectrum.meta.modality == "raman"
    assert spectrum.user["spectrum_id"] == spectrum_id


def _assert_dataset_meta(dataset: SpectralDataset, dataset_name: str) -> None:
    assert isinstance(dataset.meta, SpectralDataset.Meta)
    assert dataset.meta.dataset_name == dataset_name


def test_e2e_load_spectrum_loads_pseudo_spectrum_then_package_save_roundtrips(tmp_path: Path) -> None:
    source = _write_spectrum_csv(
        tmp_path / "load-spectrum.csv",
        "load-spectrum",
        [100.0, 101.0, 102.0],
        [1.0, 4.0, 9.0],
    )

    loaded = LoadSpectrum().load(_config({"path": str(source)}))

    assert len(loaded) == 1
    _assert_spectrum_meta(loaded[0], "load-spectrum")
    pdt.assert_frame_equal(
        _spectrum_frame(loaded[0]),
        pd.DataFrame({"lambda": [100.0, 101.0, 102.0], "intensity": [1.0, 4.0, 9.0]}),
    )
    reloaded = _roundtrip_spectra(loaded, tmp_path, "load-spectrum-output")
    _assert_spectrum_meta(reloaded[0], "load-spectrum")


def test_e2e_save_spectrum_persists_loaded_spectrum_for_reload(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "save-spectrum", [100.0, 101.0], [2.0, 5.0])
    target = tmp_path / "saved.spectrum.json"

    SaveSpectrum().save(
        spectra,
        _config({"path": str(target), "capability_id": SPECTRUM_JSON_CAPABILITY}),
    )

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["type"] == "Spectrum"
    assert payload["user"]["spectrum_id"] == "save-spectrum"
    assert payload["meta"]["lambda_unit"] == "cm^-1"
    reloaded = LoadSpectrum().load(_config({"path": str(target)}))
    _assert_spectrum_meta(reloaded[0], "save-spectrum")
    pdt.assert_frame_equal(_spectrum_frame(reloaded[0]), _spectrum_frame(spectra[0]))


def test_e2e_load_spectral_dataset_loads_two_table_fixture_then_package_save_roundtrips(tmp_path: Path) -> None:
    dataset = _load_dataset(
        tmp_path,
        "load-dataset",
        ids=["ds-a", "ds-b"],
        materials=["cell", "buffer"],
    )

    _assert_dataset_meta(dataset, "load-dataset")
    assert to_pandas_frame(dataset.index)["spectrum_id"].tolist() == ["ds-a", "ds-b"]
    assert len(to_pandas_frame(dataset.spectra)) == 6
    reloaded = _roundtrip_dataset(dataset, tmp_path, "load-dataset-output")
    _assert_dataset_meta(reloaded, "load-dataset")
    pdt.assert_frame_equal(to_pandas_frame(reloaded.index), to_pandas_frame(dataset.index))
    pdt.assert_frame_equal(to_pandas_frame(reloaded.spectra), to_pandas_frame(dataset.spectra))


def test_e2e_save_spectral_dataset_persists_manifest_with_sidecars(tmp_path: Path) -> None:
    dataset = _load_dataset(tmp_path, "save-dataset", ids=["save-a", "save-b"])
    target = tmp_path / "saved.spectraldataset.json"

    SaveSpectralDataset().save(
        dataset,
        _config({"path": str(target), "capability_id": DATASET_JSON_CAPABILITY}),
    )

    manifest = json.loads(target.read_text(encoding="utf-8"))
    assert manifest["type"] == "SpectralDataset"
    assert manifest["meta"]["dataset_name"] == "save-dataset"
    assert manifest["slots"] == {
        "index": "saved.spectraldataset.index.csv",
        "spectra": "saved.spectraldataset.spectra.csv",
    }
    reloaded = LoadSpectralDataset().load(_config({"path": str(target)}))
    _assert_dataset_meta(reloaded, "save-dataset")
    assert to_pandas_frame(reloaded.index)["spectrum_id"].tolist() == ["save-a", "save-b"]


def test_e2e_spectrum_to_spectral_dataset_loads_spectra_joins_metadata_and_saves_dataset(tmp_path: Path) -> None:
    paths = [
        _write_spectrum_csv(tmp_path / "join-a.csv", "join-a", [100.0, 101.0], [1.0, 2.0]),
        _write_spectrum_csv(tmp_path / "join-b.csv", "join-b", [100.0, 101.0], [3.0, 4.0]),
    ]
    spectra = _load_spectra(paths)
    metadata = _dataframe_collection(
        pd.DataFrame({"spectrum_id": ["join-a", "join-b"], "condition": ["drug", "control"]})
    )

    outputs = SpectrumToSpectralDataset().run(
        {"spectra": spectra, "metadata": metadata},
        _config({"dataset_name": "joined-dataset", "dataset_role": "experiment"}),
    )

    dataset = outputs["dataset"][0]
    reloaded = _roundtrip_dataset(dataset, tmp_path, "joined-dataset")
    _assert_dataset_meta(reloaded, "joined-dataset")
    index = to_pandas_frame(reloaded.index)
    assert index["spectrum_id"].tolist() == ["join-a", "join-b"]
    assert index["condition"].tolist() == ["drug", "control"]
    assert len(to_pandas_frame(reloaded.spectra)) == 4


def test_e2e_spectral_dataset_to_spectrum_splits_loaded_dataset_and_saves_spectra(tmp_path: Path) -> None:
    dataset = _load_dataset(tmp_path, "split-dataset", ids=["split-a", "split-b"])

    outputs = SpectralDatasetToSpectrum().run({"dataset": _dataset_collection(dataset)}, _config())

    reloaded = _roundtrip_spectra(outputs["spectra"], tmp_path, "split-spectra")
    assert [spectrum.user["spectrum_id"] for spectrum in reloaded] == ["split-a", "split-b"]
    _assert_spectrum_meta(reloaded[0], "split-a")
    assert _spectrum_frame(reloaded[0])["lambda"].tolist() == [100.0, 101.0, 102.0]


def test_e2e_filter_spectral_dataset_can_save_empty_boundary_dataset(tmp_path: Path) -> None:
    dataset = _load_dataset(
        tmp_path,
        "filter-dataset",
        ids=["filter-a", "filter-b"],
        materials=["cell", "buffer"],
    )

    outputs = FilterSpectralDataset().run(
        {"dataset": _dataset_collection(dataset)},
        _config({"filters": {"material": "absent"}}),
    )

    filtered = _roundtrip_dataset(outputs["dataset"][0], tmp_path, "filter-empty")
    _assert_dataset_meta(filtered, "filter-dataset")
    assert filtered.user["filtered"] is True
    assert to_pandas_frame(filtered.index).empty
    assert to_pandas_frame(filtered.spectra).empty
    assert list(to_pandas_frame(filtered.index).columns) == [
        "spectrum_id",
        "material",
        "lambda_unit",
        "intensity_unit",
        "modality",
    ]


def test_e2e_merge_spectral_dataset_prefixes_duplicate_ids_and_saves(tmp_path: Path) -> None:
    left = _load_dataset(tmp_path, "merge-left", ids=["dup"], materials=["left"])
    right = _load_dataset(tmp_path, "merge-right", ids=["dup", "unique"], materials=["right", "other"], offset=10.0)

    outputs = MergeSpectralDataset().run(
        {"datasets": Collection(items=[left, right], item_type=SpectralDataset)},
        _config({"duplicate_id_policy": "prefix"}),
    )

    merged = _roundtrip_dataset(outputs["dataset"][0], tmp_path, "merge-output")
    ids = to_pandas_frame(merged.index)["spectrum_id"].tolist()
    assert ids == ["dup", "ds2_dup", "ds2_unique"]
    assert sorted(to_pandas_frame(merged.spectra)["spectrum_id"].unique().tolist()) == sorted(ids)
    assert isinstance(merged.meta, SpectralDataset.Meta)
    assert merged.meta.lambda_unit is None


def test_e2e_attach_features_to_spectral_dataset_saves_joined_index(tmp_path: Path) -> None:
    dataset = _load_dataset(tmp_path, "attach-dataset", ids=["attach-a", "attach-b"])
    original_spectra = to_pandas_frame(dataset.spectra)
    features = _dataframe_collection(pd.DataFrame({"spectrum_id": ["attach-a", "attach-b"], "peak_area": [3.5, 7.0]}))

    outputs = AttachFeaturesToSpectralDataset().run(
        {"dataset": _dataset_collection(dataset), "features": features},
        _config(),
    )

    attached = _roundtrip_dataset(outputs["dataset"][0], tmp_path, "attach-output")
    index = to_pandas_frame(attached.index)
    assert index["peak_area"].tolist() == [3.5, 7.0]
    pdt.assert_frame_equal(to_pandas_frame(attached.spectra), original_spectra)
    _assert_dataset_meta(attached, "attach-dataset")


def test_e2e_crop_spectrum_range_saves_cropped_output(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "crop-a", [100.0, 101.0, 102.0, 103.0], [0.0, 2.0, 4.0, 8.0])

    outputs = CropSpectrumRange().run(
        {"spectra": spectra},
        _config({"lambda_min": 101.0, "lambda_max": 102.0}),
    )

    reloaded = _roundtrip_spectra(outputs["cropped"], tmp_path, "crop-output")
    _assert_spectrum_meta(reloaded[0], "crop-a")
    pdt.assert_frame_equal(
        _spectrum_frame(reloaded[0]),
        pd.DataFrame({"lambda": [101.0, 102.0], "intensity": [2.0, 4.0]}),
    )


def test_e2e_shift_spectral_axis_saves_shifted_coordinates(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "shift-a", [100.0, 101.0, 102.0], [1.0, 2.0, 3.0])

    outputs = ShiftSpectralAxis().run({"spectra": spectra}, _config({"shift": 2.5}))

    reloaded = _roundtrip_spectra(outputs["shifted"], tmp_path, "shift-output")
    _assert_spectrum_meta(reloaded[0], "shift-a")
    np.testing.assert_allclose(_spectrum_frame(reloaded[0])["lambda"], [102.5, 103.5, 104.5])
    np.testing.assert_allclose(_spectrum_frame(reloaded[0])["intensity"], [1.0, 2.0, 3.0])


def test_e2e_baseline_correction_handles_flat_baseline_and_saves_curves(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "baseline-flat", [100.0, 101.0, 102.0, 103.0], [5.0, 5.0, 5.0, 5.0])

    outputs = BaselineCorrection().run(
        {"spectra": spectra},
        _config({"method": "polynomial", "polynomial_order": 0}),
    )

    corrected = _roundtrip_spectra(outputs["corrected"], tmp_path, "baseline-corrected")
    baseline = _roundtrip_spectra(outputs["baseline"], tmp_path, "baseline-curve")
    diagnostics = _save_dataframe_output(outputs["fit_diagnostics"], tmp_path, "baseline-diagnostics")
    _assert_spectrum_meta(corrected[0], "baseline-flat")
    np.testing.assert_allclose(_spectrum_frame(corrected[0])["intensity"], [0.0, 0.0, 0.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(_spectrum_frame(baseline[0])["intensity"], [5.0, 5.0, 5.0, 5.0], atol=1e-12)
    assert diagnostics.loc[0, "status"] == "ok"
    assert diagnostics.loc[0, "converged"] in {True, np.True_}


def test_e2e_smooth_spectrum_saves_tiny_single_point_output(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "smooth-tiny", [100.0], [7.0])

    outputs = SmoothSpectrum().run(
        {"spectra": spectra},
        _config({"method": "moving_average", "window": 5}),
    )

    reloaded = _roundtrip_spectra(outputs["smoothed"], tmp_path, "smooth-output")
    _assert_spectrum_meta(reloaded[0], "smooth-tiny")
    pdt.assert_frame_equal(
        _spectrum_frame(reloaded[0]),
        pd.DataFrame({"lambda": [100.0], "intensity": [7.0]}),
    )


def test_e2e_align_and_resample_spectra_saves_aligned_and_fit_curve_outputs(tmp_path: Path) -> None:
    paths = [
        _write_spectrum_csv(tmp_path / "align-a.csv", "align-a", [100.0, 102.0], [0.0, 4.0]),
        _write_spectrum_csv(tmp_path / "align-b.csv", "align-b", [100.0, 101.0, 102.0], [1.0, 3.0, 5.0]),
    ]
    spectra = _load_spectra(paths)

    outputs = AlignAndResampleSpectra().run(
        {"spectra": spectra},
        _config({"alignment_method": "none", "target_grid_mode": "explicit", "target_grid": [100.0, 101.0, 102.0]}),
    )

    aligned = _roundtrip_spectra(outputs["aligned"], tmp_path, "align-output")
    fit_curves = _roundtrip_spectra(outputs["fit_curves"], tmp_path, "align-fit-curves")
    diagnostics = _save_dataframe_output(outputs["fit_diagnostics"], tmp_path, "align-diagnostics")
    _assert_spectrum_meta(aligned[0], "align-a")
    np.testing.assert_allclose(_spectrum_frame(aligned[0])["intensity"], [0.0, 2.0, 4.0])
    np.testing.assert_allclose(_spectrum_frame(fit_curves[0])["intensity"], [0.0, 0.0, 0.0])
    assert diagnostics["status"].tolist() == ["not_fit", "not_fit"]


def test_e2e_normalize_spectrum_handles_negative_intensities_and_saves_output(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "normalize-negative", [100.0, 101.0, 102.0], [-2.0, 0.0, 4.0])

    outputs = NormalizeSpectrum().run({"spectra": spectra}, _config({"method": "max"}))

    reloaded = _roundtrip_spectra(outputs["normalized"], tmp_path, "normalize-output")
    _assert_spectrum_meta(reloaded[0], "normalize-negative")
    np.testing.assert_allclose(_spectrum_frame(reloaded[0])["intensity"], [-0.5, 0.0, 1.0])


def test_e2e_subtract_peak_component_saves_corrected_component_and_diagnostics(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "peak-component", [100.0, 101.0, 102.0, 103.0, 104.0], [0.0, 1.0, 4.0, 1.0, 0.0])

    outputs = SubtractPeakComponent().run(
        {"spectra": spectra},
        _config({"model": "gaussian", "center": 102.0, "width": 1.0, "amplitude": 4.0}),
    )

    corrected = _roundtrip_spectra(outputs["corrected"], tmp_path, "component-corrected")
    component = _roundtrip_spectra(outputs["component"], tmp_path, "component-curve")
    diagnostics = _save_dataframe_output(outputs["fit_diagnostics"], tmp_path, "component-diagnostics")
    _assert_spectrum_meta(corrected[0], "peak-component")
    np.testing.assert_allclose(_spectrum_frame(component[0])["intensity"].iloc[2], 4.0)
    assert diagnostics.loc[0, "model"] == "gaussian"
    assert diagnostics.loc[0, "status"] == "ok"


def test_e2e_extract_intensity_saves_feature_table_for_loaded_spectrum(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "extract-a", [100.0, 101.0, 102.0], [1.0, 3.0, 5.0])

    outputs = ExtractIntensity().run({"spectra": spectra}, _config({"target_lambda": 101.5, "interpolation": "linear"}))

    features = _save_dataframe_output(outputs["features"][0], tmp_path, "extract-features")
    assert features.loc[0, "spectrum_id"] == "extract-a"
    assert features.loc[0, "status"] == "success"
    assert features.loc[0, "measured_lambda"] == pytest.approx(101.5)
    assert features.loc[0, "intensity"] == pytest.approx(4.0)


def test_e2e_calculate_auc_reports_non_overlapping_range_in_saved_feature_table(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "auc-empty", [100.0, 101.0, 102.0], [1.0, 2.0, 3.0])

    outputs = CalculateAUC().run({"spectra": spectra}, _config({"lambda_min": 200.0, "lambda_max": 210.0}))

    features = _save_dataframe_output(outputs["features"][0], tmp_path, "auc-features")
    assert features.loc[0, "spectrum_id"] == "auc-empty"
    assert features.loc[0, "status"] == "empty_range"
    assert pd.isna(features.loc[0, "auc"])
    assert features.loc[0, "lambda_min"] == pytest.approx(200.0)


def test_e2e_calculate_centroid_reports_flat_zero_signal_saved_feature_table(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "centroid-flat", [100.0, 101.0, 102.0], [0.0, 0.0, 0.0])

    outputs = CalculateCentroid().run({"spectra": spectra}, _config({"lambda_min": 100.0, "lambda_max": 102.0}))

    features = _save_dataframe_output(outputs["features"][0], tmp_path, "centroid-features")
    assert features.loc[0, "spectrum_id"] == "centroid-flat"
    assert features.loc[0, "status"] == "unusable_denominator"
    assert pd.isna(features.loc[0, "centroid_lambda"])


def test_e2e_calculate_ratio_reports_zero_denominator_saved_feature_table(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "ratio-zero", [100.0, 101.0, 102.0], [5.0, 0.0, 1.0])

    outputs = CalculateRatio().run(
        {"spectra": spectra},
        _config({"numerator_peak": 100.0, "denominator_peak": 101.0, "interpolation": "nearest"}),
    )

    features = _save_dataframe_output(outputs["features"][0], tmp_path, "ratio-features")
    assert features.loc[0, "spectrum_id"] == "ratio-zero"
    assert features.loc[0, "status"] == "zero_denominator"
    assert pd.isna(features.loc[0, "ratio"])
    assert features.loc[0, "denominator_intensity"] == pytest.approx(0.0)


def test_e2e_find_peaks_reports_flat_no_peak_saved_feature_table(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "peaks-flat", [100.0, 101.0, 102.0, 103.0], [2.0, 2.0, 2.0, 2.0])

    outputs = FindPeaks().run(
        {"spectra": spectra},
        _config({"lambda_min": 100.0, "lambda_max": 103.0, "min_prominence": 0.1}),
    )

    features = _save_dataframe_output(outputs["features"][0], tmp_path, "peaks-features")
    assert features.loc[0, "spectrum_id"] == "peaks-flat"
    assert features.loc[0, "status"] == "no_peaks"
    assert features.loc[0, "peak_count"] == 0
    assert pd.isna(features.loc[0, "peak_lambda"])


def test_e2e_fit_peak_saves_fit_curve_residual_and_parameters(tmp_path: Path) -> None:
    lambdas = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
    intensities = [1.0, 1.54, 3.43, 6.0, 3.43, 1.54, 1.0]
    spectra = _load_spectrum(tmp_path, "fit-a", lambdas, intensities)

    outputs = FitPeak().run(
        {"spectra": spectra},
        _config({"lambda_min": 100.0, "lambda_max": 106.0, "model": "gaussian"}),
    )

    fit_curves = _roundtrip_spectra(outputs["fit_curves"], tmp_path, "fit-curves")
    residuals = _roundtrip_spectra(outputs["residuals"], tmp_path, "fit-residuals")
    parameters = _save_dataframe_output(outputs["parameters"][0], tmp_path, "fit-parameters")
    _assert_spectrum_meta(fit_curves[0], "fit-a")
    _assert_spectrum_meta(residuals[0], "fit-a")
    assert parameters.loc[0, "status"] in {"success", "estimated"}
    assert parameters.loc[0, "center"] == pytest.approx(103.0, abs=0.25)
    assert parameters.loc[0, "amplitude"] > 4.0
    assert np.isfinite(_spectrum_frame(fit_curves[0])["intensity"]).all()


def test_e2e_subtract_reference_spectrum_interpolates_mismatched_axis_and_saves(tmp_path: Path) -> None:
    sample = _load_spectrum(tmp_path, "sample-sub", [100.0, 101.0, 102.0], [10.0, 12.0, 14.0])
    reference = _load_spectrum(tmp_path, "reference-sub", [100.0, 102.0], [2.0, 6.0], filename="reference-sub.csv")

    outputs = SubtractReferenceSpectrum().run(
        {"spectra": sample, "reference": reference},
        _config({"reference_grid_policy": "interpolate_reference_to_sample"}),
    )

    corrected = _roundtrip_spectra(outputs["corrected"], tmp_path, "subtract-reference-output")
    _assert_spectrum_meta(corrected[0], "sample-sub")
    np.testing.assert_allclose(_spectrum_frame(corrected[0])["intensity"], [8.0, 8.0, 8.0])


def test_e2e_divide_by_reference_spectrum_saves_explicit_zero_policy_output(tmp_path: Path) -> None:
    sample = _load_spectrum(tmp_path, "sample-div", [100.0, 101.0, 102.0], [10.0, 12.0, 14.0])
    reference = _load_spectrum(tmp_path, "reference-div", [100.0, 101.0, 102.0], [2.0, 0.0, 7.0])

    outputs = DivideByReferenceSpectrum().run(
        {"spectra": sample, "reference": reference},
        _config({"zero_denominator_policy": "zero"}),
    )

    corrected = _roundtrip_spectra(outputs["corrected"], tmp_path, "divide-reference-output")
    _assert_spectrum_meta(corrected[0], "sample-div")
    np.testing.assert_allclose(_spectrum_frame(corrected[0])["intensity"], [5.0, 0.0, 2.0])


def test_e2e_match_spectral_library_reports_unmatched_library_entries_in_saved_table(tmp_path: Path) -> None:
    spectra = _load_spectrum(tmp_path, "query-no-match", [100.0, 101.0, 102.0], [1.0, 0.0, 1.0])
    library = _empty_library_dataset()

    outputs = MatchSpectralLibrary().run(
        {"spectra": spectra, "library": _dataset_collection(library)},
        _config({"method": "cosine_similarity", "top_k": 3}),
    )

    matches = _save_dataframe_output(outputs["matches"][0], tmp_path, "library-matches")
    assert matches.loc[0, "spectrum_id"] == "query-no-match"
    assert matches.loc[0, "status"] == "no_matches"
    assert pd.isna(matches.loc[0, "library_spectrum_id"])
    assert matches.loc[0, "message"] == "library contains no reference spectra"


def test_e2e_spectral_unmixing_reports_ill_conditioned_fit_quality_saved_tables(tmp_path: Path) -> None:
    sample = _load_spectrum(tmp_path, "unmix-sample", [100.0, 101.0, 102.0], [3.0, 6.0, 9.0])
    references = _load_spectra(
        [
            _write_spectrum_csv(tmp_path / "component-a.csv", "component-a", [100.0, 101.0, 102.0], [1.0, 2.0, 3.0]),
            _write_spectrum_csv(tmp_path / "component-b.csv", "component-b", [100.0, 101.0, 102.0], [2.0, 4.0, 6.0]),
        ]
    )

    outputs = SpectralUnmixing().run(
        {"spectra": sample, "references": references},
        _config({"method": "least_squares", "condition_threshold": 10.0}),
    )

    coefficients = _save_dataframe_output(outputs["coefficients"][0], tmp_path, "unmix-coefficients")
    quality = _save_dataframe_output(outputs["fit_quality"][0], tmp_path, "unmix-fit-quality")
    assert coefficients.loc[0, "spectrum_id"] == "unmix-sample"
    assert {"coeff_component_a", "coeff_component_b"} <= set(coefficients.columns)
    assert quality.loc[0, "status"] == "ill_conditioned"
    assert quality.loc[0, "condition_number"] > 10.0
    assert quality.loc[0, "n_components"] == 2
