"""External-audience managed command execution (ADR-055 Spec 2 §5.3, #2279).

ADR-055 §5.3 makes arbitrary code an intended capability: the user authorizes
their agent to run commands with the same ordinary OS permissions as their
SciStudio instance, including installing dependencies. The hackathon demo's
``run_bash`` got every part of the lifecycle wrong (§9.2): a synchronous
``subprocess.run`` on the event loop, output clipped only after full capture,
``cwd=None`` without a project, and no process-registry integration. This
module is the production version:

* ``run_command`` spawns through asyncio (never blocking the loop), registers
  the command in the backend's
  :class:`~scistudio.engine.runners.process_handle.ProcessRegistry` — the one
  the backend's shutdown ``terminate_all`` runs on — and binds the active
  project as working directory and ``SCISTUDIO_PROJECT_DIR``. No project, no
  command: it refuses instead of running with an undefined directory.
* A command owns every process it starts. On Windows each command runs in a
  Job Object, because Windows does not reparent orphans and a tree walk from
  the shell misses any descendant whose parent already exited. On POSIX the
  command gets a new session, and its process group still names every
  descendant after the shell is reaped. Cancel and backend shutdown stop the
  whole job either way.
* Exit is detected from the process itself, not from its pipes: a background
  process the command started may hold stdout/stderr open indefinitely. Output
  keeps draining for a bounded grace period after exit, then the job is
  reported exited with a note that output may be incomplete. A background
  process that is still running keeps the job registered, so cancel and
  shutdown still reach it.
* The environment is the desktop Python terminal's (``desktop/paths.py``): the
  bundled interpreter's ``python``/``pip`` wrappers first on ``PATH`` and
  ``PIP_TARGET`` at the shared user site, so a package installed here is the
  one SciStudio imports afterwards.
* Output is captured incrementally into bounded tails; the whole stream is
  never held.
* Every command is a managed job. The originating request ending — a browser
  timeout or abort — does not end the job; ``list_commands``,
  ``get_command_status`` and ``cancel_command`` reach it by id. Job state lives
  in memory and is cleared when the backend restarts (#2279 owner decision 6).
* Commands that invoke the ``scistudio`` CLI are refused, mirroring the
  provisioned ``deny_scistudio_cli`` hook, with the MCP tools to use instead.
  This is parity with the hook, not containment: arbitrary code can always
  reach the CLI some other way (spec §4.5).

Logging records job ids and outcomes only — never the command text (FR-012).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import platform
import re
import signal
import subprocess
import sys
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, cast

from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import (
    CommandProcessRegistry,
    get_context,
    get_process_registry,
    outside_bridge_context,
)
from scistudio.ai.agent.mcp.server import AUDIENCE_EXTERNAL_TAG, mcp
from scistudio.ai.agent.mcp.tools_workspace import ToolRefusal, register_failure_outcome, status_is_failure
from scistudio.engine.runners.exit_info import ProcessExitInfo
from scistudio.engine.runners.platform import get_platform_ops
from scistudio.engine.runners.process_handle import ProcessHandle

if TYPE_CHECKING:
    import psutil

logger = logging.getLogger(__name__)

OUTPUT_TAIL_CAP_BYTES = 64 * 1024
"""Bytes of each output stream kept per job (the most recent ones)."""

DEFAULT_WAIT_SECONDS = 30.0
MAX_WAIT_SECONDS = 300.0
DEFAULT_CANCEL_GRACE_SECONDS = 5.0

PIPE_DRAIN_GRACE_SECONDS = 1.0
"""How long output is still collected after the command exits (a background process may hold the pipes)."""

COMMAND_REGISTRY_NAMESPACE = "mcp-command"
"""``workflow_id`` half of a command's ProcessRegistry key, separating it from workflow runs."""

_READ_CHUNK_BYTES = 8192
_EXIT_POLL_SECONDS = 0.1
_RESIDUE_POLL_MAX_SECONDS = 5.0
_START_TIME_TOLERANCE_SECONDS = 2.0
_MAX_RETAINED_FINISHED_JOBS = 50
_LABEL_MAX_CHARS = 80
_PREVIEW_MAX_CHARS = 120

# Credentials the backend exports for its own workers; a user command never needs them.
_STRIPPED_ENV_VARS = ("SCISTUDIO_ENGINE_IPC_TOKEN",)

_READ_TAGS = {"category:execution", "read", AUDIENCE_EXTERNAL_TAG}
_WRITE_TAGS = {"category:execution", "write", AUDIENCE_EXTERNAL_TAG}

