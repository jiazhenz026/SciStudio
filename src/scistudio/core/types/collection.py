"""Collection — homogeneous ordered container of DataObjects for block-to-block transport.

ADR-020: Collection is NOT a DataObject subclass — it is a transport wrapper only.
Type identity determined by item_type (for port matching).
Engine never unpacks, iterates, or inspects Collection contents.
"""

from __future__ import annotations

from typing import Any

from scistudio.core.types.base import DataObject


class Collection:
    """Homogeneous ordered collection of DataObjects for inter-block transport.

    Invariants:
        - All items must be instances of the same base DataObject subclass.
        - ``item_type`` is set at construction and cannot change.
        - ``length=0`` is valid only when ``item_type`` is provided explicitly.

    ADR-020 Addendum 6: Empty Collection without explicit ``item_type`` raises
    ``TypeError`` to prevent bypassing port type checks.
    """

    __slots__ = ("_item_type", "_items")

    def __init__(self, items: list[DataObject] | None = None, item_type: type | None = None) -> None:
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
    def item_type(self) -> type:
        """Return the element type of this Collection (immutable)."""
        return self._item_type

    @property
    def length(self) -> int:
        """Return the number of items in this Collection."""
        return len(self._items)

    def __iter__(self) -> Any:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, index: int | slice) -> Any:
        if isinstance(index, slice):
            return [self._items[i] for i in range(*index.indices(len(self._items)))]
        return self._items[index]

    def __class_getitem__(cls, item_type: type) -> Any:
        """Enable ``Collection[Image]`` syntax for type annotations."""
        return cls

    def __repr__(self) -> str:
        return f"Collection[{self._item_type.__name__}](length={len(self._items)})"

    @property
    def storage_refs(self) -> list[Any]:
        """Extract StorageReference from each item."""
        return [item.storage_ref for item in self._items]
