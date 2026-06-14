"""Internal table helpers for spectroscopy package data objects."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pyarrow as pa

from scistudio.core.types.dataframe import DataFrame


def to_pandas_frame(table: DataFrame) -> pd.DataFrame:
    """Return a copy of *table* as a pandas DataFrame.

    The helper accepts the in-memory payloads used by package tests and the
    Arrow table payloads produced by SciStudio storage reads.
    """

    data = table.get_in_memory_data()
    if isinstance(data, pd.DataFrame):
        return data.copy()
    if isinstance(data, pa.Table):
        return data.to_pandas()
    if isinstance(data, dict):
        return pd.DataFrame(data)
    if isinstance(data, list):
        return pd.DataFrame(data)
    if hasattr(data, "to_pandas"):
        return data.to_pandas()
    return pd.DataFrame(data)


def dataframe_from_pandas(
    frame: pd.DataFrame,
    *,
    dataframe_type: type[DataFrame] = DataFrame,
    meta: Any = None,
    user: dict[str, Any] | None = None,
) -> DataFrame:
    """Build a SciStudio DataFrame object from a pandas DataFrame."""

    clean = frame.reset_index(drop=True).copy()
    clean.columns = [str(column) for column in clean.columns]
    arrow_table = pa.Table.from_pandas(clean, preserve_index=False)
    return dataframe_type(
        columns=list(clean.columns),
        row_count=len(clean),
        schema={str(column): str(dtype) for column, dtype in clean.dtypes.items()},
        meta=meta,
        user=user,
        data=arrow_table,
    )


def table_columns(table: DataFrame) -> list[str]:
    """Return declared or materialized column names for *table*."""

    if table.columns:
        return [str(column) for column in table.columns]
    return [str(column) for column in to_pandas_frame(table).columns]
