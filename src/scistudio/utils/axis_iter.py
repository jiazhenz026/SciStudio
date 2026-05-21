"""scistudio.utils.axis_iter — single-Array extra-axis iteration utility.

Implements ADR-027 D3 (``iterate_over_axes``). The function iterates a
caller-supplied ``func`` over all axes in a source :class:`Array` that
are *not* in ``operates_on``, applying ``func`` to each slice and
stacking the results back into a new instance of the source's concrete
class.

This is the common case for 5D / 6D imaging blocks: "I know how to
process ``(y, x)``, please loop over everything else (``t``, ``z``,
``c``, ...)". The sister utility
:func:`scistudio.utils.broadcast.broadcast_apply` covers the complementary
cross-modal case (a low-dim source projected onto a high-dim target
along named axes).

Memory: O(one input slice + one output slice). Serial by design — no
threads, no asyncio, no multiprocessing (ADR-027 D3 §"Memory" / D8).
Errors raised inside the user-provided ``func`` propagate unchanged and
are NOT wrapped in :class:`BroadcastError`.

Metadata propagation follows ADR-027 D5:

- ``framework``: regenerated via ``source.framework.derive()`` (which
  sets ``derived_from=source.framework.object_id`` by default and gives
  the result a fresh ``object_id`` / ``created_at``).
- ``meta``: shared by reference (Pydantic models are frozen).
- ``user``: shallow copy.
- ``axes``: same as ``source.axes`` — results are stacked back onto the
  original shape so no axis is added or removed. ``func`` must therefore
  return an array whose number of dimensions equals ``len(operates_on)``;
  this is validated explicitly and a mismatch raises
  :class:`BroadcastError`.

Note on ``BroadcastError``: ADR-027 D3's pseudocode imports from
``scistudio.core.exceptions``, but that module does not (yet) exist. The
sibling :mod:`scistudio.utils.broadcast` already defines
:class:`BroadcastError`, so this module imports it from there. Keeping
the two utilities' error type identical is explicitly desirable: a
caller wiring these together wants the same ``except BroadcastError:``
clause to catch both.
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import product
from typing import TYPE_CHECKING, Any

import numpy as np

from scistudio.utils.broadcast import BroadcastError

if TYPE_CHECKING:
    from scistudio.core.types.array import Array


# Type alias for the user-supplied per-slice function. It receives the
# slice data (a numpy array containing only the ``operates_on``
# dimensions, in the order they appear in ``source.axes``) and a
# coordinate dict mapping each extra-axis name to its current integer
# index. It must return a numpy array whose shape is consistent across
# all slices (otherwise :class:`BroadcastError` is raised at stack time).
SliceFn = Callable[[np.ndarray, dict[str, int]], np.ndarray]


def iterate_over_axes(
    source: Array,
    operates_on: set[str] | frozenset[str],
    func: SliceFn,
) -> Array:
    """Iterate ``func`` over every axis in ``source`` not in ``operates_on``.

    For each combination of the non-``operates_on`` axis indices, calls::

        func(slice_data, slice_coord)

    where ``slice_data`` is a numpy array containing only the
    ``operates_on`` dimensions (in the order they appear in
    ``source.axes``) and ``slice_coord`` is a dict mapping each
    extra-axis name to its current integer index.

    Results are stacked back into a new instance of ``type(source)``,
    preserving ``axes`` and ``shape`` and propagating metadata per
    ADR-027 D5: ``framework`` is derived (lineage hint back to parent),
    ``meta`` is shared by reference (Pydantic models are frozen), and
    ``user`` is shallow-copied.

    Example::

        # source: FluorImage(axes=["t", "z", "c", "y", "x"],
        #                    shape=(10, 30, 4, 512, 512))
        # operates_on = {"y", "x"}
        # -> 10 * 30 * 4 = 1200 calls to func, each with a (512, 512) slice
        result = iterate_over_axes(
            source, {"y", "x"},
            lambda slice_2d, coord: gaussian_filter(slice_2d, sigma=1.0),
        )
        # result has the same axes and shape as source.

    Args:
        source: An :class:`Array` (or subclass) with ``.axes``,
            ``.shape``, and ``.to_memory()``. Must have a known shape.
        operates_on: Set of axis names that ``func`` knows how to
            handle. Must be a subset of ``source.axes``.
        func: Callable that receives a numpy slice and a coord dict and
            returns a transformed numpy array. All returned arrays must
            have the same shape so they can be stacked back into a
            single array, and must have exactly ``len(operates_on)``
            dimensions.

    Returns:
        A new instance of ``type(source)`` with the same ``axes`` as
        ``source``, shape ``source_extra_shape + func_output_shape``
        (which equals ``source.shape`` when ``func`` preserves each
        slice's shape), dtype inferred from the first slice's result,
        and metadata propagated per ADR-027 D5.

    Raises:
        BroadcastError: if ``operates_on`` is not a subset of
            ``source.axes``; if ``source.shape`` is ``None``; if any
            pair of slice outputs have different shapes; or if ``func``
            returns an array whose number of dimensions differs from
            ``len(operates_on)``.

    Note:
        This function is serial by design. Block-internal parallelism
        is the block author's choice per ADR-027 D8 / D13 and is
        explicitly forbidden inside this utility.
    """
    operates_on_fs = frozenset(operates_on)

    # 1. Validate ``operates_on`` is a subset of ``source.axes``.
    source_axes_set = set(source.axes)
    if not operates_on_fs.issubset(source_axes_set):
        missing = sorted(operates_on_fs - source_axes_set)
        raise BroadcastError(
            f"iterate_over_axes: operates_on {sorted(operates_on_fs)} is not "
            f"a subset of source.axes {source.axes} (missing: {missing})"
        )

    # 2. Refuse metadata-only sources — we cannot iterate without sizes.
    if source.shape is None:
        raise BroadcastError(f"iterate_over_axes: source.shape is required, but {type(source).__name__} has shape=None")

    # 3. Identify extra (iterated) axes and the in-``operates_on`` axes,
    # both in ``source.axes`` order so numpy indexing stays consistent.
    extra_axes: list[str] = [a for a in source.axes if a not in operates_on_fs]
    extra_sizes: list[int] = [source.shape[source.axes.index(a)] for a in extra_axes]
    operates_axes_in_order: list[str] = [a for a in source.axes if a in operates_on_fs]

    # 4. Materialise source data once. Per ADR-027 D4 this is the
    # Phase 10 Level 1 path; lazy Zarr partial-reads are deferred.
    source_data = source.to_memory()
    source_arr = np.asarray(source_data)

    # 5. Fast path: no extra axes — call ``func`` once with the full
    # array and an empty coord dict.
    if not extra_axes:
        result_slice = func(source_arr, {})
        result_arr = np.asarray(result_slice)
        if result_arr.ndim != len(operates_axes_in_order):
            raise BroadcastError(
                f"iterate_over_axes: func must return arrays with "
                f"{len(operates_axes_in_order)} dimensions (len(operates_on)), "
                f"but got an array with {result_arr.ndim} dimensions."
            )
        return _build_result(source, result_arr)

    # 6. Iterate the cartesian product of extra-axis indices.
    first_slice_shape: tuple[int, ...] | None = None
    first_slice_dtype: Any = None
    result_full: np.ndarray | None = None

    for extra_idx in product(*(range(s) for s in extra_sizes)):
        coord: dict[str, int] = dict(zip(extra_axes, extra_idx, strict=True))

        # Build a numpy index that pins the current extra-axis values
        # and keeps the operates_on axes as full slices.
        index: list[int | slice] = []
        for axis_name in source.axes:
            if axis_name in operates_on_fs:
                index.append(slice(None))
            else:
                index.append(coord[axis_name])

        slice_data = source_arr[tuple(index)]
        result_slice = func(slice_data, coord)
        result_arr = np.asarray(result_slice)

        if first_slice_shape is None:
            # First slice defines the expected per-slice shape + dtype.
            if result_arr.ndim != len(operates_axes_in_order):
                raise BroadcastError(
                    f"iterate_over_axes: func must return arrays with "
                    f"{len(operates_axes_in_order)} dimensions "
                    f"(len(operates_on)), but got an array with "
                    f"{result_arr.ndim} dimensions at coord {coord}."
                )
            first_slice_shape = result_arr.shape
            first_slice_dtype = result_arr.dtype
            # Pre-allocate the full output now that we know the slice shape.
            result_full = np.empty(
                tuple(extra_sizes) + first_slice_shape,
                dtype=first_slice_dtype,
            )
        elif result_arr.shape != first_slice_shape:
            raise BroadcastError(
                f"iterate_over_axes: slice outputs must all have the same "
                f"shape. First was {first_slice_shape}, but got "
                f"{result_arr.shape} at coord {coord}."
            )

        # ``result_full`` is guaranteed non-None after the first-slice
        # branch above, but mypy needs the assertion.
        assert result_full is not None
        result_full[extra_idx] = result_arr

    # 7. ``result_full`` is populated because ``extra_sizes`` was
    # non-empty and contained at least one index (the product of
    # non-zero ranges is non-empty). Zero-sized axes would produce an
    # empty iterator; guard that explicitly for clarity.
    if result_full is None:
        # At least one extra axis had size zero. Construct an empty
        # output of the right shape by calling ``func`` on a synthetic
        # zero-filled slice to learn the per-slice output shape would
        # require extra machinery we don't want here; instead, use the
        # source's per-slice shape (operates_on dims) which is the
        # natural identity for "no iterations happened".
        operates_shape = tuple(source.shape[source.axes.index(a)] for a in operates_axes_in_order)
        result_full = np.empty(
            tuple(extra_sizes) + operates_shape,
            dtype=source_arr.dtype,
        )

    return _build_result(source, result_full)


def _build_result(source: Array, data: np.ndarray) -> Array:
    """Construct a new ``type(source)`` instance with propagated metadata.

    Implements the ADR-027 D5 propagation rule used by
    :func:`iterate_over_axes`:

    - ``framework``: new, derived from ``source.framework`` (carries
      ``derived_from=source.framework.object_id`` and a fresh
      ``object_id`` / ``created_at``).
    - ``meta``: shared by reference (Pydantic models are frozen).
    - ``user``: shallow-copied.
    - ``axes``: same as ``source.axes``.
    - ``shape`` / ``dtype``: taken from ``data``.

    ADR-031 D3: the result is persisted to a zarr store and returned
    with ``storage_ref`` set. The former ``_data`` stashing pattern is
    eliminated.

    The private attributes ``_framework``, ``_meta``, and ``_user`` are
    accessed with explicit ``# type: ignore[attr-defined]`` comments
    rather than via the public ``.framework`` / ``.meta`` / ``.user``
    properties because the properties return read-only views while the
    construction path needs the raw slots.
    """
    import tempfile
    import uuid
    from pathlib import Path

    import zarr

    from scistudio.core.storage.flush_context import get_output_dir
    from scistudio.core.storage.ref import StorageReference

    new_framework = source._framework.derive()  # type: ignore[attr-defined]

    # Persist to zarr and set storage_ref.
    output_dir = get_output_dir()
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="scistudio_axis_iter_")
    zarr_path = str(Path(output_dir) / f"{uuid.uuid4()}.zarr")
    zarr.save(zarr_path, data)  # type: ignore[arg-type]
    ref = StorageReference(
        backend="zarr",
        path=zarr_path,
        metadata={"shape": list(data.shape), "dtype": str(data.dtype)},
    )

    result = type(source)(
        axes=list(source.axes),
        shape=tuple(data.shape),
        dtype=data.dtype,
        chunk_shape=source.chunk_shape,
        framework=new_framework,
        meta=source._meta,  # type: ignore[attr-defined]
        user=dict(source._user),  # type: ignore[attr-defined]
        storage_ref=ref,
    )
    return result


__all__ = ["SliceFn", "iterate_over_axes"]
