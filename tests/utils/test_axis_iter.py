"""Tests for ``scistudio.utils.axis_iter.iterate_over_axes``.

Covers T-011 per ADR-027 D3 and the T-011 section of
``docs/specs/phase10-implementation-standards.md``.

The 13 tests below map to the acceptance criteria in the standards doc
T-011 section plus a few edge cases the implementation contract calls
out explicitly (empty extra axes, func reducing dim count, subclass
preservation, metadata propagation per ADR-027 D5).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from pydantic import BaseModel, ConfigDict

from scistudio.core.meta import FrameworkMeta
from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.utils.axis_iter import iterate_over_axes
from scistudio.utils.broadcast import BroadcastError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_array(
    axes: list[str],
    shape: tuple[int, ...],
    *,
    fill: float | None = None,
    dtype: Any = np.float32,
    data: np.ndarray | None = None,
    meta: BaseModel | None = None,
    user: dict[str, Any] | None = None,
    array_cls: type[Array] = Array,
) -> Array:
    """Build an Array with an in-memory ``_data`` stash.

    Mirrors the T-006 ``Array.sel()`` pattern: the instance is
    constructed without a storage_ref but with ``_data`` populated, so
    ``to_memory()`` returns the array directly.
    """
    if data is None:
        if fill is not None:
            data = np.full(shape, fill, dtype=dtype)
        else:
            data = np.arange(int(np.prod(shape)), dtype=dtype).reshape(shape)
    arr = array_cls(
        axes=axes,
        shape=shape,
        dtype=data.dtype,
        meta=meta,
        user=user,
    )
    arr._data = data  # type: ignore[attr-defined]
    return arr


def _make_zarr_array(tmp_path: Any, axes: list[str], data: np.ndarray, *, chunks: tuple[int, ...]) -> Array:
    zarr = pytest.importorskip("zarr")

    zarr_path = tmp_path / "source.zarr"
    writer = zarr.open_array(
        str(zarr_path),
        mode="w",
        shape=data.shape,
        chunks=chunks,
        dtype=data.dtype,
    )
    writer[:] = data
    ref = StorageReference(
        backend="zarr",
        path=str(zarr_path),
        metadata={"shape": list(data.shape), "dtype": str(data.dtype)},
    )
    return Array(
        axes=axes,
        shape=data.shape,
        dtype=data.dtype,
        chunk_shape=chunks,
        storage_ref=ref,
    )


class _SubclassArray(Array):
    """Test-only Array subclass with a tightened required_axes schema.

    Used by ``test_iterate_over_axes_returns_same_class`` to verify that
    ``iterate_over_axes`` returns a ``type(source)`` instance rather than
    a plain ``Array``. The required_axes set matches the 2D pattern used
    in the test to avoid validation failures.
    """

    required_axes = frozenset({"y", "x"})


class _DummyMeta(BaseModel):
    """Minimal frozen Pydantic model used to exercise the ``meta`` slot.

    ADR-027 D5 requires the meta slot to be a Pydantic BaseModel (or
    ``None``); any domain plugin would provide a richer model.
    """

    model_config = ConfigDict(frozen=True)

    label: str = "test"


# ---------------------------------------------------------------------------
# Core iteration behaviour
# ---------------------------------------------------------------------------


def test_iterate_over_axes_3d_input_iterate_z() -> None:
    """3D (z, y, x) source with operates_on={y, x} -> 5 func calls."""
    src = _make_array(["z", "y", "x"], (5, 10, 10), fill=1.0)

    calls: list[dict[str, int]] = []

    def identity(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        calls.append(dict(coord))
        return slice_data

    result = iterate_over_axes(src, {"y", "x"}, identity)

    assert len(calls) == 5
    assert result.axes == ["z", "y", "x"]
    assert result.shape == (5, 10, 10)
    np.testing.assert_array_equal(np.asarray(result), np.asarray(src))


def test_iterate_over_axes_2d_no_extra_dims() -> None:
    """operates_on covers all axes -> func called once with empty coord."""
    src = _make_array(["y", "x"], (4, 5), fill=7.0)

    calls: list[dict[str, int]] = []

    def recorder(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        calls.append(dict(coord))
        assert slice_data.shape == (4, 5)
        return slice_data * 2

    result = iterate_over_axes(src, {"y", "x"}, recorder)

    assert calls == [{}]
    assert result.axes == ["y", "x"]
    assert result.shape == (4, 5)
    np.testing.assert_array_equal(np.asarray(result), np.full((4, 5), 14.0, dtype=np.float32))


def test_iterate_over_axes_5d_input() -> None:
    """5D (t, z, c, y, x) with operates_on={y, x} -> 2*3*4 = 24 calls."""
    src = _make_array(["t", "z", "c", "y", "x"], (2, 3, 4, 10, 10))

    call_count = 0
    seen_shapes: set[tuple[int, ...]] = set()

    def counter(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        nonlocal call_count
        call_count += 1
        seen_shapes.add(slice_data.shape)
        return slice_data

    result = iterate_over_axes(src, {"y", "x"}, counter)

    assert call_count == 24
    assert seen_shapes == {(10, 10)}
    assert result.axes == ["t", "z", "c", "y", "x"]
    assert result.shape == (2, 3, 4, 10, 10)


def test_iterate_over_axes_func_modifies_data() -> None:
    """Func that multiplies by 2 -> result data is 2x source data."""
    src = _make_array(["t", "y", "x"], (3, 4, 5), fill=1.5)

    def double(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        return slice_data * 2

    result = iterate_over_axes(src, {"y", "x"}, double)

    assert result.shape == (3, 4, 5)
    np.testing.assert_array_equal(
        np.asarray(result),
        np.full((3, 4, 5), 3.0, dtype=np.float32),
    )


def test_iterate_over_axes_func_changes_dtype() -> None:
    """Func that casts to float32 -> result.dtype reflects func output."""
    src = _make_array(
        ["z", "y", "x"],
        (2, 3, 3),
        data=np.arange(18, dtype=np.int32).reshape(2, 3, 3),
    )

    def to_float(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        return slice_data.astype(np.float32) + 0.5

    result = iterate_over_axes(src, {"y", "x"}, to_float)

    assert result.dtype == np.float32
    out = np.asarray(result)
    np.testing.assert_allclose(
        out,
        np.arange(18, dtype=np.float32).reshape(2, 3, 3) + 0.5,
    )


def test_iterate_over_axes_coord_dict_correct() -> None:
    """Coords cover the cartesian product of extra-axis index ranges."""
    src = _make_array(["t", "c", "y", "x"], (2, 3, 4, 5))

    coords_seen: list[dict[str, int]] = []

    def capture(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        coords_seen.append(dict(coord))
        return slice_data

    iterate_over_axes(src, {"y", "x"}, capture)

    expected = [{"t": t, "c": c} for t in range(2) for c in range(3)]
    assert coords_seen == expected


def test_iterate_over_axes_zarr_reads_per_slice_without_source_to_memory(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zarr-backed sources use partial reads instead of full materialisation."""
    data = np.arange(2 * 3 * 4 * 5, dtype=np.float32).reshape(2, 3, 4, 5)
    src = _make_zarr_array(tmp_path, ["t", "z", "y", "x"], data, chunks=(1, 1, 4, 5))

    def fail_source_to_memory() -> np.ndarray:
        raise AssertionError("source.to_memory() must not be called for Zarr-backed iterate_over_axes")

    monkeypatch.setattr(src, "to_memory", fail_source_to_memory)

    from scistudio.core.storage.zarr_backend import ZarrBackend

    original_slice = ZarrBackend.slice
    slice_calls: list[tuple[Any, ...]] = []

    def spy_slice(self: ZarrBackend, ref: StorageReference, *args: Any) -> Any:
        slice_calls.append(args)
        return original_slice(self, ref, *args)

    monkeypatch.setattr(ZarrBackend, "slice", spy_slice)

    seen_coords: list[dict[str, int]] = []

    def double(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        seen_coords.append(dict(coord))
        assert slice_data.shape == (4, 5)
        return slice_data * 2

    result = iterate_over_axes(src, {"y", "x"}, double)

    assert seen_coords == [{"t": t, "z": z} for t in range(2) for z in range(3)]
    assert len(slice_calls) == 6
    assert all(call[0] in {0, 1} and call[1] in {0, 1, 2} for call in slice_calls)
    assert all(call[2:] == (slice(None), slice(None)) for call in slice_calls)
    assert result.storage_ref is not None
    assert result.storage_ref.backend == "zarr"
    np.testing.assert_array_equal(np.asarray(result), data * 2)


# ---------------------------------------------------------------------------
# Error paths — BroadcastError surface
# ---------------------------------------------------------------------------


def test_iterate_over_axes_invalid_operates_on_raises() -> None:
    """operates_on containing an axis not in source.axes -> BroadcastError."""
    src = _make_array(["z", "y", "x"], (2, 3, 3))

    with pytest.raises(BroadcastError, match="not a subset"):
        iterate_over_axes(src, {"foo"}, lambda s, c: s)


def test_iterate_over_axes_partial_invalid_operates_on_raises() -> None:
    """operates_on={valid, invalid} -> BroadcastError names the missing one."""
    src = _make_array(["z", "y", "x"], (2, 3, 3))

    with pytest.raises(BroadcastError, match=r"missing: \['bogus'\]"):
        iterate_over_axes(src, {"y", "bogus"}, lambda s, c: s)


def test_iterate_over_axes_no_shape_raises() -> None:
    """source with shape=None -> BroadcastError (cannot iterate)."""
    src = Array(axes=["z", "y", "x"], shape=None, dtype=np.float32)

    with pytest.raises(BroadcastError, match="shape"):
        iterate_over_axes(src, {"y", "x"}, lambda s, c: s)


def test_iterate_over_axes_inconsistent_slice_shapes_raises() -> None:
    """Func that returns differently-shaped slices -> BroadcastError."""
    src = _make_array(["z", "y", "x"], (3, 4, 5))

    def inconsistent(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        # First slice returned at full shape, subsequent slices cropped.
        if coord["z"] == 0:
            return slice_data
        return slice_data[:2, :2]

    with pytest.raises(BroadcastError, match="same shape"):
        iterate_over_axes(src, {"y", "x"}, inconsistent)


def test_iterate_over_axes_func_changes_dim_count_raises() -> None:
    """Func that returns a 1D array when operates_on is 2D -> BroadcastError."""
    src = _make_array(["z", "y", "x"], (3, 4, 5))

    def flatten(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        return slice_data.ravel()  # 1D instead of 2D

    with pytest.raises(BroadcastError, match="dimensions"):
        iterate_over_axes(src, {"y", "x"}, flatten)


def test_iterate_over_axes_user_func_errors_propagate_unchanged() -> None:
    """ValueError raised inside func is NOT wrapped in BroadcastError."""
    src = _make_array(["z", "y", "x"], (3, 4, 5))

    class _CustomError(ValueError):
        pass

    def boom(slice_data: np.ndarray, coord: dict[str, int]) -> np.ndarray:
        raise _CustomError("user code failed")

    with pytest.raises(_CustomError, match="user code failed"):
        iterate_over_axes(src, {"y", "x"}, boom)


# ---------------------------------------------------------------------------
# Metadata propagation (ADR-027 D5)
# ---------------------------------------------------------------------------


def test_iterate_over_axes_preserves_metadata() -> None:
    """meta shared by reference, user shallow-copied, axes preserved."""
    meta = _DummyMeta(label="my-src")
    user = {"operator": "alice", "notes": ["n1", "n2"]}
    src = _make_array(
        ["z", "y", "x"],
        (2, 3, 3),
        fill=1.0,
        meta=meta,
        user=user,
    )

    result = iterate_over_axes(src, {"y", "x"}, lambda s, c: s)

    # meta shared by reference.
    assert result.meta is src.meta
    # user shallow-copied — equal but not the same dict.
    assert result.user == src.user
    assert result.user is not src.user
    # axes preserved.
    assert result.axes == src.axes
    assert result.axes is not src.axes  # defensive copy in _build_result


def test_iterate_over_axes_creates_derived_framework() -> None:
    """result.framework.derived_from == source.framework.object_id."""
    src = _make_array(["z", "y", "x"], (2, 3, 3))
    parent_id = src.framework.object_id

    result = iterate_over_axes(src, {"y", "x"}, lambda s, c: s)

    assert isinstance(result.framework, FrameworkMeta)
    assert result.framework.derived_from == parent_id
    assert result.framework.object_id != parent_id


# ---------------------------------------------------------------------------
# Concrete class preservation
# ---------------------------------------------------------------------------


def test_iterate_over_axes_returns_same_class() -> None:
    """Subclass input -> subclass output (not a plain Array)."""
    src = _make_array(
        ["z", "y", "x"],
        (2, 4, 4),
        fill=0.0,
        array_cls=_SubclassArray,
    )
    assert isinstance(src, _SubclassArray)

    result = iterate_over_axes(src, {"y", "x"}, lambda s, c: s)

    assert type(result) is _SubclassArray
    # Subclass invariant (required_axes={"y","x"}) still holds because
    # iterate_over_axes preserves source.axes.
    assert set(result.axes) >= {"y", "x"}
