"""Storage backends — per-type persistence (Zarr, Arrow, filesystem)."""

from __future__ import annotations

from scistudio.core.storage.arrow_backend import ArrowBackend
from scistudio.core.storage.backend_router import BackendRouter, get_router
from scistudio.core.storage.base import StorageBackend
from scistudio.core.storage.composite_store import CompositeStore
from scistudio.core.storage.filesystem import FilesystemBackend
from scistudio.core.storage.ref import StorageReference
from scistudio.core.storage.zarr_backend import ZarrBackend

__all__ = [
    "ArrowBackend",
    "BackendRouter",
    "CompositeStore",
    "FilesystemBackend",
    "StorageBackend",
    "StorageReference",
    "ZarrBackend",
    "get_router",
]
