"""ADR-048 extensible preview subsystem (SPEC 1 backend core).

core owns routing, session lifecycle, safety limits, bounded data access, API
compatibility, and generic fallback viewers; installed packages register
previewers through the ``scistudio.previewers`` entry point; projects may
register project-local previewers and defaults.

Public surface:

* Models — :class:`PreviewerSpec`, :class:`PreviewTarget`,
  :class:`PreviewEnvelope`, :class:`PreviewSession`, :class:`FrontendManifest`,
  the :data:`PreviewProvider` callable protocol, and the typed error hierarchy.
* :class:`PreviewerRegistry`, :class:`PreviewRouter`,
  :class:`PreviewSessionManager`, :class:`PreviewDataAccess`.
* :func:`build_preview_service` / :func:`get_preview_service` — a
  registry+router+session bundle the API runtime calls. Packages declare a
  ``scistudio.previewers`` entry point whose callable returns
  ``list[PreviewerSpec]`` (see :class:`PreviewerEntryPoint`).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from scistudio.previewers.data_access import PreviewDataAccess
from scistudio.previewers.models import (
    PREVIEWER_API_VERSION,
    DuplicatePreviewerIdError,
    EnvelopeKind,
    FrontendManifest,
    InvalidSpecError,
    MissingBundleError,
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
    PreviewSession,
    PreviewSource,
    PreviewTarget,
    ProviderError,
    RoutingAmbiguityError,
    TargetKind,
    UnknownPreviewerError,
    UnknownTargetError,
)
from scistudio.previewers.project import load_project_previewers
from scistudio.previewers.registry import PREVIEWER_ENTRY_POINT_GROUP, PreviewerRegistry
from scistudio.previewers.router import PreviewRouter
from scistudio.previewers.session import PreviewSessionManager

logger = logging.getLogger(__name__)


@dataclass
class PreviewService:
    """Bundle of the registry, router, and session manager for one runtime.

    The API runtime holds one of these. It is rebuilt on project switch so
    project-local previewers and defaults reflect the active project.
    """

    registry: PreviewerRegistry
    router: PreviewRouter
    sessions: PreviewSessionManager


def build_preview_service(
    *,
    project_dir: Path | None = None,
    include_monorepo: bool | None = None,
) -> PreviewService:
    """Build a fully-loaded :class:`PreviewService` (FR-001/FR-002/FR-030).

    Loads core specs unconditionally, then package specs (entry points + a
    monorepo dev fallback gated by ``SCISTUDIO_DEV=1`` unless *include_monorepo*
    is given explicitly), then project-local specs/defaults for *project_dir*.
    """
    if include_monorepo is None:
        include_monorepo = os.environ.get("SCISTUDIO_DEV") == "1"

    registry = PreviewerRegistry()
    registry.load_core()
    registry.load_packages(include_monorepo=include_monorepo)
    load_project_previewers(registry, project_dir)

    router = PreviewRouter(registry)
    sessions = PreviewSessionManager(registry)
    return PreviewService(registry=registry, router=router, sessions=sessions)


# Process-global default service so non-runtime callers (and the
# compatibility adapter before a runtime exists) can resolve previewers.
_default_service: PreviewService | None = None
_default_service_lock = threading.Lock()


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


__all__ = [
    "PREVIEWER_API_VERSION",
    "PREVIEWER_ENTRY_POINT_GROUP",
    "DuplicatePreviewerIdError",
    "EnvelopeKind",
    "FrontendManifest",
    "InvalidSpecError",
    "MissingBundleError",
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
    "PreviewRouter",
    "PreviewService",
    "PreviewSession",
    "PreviewSessionManager",
    "PreviewSource",
    "PreviewTarget",
    "PreviewerEntryPoint",
    "PreviewerRegistry",
    "PreviewerSpec",
    "ProviderError",
    "RoutingAmbiguityError",
    "TargetKind",
    "UnknownPreviewerError",
    "UnknownTargetError",
    "build_preview_service",
    "get_preview_service",
    "load_project_previewers",
]
