"""How a workflow run ends when no browser is watching it.

Closing the connection window or the browser does not stop an active
analysis. A run ends when it completes or when someone cancels it explicitly.
The ``/ws`` handler does not cancel runs when browsers disconnect, and neither
reopening a project nor switching to another one ends a run.

A lineage ``runs`` row must still not stay ``running`` once the run it
describes can no longer finish, and a run that did finish must be recorded as
what it was. This module keeps that guarantee.

* **The store a run writes through stays usable.** Reopening the active
  project keeps its ``LineageStore``. Switching to another project retires the
  previous store, which is closed only once the last live run writing through
  it has been released (:func:`retire_store`).
* **A run's terminal write is checked.** :func:`release_run` removes a run's
  owner marker only once its row is terminal. If the row is still ``running``,
  the status is written again through a store opened by path. If that fails
  too, the marker is kept and annotated with the outcome, and the next open
  records it.
* **Graceful shutdown.** :func:`shutdown_workflow_runs` cancels every live run
  and waits 10 s in total while each task's done-callback writes the terminal
  status. A run still pending after that is finalised as ``cancelled`` here,
  and its own done-callback does not overwrite that afterwards.
* **The backend is killed or crashes.** Every run first registers itself as
  live in this process, then writes an owner marker,
  ``<project>/.scistudio/run-owners/<run_id>.json`` (pid, process creation
  time, machine id, host), and only then inserts its ``runs`` row. When a
  project's lineage store opens, :func:`reconcile_interrupted_runs` finalises
  each ``running`` row whose owner is provably gone, as ``failed`` or as the
  outcome an annotated marker records. A row whose owner may be alive
  (another backend with the project open, possibly on another machine), or
  whose marker cannot be read, is left alone, because artifact retention must
  keep treating it as in flight. Reconciliation logs a warning for each row it
  cannot decide.
* **A worker process dies.** The engine already handles it: the runner raises
  on a non-zero exit, the block goes ``ERROR``, and the run finalises as
  ``failed`` through the normal done-callback.

The lineage schema has no column for a termination reason (adding one is a
``scistudio.core`` change), so reasons go to the backend log and to the run's
own diagnostic log (``run-<run_id>.log``).
"""

# Development references: #2327 (run lifetime), #1500 (stuck ``running`` rows),
# #1983 (artifact retention), ADR-055 section 7, and section 4.6 of the ADR-055
# Spec 3 local background runtime spec, which documents this contract.

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

# How long graceful shutdown waits, in total, for cancelled runs to finalise
# their lineage before finalising the stragglers itself. Read at call time so
# tests can shorten it.
_SHUTDOWN_RUN_TIMEOUT_SEC = 10.0

# Same tolerance as the engine's #1542 PID-identity check: a reused PID belongs
# to a process whose creation time is far from the recorded one.
_PROCESS_IDENTITY_TOLERANCE_SEC = 2.0

# A run owned by another machine is never finalised from here, since that
# machine may really be running it. Past this age it is reported, because it
# keeps artifact retention blocked for the project.
FOREIGN_OWNER_STALE_AFTER = timedelta(hours=24)

# A staging file this old belongs to a claim that died between writing and
# renaming it.
_STAGING_STALE_AFTER_SEC = 60.0

_OWNER_DIR_PARTS = (".scistudio", "run-owners")
_MARKER_SCHEMA = 2
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,200}$")

# _read_marker states.
_ABSENT = "absent"
_OK = "ok"
_INVALID = "invalid"
_UNREADABLE = "unreadable"

# _owner_verdict results.
_DEAD = "dead"
_ALIVE = "alive"
_FOREIGN = "foreign"


@dataclass
class _LiveRun:
    """A run this process started and has not released yet."""

    run_id: str
    recorder: Any
    store: Any
    project_dir: Path | None
    marker_path: Path | None
    task: asyncio.Task[None] | None = None


# Process-wide, because an owner marker names a process, not a runtime: two
# ``ApiRuntime`` instances in one process (tests) must not reconcile each
# other's live runs.
_LIVE_RUNS: dict[str, _LiveRun] = {}
# Stores replaced by a project switch while live runs still write through them.
_RETIRED_STORES: list[Any] = []
# Runs whose lineage shutdown finalised while their task was still going.
_FORCED_RUN_IDS: set[str] = set()
# Orders a run's claim, finalise-then-release and the store bookkeeping against
# reconciliation's check-then-finalise and the marker sweep. Under the lock,
# reconciliation sees a run either as live or as already terminal, never as
# released but still ``running``, and the sweep never sees a claimed run's
# marker before the run is registered as live.
_LOCK = threading.RLock()


