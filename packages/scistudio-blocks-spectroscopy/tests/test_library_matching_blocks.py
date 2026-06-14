from __future__ import annotations

# ruff: noqa: E402,I001

import sys
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
import pytest

PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio_blocks_spectroscopy.blocks import library_matching
from scistudio_blocks_spectroscopy.blocks.library_matching import MatchSpectralLibrary


class _SpectralDataset(CompositeData):
    expected_slots: ClassVar[dict[str, type]] = {"index": DataFrame, "spectra": DataFrame}


def _frame(data: dict[str, list[Any]]) -> DataFrame:
    pandas_frame = pd.DataFrame(data)
    result = DataFrame(columns=list(pandas_frame.columns), row_count=len(pandas_frame))
    result._data = pandas_frame
    return result


def _spectrum(
    spectrum_id: str,
    lambda_values: list[float],
    intensities: list[float],
    *,
    lambda_unit: str = "cm-1",
) -> Series:
    result = Series(
        index_name="lambda",
        value_name="intensity",
        data=pd.DataFrame({"lambda": lambda_values, "intensity": intensities}),
        user={"spectrum_id": spectrum_id, "lambda_unit": lambda_unit},
    )
    return result


def _library(rows: list[tuple[str, list[float], list[float], str]]) -> _SpectralDataset:
    index_data = {
        "spectrum_id": [row[0] for row in rows],
        "material": [f"material_{idx}" for idx, _row in enumerate(rows)],
        "lambda_unit": [row[3] for row in rows],
    }
    spectra_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for spectrum_id, lambda_values, intensities, _unit in rows:
        if spectrum_id in seen:
            continue
        seen.add(spectrum_id)
        for lambda_value, intensity in zip(lambda_values, intensities, strict=True):
            spectra_rows.append({"spectrum_id": spectrum_id, "lambda": lambda_value, "intensity": intensity})
    spectra = pd.DataFrame(spectra_rows, columns=["spectrum_id", "lambda", "intensity"])
    return _SpectralDataset(
        slots={
            "index": _frame(index_data),
            "spectra": _frame({column: spectra[column].tolist() for column in spectra.columns}),
        }
    )


def _empty_library() -> _SpectralDataset:
    return _SpectralDataset(
        slots={
            "index": _frame({"spectrum_id": [], "lambda_unit": []}),
            "spectra": _frame({"spectrum_id": [], "lambda": [], "intensity": []}),
        }
    )


def _output_frame(output: Collection) -> pd.DataFrame:
    assert output.item_type is DataFrame
    assert len(output) == 1
    return output[0]._data.copy()  # type: ignore[attr-defined]


def test_cosine_similarity_ranks_duplicate_references_deterministically() -> None:
    query = Collection(items=[_spectrum("query", [1.0, 2.0, 3.0], [1.0, 0.0, 0.0])], item_type=Series)
    library = _library(
        [
            ("ref_a", [1.0, 2.0, 3.0], [1.0, 0.0, 0.0], "cm-1"),
            ("ref_a", [1.0, 2.0, 3.0], [1.0, 0.0, 0.0], "cm-1"),
            ("ref_b", [1.0, 2.0, 3.0], [0.0, 1.0, 0.0], "cm-1"),
        ]
    )

    result = MatchSpectralLibrary().run(
        {"spectra": query, "library": library},
        BlockConfig(params={"method": "cosine_similarity", "top_k": 3}),
    )
    matches = _output_frame(result["matches"])

    assert matches["library_spectrum_id"].tolist() == ["ref_a", "ref_a", "ref_b"]
    assert matches["library_row_index"].tolist() == [0, 1, 2]
    assert matches["rank"].tolist() == [1, 2, 3]
    assert matches["score"].tolist()[:2] == [1.0, 1.0]
    assert matches["status"].tolist() == ["ok", "ok", "ok"]


def test_pearson_correlation_prefers_centered_shape() -> None:
    query = Collection(items=[_spectrum("query", [1.0, 2.0, 3.0], [1.0, 2.0, 3.0])], item_type=Series)
    library = _library(
        [
            ("positive", [1.0, 2.0, 3.0], [10.0, 20.0, 30.0], "cm-1"),
            ("negative", [1.0, 2.0, 3.0], [3.0, 2.0, 1.0], "cm-1"),
        ]
    )

    result = MatchSpectralLibrary().run(
        {"spectra": query, "library": library},
        BlockConfig(params={"method": "pearson_correlation", "top_k": 2}),
    )
    matches = _output_frame(result["matches"])

    assert matches.loc[0, "library_spectrum_id"] == "positive"
    assert matches.loc[0, "score"] == pytest.approx(1.0)
    assert matches.loc[1, "library_spectrum_id"] == "negative"
    assert matches.loc[1, "score"] == pytest.approx(-1.0)


def test_no_library_matches_returns_status_rows() -> None:
    query = Collection(items=[_spectrum("query", [1.0, 2.0], [5.0, 6.0])], item_type=Series)

    result = MatchSpectralLibrary().run(
        {"spectra": query, "library": _empty_library()},
        BlockConfig(params={"method": "cosine_similarity"}),
    )
    matches = _output_frame(result["matches"])

    assert matches.loc[0, "spectrum_id"] == "query"
    assert matches.loc[0, "library_spectrum_id"] is None
    assert matches.loc[0, "rank"] == 0
    assert matches.loc[0, "status"] == "no_matches"


def test_grid_mismatch_defaults_to_error() -> None:
    query = Collection(items=[_spectrum("query", [1.0, 2.0], [1.0, 1.0])], item_type=Series)
    library = _library([("ref", [1.0, 3.0], [1.0, 1.0], "cm-1")])

    with pytest.raises(ValueError, match="incompatible lambda grids"):
        MatchSpectralLibrary().run(
            {"spectra": query, "library": library},
            BlockConfig(params={"method": "cosine_similarity"}),
        )


def test_unit_mismatch_can_report_non_success_status() -> None:
    query = Collection(items=[_spectrum("query", [1.0, 2.0], [1.0, 1.0], lambda_unit="nm")], item_type=Series)
    library = _library([("ref", [1.0, 2.0], [1.0, 1.0], "cm-1")])

    result = MatchSpectralLibrary().run(
        {"spectra": query, "library": library},
        BlockConfig(params={"method": "cosine_similarity", "unit_policy": "report"}),
    )
    matches = _output_frame(result["matches"])

    assert matches.loc[0, "status"] == "incompatible_units"
    assert matches.loc[0, "rank"] == 0


def test_matching_method_enum_is_closed() -> None:
    method_schema = MatchSpectralLibrary.config_schema["properties"]["method"]
    assert set(method_schema["enum"]) == {
        "cosine_similarity",
        "pearson_correlation",
        "spectral_angle",
        "euclidean_distance",
    }

    query = Collection(items=[_spectrum("query", [1.0], [1.0])], item_type=Series)
    with pytest.raises(ValueError, match="method must be one of"):
        MatchSpectralLibrary().run(
            {"spectra": query, "library": _empty_library()},
            BlockConfig(params={"method": "calibration_model"}),
        )


def test_module_does_not_define_public_spectral_library_type() -> None:
    assert not hasattr(library_matching, "SpectralLibrary")