# The provisioned deny_scistudio_cli hook's pattern, widened for Windows
# (``\`` separators, ``scistudio.exe``) and applied to every shell segment.
_SCISTUDIO_CLI_RE = re.compile(r"^\s*(?:\S*[/\\])?scistudio(?:\.exe)?(?:\s|$)", re.IGNORECASE)
# ``python -m scistudio`` and ``python -m scistudio.cli.main`` (any submodule).
_PYTHON_M_SCISTUDIO_RE = re.compile(r"(?:^|\s)-m\s+scistudio(?:\.[\w.]+)?(?:\s|$)", re.IGNORECASE)
# ``python -c "from scistudio.cli.main import app; app()"``.
_PYTHON_C_SCISTUDIO_CLI_RE = re.compile(r"scistudio\.cli\b", re.IGNORECASE)
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;&|\n]")
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
# Launchers that run the command after them.
_PREFIX_WORDS = frozenset(
    {
        "sudo",
        "env",
        "command",
        "nohup",
        "time",
        "exec",
        "builtin",
        "call",
        "nice",
        "timeout",
        "xargs",
        "start",
        "setsid",
        "stdbuf",
    }
)
# A launcher's own options: ``-n``, ``-i``, ``/b``, a duration or niceness value.
_PREFIX_OPTION_RE = re.compile(r"^(?:-\S*|/[A-Za-z]{1,2}|\d+(?:\.\d+)?[smhd]?)$")
_SHELL_WRAPPERS = frozenset(
    {"sh", "bash", "zsh", "dash", "ksh", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}
)
_SHELL_COMMAND_FLAGS = frozenset({"-c", "/c", "/k", "-command"})
_CLI_ALTERNATIVES = ["list_blocks", "write_workflow", "run_workflow", "get_run_status"]
_CLI_DENIED_MESSAGE = (
    "SciStudio CLI calls bypass the GUI and lineage. Use SciStudio's MCP tools instead: "
    "list_blocks, write_workflow, run_workflow, get_run_status."
)


# ---------------------------------------------------------------------------
# Result models.
# ---------------------------------------------------------------------------


class CommandStatusResult(BaseModel):
    """State of one managed command."""

    status: str = Field(default="ok", description="'ok', or 'refused' (nothing ran; see refusal).")
    refusal: ToolRefusal | None = None
    job_id: str | None = Field(default=None, description="Pass to get_command_status / cancel_command.")
    label: str | None = Field(default=None, description="The label given to run_command, if any.")
    command_preview: str | None = Field(default=None, description="The start of the command line.")
    state: str | None = Field(default=None, description="'running', 'exited', or 'cancelled'.")
    running: bool = False
    exit_code: int | None = None
    pid: int | None = None
    working_directory: str | None = None
    started_at: float | None = Field(default=None, description="POSIX timestamp.")
    finished_at: float | None = None
    duration_seconds: float | None = None
    stdout_tail: str = Field(default="", description=f"The last {OUTPUT_TAIL_CAP_BYTES} bytes of stdout.")
    stderr_tail: str = Field(default="", description=f"The last {OUTPUT_TAIL_CAP_BYTES} bytes of stderr.")
    stdout_bytes: int = Field(default=0, description="Total bytes the command wrote to stdout.")
    stderr_bytes: int = 0
    stdout_truncated: bool = Field(default=False, description="True when stdout_tail holds fewer than stdout_bytes.")
    stderr_truncated: bool = False
    output_incomplete: bool = Field(
        default=False,
        description="True when capture stopped while a background process still held the output open.",
    )
    background_processes_running: bool = Field(
        default=False,
        description="True when the command exited but processes it started are still running.",
    )
    note: str | None = None
    next_step: str = ""


class CommandSummary(BaseModel):
    """One job in ``list_commands``."""

    job_id: str
    label: str | None = None
    command_preview: str
    state: str
    exit_code: int | None = None
    background_processes_running: bool = False
    started_at: float
    finished_at: float | None = None


class ListCommandsResult(BaseModel):
    """Result envelope for ``list_commands``."""

    jobs: list[CommandSummary] = Field(default_factory=list)
    note: str = (
        "Jobs are kept in memory only: a backend restart clears this list and stops every command "
        f"started through run_command. At most {_MAX_RETAINED_FINISHED_JOBS} finished jobs are retained."
    )