def lineage_db_path(project_dir: str | Path) -> Path:
    """The lineage database of the project at *project_dir*."""
    return Path(project_dir) / ".scistudio" / "lineage.db"


def is_same_path(first: str | Path, second: str | Path) -> bool:
    """Whether two paths name the same file, whatever their spelling."""
    try:
        return Path(first).resolve() == Path(second).resolve()
    except OSError:
        return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def owner_marker_path(project_dir: str | Path, run_id: str) -> Path | None:
    """Return the owner-marker path for *run_id*, or ``None`` for an unsafe id."""
    if not _SAFE_RUN_ID.match(run_id):
        return None
    return Path(project_dir).joinpath(*_OWNER_DIR_PARTS, f"{run_id}.json")


def live_run_ids() -> frozenset[str]:
    """Run ids this process has started and not yet released."""
    with _LOCK:
        return frozenset(_LIVE_RUNS)


# ---------------------------------------------------------------------------
# Process and machine identity
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def machine_id() -> str:
    """A stable identifier for this machine, naming whose PIDs a marker holds.

    A hostname is not stable: macOS renames the host with the network, and a
    re-created container or a renamed machine gets a new one. The operating
    system's machine identifier is used instead: ``/etc/machine-id`` (or the
    D-Bus copy) on Linux, the ``MachineGuid`` registry value on Windows, and
    ``IOPlatformUUID`` on macOS. The hostname is the fallback, prefixed so it
    can never equal a real identifier.
    """
    return _read_machine_id() or f"hostname:{socket.gethostname()}"


