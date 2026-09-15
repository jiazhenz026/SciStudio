"""Keep the panel catalog in step with the panel directories on disk."""
# Maintainer context (kept outside generated API documentation):
# #2421. The runtime discovers panels once, when it builds its preview
# service, and every MiniApp surface reads that registry: the MiniApps tab
# (``GET /api/panels/miniapps``), the catalog, and the context a MiniApp tab
# opens. A MiniApp written into ``<project>/panels/`` afterwards stayed
# invisible until something rebuilt the registries, while ``open_miniapp``
# (which discovers afresh) already accepted it. Two pieces close that gap for
# every writer, whether an agent tool, the editor, or an external program:
#
# * **Read side.** :func:`current_preview_service` compares the service's
#   recorded :func:`~scistudio.panels.registry.panel_sources_fingerprint` with
#   the directories now and rebuilds the service when they differ. The MiniApp
#   list, the catalog, and MiniApp context creation go through it, so what they
#   answer always matches the directories, with no debounce window in which a
#   just-written MiniApp is missing.
# * **Push side.** :class:`PanelCatalogRefresher` is fed by
#   :class:`PanelCatalogHandler`, a watch on the panel tiers. After a 500 ms
#   quiet period (a MiniApp is several writes: ``panel.json`` usually lands
#   before ``index.html``) it brings the service up to date and broadcasts
#   ``blocks.reloaded``, the event the workspace already treats as "the
#   registries changed, re-read the catalogs". The MiniApps tab re-reads its
#   list on that event.
#
# The watch rides on the project observer ``WorkflowWatcher`` already runs and
# restarts on a project switch, so it adds no lifecycle of its own.

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler

from scistudio.engine.events import EngineEvent
from scistudio.panels.files import ASSET_SUFFIXES
from scistudio.panels.registry import PANEL_DESCRIPTOR_FILES, SKIPPED_PANEL_PARTS, panel_sources_fingerprint

logger = logging.getLogger(__name__)

#: The event the workspace re-reads its block, type, previewer, and MiniApp
#: catalogs on. A bare string for the same reason as in
#: ``scistudio.ai.agent.mcp._reload``: ``scistudio.engine.events`` is frozen.
REGISTRIES_CHANGED_EVENT_TYPE = "blocks.reloaded"

#: Quiet period before a burst of panel-directory writes is acted on.
DEBOUNCE_SECONDS = 0.5

_CHANGE_EVENT_TYPES = frozenset({"created", "modified", "deleted", "moved"})
_REFRESH_LOCK = threading.Lock()


def _project_dir(runtime: Any) -> Path | None:
    project = getattr(runtime, "active_project", None)
    return None if project is None else Path(project.path)


def current_preview_service(runtime: Any) -> Any:
    """Return the runtime's preview service, rebuilt first if its panels are stale.

    A service whose recorded panel sources match the directories is returned
    as is. Otherwise it is rebuilt through ``runtime.refresh_preview_service``.
    Runtimes without that method (test doubles) get their service unchanged.
    """
    service = runtime.get_preview_service()
    refresh = getattr(runtime, "refresh_preview_service", None)
    if refresh is None:
        return service
    fingerprint = panel_sources_fingerprint(_project_dir(runtime))
    if getattr(service, "panel_sources", None) == fingerprint:
        return service
    with _REFRESH_LOCK:
        # Another request may have rebuilt it while this one waited.
        service = runtime.get_preview_service()
        if getattr(service, "panel_sources", None) == panel_sources_fingerprint(_project_dir(runtime)):
            return service
        logger.info("panel catalog: panel directories changed; rebuilding the preview service")
        return refresh()


def is_panel_source_change(roots: tuple[Path, ...], path: Path, *, is_directory: bool) -> bool:
    """Whether a filesystem change at *path* can alter the panel catalog."""
    for root in roots:
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if not relative.parts:
            return True
        if any(part in SKIPPED_PANEL_PARTS or part.startswith(".") for part in relative.parts):
            return False
        if is_directory:
            return True
        return relative.name in PANEL_DESCRIPTOR_FILES or relative.suffix.lower() in ASSET_SUFFIXES
    return False


class PanelCatalogRefresher:
    """Debounce panel-directory changes into one catalog refresh and broadcast."""

    def __init__(
        self,
        *,
        runtime: Any,
        event_bus: Any,
        loop: asyncio.AbstractEventLoop | None,
        debounce: float = DEBOUNCE_SECONDS,
    ) -> None:
        self.runtime = runtime
        self.event_bus = event_bus
        self.loop = loop
        self.debounce = debounce
        self._timer: threading.Timer | None = None
        self._lock = threading.RLock()
        self._stopped = False
        self._announced: Any = None

    def changed(self) -> None:
        """Restart the quiet period; the refresh runs once the writes stop."""
        with self._lock:
            if self._stopped:
                return
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(self.debounce, self.flush)
            timer.daemon = True
            self._timer = timer
        timer.start()

    def stop(self) -> None:
        """Cancel a pending refresh and ignore later changes."""
        with self._lock:
            self._stopped = True
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def flush(self) -> bool:
        """Bring the catalog up to date now; ``True`` when a broadcast went out.

        Broadcasts only when the panel sources differ from the last ones this
        refresher announced. A request that already rebuilt the service still
        gets its broadcast, and a burst that changed nothing gets none.
        """
        with self._lock:
            self._timer = None
            if self._stopped:
                return False
        try:
            service = current_preview_service(self.runtime)
        except Exception:
            logger.exception("panel catalog: refresh after a panel directory change failed")
            return False
        fingerprint = getattr(service, "panel_sources", None)
        with self._lock:
            if self._stopped or fingerprint == self._announced:
                return False
            self._announced = fingerprint
        self._broadcast()
        return True

    def _broadcast(self) -> None:
        event = EngineEvent(
            event_type=REGISTRIES_CHANGED_EVENT_TYPE,
            data={"added": [], "removed": [], "reloaded": [], "registry": "panels"},
        )
        loop = self.loop
        if loop is not None and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self.event_bus.emit(event), loop)
                return
            except RuntimeError:
                logger.debug("panel catalog: loop closed while broadcasting")
        with contextlib.suppress(Exception):
            asyncio.run(self.event_bus.emit(event))


class PanelCatalogHandler(FileSystemEventHandler):
    """Forward changes under the panel tiers to a :class:`PanelCatalogRefresher`."""

    def __init__(self, roots: tuple[Path, ...], refresher: PanelCatalogRefresher) -> None:
        super().__init__()
        self._roots = tuple(Path(root).resolve() for root in roots)
        self._refresher = refresher

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def on_any_event(self, event: FileSystemEvent) -> None:
        if getattr(event, "event_type", None) not in _CHANGE_EVENT_TYPES:
            return
        is_directory = bool(getattr(event, "is_directory", False))
        for raw in (getattr(event, "src_path", None), getattr(event, "dest_path", None)):
            if not raw:
                continue
            path = Path(raw if isinstance(raw, str) else raw.decode("utf-8", "replace"))
            if is_panel_source_change(self._roots, path, is_directory=is_directory):
                self._refresher.changed()
                return


__all__ = [
    "DEBOUNCE_SECONDS",
    "REGISTRIES_CHANGED_EVENT_TYPE",
    "PanelCatalogHandler",
    "PanelCatalogRefresher",
    "current_preview_service",
    "is_panel_source_change",
]
