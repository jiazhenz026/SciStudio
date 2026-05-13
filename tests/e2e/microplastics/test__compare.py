"""Self-tests for the numerical comparator (:mod:`_compare`).

These tests are marked ``@pytest.mark.e2e`` so they participate only in
``pytest -m e2e`` runs and are excluded from the default
``pytest -m 'not e2e'`` CI command. They exist to guarantee that the
comparator behaves correctly on the data shapes it will see in T-ECA-505
(scalars, numpy arrays, pandas DataFrames, CSV file paths).

Per ADR-033 spec §8.5 T-ECA-503 acceptance criterion: "Numerical
comparator: write a small assert_numerically_equal helper".
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

# E2E-only test: pandas + numpy are not in the default dev environment.
# Use importorskip so pytest collection succeeds (and just skips this
# module) when the optional deps are absent. Without this the default
# CI command `pytest -n auto -m 'not e2e'` fails at collection time.
pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from tests.e2e.microplastics._compare import (  # noqa: E402
    DEFAULT_ATOL,
    DEFAULT_RTOL,
    GoldenMismatch,
    assert_numerically_equal,
)

pytestmark = pytest.mark.e2e


# --------------------------------------------------------------------- scalars


def test_float_within_tolerance_passes() -> None:
    assert_numerically_equal(1.000001, 1.0, rtol=1e-3, atol=1e-6)


def test_float_outside_tolerance_fails() -> None:
    with pytest.raises(GoldenMismatch):
        assert_numerically_equal(1.1, 1.0, rtol=1e-3, atol=1e-6)


def test_int_exact_match_passes() -> None:
    assert_numerically_equal(7, 7)


def test_int_mismatch_fails() -> None:
    with pytest.raises(GoldenMismatch):
        assert_numerically_equal(8, 7)


def test_string_exact_match_passes() -> None:
    assert_numerically_equal("ROI1", "ROI1")


def test_string_mismatch_fails() -> None:
    with pytest.raises(GoldenMismatch):
        assert_numerically_equal("ROI2", "ROI1")


def test_nan_equals_nan() -> None:
    assert_numerically_equal(math.nan, math.nan)


def test_int_actual_vs_float_golden_uses_tolerance() -> None:
    # The float branch coerces both sides to float and applies tolerance,
    # so an integer actual matching a float golden is accepted. Document
    # this so reviewers understand the dispatch rule.
    assert_numerically_equal(1, 1.0)


# ---------------------------------------------------------------- numpy arrays


def test_ndarray_close_passes() -> None:
    a = np.array([1.0, 2.0, 3.0])
    g = np.array([1.0 + 1e-7, 2.0, 3.0 - 1e-7])
    assert_numerically_equal(a, g)


def test_ndarray_shape_mismatch_fails() -> None:
    with pytest.raises(GoldenMismatch):
        assert_numerically_equal(np.array([1.0, 2.0]), np.array([1.0, 2.0, 3.0]))


def test_ndarray_value_mismatch_reports_worst_cell() -> None:
    a = np.array([1.0, 2.0, 3.0])
    g = np.array([1.0, 2.0, 99.0])
    with pytest.raises(GoldenMismatch) as exc_info:
        assert_numerically_equal(a, g)
    assert "worst cell" in str(exc_info.value)


def test_ndarray_int_exact_match() -> None:
    a = np.array([1, 2, 3], dtype=np.int64)
    g = np.array([1, 2, 3], dtype=np.int64)
    assert_numerically_equal(a, g)


# ----------------------------------------------------------------- dataframes


def test_dataframe_close_passes() -> None:
    a = pd.DataFrame({"Raman_Shift": [2800.0, 2806.12], "ROI1": [-5.246, -5.377]})
    g = pd.DataFrame(
        {
            "Raman_Shift": [2800.0, 2806.12],
            "ROI1": [-5.246 + 1e-7, -5.377 - 1e-7],
        }
    )
    assert_numerically_equal(a, g)


def test_dataframe_column_mismatch_fails() -> None:
    a = pd.DataFrame({"X": [1.0], "Y": [2.0]})
    g = pd.DataFrame({"X": [1.0], "Z": [2.0]})
    with pytest.raises(GoldenMismatch) as exc_info:
        assert_numerically_equal(a, g)
    msg = str(exc_info.value)
    assert "missing" in msg and "extra" in msg


def test_dataframe_row_count_mismatch_fails() -> None:
    a = pd.DataFrame({"X": [1.0, 2.0]})
    g = pd.DataFrame({"X": [1.0, 2.0, 3.0]})
    with pytest.raises(GoldenMismatch):
        assert_numerically_equal(a, g)


def test_dataframe_object_column_exact_match() -> None:
    a = pd.DataFrame({"label": ["50nm", "200nm"]})
    g = pd.DataFrame({"label": ["50nm", "200nm"]})
    assert_numerically_equal(a, g)


def test_dataframe_object_column_mismatch_fails() -> None:
    a = pd.DataFrame({"label": ["50nm", "300nm"]})
    g = pd.DataFrame({"label": ["50nm", "200nm"]})
    with pytest.raises(GoldenMismatch):
        assert_numerically_equal(a, g)


# ------------------------------------------------------------------- csv paths


def test_csv_paths_compared_as_dataframes(tmp_path: Path) -> None:
    df = pd.DataFrame({"Raman_Shift": [2800.0, 2806.12], "ROI1": [-5.0, -5.1]})
    a_path = tmp_path / "actual.csv"
    g_path = tmp_path / "golden.csv"
    df.to_csv(a_path, index=False)
    df.to_csv(g_path, index=False)
    assert_numerically_equal(a_path, g_path)


def test_csv_mismatch_via_paths(tmp_path: Path) -> None:
    a_path = tmp_path / "actual.csv"
    g_path = tmp_path / "golden.csv"
    pd.DataFrame({"X": [1.0]}).to_csv(a_path, index=False)
    pd.DataFrame({"X": [99.0]}).to_csv(g_path, index=False)
    with pytest.raises(GoldenMismatch):
        assert_numerically_equal(a_path, g_path)


# ----------------------------------------------------------- containers (dict/list)


def test_dict_recursive_compare() -> None:
    actual = {"thr_uV": 1.23, "n_particles": 33, "label": "50nm"}
    golden = {"thr_uV": 1.23001, "n_particles": 33, "label": "50nm"}
    assert_numerically_equal(actual, golden)


def test_dict_missing_key_fails() -> None:
    with pytest.raises(GoldenMismatch):
        assert_numerically_equal({"a": 1}, {"a": 1, "b": 2})


def test_list_of_floats_compared_elementwise() -> None:
    assert_numerically_equal([1.0, 2.0], [1.000001, 2.0])


# ----------------------------------------------------------- default tolerances


def test_default_tolerances_documented() -> None:
    # Sanity: the documented contract in the golden README is
    # rtol=1e-3, atol=1e-6. Pin it so reviewers notice silent changes.
    assert DEFAULT_RTOL == 1e-3
    assert DEFAULT_ATOL == 1e-6
