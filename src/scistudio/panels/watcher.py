"""Watch the panel directories: page edits of open panels, and the panel tiers."""
# Maintainer context (kept outside generated API documentation):
# Two watches, both owned by the panel service.
#
# **Page edits (ADR-054 MiniApp FR-022, all context kinds).** While any context
# (preview, interactive or MiniApp) is open on a project- or user-tier panel,
# the panel's own directory is watched and ``panel.files_changed`` is emitted
# with the panel id, so every host showing that panel reloads it in place. One
# watch per panel, shared by all of its open contexts
# (:class:`PanelFileWatches`). Three rules keep it quiet:
#
# * **Only the page counts.** ``panel.py`` and files whose suffix the token asset
#   route serves (:data:`scistudio.panels.files.ASSET_SUFFIXES`). ``panel.json``
#   is the descriptor, not the page: a descriptor change goes through the
#   catalog, which revokes the contexts using the panel. ``__pycache__/`` and
#   the data files the host writes (``answers.json``) never count.
# * **Only the tiers a person edits.** Project and user panels are watched;
#   package and core panels ship inside an installation and are not.
# * **One event per burst.** A 500 ms trailing debounce.
#
# **The catalog (#2465).** :class:`PanelSourceWatcher` watches the project and
# user panel tiers and, 500 ms after a burst of writes that can change the
# catalog, asks the service to rescan. The rescan is incremental: only panels
# whose descriptor changed are revoked. It has its own observer and is re-armed
# on a project switch, so it depends on no other watcher.
# Development references: #2421, #2465, ADR-054.

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
from scistudio.panels.registry import PANEL_DESCRIPTOR_FILES, SKIPPED_PANEL_PARTS, is_ignored_panel_file
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

_PAGE_PYTHON = "panel.py"


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
    if any(part in SKIPPED_PANEL_PARTS for part in relative.parts):
        return False
    # MiniApp FR-051: answers.json is data the host writes on a submit, and a
    # reload would wipe the message the submit left on screen.
    if is_ignored_panel_file(relative.name):
        return False
    if relative.name == _PAGE_PYTHON:
        return True
    if relative.name in PANEL_DESCRIPTOR_FILES:
        return False
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


class PanelFileWatches:
    """One page watch per open panel, shared by every context open on it."""

    def __init__(self, *, event_bus: Any, loop: Any = None, debounce: float = DEBOUNCE_SECONDS) -> None:
        self.event_bus = event_bus
        self.loop = loop
        self.debounce = debounce
        self._lock = threading.Lock()
        self._watches: dict[str, tuple[PanelDirectoryWatcher, int]] = {}

    def acquire(self, panel: Any) -> bool:
        """Count one more open context on *panel*; ``True`` when it is watched."""
        if not watches(panel):
            return False
        with self._lock:
            held = self._watches.get(panel.id)
            if held is not None and held[0].directory == Path(panel.root).resolve():
                self._watches[panel.id] = (held[0], held[1] + 1)
                return True
        watcher = PanelDirectoryWatcher(
            panel_id=panel.id,
            directory=Path(panel.root),
            event_bus=self.event_bus,
            loop=self.loop,
            debounce=self.debounce,
        )
        try:
            started = watcher.start()
        except Exception:
            # A panel that cannot be watched still opens; it just does not reload.
            logger.warning("panel watcher: %s not watched", panel.id, exc_info=True)
            started = False
        if not started:
            return False
        with self._lock:
            previous = self._watches.get(panel.id)
            if previous is None or previous[0].directory != watcher.directory:
                self._watches[panel.id] = (watcher, 1)
                extra = previous[0] if previous is not None else None
            else:
                self._watches[panel.id] = (previous[0], previous[1] + 1)
                extra = watcher
        if extra is not None:
            _stop_in_background(extra)
        return True

    def release(self, panel_id: str) -> None:
        """Count one context fewer on *panel_id*; the last one stops the watch."""
        with self._lock:
            held = self._watches.get(panel_id)
            if held is None:
                return
            if held[1] > 1:
                self._watches[panel_id] = (held[0], held[1] - 1)
                return
            del self._watches[panel_id]
        _stop_in_background(held[0])

    def watched(self) -> dict[str, int]:
        with self._lock:
            return {panel_id: count for panel_id, (_watcher, count) in self._watches.items()}

    def stop_all(self) -> None:
        with self._lock:
            held, self._watches = list(self._watches.values()), {}
        for watcher, _count in held:
            _stop_in_background(watcher)


def _stop_in_background(watcher: Any) -> None:
    thread = threading.Thread(target=watcher.stop, name="panel-watch-stop", daemon=True)
    thread.start()


