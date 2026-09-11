"""How a workflow run ends when no browser is watching it (#2327).

ADR-055 §7: closing the connection window or the browser does not stop an
active analysis. A run ends when it completes or when someone cancels it
explicitly; the ``/ws`` handler no longer cancels runs after the last browser
disconnects.

That leaves the guarantee #1500 was after: a lineage ``runs`` row must not
stay ``running`` once the run it describes can no longer finish. Three events
end a run without the scheduler's own completion, and each is handled:

* **Graceful shutdown.** :func:`shutdown_workflow_runs` cancels every live run
  and waits a bounded time while each task's done-callback writes the terminal
  status. A run still pending after the bound is finalised as ``cancelled``
  here.
* **The backend is killed or crashes.** No code runs at that moment, so the
  repair happens on the next open. Every run first writes an *owner marker*,
  ``<project>/.scistudio/run-owners/<run_id>.json`` (pid, process creation
  time, host), and only then inserts its ``runs`` row; the marker is removed
  once the row is final. When a project's lineage store opens,
  :func:`reconcile_interrupted_runs` finalises as ``failed`` each ``running``
  row whose owner is provably gone. A row whose owner is still alive (another
  backend with the same project open, possibly on another host) is left
  alone, because artifact retention (#1983) must keep treating it as in
  flight.
* **A worker process dies.** The engine already handles it: the runner raises
  on a non-zero exit, the block goes ``ERROR``, and the run finalises as
  ``failed`` through the normal done-callback.

The lineage schema has no column for a termination reason (adding one is a
``scistudio.core`` change), so the reason goes to the backend log and to the
run's own diagnostic log (``run-<run_id>.log``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._helpers import _now_iso

if TYPE_CHECKING:
    from . import ApiRuntime

logger = logging.getLogger(__name__)

# Terminal status written for a run whose owning process exited mid-run. The
# lineage status set is fixed (running | completed | failed | cancelled); an
# interrupted run did not complete and nobody asked it to stop, so "failed".
INTERRUPTED_RUN_STATUS = "failed"
# Terminal status written when backend shutdown ends a run.
SHUTDOWN_RUN_STATUS = "cancelled"

# How long graceful shutdown waits for cancelled runs to finalise their lineage
# before finalising the stragglers itself. Read at call time so tests can
# shorten it.
_SHUTDOWN_RUN_TIMEOUT_SEC = 10.0

# Same tolerance as the engine's #1542 PID-identity check: a reused PID belongs
# to a process whose creation time is far from the recorded one.
_PROCESS_IDENTITY_TOLERANCE_SEC = 2.0

_OWNER_DIR_PARTS = (".scistudio", "run-owners")
_MARKER_SCHEMA = 1
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


@dataclass
class _LiveRun:
    """A run this process started and has not finalised yet."""

    run_id: str
    recorder: Any
    marker_path: Path | None
    task: asyncio.Task[None] | None = None


# Process-wide, because an owner marker names a process, not a runtime: two
# ``ApiRuntime`` instances in one process (tests) must not reconcile each
# other's live runs.
_LIVE_RUNS: dict[str, _LiveRun] = {}
# Orders a run's finalise-then-release against reconciliation's
# check-then-finalise. Finalisation happens before ``release_run`` on the
# event-loop thread; reconciliation runs on whichever thread opens the
# project. Under the lock, reconciliation sees a run either as still live or
# as already terminal, never as released-but-still-``running``.
_LOCK = threading.Lock()


def owner_marker_path(project_dir: str | Path, run_id: str) -> Path | None:
    """Return the owner-marker path for *run_id*, or ``None`` for an unsafe id."""
    if not _SAFE_RUN_ID.match(run_id):
        return None
    return Path(project_dir).joinpath(*_OWNER_DIR_PARTS, f"{run_id}.json")


def live_run_ids() -> frozenset[str]:
    """Run ids this process has started and not yet finalised."""
    with _LOCK:
        return frozenset(_LIVE_RUNS)


def _this_process() -> dict[str, Any]:
    create_time: float | None
    try:
        import psutil

        create_time = float(psutil.Process(os.getpid()).create_time())
    except Exception:
        create_time = None
    return {"pid": os.getpid(), "process_create_time": create_time, "host": socket.gethostname()}


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("#2327: could not remove run owner marker %s", path, exc_info=True)


def claim_run(recorder: Any, *, workflow_id: str, project_dir: str | Path | None) -> None:
    """Mark *recorder*'s run as owned by this process.

    Call this before the ``runs`` row is inserted. A reader that can see the
    row then always finds the marker too, so a run that has just started is
    never mistaken for an interrupted one. A marker that cannot be written is
    logged and skipped: the run still works, but another process could
    reconcile it while this one is running it.
    """
    run_id = str(recorder.run_id)
    marker_path = owner_marker_path(project_dir, run_id) if project_dir is not None else None
    if marker_path is not None:
        payload = {
            "schema": _MARKER_SCHEMA,
            "run_id": run_id,
            "workflow_id": workflow_id,
            "claimed_at": _now_iso(),
            **_this_process(),
        }
        try:
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            staging = marker_path.with_suffix(".json.tmp")
            staging.write_text(json.dumps(payload), encoding="utf-8")
            os.replace(staging, marker_path)
        except OSError:
            logger.warning("#2327: could not write the owner marker for run %s", run_id, exc_info=True)
            marker_path = None
    with _LOCK:
        _LIVE_RUNS[run_id] = _LiveRun(run_id=run_id, recorder=recorder, marker_path=marker_path)


def attach_task(run_id: str, task: asyncio.Task[None]) -> None:
    """Record the asyncio task executing a claimed run (used by shutdown)."""
    with _LOCK:
        entry = _LIVE_RUNS.get(run_id)
        if entry is not None:
            entry.task = task


def release_run(run_id: str) -> None:
    """Forget a finished run and remove its owner marker.

    Call only after the run's terminal status has been written, or at least
    attempted. Reconciliation treats a ``running`` row that is neither live
    here nor owned by a live process as interrupted.
    """
    with _LOCK:
        entry = _LIVE_RUNS.pop(run_id, None)
    if entry is not None and entry.marker_path is not None:
        _unlink_quietly(entry.marker_path)


def abandon_run(recorder: Any, *, status: str = INTERRUPTED_RUN_STATUS) -> None:
    """Finalise and release a run whose task never started.

    ``start_workflow`` inserts the ``runs`` row before it builds the scheduler
    and task. If either step raises, the row would otherwise stay ``running``.
    """
    if recorder is None:
        return
    try:
        recorder.finalize_run(status=status)
    except Exception:
        logger.warning("#2327: could not finalise abandoned run %s", getattr(recorder, "run_id", "?"), exc_info=True)
    with contextlib.suppress(Exception):
        recorder.dispose()
    release_run(str(recorder.run_id))


def _live_run_for_task(task: asyncio.Task[None]) -> _LiveRun | None:
    with _LOCK:
        for entry in _LIVE_RUNS.values():
            if entry.task is task:
                return entry
    return None


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------


async def shutdown_workflow_runs(self: ApiRuntime, *, timeout_sec: float | None = None) -> list[str]:
    """Cancel every live run and wait, bounded, until its lineage is terminal.

    Cancelling a run's task makes its done-callback finalise the lineage row as
    ``cancelled``. A task that has not finished when *timeout_sec* elapses (a
    block that ignores cancellation, say) is finalised as ``cancelled`` here so
    that its row does not outlive the process as ``running``.

    Returns:
        The run ids this function finalised itself because their task did not
        finish within the bound.
    """
    bound = _SHUTDOWN_RUN_TIMEOUT_SEC if timeout_sec is None else timeout_sec
    pending = [run.task for run in list(self.workflow_runs.values()) if not run.task.done()]
    if not pending:
        return []
    for task in pending:
        task.cancel()
    _finished, still_pending = await asyncio.wait(pending, timeout=bound)
    # A finished task's done-callbacks, lineage finalisation included, are
    # scheduled ahead of asyncio.wait's own wake-up. Yield once so that every
    # one of them has run before the caller tears the runtime down.
    await asyncio.sleep(0)

    forced: list[str] = []
    for task in still_pending:
        entry = _live_run_for_task(task)
        if entry is None:
            continue
        try:
            entry.recorder.finalize_run(status=SHUTDOWN_RUN_STATUS)
        except Exception:
            logger.warning("#2327: could not finalise run %s at shutdown", entry.run_id, exc_info=True)
        release_run(entry.run_id)
        logger.warning(
            "#2327: run %s did not stop within %.1fs of backend shutdown; its lineage is recorded as %r.",
            entry.run_id,
            bound,
            SHUTDOWN_RUN_STATUS,
        )
        forced.append(entry.run_id)
    return forced


# ---------------------------------------------------------------------------
# Startup reconciliation
# ---------------------------------------------------------------------------


def _read_marker(path: Path | None) -> dict[str, Any] | None:
    """Return the marker's content, ``None`` when absent, ``{}`` when unreadable."""
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _owner_may_be_alive(marker: dict[str, Any]) -> bool:
    """Whether the process named by *marker* might still be running the run.

    ``False`` only when that is provable: the marker is unreadable, the PID is
    gone, the PID now belongs to a different process, or the marker names this
    very process (whose live runs the caller has already excluded). A process
    on another host, or one this process may not inspect, counts as alive.
    """
    pid = marker.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool):
        return False
    host = marker.get("host")
    if isinstance(host, str) and host and host != socket.gethostname():
        return True
    if pid == os.getpid():
        return False
    try:
        import psutil

        actual = psutil.Process(pid).create_time()
    except Exception as exc:
        try:
            import psutil

            gone = isinstance(exc, psutil.NoSuchProcess)
        except ImportError:
            gone = False
        return not gone
    recorded = marker.get("process_create_time")
    if not isinstance(recorded, int | float):
        return True
    return bool(abs(float(actual) - float(recorded)) <= _PROCESS_IDENTITY_TOLERANCE_SEC)


