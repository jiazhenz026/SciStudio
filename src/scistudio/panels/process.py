"""The resident panel subprocess host: launcher, registry handle, call pipe.

ADR-054 MiniApp FR-006..FR-015. A context that provides ``call`` for a panel
with ``panel.py`` starts one subprocess through :func:`start_panel_process`, off
the API event loop, using the interpreter and import roots block workers get.
:class:`PanelProcess` owns the control pipe on a single background thread so
calls run one at a time, in order; a bounded queue, a per-call timeout, a result
budget, and crash capture keep a faulty ``panel.py`` from taking the app down.
:class:`PanelProcessHandle` registers in the application process registry and
ends the whole process tree, modelled on the agent's command handle.
"""

from __future__ import annotations

import contextlib
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from scistudio.engine.runners.exit_info import ProcessExitInfo
from scistudio.engine.runners.platform import get_platform_ops
from scistudio.engine.runners.process_handle import ProcessHandle, ProcessRegistry
from scistudio.panels.process_config import (
    call_timeout,
    max_result_bytes,
    max_waiting,
    startup_timeout,
    teardown_grace,
)
from scistudio.panels.protocol import ProtocolError, recv_frame, send_frame

logger = logging.getLogger(__name__)

REGISTRY_NAMESPACE = "panel-context"
_START_TIME_TOLERANCE_SECONDS = 2.0

# States surfaced to the tab (FR-015).
STARTING = "starting"
RUNNING = "running"
UNRESPONSIVE = "unresponsive"
STOPPED = "stopped"
CRASHED = "crashed"
START_FAILED = "start_failed"


