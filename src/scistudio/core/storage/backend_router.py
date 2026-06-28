"""BackendRouter -- maps DataObject type -> StorageBackend + backend name."""

from __future__ import annotations

from collections.abc import Callable

from scistudio.core.storage.base import StorageBackend


class BackendRouter:
    """Pick the right storage backend for a given data type.

    A registry that maps a ``DataObject`` subtype to the backend (and backend
    name) that should persist it. Lookups walk the type's method resolution
    order, so registering a base type also covers its subtypes. The shared
    default instance is available via :func:`get_router`.

    Example:
        >>> from scistudio.core.storage import FilesystemBackend
        >>> router = BackendRouter()
        >>> router.register(str, "filesystem", FilesystemBackend())
        >>> router.backend_name_for(str)
        'filesystem'
    """

    def __init__(self) -> None:
        self._routes: dict[type, tuple[str, StorageBackend]] = {}

    def register(self, data_type: type, backend_name: str, backend: StorageBackend) -> None:
        """Register the backend that should persist *data_type*.

        Args:
            data_type: The ``DataObject`` subtype to route.
            backend_name: Short backend identifier (e.g. ``"zarr"``, ``"arrow"``).
            backend: The backend instance that handles this type.
        """
        self._routes[data_type] = (backend_name, backend)

    def resolve(self, data_type: type) -> tuple[str, StorageBackend]:
        """Resolve *data_type* to its backend by walking the type's MRO.

        Returns the first registered ancestor, so a subtype inherits its base
        type's registration.

        Args:
            data_type: The type to resolve.

        Returns:
            A ``(backend_name, backend)`` tuple.

        Raises:
            KeyError: When no type in *data_type*'s MRO is registered.
        """
        for cls in data_type.__mro__:
            if cls in self._routes:
                return self._routes[cls]
        raise KeyError(f"No storage backend registered for {data_type.__name__}")

    def backend_for(self, data_type: type) -> StorageBackend:
        """Return the backend instance that persists *data_type*.

        Args:
            data_type: The type to resolve.

        Returns:
            The registered :class:`StorageBackend` for the type.

        Raises:
            KeyError: When no type in *data_type*'s MRO is registered.
        """
        return self.resolve(data_type)[1]

    def backend_name_for(self, data_type: type) -> str:
        """Return the backend name string for *data_type*.

        Args:
            data_type: The type to resolve.

        Returns:
            The short backend identifier (e.g. ``"zarr"``).

        Raises:
            KeyError: When no type in *data_type*'s MRO is registered.
        """
        return self.resolve(data_type)[0]

    def extension_for(self, data_type: type) -> str:
        """Return the on-disk file extension used by *data_type*'s backend.

        Args:
            data_type: The type to resolve.

        Returns:
            The extension string (e.g. ``".zarr"``, ``".parquet"``), or ``""``
            for composite directories.

        Raises:
            KeyError: When no type in *data_type*'s MRO is registered.
        """
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
    """Return the process-wide default :class:`BackendRouter`, building it once.

    The default router is built lazily on first access from the registered
    type-to-backend wiring.

    Returns:
        The shared :class:`BackendRouter` instance.

    Raises:
        RuntimeError: When the default wiring has not been registered yet —
            import ``scistudio.core.types`` first, which registers it.
    """
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