def _owner_description(marker: dict[str, Any] | None) -> str:
    if marker is None:
        return "no process has claimed it (it has no owner marker)"
    pid = marker.get("pid")
    host = marker.get("host") or "this machine"
    if pid == os.getpid():
        return f"this backend (pid {pid}) is no longer running it"
    if isinstance(pid, int):
        return f"the SciStudio process that ran it (pid {pid} on {host}) has exited, most likely a crash or forced kill"
    return "its owner marker is unreadable"


def _report_interrupted(
    run_id: str,
    row: dict[str, Any],
    marker: dict[str, Any] | None,
    project_dir: Path,
) -> None:
    message = (
        "#2327: run %s of workflow %r (started %s) was still marked 'running' but %s, so it can no "
        "longer finish. Its lineage is now recorded as %r. finished_at records when this was "
        "detected, not when the run stopped."
    )
    args = (
        run_id,
        row.get("workflow_id"),
        row.get("started_at"),
        _owner_description(marker),
        INTERRUPTED_RUN_STATUS,
    )
    try:
        from scistudio.engine.run_logging import run_log_context

        # Also append the reason to the run's own diagnostic log.
        with run_log_context(run_id, project_root=project_dir):
            logger.warning(message, *args)
    except Exception:
        logger.warning(message, *args)


