from __future__ import annotations

import math
import tomllib
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pyarrow as pa
import pytest
import scistudio_blocks_spectroscopy as spectroscopy
import scistudio_blocks_spectroscopy.blocks as spectroscopy_blocks
import scistudio_blocks_spectroscopy.types as spectroscopy_types
from helpers import make_dataset
from scistudio_blocks_spectroscopy._tables import dataframe_from_pandas, to_pandas_frame
from scistudio_blocks_spectroscopy.blocks.feature_extraction import (
    CalculateAUC,
    CalculateCentroid,
    CalculateRatio,
    ExtractIntensity,
    FindPeaks,
)
from scistudio_blocks_spectroscopy.blocks.utilities import (
    AttachFeaturesToSpectralDataset,
    LoadSpectralDataset,
    LoadSpectrum,
    SaveSpectralDataset,
    SaveSpectrum,
    SpectrumToSpectralDataset,
)
from scistudio_blocks_spectroscopy.previewers import (
    SPECTRAL_DATASET_PREVIEWER_ID,
    SPECTRUM_PREVIEWER_ID,
    get_previewers,
)
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.previewers.models import PreviewLimits, PreviewRequest, PreviewTarget, TargetKind
from scistudio.testing import BlockTestHarness

EXPECTED_BLOCK_NAMES = [
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

EXPECTED_PACKAGE_ALL = [
    "AlignAndResampleSpectra",
    "AttachFeaturesToSpectralDataset",
    "BaselineCorrection",
    "CalculateAUC",
    "CalculateCentroid",
    "CalculateRatio",
    "CropSpectrumRange",
    "DivideByReferenceSpectrum",
    "ExtractIntensity",
    "FilterSpectralDataset",
    "FindPeaks",
    "FitPeak",
    "LoadSpectralDataset",
    "LoadSpectrum",
    "MatchSpectralLibrary",
    "MergeSpectralDataset",
    "NormalizeSpectrum",
    "SaveSpectralDataset",
    "SaveSpectrum",
    "ShiftSpectralAxis",
    "SmoothSpectrum",
    "SpectralDataset",
    "SpectralDatasetToSpectrum",
    "SpectralUnmixing",
    "Spectrum",
    "SpectrumToSpectralDataset",
    "SubtractPeakComponent",
    "SubtractReferenceSpectrum",
    "__version__",
    "get_block_package",
    "get_blocks",
    "get_package_info",
    "get_previewers",
    "get_types",
]

DISALLOWED_PUBLIC_NAMES = {
    "FeatureTable",
    "SpectralLibrary",
    "SpectraTable",
    "CalculateFWHM",
    "MeasurePeakInRange",
    "NormalizeByReferenceSpectrum",
}

EXPECTED_PORT_CONTRACTS = {
    "LoadSpectrum": {
        "type_name": "spectroscopy.load_spectrum",
        "inputs": [("data", ("DataObject",), False, False)],
        "outputs": [("spectra", ("Spectrum",), True, True)],
    },
    "SaveSpectrum": {
        "type_name": "spectroscopy.save_spectrum",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("path", ("Text",), False, True)],
    },
    "LoadSpectralDataset": {
        "type_name": "spectroscopy.load_spectral_dataset",
        "inputs": [("data", ("DataObject",), False, False)],
        "outputs": [("dataset", ("SpectralDataset",), False, True)],
    },
    "SaveSpectralDataset": {
        "type_name": "spectroscopy.save_spectral_dataset",
        "inputs": [("dataset", ("SpectralDataset",), False, True)],
        "outputs": [("path", ("Text",), False, True)],
    },
    "SpectrumToSpectralDataset": {
        "type_name": "spectroscopy.spectrum_to_spectral_dataset",
        "inputs": [("spectra", ("Spectrum",), True, True), ("metadata", ("DataFrame",), False, False)],
        "outputs": [("dataset", ("SpectralDataset",), False, True)],
    },
    "SpectralDatasetToSpectrum": {
        "type_name": "spectroscopy.spectral_dataset_to_spectrum",
        "inputs": [("dataset", ("SpectralDataset",), False, True)],
        "outputs": [("spectra", ("Spectrum",), True, True)],
    },
    "FilterSpectralDataset": {
        "type_name": "spectroscopy.filter_spectral_dataset",
        "inputs": [("dataset", ("SpectralDataset",), False, True)],
        "outputs": [("dataset", ("SpectralDataset",), False, True)],
    },
    "MergeSpectralDataset": {
        "type_name": "spectroscopy.merge_spectral_dataset",
        "inputs": [("datasets", ("SpectralDataset",), True, True)],
        "outputs": [("dataset", ("SpectralDataset",), False, True)],
    },
    "AttachFeaturesToSpectralDataset": {
        "type_name": "spectroscopy.attach_features_to_spectral_dataset",
        "inputs": [("dataset", ("SpectralDataset",), False, True), ("features", ("DataFrame",), False, True)],
        "outputs": [("dataset", ("SpectralDataset",), False, True)],
    },
    "CropSpectrumRange": {
        "type_name": "spectroscopy.crop_spectrum_range",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("cropped", ("Spectrum",), True, True)],
    },
    "ShiftSpectralAxis": {
        "type_name": "spectroscopy.shift_spectral_axis",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("shifted", ("Spectrum",), True, True)],
    },
    "BaselineCorrection": {
        "type_name": "spectroscopy.baseline_correction",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [
            ("corrected", ("Spectrum",), True, True),
            ("baseline", ("Spectrum",), True, True),
            ("fit_diagnostics", ("DataFrame",), False, True),
        ],
    },
    "SmoothSpectrum": {
        "type_name": "spectroscopy.smooth_spectrum",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("smoothed", ("Spectrum",), True, True)],
    },
    "AlignAndResampleSpectra": {
        "type_name": "spectroscopy.align_and_resample_spectra",
        "inputs": [("spectra", ("Spectrum",), True, True), ("reference", ("Spectrum",), False, False)],
        "outputs": [
            ("aligned", ("Spectrum",), True, True),
            ("fit_curves", ("Spectrum",), True, True),
            ("fit_diagnostics", ("DataFrame",), False, True),
        ],
    },
    "NormalizeSpectrum": {
        "type_name": "spectroscopy.normalize_spectrum",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("normalized", ("Spectrum",), True, True)],
    },
    "SubtractPeakComponent": {
        "type_name": "spectroscopy.subtract_peak_component",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [
            ("corrected", ("Spectrum",), True, True),
            ("component", ("Spectrum",), True, True),
            ("fit_diagnostics", ("DataFrame",), False, True),
        ],
    },
    "ExtractIntensity": {
        "type_name": "spectroscopy.extract_intensity",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("features", ("DataFrame",), False, True)],
    },
    "CalculateAUC": {
        "type_name": "spectroscopy.calculate_auc",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("features", ("DataFrame",), False, True)],
    },
    "CalculateCentroid": {
        "type_name": "spectroscopy.calculate_centroid",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("features", ("DataFrame",), False, True)],
    },
    "CalculateRatio": {
        "type_name": "spectroscopy.calculate_ratio",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("features", ("DataFrame",), False, True)],
    },
    "FindPeaks": {
        "type_name": "spectroscopy.find_peaks",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [("features", ("DataFrame",), False, True)],
    },
    "FitPeak": {
        "type_name": "spectroscopy.fit_peak",
        "inputs": [("spectra", ("Spectrum",), True, True)],
        "outputs": [
            ("fit_curves", ("Spectrum",), True, True),
            ("residuals", ("Spectrum",), True, True),
            ("parameters", ("DataFrame",), False, True),
        ],
    },
    "SubtractReferenceSpectrum": {
        "type_name": "spectroscopy.subtract_reference_spectrum",
        "inputs": [("spectra", ("Spectrum",), True, True), ("reference", ("Spectrum",), False, True)],
        "outputs": [("corrected", ("Spectrum",), True, True)],
    },
    "DivideByReferenceSpectrum": {
        "type_name": "spectroscopy.divide_by_reference_spectrum",
        "inputs": [("spectra", ("Spectrum",), True, True), ("reference", ("Spectrum",), False, True)],
        "outputs": [("corrected", ("Spectrum",), True, True)],
    },
    "MatchSpectralLibrary": {
        "type_name": "spectroscopy.match_spectral_library",
        "inputs": [("spectra", ("Spectrum",), True, True), ("library", ("SpectralDataset",), False, True)],
        "outputs": [("matches", ("DataFrame",), False, True)],
    },
    "SpectralUnmixing": {
        "type_name": "spectroscopy.spectral_unmixing",
        "inputs": [("spectra", ("Spectrum",), True, True), ("references", ("Spectrum",), True, True)],
        "outputs": [("coefficients", ("DataFrame",), False, True), ("fit_quality", ("DataFrame",), False, True)],
    },
}

