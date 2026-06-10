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


def get_router() -> BackendRouter:
    """Return the default singleton ``BackendRouter``, building it on first access."""
    global _default_router
    if _default_router is None:
        # TODO(#1342): this import cannot be hoisted to module top level because
        # _defaults.py imports BackendRouter from this module, creating a cycle:
        #   backend_router -> _defaults -> backend_router
        # The lazy import breaks the cycle while preserving the public symbol path
        # `scistudio.core.storage.backend_router.get_router` and the test
        # monkeypatch target at tests/blocks/test_auto_flush_composite.py:49,72.
        # Resolving this properly requires either splitting BackendRouter out or
        # inverting the dependency; tracked at issue #1342.
        # Followup: https://github.com/zjzcpj/SciStudio/issues/1342
        from scistudio.core.storage._defaults import build_default

        _default_router = build_default()
    return _default_router
