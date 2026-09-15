"""The deprecated Python previewers, as the panel service's fallback renderer."""
# Maintainer context (kept outside generated API documentation):
# ADR-054 §8: the Python previewer forms stay as deprecated compatibility
# and are removed in 0.3.6. This module is the single call path
# from the panel subsystem into that code. It contributes candidates (and
# project default declarations) to the one routing ladder, renders the preview
# when a legacy candidate wins, and holds the legacy sessions. It never holds,
# installs or rebuilds a panel. Removing the legacy previewers in 0.3.6 is
# removing this module and its uses in :mod:`scistudio.panels.service`.
# Development references: #2465, ADR-048, ADR-054.

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scistudio.panels.sessions import ChildContextResolver, ChildSessionFactory
from scistudio.previewers.models import PreviewerSpec, PreviewTarget
from scistudio.stability import internal

#: ``(project_dir, child_context_resolver) -> PreviewService``.
LegacyFactory = Callable[[Path | None, ChildContextResolver | None], Any]
#: ``(target, query) -> spec``: the panel service's router.
SpecResolver = Callable[[PreviewTarget, dict[str, Any]], PreviewerSpec]


def build_legacy_service(project_dir: Path | None, child_context_resolver: ChildContextResolver | None) -> Any:
    from scistudio.previewers import build_preview_service

    return build_preview_service(project_dir=project_dir, child_context_resolver=child_context_resolver)


@internal()
class LegacyPreviewers:
    """The legacy previewer registry and session manager for one project."""

    def __init__(
        self,
        *,
        factory: LegacyFactory = build_legacy_service,
        child_context_resolver: ChildContextResolver | None = None,
        child_session: ChildSessionFactory | None = None,
        resolver: SpecResolver | None = None,
    ) -> None:
        self._factory = factory
        self._child_context_resolver = child_context_resolver
        self._child_session = child_session
        self._resolver = resolver
        self._lock = threading.Lock()
        self._service: Any = None
        self.generation = 0

    @property
    def service(self) -> Any:
        """The current ``PreviewService`` (registry + sessions); built on first use."""
        service = self._service
        if service is None:
            raise RuntimeError("legacy previewers are not loaded; call rebuild() first")
        return service

    @property
    def loaded(self) -> bool:
        return self._service is not None

    def rebuild(self, project_dir: Path | None) -> None:
        """Rescan every legacy tier for *project_dir*; open legacy sessions end."""
        service = self._factory(project_dir, self._child_context_resolver)
        self._wire(service)
        with self._lock:
            self._service = service
            self.generation += 1

    def adopt(self, service: Any) -> None:
        """Use an already-built ``PreviewService`` (tests, standalone hosts)."""
        self._wire(service)
        with self._lock:
            self._service = service
            self.generation += 1

    def _wire(self, service: Any) -> None:
        sessions = service.sessions
        if self._resolver is not None and hasattr(sessions, "set_resolver"):
            sessions.set_resolver(self._resolver)
        if self._child_session is not None and hasattr(sessions, "set_child_session"):
            sessions.set_child_session(self._child_session)

    # -- candidates ---------------------------------------------------------

    def specs(self) -> list[PreviewerSpec]:
        return list(self.service.registry.all_specs()) if self.loaded else []

    def shadowed(self) -> list[PreviewerSpec]:
        registry = self.service.registry if self.loaded else None
        shadowed = getattr(registry, "shadowed_specs", None)
        return list(shadowed()) if callable(shadowed) else []

    def diagnostics(self) -> list[str]:
        return list(self.service.registry.diagnostics) if self.loaded else []

    def project_default_for(self, type_name: str) -> str | None:
        return self.service.registry.project_default_for(type_name) if self.loaded else None

    def get(self, previewer_id: str) -> PreviewerSpec | None:
        return self.service.registry.get(previewer_id) if self.loaded else None

    # -- sessions -----------------------------------------------------------

    def owns(self, session_id: str) -> bool:
        return self.loaded and bool(self.service.sessions.owns(session_id))

    def create_session(
        self,
        spec: PreviewerSpec,
        target: PreviewTarget,
        query: dict[str, Any],
        *,
        guard: Callable[[], None] | None = None,
        authority: Any = None,
    ) -> Any:
        return self.service.sessions.create_session(target, query, spec=spec, guard=guard, authority=authority)

    @property
    def sessions(self) -> Any:
        return self.service.sessions


__all__ = ["LegacyPreviewers", "build_legacy_service"]
