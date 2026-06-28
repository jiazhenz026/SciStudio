"""Ordered batches of one data type (:class:`Collection`).

A :class:`Collection` is how a block hands a *set* of data objects to the
next block — for example every field of view in a plate, each as an
:class:`Array`. Every item must be the same kind of object, which is what
lets ports check that the receiving block can handle the batch. SciStudio
itself never unpacks or inspects a Collection's contents.
"""

from __future__ import annotations

from typing import Any

from scistudio.core.types.base import DataObject
from scistudio.stability import stable


@stable(since="0.3.1")
class Collection:
    """An ordered batch of :class:`DataObject` items, all of one type.

    Blocks use a :class:`Collection` to pass many items at once — a stack of
    images, a set of spectra — while keeping the batch type-checkable at the
    boundary between blocks. SciStudio itself never looks inside a
    Collection; it only checks the item type for port matching.

    Rules it enforces:

    - every item must be an instance of the same :class:`DataObject`
      subclass;
    - the item type is fixed once the Collection is created;
    - an empty Collection is allowed only if you state ``item_type``
      explicitly, so an empty batch still has a checkable type.

    Example:
        >>> from scistudio.core.types import Array, Collection
        >>> imgs = [Array(axes=["y", "x"]), Array(axes=["y", "x"])]
        >>> batch = Collection(imgs)
        >>> batch.item_type.__name__
        'Array'
        >>> len(batch)
        2
    """

    __slots__ = ("_item_type", "_items")

    @stable(since="0.3.1")
    def __init__(self, items: list[DataObject] | None = None, item_type: type | None = None) -> None:
        """Create a Collection from a list of same-typed items.

        Args:
            items: The items to hold, in order. Defaults to empty.
            item_type: The element type. Inferred from the first item when
                items are given; required when *items* is empty.

        Raises:
            TypeError: if the Collection is empty and *item_type* is not
                given, or if the items are not all the same type.
        """
        items = items if items is not None else []

        # ADR-020-Add6: empty Collection must specify item_type explicitly.
        if not items and item_type is None:
            raise TypeError("item_type is required for empty Collection")

        # Infer item_type from first item if not provided.
        if items and item_type is None:
            item_type = type(items[0])

        # Validate homogeneity.
        if items:
            for i, item in enumerate(items):
                if not isinstance(item, item_type):  # type: ignore[arg-type]
                    raise TypeError(
                        f"Collection requires homogeneous types: item[{i}] is "
                        f"{type(item).__name__}, expected {item_type.__name__}"  # type: ignore[union-attr]
                    )

        self._items: list[DataObject] = list(items)
        self._item_type: type = item_type or DataObject

    @property
    @stable(since="0.3.1")
    def item_type(self) -> type:
        """The element type shared by every item (fixed at creation).

        Returns:
            The :class:`DataObject` subclass of the items.
        """
        return self._item_type

    @property
    @stable(since="0.3.1")
    def length(self) -> int:
        """The number of items in the Collection.

        Returns:
            The item count.
        """
        return len(self._items)

    @stable(since="0.3.1")
    def __iter__(self) -> Any:
        """Return an iterator over the items, in order."""
        return iter(self._items)

    @stable(since="0.3.1")
    def __len__(self) -> int:
        """Return the number of items (same as :attr:`length`)."""
        return len(self._items)

    @stable(since="0.3.1")
    def __getitem__(self, index: int | slice) -> Any:
        """Index or slice the Collection.

        Args:
            index: A position (``int``) or a range (``slice``).

        Returns:
            The single :class:`DataObject` at that position for an ``int``,
            or a ``list`` of items for a ``slice``.
        """
        if isinstance(index, slice):
            return [self._items[i] for i in range(*index.indices(len(self._items)))]
        return self._items[index]

    @stable(since="0.3.1")
    def __class_getitem__(cls, item_type: type) -> Any:
        """Support ``Collection[Array]`` syntax in type annotations.

        Returns the class unchanged; the bracketed type is only a hint for
        readers and type checkers, not a distinct runtime type.
        """
        return cls

    @stable(since="0.3.1")
    def __repr__(self) -> str:
        """Return the ``Collection[Type](length=N)`` display string."""
        return f"Collection[{self._item_type.__name__}](length={len(self._items)})"

    @property
    @stable(since="0.3.1")
    def storage_refs(self) -> list[Any]:
        """The storage reference of each item, in order.

        Returns:
            A list of each item's :class:`StorageReference` (an entry is
            ``None`` for any item not yet persisted).
        """
        return [item.storage_ref for item in self._items]
