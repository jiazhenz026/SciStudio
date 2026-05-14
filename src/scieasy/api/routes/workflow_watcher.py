"""Filesystem watcher that emits ``workflow.changed`` on canvas-relevant edits.

ADR-034 Phase 2 §3.6 — when claude or codex (or any external editor) writes
a workflow YAML in the active project's ``workflows/`` directory, the canvas
must refetch and refresh. PTY mode no longer carries the in-process
``write_workflow`` MCP-call hook ADR-033 relied on, so we observe the
filesystem directly via :mod:`watchdog` and republish through the existing
``EventBus`` so the standard ``/ws`` outbound loop forwards the event.

Design constraints (kept narrow on purpose):

* **Single observer per app instance.** Started in ``lifespan`` after the
  ApiRuntime is built; stopped in the ``finally`` block. The
  ``WorkflowWatcher`` is a module-level singleton keyed by project path.
* **Self-write suppression.** Canvas-side code paths (``ApiRuntime.save_workflow``
  + the two ``save_yaml`` calls in :mod:`scieasy.api.routes.workflows`) call
  :func:`mark_self_write` *immediately after* writing so the inbound
  ``FileModifiedEvent`` for that exact ``(path, mtime, size)`` triple is
  suppressed.  The dedupe deque caps at 32 entries (FIFO).
* **200 ms per-path debounce.**  Editors that write atomically by renaming
  a tempfile, plus AV/cloud-sync churn on Windows, can produce a burst of
  Modified/Created events. The watcher coalesces them.
* **YAML-only filter.**  ``.yaml`` and ``.yml`` (case-insensitive). Anything
  else in the workflows directory is ignored.
* **Path resolution.**  All inputs and stored paths go through
  ``Path.resolve()`` so symlinked roots (e.g. macOS ``/tmp`` ->
  ``/private/tmp``) compare equal.

Platform notes:

* **Windows** — ``watchdog`` uses ``ReadDirectoryChangesW``. Antivirus and
  cloud-sync clients can cause spurious modify events; the 200 ms debounce
  plus the ``(mtime, size)`` self-write tuple absorb that noise without
  needing the polling fallback.
* **macOS** — ``watchdog`` uses FSEvents. Filenames are normalised to NFD
  by HFS+/APFS; we therefore normalise both stored and emitted paths
  through :func:`unicodedata.normalize` before comparing or sending.
  ``/tmp`` is a symlink to ``/private/tmp``; ``Path.resolve()`` collapses
  this so the self-write dedupe matches.
* **Linux** — ``watchdog`` uses inotify. No NFD normalisation needed;
  filenames are passed through verbatim.

The watcher emits engine events of type ``workflow.changed`` (the existing
:data:`scieasy.engine.events.WORKFLOW_CHANGED` constant from #718). The
``/ws`` handler already forwards that event type to connected clients, so
no new WebSocket protocol is added — the browser observes the same
``workflow.changed`` payload it already handles for canvas saves.
"""

from __future__ import annotations

import asyncio
import logging
import time
import unicodedata
from collections import deque
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import Any

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from scieasy.engine.events import WORKFLOW_CHANGED, EngineEvent, EventBus

logger = logging.getLogger(__name__)

# Debounce window per path (ADR-034 §3.6: "Coalesce rapid writes within 200ms").
_DEBOUNCE_SECONDS = 0.2

# Cap on the (path, mtime, size) deque used for self-write suppression. 32
# entries is enough to absorb several rapid canvas saves while keeping the
# linear scan cheap (the deque is consulted on every relevant fs event).
_SELF_WRITE_DEQUE_CAP = 32


def _normalise(path: Path) -> Path:
    """Return *path* resolved + Unicode-NFC for stable cross-platform compare.

    macOS HFS+/APFS reports NFD-normalised paths in FSEvents callbacks; the
    canvas writer reports whatever form the caller passed in. Both ends are
    normalised through NFC here so the self-write dedupe matches regardless
    of how the filename was encoded.
    """
    resolved = path.resolve()
    return Path(unicodedata.normalize("NFC", str(resolved)))


def _kind_for(event: FileSystemEvent) -> str | None:
    """Map a watchdog event to our wire-level ``kind`` string.

    Returns ``None`` for event types we ignore (e.g. directory events,
    closed-write).
    """
    if event.is_directory:
        return None
    if isinstance(event, FileModifiedEvent):
        return "modified"
    if isinstance(event, FileCreatedEvent):
        return "created"
    if isinstance(event, FileDeletedEvent):
        return "deleted"
    if isinstance(event, FileMovedEvent):
        return "moved"
    return None


def _is_yaml(path: Path | str) -> bool:
    """``True`` iff *path* has a YAML suffix (case-insensitive)."""
    return Path(path).suffix.lower() in {".yaml", ".yml"}


