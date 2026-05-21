"""Tests for ``scistudio.utils.constraints`` port helper factories.

Covers T-010 per ADR-027 D4 (companion) and the T-010 section of
``docs/specs/phase10-implementation-standards.md``.

Every factory in ``scistudio.utils.constraints`` is a closure: the outer
function captures configuration, and the inner ``_check`` callable is
what the block runtime actually invokes. These tests exercise the inner
callable directly against hand-built Collections and raw lists (the
standards doc explicitly calls out that the constraint function is
duck-typed and should accept any iterable, not just Collection).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from scistudio.blocks.base.ports import InputPort, validate_port_constraint
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection
from scistudio.utils.constraints import (
    ConstraintFn,
    has_axes,
    has_dtype,
    has_exact_axes,
    has_min_shape,
    has_shape,
    is_2d,
    is_3d,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _arr(axes: list[str], shape: tuple[int, ...] | None = None, dtype: Any = None) -> Array:
    """Build an Array without touching storage. Shape defaults to ones."""
    if shape is None:
        shape = tuple(1 for _ in axes)
    return Array(axes=axes, shape=shape, dtype=dtype)


@pytest.fixture
def img_2d_yx() -> Array:
    return _arr(["y", "x"], (4, 5))


@pytest.fixture
def img_3d_cyx() -> Array:
    return _arr(["c", "y", "x"], (2, 4, 5))


@pytest.fixture
def img_3d_tzc() -> Array:
    return _arr(["t", "z", "c"], (2, 3, 4))


@pytest.fixture
def img_4d_tczy() -> Array:
    return _arr(["t", "c", "y", "x"], (2, 3, 4, 5))


# ---------------------------------------------------------------------------
# has_axes
# ---------------------------------------------------------------------------


def test_has_axes_accepts_superset(img_3d_cyx: Array) -> None:
    """A 3D array with axes [c, y, x] satisfies has_axes('y', 'x')."""
    check = has_axes("y", "x")
    assert check([img_3d_cyx]) is True


def test_has_axes_accepts_exact(img_2d_yx: Array) -> None:
    """A 2D array with axes [y, x] satisfies has_axes('y', 'x')."""
    check = has_axes("y", "x")
    assert check([img_2d_yx]) is True


def test_has_axes_allows_extra_axes(img_4d_tczy: Array) -> None:
    """Extra axes are fine — has_axes is a superset predicate."""
    check = has_axes("y", "x")
    assert check([img_4d_tczy]) is True


def test_has_axes_rejects_missing(img_3d_tzc: Array) -> None:
    """An array whose axes don't include 'y' or 'x' is rejected."""
    check = has_axes("y", "x")
    assert check([img_3d_tzc]) is False


def test_has_axes_rejects_item_without_axes_attr() -> None:
    """Items missing the 'axes' attribute fail the constraint, not raise."""
    check = has_axes("y", "x")
    bogus = SimpleNamespace(shape=(4, 5))  # no .axes
    assert check([bogus]) is False


def test_has_axes_predicate_name_is_descriptive() -> None:
    """The returned callable carries a useful ``__name__``."""
    check = has_axes("y", "x")
    assert check.__name__ == "has_axes('y', 'x')"
    assert check.__doc__ is not None
    assert "y" in check.__doc__ and "x" in check.__doc__


def test_has_axes_iterates_collection_per_adr020(img_2d_yx: Array, img_3d_cyx: Array) -> None:
    """has_axes accepts any iterable (duck-typed per the standards doc)."""
    check = has_axes("y", "x")
    col = Collection([img_2d_yx, img_3d_cyx], item_type=Array)
    assert check(col) is True


def test_has_axes_returns_constraint_fn_type() -> None:
    """has_axes returns something callable that matches ConstraintFn."""
    check: ConstraintFn = has_axes("y", "x")
    assert callable(check)


# ---------------------------------------------------------------------------
# has_exact_axes
# ---------------------------------------------------------------------------


def test_has_exact_axes_accepts_exact(img_2d_yx: Array) -> None:
    check = has_exact_axes("y", "x")
    assert check([img_2d_yx]) is True


def test_has_exact_axes_accepts_reordered() -> None:
    """Set equality — order does not matter."""
    check = has_exact_axes("y", "x")
    arr = _arr(["x", "y"], (5, 4))
    assert check([arr]) is True


def test_has_exact_axes_rejects_extra(img_3d_cyx: Array) -> None:
    check = has_exact_axes("y", "x")
    assert check([img_3d_cyx]) is False


def test_has_exact_axes_rejects_missing() -> None:
    check = has_exact_axes("y", "x")
    arr = _arr(["y"], (4,))
    assert check([arr]) is False


def test_has_exact_axes_rejects_item_without_axes_attr() -> None:
    check = has_exact_axes("y", "x")
    assert check([SimpleNamespace()]) is False


# ---------------------------------------------------------------------------
# has_shape (ndim)
# ---------------------------------------------------------------------------


def test_has_shape_accepts_correct_ndim(img_2d_yx: Array) -> None:
    check = has_shape(2)
    assert check([img_2d_yx]) is True


def test_has_shape_rejects_wrong_ndim(img_3d_cyx: Array) -> None:
    check = has_shape(2)
    assert check([img_3d_cyx]) is False


def test_has_shape_rejects_item_without_ndim_attr() -> None:
    check = has_shape(2)
    assert check([SimpleNamespace()]) is False


