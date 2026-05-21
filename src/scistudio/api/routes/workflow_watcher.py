"""Filesystem watcher that emits ``workflow.changed`` on canvas-relevant edits
and ``git.head_changed`` on HEAD/ref tip movements (ADR-039 §3.8).

D39-3.2 (#968): this is now the **single source of truth** for
``git.head_changed`` events. The previous parallel
``core.versioning.watcher.GitChangeWatcher`` asyncio-poll implementation
was deleted because (a) it emitted with the wrong payload key
(``head_sha`` vs the frontend's expected ``commit_sha``) and (b) its
lifespan was not re-bound on project switch. The watchdog-based handler
below already provides project-switch hot-reload via
``WorkflowWatcher.start_for_project`` (invoked from
``routes/projects.py::_restart_workflow_watcher``) and emits the
canonical ``commit_sha`` field that ``frontend/src/hooks/useWebSocket.ts``
reads.

ADR-034 Phase 2 §3.6 — when claude or codex (or any external editor) writes
a workflow YAML in the active project's ``workflows/`` directory, the canvas
must refetch and refresh. PTY mode no longer carries the in-process
``write_workflow`` MCP-call hook ADR-033 relied on, so we observe the
filesystem directly via :mod:`watchdog` and republish through the existing
``EventBus`` so the standard ``/ws`` outbound loop forwards the event.

ADR-039 §3.8 — when an external actor (CLI ``git`` command, an editor's
git plugin, an agent running git via the PTY) moves ``HEAD`` or a branch
tip, the canvas and the Git tab (D39-2.3a-and-later) must invalidate their
cached log/branch/status state. We extend the same watcher to observe
``<project>/.git/HEAD`` and ``<project>/.git/refs/heads/*`` and publish a
new ``git.head_changed`` engine event with payload
``{commit_sha, ref, kind}``.

Design constraints (kept narrow on purpose):

* **Single observer per app instance.** Started in ``lifespan`` after the
  ApiRuntime is built; stopped in the ``finally`` block. The
  ``WorkflowWatcher`` is a module-level singleton keyed by project path.
* **Self-write suppression.** Canvas-side code paths (``ApiRuntime.save_workflow``
  + the two ``save_yaml`` calls in :mod:`scistudio.api.routes.workflows`) call
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
:data:`scistudio.engine.events.WORKFLOW_CHANGED` constant from #718). The
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

from scistudio.engine.events import GIT_HEAD_CHANGED, WORKFLOW_CHANGED, EngineEvent, EventBus

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
    """Bridge from watchdog events into the SciStudio ``EventBus``.

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

        # Suppress spurious deletes that fire as part of an atomic
        # replace (``os.replace(tmp, existing.yaml)`` on Windows emits a
        # ``FileDeletedEvent(existing.yaml)`` immediately followed by a
        # ``FileMovedEvent(tmp → existing.yaml)``). If the path still
        # exists at this point, the rename has already completed and the
        # delete event was a transient artifact of the atomic replace —
        # forwarding it to the frontend would blank the canvas the user
        # is currently editing.
        if kind == "deleted" and path.exists():
            logger.debug(
                "workflow_watcher: suppressing transient delete (file still exists): %s",
                path,
            )
            return

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