# ---------------------------------------------------------------------------
# Job bookkeeping.
# ---------------------------------------------------------------------------


class _BoundedTail:
    """The most recent *cap* bytes of a stream, plus its total length."""

    def __init__(self, cap: int) -> None:
        self._cap = cap
        self._buffer = bytearray()
        self.total_bytes = 0

    def feed(self, chunk: bytes) -> None:
        self.total_bytes += len(chunk)
        self._buffer += chunk
        overflow = len(self._buffer) - self._cap
        if overflow > 0:
            del self._buffer[:overflow]

    @property
    def truncated(self) -> bool:
        return self.total_bytes > len(self._buffer)

    def text(self) -> str:
        data = bytes(self._buffer)
        if self.truncated:
            # The cut may land inside a multi-byte character.
            skip = 0
            while skip < min(3, len(data)) and (data[skip] & 0xC0) == 0x80:
                skip += 1
            data = data[skip:]
        return data.decode("utf-8", errors="replace")


def _process_group_members(pgid: int, started_at: float) -> list[psutil.Process]:
    """Live processes in *pgid* that started no earlier than the command (POSIX).

    The start-time filter keeps a recycled group id from ever matching someone
    else's processes: a group can only be reused after every original member is
    gone, and its new members start later than this command did only by chance —
    they would also have to be in our session's group id, which cannot happen
    while any member of ours is alive.
    """
    import psutil

    getpgid = cast(Callable[[int], int], os.getpgid)  # type: ignore[attr-defined]
    members: list[psutil.Process] = []
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


class _CommandHandle(ProcessHandle):
    """Registry handle for a managed command: it owns the command's whole job.

    ``terminate`` / ``kill`` stop every process the command started, and
    ``owns_live_process`` keeps the handle meaningful to the registry's
    shutdown ``terminate_all`` after the shell itself has exited, for as long
    as anything it started is still running.
    """

    def __init__(self, *, block_id: str, pid: int, started_at: float, job_object: Any) -> None:
        from scistudio.engine.resources import ResourceRequest

        super().__init__(
            block_id=block_id,
            pid=pid,
            start_time=datetime.now(),
            resource_request=ResourceRequest(),
            workflow_id=COMMAND_REGISTRY_NAMESPACE,
        )
        self.job_object = job_object
        # A new session makes the shell its process-group leader: pgid == pid.
        self.pgid: int | None = None if sys.platform == "win32" else pid
        self.started_at = started_at

    def live_members(self) -> int:
        """How many processes of this command are still running."""
        if self.job_object is not None:
            count = self._platform_ops.job_active_process_count(self.job_object)
            if count is not None:
                return count
        if self.pgid is not None:
            return len(_process_group_members(self.pgid, self.started_at))
        # No Job Object (creation or assignment failed): only the shell is known.
        return 1 if ProcessHandle.owns_live_process(self) else 0

    def owns_live_process(self) -> bool:
        return self.live_members() > 0

    def terminate(self, grace_period_sec: float = 5.0) -> ProcessExitInfo:
        return self._stop(grace_period_sec)

    def kill(self) -> ProcessExitInfo:
        return self._stop(0.0)

    def _stop(self, grace: float) -> ProcessExitInfo:
        self.was_killed_by_framework = True
        details: list[str] = []
        if self.pgid is not None:
            details.append(self._stop_process_group(self.pgid, grace))
        else:
            if self.job_object is not None and self._platform_ops.terminate_job_object(self.job_object):
                # The job holds every process the command started, orphans included.
                details.append("job object terminated")
            elif ProcessHandle.owns_live_process(self):
                # No Job Object: walk the tree from the shell (identity-checked, #1542).
                try:
                    details.append(self._platform_ops.terminate_tree(self.pid, grace).platform_detail)
                except Exception as exc:  # the tree may exit while it is being walked
                    details.append(f"tree walk ended early ({type(exc).__name__})")
        return ProcessExitInfo(
            exit_code=None,
            was_killed_by_framework=True,
            platform_detail="; ".join(detail for detail in details if detail) or "nothing left to stop",
        )

    def _stop_process_group(self, pgid: int, grace: float) -> str:
        import psutil

        killpg = cast(Callable[[int, int], None], os.killpg)  # type: ignore[attr-defined]
        sigkill = cast(int, signal.SIGKILL)  # type: ignore[attr-defined]
        members = _process_group_members(pgid, self.started_at)
        if not members:
            return "process group already empty"
        with contextlib.suppress(ProcessLookupError, PermissionError):
            killpg(pgid, signal.SIGTERM)
        _gone, alive = psutil.wait_procs(members, timeout=grace)
        if not alive:
            return "process group terminated"
        with contextlib.suppress(ProcessLookupError, PermissionError):
            killpg(pgid, sigkill)
        psutil.wait_procs(alive, timeout=2.0)
        return "process group killed after grace"

    def close(self) -> None:
        """Release the Job Object (kill-on-close: anything still in it is stopped)."""
        if self.job_object is not None:
            self._platform_ops.close_job_object(self.job_object)
            self.job_object = None


