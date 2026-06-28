"""with_meta_changes — free-function immutable update helper for Meta models.

Implements part of ADR-027 D5. The ``DataObject.with_meta()`` instance
method will be added in T-005; this module provides the underlying
logic so it can be used both from instance methods and from utility
code without forcing a dependency on ``DataObject``.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

from pydantic import BaseModel

from scistudio.stability import stable

T = TypeVar("T", bound=BaseModel)


@stable(since="0.3.1")
def with_meta_changes(meta: T, **changes: Any) -> T:
    """Return a new Pydantic ``Meta`` instance with the given fields updated.

    Pure helper used by ``DataObject.with_meta()`` (T-005). Does not
    know about ``DataObject``; operates on any Pydantic ``BaseModel``
    instance representing a ``DataObject``'s ``meta`` slot. Living in
    ``scistudio.core.meta`` keeps the import direction clean: T-005's
    ``DataObject.with_meta(**changes)`` instance method delegates here
    rather than the other way around.

    Args:
        meta: A Pydantic ``BaseModel`` instance (typically a subclass
            ``Meta`` defined on a ``DataObject`` plugin type).
        **changes: Field assignments to apply.

    Returns:
        A new ``BaseModel`` instance of the same class as ``meta``,
        with the changes applied. The original is unchanged (Pydantic
        ``model_copy`` always returns a new instance).

    Raises:
        pydantic.ValidationError: If the changes violate the model's
            field constraints. Pydantic raises this from ``model_copy``
            when the resulting instance would be invalid.

    Example:
        >>> from pydantic import BaseModel
        >>> class M(BaseModel):
        ...     x: int = 0
        ...     y: int = 0
        >>> a = M(x=1, y=2)
        >>> b = with_meta_changes(a, x=10)
        >>> b.x, b.y
        (10, 2)
        >>> a.x, a.y  # original unchanged
        (1, 2)
    """
    return cast(T, meta.model_copy(update=changes))
