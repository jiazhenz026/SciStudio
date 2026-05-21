"""StorageReference — lightweight pointer to a stored data object."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StorageReference:
    """Immutable pointer to a persisted data object in a storage backend.

    Attributes:
        backend: Identifier for the storage backend (e.g. "zarr", "arrow", "filesystem").
        path: Location of the data within the backend.
        format: Optional format hint (e.g. "ome-tiff", "parquet").
        metadata: Optional extra metadata attached to the reference.
    """

    backend: str
    path: str
    format: str | None = None
    metadata: dict[str, Any] | None = field(default=None)

    def __post_init__(self) -> None:
        """Normalize *path* to POSIX forward-slash format (ADR-017, #53)."""
        self.path = self.path.replace("\\", "/")