@dataclass
class _Job:
    job_id: str
    project_dir: Path
    started_at: float
    registry: CommandProcessRegistry
    process: asyncio.subprocess.Process
    handle: _CommandHandle
    stdout: _BoundedTail
    stderr: _BoundedTail
    command_preview: str
    label: str | None = None
    task: asyncio.Task[None] | None = None
    exited: asyncio.Event = field(default_factory=asyncio.Event)
    state: str = "running"
    exit_code: int | None = None
    finished_at: float | None = None
    cancel_requested: bool = False
    output_incomplete: bool = False
    released: bool = False
    note: str | None = None

    @property
    def block_id(self) -> str:
        return f"command-{self.job_id}"

    @property
    def background_running(self) -> bool:
        return self.state != "running" and not self.released


_JOBS: OrderedDict[str, _Job] = OrderedDict()


def _evict_finished_jobs() -> None:
    finished = [job_id for job_id, job in _JOBS.items() if job.released]
    for job_id in finished[: max(0, len(finished) - _MAX_RETAINED_FINISHED_JOBS)]:
        _JOBS.pop(job_id, None)


# ---------------------------------------------------------------------------
# Policy and environment.
# ---------------------------------------------------------------------------


def _drop_launchers(tokens: list[str]) -> list[str]:
    """Strip leading env assignments and launchers (with their options) from a command."""
    while tokens:
        if _ENV_ASSIGNMENT_RE.match(tokens[0]):
            tokens = tokens[1:]
            continue
        if tokens[0].casefold() not in _PREFIX_WORDS:
            break
        tokens = tokens[1:]
        while tokens and _PREFIX_OPTION_RE.match(tokens[0]):
            tokens = tokens[1:]
    return tokens


def invokes_scistudio_cli(command: str, _depth: int = 0) -> bool:
    """True when any shell segment of *command* runs the ``scistudio`` CLI.

    Covers the hook's pattern plus quoted names, launchers (``nohup``,
    ``nice``, ``timeout``, ``start /b``, ``env -i`` ...), shell wrappers
    (``sh -c``, ``bash -c``, ``cmd /c``, ``powershell -Command``), and the
    Python module/import forms. Parity with the provisioned hook, not
    containment.
    """
    if _depth > 4:
        return False
    for segment in _SEGMENT_SPLIT_RE.split(command):
        tokens = [token.strip("\"'") for token in segment.split()]
        tokens = _drop_launchers([token for token in tokens if token])
        if not tokens:
            continue
        head = os.path.basename(tokens[0].replace("\\", "/")).casefold()
        if head in _SHELL_WRAPPERS:
            rest = tokens[1:]
            while rest and rest[0].casefold() not in _SHELL_COMMAND_FLAGS and rest[0].startswith(("-", "/")):
                rest = rest[1:]
            if (
                rest
                and rest[0].casefold() in _SHELL_COMMAND_FLAGS
                and invokes_scistudio_cli(" ".join(rest[1:]), _depth + 1)
            ):
                return True
            continue
        joined = " ".join(tokens)
        if _SCISTUDIO_CLI_RE.search(joined) or _PYTHON_M_SCISTUDIO_RE.search(joined):
            return True
        if head.startswith("python") and "-c" in tokens and _PYTHON_C_SCISTUDIO_CLI_RE.search(joined):
            return True
    return False


def _shell_description() -> str:
    if sys.platform == "win32":
        return f"{os.environ.get('COMSPEC', 'cmd.exe')} /c (Windows command processor)"
    return "/bin/sh -c"