EXPECTED_CONFIG_CONTRACTS = {
    "LoadSpectrum": {
        "required": ["path"],
        "properties": {"path": {}, "format": {"default": None}, "capability_id": {"default": None}},
    },
    "SaveSpectrum": {
        "required": ["path"],
        "properties": {"path": {}, "format": {"default": None}, "capability_id": {"default": None}},
    },
    "LoadSpectralDataset": {
        "required": [],
        "properties": {
            "path": {"default": None},
            "index_path": {"default": None},
            "spectra_path": {"default": None},
            "format": {"default": None},
            "capability_id": {"default": None},
        },
    },
    "SaveSpectralDataset": {
        "required": ["path"],
        "properties": {"path": {}, "format": {"default": None}, "capability_id": {"default": None}},
    },
    "SpectrumToSpectralDataset": {
        "required": [],
        "properties": {
            "metadata_join_key": {"default": "spectrum_id"},
            "dataset_name": {"default": None},
            "dataset_role": {"default": "experiment"},
        },
    },
    "SpectralDatasetToSpectrum": {"required": [], "properties": {}},
    "FilterSpectralDataset": {"required": [], "properties": {"filters": {"default": {}}}},
    "MergeSpectralDataset": {
        "required": [],
        "properties": {"duplicate_id_policy": {"default": "error", "enum": ["error", "prefix", "remap"]}},
    },
    "AttachFeaturesToSpectralDataset": {
        "required": [],
        "properties": {
            "join_key": {"default": "spectrum_id"},
            "conflict_policy": {"default": "error", "enum": ["error", "overwrite", "suffix"]},
        },
    },
    "CropSpectrumRange": {
        "required": [],
        "properties": {"lambda_min": {"default": None}, "lambda_max": {"default": None}},
    },
    "ShiftSpectralAxis": {"required": [], "properties": {"shift": {"default": 0.0}}},
    "BaselineCorrection": {
        "required": [],
        "properties": {
            "method": {"default": "polynomial", "enum": ["polynomial", "asls", "arpls", "airpls"]},
            "polynomial_order": {"default": 2},
            "lambda_smoothness": {"default": 100000.0},
            "asymmetry": {"default": 0.001},
            "max_iterations": {"default": 50},
            "tolerance": {"default": 1e-6},
        },
    },
    "SmoothSpectrum": {
        "required": [],
        "properties": {
            "method": {"default": "savitzky_golay", "enum": ["savitzky_golay", "moving_average", "gaussian", "median"]},
            "window": {"default": 5},
            "polyorder": {"default": 2},
            "sigma": {"default": 1.0},
        },
    },
    "AlignAndResampleSpectra": {
        "required": [],
        "properties": {
            "alignment_method": {"default": "none", "enum": ["none", "peak_fit", "cross_correlation"]},
            "target_grid_mode": {
                "default": "first_spectrum",
                "enum": ["first_spectrum", "reference_spectrum", "range_step", "explicit"],
            },
            "target_grid": {},
            "lambda_min": {"default": None},
            "lambda_max": {"default": None},
            "step": {"default": None},
            "reference_index": {"default": 0},
            "peak_center": {"default": None},
            "fit_window": {"default": None},
        },
    },
    "NormalizeSpectrum": {"required": [], "properties": {"method": {"default": "max", "enum": ["max", "minmax"]}}},
    "SubtractPeakComponent": {
        "required": [],
        "properties": {
            "model": {"default": "gaussian", "enum": ["gaussian", "lorentzian", "voigt"]},
            "center": {"default": None},
            "width": {"default": None},
            "amplitude": {"default": None},
            "eta": {"default": 0.5},
            "fit_window": {"default": None},
        },
    },
    "ExtractIntensity": {
        "required": [],
        "properties": {
            "target_lambda": {},
            "target_peak": {},
            "lambda_min": {},
            "lambda_max": {},
            "interpolation": {"default": "linear", "enum": ["linear", "nearest", "none"]},
        },
    },
    "CalculateAUC": {"required": ["lambda_min", "lambda_max"], "properties": {"lambda_min": {}, "lambda_max": {}}},
    "CalculateCentroid": {
        "required": ["lambda_min", "lambda_max"],
        "properties": {"lambda_min": {}, "lambda_max": {}},
    },
    "CalculateRatio": {
        "required": ["numerator_peak", "denominator_peak"],
        "properties": {
            "numerator_peak": {},
            "denominator_peak": {},
            "interpolation": {"default": "linear", "enum": ["linear", "nearest", "none"]},
        },
    },
    "FindPeaks": {
        "required": [],
        "properties": {
            "lambda_min": {},
            "lambda_max": {},
            "min_height": {},
            "min_prominence": {"default": 0.0},
            "target_rank": {"default": 1},
        },
    },
    "FitPeak": {
        "required": ["lambda_min", "lambda_max", "model"],
        "properties": {
            "lambda_min": {},
            "lambda_max": {},
            "model": {"default": "gaussian", "enum": ["gaussian", "lorentzian", "voigt"]},
        },
    },
    "SubtractReferenceSpectrum": {
        "required": [],
        "properties": {
            "reference_grid_policy": {"default": "error", "enum": ["error", "interpolate_reference_to_sample"]}
        },
    },
    "DivideByReferenceSpectrum": {
        "required": [],
        "properties": {
            "reference_grid_policy": {"default": "error", "enum": ["error", "interpolate_reference_to_sample"]},
            "zero_denominator_policy": {"default": "error", "enum": ["epsilon", "error", "inf", "nan", "zero"]},
            "epsilon": {"default": 1e-12},
        },
    },
    "MatchSpectralLibrary": {
        "required": ["method", "top_k"],
        "properties": {
            "method": {
                "default": "cosine_similarity",
                "enum": ["cosine_similarity", "pearson_correlation", "spectral_angle", "euclidean_distance"],
            },
            "top_k": {"default": 5},
            "grid_policy": {"default": "error", "enum": ["error", "report"]},
            "unit_policy": {"default": "error", "enum": ["error", "report"]},
        },
    },
    "SpectralUnmixing": {
        "required": ["method", "component_label_source"],
        "properties": {
            "method": {
                "default": "least_squares",
                "enum": [
                    "least_squares",
                    "non_negative_least_squares",
                    "sum_to_one_non_negative_least_squares",
                ],
            },
            "component_label_source": {"default": "spectrum_id"},
            "grid_policy": {"default": "error", "enum": ["error", "interpolate_references_to_sample"]},
            "condition_threshold": {"default": 10000000000.0},
        },
    },
}

