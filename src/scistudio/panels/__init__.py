"""The extensible preview subsystem (backend core).

A *preview* turns a stored data object, collection, or artifact into a bounded,
JSON-safe view the frontend can display. The core owns routing, session
lifecycle, safety limits, bounded data access, API compatibility, and the
generic fallback viewers. Installed packages add their own panels through
the ``scistudio.previewers`` entry point, the user library registers
panels for every project (``~/.scistudio/previewers``), and a project may
register project-local panels and defaults.

If you are writing a panel, import the public types from the canonical
author roots — :mod:`scistudio.panels.models`,
:mod:`scistudio.panels.data_access`, and
:mod:`scistudio.panels.helpers` (``sanitize_svg``) — rather than from this
package top level. Your package wires a ``scistudio.previewers`` entry point to
a callable returning ``list[PanelSpec]`` (see :class:`PanelEntryPoint`)
and otherwise only constructs the public model and data-access types. The whole
preview subsystem is **provisional**.

The operational layer — :class:`PanelRegistry`, :class:`PreviewRouter`,
:class:`PreviewSessionManager`, :class:`PreviewService`,
:func:`build_preview_service`, :func:`get_preview_service`,
:func:`load_project_panels`, and :func:`load_user_panels` — is
core-internal machinery. It stays
importable for the API runtime but carries no author stability promise and is
excluded from the generated reference, so it is not advertised here as author
surface.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scistudio.core.dropins import panel_roots
from scistudio.panels.choices import load_choice_layers

# ADR-048 compatibility shim (FR-042). Deleted with the module it names.
from scistudio.panels.compat import install_compat_panels
from scistudio.panels.data_access import PreviewDataAccess
from scistudio.panels.discovery import PanelDiscovery, discover_panels, register_discovered_panels

# Public author symbols (ADR-052 §8.1) re-exported here for convenience; the
# canonical author root is ``scistudio.panels.models``.
from scistudio.panels.models import (
    PANEL_API_VERSION,
    EnvelopeKind,
    FrontendManifest,
    OwnerKind,
    PanelEntryPoint,
    PanelSpec,
    PreviewEnvelope,
    PreviewError,
    PreviewErrorCode,
    PreviewErrorInfo,
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
# (``scistudio.panels.models`` / ``scistudio.panels.registry``).
from scistudio.panels.models import (
    UnknownPanelError as UnknownPanelError,
)
from scistudio.panels.models import (
    UnknownTargetError as UnknownTargetError,
)
from scistudio.panels.project import load_project_panels, load_user_panels
from scistudio.panels.registry import PanelRegistry
from scistudio.panels.router import PreviewRouter
from scistudio.panels.session import PreviewSessionManager
from scistudio.stability import internal

logger = logging.getLogger(__name__)


@internal()
@dataclass
class PreviewService:
    """Bundle of the registry, router, and session manager for one runtime.

    The API runtime holds one of these. It is rebuilt on project switch so
    project-local panels and defaults reflect the active project.
    """

    registry: PanelRegistry
    router: PreviewRouter
    sessions: PreviewSessionManager
    panels: PanelDiscovery = field(default_factory=PanelDiscovery)
    """What the four-tier on-disk scan found (ADR-054 spec 1 FR-018/FR-019).

    Held beside the registry rather than inside it because the two answer
    different questions: the registry answers "which panel renders this type",
    and this answers "which directory is this panel's document served from, and
    which tier did it win from". The asset route and the discovery surface read
    it; routing reads the registry.
    """


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
    for *project_dir*, then user-library specs. The user tier loads
    unconditionally — it does not depend on an open project (#2017, mirroring
    the user type/block tiers) — but *which* library answers as the user tier
    follows *project_dir*: a tutorial project's user tier is the
    tutorial-scoped library (Learning Center FR-070/FR-071, #2086). Project
    loads before user so a project panel shadows a user panel with the
    same id, matching the project-first registration order the type registry
    uses.

    The person's per-type panel choices load last (#2049). They are read
    after discovery because a choice is only usable once the panel it names
    is registered; loading them here means every event that rebuilds the
    registry also re-reads them, so a choice written to disk takes effect on
    the next reload without a separate refresh path.
    """
    registry = PanelRegistry()
    registry.load_core()
    registry.load_packages()
    load_project_panels(registry, project_dir)
    load_user_panels(registry, project_dir)

    # ADR-054 spec 1 FR-018/FR-046: the on-disk scan, across all four tiers.
    # It runs here and only here, which is what makes FR-046's "takes effect
    # after a registry rebuild" true: rebuilding the service *is* rescanning,
    # and there is no other path by which a directory added to a project
    # becomes visible.
    project_roots = panel_roots(project_dir)
    discovery = discover_panels(
        user_roots=project_roots[-1:],
        project_roots=project_roots[:-1],
    )
    register_discovered_panels(registry, discovery)

    # ADR-048 compatibility shim (FR-042, FR-043). Last, and only for an id no
    # directory claimed, so a package that has migrated shadows its own shim
    # without anybody withdrawing anything. Removed as a unit with
    # ``scistudio.panels.compat``; that module's docstring lists every piece.
    install_compat_panels(registry, discovery)

    registry.set_panel_choices(load_choice_layers(project_dir))

    router = PreviewRouter(registry)
    sessions = PreviewSessionManager(
        registry,
        child_context_resolver=child_context_resolver,
        project_dir=project_dir,
    )
    return PreviewService(registry=registry, router=router, sessions=sessions, panels=discovery)


# Process-global default service so non-runtime callers (and the
# compatibility adapter before a runtime exists) can resolve panels.
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
# ``.helpers`` (ADR-052 §8). The Internal operational layer (PanelRegistry,
# PreviewRouter, PreviewSessionManager, PreviewService, build_preview_service,
# get_preview_service, load_project_panels, load_user_panels) stays
# importable from this module
# for the API runtime but is decorated ``@internal`` and excluded here so it is
# not advertised as author surface. ``UnknownPanelError`` /
# ``UnknownTargetError`` remain importable (back-compat) but are likewise excluded.
__all__ = [
    "PANEL_API_VERSION",
    "EnvelopeKind",
    "FrontendManifest",
    "OwnerKind",
    "PanelEntryPoint",
    "PanelSpec",
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
    "ProviderError",
    "TargetKind",
]
