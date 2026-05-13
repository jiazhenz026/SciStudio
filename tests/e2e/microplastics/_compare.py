"""Numerical comparator for golden-reference assertions.

Per ADR-033 spec §8.5 T-ECA-503: provides ``assert_numerically_equal`` for
comparing actual outputs (from the agent's workflow run) against golden
outputs captured from the source ipynb.

The comparator is type-aware:

* **Floats / numpy float arrays** — compared with ``np.allclose`` using
  ``rtol`` and ``atol``.
* **Integer scalars / integer arrays** — compared exactly.
* **Strings / categorical labels** — compared exactly.
* **pandas DataFrames** — aligned on columns and index, then dispatched
  per-column according to the column's dtype.
* **pandas Series** — same as a one-column DataFrame.
* **CSV file paths** — loaded with ``pd.read_csv`` and compared as
  DataFrames.

The default tolerances ``rtol=1e-3, atol=1e-6`` are the contract documented
in ``tests/e2e/microplastics/golden/README.md``. Callers may override per
call site.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_RTOL = 1e-3
DEFAULT_ATOL = 1e-6


class GoldenMismatch(AssertionError):  # noqa: N818 — intentional non-Error suffix (legacy test-helper convention)
    """Raised by :func:`assert_numerically_equal` on any mismatch.

    The exception message is human-readable and structured enough for the
    diff-reporter that T-ECA-505 will write to ``runs/<ts>/diff.md``.
    """


def assert_numerically_equal(
    actual: Any,
    golden: Any,
    *,
    rtol: float = DEFAULT_RTOL,
    atol: float = DEFAULT_ATOL,
    context: str = "",
) -> None:
    """Assert that ``actual`` matches ``golden`` within tolerance.

    Parameters
    ----------
    actual, golden
        Values to compare. May be scalars, strings, numpy arrays, pandas
        Series/DataFrames, or filesystem paths to CSV files.
    rtol, atol
        Float tolerances forwarded to ``np.allclose``. Ignored for
        non-float dtypes (which require exact equality).
    context
        Human label prepended to error messages, e.g. the field name or
        file stem. Recursive comparisons append sub-paths automatically.

    Raises
    ------
    GoldenMismatch
        On any mismatch in shape, dtype, or value.
    """
    # 1. Path-likes pointing at CSVs are loaded eagerly.
    actual = _maybe_load_csv(actual)
    golden = _maybe_load_csv(golden)

    # 2. Dispatch on golden's runtime type (the contract).
    if isinstance(golden, pd.DataFrame):
        if not isinstance(actual, pd.DataFrame):
            raise GoldenMismatch(f"{_ctx(context)}expected DataFrame, got {type(actual).__name__}")
        _assert_dataframe_equal(actual, golden, rtol=rtol, atol=atol, context=context)
        return

    if isinstance(golden, pd.Series):
        if not isinstance(actual, pd.Series):
            raise GoldenMismatch(f"{_ctx(context)}expected Series, got {type(actual).__name__}")
        _assert_series_equal(actual, golden, rtol=rtol, atol=atol, context=context)
        return

    if isinstance(golden, np.ndarray):
        if not isinstance(actual, np.ndarray):
            try:
                actual = np.asarray(actual)
            except Exception as exc:
                raise GoldenMismatch(f"{_ctx(context)}expected ndarray, got {type(actual).__name__} ({exc!r})") from exc
        _assert_ndarray_equal(actual, golden, rtol=rtol, atol=atol, context=context)
        return

    if isinstance(golden, (list, tuple)):
        if not isinstance(actual, (list, tuple)) or len(actual) != len(golden):
            raise GoldenMismatch(
                f"{_ctx(context)}sequence length/type mismatch: "
                f"actual={type(actual).__name__}(len {len(actual) if hasattr(actual, '__len__') else '?'}), "
                f"golden={type(golden).__name__}(len {len(golden)})"
            )
        for i, (a, g) in enumerate(zip(actual, golden, strict=True)):
            assert_numerically_equal(a, g, rtol=rtol, atol=atol, context=f"{context}[{i}]")
        return

    if isinstance(golden, dict):
        if not isinstance(actual, dict):
            raise GoldenMismatch(f"{_ctx(context)}expected dict, got {type(actual).__name__}")
        missing = set(golden) - set(actual)
        extra = set(actual) - set(golden)
        if missing or extra:
            raise GoldenMismatch(f"{_ctx(context)}key mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
        for k, g in golden.items():
            assert_numerically_equal(actual[k], g, rtol=rtol, atol=atol, context=f"{context}.{k}")
        return

    # 3. Scalar fallback.
    _assert_scalar_equal(actual, golden, rtol=rtol, atol=atol, context=context)


# --------------------------------------------------------------------- helpers


def _ctx(context: str) -> str:
    return f"{context}: " if context else ""


def _is_numeric_dtype(dtype: Any) -> bool:
    """Return True for numpy/pandas numeric dtypes (float, int, complex).

    Tolerates pandas extension dtypes (``StringDtype``, ``CategoricalDtype``,
    nullable ints) which ``np.issubdtype`` cannot introspect directly.
    """
    # pandas' helper is the authoritative answer here.
    try:
        return bool(pd.api.types.is_numeric_dtype(dtype))
    except (TypeError, ValueError):
        return False


def _maybe_load_csv(value: Any) -> Any:
    """If ``value`` is a path-like to a ``.csv``, load and return a DataFrame."""
    if isinstance(value, (str, os.PathLike)) and not isinstance(value, np.ndarray):
        try:
            p = Path(value)
        except TypeError:
            return value
        if p.suffix.lower() == ".csv" and p.exists():
            return pd.read_csv(p)
    return value


def _assert_scalar_equal(
    actual: Any,
    golden: Any,
    *,
    rtol: float,
    atol: float,
    context: str,
) -> None:
    # Strings / labels: exact.
    if isinstance(golden, str):
        if not isinstance(actual, str) or actual != golden:
            raise GoldenMismatch(f"{_ctx(context)}string mismatch: actual={actual!r}, golden={golden!r}")
        return

    # Booleans: exact.
    if isinstance(golden, (bool, np.bool_)):
        if bool(actual) != bool(golden):
            raise GoldenMismatch(f"{_ctx(context)}bool mismatch: actual={actual!r}, golden={golden!r}")
        return

    # Integers: exact.
    if isinstance(golden, (int, np.integer)) and not isinstance(golden, bool):
        if not isinstance(actual, (int, np.integer)) or int(actual) != int(golden):
            raise GoldenMismatch(f"{_ctx(context)}int mismatch: actual={actual!r}, golden={golden!r}")
        return

    # Floats: tolerance-based.
    if isinstance(golden, (float, np.floating)):
        af = float(actual)
        gf = float(golden)
        if math.isnan(gf):
            if not math.isnan(af):
                raise GoldenMismatch(f"{_ctx(context)}expected NaN, got {actual!r}")
            return
        if not math.isclose(af, gf, rel_tol=rtol, abs_tol=atol):
            raise GoldenMismatch(
                f"{_ctx(context)}float mismatch: actual={af!r}, golden={gf!r}, rtol={rtol}, atol={atol}"
            )
        return

    # Fallback for anything else: require equality.
    if actual != golden:
        raise GoldenMismatch(f"{_ctx(context)}value mismatch: actual={actual!r}, golden={golden!r}")


def _assert_ndarray_equal(
    actual: np.ndarray,
    golden: np.ndarray,
    *,
    rtol: float,
    atol: float,
    context: str,
) -> None:
    if actual.shape != golden.shape:
        raise GoldenMismatch(f"{_ctx(context)}shape mismatch: actual={actual.shape}, golden={golden.shape}")
    if np.issubdtype(golden.dtype, np.floating):
        if not np.allclose(actual, golden, rtol=rtol, atol=atol, equal_nan=True):
            # Report the worst-offending cell to make diagnosis tractable.
            diff = np.abs(actual.astype(np.float64) - golden.astype(np.float64))
            worst = np.unravel_index(np.nanargmax(diff), diff.shape)
            raise GoldenMismatch(
                f"{_ctx(context)}float array mismatch: worst cell {worst} "
                f"actual={actual[worst]!r} golden={golden[worst]!r} "
                f"|diff|={diff[worst]!r}"
            )
    else:
        if not np.array_equal(actual, golden):
            raise GoldenMismatch(f"{_ctx(context)}array (dtype={golden.dtype}) mismatch")


def _assert_series_equal(
    actual: pd.Series,
    golden: pd.Series,
    *,
    rtol: float,
    atol: float,
    context: str,
) -> None:
    if list(actual.index) != list(golden.index):
        raise GoldenMismatch(f"{_ctx(context)}series index mismatch")
    _assert_ndarray_equal(
        np.asarray(actual.values),
        np.asarray(golden.values),
        rtol=rtol,
        atol=atol,
        context=context,
    )


def _assert_dataframe_equal(
    actual: pd.DataFrame,
    golden: pd.DataFrame,
    *,
    rtol: float,
    atol: float,
    context: str,
) -> None:
    """Align by columns + index, then compare per-column by dtype."""
    actual_cols = list(actual.columns)
    golden_cols = list(golden.columns)
    if actual_cols != golden_cols:
        missing = [c for c in golden_cols if c not in actual_cols]
        extra = [c for c in actual_cols if c not in golden_cols]
        raise GoldenMismatch(f"{_ctx(context)}DataFrame column mismatch: missing={missing}, extra={extra}")

    if len(actual) != len(golden):
        raise GoldenMismatch(f"{_ctx(context)}DataFrame row count mismatch: actual={len(actual)}, golden={len(golden)}")

    for col in golden_cols:
        col_ctx = f"{context}[{col!r}]" if context else f"[{col!r}]"
        g = golden[col]
        a = actual[col]
        if _is_numeric_dtype(g.dtype):
            _assert_ndarray_equal(
                np.asarray(a.values),
                np.asarray(g.values),
                rtol=rtol,
                atol=atol,
                context=col_ctx,
            )
        else:
            # Object / string columns: cell-wise exact comparison.
            for i, (av, gv) in enumerate(zip(a.tolist(), g.tolist(), strict=True)):
                if av != gv:
                    # NaN comparisons fall through; handle them explicitly.
                    try:
                        if pd.isna(av) and pd.isna(gv):
                            continue
                    except (TypeError, ValueError):
                        pass
                    raise GoldenMismatch(f"{col_ctx} row {i}: actual={av!r}, golden={gv!r}")


__all__ = (
    "DEFAULT_ATOL",
    "DEFAULT_RTOL",
    "GoldenMismatch",
    "assert_numerically_equal",
)