SPECTRUM_META_FIELDS = ("lambda_unit", "intensity_unit", "lambda_kind", "modality")
DATASET_META_FIELDS = ("dataset_name", "dataset_role", "lambda_unit", "intensity_unit", "modality", "schema_version")
DATASET_VENDOR_META_FIELDS = ("dataset_role", "lambda_unit", "intensity_unit", "modality")


def _port_contracts(ports: list[Any]) -> list[tuple[str, tuple[str, ...], bool, bool]]:
    return [
        (
            port.name,
            tuple(data_type.__name__ for data_type in port.accepted_types),
            bool(port.is_collection),
            bool(port.required),
        )
        for port in ports
    ]


def _spectrum(spectrum_id: str | None, lambdas: list[float], intensities: list[float]) -> Spectrum:
    user = {"source_file": "source.txt"}
    if spectrum_id is not None:
        user["spectrum_id"] = spectrum_id
    return Spectrum(
        length=len(lambdas),
        meta=Spectrum.Meta(spectrum_id=spectrum_id, source_file="source.txt"),
        user=user,
        data=pa.table({"lambda": lambdas, "intensity": intensities}),
    )


def _spectra(*spectra: Spectrum) -> Collection:
    return Collection(items=list(spectra), item_type=Spectrum)


def _dataframe_collection(frame: pd.DataFrame) -> Collection:
    return Collection(items=[dataframe_from_pandas(frame)], item_type=DataFrame)


