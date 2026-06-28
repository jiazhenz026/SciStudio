"""Ergonomic accessor round-trips (ADR-052 §3.1 / spec §10).

The accessors are additive, public-only, read-only: they wrap ``to_memory()``
and never replace it. ``Array.to_numpy()`` -> ndarray; ``DataFrame.to_pandas()``
-> pandas.DataFrame and ``.to_numpy()`` -> ndarray; ``Series.to_pandas()`` ->
pandas.Series and ``.to_numpy()`` -> ndarray. ``Text``/``Artifact``/
``CompositeData`` expose NO such accessor (already ergonomic).

``Array.to_memory()`` reads its in-memory transient slot, so an ``Array``
round-trips without persistence. ``DataFrame``/``Series`` ``to_memory()`` route
through ``storage_ref`` -> backend by design (ADR-031), so those round-trips
persist the object first (``save()`` to a temp Arrow/Parquet backend) and then
read — the documented usage, not a weakened assertion.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest
from _spec_data import NO_ACCESSOR_TYPES, import_root

_TYPES = "scistudio.core.types"


def _cls(name: str):
    module = import_root(_TYPES)
    assert module is not None, f"{_TYPES} failed to import"
    obj = getattr(module, name, None)
    assert obj is not None, f"{name} not importable from {_TYPES}"
    return obj


def test_array_to_numpy_roundtrip() -> None:
    Array = _cls("Array")  # noqa: N806 — holds a class ref, PascalCase is correct
    payload = np.arange(12, dtype="float64").reshape(3, 4)
    arr = Array(axes=("y", "x"), data=payload)

    out = arr.to_numpy()
    assert isinstance(out, np.ndarray), "Array.to_numpy() must return numpy.ndarray (§10)"
    # Wraps the inherited canonical reader (to_memory() is already an ndarray).
    np.testing.assert_array_equal(out, np.asarray(arr.to_memory()))


def test_dataframe_accessors_roundtrip(tmp_path) -> None:
    DataFrame = _cls("DataFrame")  # noqa: N806 — holds a class ref, PascalCase is correct
    table = pa.table({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
    df = DataFrame(data=table)
    # ADR-031: DataFrame.to_memory() reads via storage_ref -> backend; persist
    # to a temp Arrow/Parquet backend so the accessor has a real source to wrap.
    df.save(str(tmp_path / "df.parquet"))

    pdf = df.to_pandas()
    assert isinstance(pdf, pd.DataFrame), "DataFrame.to_pandas() must return pandas.DataFrame (§10)"
    # Wraps to_memory() (a pyarrow.Table) -> same values.
    pd.testing.assert_frame_equal(pdf.reset_index(drop=True), df.to_memory().to_pandas())

    nd = df.to_numpy()
    assert isinstance(nd, np.ndarray), "DataFrame.to_numpy() must return numpy.ndarray (§10)"
    assert nd.shape[0] == 3


def test_series_accessors_roundtrip(tmp_path) -> None:
    Series = _cls("Series")  # noqa: N806 — holds a class ref, PascalCase is correct
    table = pa.table({"value": [10.0, 20.0, 30.0]})
    series = Series(data=table)
    series.save(str(tmp_path / "s.parquet"))  # ADR-031: persist so to_memory() has a source

    ps = series.to_pandas()
    assert isinstance(ps, pd.Series), "Series.to_pandas() must return pandas.Series (§10)"

    nd = series.to_numpy()
    assert isinstance(nd, np.ndarray), "Series.to_numpy() must return numpy.ndarray (§10)"
    np.testing.assert_array_equal(np.asarray(ps), nd)


@pytest.mark.parametrize("cls_name", NO_ACCESSOR_TYPES)
@pytest.mark.parametrize("accessor", ("to_pandas", "to_numpy"))
def test_already_ergonomic_types_have_no_accessor(cls_name: str, accessor: str) -> None:
    """Text/Artifact/CompositeData must NOT define ergonomic accessors (§10)."""
    cls = _cls(cls_name)
    assert not hasattr(cls, accessor), (
        f"{cls_name} must not expose .{accessor}() -- its to_memory() is already "
        f"ergonomic (ADR-052 §3.1 / spec §10)"
    )