class PanelCallError(Exception):
    """A call could not be completed; ``code`` is the stable page-facing reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _posix_group_members(pgid: int, started_at: float) -> list[Any]:
    """Live processes in *pgid* that started no earlier than the process.

    The kernel keeps a process-group id reserved while any member is alive, so
    the id names only ours; the start-time filter drops an id recycled after we
    exited (mirrors the agent command handle, #2292 / #1542). Signalling each
    member's PID individually — rather than ``killpg`` — avoids the EPERM the
    kernel returns for an orphaned group whose leader has already exited.
    """
    import psutil

    getpgid = os.getpgid  # type: ignore[attr-defined]
    members: list[Any] = []
    for proc in psutil.process_iter(["create_time"]):
        try:
            if getpgid(proc.pid) != pgid:
                continue
            if (proc.info.get("create_time") or 0.0) + _START_TIME_TOLERANCE_SECONDS < started_at:
                continue
            if proc.status() == psutil.STATUS_ZOMBIE:
                continue
        except (psutil.Error, OSError):
            continue
        members.append(proc)
    return members


class PanelProcessHandle(ProcessHandle):
    """Registry handle that ends a panel process and everything it started.

    Registered in the application registry (``app.state.registry``) under the
    ``panel-context`` namespace keyed by ``context-<context_id>``, so shutdown's
    ``terminate_all`` reaches it (FR-008). On POSIX the child is its own
    process-group leader and every live group member is signalled by PID; on
    Windows the tree is held in a Job Object. ``owns_live_process`` stays true
    while any process the panel started is alive, so a lingering child is not
    orphaned by shutdown.
    """

    def __init__(self, *, context_id: str, pid: int, started_at: float, job_object: Any) -> None:
        from scistudio.engine.resources import ResourceRequest

        super().__init__(
            block_id=f"context-{context_id}",
            pid=pid,
            start_time=datetime.now(),
            resource_request=ResourceRequest(),
            workflow_id=REGISTRY_NAMESPACE,
        )
        self.context_id = context_id
        self.job_object = job_object
        self.pgid: int | None = None if sys.platform == "win32" else pid
        self.started_at = started_at

    def live_members(self) -> int:
        if self.job_object is not None:
            count = self._platform_ops.job_active_process_count(self.job_object)
            if count is not None:
                return count
        if self.pgid is not None:
            try:
                return len(_posix_group_members(self.pgid, self.started_at))
            except Exception:
                return 1 if ProcessHandle.owns_live_process(self) else 0
        return 1 if ProcessHandle.owns_live_process(self) else 0

    def owns_live_process(self) -> bool:
        return self.live_members() > 0

    def terminate(self, grace_period_sec: float = 5.0) -> ProcessExitInfo:
        self.was_killed_by_framework = True
        detail = self._stop(grace_period_sec)
        self._close_job()
        return ProcessExitInfo(exit_code=None, was_killed_by_framework=True, platform_detail=detail)

    def kill(self) -> ProcessExitInfo:
        self.was_killed_by_framework = True
        detail = self._stop(0.0)
        self._close_job()
        return ProcessExitInfo(exit_code=None, was_killed_by_framework=True, platform_detail=detail)

    def _stop(self, grace: float) -> str:
        if self.pgid is None:
            # Windows: the Job Object holds the tree; fall back to the base
            # psutil tree walk when no job was created.
            if self.job_object is not None and self._platform_ops.terminate_job_object(self.job_object):
                return "job object terminated"
            info = self._platform_ops.terminate_tree(self.pid, grace)
            return info.platform_detail
        return self._stop_group(grace)

    def _stop_group(self, grace: float) -> str:
        import signal

        import psutil

        members = _posix_group_members(self.pgid, self.started_at) if self.pgid is not None else []
        if not members:
            return "process group already empty"
        for proc in members:
            with contextlib.suppress(psutil.Error, OSError):
                proc.send_signal(signal.SIGTERM)
        _, alive = psutil.wait_procs(members, timeout=grace)
        for proc in alive:
            with contextlib.suppress(psutil.Error, OSError):
                proc.kill()
        return "process group terminated" if not alive else "process group killed after grace"

    def _close_job(self) -> None:
        if self.job_object is not None:
            try:
                self._platform_ops.close_job_object(self.job_object)
            finally:
                self.job_object = None


class _Call:
    __slots__ = ("args", "done", "error", "fn", "header", "payload")

    def __init__(self, fn: str, args: dict[str, Any]) -> None:
        self.fn = fn
        self.args = args
        self.done = threading.Event()
        self.header: dict[str, Any] | None = None
        self.payload: bytes = b""
        self.error: PanelCallError | None = None


class PanelProcess:
    """One panel subprocess and the single thread that owns its control pipe."""

    def __init__(
        self,
        *,
        context_id: str,
        handle: PanelProcessHandle,
        popen: subprocess.Popen[bytes],
        registry: ProcessRegistry,
        log_path: Path,
        setup_payload: Any,
    ) -> None:
        self.context_id = context_id
        self.handle = handle
        self._popen = popen
        self._registry = registry
        self.log_path = log_path
        self._setup_payload = setup_payload
        self._request: BinaryIO = popen.stdin  # type: ignore[assignment]
        self._response: BinaryIO = popen.stdout  # type: ignore[assignment]
        self.state = STARTING
        self.started_at = time.time()
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._jobs: queue.Queue[_Call | None] = queue.Queue(maxsize=max_waiting())
        self._setup_error: dict[str, Any] | None = None
        self._closing = False
        self._startup_timer: threading.Timer | None = None
        self._worker = threading.Thread(target=self._pump, name=f"panel-{context_id}", daemon=True)

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._startup_timer = threading.Timer(startup_timeout(), self._on_startup_timeout)
        self._startup_timer.daemon = True
        self._startup_timer.start()
        self._worker.start()

    def _on_startup_timeout(self) -> None:
        with self._lock:
            if self.state != STARTING:
                return
            self.state = START_FAILED
            self._setup_error = {"type": "TimeoutError", "message": "panel.py setup did not complete in time"}
        self._ready.set()
        # Closing the pipe (via terminate) unblocks the worker's blocking read.
        self._terminate_tree()

    def _pump(self) -> None:
        try:
            send_frame(self._request, {"type": "setup", "data": self._setup_payload})
            header, _ = recv_frame(self._response, max_payload=max_result_bytes())
        except (OSError, ProtocolError):
            self._on_exit(unexpected=self.state == STARTING)
            return
        with self._lock:
            if self.state != STARTING:
                self._ready.set()
            elif header.get("type") == "ready":
                self.state = RUNNING
            else:
                self.state = START_FAILED
                self._setup_error = header.get("error") if isinstance(header.get("error"), dict) else None
        self._cancel_startup_timer()
        self._ready.set()
        if self.state != RUNNING:
            self._terminate_tree()
            return
        self._serve_calls()

    def _serve_calls(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:  # shutdown sentinel
                self._graceful_shutdown()
                return
            try:
                send_frame(self._request, {"type": "call", "id": id(job), "fn": job.fn, "args": job.args})
                header, payload = recv_frame(self._response, max_payload=max_result_bytes())
            except (OSError, ProtocolError):
                job.error = PanelCallError("process_exited", "The panel process exited")
                job.done.set()
                self._on_exit(unexpected=True)
                return
            job.header, job.payload = header, payload
            with self._lock:
                if self.state == UNRESPONSIVE:
                    # The slow call the caller gave up on has returned.
                    self.state = RUNNING
            job.done.set()

    def _graceful_shutdown(self) -> None:
        # panel.py's teardown runs on the shutdown message; give it the grace
        # period to exit on its own before the tree is terminated (FR-013).
        with contextlib.suppress(OSError, ProtocolError):
            send_frame(self._request, {"type": "shutdown"})
        with contextlib.suppress(Exception):
            self._popen.wait(timeout=teardown_grace())
        # Always end the tree even after the root exited on its own: a child
        # panel.py started is in the same process group and must not survive.
        self._terminate_tree()
        self._reap()
        with self._lock:
            if self.state not in (CRASHED, START_FAILED):
                self.state = STOPPED
        self._fail_pending()
        self._deregister()

    def _on_exit(self, *, unexpected: bool) -> None:
        with self._lock:
            if self.state not in (STOPPED, START_FAILED):
                self.state = CRASHED if unexpected else STOPPED
        self._cancel_startup_timer()
        self._reap()
        self._ready.set()
        self._fail_pending()
        self._deregister()

    def _reap(self) -> None:
        """Reap the child so a finished process is not left as a zombie."""
        with contextlib.suppress(Exception):
            self._popen.wait(timeout=teardown_grace())

    def _fail_pending(self) -> None:
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return
            if job is None:
                continue
            job.error = PanelCallError("process_exited", "The panel process exited")
            job.done.set()

    def stop(self) -> None:
        """Graceful close: teardown, grace, then kill the tree (FR-013)."""
        with self._lock:
            if self._closing:
                return
            self._closing = True
            running = self.state == RUNNING and self._worker.is_alive()
        self._cancel_startup_timer()
        if running:
            # The worker owns the pipe; drive teardown through it and wait for
            # it to terminate and reap the tree.
            with contextlib.suppress(queue.Full):
                self._jobs.put_nowait(None)  # shutdown sentinel
            self._worker.join(timeout=teardown_grace() + 5.0)
        if self._popen.poll() is None:
            self._terminate_tree()
        self._reap()
        with self._lock:
            if self.state not in (CRASHED, START_FAILED):
                self.state = STOPPED
        self._fail_pending()
        self._deregister()

    def _terminate_tree(self) -> None:
        try:
            self.handle.terminate(teardown_grace())
        except Exception:
            logger.exception("panel %s: terminate failed", self.context_id)

    def _cancel_startup_timer(self) -> None:
        timer, self._startup_timer = self._startup_timer, None
        if timer is not None:
            timer.cancel()

    def _deregister(self) -> None:
        self._registry.deregister(REGISTRY_NAMESPACE, self.handle.block_id)

    # -- calls -------------------------------------------------------------

    def call(self, fn: str, args: dict[str, Any]) -> _Call:
        """Enqueue one call and wait for its result, honouring the call limits.

        Runs on a worker thread (the route awaits it via ``asyncio.to_thread``).
        Returns the completed :class:`_Call`; raises :class:`PanelCallError` for
        busy, timeout, process_exited, start_failed, or too_large.
        """
        self._ready.wait(startup_timeout())
        with self._lock:
            state = self.state
        if state == START_FAILED:
            raise PanelCallError("start_failed", "The panel did not start")
        if state in (STOPPED, CRASHED):
            raise PanelCallError("process_exited", "The panel process is not running")
        if state == UNRESPONSIVE:
            raise PanelCallError("busy", "A previous call has not returned")
        if state != RUNNING:
            raise PanelCallError("busy", "The panel is still starting")
        job = _Call(fn, args)
        try:
            self._jobs.put_nowait(job)
        except queue.Full as exc:
            raise PanelCallError("busy", "Too many calls are already waiting") from exc
        if not job.done.wait(call_timeout()):
            with self._lock:
                if self.state == RUNNING:
                    self.state = UNRESPONSIVE
            raise PanelCallError("timeout", "The call exceeded the panel time limit")
        if job.error is not None:
            raise job.error
        header = job.header or {}
        if header.get("type") == "error":
            code = header.get("error_code")
            if code == "too_large":
                raise PanelCallError("too_large", "The result exceeds the panel byte budget")
            return job  # author-exception error frame; the route shapes it
        return job

    # -- observability -----------------------------------------------------

    def resident_memory(self) -> int | None:
        try:
            import psutil

            return int(psutil.Process(self._popen.pid).memory_info().rss)
        except Exception:
            return None

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = self.state
            error = self._setup_error
        info: dict[str, Any] = {
            "state": state,
            "pid": self._popen.pid,
            "started_at": self.started_at,
            "resident_memory": self.resident_memory(),
            "exit_code": self._popen.poll(),
        }
        if error is not None:
            info["error"] = error
        if state in (CRASHED, START_FAILED):
            info["log_tail"] = self.log_tail()
        return info

    def log_tail(self, *, max_bytes: int = 8192) -> str:
        try:
            with self.log_path.open("rb") as handle:
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - max_bytes))
                return handle.read().decode("utf-8", errors="replace")
        except OSError:
            return ""


def _log_path(project_dir: Path, context_id: str) -> Path:
    directory = project_dir / ".scistudio" / "panels" / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{context_id}.log"


def _process_env(panel_dir: Path, project_dir: Path, import_roots: tuple[str, ...]) -> dict[str, str]:
    """The block-worker import surface plus the panel directory and no bytecode.

    FR-006: the runtime import roots blocks receive, the panel directory on the
    import path, ``PYTHONDONTWRITEBYTECODE=1`` so importing ``panel.py`` writes
    nothing into the panel directory, and ``SCISTUDIO_PROJECT_DIR`` as workers
    receive it.
    """
    env = dict(os.environ)
    parent_cwd = Path(os.getcwd())
    existing = [part for part in env.get("PYTHONPATH", "").split(os.pathsep) if part]
    ordered = [str(parent_cwd), str(parent_cwd / "src"), *import_roots, *existing]
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(ordered))
    env["SCISTUDIO_PANEL_DIR"] = str(panel_dir.resolve())
    env["SCISTUDIO_PROJECT_DIR"] = str(project_dir.resolve())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def start_panel_process(
    *,
    context_id: str,
    panel_dir: Path,
    project_dir: Path,
    registry: ProcessRegistry,
    setup_payload: Any,
    import_roots: tuple[str, ...] = (),
    python_executable: str | None = None,
) -> PanelProcess:
    """Launch the panel subprocess and register its handle (FR-006/FR-008)."""
    panel_dir = Path(panel_dir)
    project_dir = Path(project_dir)
    log_path = _log_path(project_dir, context_id)
    platform_ops = get_platform_ops()
    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        # Author print/stderr and any early traceback land in the per-context
        # log; the control channel is the redirected stdin/stdout (bootstrap).
        "stderr": log_path.open("ab"),
        "cwd": str(project_dir),
        "env": _process_env(panel_dir, project_dir, import_roots),
    }
    popen_kwargs = platform_ops.create_process_group(popen_kwargs)
    job_object = platform_ops.create_job_object() if sys.platform == "win32" else None
    popen = subprocess.Popen(
        [python_executable or sys.executable, "-m", "scistudio.panels.bootstrap"],
        **popen_kwargs,
    )
    # The parent no longer needs its copy of the log write end.
    with contextlib.suppress(Exception):
        popen_kwargs["stderr"].close()
    if job_object is not None:
        platform_ops.assign_to_job(job_object, popen.pid)
    handle = PanelProcessHandle(context_id=context_id, pid=popen.pid, started_at=time.time(), job_object=job_object)
    handle._popen = popen
    registry.register(handle)
    process = PanelProcess(
        context_id=context_id,
        handle=handle,
        popen=popen,
        registry=registry,
        log_path=log_path,
        setup_payload=setup_payload,
    )
    process.start()
    return process


__all__ = [
    "CRASHED",
    "REGISTRY_NAMESPACE",
    "RUNNING",
    "STARTING",
    "START_FAILED",
    "STOPPED",
    "UNRESPONSIVE",
    "PanelCallError",
    "PanelProcess",
    "PanelProcessHandle",
    "start_panel_process",
]