def build_command_environment(project_dir: Path) -> dict[str, str]:
    """The environment a command runs with (ADR-055 Spec 2 FR-010).

    The desktop Python terminal's contract (:func:`scistudio.desktop.paths.user_python_terminal_env`):
    the bundled interpreter's ``python``/``pip`` wrappers first on ``PATH``,
    ``PIP_TARGET`` at the shared user dependency site, and the wrappers adding
    that site to ``PYTHONPATH`` — the same site SciStudio's registries and
    workers import from. Plus ``SCISTUDIO_PROJECT_DIR``, as worker processes
    receive it, unbuffered Python output so the tail stays current, and UTF-8
    Python stdio (unless the user set ``PYTHONIOENCODING``) so the tails, which
    are decoded as UTF-8, show non-ASCII text — a Windows Python child would
    otherwise write its pipes in the ANSI code page.
    """
    from scistudio.desktop.paths import user_python_terminal_env

    env = {key: value for key, value in os.environ.items() if key not in _STRIPPED_ENV_VARS}
    env.update(user_python_terminal_env(sys.executable))
    env["SCISTUDIO_PROJECT_DIR"] = str(project_dir.resolve())
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def describe_command_environment(project_dir: Path | None) -> dict[str, Any]:
    """What ``run_command`` would run with, without creating anything (for get_agent_context)."""
    from scistudio.desktop.paths import user_python_bin_dir, user_python_site_dir

    site_dir = user_python_site_dir()
    return {
        "shell": _shell_description(),
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "platform": sys.platform,
        "working_directory": str(project_dir) if project_dir is not None else None,
        "user_site_packages": str(site_dir),
        "user_site_packages_exists": site_dir.is_dir(),
        "python_wrappers_dir": str(user_python_bin_dir()),
        "environment_set": {
            "SCISTUDIO_PROJECT_DIR": str(project_dir) if project_dir is not None else None,
            "PIP_TARGET": str(site_dir),
            "PATH": "SciStudio python/pip wrappers first, then the bundled interpreter's directory",
        },
        "notes": [
            "`python` and `pip` resolve to SciStudio's bundled interpreter; `pip install` lands in "
            "user_site_packages, which SciStudio blocks and workers import from.",
            "One environment is shared by all of this user's projects; there are no per-project environments.",
            "Commands run with the backend user's ordinary OS permissions and no additional sandbox.",
            "A command's background processes belong to its job: cancel_command and backend shutdown stop them.",
        ],
    }


# ---------------------------------------------------------------------------
# Spawn, supervise, report.
# ---------------------------------------------------------------------------


