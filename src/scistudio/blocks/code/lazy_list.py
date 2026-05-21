"""LazyList -- memory-safe wrapper for Collection items in CodeBlock.

ADR-020-Add4: When CodeBlock auto-unpacks a Collection with length > 1,
it wraps the Collection in a LazyList instead of materializing all items.

Usage in CodeBlock auto-unpack::

    # Collection length=1 -> single native object (numpy array, pandas DataFrame)
    # Collection length>1 -> LazyList (this class)

Memory guarantee::

    for x in lazy_list:  # loads 1 item at a time, O(1) memory
        process(x)

    lazy_list[5]  # loads only item 5

    all_items = lazy_list.to_list()  # explicit full materialization
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from typing import Any, overload

from scistudio.core.types.collection import Collection

# Warn when to_list() would load more items than this threshold.
_ITEM_COUNT_WARNING_THRESHOLD = 100


def _load_item(collection: Collection, index: int) -> Any:
    """Load a single item via ``collection[index].view().to_memory()``."""
    return collection[index].view().to_memory()


class LazyList:
    """Memory-safe list-like wrapper for Collection items.

    Wraps a :class:`Collection` and presents a list-like interface to user
    scripts.  Data is loaded on demand: iteration yields one item at a time
    (O(1) peak memory), indexing loads only the requested item, and
    ``len()`` returns the count without touching storage.
    """

    __slots__ = ("_collection",)

    def __init__(self, collection: Collection) -> None:
        self._collection = collection

    # -- Sequence protocol -----------------------------------------------------

    def __iter__(self) -> Iterator[Any]:
        """Yield items one at a time; each previous item is eligible for GC."""
        for i in range(len(self._collection)):
            yield _load_item(self._collection, i)

    @overload
    def __getitem__(self, index: int) -> Any: ...

    @overload
    def __getitem__(self, index: slice) -> list[Any]: ...

    def __getitem__(self, index: int | slice) -> Any:
        """Load the requested item(s) from the Collection.

        * ``int`` index -- returns a single materialised object.
        * ``slice`` -- returns a ``list`` of materialised objects.
        """
        if isinstance(index, slice):
            indices = range(*index.indices(len(self._collection)))
            return [_load_item(self._collection, i) for i in indices]
        # Normalise negative indices.
        length = len(self._collection)
        if index < 0:
            index += length
        if index < 0 or index >= length:
            raise IndexError(f"LazyList index {index} out of range (length {length})")
        return _load_item(self._collection, index)

    def __len__(self) -> int:
        """Return the number of items without loading any data."""
        return len(self._collection)

    # -- explicit materialisation ----------------------------------------------

    def to_list(self) -> list[Any]:
        """Load all items into memory and return as a plain list.

        Emits a :class:`ResourceWarning` when the Collection contains more
        than ``_ITEM_COUNT_WARNING_THRESHOLD`` items.
        """
        length = len(self._collection)
        if length > _ITEM_COUNT_WARNING_THRESHOLD:
            warnings.warn(
                f"LazyList.to_list() is loading {length} items into memory. "
                "Consider iterating with a for-loop instead.",
                ResourceWarning,
                stacklevel=2,
            )
        return [_load_item(self._collection, i) for i in range(length)]

    def __repr__(self) -> str:
        return f"LazyList(length={len(self._collection)})"
