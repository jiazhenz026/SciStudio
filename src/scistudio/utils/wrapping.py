"""wrap_as_dataobject() -- auto-detect DataObject type from raw data."""

from __future__ import annotations

from typing import Any


def wrap_as_dataobject(data: Any) -> Any:
    """Auto-detect the appropriate DataObject subtype for *data* and wrap it.

    Handles:
    - ``str`` → :class:`~scistudio.core.types.text.Text`
    - ``numpy.ndarray`` → :class:`~scistudio.core.types.array.Array`
    - ``pandas.DataFrame`` → :class:`~scistudio.core.types.dataframe.DataFrame`
    - ``pandas.Series`` → :class:`~scistudio.core.types.series.Series`

    numpy and pandas are soft dependencies; their absence does not affect
    wrapping of the other supported types.

    Raises:
        TypeError: when *data* cannot be mapped to any known DataObject subtype.
    """
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
                shape=tuple(data.shape),
                dtype=str(data.dtype),
                data=data,
            )
    except ImportError:
        pass

    try:
        import pandas as pd

        if isinstance(data, pd.DataFrame):
            from scistudio.core.types.dataframe import DataFrame

            return DataFrame(
                columns=[str(c) for c in data.columns],
                row_count=len(data),
                data=data,
            )
        if isinstance(data, pd.Series):
            from scistudio.core.types.series import Series

            return Series(
                index_name=str(data.index.name) if data.index.name is not None else None,
                value_name=str(data.name) if data.name is not None else None,
                length=len(data),
                data=data,
            )
    except ImportError:
        pass

    raise TypeError(
        f"Cannot wrap {type(data).__qualname__!r} as a DataObject: no mapping "
        f"for this type. Supported raw types: str, numpy.ndarray, "
        f"pandas.DataFrame, pandas.Series."
    )
