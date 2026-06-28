"""ADR-052 §3.1 / §10 ergonomic accessor round-trips.

The accessors (``Array.to_numpy``, ``DataFrame.to_pandas``/``to_numpy``,
``Series.to_pandas``/``to_numpy``) are **additive, read-only, public-only**
conveniences that *wrap* ``to_memory()`` and never replace the canonical form
(ADR-031). This file pins:

* the return types (ndarray / ``pandas.DataFrame`` / ``pandas.Series``);
* that each accessor carries the same data as ``to_memory()`` (it is a wrapper,
  not a different value);
* that ``to_memory()`` still returns the canonical form afterward (additive, not
  a replacement);
* that already-ergonomic types (``Text`` / ``Artifact`` / ``CompositeData``) add
  no such accessor.

``Array.to_memory()`` reads its ``_transient_data`` slot, so an in-memory
``Array`` round-trips without persistence. ``DataFrame``/``Series``
``to_memory()`` route through ``storage_ref`` -> backend by design (ADR-031); an
unpersisted instance raises "no storage reference set". The ``DataFrame``/
``Series`` accessor checks therefore persist the object first (``save()`` to a
temp Arrow/Parquet backend) and then read — exercising a realistically-persisted
object, which is the documented usage, not a weakened assertion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa

from scistudio.core.types import (
    Array,
    Artifact,
    CompositeData,
    DataFrame,
    Series,
    Text,
)

# ---------------------------------------------------------------------------
# Array.to_numpy()
# ---------------------------------------------------------------------------


def test_array_to_numpy_returns_ndarray_wrapping_to_memory() -> None:
    raw = np.arange(9, dtype="float64").reshape(3, 3)
    arr = Array(axes=["y", "x"], shape=(3, 3), dtype="float64", data=raw)

    out = arr.to_numpy()
    assert isinstance(out, np.ndarray), "Array.to_numpy() must return a numpy ndarray (§10)"
    # Wraps the canonical reader: same data as to_memory() (which is already ndarray).
    np.testing.assert_array_equal(out, arr.to_memory())
    np.testing.assert_array_equal(out, raw)


def test_array_accessor_is_additive_not_a_replacement() -> None:
    raw = np.arange(4, dtype="float32").reshape(2, 2)
    arr = Array(axes=["y", "x"], shape=(2, 2), dtype="float32", data=raw)
    _ = arr.to_numpy()
    # to_memory() is untouched and still the canonical ndarray form.
    assert isinstance(arr.to_memory(), np.ndarray)


# ---------------------------------------------------------------------------
# DataFrame.to_pandas() / to_numpy()
# ---------------------------------------------------------------------------


def _sample_table() -> pa.Table:
    return pa.table({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})


def test_dataframe_to_pandas_returns_dataframe_wrapping_to_memory(tmp_path) -> None:
    table = _sample_table()
    df = DataFrame(data=table)
    # ADR-031: DataFrame.to_memory() reads via storage_ref -> backend; persist
    # to a temp Arrow/Parquet backend so the accessor has a real source to wrap.
    df.save(str(tmp_path / "df.parquet"))

    out = df.to_pandas()
    assert isinstance(out, pd.DataFrame), "DataFrame.to_pandas() must return a pandas.DataFrame (§10)"
    # Wraps to_memory(): the canonical form is the Arrow table; to_pandas() is its pandas view.
    assert isinstance(df.to_memory(), pa.Table)
    pd.testing.assert_frame_equal(out, df.to_memory().to_pandas())


def test_dataframe_to_numpy_returns_ndarray(tmp_path) -> None:
    df = DataFrame(data=_sample_table())
    df.save(str(tmp_path / "df.parquet"))
    out = df.to_numpy()
    assert isinstance(out, np.ndarray), "DataFrame.to_numpy() must return a numpy ndarray (§10)"
    assert out.shape[0] == 3
    np.testing.assert_array_equal(out, df.to_pandas().to_numpy())


def test_dataframe_accessor_is_additive_not_a_replacement(tmp_path) -> None:
    df = DataFrame(data=_sample_table())
    df.save(str(tmp_path / "df.parquet"))
    _ = df.to_pandas()
    # to_memory() still returns the canonical Arrow form (ADR-031 unchanged).
    assert isinstance(df.to_memory(), pa.Table)


# ---------------------------------------------------------------------------
# Series.to_pandas() / to_numpy()
# ---------------------------------------------------------------------------


def test_series_to_pandas_returns_series(tmp_path) -> None:
    values = np.array([1.0, 2.0, 3.0])
    s = Series(value_name="signal", length=3, data=values)
    s.save(str(tmp_path / "s.parquet"))  # ADR-031: persist so to_memory() has a source

    out = s.to_pandas()
    assert isinstance(out, pd.Series), "Series.to_pandas() must return a pandas.Series (§10)"
    np.testing.assert_array_equal(out.to_numpy(), values)


def test_series_to_numpy_returns_ndarray_wrapping_to_memory(tmp_path) -> None:
    values = np.array([10.0, 20.0, 30.0])
    s = Series(value_name="signal", length=3, data=values)
    s.save(str(tmp_path / "s.parquet"))

    out = s.to_numpy()
    assert isinstance(out, np.ndarray), "Series.to_numpy() must return a numpy ndarray (§10)"
    np.testing.assert_array_equal(out, values)
    # Canonical form is still an Arrow table (single column) after the read.
    assert isinstance(s.to_memory(), pa.Table)


# ---------------------------------------------------------------------------
# Types that must NOT gain an accessor (§10: already ergonomic).
# ---------------------------------------------------------------------------


def test_text_artifact_composite_have_no_ergonomic_accessor() -> None:
    for cls in (Text, Artifact, CompositeData):
        assert not hasattr(cls, "to_pandas"), f"{cls.__name__} must not define to_pandas (§10)"
        assert not hasattr(cls, "to_numpy"), f"{cls.__name__} must not define to_numpy (§10)"
