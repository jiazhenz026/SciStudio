"""broadcast_apply() -- named-axis-aware broadcast of arrays."""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterator
from typing import Any

import numpy as np

_MEMORY_WARN_BYTES: int = 2 * 1024**3  # 2 GB


class BroadcastError(Exception):
    """Raised when axis alignment fails during broadcast."""


def iter_axis_slices(
    data: np.ndarray,  # type: ignore[type-arg]
    axes: list[str],
    over_axis: str,
) -> Iterator[tuple[int, np.ndarray]]:  # type: ignore[type-arg]
    """Yield ``(index, slice)`` pairs by iterating over *over_axis*.

    Args:
        data: The N-dimensional array to iterate.
        axes: Named axis labels for *data* (length must match ``data.ndim``).
        over_axis: The axis name to iterate over.

    Raises:
        BroadcastError: If *over_axis* is not found in *axes*.
    """
    if over_axis not in axes:
        raise BroadcastError(f"Axis '{over_axis}' not found in axes {axes}.")
    axis_idx = axes.index(over_axis)
    for i in range(data.shape[axis_idx]):
        idx: list[Any] = [slice(None)] * data.ndim
        idx[axis_idx] = i
        yield i, data[tuple(idx)]


def broadcast_apply(
    source: Any,
    target: Any,
    func: Callable[..., Any],
    over_axes: list[str],
) -> list[Any]:
    """Apply a lower-dim array to a higher-dim array along named axes.

    Iterates over *over_axes* in the target, extracting slices that share
    the remaining axes with source, and calls *func* on each pair.

    Args:
        source: A lower-dimensional array. Must have an ``axes`` attribute
            (list of axis name strings) or be a plain ndarray used without
            axis validation.
        target: A higher-dimensional array to iterate over.
        func: A callable ``func(source_data, target_slice) -> result``.
        over_axes: Axis names in target to iterate over.

    Returns:
        A list of results, one per slice along *over_axes*.

    Raises:
        BroadcastError: If source axes are not a subset of
            target axes minus *over_axes*.

    .. note::
        This is an **in-memory-only** utility. Both *source* and *target*
        are fully materialised via ``np.asarray()`` before processing.
        For datasets exceeding 2 GB, consider using ``DataObject.iter_chunks()``
        to process data in manageable pieces.
    """
    source_data = np.asarray(source)
    target_data = np.asarray(target)

    # Memory guard: warn if combined array size exceeds threshold.
    total_bytes = source_data.nbytes + target_data.nbytes
    if total_bytes > _MEMORY_WARN_BYTES:
        warnings.warn(
            f"broadcast_apply: combined input size is {total_bytes / 1024**3:.1f} GB, "
            f"exceeding the {_MEMORY_WARN_BYTES / 1024**3:.0f} GB threshold. "
            f"Consider using DataObject.iter_chunks() for large datasets.",
            ResourceWarning,
            stacklevel=2,
        )

    # Get axis names
    source_axes: list[str] | None = getattr(source, "axes", None)
    target_axes: list[str] | None = getattr(target, "axes", None)

    if target_axes is None:
        raise BroadcastError("Target must have named axes for broadcast_apply.")

    if len(target_axes) != target_data.ndim:
        raise BroadcastError(
            f"Target axes length ({len(target_axes)}) does not match target ndim ({target_data.ndim})."
        )

    # Validate over_axes exist in target
    for ax in over_axes:
        if ax not in target_axes:
            raise BroadcastError(f"over_axis '{ax}' not found in target axes {target_axes}.")

    # The remaining axes after removing over_axes
    remaining_axes = [ax for ax in target_axes if ax not in over_axes]

    # Validate source axes are a subset of remaining axes
    if source_axes is not None:
        source_set = set(source_axes)
        remaining_set = set(remaining_axes)
        if not source_set.issubset(remaining_set):
            raise BroadcastError(
                f"Source axes {source_axes} are not a subset of target axes minus over_axes {remaining_axes}."
            )

    # Build iteration: iterate over all combinations of over_axes
    over_axis_indices = [target_axes.index(ax) for ax in over_axes]
    over_axis_sizes = [target_data.shape[i] for i in over_axis_indices]

    results: list[Any] = []
    # Use np.ndindex to iterate over the over_axes dimensions
    for idx in np.ndindex(*over_axis_sizes):
        slicing: list[Any] = [slice(None)] * target_data.ndim
        for value, dim_idx in zip(idx, over_axis_indices, strict=True):
            slicing[dim_idx] = value
        target_slice = target_data[tuple(slicing)]
        results.append(func(source_data, target_slice))

    return results