def _feature_rows(output: Collection) -> list[dict[str, Any]]:
    table = output[0].get_in_memory_data()
    assert isinstance(table, pa.Table)
    return cast(list[dict[str, Any]], table.to_pylist())


def _all_io_capabilities() -> dict[str, Any]:
    blocks = (LoadSpectrum, SaveSpectrum, LoadSpectralDataset, SaveSpectralDataset)
    return {capability.id: capability for block in blocks for capability in block.get_format_capabilities()}


def _capability_expected(
    *,
    direction: str,
    data_type: str,
    format_id: str,
    extensions: tuple[str, ...],
    label: str,
    block_type: str,
    handler: str,
    roundtrip_group: str | None,
    fidelity_level: str,
    typed_reads: tuple[str, ...] = (),
    typed_writes: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "direction": direction,
        "data_type": data_type,
        "format_id": format_id,
        "extensions": extensions,
        "label": label,
        "block_type": block_type,
        "handler": handler,
        "roundtrip_group": roundtrip_group,
        "fidelity_level": fidelity_level,
        "typed_reads": typed_reads,
        "typed_writes": typed_writes,
    }


EXPECTED_CAPABILITIES = {
    "scistudio-blocks-spectroscopy.spectrum.txt.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="txt",
        extensions=(".txt",),
        label="Text spectrum",
        block_type="LoadSpectrum",
        handler="_load_delimited_text",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.txt",
        fidelity_level="pixel_only",
    ),
    "scistudio-blocks-spectroscopy.spectrum.txt.save": _capability_expected(
        direction="save",
        data_type="Spectrum",
        format_id="txt",
        extensions=(".txt",),
        label="Text spectrum",
        block_type="SaveSpectrum",
        handler="_save_delimited_text",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.txt",
        fidelity_level="pixel_only",
    ),
    "scistudio-blocks-spectroscopy.spectrum.csv.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="csv",
        extensions=(".csv",),
        label="CSV spectrum",
        block_type="LoadSpectrum",
        handler="_load_delimited_text",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.csv",
        fidelity_level="pixel_only",
    ),
    "scistudio-blocks-spectroscopy.spectrum.csv.save": _capability_expected(
        direction="save",
        data_type="Spectrum",
        format_id="csv",
        extensions=(".csv",),
        label="CSV spectrum",
        block_type="SaveSpectrum",
        handler="_save_delimited_text",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.csv",
        fidelity_level="pixel_only",
    ),
    "scistudio-blocks-spectroscopy.spectrum.tsv.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV spectrum",
        block_type="LoadSpectrum",
        handler="_load_delimited_text",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.tsv",
        fidelity_level="pixel_only",
    ),
    "scistudio-blocks-spectroscopy.spectrum.tsv.save": _capability_expected(
        direction="save",
        data_type="Spectrum",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV spectrum",
        block_type="SaveSpectrum",
        handler="_save_delimited_text",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.tsv",
        fidelity_level="pixel_only",
    ),
    "scistudio-blocks-spectroscopy.spectrum.xlsx.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="xlsx",
        extensions=(".xlsx", ".xls"),
        label="Excel spectrum workbook",
        block_type="LoadSpectrum",
        handler="_load_spectrum_xlsx",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.xlsx",
        fidelity_level="typed_meta",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.xlsx.save": _capability_expected(
        direction="save",
        data_type="Spectrum",
        format_id="xlsx",
        extensions=(".xlsx",),
        label="Excel spectrum workbook",
        block_type="SaveSpectrum",
        handler="_save_spectrum_xlsx",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.xlsx",
        fidelity_level="typed_meta",
        typed_writes=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.spectrum_json.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="spectrum_json",
        extensions=(".spectrum.json",),
        label="Native Spectrum JSON",
        block_type="LoadSpectrum",
        handler="_load_spectrum_json",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.spectrum_json",
        fidelity_level="lossless",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.spectrum_json.save": _capability_expected(
        direction="save",
        data_type="Spectrum",
        format_id="spectrum_json",
        extensions=(".spectrum.json",),
        label="Native Spectrum JSON",
        block_type="SaveSpectrum",
        handler="_save_spectrum_json",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.spectrum_json",
        fidelity_level="lossless",
        typed_writes=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.jcamp_dx.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="jcamp_dx",
        extensions=(".jdx", ".dx", ".jcamp"),
        label="JCAMP-DX spectrum",
        block_type="LoadSpectrum",
        handler="_load_jcamp_dx",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.jcamp_dx",
        fidelity_level="typed_meta",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.jcamp_dx.save": _capability_expected(
        direction="save",
        data_type="Spectrum",
        format_id="jcamp_dx",
        extensions=(".jdx", ".dx", ".jcamp"),
        label="JCAMP-DX spectrum",
        block_type="SaveSpectrum",
        handler="_save_jcamp_dx",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.jcamp_dx",
        fidelity_level="typed_meta",
        typed_writes=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.spc.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="spc",
        extensions=(".spc",),
        label="SPC spectrum",
        block_type="LoadSpectrum",
        handler="_load_spc",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.spc",
        fidelity_level="typed_meta",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.spc.save": _capability_expected(
        direction="save",
        data_type="Spectrum",
        format_id="spc",
        extensions=(".spc",),
        label="SPC spectrum",
        block_type="SaveSpectrum",
        handler="_save_spc",
        roundtrip_group="scistudio-blocks-spectroscopy.spectrum.spc",
        fidelity_level="typed_meta",
        typed_writes=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.thermo_omnic_spa.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="thermo_omnic_spa",
        extensions=(".spa",),
        label="Thermo OMNIC SPA spectrum",
        block_type="LoadSpectrum",
        handler="_load_thermo_omnic_spa",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.bruker_opus.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="bruker_opus",
        extensions=(".opus",),
        label="Bruker OPUS spectrum",
        block_type="LoadSpectrum",
        handler="_load_bruker_opus",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.horiba_labspec.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="horiba_labspec",
        extensions=(".l6s", ".l5s", ".ngs", ".xml"),
        label="HORIBA LabSpec spectrum",
        block_type="LoadSpectrum",
        handler="_load_horiba_labspec",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.renishaw_wdf.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="renishaw_wdf",
        extensions=(".wdf",),
        label="Renishaw WiRE spectrum",
        block_type="LoadSpectrum",
        handler="_load_renishaw_wdf",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.andor_solis.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="andor_solis",
        extensions=(".sif", ".fits", ".fit", ".asc"),
        label="Andor Solis spectrum",
        block_type="LoadSpectrum",
        handler="_load_andor_solis",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectrum.princeton_spe.load": _capability_expected(
        direction="load",
        data_type="Spectrum",
        format_id="princeton_spe",
        extensions=(".spe",),
        label="Princeton/LightField SPE spectrum",
        block_type="LoadSpectrum",
        handler="_load_princeton_spe",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=SPECTRUM_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="spectral_dataset_manifest_json",
        extensions=(".json",),
        label="SpectralDataset manifest (JSON)",
        block_type="LoadSpectralDataset",
        handler="_load_manifest_json",
        roundtrip_group="scistudio-blocks-spectroscopy.spectral_dataset.manifest_json",
        fidelity_level="lossless",
        typed_reads=DATASET_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.manifest_json.save": _capability_expected(
        direction="save",
        data_type="SpectralDataset",
        format_id="spectral_dataset_manifest_json",
        extensions=(".json",),
        label="SpectralDataset manifest (JSON)",
        block_type="SaveSpectralDataset",
        handler="_save_manifest_json",
        roundtrip_group="scistudio-blocks-spectroscopy.spectral_dataset.manifest_json",
        fidelity_level="lossless",
        typed_writes=DATASET_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.xlsx.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="xlsx",
        extensions=(".xlsx", ".xls"),
        label="SpectralDataset Excel workbook",
        block_type="LoadSpectralDataset",
        handler="_load_dataset_xlsx",
        roundtrip_group="scistudio-blocks-spectroscopy.spectral_dataset.xlsx",
        fidelity_level="typed_meta",
        typed_reads=DATASET_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.xlsx.save": _capability_expected(
        direction="save",
        data_type="SpectralDataset",
        format_id="xlsx",
        extensions=(".xlsx",),
        label="SpectralDataset Excel workbook",
        block_type="SaveSpectralDataset",
        handler="_save_dataset_xlsx",
        roundtrip_group="scistudio-blocks-spectroscopy.spectral_dataset.xlsx",
        fidelity_level="typed_meta",
        typed_writes=DATASET_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.spc.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="spc",
        extensions=(".spc",),
        label="SPC spectral dataset",
        block_type="LoadSpectralDataset",
        handler="_load_spc_dataset",
        roundtrip_group="scistudio-blocks-spectroscopy.spectral_dataset.spc",
        fidelity_level="typed_meta",
        typed_reads=DATASET_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.spc.save": _capability_expected(
        direction="save",
        data_type="SpectralDataset",
        format_id="spc",
        extensions=(".spc",),
        label="SPC spectral dataset",
        block_type="SaveSpectralDataset",
        handler="_save_spc_dataset",
        roundtrip_group="scistudio-blocks-spectroscopy.spectral_dataset.spc",
        fidelity_level="typed_meta",
        typed_writes=DATASET_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.thermo_omnic_spg.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="thermo_omnic_spg",
        extensions=(".spg",),
        label="Thermo OMNIC SPG dataset",
        block_type="LoadSpectralDataset",
        handler="_load_thermo_omnic_spg",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=DATASET_VENDOR_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.renishaw_wdf.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="renishaw_wdf",
        extensions=(".wdf",),
        label="Renishaw WiRE dataset",
        block_type="LoadSpectralDataset",
        handler="_load_renishaw_wdf_dataset",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=DATASET_VENDOR_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.bruker_opus.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="bruker_opus",
        extensions=(".opus",),
        label="Bruker OPUS dataset",
        block_type="LoadSpectralDataset",
        handler="_load_bruker_opus_dataset",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=DATASET_VENDOR_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.horiba_labspec.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="horiba_labspec",
        extensions=(".l6s", ".l5s", ".ngc", ".xml", ".txt"),
        label="HORIBA LabSpec dataset",
        block_type="LoadSpectralDataset",
        handler="_load_horiba_labspec_dataset",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=DATASET_VENDOR_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.witec_project.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="witec_project",
        extensions=(".wip", ".wid"),
        label="WITec project dataset",
        block_type="LoadSpectralDataset",
        handler="_load_witec_project",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=DATASET_VENDOR_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.andor_solis.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="andor_solis",
        extensions=(".sif", ".fits", ".fit"),
        label="Andor Solis dataset",
        block_type="LoadSpectralDataset",
        handler="_load_andor_solis_dataset",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=DATASET_VENDOR_META_FIELDS,
    ),
    "scistudio-blocks-spectroscopy.spectral_dataset.princeton_spe.load": _capability_expected(
        direction="load",
        data_type="SpectralDataset",
        format_id="princeton_spe",
        extensions=(".spe",),
        label="Princeton/LightField SPE dataset",
        block_type="LoadSpectralDataset",
        handler="_load_princeton_spe_dataset",
        roundtrip_group=None,
        fidelity_level="typed_meta",
        typed_reads=DATASET_VENDOR_META_FIELDS,
    ),
}


