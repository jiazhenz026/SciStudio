"""Tests for wrap_as_dataobject() auto-detection (#1639)."""

from __future__ import annotations

import pytest

from scistudio.utils.wrapping import wrap_as_dataobject

# ---------------------------------------------------------------------------
# str → Text
# ---------------------------------------------------------------------------


def test_str_wraps_to_text() -> None:
    from scistudio.core.types.text import Text

    result = wrap_as_dataobject("hello world")
    assert isinstance(result, Text)
    assert result.content == "hello world"


def test_str_empty_wraps_to_text() -> None:
    from scistudio.core.types.text import Text

    result = wrap_as_dataobject("")
    assert isinstance(result, Text)
    assert result.content == ""


# ---------------------------------------------------------------------------
# numpy.ndarray → Array
# ---------------------------------------------------------------------------

numpy = pytest.importorskip("numpy", reason="numpy not installed")


def test_numpy_1d_wraps_to_array() -> None:
    import numpy as np

    from scistudio.core.types.array import Array

    arr = np.array([1.0, 2.0, 3.0])
    result = wrap_as_dataobject(arr)
    assert isinstance(result, Array)
    assert result.axes == ["dim_0"]
    assert result.shape == (3,)
    assert result.dtype == "float64"


def test_numpy_2d_wraps_to_array() -> None:
    import numpy as np

    from scistudio.core.types.array import Array

    arr = np.zeros((4, 5), dtype=np.int32)
    result = wrap_as_dataobject(arr)
    assert isinstance(result, Array)
    assert result.axes == ["dim_0", "dim_1"]
    assert result.shape == (4, 5)
    assert result.dtype == "int32"


def test_numpy_3d_axes_named_sequentially() -> None:
    import numpy as np

    arr = np.ones((2, 3, 4))
    result = wrap_as_dataobject(arr)
    assert result.axes == ["dim_0", "dim_1", "dim_2"]


def test_numpy_0d_wraps_to_scalar_array() -> None:
    import numpy as np

    from scistudio.core.types.array import Array

    arr = np.array(42)
    result = wrap_as_dataobject(arr)
    assert isinstance(result, Array)
    assert result.axes == []
    assert result.shape == ()


# ---------------------------------------------------------------------------
# pandas.DataFrame → DataFrame
# ---------------------------------------------------------------------------

pandas = pytest.importorskip("pandas", reason="pandas not installed")


def test_pandas_dataframe_wraps_to_dataframe() -> None:
    import pandas as pd

    from scistudio.core.types.dataframe import DataFrame

    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    result = wrap_as_dataobject(df)
    assert isinstance(result, DataFrame)
    assert result.columns == ["x", "y"]
    assert result.row_count == 2


def test_pandas_dataframe_empty_wraps_correctly() -> None:
    import pandas as pd

    from scistudio.core.types.dataframe import DataFrame

    df = pd.DataFrame()
    result = wrap_as_dataobject(df)
    assert isinstance(result, DataFrame)
    assert result.columns == []
    assert result.row_count == 0


# ---------------------------------------------------------------------------
# pandas.Series → Series
# ---------------------------------------------------------------------------


def test_pandas_series_wraps_to_series() -> None:
    import pandas as pd

    from scistudio.core.types.series import Series

    s = pd.Series([10, 20, 30], name="intensity")
    result = wrap_as_dataobject(s)
    assert isinstance(result, Series)
    assert result.value_name == "intensity"
    assert result.length == 3


def test_pandas_series_with_named_index() -> None:
    import pandas as pd

    from scistudio.core.types.series import Series

    idx = pd.Index([400.0, 500.0, 600.0], name="wavelength")
    s = pd.Series([0.1, 0.5, 0.3], index=idx, name="absorbance")
    result = wrap_as_dataobject(s)
    assert isinstance(result, Series)
    assert result.index_name == "wavelength"
    assert result.value_name == "absorbance"


def test_pandas_series_anonymous_index_and_value() -> None:
    import pandas as pd

    from scistudio.core.types.series import Series

    s = pd.Series([1, 2, 3])
    result = wrap_as_dataobject(s)
    assert isinstance(result, Series)
    assert result.index_name is None
    assert result.value_name is None


# ---------------------------------------------------------------------------
# Unsupported type → TypeError
# ---------------------------------------------------------------------------


def test_unsupported_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="Cannot wrap"):
        wrap_as_dataobject(42)


def test_unsupported_list_raises_type_error() -> None:
    with pytest.raises(TypeError, match="Cannot wrap"):
        wrap_as_dataobject([1, 2, 3])


def test_unsupported_dict_raises_type_error() -> None:
    with pytest.raises(TypeError, match="Cannot wrap"):
        wrap_as_dataobject({"a": 1})
