"""Port constraint helper factories.

Implements ADR-027 D4 (companion module): predicates that block authors
compose into ``InputPort(constraint=...)`` to validate incoming
``Collection`` items beyond what the type-class hierarchy can express.

Each factory returns a ``Callable[[Collection], bool]``. The framework's
port-checking layer (see :func:`scistudio.blocks.base.ports.validate_port_constraint`)
calls the predicate on the entire :class:`~scistudio.core.types.collection.Collection`
at port-validation time, pre-execution.

These are **pure Python** predicates with **no dependency on storage
backends** — they read instance attributes (``axes``, ``ndim``, ``dtype``)
from each item in the collection. They do NOT call ``to_memory()`` or
trigger any I/O, which is critical for Phase 10's Level 1 laziness model
(ADR-027 D4).

Semantics for every factory in this module:

- Iterates the collection once and short-circuits on the first failing item.
- Items missing the inspected attribute (e.g. no ``axes``) fail the
  constraint by returning ``False`` — never raise ``AttributeError``.
- Empty iterables return ``True`` (vacuous truth, matching Python's
  ``all()`` semantics). A Collection that has no items cannot violate a
  per-item invariant.
- The returned callable carries a descriptive ``__name__`` and ``__doc__``
  so failures in :func:`~scistudio.blocks.base.ports.validate_port_constraint`
  surface a useful breadcrumb.

Example:

.. code-block:: python

    from scistudio.blocks.base.ports import InputPort
    from scistudio.utils.constraints import has_axes, has_shape

    InputPort(
        name="image",
        accepted_types=[Image],
        constraint=has_axes("y", "x"),
        constraint_description="image must carry spatial axes (y, x)",
    )

    InputPort(
        name="volume",
        accepted_types=[Array],
        constraint=has_shape(3),
        constraint_description="volume must be 3D",
    )

Source ADR sections: ADR-027 D4 (companion — the ``has_*`` helpers
complement the per-instance ``axes`` introduced by ADR-027 D1 and the
per-class ``required_axes`` declared by subclasses).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# A constraint is a callable that takes a Collection (or any iterable of
# DataObject items per ADR-020) and returns True iff every item in the
# collection satisfies the constraint. The framework calls these inside
# ``validate_port_constraint`` before dispatching the block.
ConstraintFn = Callable[[Any], bool]


def has_axes(*required: str) -> ConstraintFn:
    """Require every item in the collection to include all ``required`` axes.

    The check is "item axes is a **superset** of ``required``" — items may
    have additional axes beyond the required set. For exact-match behaviour
    use :func:`has_exact_axes`.

    Args:
        *required: Axis names every item must carry (e.g. ``"y", "x"``).

    Returns:
        A predicate ``check(collection) -> bool`` suitable for
        ``InputPort(constraint=...)``.

    Example:
        >>> check = has_axes("y", "x")  # accepts 2D, 3D, 4D, ... with y,x present
        >>> check.__name__
        "has_axes('y', 'x')"
    """
    required_set = frozenset(required)

    def _check(collection: Any) -> bool:
        try:
            for item in collection:
                item_axes = getattr(item, "axes", None)
                if item_axes is None:
                    return False
                if not required_set.issubset(set(item_axes)):
                    return False
        except TypeError:
            # collection is not iterable
            return False
        return True

    _check.__name__ = f"has_axes({', '.join(repr(a) for a in required)})"
    _check.__doc__ = f"has_axes({', '.join(repr(a) for a in required)}) — every item's axes must be a superset."
    return _check


def has_exact_axes(*axes: str) -> ConstraintFn:
    """Require every item in the collection to have **exactly** ``axes``.

    The comparison is set equality — order does not matter (per ADR-027
    D1 the canonical order of axes on an instance is governed by the
    instance's class, not by this constraint).

    Args:
        *axes: Axis names that must match each item's axes as a set.

    Returns:
        A predicate ``check(collection) -> bool``.

    Example:
        >>> check = has_exact_axes("y", "x")  # accepts only ["y", "x"] or ["x", "y"]
    """
    expected_set = frozenset(axes)

    def _check(collection: Any) -> bool:
        try:
            for item in collection:
                item_axes = getattr(item, "axes", None)
                if item_axes is None:
                    return False
                if set(item_axes) != expected_set:
                    return False
        except TypeError:
            return False
        return True

    _check.__name__ = f"has_exact_axes({', '.join(repr(a) for a in axes)})"
    _check.__doc__ = f"has_exact_axes({', '.join(repr(a) for a in axes)}) — every item's axes must equal this set."
    return _check


def has_shape(ndim: int) -> ConstraintFn:
    """Require every item in the collection to have exactly ``ndim`` dimensions.

    Reads ``item.ndim`` (which :class:`scistudio.core.types.array.Array`
    exposes as ``len(self.axes)``). Items without an ``ndim`` attribute
    fail the constraint.

    Args:
        ndim: The exact number of dimensions each item must have.

    Returns:
        A predicate ``check(collection) -> bool``.
    """

    def _check(collection: Any) -> bool:
        try:
            for item in collection:
                item_ndim = getattr(item, "ndim", None)
                if item_ndim is None:
                    return False
                if item_ndim != ndim:
                    return False
        except TypeError:
            return False
        return True

    _check.__name__ = f"has_shape({ndim!r})"
    _check.__doc__ = f"has_shape({ndim!r}) — every item must have ndim == {ndim}."
    return _check


def has_min_shape(ndim: int) -> ConstraintFn:
    """Require every item in the collection to have at least ``ndim`` dimensions.

    Reads ``item.ndim``. Items without an ``ndim`` attribute fail.

    Args:
        ndim: The minimum number of dimensions each item must have.

    Returns:
        A predicate ``check(collection) -> bool``.
    """

    def _check(collection: Any) -> bool:
        try:
            for item in collection:
                item_ndim = getattr(item, "ndim", None)
                if item_ndim is None:
                    return False
                if item_ndim < ndim:
                    return False
        except TypeError:
            return False
        return True

    _check.__name__ = f"has_min_shape({ndim!r})"
    _check.__doc__ = f"has_min_shape({ndim!r}) — every item must have ndim >= {ndim}."
    return _check


def has_dtype(*dtypes: Any) -> ConstraintFn:
    """Require every item's ``dtype`` to match one of the given dtypes.

    Comparison is by ``str(item.dtype)`` so numpy dtype objects, string
    labels, and Python type literals normalise to the same key. This
    mirrors the common idiom ``str(np.float32) == "<class 'numpy.float32'>"``
    vs ``str(np.dtype("float32")) == "float32"`` — callers should pass the
    form they expect (typically a numpy dtype object or a plain string).

    Args:
        *dtypes: Accepted dtypes. Each is normalised with ``str(...)``.

    Returns:
        A predicate ``check(collection) -> bool``.
    """
    expected = {str(d) for d in dtypes}

    def _check(collection: Any) -> bool:
        try:
            for item in collection:
                item_dtype = getattr(item, "dtype", None)
                if item_dtype is None:
                    return False
                if str(item_dtype) not in expected:
                    return False
        except TypeError:
            return False
        return True

    _check.__name__ = f"has_dtype({', '.join(repr(d) for d in dtypes)})"
    _check.__doc__ = f"has_dtype({', '.join(repr(d) for d in dtypes)}) — every item's str(dtype) must match."
    return _check


def is_2d() -> ConstraintFn:
    """Convenience alias: every item must be 2D (``ndim == 2``)."""
    return has_shape(2)


def is_3d() -> ConstraintFn:
    """Convenience alias: every item must be 3D (``ndim == 3``)."""
    return has_shape(3)


__all__ = [
    "ConstraintFn",
    "has_axes",
    "has_dtype",
    "has_exact_axes",
    "has_min_shape",
    "has_shape",
    "is_2d",
    "is_3d",
]
