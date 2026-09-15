"""The runtime's panel subsystem: catalog, routing, sessions, contexts and watches."""
# Maintainer context (kept outside generated API documentation):
# ADR-054 §2 "one panel subsystem whose operations are decided by the context
# that opened it" (#2465). One :class:`PanelService` per API runtime, built once
# and never rebuilt. It owns:
#
# * the panel catalog: a :class:`~scistudio.panels.registry.PanelRegistry` from
#   :func:`~scistudio.panels.registry.discover_panels`, merged with the
#   deprecated previewers into one namespace (FR-007);
# * routing: :class:`~scistudio.panels.router.PanelRouter`, the only ladder;
# * preview sessions routed to a panel, and the call path into the legacy
#   renderer when a legacy previewer wins (:mod:`scistudio.panels.legacy`);
# * panel contexts and their ``panel.py`` processes;
# * change watching: the panel tiers (rescan) and every open panel's page
#   (``panel.files_changed``);
# * project switch.
#
# A catalog change is applied incrementally. The service diffs the old catalog
# against the new one by descriptor fingerprint, revokes only the contexts on a
# panel that was removed, changed or shadowed (``panel.contexts_revoked``), and
# announces the diff on ``blocks.reloaded`` with the preview type claims whose
# candidates changed, so the host re-routes only the previews those claims
# affect. Unrelated panels, and the MiniApps open on them, are untouched.
#
# Locking: state is an immutable snapshot swapped under ``_lock``; readers
# (routing, lookups, contexts) never take ``_lock``. Contexts are revoked and
# events emitted after ``_lock`` is released.
# Development references: #2421, #2428, #2455, #2465, ADR-048, ADR-054.

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scistudio.engine.events import EngineEvent
from scistudio.panels.contexts import PANEL_EVENTS, PanelContexts, project_key
from scistudio.panels.descriptor import PanelDescriptor
from scistudio.panels.legacy import LegacyFactory, LegacyPreviewers, build_legacy_service
from scistudio.panels.registry import (
    PanelRegistry,
    PanelSourcesFingerprint,
    RegistryDiff,
    diff_panels,
    discover_panels,
    panel_fingerprint,
    panel_sources_fingerprint,
)
from scistudio.panels.router import CandidateSet, PanelRouter, merge_candidates, spec_claim
from scistudio.panels.sessions import PreviewSessions, routing_error_envelope
from scistudio.panels.watcher import PanelFileWatches, PanelSourceWatcher
from scistudio.previewers.models import (
    PreviewEnvelope,
    PreviewError,
    PreviewerSpec,
    PreviewTarget,
    UnknownPreviewerError,
)
from scistudio.stability import internal

logger = logging.getLogger(__name__)

#: Announces a catalog change; the workspace re-reads the catalogs the payload names.
REGISTRIES_CHANGED = "blocks.reloaded"
#: Data: ``{"context_ids": [...], "panel_ids": [...], "reason": str}``.
PANEL_CONTEXTS_REVOKED = "panel.contexts_revoked"
#: Data: ``{"type": str}``: open previews of that type re-route.
PANEL_CHOICES_CHANGED = "panel.choices_changed"

Discover = Callable[[Path | None, Any], PanelRegistry]
ChoicesLoader = Callable[[Path | None], dict[str, str]]


def _default_discover(project_dir: Path | None, registered_types: Any) -> PanelRegistry:
    return discover_panels(project_dir, registered_types=registered_types)


def _default_choices(project_dir: Path | None) -> dict[str, str]:
    from scistudio.previewers.choices import load_choices

    return load_choices(project_dir)


@dataclass(frozen=True)
class _State:
    panels: PanelRegistry = field(default_factory=PanelRegistry)
    candidates: CandidateSet = field(default_factory=CandidateSet)
    sources: PanelSourcesFingerprint | None = None
    choices: Mapping[str, str] = field(default_factory=dict)
    project: tuple[Any, ...] | None = None
    generation: int = 0


