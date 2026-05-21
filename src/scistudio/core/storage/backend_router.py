"""BackendRouter -- maps DataObject type -> StorageBackend + backend name."""

from __future__ import annotations

from scistudio.core.storage.base import StorageBackend


class BackendRouter:
    """Route DataObject types to their appropriate StorageBackend via MRO resolution."""

    def __init__(self) -> None:
        self._routes: dict[type, tuple[str, StorageBackend]] = {}

    def register(self, data_type: type, backend_name: str, backend: StorageBackend) -> None:
        """Register a mapping from *data_type* to (*backend_name*, *backend*)."""
        self._routes[data_type] = (backend_name, backend)

    def resolve(self, data_type: type) -> tuple[str, StorageBackend]:
        """Walk MRO to find the first registered ancestor type.

        Returns a tuple of (backend_name, backend_instance).
        Raises ``KeyError`` if no registered type is found in the MRO.
        """
        for cls in data_type.__mro__:
            if cls in self._routes:
                return self._routes[cls]
        raise KeyError(f"No storage backend registered for {data_type.__name__}")

    def backend_for(self, data_type: type) -> StorageBackend:
        """Return the StorageBackend for *data_type*."""
        return self.resolve(data_type)[1]

    def backend_name_for(self, data_type: type) -> str:
        """Return the backend name string for *data_type*."""
        return self.resolve(data_type)[0]

    def extension_for(self, data_type: type) -> str:
        """Return the file extension for *data_type*'s backend."""
        name = self.backend_name_for(data_type)
        return _BACKEND_EXTENSIONS[name]


_BACKEND_EXTENSIONS: dict[str, str] = {
    "zarr": ".zarr",
    "arrow": ".parquet",
    "filesystem": ".txt",
    "composite": "",
}

_default_router: BackendRouter | None = None


def _build_default_router() -> BackendRouter:
    """Build router with standard type -> backend mappings."""
    from scistudio.core.storage.arrow_backend import ArrowBackend
    from scistudio.core.storage.composite_store import CompositeStore
    from scistudio.core.storage.filesystem import FilesystemBackend
    from scistudio.core.storage.zarr_backend import ZarrBackend
    from scistudio.core.types.array import Array
    from scistudio.core.types.artifact import Artifact
    from scistudio.core.types.composite import CompositeData
    from scistudio.core.types.dataframe import DataFrame
    from scistudio.core.types.series import Series
    from scistudio.core.types.text import Text

    router = BackendRouter()
    zarr = ZarrBackend()
    arrow = ArrowBackend()
    fs = FilesystemBackend()
    composite = CompositeStore()

    router.register(Array, "zarr", zarr)
    router.register(Series, "zarr", zarr)
    router.register(DataFrame, "arrow", arrow)
    router.register(Text, "filesystem", fs)
    router.register(Artifact, "filesystem", fs)
    router.register(CompositeData, "composite", composite)
    return router


def get_router() -> BackendRouter:
    """Return the default singleton BackendRouter, building it on first access."""
    global _default_router
    if _default_router is None:
        _default_router = _build_default_router()
    return _default_router
