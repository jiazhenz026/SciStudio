"""Tests for wrap_as_dataobject() auto-detection logic.

Covers issue #1639: the stub previously raised NotImplementedError.
"""

from __future__ import annotations

import pytest

from scistudio.core.types.array import Array
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text
from scistudio.utils.wrapping import wrap_as_dataobject

# ---------------------------------------------------------------------------
# Passthrough — already a DataObject
# ---------------------------------------------------------------------------


def test_passthrough_returns_same_instance() -> None:
    obj = Text(content="hello")
    result = wrap_as_dataobject(obj)
    assert result is obj


# ---------------------------------------------------------------------------
# str → Text
# ---------------------------------------------------------------------------


def test_str_wraps_to_text() -> None:
    result = wrap_as_dataobject("hello world")
    assert isinstance(result, Text)
    assert result.content == "hello world"


def test_empty_str_wraps_to_text() -> None:
    result = wrap_as_dataobject("")
    assert isinstance(result, Text)
    assert result.content == ""


# ---------------------------------------------------------------------------
# numpy ndarray → Array
# ---------------------------------------------------------------------------


numpy = pytest.importorskip("numpy")


def test_1d_ndarray_wraps_to_array() -> None:
    arr = numpy.array([1.0, 2.0, 3.0])
    result = wrap_as_dataobject(arr)
    assert isinstance(result, Array)
    assert result.axes == ["dim_0"]
    assert result.shape == (3,)
    assert result._transient_data is arr


def test_2d_ndarray_wraps_to_array() -> None:
    arr = numpy.zeros((4, 5))
    result = wrap_as_dataobject(arr)
    assert isinstance(result, Array)
    assert result.axes == ["dim_0", "dim_1"]
    assert result.shape == (4, 5)


def test_3d_ndarray_axes_generated() -> None:
    arr = numpy.zeros((2, 3, 4))
    result = wrap_as_dataobject(arr)
    assert isinstance(result, Array)
    assert result.axes == ["dim_0", "dim_1", "dim_2"]


# ---------------------------------------------------------------------------
# pandas DataFrame → DataFrame
# ---------------------------------------------------------------------------


pandas = pytest.importorskip("pandas")


def test_dataframe_wraps() -> None:
    df = pandas.DataFrame({"a": [1, 2], "b": [3, 4]})
    result = wrap_as_dataobject(df)
    assert isinstance(result, DataFrame)
    assert result.columns == ["a", "b"]
    assert result.row_count == 2
    assert result._transient_data is df


def test_empty_dataframe_wraps() -> None:
    df = pandas.DataFrame()
    result = wrap_as_dataobject(df)
    assert isinstance(result, DataFrame)
    assert result.columns == []
    assert result.row_count == 0


# ---------------------------------------------------------------------------
# pandas Series → Series
# ---------------------------------------------------------------------------


def test_series_wraps() -> None:
    s = pandas.Series([10, 20, 30], name="intensity")
    result = wrap_as_dataobject(s)
    assert isinstance(result, Series)
    assert result.value_name == "intensity"
    assert result.length == 3
    assert result._transient_data is s


def test_series_with_named_index_wraps() -> None:
    s = pandas.Series([1.0, 2.0], index=pandas.Index([100, 200], name="wavenumber"), name="signal")
    result = wrap_as_dataobject(s)
    assert isinstance(result, Series)
    assert result.index_name == "wavenumber"
    assert result.value_name == "signal"


def test_series_unnamed_wraps() -> None:
    s = pandas.Series([1, 2, 3])
    result = wrap_as_dataobject(s)
    assert isinstance(result, Series)
    assert result.value_name is None
    assert result.index_name is None


# ---------------------------------------------------------------------------
# TypeError for unsupported types
# ---------------------------------------------------------------------------


def test_unsupported_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="wrap_as_dataobject"):
        wrap_as_dataobject(42)


def test_unsupported_list_raises_type_error() -> None:
    with pytest.raises(TypeError, match="wrap_as_dataobject"):
        wrap_as_dataobject([1, 2, 3])


def test_unsupported_none_raises_type_error() -> None:
    with pytest.raises(TypeError, match="wrap_as_dataobject"):
        wrap_as_dataobject(None)
