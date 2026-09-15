"""Watch an open MiniApp's panel directory and announce page changes."""
# Watch an open MiniApp's panel directory and announce page changes.
#
# ADR-054 MiniApp FR-022. While a ``miniapp`` context is open on a project- or
# user-tier MiniApp, the backend watches that MiniApp's own directory and emits
# ``panel.files_changed`` with the panel id, so the host can reload the MiniApp —
# a new frame, context, and process on the same source.
#
# Three rules make the watch quiet enough to be trusted:
#
# * **Only the page counts.** ``panel.json``, ``panel.py``, and files whose suffix
# is one the token asset route serves (:data:`scistudio.panels.files.ASSET_SUFFIXES`).
# ``__pycache__/`` and every other name are ignored, so what ``panel.py`` writes
# into its own directory never reloads the tab that is running it.
# * **Only the tiers a person edits.** Project and user MiniApps are watched;
# package and core MiniApps ship inside an installation and are not.
# * **One event per burst.** An editor that writes atomically produces several
# filesystem events; the 500 ms trailing debounce coalesces them into one.
#
# The watch is owned by the context: it starts when the context opens and stops
# when it closes, so nothing observes a directory no one is looking at.

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from scistudio.engine.events import EngineEvent
from scistudio.panels.files import ASSET_SUFFIXES
from scistudio.previewers.models import OwnerKind

logger = logging.getLogger(__name__)

# Declared here as a bare string rather than in ``scistudio.engine.events``,
# which ADR-035/036 froze; ``src/scistudio/api/ws.py`` carries the same literal
# in its outbound event set.
PANEL_FILES_CHANGED = "panel.files_changed"

# FR-022: the host reloads debounced by 500 milliseconds.
DEBOUNCE_SECONDS = 0.5

# FR-022: only the tiers a person edits in place are watched.
WATCHED_TIERS = (OwnerKind.PROJECT, OwnerKind.USER)

_MANIFEST_AND_PYTHON = ("panel.json", "panel.py")
_IGNORED_PARTS = {"__pycache__"}


def watches(panel: Any) -> bool:
    """Whether an open context on *panel* should watch its directory."""
    return getattr(panel, "owner_kind", None) in WATCHED_TIERS


def counts(directory: Path, path: Path) -> bool:
    """Whether a changed path is part of the MiniApp's page."""
    # Whether a changed path is part of the MiniApp's page (FR-022).
    try:
        relative = path.relative_to(directory)
    except ValueError:
        return False
    if any(part in _IGNORED_PARTS for part in relative.parts):
        return False
    if relative.name in _MANIFEST_AND_PYTHON:
        return True
    return relative.suffix.lower() in ASSET_SUFFIXES


class _PanelDirectoryHandler(FileSystemEventHandler):
    def __init__(self, directory: Path, changed: Any) -> None:
        super().__init__()
        self._directory = directory
        self._changed = changed

    def on_any_event(self, event: FileSystemEvent) -> None:
        if getattr(event, "is_directory", False):
            return
        for raw in (getattr(event, "src_path", None), getattr(event, "dest_path", None)):
            if not raw:
                continue
            candidate = Path(raw if isinstance(raw, str) else raw.decode("utf-8", "replace"))
            if counts(self._directory, candidate):
                self._changed()
                return


class PanelDirectoryWatcher:
    """One watch over one open MiniApp's directory, debounced and quiet."""

    def __init__(
        self,
        *,
        panel_id: str,
        directory: Path,
        event_bus: Any,
        loop: asyncio.AbstractEventLoop | None = None,
        debounce: float = DEBOUNCE_SECONDS,
    ) -> None:
        self.panel_id = panel_id
        self.directory = Path(directory).resolve()
        self.event_bus = event_bus
        self.loop = loop
        self.debounce = debounce
        self._observer: Any = None
        self._timer: threading.Timer | None = None
        self._lock = threading.RLock()
        self._stopped = False

    def start(self) -> bool:
        """Begin watching; ``False`` when the directory cannot be observed."""
        if not self.directory.is_dir():
            return False
        handler = _PanelDirectoryHandler(self.directory, self._changed)
        observer = Observer()
        try:
            observer.schedule(handler, str(self.directory), recursive=True)
            observer.start()
        except Exception:
            logger.warning("panel watcher: cannot watch %s", self.directory, exc_info=True)
            with contextlib.suppress(Exception):
                observer.stop()
            return False
        self._observer = observer
        return True

    def stop(self) -> None:
        """Stop the watch and drop any change that had not been announced yet."""
        with self._lock:
            self._stopped = True
            timer, self._timer = self._timer, None
            observer, self._observer = self._observer, None
        if timer is not None:
            timer.cancel()
        if observer is not None:
            with contextlib.suppress(Exception):
                observer.stop()
            with contextlib.suppress(Exception):
                observer.join(timeout=2.0)

    # -- internals ---------------------------------------------------------

    def _changed(self) -> None:
        """Restart the trailing debounce so a burst of writes emits once."""
        with self._lock:
            if self._stopped:
                return
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(self.debounce, self._emit)
            timer.daemon = True
            self._timer = timer
        timer.start()

    def _emit(self) -> None:
        with self._lock:
            self._timer = None
            if self._stopped:
                return
        event = EngineEvent(event_type=PANEL_FILES_CHANGED, data={"panel_id": self.panel_id})
        loop = self.loop
        if loop is not None and not loop.is_closed():
            try:
                asyncio.run_coroutine_threadsafe(self.event_bus.emit(event), loop)
                return
            except RuntimeError:
                logger.debug("panel watcher: loop closed while emitting for %s", self.panel_id)
        # No API event loop is available (a synchronous host, or a test): the
        # bus is still the only delivery path, so dispatch it on this thread.
        with contextlib.suppress(Exception):
            asyncio.run(self.event_bus.emit(event))


__all__ = [
    "DEBOUNCE_SECONDS",
    "PANEL_FILES_CHANGED",
    "WATCHED_TIERS",
    "PanelDirectoryWatcher",
    "counts",
    "watches",
]