@internal()
class PanelService:
    """The runtime-owned panel subsystem: one per runtime, never rebuilt."""

    def __init__(
        self,
        runtime: Any,
        *,
        discover: Discover = _default_discover,
        legacy_factory: LegacyFactory = build_legacy_service,
        choices_loader: ChoicesLoader = _default_choices,
    ) -> None:
        self.runtime = runtime
        self.event_bus = getattr(runtime, "event_bus", None)
        self.loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.RLock()
        self._discover = discover
        self._choices_loader = choices_loader
        self._state = _State()
        self._loaded = False
        self._tasks: set[asyncio.Task[None]] = set()
        resolver = getattr(runtime, "resolve_child_preview_context", None)
        self.legacy = LegacyPreviewers(
            factory=legacy_factory,
            child_context_resolver=resolver,
            child_session=self._child_session,
            resolver=self.route,
        )
        self.sessions = PreviewSessions(child_context_resolver=resolver, child_session=self._child_session)
        self.file_watches = PanelFileWatches(event_bus=self.event_bus)
        self.contexts = PanelContexts(runtime, self)
        self._source_watcher = PanelSourceWatcher(self._on_source_change)
        self._watching = False
        self._subscribed = False
        self._subscribe()

    def _subscribe(self) -> None:
        if self.event_bus is None or self._subscribed:
            return
        for event in PANEL_EVENTS:
            self.event_bus.subscribe(event, self.contexts.on_event)
        self._subscribed = True

    # -- lifecycle ------------------------------------------------------------

    @property
    def project_dir(self) -> Path | None:
        project = getattr(self.runtime, "active_project", None)
        return None if project is None else Path(project.path)

    @property
    def generation(self) -> int:
        return self._state.generation

    def remember_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """Hand events from watch threads to *loop* (the API event loop)."""
        if loop is not None:
            self.loop = loop
            self.file_watches.loop = loop

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Load the catalog and start watching the panel tiers."""
        self.remember_loop(loop)
        self._subscribe()
        self.ensure_loaded()
        self._watching = True
        self._arm_source_watch()

    def stop(self) -> None:
        """Stop the watches and close every context (application shutdown)."""
        self._watching = False
        self._source_watcher.stop()
        self.contexts.close_all()
        self.file_watches.stop_all()
        if self.event_bus is not None and self._subscribed:
            for event in PANEL_EVENTS:
                self.event_bus.unsubscribe(event, self.contexts.on_event)
            self._subscribed = False

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            project_dir = self.project_dir
            self.legacy.rebuild(project_dir)
            sources = panel_sources_fingerprint(project_dir)
            self._state = self._compose(
                self._discover(project_dir, self._registered_types()),
                sources=sources,
                choices=self._choices_loader(project_dir),
                generation=1,
            )
            self._loaded = True

    def close_project(self) -> list[str]:
        """End every context and process of the project being left, immediately."""
        closed = self.contexts.close_project()
        self.sessions.clear()
        if closed:
            self._emit(PANEL_CONTEXTS_REVOKED, {"context_ids": closed, "panel_ids": [], "reason": "project_switch"})
        return closed

    def refresh(self) -> RegistryDiff:
        """Every registry was rebuilt: rescan the legacy previewers, then the panels.

        When the open project changed since the last load this is a project
        switch: contexts of the old project end, the choices are re-read and the
        tier watch is re-armed on the new project's panel folders.
        """
        if not self._loaded:
            # First use: loading already read every tier for the open project.
            self.ensure_loaded()
            return RegistryDiff()
        switching = self._state.project != project_key(self.runtime)
        if switching:
            self.close_project()
        diff = self.rescan(force=True, legacy=True, reload_choices=switching)
        if switching and self._watching:
            self._arm_source_watch()
        return diff

    def ensure_fresh(self) -> RegistryDiff:
        """Bring the catalog up to date when the panel folders changed on disk."""
        # Development references: #2421.
        return self.rescan()

    def rescan(self, *, force: bool = False, legacy: bool = False, reload_choices: bool = False) -> RegistryDiff:
        """Rediscover the panels and apply the difference incrementally.

        Without ``force`` nothing is rediscovered while the panel folders look
        unchanged (stats and listings only). ``legacy`` rescans the deprecated
        previewers first.
        """
        self.ensure_loaded()
        with self._lock:
            project_dir = self.project_dir
            sources = panel_sources_fingerprint(project_dir)
            old = self._state
            if not (force or legacy or reload_choices) and sources == old.sources:
                return RegistryDiff()
            if legacy:
                self.legacy.rebuild(project_dir)
            choices = self._choices_loader(project_dir) if reload_choices else old.choices
            new = self._compose(
                self._discover(project_dir, self._registered_types()),
                sources=sources,
                choices=choices,
                generation=old.generation + 1,
            )
            diff = diff_panels(
                old.candidates.panels,
                new.candidates.panels,
                old_candidates=_candidate_keys(old.candidates),
                new_candidates=_candidate_keys(new.candidates),
                catalog_changed=_catalog_summary(old.candidates) != _catalog_summary(new.candidates),
                legacy_reloaded=legacy,
            )
            self._state = new
        self._apply(diff, new.candidates.panels, reason="panel_changed")
        return diff

    def _apply(self, diff: RegistryDiff, current: Mapping[str, PanelDescriptor], *, reason: str) -> None:
        invalidated = diff.invalidated
        if invalidated:
            self.sessions.discard(invalidated)
            closed = self.contexts.invalidate_panels(invalidated, current)
            if closed:
                self._emit(
                    PANEL_CONTEXTS_REVOKED,
                    {"context_ids": closed, "panel_ids": sorted(invalidated), "reason": reason},
                )
        if not diff.empty:
            logger.info(
                "panel catalog: added=%s removed=%s changed=%s preview_types=%s legacy_reloaded=%s",
                sorted(diff.added),
                sorted(diff.removed),
                sorted(diff.changed),
                sorted(diff.preview_types),
                diff.legacy_reloaded,
            )
            self._emit(REGISTRIES_CHANGED, diff.to_event_data())

    def _compose(
        self,
        panels: PanelRegistry,
        *,
        sources: PanelSourcesFingerprint | None,
        choices: Mapping[str, str],
        generation: int,
    ) -> _State:
        candidates = merge_candidates(
            panels=panels.panels,
            shadowed_panels=panels.shadowed,
            panel_diagnostics=panels.diagnostics,
            legacy_specs=self.legacy.specs(),
            legacy_shadowed=self.legacy.shadowed(),
            legacy_diagnostics=self.legacy.diagnostics(),
        )
        return _State(
            panels=panels,
            candidates=candidates,
            sources=sources,
            choices=dict(choices),
            project=project_key(self.runtime),
            generation=generation,
        )

    def _registered_types(self) -> Any:
        registry = getattr(self.runtime, "type_registry", None)
        all_types = getattr(registry, "all_types", None)
        if not callable(all_types):
            return None
        try:
            return tuple(all_types().keys())
        except Exception:
            logger.debug("panel catalog: type registry unavailable; discovery scans types itself", exc_info=True)
            return None

    def _arm_source_watch(self) -> None:
        from scistudio.core.dropins import panel_scan_dirs

        try:
            self._source_watcher.start(tuple(panel_scan_dirs(self.project_dir)))
        except Exception:
            logger.warning("panel source watcher: not started", exc_info=True)

    def _on_source_change(self) -> None:
        self.rescan()

    # -- catalog --------------------------------------------------------------

    def panel(self, panel_id: str) -> PanelDescriptor | None:
        """The winning panel for *panel_id*, the only one a context may open."""
        self.ensure_loaded()
        return self._state.candidates.panels.get(panel_id)

    @staticmethod
    def panel_fingerprint(panel: PanelDescriptor) -> tuple[object, ...]:
        return panel_fingerprint(panel)

    def registry(self) -> PanelRegistry:
        """A copy of the effective panel catalog: winners, shadowed, diagnostics."""
        self.ensure_loaded()
        state = self._state
        view = PanelRegistry()
        view.panels = dict(state.candidates.panels)
        view.shadowed = list(state.candidates.shadowed_panels)
        view.diagnostics = list(state.panels.diagnostics)
        return view

    def catalog(self) -> dict[str, Any]:
        """``GET /api/panels/catalog``: winners, then shadowed panels, with diagnostics."""
        self.ensure_fresh()
        registry = self.registry()
        return {
            "panels": [
                panel.to_dict() | {"owner_kind": panel.owner_kind.value, "shadowed": False}
                for panel in registry.panels.values()
            ]
            + [
                panel.to_dict() | {"owner_kind": panel.owner_kind.value, "shadowed": True}
                for panel in registry.shadowed
            ],
            "diagnostics": registry.diagnostics,
        }

    def miniapps(self) -> dict[str, PanelDescriptor]:
        """Every winning panel that opens as a MiniApp, fresh from disk."""
        self.ensure_fresh()
        return {
            panel_id: panel for panel_id, panel in self._state.candidates.panels.items() if "miniapp" in panel.contexts
        }

    def all_specs(self) -> list[PreviewerSpec]:
        """Every routing candidate, panels and legacy previewers alike."""
        self.ensure_loaded()
        return list(self._state.candidates.routable)

    def previewer(self, previewer_id: str) -> PreviewerSpec | None:
        """The namespace winner for *previewer_id* (a panel card or a legacy spec)."""
        self.ensure_loaded()
        return self._state.candidates.by_id.get(previewer_id)

    def previewer_catalog(self) -> tuple[list[tuple[PreviewerSpec, bool]], list[str]]:
        """The Previewers listing: every card with whether it is shadowed, and diagnostics."""
        self.ensure_loaded()
        candidates = self._state.candidates
        return candidates.catalog_specs(), list(candidates.diagnostics)

    def legacy_service(self) -> Any:
        """The deprecated previewers' ``PreviewService`` (registry + sessions)."""
        self.ensure_loaded()
        return self.legacy.service

    # -- choices --------------------------------------------------------------

    def choices(self) -> dict[str, str]:
        self.ensure_loaded()
        return dict(self._state.choices)

    def set_choice(self, path: Path, target_type: str, previewer_id: str) -> None:
        """Persist a choice at the layer *path* and re-route previews of *target_type*."""
        from scistudio.previewers.choices import write_choice

        write_choice(path, target_type, previewer_id)
        self._choices_changed(target_type)

    def clear_choice(self, path: Path, target_type: str) -> None:
        """Remove the choice at the layer *path* and re-route previews of *target_type*."""
        from scistudio.previewers.choices import clear_choice

        clear_choice(path, target_type)
        self._choices_changed(target_type)

    def _choices_changed(self, target_type: str) -> None:
        self.ensure_loaded()
        with self._lock:
            old = self._state
            choices = self._choices_loader(self.project_dir)
            self._state = _State(
                panels=old.panels,
                candidates=old.candidates,
                sources=old.sources,
                choices=choices,
                project=old.project,
                generation=old.generation + 1,
            )
        self._emit(PANEL_CHOICES_CHANGED, {"type": target_type})

    # -- routing and sessions -------------------------------------------------

    def router(self) -> PanelRouter:
        self.ensure_loaded()
        state = self._state
        return PanelRouter(
            state.candidates.routable,
            choices=state.choices,
            project_default=self.legacy.project_default_for,
        )

    def route(self, target: PreviewTarget, query: Mapping[str, Any] | None = None) -> PreviewerSpec:
        """The candidate that previews *target* (``core_only`` / ``panel_id`` honoured)."""
        return self.router().select(target, query)

    def create_preview_session(
        self,
        target: PreviewTarget,
        query: dict[str, Any] | None = None,
        *,
        guard: Callable[[], None] | None = None,
        authority: Any = None,
        fresh: bool = False,
    ) -> PreviewEnvelope:
        """Route *target* and open a session on the renderer of the winner."""
        if fresh:
            self.ensure_fresh()
        query = dict(query or {})
        if guard is not None:
            guard()
        try:
            spec = self.route(target, query)
        except PreviewError as exc:
            return routing_error_envelope(target, exc)
        if spec.panel is not None:
            return self.sessions.create_session(spec, target, query, guard=guard, authority=authority)
        return self.legacy.create_session(spec, target, query, guard=guard, authority=authority)  # type: ignore[no-any-return]

    def _child_session(self, target: PreviewTarget, query: dict[str, Any]) -> PreviewEnvelope:
        return self.create_preview_session(target, query)

    def _api_version(self, panel_id: str) -> str | None:
        panel = self._state.candidates.panels.get(panel_id)
        return None if panel is None else panel.api_version

    def _legacy_sessions(self, session_id: str) -> Any:
        if self.sessions.owns(session_id):
            return None
        if self.legacy.owns(session_id):
            return self.legacy.sessions
        raise UnknownPreviewerError(f"Unknown preview session: {session_id}", detail={"session_id": session_id})

    def read_session(self, session_id: str) -> PreviewEnvelope:
        legacy = self._legacy_sessions(session_id)
        if legacy is None:
            return self.sessions.read_session(session_id, self._api_version)
        return legacy.read_session(session_id)  # type: ignore[no-any-return]

    def patch_session(self, session_id: str, query_patch: dict[str, Any]) -> PreviewEnvelope:
        legacy = self._legacy_sessions(session_id)
        if legacy is None:
            return self.sessions.patch_session(session_id, query_patch, self._api_version)
        return legacy.patch_session(session_id, query_patch)  # type: ignore[no-any-return]

    def read_resource(self, session_id: str, resource_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        store = self._legacy_sessions(session_id) or self.sessions
        return store.read_resource(session_id, resource_id, params)  # type: ignore[no-any-return]

    def save_resource(
        self, session_id: str, resource_id: str, destination: Path, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        store = self._legacy_sessions(session_id) or self.sessions
        return store.save_resource(session_id, resource_id, destination, params)  # type: ignore[no-any-return]

    def frozen_session(self, session_id: str) -> Any:
        store = self._legacy_sessions(session_id) or self.sessions
        return store.frozen_session(session_id)

    def session_authority(self, session_id: str) -> Any:
        store = self._legacy_sessions(session_id) or self.sessions
        return store.session_authority(session_id)

    # -- contexts -------------------------------------------------------------

    def open_context(self, payload: dict[str, Any], *, process_registry: Any = None) -> Any:
        """Open a panel context on a catalog brought up to date first."""
        self.ensure_fresh()
        return self.contexts.create(payload, process_registry=process_registry)

    # -- events ---------------------------------------------------------------

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        bus = self.event_bus
        if bus is None:
            return
        event = EngineEvent(event_type=event_type, data=data)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None:
            task = running.create_task(bus.emit(event))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return
        loop = self.loop
        if loop is not None and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(bus.emit(event), loop)
                return
            except RuntimeError:
                logger.debug("panel service: loop closed while emitting %s", event_type)
        with contextlib.suppress(Exception):
            asyncio.run(bus.emit(event))


def _candidate_keys(candidates: CandidateSet) -> set[tuple[object, ...]]:
    return {
        (spec_claim(spec), spec.previewer_id, spec.owner_kind.value, spec.priority, spec.panel is not None)
        for spec in candidates.routable
    }


def _catalog_summary(candidates: CandidateSet) -> tuple[object, ...]:
    return (
        tuple((spec.previewer_id, spec.owner_kind.value, shadowed) for spec, shadowed in candidates.catalog_specs()),
        candidates.diagnostics,
    )


_SERVICE_LOCK = threading.Lock()


def get_panel_service(runtime: Any) -> PanelService:
    """The runtime's one panel service, built on first use and never rebuilt."""
    service = getattr(runtime, "_panel_service", None)
    if service is None:
        with _SERVICE_LOCK:
            service = getattr(runtime, "_panel_service", None)
            if service is None:
                service = PanelService(runtime)
                runtime._panel_service = service
    return service  # type: ignore[no-any-return]


__all__ = [
    "PANEL_CHOICES_CHANGED",
    "PANEL_CONTEXTS_REVOKED",
    "REGISTRIES_CHANGED",
    "PanelService",
    "get_panel_service",
]
