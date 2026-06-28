"""Immutable-update helper for metadata models.

``with_meta_changes`` returns a copy of a Pydantic metadata model with some
fields replaced, leaving the original untouched. It backs
``DataObject.with_meta()`` but knows nothing about ``DataObject`` itself, so it
can be reused by utility code without creating a dependency on the data type.
"""

from __future__ import annotations

from typing import Any, TypeVar, cast

from pydantic import BaseModel

from scistudio.stability import stable

T = TypeVar("T", bound=BaseModel)


@stable(since="0.3.1")
def with_meta_changes(meta: T, **changes: Any) -> T:
    """Return a copy of a metadata model with the given fields updated.

    A pure helper backing ``DataObject.with_meta()``. It works on any Pydantic
    ``BaseModel`` (typically a ``DataObject``'s ``meta`` slot) and never mutates
    the input — the original instance is returned unchanged.

    Args:
        meta: A Pydantic ``BaseModel`` instance, usually a ``Meta`` subclass
            defined on a ``DataObject`` plugin type.
        **changes: Field assignments to apply to the copy.

    Returns:
        A new instance of the same class as ``meta`` with ``changes`` applied.

    Raises:
        pydantic.ValidationError: If the changes would violate the model's
            field constraints.

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