def test_exact_public_type_and_block_export_surface() -> None:
    assert [data_type.__name__ for data_type in spectroscopy.get_types()] == ["Spectrum", "SpectralDataset"]
    assert spectroscopy_types.__all__ == ["SpectralDataset", "Spectrum"]
    assert [block.__name__ for block in spectroscopy.get_blocks()] == EXPECTED_BLOCK_NAMES
    assert set(spectroscopy_blocks.__all__) == set(EXPECTED_BLOCK_NAMES)
    assert spectroscopy.__all__ == EXPECTED_PACKAGE_ALL

    for name in DISALLOWED_PUBLIC_NAMES:
        assert not hasattr(spectroscopy, name)
        assert not hasattr(spectroscopy_blocks, name)
        assert not hasattr(spectroscopy_types, name)


def test_type_metadata_slots_and_table_columns_are_exact() -> None:
    assert set(Spectrum.Meta.model_fields) == {
        "spectrum_id",
        "sample_label",
        "lambda_unit",
        "intensity_unit",
        "lambda_kind",
        "modality",
        "source_file",
    }
    assert set(SpectralDataset.Meta.model_fields) == set(DATASET_META_FIELDS)
    assert SpectralDataset.Meta().dataset_role == "experiment"
    assert SpectralDataset.Meta().schema_version == "1"
    assert SpectralDataset.expected_slots == {"index": DataFrame, "spectra": DataFrame}

    dataset = make_dataset()
    assert dataset.index.columns is not None
    assert dataset.spectra.columns is not None
    assert set(dataset.index.columns) >= {"spectrum_id"}
    assert set(dataset.spectra.columns) >= {"spectrum_id", "lambda", "intensity"}
    assert not hasattr(Spectrum, "format_capabilities")
    assert not hasattr(SpectralDataset, "format_capabilities")
    assert not hasattr(Spectrum, "supported_extensions")
    assert not hasattr(SpectralDataset, "supported_extensions")


