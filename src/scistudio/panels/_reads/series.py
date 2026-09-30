"""Paged, exact x/y reads for panel series and table point reads."""
# Development references: ADR-054, #1886, #2460.
#
# A panel never sees a sample of a series. A read names a window of source rows
# (``offset``, ``limit``) and receives every row in it, in source order, with its
# value as stored: a NaN, an infinity, or a missing cell comes back in place as
# NaN (or the distinct JSON sentinels) rather than being dropped. The row at
# position ``i`` of a window is source row ``offset + i``, so a consumer never
# has to reconstruct where a point came from, and the whole source is reached by
# following ``next_offset`` until it is ``None``.

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np


def _number(value: Any) -> float:
    """The value as a float, or NaN when it is not a number at all."""
    if value is None or isinstance(value, (str, bytes)):
        return math.nan
    try:
        return float(value)
    except (ValueError, TypeError, OverflowError):
        return math.nan


def _validate_window(offset: int, limit: int) -> None:
    if offset < 0:
        raise ValueError("offset must be nonnegative")
    if limit < 1:
        raise ValueError("limit must be positive")


def _parquet_window(path: Path, columns: list[str], offset: int, stop: int) -> list[list[Any]]:
    """Read source rows ``[offset, stop)`` of *columns*, touching only their row groups."""
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    out: list[list[Any]] = [[] for _ in columns]
    start = 0
    for group in range(parquet.metadata.num_row_groups):
        rows = parquet.metadata.row_group(group).num_rows
        end = start + rows
        if end > offset and start < stop:
            table = parquet.read_row_group(group, columns=columns)
            lo, hi = max(offset, start) - start, min(stop, end) - start
            for position, name in enumerate(columns):
                out[position].extend(table.column(name).slice(lo, hi - lo).to_pylist())
        if end >= stop:
            break
        start = end
    return out


def read_xy_window(
    path: Path,
    metadata: dict[str, Any],
    *,
    x_column: str | None,
    y_column: str | None,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    """Return the exact x/y rows of one source window.

    With two named columns (or at least two columns in the file) the x values
    come from the first and the y values from the second. A single-column table,
    or in-memory ``metadata['values']``, is plotted against its source position.
    """
    _validate_window(offset, limit)
    values = metadata.get("values") if isinstance(metadata, dict) else None
    if isinstance(values, list) and values:
        total = len(values)
        stop = min(total, offset + limit)
        window = values[offset:stop]
        xs = [float(offset + i) for i in range(len(window))]
        ys = [_number(v) for v in window]
        columns: list[str] = []
        x_name = y_name = None
    elif path.exists() and path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq

        parquet = pq.ParquetFile(path)
        columns = list(parquet.schema_arrow.names)
        total = int(parquet.metadata.num_rows)
        stop = min(total, offset + limit)
        if not columns:
            xs, ys, x_name, y_name = [], [], None, None
        elif len(columns) == 1:
            x_name, y_name = None, columns[0]
            (raw,) = _parquet_window(path, [y_name], offset, stop) if stop > offset else ([],)
            xs = [float(offset + i) for i in range(len(raw))]
            ys = [_number(v) for v in raw]
        else:
            x_name = x_column if x_column in columns else columns[0]
            y_name = y_column if y_column in columns else columns[1]
            wanted = list(dict.fromkeys([x_name, y_name]))
            raw_columns = _parquet_window(path, wanted, offset, stop) if stop > offset else [[] for _ in wanted]
            by_name = dict(zip(wanted, raw_columns, strict=True))
            xs = [_number(v) for v in by_name[x_name]]
            ys = [_number(v) for v in by_name[y_name]]
    else:
        total, stop, xs, ys, columns, x_name, y_name = 0, 0, [], [], [], None, None
    if offset > total:
        raise ValueError("offset is beyond the end of the source")
    pairs = np.column_stack([np.asarray(xs, dtype="<f8"), np.asarray(ys, dtype="<f8")]) if xs else np.empty((0, 2))
    next_offset = stop if stop < total else None
    nonnumeric = int((~np.isfinite(pairs)).any(axis=1).sum()) if len(pairs) else 0
    return {
        "values": pairs.astype("<f8"),
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset,
        "total": total,
        "nonnumeric": nonnumeric,
        "columns": columns,
        "x_column": x_name,
        "y_column": y_name,
        "truncated": next_offset is not None,
        "complete": next_offset is None,
    }
