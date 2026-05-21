"""StorageBackend protocol — read, write, slice, iter_chunks, metadata."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, runtime_checkable

from typing_extensions import Protocol

from scistudio.core.storage.ref import StorageReference


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol that every storage backend must satisfy.

    All methods raise :class:`NotImplementedError` in concrete stub
    implementations (Phase 1).
    """

    def read(self, ref: StorageReference) -> Any:
        """Read the data identified by *ref* and return it."""
        ...

    def write(self, data: Any, ref: StorageReference) -> StorageReference:
        """Write *data* to the location described by *ref*.

        Returns an updated :class:`StorageReference` with any backend-assigned
        metadata (e.g. chunk layout, checksum).

        Concrete implementations should handle raw in-memory data
        (ADR-020-Add5, ADR-031 D2: ViewProxy eliminated).
        """
        ...

    def slice(self, ref: StorageReference, *args: Any) -> Any:
        """Return a sub-selection of the data identified by *ref*."""
        ...

    def iter_chunks(self, ref: StorageReference, chunk_size: int) -> Iterator[Any]:
        """Yield successive chunks of size *chunk_size* from *ref*."""
        ...

    def get_metadata(self, ref: StorageReference) -> dict[str, Any]:
        """Return backend-level metadata for the data at *ref*."""
        ...

    def write_from_memory(self, data: Any, path: str) -> StorageReference:
        """Write raw in-memory data to storage at *path* and return a reference.

        ADR-020-Add5: Handles DataObjects that exist only in-memory (no
        existing StorageReference). Concrete backends implement this to
        persist raw Python/numpy/arrow data to their storage format.

        Parameters
        ----------
        data:
            The raw in-memory data to persist.
        path:
            Target path within the backend's storage.
        """
        ...
