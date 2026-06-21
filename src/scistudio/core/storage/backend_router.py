"""BackendRouter -- maps DataObject type -> StorageBackend + backend name."""

from __future__ import annotations

from collections.abc import Callable

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
_default_builder: Callable[[], BackendRouter] | None = None


def set_default_builder(builder: Callable[[], BackendRouter]) -> None:
    """Register the factory that builds the default singleton router.

    #1342 / round-4 no-cycles: the default ``type -> backend`` wiring lives on
    the ``core.types`` side (``scistudio.core.types._backend_defaults``) so this
    storage module never imports the concrete type classes. That wiring calls
    this at import time to hand ``get_router`` a builder *callback*; storage
    holds only the callable, not an import edge back to ``core.types``. Building
    stays lazy (first ``get_router`` access), so behaviour is unchanged.
    """
    global _default_builder
    _default_builder = builder


def get_router() -> BackendRouter:
    """Return the default singleton ``BackendRouter``, building it on first access."""
    global _default_router
    if _default_router is None:
        if _default_builder is None:
            raise RuntimeError(
                "BackendRouter default builder is not registered. Import "
                "scistudio.core.types (which registers the default type -> backend "
                "wiring via core.types._backend_defaults) before resolving a "
                "storage backend."
            )
        _default_router = _default_builder()
    return _default_router
