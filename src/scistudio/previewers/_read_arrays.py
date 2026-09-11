"""Storage-sliced numeric reads and their transport representation (ADR-054)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class NumericRead:
    """A bounded numeric buffer with metadata shared by JSON and binary."""

    values: np.ndarray
    metadata: dict[str, Any]

    def to_bytes(self) -> bytes:
        return self.values.tobytes(order="C")

    def to_json(self) -> dict[str, Any]:
        values = self.values.tolist()
        if self.values.dtype.kind == "f":

            def safe(value: Any) -> Any:
                if isinstance(value, list):
                    return [safe(item) for item in value]
                return value if math.isfinite(value) else None

            values = safe(values)
        return {**self.metadata, "values": values}


def numeric_read(values: Any, metadata: dict[str, Any], max_bytes: int) -> NumericRead:
    """Preserve numeric dtype, normalizing only byte order and contiguity."""
    array = np.asarray(values)
    if array.dtype.kind not in "biuf":
        raise ValueError(f"Unsupported panel numeric dtype: {array.dtype}")
    if array.nbytes > max_bytes:
        raise ValueError(f"Numeric read exceeds the {max_bytes}-byte budget")
    array = np.ascontiguousarray(array, dtype=array.dtype.newbyteorder("<"))
    return NumericRead(array, {**metadata, "dtype": array.dtype.str, "shape": list(array.shape)})


@dataclass(frozen=True)
class PlaneSelection:
    """Select the displayed y/x axes without materializing the source."""

    handle: Any
    shape: list[int]
    axes: list[str]
    selector: list[Any]
    y: int
    x: int
    slice_axes: list[dict[str, Any]]

    @property
    def height(self) -> int:
        return self.shape[self.y] if len(self.shape) >= 2 else 1

    @property
    def width(self) -> int:
        return self.shape[self.x] if self.shape else 1

    def read(self, rows: slice, columns: slice) -> np.ndarray:
        selector = list(self.selector)
        if not self.shape:
            return np.asarray(self.handle[()]).reshape(1, 1)[rows, columns]
        if len(self.shape) == 1:
            return np.asarray(self.handle[columns]).reshape(1, -1)[rows, :]
        selector[self.y] = rows
        selector[self.x] = columns
        result = np.asarray(self.handle[tuple(selector)])
        return result.T if self.y > self.x else result


def select_plane(access: Any, ref: Any, slice_index: int, axis_indices: dict[int, int] | None) -> PlaneSelection:
    handle, shape, _ = access._open_array_handle(ref)
    axes = access._axes_from_ref(ref, shape)
    if len(axes) != len(shape) or len(set(axes)) != len(axes):
        axes = []
    ndim = len(shape)
    if ndim >= 2:
        y, x = (axes.index("y"), axes.index("x")) if "y" in axes and "x" in axes else (ndim - 2, ndim - 1)
    else:
        y = x = 0
    extra = [i for i in range(ndim) if i not in {y, x}]
    picks = dict(axis_indices or {})
    if any(axis not in extra for axis in picks):
        raise ValueError("axis_indices must address only non-displayed axes")
    if extra:
        picks.setdefault(extra[0], slice_index)
    selector: list[Any] = [slice(None)] * ndim
    slice_axes = []
    for axis in extra:
        if shape[axis] == 0:
            raise ValueError("Cannot select a plane along an empty axis")
        index = max(0, min(int(picks.get(axis, 0)), shape[axis] - 1))
        selector[axis] = index
        slice_axes.append(
            {"axis": axis, "name": axes[axis] if axes else f"axis {axis}", "size": shape[axis], "index": index}
        )
    return PlaneSelection(handle, shape, axes, selector, y, x, slice_axes)


def _extent(selection: PlaneSelection, byte_budget: int) -> tuple[float | None, float | None]:
    """Compute full-plane extrema in bounded tiles, including unsampled cells."""
    itemsize = max(8, np.dtype(selection.handle.dtype).itemsize)
    edge = max(1, min(256, math.isqrt(max(1, byte_budget // itemsize))))
    low = high = None
    for y in range(0, selection.height, edge):
        for x in range(0, selection.width, edge):
            tile = selection.read(slice(y, y + edge), slice(x, x + edge))
            finite = tile[np.isfinite(tile)]
            if finite.size:
                lo, hi = float(finite.min()), float(finite.max())
                low = lo if low is None else min(low, lo)
                high = hi if high is None else max(high, hi)
    return low, high


def read_plane(access: Any, ref: Any, slice_index: int, axis_indices: dict[int, int] | None) -> NumericRead:
    selection = select_plane(access, ref, slice_index, axis_indices)
    dtype = np.dtype(selection.handle.dtype)
    if dtype.kind not in "biuf":
        raise ValueError(f"Unsupported panel numeric dtype: {dtype}")
    max_cells = access.max_bytes // dtype.itemsize
    if max_cells < 1:
        raise ValueError("Numeric read byte budget is smaller than one value")
    edge = min(access.max_dim, max(1, math.isqrt(max_cells)))
    step_y, step_x = max(1, math.ceil(selection.height / edge)), max(1, math.ceil(selection.width / edge))
    values = selection.read(slice(0, selection.height, step_y), slice(0, selection.width, step_x))
    vmin, vmax = _extent(selection, access.max_bytes)
    sampled = step_y > 1 or step_x > 1
    return numeric_read(
        values,
        {
            "source_shape": selection.shape,
            "source_dtype": str(dtype),
            "axes": selection.axes,
            "slice_axes": selection.slice_axes,
            "vmin": vmin,
            "vmax": vmax,
            "sampled": sampled,
            "truncated": sampled,
            "complete": not sampled,
            "decimation": "stride" if sampled else "none",
            "strides": [step_y, step_x],
        },
        access.max_bytes,
    )


def read_tile(
    access: Any,
    ref: Any,
    *,
    slice_index: int,
    axis_indices: dict[int, int] | None,
    y0: int,
    x0: int,
    height: int | None,
    width: int | None,
) -> NumericRead:
    selection = select_plane(access, ref, slice_index, axis_indices)
    if y0 < 0 or x0 < 0 or y0 > selection.height or x0 > selection.width:
        raise ValueError("Tile offsets must be within the displayed plane")
    if (height is not None and height < 0) or (width is not None and width < 0):
        raise ValueError("Tile dimensions must be nonnegative")
    requested_h = selection.height - y0 if height is None else min(height, selection.height - y0)
    requested_w = selection.width - x0 if width is None else min(width, selection.width - x0)
    h, w = min(access.max_tile, requested_h), min(access.max_tile, requested_w)
    dtype = np.dtype(selection.handle.dtype)
    if h * w * dtype.itemsize > access.max_bytes:
        raise ValueError(f"Numeric read exceeds the {access.max_bytes}-byte budget")
    values = selection.read(slice(y0, y0 + h), slice(x0, x0 + w))
    truncated = h < requested_h or w < requested_w
    return numeric_read(
        values,
        {
            "source_shape": selection.shape,
            "source_dtype": str(dtype),
            "axes": selection.axes,
            "slice_axes": selection.slice_axes,
            "y0": y0,
            "x0": x0,
            "height": h,
            "width": w,
            "sampled": False,
            "truncated": truncated,
            "complete": not truncated,
        },
        access.max_bytes,
    )