def _sweep_stale_markers(store: Any, project_dir: Path) -> None:
    """Remove markers left by runs whose row is already terminal or never appeared."""
    owner_dir = project_dir.joinpath(*_OWNER_DIR_PARTS)
    try:
        paths = sorted(owner_dir.glob("*.json"))
    except OSError:
        return
    for path in paths:
        run_id = path.stem
        with _LOCK:
            if run_id in _LIVE_RUNS:
                continue
            try:
                row = store.get_run(run_id)
            except Exception:
                continue
            if row is not None and row.get("status") == "running":
                continue
            if row is None and _owner_may_be_alive(_read_marker(path) or {}):
                # Claimed by a live process that has not inserted its row yet.
                continue
        _unlink_quietly(path)


def reconcile_interrupted_runs(store: Any, project_dir: str | Path) -> list[str]:
    """Finalise the ``running`` rows that no live process will ever finish.

    Called whenever a project's lineage store is opened, the first moment this
    process can see rows a previous process left behind. Never raises: a
    failure is logged and leaves the rows untouched.

    Returns:
        The run ids that were finalised as :data:`INTERRUPTED_RUN_STATUS`.
    """
    root = Path(project_dir)
    try:
        candidates = list(store.runs_in_progress())
    except Exception:
        logger.warning("#2327: could not list in-progress runs for reconciliation", exc_info=True)
        return []

    reconciled: list[str] = []
    for run_id in candidates:
        marker_path = owner_marker_path(root, run_id)
        with _LOCK:
            if run_id in _LIVE_RUNS:
                continue
            marker = _read_marker(marker_path)
            if marker is not None and _owner_may_be_alive(marker):
                continue
            try:
                row = store.get_run(run_id)
                if row is None or row.get("status") != "running":
                    continue
                store.finalize_run(run_id, finished_at=_now_iso(), status=INTERRUPTED_RUN_STATUS)
            except Exception:
                logger.warning("#2327: could not reconcile interrupted run %s", run_id, exc_info=True)
                continue
        if marker_path is not None:
            _unlink_quietly(marker_path)
        _report_interrupted(run_id, row, marker, root)
        reconciled.append(run_id)

    try:
        _sweep_stale_markers(store, root)
    except Exception:
        logger.debug("#2327: owner-marker sweep failed", exc_info=True)
    return reconciled


__all__ = [
    "INTERRUPTED_RUN_STATUS",
    "SHUTDOWN_RUN_STATUS",
    "abandon_run",
    "attach_task",
    "claim_run",
    "live_run_ids",
    "owner_marker_path",
    "reconcile_interrupted_runs",
    "release_run",
    "shutdown_workflow_runs",
]
