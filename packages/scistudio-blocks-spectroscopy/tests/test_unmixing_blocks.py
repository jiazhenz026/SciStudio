from __future__ import annotations

# ruff: noqa: E402,I001

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio_blocks_spectroscopy.blocks import unmixing
from scistudio_blocks_spectroscopy.blocks.unmixing import SpectralUnmixing


def _spectrum(
    spectrum_id: str,
    intensities: list[float],
    *,
    lambda_values: list[float] | None = None,
    user: dict[str, Any] | None = None,
) -> Series:
    coordinates = lambda_values or [float(index) for index in range(len(intensities))]
    metadata = {"spectrum_id": spectrum_id, "lambda_unit": "cm-1"}
    metadata.update(user or {})
    return Series(
        index_name="lambda",
        value_name="intensity",
        data=pd.DataFrame({"lambda": coordinates, "intensity": intensities}),
        user=metadata,
    )


def _collection(items: list[Series]) -> Collection:
    data_objects: list[DataObject] = [*items]
    return Collection(items=data_objects, item_type=Series)


def _output_frame(output: Collection) -> pd.DataFrame:
    assert output.item_type is DataFrame
    assert len(output) == 1
    return output[0]._data.copy()  # type: ignore[attr-defined]


def test_least_squares_outputs_coefficients_and_fit_quality() -> None:
    sample = _spectrum("sample", [0.25, 0.75, 0.0])
    references = [_spectrum("A", [1.0, 0.0, 0.0]), _spectrum("B", [0.0, 1.0, 0.0])]

    result = SpectralUnmixing().run(
        {"spectra": _collection([sample]), "references": _collection(references)},
        BlockConfig(params={"method": "least_squares"}),
    )
    coefficients = _output_frame(result["coefficients"])
    fit_quality = _output_frame(result["fit_quality"])

    assert coefficients.columns.tolist() == ["spectrum_id", "method", "coeff_a", "coeff_b"]
    assert coefficients.loc[0, "coeff_a"] == pytest.approx(0.25)
    assert coefficients.loc[0, "coeff_b"] == pytest.approx(0.75)
    assert fit_quality.loc[0, "status"] == "ok"
    assert fit_quality.loc[0, "residual_norm"] == pytest.approx(0.0)
    assert fit_quality.loc[0, "rmse"] == pytest.approx(0.0)
    assert fit_quality.loc[0, "n_components"] == 2


def test_non_negative_least_squares_enforces_non_negative_coefficients() -> None:
    sample = _spectrum("sample", [0.2, 0.8])
    references = [_spectrum("A", [1.0, 0.0]), _spectrum("B", [0.0, 1.0])]

    result = SpectralUnmixing().run(
        {"spectra": _collection([sample]), "references": _collection(references)},
        BlockConfig(params={"method": "non_negative_least_squares"}),
    )
    coefficients = _output_frame(result["coefficients"])

    assert coefficients.loc[0, "coeff_a"] >= -1e-12
    assert coefficients.loc[0, "coeff_b"] >= -1e-12
    assert coefficients.loc[0, "coeff_a"] == pytest.approx(0.2)
    assert coefficients.loc[0, "coeff_b"] == pytest.approx(0.8)


def test_sum_to_one_non_negative_least_squares_sums_to_one() -> None:
    sample = _spectrum("sample", [0.3, 0.7])
    references = [_spectrum("A", [1.0, 0.0]), _spectrum("B", [0.0, 1.0])]

    result = SpectralUnmixing().run(
        {"spectra": _collection([sample]), "references": _collection(references)},
        BlockConfig(params={"method": "sum_to_one_non_negative_least_squares"}),
    )
    coefficients = _output_frame(result["coefficients"])

    values = coefficients[["coeff_a", "coeff_b"]].iloc[0].to_numpy(dtype=float)
    assert np.all(values >= -1e-12)
    assert float(np.sum(values)) == pytest.approx(1.0)


def test_duplicate_reference_labels_create_collision_free_columns() -> None:
    sample = _spectrum("sample", [0.4, 0.6])
    references = [
        _spectrum("ref-1", [1.0, 0.0], user={"material": "same label"}),
        _spectrum("ref-2", [0.0, 1.0], user={"material": "same label"}),
    ]

    result = SpectralUnmixing().run(
        {"spectra": _collection([sample]), "references": _collection(references)},
        BlockConfig(params={"method": "least_squares", "component_label_source": "material"}),
    )
    coefficients = _output_frame(result["coefficients"])

    assert coefficients.columns.tolist() == [
        "spectrum_id",
        "method",
        "coeff_same_label",
        "coeff_same_label_2",
    ]
    assert coefficients.loc[0, "coeff_same_label"] == pytest.approx(0.4)
    assert coefficients.loc[0, "coeff_same_label_2"] == pytest.approx(0.6)


def test_ill_conditioned_reference_matrix_is_reported() -> None:
    sample = _spectrum("sample", [3.0, 3.0, 3.0])
    references = [
        _spectrum("A", [1.0, 1.0, 1.0]),
        _spectrum("B", [2.0, 2.0, 2.0]),
    ]

    result = SpectralUnmixing().run(
        {"spectra": _collection([sample]), "references": _collection(references)},
        BlockConfig(params={"method": "least_squares", "condition_threshold": 100.0}),
    )
    fit_quality = _output_frame(result["fit_quality"])

    assert fit_quality.loc[0, "status"] == "ill_conditioned"
    assert fit_quality.loc[0, "condition_number"] > 100.0
    assert "ill-conditioned" in fit_quality.loc[0, "message"]


def test_grid_mismatch_defaults_to_error() -> None:
    sample = _spectrum("sample", [1.0, 2.0], lambda_values=[1.0, 2.0])
    references = [_spectrum("A", [1.0, 2.0], lambda_values=[1.0, 3.0])]

    with pytest.raises(ValueError, match="incompatible lambda grids"):
        SpectralUnmixing().run(
            {"spectra": _collection([sample]), "references": _collection(references)},
            BlockConfig(params={"method": "least_squares"}),
        )


def test_unmixing_method_enum_and_output_ports_are_closed() -> None:
    method_schema = SpectralUnmixing.config_schema["properties"]["method"]
    assert set(method_schema["enum"]) == {
        "least_squares",
        "non_negative_least_squares",
        "sum_to_one_non_negative_least_squares",
    }
    assert [port.name for port in SpectralUnmixing.output_ports] == ["coefficients", "fit_quality"]

    sample = _spectrum("sample", [1.0])
    reference = _spectrum("A", [1.0])
    with pytest.raises(ValueError, match="method must be one of"):
        SpectralUnmixing().run(
            {"spectra": _collection([sample]), "references": _collection([reference])},
            BlockConfig(params={"method": "pca"}),
        )


def test_module_does_not_define_result_type_or_spectrum_outputs() -> None:
    assert not hasattr(unmixing, "SpectralUnmixingResult")
    assert [port.name for port in SpectralUnmixing.output_ports] == ["coefficients", "fit_quality"]
