"""Default ``type -> backend`` wiring for ``scistudio.core.storage``.

This module is the single place that knows the concrete pairings between
SciStudio's six core data types and their persistence backends. It exists
to break the ``core.types <-> core.storage.backend_router`` circular import
chain tracked in #1335 by isolating the type-level imports here, away from
``backend_router.py``.

The public ``get_router`` symbol remains in
``scistudio.core.storage.backend_router`` (it lazy-imports
:func:`build_default` from this module) so existing call sites and the
``patch("scistudio.core.storage.backend_router.get_router")`` monkeypatch
target keep working unchanged.

Governance: ADR-031 (Data Object Reference-Only Contract, ViewProxy
Elimination, And Lazy Loading Enforcement) governs
``scistudio.core.storage``. The extraction itself is tracked at #1335 and
its umbrella PR #1344; the residual lazy-import debt is tracked at #1342.
"""

from __future__ import annotations

from scistudio.core.storage.arrow_backend import ArrowBackend
from scistudio.core.storage.backend_router import BackendRouter
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
