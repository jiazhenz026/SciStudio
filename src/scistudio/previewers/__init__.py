"""ADR-048 extensible preview subsystem (SPEC 1 backend core).

core owns routing, session lifecycle, safety limits, bounded data access, API
compatibility, and generic fallback viewers; installed packages register
previewers through the ``scistudio.previewers`` entry point; projects may
register project-local previewers and defaults.

**Author surface (ADR-052 §8):** the canonical author roots are
:mod:`scistudio.previewers.models`, :mod:`scistudio.previewers.data_access`, and
:mod:`scistudio.previewers.helpers` (``sanitize_svg``) — import the public types
from there, not from this package top level. The whole preview subsystem is
``provisional``.

**Operational layer (Internal):** :class:`PreviewerRegistry`,
:class:`PreviewRouter`, :class:`PreviewSessionManager`, :class:`PreviewService`,
:func:`build_preview_service`, :func:`get_preview_service`, and
:func:`load_project_previewers` are decorated ``@internal``: core owns this
machinery and it stays importable for the API runtime, but it carries no author
stability promise and is excluded from the generated reference. They are kept
importable from this module for the runtime; ``__all__`` no longer advertises
them as author surface. A package declares a ``scistudio.previewers`` entry
point whose callable returns ``list[PreviewerSpec]`` (see
:class:`PreviewerEntryPoint`) and otherwise only constructs the public model and
data-access types.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.previewers.data_access import PreviewDataAccess

# Public author symbols (ADR-052 §8.1) re-exported here for convenience; the
# canonical author root is ``scistudio.previewers.models``.
from scistudio.previewers.models import (
    PREVIEWER_API_VERSION,
    EnvelopeKind,
    FrontendManifest,
    OwnerKind,
    PreviewEnvelope,
    PreviewerEntryPoint,
    PreviewError,
    PreviewErrorCode,
    PreviewErrorInfo,
    PreviewerSpec,
    PreviewLimits,
    PreviewMetadata,
    PreviewProvider,
    PreviewRequest,
    PreviewResource,
    PreviewResourceProvider,
    PreviewSource,
    PreviewTarget,
    ProviderError,
    TargetKind,
)

# Back-compat re-exports kept importable from this package for existing callers
# (``scistudio.api.routes.data`` imports these two from here), but excluded from
# ``__all__`` so they are not advertised as author surface. Both are Internal
# (ADR-052 §8.1); the redundant ``as`` alias marks the intentional re-export.
# The other Internal model types (``PreviewSession`` and the remaining
# runtime-raised errors) and ``PREVIEWER_ENTRY_POINT_GROUP`` are no longer
# re-exported here — import them from the deep module
# (``scistudio.previewers.models`` / ``scistudio.previewers.registry``).
from scistudio.previewers.models import (
    UnknownPreviewerError as UnknownPreviewerError,
)
from scistudio.previewers.models import (
    UnknownTargetError as UnknownTargetError,
)
from scistudio.previewers.project import load_project_previewers
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter
from scistudio.previewers.session import PreviewSessionManager
from scistudio.stability import internal

logger = logging.getLogger(__name__)


@internal()
@dataclass
class PreviewService:
    """Bundle of the registry, router, and session manager for one runtime.

    The API runtime holds one of these. It is rebuilt on project switch so
    project-local previewers and defaults reflect the active project.
    """

    registry: PreviewerRegistry
    router: PreviewRouter
    sessions: PreviewSessionManager


@internal()
def build_preview_service(
    *,
    project_dir: Path | None = None,
    child_context_resolver: Callable[[PreviewTarget, dict[str, Any]], tuple[PreviewTarget, dict[str, Any]]]
    | None = None,
) -> PreviewService:
    """Build a fully-loaded :class:`PreviewService` (FR-001/FR-002/FR-030).

    Loads core specs unconditionally, then package specs (discovered via
    ``scistudio.previewers`` entry points), then project-local specs/defaults
    for *project_dir*.
    """
    registry = PreviewerRegistry()
    registry.load_core()
    registry.load_packages()
    load_project_previewers(registry, project_dir)

    router = PreviewRouter(registry)
    sessions = PreviewSessionManager(
        registry,
        child_context_resolver=child_context_resolver,
    )
    return PreviewService(registry=registry, router=router, sessions=sessions)


# Process-global default service so non-runtime callers (and the
# compatibility adapter before a runtime exists) can resolve previewers.
_default_service: PreviewService | None = None
_default_service_lock = threading.Lock()


@internal()
def get_preview_service(*, project_dir: Path | None = None, refresh: bool = False) -> PreviewService:
    """Return a process-global :class:`PreviewService`, building it on first use.

    The API runtime is the authoritative owner of a per-project service; this
    accessor exists for callers without a runtime handle (e.g. unit tests and
    the one-shot compatibility path). Pass ``refresh=True`` to rebuild.
    """
    global _default_service
    with _default_service_lock:
        if _default_service is None or refresh:
            _default_service = build_preview_service(project_dir=project_dir)
        return _default_service


# ``__all__`` advertises only the public author surface re-exported for
# convenience; the canonical roots are ``.models`` / ``.data_access`` /
# ``.helpers`` (ADR-052 §8). The Internal operational layer (PreviewerRegistry,
# PreviewRouter, PreviewSessionManager, PreviewService, build_preview_service,
# get_preview_service, load_project_previewers) stays importable from this module
# for the API runtime but is decorated ``@internal`` and excluded here so it is
# not advertised as author surface. ``UnknownPreviewerError`` /
# ``UnknownTargetError`` remain importable (back-compat) but are likewise excluded.
__all__ = [
    "PREVIEWER_API_VERSION",
    "EnvelopeKind",
    "FrontendManifest",
    "OwnerKind",
    "PreviewDataAccess",
    "PreviewEnvelope",
    "PreviewError",
    "PreviewErrorCode",
    "PreviewErrorInfo",
    "PreviewLimits",
    "PreviewMetadata",
    "PreviewProvider",
    "PreviewRequest",
    "PreviewResource",
    "PreviewResourceProvider",
    "PreviewSource",
    "PreviewTarget",
    "PreviewerEntryPoint",
    "PreviewerSpec",
    "ProviderError",
    "TargetKind",
]