@pytest.mark.parametrize("block_cls", spectroscopy.get_blocks(), ids=lambda cls: cls.__name__)
def test_public_blocks_satisfy_core_block_harness(block_cls: type) -> None:
    errors = BlockTestHarness(block_cls).validate_block()
    assert not errors, errors


@pytest.mark.parametrize("block_cls", spectroscopy.get_blocks(), ids=lambda cls: cls.__name__)
def test_block_type_names_ports_and_collections_match_spec(block_cls: type) -> None:
    block = cast(Any, block_cls)
    expected = cast(dict[str, Any], EXPECTED_PORT_CONTRACTS[block.__name__])
    assert block.type_name == expected["type_name"]
    assert _port_contracts(block.input_ports) == expected["inputs"]
    assert _port_contracts(block.output_ports) == expected["outputs"]


@pytest.mark.parametrize("block_cls", spectroscopy.get_blocks(), ids=lambda cls: cls.__name__)
def test_block_config_defaults_enums_and_required_keys_match_spec(block_cls: type) -> None:
    block = cast(Any, block_cls)
    expected = cast(dict[str, Any], EXPECTED_CONFIG_CONTRACTS[block.__name__])
    expected_properties = cast(dict[str, dict[str, Any]], expected["properties"])
    schema = cast(dict[str, Any], block.config_schema)
    properties = schema.get("properties", {})

    assert schema["type"] == "object"
    assert schema.get("required", []) == expected["required"]
    assert set(properties) == set(expected_properties)
    for property_name, property_expectation in expected_properties.items():
        property_schema = properties[property_name]
        for key in ("default", "enum"):
            if key in property_expectation:
                assert property_schema.get(key) == property_expectation[key]