async def _spawn(command: str, cwd: Path, env: dict[str, str]) -> asyncio.subprocess.Process:
    """Start *command* in the platform shell, in its own process group.

    POSIX: ``/bin/sh -c`` through ``create_subprocess_exec`` with a new
    session, so the process group is the whole tree. Windows: the command
    processor through ``create_subprocess_shell`` — CreateProcess
    command-line quoting would corrupt a command string passed to
    ``create_subprocess_exec("cmd.exe", "/c", ...)`` — with a new process
    group and no console window.
    """
    group_kwargs: dict[str, Any] = get_platform_ops().create_process_group({})
    common: dict[str, Any] = {
        "stdin": asyncio.subprocess.DEVNULL,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "cwd": str(cwd),
        "env": env,
        **group_kwargs,
    }
    if sys.platform == "win32":
        common["creationflags"] = common.get("creationflags", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return await asyncio.create_subprocess_shell(command, **common)
    return await asyncio.create_subprocess_exec("/bin/sh", "-c", command, **common)


async def _pump(stream: asyncio.StreamReader | None, tail: _BoundedTail) -> None:
    if stream is None:
        return
    while True:
        chunk = await stream.read(_READ_CHUNK_BYTES)
        if not chunk:
            return
        tail.feed(chunk)


def _close_transport(job: _Job) -> None:
    """Close the pipes of an exited command (prevents unclosed-transport warnings)."""
    if job.process.returncode is None:
        return  # closing a live process's transport would kill it
    transport = getattr(job.process, "_transport", None)
    if transport is not None:
        with contextlib.suppress(Exception):
            transport.close()


def _release(job: _Job) -> None:
    """The command and everything it started are gone: drop it from the registry."""
    if job.released:
        return
    job.released = True
    job.registry.deregister(COMMAND_REGISTRY_NAMESPACE, job.block_id)
    job.handle.close()
    _close_transport(job)
    _evict_finished_jobs()


async def _release_when_idle(job: _Job) -> None:
    """Keep the job registered while a background process it started is still running."""
    delay = _EXIT_POLL_SECONDS * 5
    while not job.released and await asyncio.to_thread(job.handle.live_members) > 0:
        await asyncio.sleep(delay)
        delay = min(delay * 2, _RESIDUE_POLL_MAX_SECONDS)
    _release(job)


async def _supervise(job: _Job) -> None:
    """Collect output until the command exits, record its terminal state, then watch for leftovers."""
    pumps = [
        asyncio.ensure_future(_pump(job.process.stdout, job.stdout)),
        asyncio.ensure_future(_pump(job.process.stderr, job.stderr)),
    ]
    try:
        # asyncio's Process.wait() resolves only after every pipe has closed, and a
        # background process the command started may hold them open indefinitely.
        # returncode is set as soon as the process itself exits, so watch that.
        while job.process.returncode is None and not all(pump.done() for pump in pumps):
            await asyncio.sleep(_EXIT_POLL_SECONDS)
        exit_code = job.process.returncode
        if exit_code is None:
            exit_code = await job.process.wait()
        _done, pending = await asyncio.wait(pumps, timeout=PIPE_DRAIN_GRACE_SECONDS)
        if pending:
            for pump in pending:
                pump.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            job.output_incomplete = True
            job.note = (
                "The command exited, but a background process it started still holds its output open, so "
                f"output capture stopped {PIPE_DRAIN_GRACE_SECONDS:g} s after exit and may be incomplete. That "
                "process keeps running until it ends, cancel_command stops it, or the backend shuts down."
            )
        job.exit_code = exit_code
        job.state = "cancelled" if job.cancel_requested else "exited"
        job.finished_at = time.time()
        job.exited.set()
        logger.info("run_command job=%s outcome=%s exit_code=%s", job.job_id, job.state, exit_code)
        await _release_when_idle(job)
    except asyncio.CancelledError:
        # Loop teardown at backend shutdown: the lifespan's terminate_all has already stopped the job.
        for pump in pumps:
            pump.cancel()
        raise
    finally:
        if job.finished_at is None:
            job.finished_at = time.time()
        job.exited.set()
        _release(job)


async def _wait(job: _Job, seconds: float) -> None:
    """Wait up to *seconds* for the command to exit; a timeout or caller abort leaves it running."""
    if job.exited.is_set() or seconds <= 0:
        return
    with contextlib.suppress(TimeoutError):
        # Only this waiter is cancelled if the calling request goes away; the job is not.
        await asyncio.wait_for(job.exited.wait(), timeout=seconds)


def _report(job: _Job) -> CommandStatusResult:
    running = job.state == "running"
    end = job.finished_at if job.finished_at is not None else time.time()
    if running:
        next_step = (
            f"The command is still running. Poll get_command_status(job_id='{job.job_id}'), or stop it and "
            f"every process it started with cancel_command(job_id='{job.job_id}')."
        )
    elif job.background_running:
        next_step = (
            "The command exited, but a background process it started is still running. "
            f"cancel_command(job_id='{job.job_id}') stops it."
        )
    else:
        next_step = "The command has finished. Inspect exit_code and the output tails."
    return CommandStatusResult(
        job_id=job.job_id,
        label=job.label,
        command_preview=job.command_preview,
        state=job.state,
        running=running,
        exit_code=job.exit_code,
        pid=job.process.pid,
        working_directory=str(job.project_dir),
        started_at=job.started_at,
        finished_at=job.finished_at,
        duration_seconds=round(end - job.started_at, 3),
        stdout_tail=job.stdout.text(),
        stderr_tail=job.stderr.text(),
        stdout_bytes=job.stdout.total_bytes,
        stderr_bytes=job.stderr.total_bytes,
        stdout_truncated=job.stdout.truncated,
        stderr_truncated=job.stderr.truncated,
        output_incomplete=job.output_incomplete,
        background_processes_running=job.background_running,
        note=job.note,
        next_step=next_step,
    )


def _refused(code: str, message: str, use_instead: list[str] | None = None) -> CommandStatusResult:
    logger.info("run_command outcome=refused code=%s", code)
    return CommandStatusResult(
        status="refused",
        refusal=ToolRefusal(code=code, message=message, use_instead=list(use_instead or [])),
    )


def _unknown_job(job_id: str) -> CommandStatusResult:
    return CommandStatusResult(
        status="refused",
        refusal=ToolRefusal(
            code="unknown_job",
            message=(
                f"No command job '{job_id}'. Job state is kept in memory only, so a backend restart "
                "clears it (and stops the command); finished jobs beyond the retention limit are dropped."
            ),
            use_instead=["list_commands"],
        ),
        job_id=job_id,
    )


def _clamp_wait(seconds: float) -> float:
    return max(0.0, min(float(seconds), MAX_WAIT_SECONDS))


def _preview(command: str) -> str:
    flat = " ".join(command.split())
    return flat if len(flat) <= _PREVIEW_MAX_CHARS else flat[: _PREVIEW_MAX_CHARS - 1] + "…"


# ---------------------------------------------------------------------------
# Tools.
# ---------------------------------------------------------------------------


@mcp.tool(name="run_command", tags=_WRITE_TAGS)
async def run_command(
    command: Annotated[str, Field(description="Shell command line to run (POSIX /bin/sh; Windows cmd.exe).")],
    wait_seconds: Annotated[
        float,
        Field(
            description=(
                f"Seconds to wait for completion before returning (0-{MAX_WAIT_SECONDS:g}). A command still "
                "running afterwards keeps running as a managed job."
            ),
        ),
    ] = DEFAULT_WAIT_SECONDS,
    label: Annotated[
        str | None,
        Field(description=f"Optional short name (up to {_LABEL_MAX_CHARS} characters) shown by list_commands."),
    ] = None,
) -> CommandStatusResult:
    """Run a shell command in the active project as a managed job.

    Runs with the active project as working directory, ``SCISTUDIO_PROJECT_DIR``
    set, and SciStudio's bundled Python first on ``PATH`` — ``pip install``
    lands in the user dependency site SciStudio imports from. The command runs
    with the user's ordinary OS permissions. Output is captured into bounded
    tails. If it is still running after ``wait_seconds``, the result says so
    with a ``job_id``: the job keeps running even if this request ends; use
    get_command_status to follow it and cancel_command to stop it and every
    process it started, including background ones. Commands that invoke the
    ``scistudio`` CLI are refused — use the MCP tools (list_blocks,
    write_workflow, run_workflow, get_run_status).
    """
    ctx = get_context()
    project_dir = ctx.project_dir
    if project_dir is None:
        return _refused(
            "no_active_project",
            "run_command runs in the active project (working directory and SCISTUDIO_PROJECT_DIR), and no "
            "project is open. Open a project first.",
            ["get_agent_context"],
        )
    if not command.strip():
        return _refused("invalid_command", "The command is empty.")
    if invokes_scistudio_cli(command):
        return _refused("scistudio_cli_denied", _CLI_DENIED_MESSAGE, _CLI_ALTERNATIVES)
    registry = get_process_registry(ctx)
    if registry is None:
        return _refused(
            "execution_unavailable",
            "This SciStudio context has no backend process registry (for example the standalone MCP bridge). "
            "Managed commands need the backend, so they stop when it stops.",
        )

    cwd = Path(project_dir)
    env = await asyncio.to_thread(build_command_environment, cwd)
    ops = get_platform_ops()
    started_at = time.time()
    try:
        process = await _spawn(command, cwd, env)
    except OSError as exc:
        return _refused("spawn_failed", f"The command could not be started: {exc.strerror or type(exc).__name__}.")
    # Windows: put the command in a Job Object at once, so every process it starts from
    # here on belongs to the job. (A process the shell starts in the instant before this
    # call is still reached by the tree walk while its parent lives.)
    job_object = ops.create_job_object()
    if job_object is not None and not ops.assign_to_job(job_object, process.pid):
        ops.close_job_object(job_object)
        job_object = None
    job_id = uuid.uuid4().hex[:12]
    handle = _CommandHandle(block_id=f"command-{job_id}", pid=process.pid, started_at=started_at, job_object=job_object)
    registry.register(handle)
    job = _Job(
        job_id=job_id,
        project_dir=cwd,
        started_at=started_at,
        registry=registry,
        process=process,
        handle=handle,
        stdout=_BoundedTail(OUTPUT_TAIL_CAP_BYTES),
        stderr=_BoundedTail(OUTPUT_TAIL_CAP_BYTES),
        command_preview=_preview(command),
        label=(label or "").strip()[:_LABEL_MAX_CHARS] or None,
    )
    _JOBS[job_id] = job
    # A task of its own, not part of this request, so the request ending does not end
    # the job; started outside the bridge-call marker, since it outlives the call.
    job.task = asyncio.get_running_loop().create_task(
        _supervise(job), name=f"mcp-command-{job_id}", context=outside_bridge_context()
    )
    logger.info("run_command job=%s outcome=started", job_id)
    await _wait(job, _clamp_wait(wait_seconds))
    return _report(job)


@mcp.tool(name="get_command_status", tags=_READ_TAGS)
async def get_command_status(
    job_id: Annotated[str, Field(description="The job_id run_command returned.")],
    wait_seconds: Annotated[
        float,
        Field(description=f"Seconds to wait for the job to finish before reporting (0-{MAX_WAIT_SECONDS:g})."),
    ] = 0.0,
) -> CommandStatusResult:
    """Report a managed command's state, exit code, and output tails.

    Optionally waits up to ``wait_seconds`` for it to finish first. Waiting
    never affects the job; aborting this call leaves it running.
    """
    job = _JOBS.get(job_id)
    if job is None:
        return _unknown_job(job_id)
    await _wait(job, _clamp_wait(wait_seconds))
    return _report(job)


@mcp.tool(name="list_commands", tags=_READ_TAGS)
async def list_commands() -> ListCommandsResult:
    """List the managed commands this backend knows about, newest last.

    Use it to find a job whose ``run_command`` request ended before its result
    arrived (for example after a browser timeout). ``label`` and
    ``command_preview`` tell jobs apart.
    """
    return ListCommandsResult(
        jobs=[
            CommandSummary(
                job_id=job.job_id,
                label=job.label,
                command_preview=job.command_preview,
                state=job.state,
                exit_code=job.exit_code,
                background_processes_running=job.background_running,
                started_at=job.started_at,
                finished_at=job.finished_at,
            )
            for job in _JOBS.values()
        ]
    )


@mcp.tool(name="cancel_command", tags=_WRITE_TAGS)
async def cancel_command(
    job_id: Annotated[str, Field(description="The job_id run_command returned.")],
    grace_seconds: Annotated[
        float,
        Field(description="Seconds to allow a graceful exit before the job's processes are killed (0-60)."),
    ] = DEFAULT_CANCEL_GRACE_SECONDS,
) -> CommandStatusResult:
    """Stop a managed command and every process it started.

    Stops the whole job — including processes whose parent already exited and
    background processes left running after the command itself exited —
    gracefully, then forced after ``grace_seconds``, and reports the terminal
    state. Cancelling a job with nothing left running just reports it.
    """
    job = _JOBS.get(job_id)
    if job is None:
        return _unknown_job(job_id)
    if job.state != "running" and job.released:
        result = _report(job)
        result.note = "The command had already finished; nothing to cancel."
        return result
    was_running = job.state == "running"
    if was_running:
        job.cancel_requested = True
    grace = max(0.0, min(float(grace_seconds), 60.0))
    # Stopping the job sleeps through its grace period; keep it off the event loop.
    await asyncio.to_thread(job.handle.terminate, grace)
    await _wait(job, grace + 5.0)
    if job.exited.is_set() and await asyncio.to_thread(job.handle.live_members) == 0:
        _release(job)
    result = _report(job)
    if job.state == "running":
        result.note = "Termination was requested but the command has not exited yet; poll get_command_status."
    elif not was_running:
        result.note = (
            "The command had already exited; the background processes it left running were stopped."
            if job.released
            else "The command had already exited; stopping its background processes was requested."
        )
    logger.info("cancel_command job=%s outcome=%s", job.job_id, job.state)
    return result


def _command_failed(structured: dict[str, Any]) -> bool:
    """A refusal, or a command that ended with a non-zero exit (owner decision 2026-09-11)."""
    if status_is_failure(structured):
        return True
    return structured.get("state") == "exited" and structured.get("exit_code") not in (None, 0)


def _cancel_failed(structured: dict[str, Any]) -> bool:
    """A refusal, or a cancel that did not stop the command or its background processes."""
    if status_is_failure(structured):
        return True
    return bool(structured.get("running")) or bool(structured.get("background_processes_running"))


register_failure_outcome("run_command", _command_failed)
register_failure_outcome("get_command_status", _command_failed)
register_failure_outcome("cancel_command", _cancel_failed)


__all__ = [
    "COMMAND_REGISTRY_NAMESPACE",
    "OUTPUT_TAIL_CAP_BYTES",
    "PIPE_DRAIN_GRACE_SECONDS",
    "CommandStatusResult",
    "ListCommandsResult",
    "build_command_environment",
    "cancel_command",
    "describe_command_environment",
    "get_command_status",
    "invokes_scistudio_cli",
    "list_commands",
    "run_command",
]
