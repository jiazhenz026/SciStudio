"""StorageBackend protocol — read, write, slice, iter_chunks, metadata."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, runtime_checkable

from typing_extensions import Protocol

from scistudio.core.storage.ref import StorageReference


@runtime_checkable
class StorageBackend(Protocol):
    """Interface that every storage backend implements.

    A storage backend knows how to persist and retrieve one family of data
    (arrays, tables, files, and so on). Code that moves data around depends on
    this interface rather than a concrete backend, so the same caller works
    with Zarr arrays, Arrow tables, or plain files. To find the backend for a
    given data type, use
    :class:`~scistudio.core.storage.backend_router.BackendRouter`.

    Implementations are duck-typed: any object that provides these methods
    satisfies the protocol (it is ``runtime_checkable``).
    """

    def read(self, ref: StorageReference) -> Any:
        """Read and return the data identified by *ref*.

        Args:
            ref: Pointer to the stored data.

        Returns:
            The data in the backend's natural in-memory form (e.g. a numpy
            array, a PyArrow table, or text/bytes).
        """
        ...

    def write(self, data: Any, ref: StorageReference) -> StorageReference:
        """Write *data* to the location described by *ref*.

        Accepts raw in-memory data (numpy arrays, dicts, text/bytes, and so on).

        Args:
            data: The in-memory data to persist.
            ref: Pointer describing where to write the data.

        Returns:
            An updated :class:`StorageReference` carrying any backend-assigned
            metadata (e.g. chunk layout, column names, size).
        """
        ...

    def slice(self, ref: StorageReference, *args: Any) -> Any:
        """Return a sub-selection of the data at *ref* without reading it whole.

        Args:
            ref: Pointer to the stored data.
            *args: Backend-specific selection (e.g. array index expressions,
                column names, or a byte ``(offset, length)``).

        Returns:
            The selected subset, in the backend's natural in-memory form.
        """
        ...

    def iter_chunks(self, ref: StorageReference, chunk_size: int) -> Iterator[Any]:
        """Yield the data at *ref* in successive chunks.

        Lets a caller stream a large object instead of loading it all at once.

        Args:
            ref: Pointer to the stored data.
            chunk_size: Rows/elements/bytes per chunk (meaning is
                backend-specific).

        Yields:
            One chunk at a time, in the backend's natural in-memory form.
        """
        ...

    def get_metadata(self, ref: StorageReference) -> dict[str, Any]:
        """Return backend-level metadata for the data at *ref*.

        Args:
            ref: Pointer to the stored data.

        Returns:
            A dict of descriptive fields (e.g. shape, dtype, columns, size). The
            exact keys depend on the backend.
        """
        ...

    def write_from_memory(self, data: Any, path: str) -> StorageReference:
        """Persist raw in-memory data at *path* and return a reference to it.

        Use this when the data exists only in memory and has no existing
        :class:`StorageReference` yet; the backend chooses its own storage
        format.

        Args:
            data: The raw in-memory data to persist.
            path: Target path within the backend's storage.

        Returns:
            A :class:`StorageReference` pointing at the newly written data.
        """
        ...