def test_format_capability_matrix_fields_match_adr043_spec() -> None:
    capabilities = _all_io_capabilities()
    assert set(capabilities) == set(EXPECTED_CAPABILITIES)

    for capability_id, expected in EXPECTED_CAPABILITIES.items():
        capability = capabilities[capability_id]
        assert capability.direction == expected["direction"]
        assert capability.data_type.__name__ == expected["data_type"]
        assert capability.format_id == expected["format_id"]
        assert capability.extensions == expected["extensions"]
        assert capability.label == expected["label"]
        assert capability.block_type == expected["block_type"]
        assert capability.handler == expected["handler"]
        assert capability.is_default is True
        assert capability.priority == 0
        assert capability.roundtrip_group == expected["roundtrip_group"]
        assert capability.metadata_fidelity.level == expected["fidelity_level"]
        assert capability.metadata_fidelity.typed_meta_reads == expected["typed_reads"]
        assert capability.metadata_fidelity.typed_meta_writes == expected["typed_writes"]
        assert capability.is_synthesized is False
        assert hasattr(globals()[capability.block_type](), capability.handler)


def test_vendor_capabilities_are_load_only_and_not_roundtrip_or_lossless() -> None:
    capabilities = _all_io_capabilities()
    vendor_ids = {
        capability_id
        for capability_id in capabilities
        if any(
            vendor in capability_id
            for vendor in (
                "thermo_omnic",
                "bruker_opus",
                "horiba_labspec",
                "renishaw_wdf",
                "andor_solis",
                "princeton_spe",
                "witec_project",
            )
        )
    }

    assert vendor_ids
    assert all(capabilities[capability_id].direction == "load" for capability_id in vendor_ids)
    assert all(capabilities[capability_id].roundtrip_group is None for capability_id in vendor_ids)
    assert all(capabilities[capability_id].metadata_fidelity.level != "lossless" for capability_id in vendor_ids)
    assert not any(capability_id.endswith(".zip.load") for capability_id in capabilities)
    assert not any(capability_id.endswith(".zip.save") for capability_id in capabilities)


def test_io_capability_id_is_config_reference_only() -> None:
    for block_cls in (LoadSpectrum, SaveSpectrum, LoadSpectralDataset, SaveSpectralDataset):
        assert issubclass(block_cls, IOBlock)
        assert block_cls.config_schema["properties"]["capability_id"]["default"] is None

    assert not hasattr(Spectrum, "capability_id")
    assert not hasattr(SpectralDataset, "capability_id")


def test_previewer_entry_point_and_display_only_payloads_match_adr048_contract() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    assert pyproject["project"]["entry-points"]["scistudio.previewers"] == {
        "spectroscopy": "scistudio_blocks_spectroscopy.previewers:get_previewers"
    }

    specs = {spec.previewer_id: spec for spec in get_previewers()}
    assert set(specs) == {SPECTRUM_PREVIEWER_ID, SPECTRAL_DATASET_PREVIEWER_ID}

    expected_payloads: dict[str, dict[str, Any]] = {
        SPECTRUM_PREVIEWER_ID: {
            "index_name": "lambda",
            "value_name": "intensity",
            "display": "line",
            "export": ("figure", "visible_points"),
        },
        SPECTRAL_DATASET_PREVIEWER_ID: {
            "slots": {"index": "DataFrame", "spectra": "DataFrame"},
            "display": "spectral_dataset",
            "export": ("figure", "visible_spectra", "selected_index", "grouped_summary"),
        },
    }
    for previewer_id, expected_payload in expected_payloads.items():
        spec = specs[previewer_id]
        assert callable(spec.backend_provider)
        envelope = spec.backend_provider(  # type: ignore[misc]
            PreviewRequest(
                target=PreviewTarget(
                    kind=TargetKind.DATA_REF,
                    ref="data/object",
                    recorded_type=spec.target_type,
                    type_chain=("DataObject", spec.target_type),
                ),
                spec=spec,
                query={"_record_metadata": {"sample": "A"}},
                data_access=None,  # type: ignore[arg-type]
                limits=PreviewLimits(),
            )
        )
        assert envelope.payload == {**expected_payload, "metadata": {"sample": "A"}}
        assert "processing" not in envelope.payload
        assert "workflow_output" not in envelope.payload
        assert "lineage" not in envelope.payload