def is_panel_source_change(roots: tuple[Path, ...], path: Path, *, is_directory: bool) -> bool:
    """Whether a filesystem change at *path* can alter the panel catalog."""
    for root in roots:
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if not relative.parts:
            return True
        if any(part in SKIPPED_PANEL_PARTS or part.startswith(".") for part in relative.parts[:-1]):
            return False
        if is_directory:
            return not relative.name.startswith(".") and relative.name not in SKIPPED_PANEL_PARTS
        if is_ignored_panel_file(relative.name):
            return False
        return relative.name in PANEL_DESCRIPTOR_FILES or relative.suffix.lower() in ASSET_SUFFIXES
    return False


class _SourceHandler(FileSystemEventHandler):
    def __init__(self, owner: PanelSourceWatcher) -> None:
        super().__init__()
        self._owner = owner

    def on_any_event(self, event: FileSystemEvent) -> None:
        if getattr(event, "event_type", None) not in ("created", "modified", "deleted", "moved"):
            return
        is_directory = bool(getattr(event, "is_directory", False))
        for raw in (getattr(event, "src_path", None), getattr(event, "dest_path", None)):
            if not raw:
                continue
            path = Path(raw if isinstance(raw, str) else raw.decode("utf-8", "replace"))
            self._owner.observed(path, is_directory=is_directory)


class PanelSourceWatcher:
    """Watch the project and user panel tiers; debounce changes into ``on_change``."""

    def __init__(self, on_change: Any, *, debounce: float = DEBOUNCE_SECONDS) -> None:
        self._on_change = on_change
        self.debounce = debounce
        self._lock = threading.RLock()
        self._observer: Any = None
        self._timer: threading.Timer | None = None
        self._roots: tuple[Path, ...] = ()
        self._missing: tuple[Path, ...] = ()
        self._stopped = True
        self._generation = 0

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def start(self, roots: tuple[Path, ...]) -> bool:
        """(Re)arm the watch on *roots*; ``False`` when nothing could be observed."""
        self.stop()
        resolved = tuple(dict.fromkeys(_resolve(root) for root in roots))
        observer = Observer()
        handler = _SourceHandler(self)
        scheduled: set[Path] = set()
        missing: list[Path] = []
        for root in resolved:
            target: Path | None = root
            recursive = True
            if not root.is_dir():
                # Watch the nearest existing parent for the tier being created.
                missing.append(root)
                target = next((parent for parent in root.parents if parent.is_dir()), None)
                recursive = False
            if target is None:
                continue
            if target in scheduled:
                continue
            try:
                observer.schedule(handler, str(target), recursive=recursive)
                scheduled.add(target)
            except Exception:
                logger.warning("panel source watcher: cannot watch %s", target, exc_info=True)
        if not scheduled:
            return False
        try:
            observer.start()
        except Exception:
            logger.warning("panel source watcher: observer did not start", exc_info=True)
            return False
        with self._lock:
            self._observer = observer
            self._roots = resolved
            self._missing = tuple(missing)
            self._stopped = False
            self._generation += 1
        return True

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            self._generation += 1
            observer, self._observer = self._observer, None
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()
        if observer is not None:
            with contextlib.suppress(Exception):
                observer.stop()
            with contextlib.suppress(Exception):
                observer.join(timeout=2.0)

    def observed(self, path: Path, *, is_directory: bool) -> None:
        with self._lock:
            if self._stopped:
                return
            roots, missing, generation = self._roots, self._missing, self._generation
        # A non-recursive watch on a parent may report the parent itself rather
        # than the child created in it, so look at the missing tiers directly.
        if any((path == root or path in root.parents) and root.is_dir() for root in missing):
            # A tier directory appeared: watch it recursively from now on. The
            # observer cannot be stopped from its own thread, and re-arming
            # cancels a pending rescan, so the rescan is requested after it.
            threading.Thread(
                target=self._rearm, args=(roots, generation), name="panel-source-rearm", daemon=True
            ).start()
            return
        if is_panel_source_change(roots, path, is_directory=is_directory):
            self.changed()

    def _rearm(self, roots: tuple[Path, ...], generation: int) -> None:
        with self._lock:
            if self._stopped or generation != self._generation:
                return
        if self.start(roots):
            self.changed()

    def changed(self) -> None:
        """Restart the quiet period; ``on_change`` runs once the writes stop."""
        with self._lock:
            if self._stopped:
                return
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(self.debounce, self._flush)
            timer.daemon = True
            self._timer = timer
        timer.start()

    def _flush(self) -> None:
        with self._lock:
            self._timer = None
            if self._stopped:
                return
        try:
            self._on_change()
        except Exception:
            logger.exception("panel source watcher: rescan after a panel directory change failed")


def _resolve(path: Path) -> Path:
    try:
        return Path(path).resolve()
    except OSError:
        return Path(path)


__all__ = [
    "DEBOUNCE_SECONDS",
    "PANEL_FILES_CHANGED",
    "WATCHED_TIERS",
    "PanelDirectoryWatcher",
    "PanelFileWatches",
    "PanelSourceWatcher",
    "counts",
    "is_panel_source_change",
    "watches",
]