def _read_machine_id() -> str | None:
    try:
        if sys.platform == "win32":
            import winreg

            access = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, access) as key:
                value, _kind = winreg.QueryValueEx(key, "MachineGuid")
            return str(value).strip() or None
        if sys.platform == "darwin":
            ioreg = shutil.which("ioreg")
            if ioreg is None:
                return None
            listing = subprocess.run(
                [ioreg, "-rd1", "-c", "IOPlatformExpertDevice"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout
            found = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', listing)
            return found.group(1) if found else None
        for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            with contextlib.suppress(OSError):
                text = Path(candidate).read_text(encoding="ascii").strip()
                if text:
                    return text
    except Exception:
        logger.debug("#2327: could not read the machine identifier", exc_info=True)
    return None


def _this_process() -> dict[str, Any]:
    create_time: float | None
    try:
        import psutil

        create_time = float(psutil.Process(os.getpid()).create_time())
    except Exception:
        create_time = None
    return {
        "pid": os.getpid(),
        "process_create_time": create_time,
        "machine_id": machine_id(),
        "host": socket.gethostname(),
    }


# ---------------------------------------------------------------------------
# Owner markers
# ---------------------------------------------------------------------------


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("#2327: could not remove run owner marker %s", path, exc_info=True)


def _write_marker(path: Path, payload: dict[str, Any], *, create_parent: bool = True) -> None:
    """Write *payload* to *path* atomically; raises ``OSError`` on failure.

    With ``create_parent=False`` a missing directory is an error rather than
    something to create, so a deleted project is never recreated.
    """
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_suffix(".json.tmp")
    try:
        staging.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(staging, path)
    except OSError:
        _unlink_quietly(staging)
        raise


def _read_marker(path: Path | None) -> tuple[str, dict[str, Any]]:
    """Read an owner marker as ``(state, content)``.

    ``absent``: there is no marker. ``ok``: the content follows. ``invalid``:
    the file holds no marker; writes are atomic, so this is not a half-written
    one. ``unreadable``: the read itself failed (a Windows sharing violation, a
    scanner holding the file, a network filesystem error). An unreadable marker
    says nothing about its owner.
    """
    if path is None:
        return _ABSENT, {}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _ABSENT, {}
    except OSError:
        return _UNREADABLE, {}
    try:
        data = json.loads(text)
    except ValueError:
        return _INVALID, {}
    return (_OK, data) if isinstance(data, dict) else (_INVALID, {})


# ---------------------------------------------------------------------------
# Claim and release
# ---------------------------------------------------------------------------


def claim_run(recorder: Any, *, workflow_id: str, project_dir: str | Path | None, store: Any) -> None:
    """Register *recorder*'s run as live here, then write its owner marker.

    Call this before the ``runs`` row is inserted, so that a reader who can see
    the row always finds the marker too. The run is registered before the
    marker is written, so a sweep can never take the marker for an orphan.

    Raises:
        OSError: The marker could not be written. The run is unregistered
            again, and the caller must not insert its row: without a marker,
            another backend would take the live run for an interrupted one.
    """
    run_id = str(recorder.run_id)
    root = Path(project_dir) if project_dir is not None else None
    marker_path = owner_marker_path(root, run_id) if root is not None else None
    with _LOCK:
        _LIVE_RUNS[run_id] = _LiveRun(
            run_id=run_id,
            recorder=recorder,
            store=store,
            project_dir=root,
            marker_path=marker_path,
        )
    if marker_path is None:
        return
    payload = {
        "schema": _MARKER_SCHEMA,
        "run_id": run_id,
        "workflow_id": workflow_id,
        "claimed_at": _now_iso(),
        **_this_process(),
    }
    try:
        _write_marker(marker_path, payload)
    except OSError:
        with _LOCK:
            _LIVE_RUNS.pop(run_id, None)
        raise


def attach_task(run_id: str, task: asyncio.Task[None]) -> None:
    """Record the asyncio task executing a claimed run (used by shutdown)."""
    with _LOCK:
        entry = _LIVE_RUNS.get(run_id)
        if entry is not None:
            entry.task = task


def _row_status(store: Any, run_id: str) -> str:
    """``terminal``, ``running``, ``absent`` or ``unknown`` (store unusable)."""
    if store is None:
        return "absent"
    try:
        row = store.get_run(run_id)
    except Exception:
        return "unknown"
    if row is None:
        return "absent"
    return "running" if row.get("status") == "running" else "terminal"


def _open_store_by_path(project_dir: Path) -> Any:
    from scistudio.core.lineage.store import LineageStore

    return LineageStore(lineage_db_path(project_dir))


def _ensure_terminal_row(entry: _LiveRun, status: str | None) -> bool:
    """Whether *entry*'s row is terminal (or was never inserted) after a retry.

    A row still ``running``, or a store that no longer answers, gets *status*
    written through a store opened by path. The flag ``provenance_degraded`` is
    set, because the writes that failed before may have included block lineage.
    """
    if _row_status(entry.store, entry.run_id) in ("terminal", "absent"):
        return True
    if status not in _TERMINAL_STATUSES or entry.project_dir is None:
        return False
    if not lineage_db_path(entry.project_dir).is_file():
        # #2327 re-audit N3: the project was deleted mid-run. Opening a store
        # by path would recreate the folder and a fresh database inside it.
        logger.warning(
            "#2327: run %s ended %r, but its project's lineage database is gone; nothing is recorded.",
            entry.run_id,
            status,
        )
        return True
    try:
        fallback = _open_store_by_path(entry.project_dir)
    except Exception:
        logger.warning("#2327: could not reopen the lineage store for run %s", entry.run_id, exc_info=True)
        return False
    try:
        row = fallback.get_run(entry.run_id)
        if row is None:
            return True
        if row.get("status") == "running":
            fallback.finalize_run(entry.run_id, finished_at=_now_iso(), status=status, provenance_degraded=True)
            row = fallback.get_run(entry.run_id)
        recorded = row is not None and row.get("status") != "running"
        if recorded:
            logger.warning(
                "#2327: run %s ended %r but that was not recorded through its own lineage store; recorded it "
                "through a reopened store and marked its provenance degraded.",
                entry.run_id,
                status,
            )
        return recorded
    except Exception:
        logger.warning("#2327: could not record the outcome of run %s", entry.run_id, exc_info=True)
        return False
    finally:
        with contextlib.suppress(Exception):
            fallback.close()


def _annotate_unrecorded(entry: _LiveRun, status: str | None) -> None:
    """Keep *entry*'s marker, recording the outcome its row is missing."""
    if entry.marker_path is None:
        return
    if status not in _TERMINAL_STATUSES:
        logger.warning(
            "#2327: run %s has ended but its lineage row is still 'running' and its outcome is unknown. Its "
            "owner marker is kept; the next open of the project records it as %r.",
            entry.run_id,
            INTERRUPTED_RUN_STATUS,
        )
        return
    state, data = _read_marker(entry.marker_path)
    if state != _OK:
        data = {"schema": _MARKER_SCHEMA, "run_id": entry.run_id, **_this_process()}
    data.update({"unrecorded_status": status, "unrecorded_at": _now_iso()})
    try:
        _write_marker(entry.marker_path, data, create_parent=False)
    except OSError:
        logger.warning("#2327: could not annotate the owner marker of run %s", entry.run_id, exc_info=True)
        return
    logger.warning(
        "#2327: run %s ended %r but its lineage row could not be updated. Its owner marker records the "
        "outcome, and the next open of the project writes it.",
        entry.run_id,
        status,
    )


def _stores_ready_to_close() -> list[Any]:
    """Pop the retired stores that no live run writes through any more."""
    ready = [store for store in _RETIRED_STORES if not any(e.store is store for e in _LIVE_RUNS.values())]
    _RETIRED_STORES[:] = [store for store in _RETIRED_STORES if not any(store is r for r in ready)]
    return ready


def _close_stores(stores: list[Any]) -> None:
    for store in stores:
        try:
            store.close()
        except Exception:
            logger.debug("#2327: closing a retired lineage store raised", exc_info=True)


def release_run(run_id: str, *, terminal_status: str | None = None) -> None:
    """Forget a finished run once its row is terminal.

    The owner marker is removed only when the row is terminal. A row still
    ``running`` gets *terminal_status* written again through a store opened by
    path. If that fails too, the marker stays, annotated with the outcome,
    and the next open records it. Call this only after the run's own
    terminal write has run.
    """
    with _LOCK:
        entry = _LIVE_RUNS.pop(run_id, None)
        if entry is None:
            return
        if _ensure_terminal_row(entry, terminal_status):
            if entry.marker_path is not None:
                _unlink_quietly(entry.marker_path)
        else:
            _annotate_unrecorded(entry, terminal_status)
        to_close = _stores_ready_to_close()
    _close_stores(to_close)


def retire_store(store: Any) -> None:
    """Close *store* now, or once the last live run writing through it is released.

    A project switch does not end the previous project's runs; they keep
    recording their blocks and outcome through the store they started with.
    """
    if store is None:
        return
    with _LOCK:
        if any(entry.store is store for entry in _LIVE_RUNS.values()):
            if not any(retired is store for retired in _RETIRED_STORES):
                _RETIRED_STORES.append(store)
            return
    _close_stores([store])


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
    release_run(str(recorder.run_id), terminal_status=status)


def consume_forced(run_id: str | None) -> bool:
    """Whether shutdown already finalised *run_id*; its task must not again."""
    if run_id is None:
        return False
    with _LOCK:
        if run_id in _FORCED_RUN_IDS:
            _FORCED_RUN_IDS.discard(run_id)
            return True
    return False


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
    ``cancelled``. The wait is *timeout_sec* in total, not per run. A task that
    has not finished by then (a block that ignores cancellation, say) is
    finalised as ``cancelled`` here, so its row does not outlive the process as
    ``running``. If that task ends afterwards, its done-callback leaves the row alone.

    Returns:
        The run ids this function finalised itself because their task did not
        finish within the bound.
    """
    bound = _SHUTDOWN_RUN_TIMEOUT_SEC if timeout_sec is None else timeout_sec
    # #2362: every run this process holds, including one a project switch
    # detached from ``workflow_runs`` — it is still executing and still needs a
    # terminal lineage row before the process exits. A runtime stand-in without
    # the accessor falls back to the mapping.
    everything = getattr(self, "all_workflow_runs", None)
    runs = everything() if callable(everything) else list(self.workflow_runs.values())
    pending = [run.task for run in runs if not run.task.done()]
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
        with _LOCK:
            _FORCED_RUN_IDS.add(entry.run_id)
        try:
            entry.recorder.finalize_run(status=SHUTDOWN_RUN_STATUS)
        except Exception:
            logger.warning("#2327: could not finalise run %s at shutdown", entry.run_id, exc_info=True)
        release_run(entry.run_id, terminal_status=SHUTDOWN_RUN_STATUS)
        logger.warning(
            "#2327: run %s did not stop within %.1fs of backend shutdown; its lineage is recorded as %r.",
            entry.run_id,
            bound,
            SHUTDOWN_RUN_STATUS,
        )
        forced.append(entry.run_id)
    return forced


# ---------------------------------------------------------------------------
# Reconciliation when a project's lineage store opens
# ---------------------------------------------------------------------------


def _owner_verdict(marker: dict[str, Any]) -> str:
    """``dead``, ``alive`` or ``foreign`` for the process a marker names.

    ``dead`` only when that is provable: there is no usable PID, the PID is
    gone, it now belongs to a different process, it is a zombie, or the marker
    names this very process (whose live runs the caller has already
    excluded). ``foreign`` means another machine's process, which cannot be
    checked from here. A process this one may not inspect counts as alive.
    """
    pid = marker.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool):
        return _DEAD
    owner_machine = marker.get("machine_id")
    if isinstance(owner_machine, str) and owner_machine:
        if owner_machine != machine_id():
            return _FOREIGN
    else:
        host = marker.get("host")
        if isinstance(host, str) and host and host != socket.gethostname():
            return _FOREIGN
    if pid == os.getpid():
        return _DEAD
    try:
        import psutil
    except ImportError:
        return _ALIVE
    try:
        process = psutil.Process(pid)
        actual = float(process.create_time())
    except psutil.NoSuchProcess:
        return _DEAD
    except Exception:
        return _ALIVE
    try:
        if process.status() == psutil.STATUS_ZOMBIE:
            return _DEAD
    except psutil.NoSuchProcess:
        return _DEAD
    except Exception:
        logger.debug("#2327: could not read the status of pid %s", pid, exc_info=True)
    recorded = marker.get("process_create_time")
    if not isinstance(recorded, int | float):
        return _ALIVE
    return _ALIVE if abs(actual - float(recorded)) <= _PROCESS_IDENTITY_TOLERANCE_SEC else _DEAD


def _owner_description(marker: dict[str, Any] | None) -> str:
    if marker is None:
        return "no process has claimed it (it has no owner marker)"
    pid = marker.get("pid")
    host = marker.get("host") or "this machine"
    if pid == os.getpid():
        return f"this backend (pid {pid}) is no longer running it"
    if isinstance(pid, int) and not isinstance(pid, bool):
        return f"the SciStudio process that ran it (pid {pid} on {host}) has exited, most likely a crash or forced kill"
    return "its owner marker names no process"


def _recorded_outcome(marker: dict[str, Any] | None) -> str | None:
    value = (marker or {}).get("unrecorded_status")
    return value if value in _TERMINAL_STATUSES else None


def _log_to_run(run_id: str, project_dir: Path, message: str, *args: Any) -> None:
    """Warn in the backend log and in the run's own diagnostic log."""
    try:
        from scistudio.engine.run_logging import run_log_context

        with run_log_context(run_id, project_root=project_dir):
            logger.warning(message, *args)
    except Exception:
        logger.warning(message, *args)


def _report_reconciled(
    run_id: str,
    row: dict[str, Any],
    marker: dict[str, Any] | None,
    status: str,
    project_dir: Path,
) -> None:
    if _recorded_outcome(marker) is not None:
        _log_to_run(
            run_id,
            project_dir,
            "#2327: run %s of workflow %r (started %s) ended %r, but its lineage row could not be updated "
            "at the time. It is now recorded as %r; finished_at records when this was written, not when the "
            "run stopped.",
            run_id,
            row.get("workflow_id"),
            row.get("started_at"),
            status,
            status,
        )
        return
    _log_to_run(
        run_id,
        project_dir,
        "#2327: run %s of workflow %r (started %s) was still marked 'running' but %s, so it can no longer "
        "finish. Its lineage is now recorded as %r. finished_at records when this was detected, not when the "
        "run stopped.",
        run_id,
        row.get("workflow_id"),
        row.get("started_at"),
        _owner_description(marker),
        status,
    )


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _warn_foreign(store: Any, run_id: str, marker: dict[str, Any]) -> None:
    """Report a run another machine has owned for longer than the staleness limit."""
    since = _parse_time(marker.get("claimed_at"))
    if since is None:
        with contextlib.suppress(Exception):
            since = _parse_time((store.get_run(run_id) or {}).get("started_at"))
    if since is None or datetime.now(UTC) - since < FOREIGN_OWNER_STALE_AFTER:
        return
    hours = int((datetime.now(UTC) - since).total_seconds() // 3600)
    logger.warning(
        "#2327: run %s is still marked 'running' and has been owned by another machine (machine id %s, host %s) "
        "since %s, %d hours ago. SciStudio cannot check a process on another machine, so the run is left "
        "running; artifact retention for this project stays blocked until it finishes there, or until that "
        "machine opens the project and reconciles it.",
        run_id,
        marker.get("machine_id") or "unknown",
        marker.get("host") or "unknown",
        since.isoformat(),
        hours,
    )


def _sweep_owner_dir(store: Any, project_dir: Path) -> None:
    """Remove markers of runs that ended, and staging files of claims that died."""
    owner_dir = project_dir.joinpath(*_OWNER_DIR_PARTS)
    try:
        paths = sorted(owner_dir.iterdir())
    except OSError:
        return
    now = time.time()
    for path in paths:
        name = path.name
        if name.endswith(".json.tmp"):
            with _LOCK:
                if name[: -len(".json.tmp")] in _LIVE_RUNS:
                    continue
                with contextlib.suppress(OSError):
                    if now - path.stat().st_mtime > _STAGING_STALE_AFTER_SEC:
                        path.unlink()
            continue
        if not name.endswith(".json"):
            continue
        run_id = name[: -len(".json")]
        with _LOCK:
            if run_id in _LIVE_RUNS:
                continue
            state, marker = _read_marker(path)
            if state == _UNREADABLE:
                continue
            try:
                row = store.get_run(run_id)
            except Exception:
                continue
            if row is not None and row.get("status") == "running":
                continue
            if row is None and state == _OK and _owner_verdict(marker) != _DEAD:
                # Claimed by a live process that has not inserted its row yet.
                continue
            _unlink_quietly(path)


def reconcile_interrupted_runs(store: Any, project_dir: str | Path) -> list[str]:
    """Finalise the ``running`` rows that no live process will ever finish.

    Called whenever a project's lineage store is opened, the first moment this
    process can see rows a previous process left behind. Never raises: a
    failure is logged and leaves the rows untouched.

    Returns:
        The run ids that were finalised.
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
            state, marker = _read_marker(marker_path)
            if state == _UNREADABLE:
                logger.warning(
                    "#2327: run %s is still marked 'running' but its owner marker %s could not be read, so its "
                    "owner is unknown. It is left running; artifact retention stays blocked while it is.",
                    run_id,
                    marker_path,
                )
                continue
            owner = marker if state == _OK else None
            if owner is not None:
                verdict = _owner_verdict(owner)
                if verdict == _FOREIGN:
                    _warn_foreign(store, run_id, owner)
                    continue
                if verdict == _ALIVE:
                    continue
            status = _recorded_outcome(owner) or INTERRUPTED_RUN_STATUS
            try:
                row = store.get_run(run_id)
                if row is None or row.get("status") != "running":
                    continue
                store.finalize_run(run_id, finished_at=_now_iso(), status=status)
            except Exception:
                logger.warning("#2327: could not reconcile interrupted run %s", run_id, exc_info=True)
                continue
            if marker_path is not None:
                _unlink_quietly(marker_path)
        _report_reconciled(run_id, row, owner, status, root)
        reconciled.append(run_id)

    try:
        _sweep_owner_dir(store, root)
    except Exception:
        logger.debug("#2327: owner-marker sweep failed", exc_info=True)
    return reconciled


__all__ = [
    "FOREIGN_OWNER_STALE_AFTER",
    "INTERRUPTED_RUN_STATUS",
    "SHUTDOWN_RUN_STATUS",
    "abandon_run",
    "attach_task",
    "claim_run",
    "consume_forced",
    "is_same_path",
    "lineage_db_path",
    "live_run_ids",
    "machine_id",
    "owner_marker_path",
    "reconcile_interrupted_runs",
    "release_run",
    "retire_store",
    "shutdown_workflow_runs",
]