def test_feature_measurement_edge_statuses_are_explicit() -> None:
    empty = _spectrum("empty", [], [])
    single = _spectrum("single", [5.0], [9.0])
    unsorted_duplicate = _spectrum("dup", [3.0, 1.0, 2.0, 2.0], [30.0, 10.0, 20.0, 22.0])
    zero_denominator = _spectrum("zero-den", [0.0, 5.0, 10.0], [0.0, 4.0, 8.0])

    empty_intensity_rows = _feature_rows(
        ExtractIntensity(config={"params": {"target_lambda": 1.0}}).run(
            {"spectra": _spectra(empty)},
            ExtractIntensity(config={"params": {"target_lambda": 1.0}}).config,
        )["features"]
    )
    assert empty_intensity_rows[0]["status"] == "empty_spectrum"
    assert empty_intensity_rows[0]["intensity"] is None

    single_intensity = ExtractIntensity(config={"params": {"target_lambda": 5.0}})
    single_rows = _feature_rows(
        single_intensity.run({"spectra": _spectra(single)}, single_intensity.config)["features"]
    )
    assert single_rows[0]["status"] == "success"
    assert single_rows[0]["intensity"] == 9.0

    single_auc = CalculateAUC(config={"params": {"lambda_min": 5.0, "lambda_max": 5.0}})
    single_auc_rows = _feature_rows(single_auc.run({"spectra": _spectra(single)}, single_auc.config)["features"])
    assert single_auc_rows[0]["status"] == "empty_range"
    assert single_auc_rows[0]["auc"] is None

    unsorted_auc = CalculateAUC(config={"params": {"lambda_min": 1.0, "lambda_max": 3.0}})
    unsorted_rows = _feature_rows(
        unsorted_auc.run({"spectra": _spectra(unsorted_duplicate)}, unsorted_auc.config)["features"]
    )
    assert unsorted_rows[0]["status"] == "success"
    assert math.isclose(unsorted_rows[0]["auc"], 42.0)

    centroid = CalculateCentroid(config={"params": {"lambda_min": 5.0, "lambda_max": 5.0}})
    centroid_rows = _feature_rows(centroid.run({"spectra": _spectra(single)}, centroid.config)["features"])
    assert centroid_rows[0]["status"] == "empty_range"
    assert centroid_rows[0]["centroid_lambda"] is None

    ratio = CalculateRatio(config={"params": {"numerator_peak": 10.0, "denominator_peak": 0.0}})
    ratio_rows = _feature_rows(ratio.run({"spectra": _spectra(zero_denominator)}, ratio.config)["features"])
    assert ratio_rows[0]["status"] == "zero_denominator"
    assert ratio_rows[0]["ratio"] is None

    peak_rows = _feature_rows(FindPeaks().run({"spectra": _spectra(empty)}, FindPeaks().config)["features"])
    assert peak_rows[0]["status"] == "no_peaks"
    assert peak_rows[0]["peak_lambda"] is None


def test_missing_ids_are_generated_and_missing_feature_values_remain_joinable() -> None:
    no_id_spectrum = _spectrum(None, [1.0, 2.0], [3.0, 4.0])
    dataset = SpectrumToSpectralDataset().run(
        {"spectra": _spectra(no_id_spectrum)}, SpectrumToSpectralDataset().config
    )["dataset"][0]
    index = to_pandas_frame(dataset.index)

    assert index.loc[0, "spectrum_id"] == "spectrum-1"
    assert index.loc[0, "source_file"] == "source.txt"

    base_dataset = make_dataset(ids=("s1", "s2"), materials=("cell", "media"))
    features = _dataframe_collection(pd.DataFrame({"spectrum_id": ["s1"], "peak_area": [10.0]}))
    attached = AttachFeaturesToSpectralDataset().run(
        {"dataset": Collection(items=[base_dataset], item_type=SpectralDataset), "features": features},
        AttachFeaturesToSpectralDataset().config,
    )["dataset"][0]
    attached_index = to_pandas_frame(attached.index)

    assert attached_index["peak_area"].iloc[0] == 10.0
    assert math.isnan(float(attached_index["peak_area"].iloc[1]))
    assert to_pandas_frame(attached.spectra).equals(to_pandas_frame(base_dataset.spectra))
