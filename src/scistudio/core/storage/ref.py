"""StorageReference — lightweight pointer to a stored data object."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scistudio.stability import stable


@stable(since="0.3.1")
@dataclass
class StorageReference:
    """Lightweight pointer to a data object stored in a backend.

    A ``StorageReference`` records *where* a piece of data lives (which backend
    and path) and optionally *how* it is encoded, without holding the data
    itself. Backends accept and return these references when they read, write,
    or slice data, so the rest of the runtime can pass data around by reference
    instead of by value.

    Example:
        >>> ref = StorageReference(backend="zarr", path="data/image.zarr")
        >>> ref.backend
        'zarr'
    """

    backend: str
    """Identifier of the storage backend (e.g. ``"zarr"``, ``"arrow"``, ``"filesystem"``)."""
    path: str
    """Location of the data within the backend, stored as a POSIX (forward-slash) path."""
    format: str | None = None
    """Optional format hint (e.g. ``"ome-tiff"``, ``"parquet"``); ``None`` when unspecified."""
    metadata: dict[str, Any] | None = field(default=None)
    """Optional extra metadata attached to the reference (e.g. shape, columns, size)."""

    def __post_init__(self) -> None:
        """Normalise *path* to POSIX forward-slash form."""
        self.path = self.path.replace("\\", "/")