class _GitHeadHandler(FileSystemEventHandler):
    """Bridge watchdog events on ``<project>/.git/`` to ``GIT_HEAD_CHANGED``.

    ADR-039 §3.8: the canvas and the (D39-2.3a-and-later) Git tab must
    refresh their cached log / branch / status views when an external
    actor (CLI ``git`` command, an editor's git plugin, an agent calling
    git via the PTY) moves ``HEAD`` or a branch tip.

    The handler observes two surfaces inside ``.git``:

    * ``HEAD`` — a tiny file holding either a ``ref: refs/heads/<branch>``
      symbolic reference or a detached-HEAD SHA. Modified on branch
      switch, detach, and reset.
    * ``refs/heads/*`` — one file per branch tip. Modified on commit,
      reset, fast-forward, and merge.

    Other ``.git`` traffic (index churn, packed-refs, reflog) is filtered
    out because it does not change the user-visible HEAD/branch state and
    would otherwise generate a flood of events on every git operation.

    Event payload:
        ``{"commit_sha": <new SHA or None>, "ref": "HEAD" | "refs/heads/<branch>", "kind": "head" | "refs"}``

    The handler reuses the same 200ms-debounce window as the workflow
    handler — bursts of git internal writes collapse to one event.
    """

    def __init__(
        self,
        git_dir: Path,
        broadcast: Callable[[dict[str, Any]], Any],
        loop: asyncio.AbstractEventLoop | None,
    ) -> None:
        super().__init__()
        self._git_dir = _normalise(git_dir)
        self._broadcast = broadcast
        self._loop = loop
        self._last_emit: dict[Path, float] = {}
        self._lock = RLock()

    # -- helpers -----------------------------------------------------------

    def _read_head_sha(self, path: Path) -> str | None:
        """Return the commit SHA at *path*.

        For ``HEAD``: if it contains a ``ref: refs/heads/<branch>`` line,
        resolve the SHA from that ref file; else treat the contents as a
        raw SHA (detached HEAD).

        For ``refs/heads/<branch>``: contents *are* the SHA.

        Returns ``None`` if the file cannot be read or parsed — emission
        proceeds without ``commit_sha`` so the frontend still invalidates
        its cache even if we cannot pinpoint the new SHA.
        """
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not text:
            return None
        if text.startswith("ref:"):
            # Symbolic ref → resolve the pointed-at file under the same .git.
            target = text.split(":", 1)[1].strip()
            try:
                resolved = (self._git_dir / target).read_text(encoding="utf-8").strip()
                return resolved or None
            except OSError:
                return None
        # Sanity: a SHA is 40 hex chars (or 64 for sha256-objects repos).
        # We accept anything non-empty here; the frontend treats commit_sha
        # as opaque.
        return text

    def _classify(self, path: Path) -> tuple[str, str] | None:
        """Return ``(ref, kind)`` for *path* inside ``.git``, else ``None``.

        Only the HEAD file and ref files under ``refs/heads/`` are
        treated as user-visible. ``packed-refs``, ``index``, ``logs/``,
        ``ORIG_HEAD``, ``FETCH_HEAD``, ``MERGE_HEAD``, etc. are
        deliberately ignored to keep the event surface narrow.
        """
        try:
            rel = path.relative_to(self._git_dir)
        except ValueError:
            return None
        parts = rel.parts
        # Codex P2-A: filter out ref lockfiles (e.g. ``refs/heads/main.lock``).
        # Git creates these transiently during every ref update; emitting
        # them produces duplicate events and bogus ``ref`` values that
        # downstream consumers may interpret as real branch names.
        if parts and parts[-1].endswith(".lock"):
            return None
        if len(parts) == 1 and parts[0] == "HEAD":
            return ("HEAD", "head")
        if len(parts) >= 3 and parts[0] == "refs" and parts[1] == "heads":
            ref_name = "/".join(parts)  # e.g. "refs/heads/feature/x"
            return (ref_name, "refs")
        return None

    # -- watchdog callback -------------------------------------------------

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        # We forward modified + created + moved (delete of HEAD is a torn
        # repo, ignore). watchdog's event_type strings differ across
        # platforms; keying off isinstance keeps it stable.
        if not isinstance(event, FileModifiedEvent | FileCreatedEvent | FileMovedEvent):
            return
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
        normalised = _normalise(path)

        classified = self._classify(normalised)
        if classified is None:
            return
        ref, kind = classified

        now = time.monotonic()
        with self._lock:
            last = self._last_emit.get(normalised, 0.0)
            if now - last < _DEBOUNCE_SECONDS:
                return
            self._last_emit[normalised] = now

        commit_sha = self._read_head_sha(normalised)
        payload: dict[str, Any] = {
            "commit_sha": commit_sha,
            "ref": ref,
            "kind": kind,
        }
        logger.debug("git_head_watcher: emitting %s for ref=%s sha=%s", kind, ref, commit_sha)

        if self._loop is None:
            try:
                self._broadcast(payload)
            except Exception:
                logger.exception("git_head_watcher: synchronous broadcast failed")
            return

        try:
            asyncio.run_coroutine_threadsafe(self._dispatch(payload), self._loop)
        except RuntimeError:
            logger.warning("git_head_watcher: asyncio loop closed; dropping event")

    async def _dispatch(self, payload: dict[str, Any]) -> None:
        try:
            result = self._broadcast(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            logger.exception("git_head_watcher: broadcast failed for ref=%s", payload.get("ref"))


class WorkflowWatcher:
    """Lifecycle wrapper around the project's watchdog observers.

    One of these lives on ``app.state`` for the duration of the FastAPI
    lifespan. ``start_for_project`` is called whenever the active project
    changes; calling it again is idempotent (it stops the previous
    observers and replaces them).

    The watcher manages **two** schedules per project:

    1. ``<project>/workflows/`` for canvas-relevant YAML edits (ADR-034).
    2. ``<project>/.git/`` for HEAD + ``refs/heads/*`` movements
       (ADR-039 §3.8). Silently skipped when the project is not a git
       repo yet (no ``.git`` directory) — D39-2.2a/b's auto-init will
       create it later.

    Both surfaces emit engine events on the supplied :class:`EventBus` —
    not directly on the websocket — so per-event fan-out, error
    isolation, and subscriber list semantics are uniform with the rest
    of the engine.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        # watchdog's Observer is a factory function, not a class — mypy
        # cannot use it as a type annotation. We store it as ``Any``.
        self._observer: Any = None
        self._handler: _WorkflowFileHandler | None = None
        self._git_handler: _GitHeadHandler | None = None
        self._watched_dir: Path | None = None
        self._watched_git_dir: Path | None = None
        self._lock = RLock()

    @property
    def watched_dir(self) -> Path | None:
        return self._watched_dir

    @property
    def watched_git_dir(self) -> Path | None:
        return self._watched_git_dir

    @property
    def handler(self) -> _WorkflowFileHandler | None:
        return self._handler

    @property
    def git_handler(self) -> _GitHeadHandler | None:
        return self._git_handler

    def start_for_project(self, project_dir: Path, loop: asyncio.AbstractEventLoop) -> None:
        """Begin watching ``<project_dir>/workflows/`` for YAML changes and
        ``<project_dir>/.git/`` for HEAD/ref movements (ADR-039 §3.8).

        If a previous project was being observed, its observers are stopped
        first. If the workflows directory does not exist yet it is created
        (best-effort) so the watcher attaches before the first save. The
        ``.git/`` schedule is skipped silently when the project is not yet
        a git repo — D39-2.2b auto-init populates it on first save and
        ``start_for_project`` will catch up on the next project re-open.
        """
        workflows_dir = (project_dir / "workflows").resolve()
        git_dir = (project_dir / ".git").resolve()
        # Codex P2-B: scheduling below uses ``git_dir.is_dir()`` (worktrees
        # carry ``.git`` as a gitlink *file*, not a directory). The
        # idempotency guard must mirror that or it never matches when
        # ``.git`` exists-but-isn't-a-dir, causing repeated teardown +
        # rebuild and the git watcher never attaches.
        expected_git_dir = git_dir if git_dir.is_dir() else None
        with self._lock:
            if (
                self._observer is not None
                and self._watched_dir == workflows_dir
                and self._watched_git_dir == expected_git_dir
            ):
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
                # ADR-039 §3.8: also watch the project's .git directory if
                # one exists. The handler filters down to HEAD + refs/heads/
                # internally so the schedule itself can stay recursive (we
                # want to pick up new branches without restarting the
                # observer).
                git_handler: _GitHeadHandler | None = None
                watched_git: Path | None = None
                if git_dir.is_dir():
                    git_handler = _GitHeadHandler(
                        git_dir=git_dir,
                        broadcast=self._broadcast_git_to_event_bus,
                        loop=loop,
                    )
                    try:
                        observer.schedule(git_handler, str(git_dir), recursive=True)
                        watched_git = git_dir
                    except Exception:
                        # Failure to schedule the git surface must not
                        # prevent the workflows surface from starting.
                        logger.warning(
                            "workflow_watcher: failed to schedule git watch for %s",
                            git_dir,
                            exc_info=True,
                        )
                        git_handler = None
                observer.start()
            except Exception:
                logger.exception("workflow_watcher: failed to start observer for %s", workflows_dir)
                return
            self._observer = observer
            self._handler = handler
            self._git_handler = git_handler
            self._watched_dir = workflows_dir
            self._watched_git_dir = watched_git
            logger.info(
                "workflow_watcher: watching %s%s",
                workflows_dir,
                f" + git {watched_git}" if watched_git else "",
            )

    def stop(self) -> None:
        """Stop the observer if running; no-op otherwise."""
        with self._lock:
            obs = self._observer
            self._observer = None
            self._handler = None
            self._git_handler = None
            self._watched_dir = None
            self._watched_git_dir = None
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

    async def _broadcast_git_to_event_bus(self, payload: dict[str, Any]) -> None:
        """Emit a ``git.head_changed`` EngineEvent so /ws forwards it.

        ADR-039 §3.8: the canvas + Git tab subscribes to this event to
        invalidate cached log/branch/status state when an external actor
        moves HEAD or a branch tip.
        """
        await self._event_bus.emit(
            EngineEvent(
                event_type=GIT_HEAD_CHANGED,
                data={
                    "commit_sha": payload.get("commit_sha"),
                    "ref": payload.get("ref"),
                    "kind": payload.get("kind"),
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
