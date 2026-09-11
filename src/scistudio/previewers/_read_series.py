"""Bounded-memory, explicit uniform-index decimation for panel series."""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, OverflowError):
        return None


def _pairs(path: Path, metadata: dict[str, Any], batch_size: int) -> tuple[int, Iterable[tuple[Any, Any]]]:
    values = metadata.get("values")
    if isinstance(values, list) and values:
        return len(values), enumerate(values)
    if not path.exists() or path.suffix.lower() != ".parquet":
        return 0, iter(())
    import pyarrow.parquet as pq

    parquet = pq.ParquetFile(path)
    names = parquet.schema_arrow.names
    if not names:
        return 0, iter(())
    index, value = metadata.get("index_name"), metadata.get("value_name")
    columns = [index, value] if index in names and value in names else names[:2]

    def rows() -> Iterable[tuple[Any, Any]]:
        offset = 0
        for batch in parquet.iter_batches(batch_size=batch_size, columns=list(dict.fromkeys(columns))):
            if len(columns) == 1:
                for item in batch.column(0).to_pylist():
                    yield offset, item
                    offset += 1
            else:
                yield from zip(batch.column(columns[0]).to_pylist(), batch.column(columns[1]).to_pylist(), strict=True)

    return int(parquet.metadata.num_rows), rows()


def decimate(ref: Any, metadata: dict[str, Any], *, max_points: int, batch_size: int) -> dict[str, Any]:
    """Select evenly spaced source indices, retaining endpoints when budget > 1.

    Nonfinite rows are omitted, never replaced with zeros. Their count covers
    the entire source, which is streamed in bounded batches, not collected.
    """
    path = Path(ref.path)
    if ref.backend == "zarr" or path.suffix.lower() == ".zarr" or path.is_dir():
        raise ValueError("Series preview expects Arrow/Parquet storage; got Zarr/directory storage")
    total, pairs = _pairs(path, metadata, batch_size)
    limit = min(total, max_points)
    selected = {i * (total - 1) // (limit - 1) for i in range(limit)} if limit > 1 else {0} if limit else set()
    points, nonnumeric = [], 0
    for index, (raw_x, raw_y) in enumerate(pairs):
        x, y = _finite(raw_x), _finite(raw_y)
        if x is None or y is None:
            nonnumeric += 1
        elif index in selected:
            points.append({"x": x, "y": y})
    sampled = total > max_points
    return {
        "points": points,
        "total": total,
        "nonnumeric": nonnumeric,
        "sampled": sampled,
        "truncated": sampled,
        "complete": not sampled,
        "decimation": "uniform-index" if sampled else "none",
    }