class _WorkflowFileHandler(FileSystemEventHandler):
    """Bridge from watchdog events into the SciEasy ``EventBus``.

    The handler captures three pieces of context at construction:

    * ``project_dir`` — the project root, used to compute the relative path
      that the frontend compares against ``state.currentProject.path``.
    * ``broadcast`` — callable invoked with a flat dict payload. Production
      wires this to ``EventBus.emit(EngineEvent(...))`` via the lifecycle
      adapter; tests inject a mock here.
    * ``loop`` — the asyncio loop the observer thread schedules emits onto.
      ``None`` is allowed for tests that drive ``broadcast`` synchronously.
    """

    def __init__(
        self,
        project_dir: Path,
        broadcast: Callable[[dict[str, Any]], Any],
        loop: asyncio.AbstractEventLoop | None,
    ) -> None:
        super().__init__()
        self._project_dir = _normalise(project_dir)
        self._broadcast = broadcast
        self._loop = loop
        self._last_emit: dict[Path, float] = {}
        self._self_writes: deque[tuple[Path, float, int]] = deque(maxlen=_SELF_WRITE_DEQUE_CAP)
        self._lock = RLock()

    # -- self-write suppression API ----------------------------------------

    def mark_self_write(self, path: Path) -> None:
        """Record that the canvas just wrote *path*.

        The watcher discards the next event whose ``(normalised_path, mtime,
        size)`` matches this triple. Safe to call even if the file does not
        exist yet — we resolve mtime/size lazily.
        """
        try:
            stat = path.stat()
            entry = (_normalise(path), stat.st_mtime, stat.st_size)
        except OSError:
            # File may have been removed between save and the call; skip.
            return
        with self._lock:
            self._self_writes.append(entry)

    def _is_self_write(self, path: Path) -> bool:
        try:
            stat = path.stat()
        except OSError:
            return False
        target = (_normalise(path), stat.st_mtime, stat.st_size)
        with self._lock:
            for entry in self._self_writes:
                if entry == target:
                    return True
        return False

    # -- watchdog callbacks ------------------------------------------------

    def on_any_event(self, event: FileSystemEvent) -> None:
        # We forward via on_any_event so all four kinds (modified/created/
        # deleted/moved) flow through a single debounce + filter pipeline.
        kind = _kind_for(event)
        if kind is None:
            return

        # For FileMovedEvent we want ``dest_path`` (the *new* name) — atomic
        # writes on Windows + POSIX both materialise as ``tmp.XYZ`` →
        # rename → final.yaml, so the only event whose path matches the
        # final filename is the move's destination. For all other kinds
        # ``src_path`` is the canonical key.
        raw_path: bytes | str | None
        if isinstance(event, FileMovedEvent):
            dest = getattr(event, "dest_path", None)
            raw_path = dest if dest else event.src_path
        else:
            raw_path = event.src_path if hasattr(event, "src_path") else None
        if not raw_path:
            return
        if isinstance(raw_path, bytes):
            raw_path = raw_path.decode("utf-8", errors="replace")
        path = Path(raw_path)
        if not _is_yaml(path):
            return
        # Promote a move-into-watched-tree to ``created`` semantically:
        # what the canvas cares about is "a workflow YAML appeared", not
        # the underlying atomic-write mechanics.
        if isinstance(event, FileMovedEvent):
            kind = "created"

        normalised = _normalise(path)

        # Self-write suppression (only meaningful for events on existing
        # files; deletions cannot match a (path, mtime, size) tuple).
        if kind in {"modified", "created"} and self._is_self_write(path):
            logger.debug("workflow_watcher: suppressing self-write event %s %s", kind, path)
            return

        now = time.monotonic()
        with self._lock:
            last = self._last_emit.get(normalised, 0.0)
            if now - last < _DEBOUNCE_SECONDS:
                return
            self._last_emit[normalised] = now

        try:
            relative = normalised.relative_to(self._project_dir)
        except ValueError:
            # Event raised for a path outside the project root — should not
            # happen because we watch project_dir/workflows, but be safe.
            relative = normalised

        payload: dict[str, Any] = {
            "type": "workflow.changed",
            "path": str(relative).replace("\\", "/"),
            "kind": kind,
            "workflow_id": normalised.stem,
            "changed_by": "watcher",
        }
        logger.debug("workflow_watcher: emitting %s for %s", kind, payload["path"])

        if self._loop is None:
            # Synchronous broadcast path used by unit tests.
            try:
                self._broadcast(payload)
            except Exception:
                logger.exception("workflow_watcher: synchronous broadcast failed")
            return

        # Watchdog dispatches callbacks on its own thread; hop back onto the
        # asyncio loop so EventBus.emit's awaitable callbacks (e.g. WS sends)
        # run in the right context.
        try:
            asyncio.run_coroutine_threadsafe(self._dispatch(payload), self._loop)
        except RuntimeError:
            logger.warning("workflow_watcher: asyncio loop closed; dropping event")

    async def _dispatch(self, payload: dict[str, Any]) -> None:
        try:
            result = self._broadcast(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("workflow_watcher: broadcast failed for %s", payload.get("path"))


class WorkflowWatcher:
    """Lifecycle wrapper around a single :class:`watchdog.observers.Observer`.

    One of these lives on ``app.state`` for the duration of the FastAPI
    lifespan. ``start_for_project`` is called whenever the active project
    changes; calling it again is idempotent (it stops the previous observer
    and replaces it).

    The watcher emits engine events on the supplied :class:`EventBus` —
    not directly on the websocket — so per-event fan-out, error isolation,
    and subscriber list semantics are uniform with the rest of the engine.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        # watchdog's Observer is a factory function, not a class — mypy
        # cannot use it as a type annotation. We store it as ``Any``.
        self._observer: Any = None
        self._handler: _WorkflowFileHandler | None = None
        self._watched_dir: Path | None = None
        self._lock = RLock()

    @property
    def watched_dir(self) -> Path | None:
        return self._watched_dir

    @property
    def handler(self) -> _WorkflowFileHandler | None:
        return self._handler

    def start_for_project(self, project_dir: Path, loop: asyncio.AbstractEventLoop) -> None:
        """Begin watching ``<project_dir>/workflows/`` for YAML changes.

        If a previous project was being observed, its observer is stopped
        first. If the workflows directory does not exist yet it is created
        (best-effort) so the watcher attaches before the first save.
        """
        workflows_dir = (project_dir / "workflows").resolve()
        with self._lock:
            if self._observer is not None and self._watched_dir == workflows_dir:
                logger.debug("workflow_watcher: already watching %s", workflows_dir)
                return
            self.stop()

            try:
                workflows_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                logger.warning(
                    "workflow_watcher: cannot create %s; observer not started",
                    workflows_dir,
                    exc_info=True,
                )
                return

            handler = _WorkflowFileHandler(
                project_dir=project_dir,
                broadcast=self._broadcast_to_event_bus,
                loop=loop,
            )
            observer = Observer()
            try:
                observer.schedule(handler, str(workflows_dir), recursive=True)
                observer.start()
            except Exception:
                logger.exception("workflow_watcher: failed to start observer for %s", workflows_dir)
                return
            self._observer = observer
            self._handler = handler
            self._watched_dir = workflows_dir
            logger.info("workflow_watcher: watching %s", workflows_dir)

    def stop(self) -> None:
        """Stop the observer if running; no-op otherwise."""
        with self._lock:
            obs = self._observer
            self._observer = None
            self._handler = None
            self._watched_dir = None
        if obs is None:
            return
        try:
            obs.stop()
            obs.join(timeout=2.0)
        except Exception:
            logger.warning("workflow_watcher: observer stop raised", exc_info=True)

    def mark_self_write(self, path: Path) -> None:
        """Record that the canvas just wrote *path*; suppress the next echo."""
        with self._lock:
            handler = self._handler
        if handler is not None:
            handler.mark_self_write(path)

    async def _broadcast_to_event_bus(self, payload: dict[str, Any]) -> None:
        """Emit a ``workflow.changed`` EngineEvent so /ws forwards it."""
        await self._event_bus.emit(
            EngineEvent(
                event_type=WORKFLOW_CHANGED,
                data={
                    "workflow_id": payload.get("workflow_id"),
                    "path": payload.get("path"),
                    "kind": payload.get("kind"),
                    "changed_by": payload.get("changed_by", "watcher"),
                },
            )
        )


# ----------------------------------------------------------------------------
# Module-level singleton accessors.
#
# The FastAPI lifespan stores the active watcher on ``app.state.workflow_watcher``;
# callers that need to mark a self-write (the canvas save paths in
# ``ApiRuntime.save_workflow`` + ``routes/workflows.py``) reach the singleton
# via :func:`get_active_watcher`. The accessor is import-cycle-safe because it
# is read lazily.
# ----------------------------------------------------------------------------

_active_watcher: WorkflowWatcher | None = None


def set_active_watcher(watcher: WorkflowWatcher | None) -> None:
    """Install the global watcher (lifespan owns this)."""
    global _active_watcher
    _active_watcher = watcher


def get_active_watcher() -> WorkflowWatcher | None:
    """Return the currently active watcher, if any."""
    return _active_watcher


def mark_self_write(path: Path) -> None:
    """Module-level convenience: mark *path* as a canvas-originated write.

    Callers that do not want to depend on the FastAPI app state (e.g. the
    runtime's ``save_workflow`` method) use this function. If no watcher is
    active the call is a silent no-op so unit tests of ``ApiRuntime`` do
    not need to set up the FS observer.
    """
    watcher = _active_watcher
    if watcher is None:
        return
    watcher.mark_self_write(path)
