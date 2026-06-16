"""wrap_as_dataobject() -- auto-detect DataObject type from raw data."""

from __future__ import annotations

from typing import Any


def wrap_as_dataobject(data: Any) -> Any:
    """Auto-detect the appropriate DataObject subtype for *data* and wrap it.

    Dispatch rules (checked in order):

    - :class:`~scistudio.core.types.base.DataObject` instance → returned unchanged.
    - ``numpy.ndarray`` → :class:`~scistudio.core.types.array.Array`
      with generated axes ``["dim_0", ..., "dim_N"]``.
    - ``pandas.DataFrame`` → :class:`~scistudio.core.types.dataframe.DataFrame`
      with ``columns``, ``row_count``, and ``data`` populated.
    - ``pandas.Series`` → :class:`~scistudio.core.types.series.Series`
      with ``index_name``, ``value_name``, ``length``, and ``data`` populated.
    - ``str`` → :class:`~scistudio.core.types.text.Text` with ``content`` set.

    Raises:
        TypeError: when *data* is not one of the recognised types.
    """
    from scistudio.core.types.base import DataObject

    if isinstance(data, DataObject):
        return data

    if isinstance(data, str):
        from scistudio.core.types.text import Text

        return Text(content=data)

    try:
        import numpy as np

        if isinstance(data, np.ndarray):
            from scistudio.core.types.array import Array

            axes = [f"dim_{i}" for i in range(data.ndim)]
            return Array(
                axes=axes,
                shape=data.shape,
                dtype=data.dtype,
                data=data,
            )
    except ImportError:
        pass

    try:
        import pandas as pd

        if isinstance(data, pd.DataFrame):
            from scistudio.core.types.dataframe import DataFrame

            return DataFrame(
                columns=list(data.columns.astype(str)),
                row_count=len(data),
                data=data,
            )

        if isinstance(data, pd.Series):
            from scistudio.core.types.series import Series

            index_name = str(data.index.name) if data.index.name is not None else None
            value_name = str(data.name) if data.name is not None else None
            return Series(
                index_name=index_name,
                value_name=value_name,
                length=len(data),
                data=data,
            )
    except ImportError:
        pass

    raise TypeError(
        f"wrap_as_dataobject() cannot auto-detect a DataObject subtype for "
        f"{type(data).__name__!r}. Pass a numpy ndarray, pandas DataFrame or "
        f"Series, str, or an existing DataObject."
    )
