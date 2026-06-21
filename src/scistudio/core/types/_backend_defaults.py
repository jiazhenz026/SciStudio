"""Default ``type -> backend`` wiring for SciStudio's six core data types.

#1342 / round-4 no-cycles: this wiring used to live in
``scistudio.core.storage._defaults`` and imported the six concrete type
classes — a ``core.storage -> core.types`` edge that, together with
``DataObject.save`` reaching into ``backend_router``, closed the
``core.types <-> core.storage`` import cycle.

Hosting it on the ``core.types`` side inverts that edge to the natural
direction (``core.types -> core.storage``): the storage layer holds only a
builder *callback* (see :func:`scistudio.core.storage.backend_router.set_default_builder`)
and never imports a concrete type. Building stays lazy — ``get_router``
invokes this builder on first access — so behaviour is identical to the
pre-#1342 form. The ``type -> backend`` pairings themselves are unchanged;
only their definition site moved.

ADR-031 governs ``scistudio.core.storage``; this module only relocates the
default wiring and does not change any storage contract.
"""

from __future__ import annotations

from scistudio.core.storage.arrow_backend import ArrowBackend
from scistudio.core.storage.backend_router import BackendRouter, set_default_builder
from scistudio.core.storage.composite_store import CompositeStore
from scistudio.core.storage.filesystem import FilesystemBackend
from scistudio.core.storage.zarr_backend import ZarrBackend
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text


def build_default() -> BackendRouter:
    """Build a ``BackendRouter`` with the standard six type -> backend mappings."""
    router = BackendRouter()
    zarr = ZarrBackend()
    arrow = ArrowBackend()
    fs = FilesystemBackend()
    composite = CompositeStore()

    router.register(Array, "zarr", zarr)
    router.register(Series, "arrow", arrow)
    router.register(DataFrame, "arrow", arrow)
    router.register(Text, "filesystem", fs)
    router.register(Artifact, "filesystem", fs)
    router.register(CompositeData, "composite", composite)
    return router


# Hand the builder to the storage layer at import time. ``core.types.__init__``
# imports this module, and importing any DataObject runs that package __init__,
# so the callback is registered before any ``save`` / ``get_router`` call.
set_default_builder(build_default)