# ---------------------------------------------------------------------------
# has_min_shape
# ---------------------------------------------------------------------------


def test_has_min_shape_accepts_at_least_ndim(img_3d_cyx: Array, img_4d_tczy: Array) -> None:
    check = has_min_shape(3)
    assert check([img_3d_cyx]) is True
    assert check([img_4d_tczy]) is True


def test_has_min_shape_rejects_lower(img_2d_yx: Array) -> None:
    check = has_min_shape(3)
    assert check([img_2d_yx]) is False


def test_has_min_shape_rejects_item_without_ndim() -> None:
    check = has_min_shape(2)
    assert check([SimpleNamespace()]) is False


# ---------------------------------------------------------------------------
# has_dtype
# ---------------------------------------------------------------------------


def test_has_dtype_accepts_string_match() -> None:
    check = has_dtype("float32")
    arr = _arr(["y", "x"], (4, 5), dtype="float32")
    assert check([arr]) is True


def test_has_dtype_accepts_numpy_dtype() -> None:
    """A numpy dtype object and its string form normalise to the same key."""
    np_dtype = np.dtype("float32")
    check = has_dtype(np_dtype)
    arr = _arr(["y", "x"], (4, 5), dtype=np_dtype)
    assert check([arr]) is True


def test_has_dtype_rejects_other() -> None:
    check = has_dtype("float32")
    arr = _arr(["y", "x"], (4, 5), dtype="uint16")
    assert check([arr]) is False


def test_has_dtype_rejects_item_without_dtype() -> None:
    check = has_dtype("float32")
    assert check([SimpleNamespace()]) is False


# ---------------------------------------------------------------------------
# Convenience aliases
# ---------------------------------------------------------------------------


def test_is_2d_accepts_2d_only(img_2d_yx: Array, img_3d_cyx: Array) -> None:
    check = is_2d()
    assert check([img_2d_yx]) is True
    assert check([img_3d_cyx]) is False


def test_is_3d_accepts_3d_only(img_2d_yx: Array, img_3d_cyx: Array) -> None:
    check = is_3d()
    assert check([img_3d_cyx]) is True
    assert check([img_2d_yx]) is False


# ---------------------------------------------------------------------------
# Multi-item collection semantics + empty collection vacuous truth
# ---------------------------------------------------------------------------


def test_constraint_passes_full_collection(img_2d_yx: Array, img_3d_cyx: Array) -> None:
    """Every item satisfies has_axes('y', 'x') -> predicate is True."""
    check = has_axes("y", "x")
    col = Collection([img_2d_yx, img_3d_cyx], item_type=Array)
    assert check(col) is True


def test_constraint_fails_one_item(img_2d_yx: Array, img_3d_tzc: Array) -> None:
    """A single non-matching item fails the whole collection."""
    check = has_axes("y", "x")
    col = Collection([img_2d_yx, img_3d_tzc], item_type=Array)
    assert check(col) is False


def test_constraint_handles_empty_collection() -> None:
    """An empty iterable is vacuously true (Python's ``all()`` semantics)."""
    check = has_axes("y", "x")
    # Empty Collection requires an explicit item_type per ADR-020 Add6.
    empty_col = Collection([], item_type=Array)
    assert check(empty_col) is True
    # Also verify against a plain empty list (duck-typed acceptance).
    assert check([]) is True


def test_constraint_short_circuits_on_first_failure() -> None:
    """The predicate stops iterating after the first failure."""
    check = has_axes("y", "x")

    # A generator that yields one bad item then would raise if advanced.
    def bad_generator() -> Any:
        yield _arr(["t"], (3,))  # fails immediately
        raise AssertionError("should have short-circuited before the second item")

    assert check(bad_generator()) is False


def test_constraint_handles_non_iterable() -> None:
    """A non-iterable value fails gracefully rather than raising."""
    check = has_axes("y", "x")
    assert check(42) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Integration with InputPort / validate_port_constraint
# ---------------------------------------------------------------------------


def test_constraint_used_in_input_port(img_2d_yx: Array, img_3d_tzc: Array) -> None:
    """Define an InputPort with constraint=has_axes('y','x') and validate.

    Mirrors how a block author actually uses the helper: pass it straight
    into ``InputPort(constraint=...)`` and let ``validate_port_constraint``
    call it with a Collection.
    """
    port = InputPort(
        name="image",
        accepted_types=[Array],
        constraint=has_axes("y", "x"),
        constraint_description="image must carry spatial axes (y, x)",
    )

    good_col = Collection([img_2d_yx], item_type=Array)
    ok, msg = validate_port_constraint(port, good_col)
    assert ok is True
    assert msg == ""

    bad_col = Collection([img_3d_tzc], item_type=Array)
    ok, msg = validate_port_constraint(port, bad_col)
    assert ok is False
    assert "spatial axes" in msg


def test_input_port_surfaces_constraint_description_on_failure(img_3d_tzc: Array) -> None:
    """The port's ``constraint_description`` is what users see on rejection."""
    port = InputPort(
        name="image",
        accepted_types=[Array],
        constraint=has_exact_axes("y", "x"),
        constraint_description="image must be exactly (y, x)",
    )
    col = Collection([img_3d_tzc], item_type=Array)
    ok, msg = validate_port_constraint(port, col)
    assert ok is False
    assert msg == "image must be exactly (y, x)"
