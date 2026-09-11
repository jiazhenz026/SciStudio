"""External-audience managed command execution (ADR-055 Spec 2 §5.3, #2279).

ADR-055 §5.3 makes arbitrary code an intended capability: the user authorizes
their agent to run commands with the same ordinary OS permissions as their
SciStudio instance, including installing dependencies. The hackathon demo's
``run_bash`` got every part of the lifecycle wrong (§9.2): a synchronous
``subprocess.run`` on the event loop, output clipped only after full capture,
``cwd=None`` without a project, and no process-registry integration. This
module is the production version:

* ``run_command`` spawns through asyncio (never blocking the loop) with the
  platform process-group flags, registers the process in the backend's
  :class:`~scistudio.engine.runners.process_handle.ProcessRegistry` — the one
  the backend's shutdown ``terminate_all`` runs on — and binds the active
  project as working directory and ``SCISTUDIO_PROJECT_DIR``. No project, no
  command: it refuses instead of running with an undefined directory.
* The environment is the desktop Python terminal's (``desktop/paths.py``): the
  bundled interpreter's ``python``/``pip`` wrappers first on ``PATH`` and
  ``PIP_TARGET`` at the shared user site, so a package installed here is the
  one SciStudio imports afterwards.
* Output is captured incrementally into bounded tails; the whole stream is
  never held.
* Every command is a managed job. The originating request ending — a browser
  timeout or abort — does not end the job; ``get_command_status`` and
  ``cancel_command`` reach it by id, and ``cancel_command`` terminates the
  whole process tree. Job state lives in memory and is cleared when the
  backend restarts (#2279 owner decision 6).
* Commands that invoke the ``scistudio`` CLI are refused, mirroring the
  provisioned ``deny_scistudio_cli`` hook, with the MCP tools to use instead.

Logging records job ids and outcomes only — never the command text (FR-012).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import platform
import re
import subprocess
import sys
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, cast

from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import CommandProcessRegistry, get_context, get_process_registry
from scistudio.ai.agent.mcp.server import AUDIENCE_EXTERNAL_TAG, mcp
from scistudio.ai.agent.mcp.tools_workspace import ToolRefusal

if TYPE_CHECKING:
    from scistudio.engine.runners.process_handle import ProcessHandle, ProcessRegistry

logger = logging.getLogger(__name__)

OUTPUT_TAIL_CAP_BYTES = 64 * 1024
"""Bytes of each output stream kept per job (the most recent ones)."""

DEFAULT_WAIT_SECONDS = 30.0
MAX_WAIT_SECONDS = 300.0
DEFAULT_CANCEL_GRACE_SECONDS = 5.0

COMMAND_REGISTRY_NAMESPACE = "mcp-command"
"""``workflow_id`` half of a command's ProcessRegistry key, separating it from workflow runs."""

_READ_CHUNK_BYTES = 8192
_PIPE_DRAIN_GRACE_SECONDS = 1.0
_MAX_RETAINED_FINISHED_JOBS = 50

# Credentials the backend exports for its own workers; a user command never needs them.
_STRIPPED_ENV_VARS = ("SCISTUDIO_ENGINE_IPC_TOKEN",)

_READ_TAGS = {"category:execution", "read", AUDIENCE_EXTERNAL_TAG}
_WRITE_TAGS = {"category:execution", "write", AUDIENCE_EXTERNAL_TAG}

# The provisioned deny_scistudio_cli hook's pattern, widened for Windows
# (``\`` separators, ``scistudio.exe``) and applied to every shell segment.
_SCISTUDIO_CLI_RE = re.compile(r"^\s*(?:\S*[/\\])?scistudio(?:\.exe)?(?:\s|$)", re.IGNORECASE)
_PYTHON_M_SCISTUDIO_RE = re.compile(r"(?:^|\s)-m\s+scistudio(?:\s|$)", re.IGNORECASE)
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;&|\n]")
_ENV_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
_PREFIX_WORDS = frozenset({"sudo", "env", "command", "nohup", "time", "exec", "builtin", "call"})
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
    note: str | None = None
    next_step: str = ""


class CommandSummary(BaseModel):
    """One job in ``list_commands``."""

    job_id: str
    state: str
    exit_code: int | None = None
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


@dataclass
class _Job:
    job_id: str
    project_dir: Path
    started_at: float
    registry: CommandProcessRegistry
    process: asyncio.subprocess.Process
    handle: ProcessHandle
    stdout: _BoundedTail
    stderr: _BoundedTail
    task: asyncio.Task[None] | None = None
    state: str = "running"
    exit_code: int | None = None
    finished_at: float | None = None
    cancel_requested: bool = False
    note: str | None = None

    @property
    def block_id(self) -> str:
        return f"command-{self.job_id}"


_JOBS: OrderedDict[str, _Job] = OrderedDict()


def _evict_finished_jobs() -> None:
    finished = [job_id for job_id, job in _JOBS.items() if job.state != "running"]
    for job_id in finished[: max(0, len(finished) - _MAX_RETAINED_FINISHED_JOBS)]:
        _JOBS.pop(job_id, None)


# ---------------------------------------------------------------------------
# Policy and environment.
# ---------------------------------------------------------------------------


def invokes_scistudio_cli(command: str) -> bool:
    """True when any shell segment of *command* runs the ``scistudio`` CLI."""
    # _SCISTUDIO_CLI_RE accepts both separators, so paths need no normalization.
    for segment in _SEGMENT_SPLIT_RE.split(command):
        tokens = segment.split()
        while tokens and (_ENV_ASSIGNMENT_RE.match(tokens[0]) or tokens[0].casefold() in _PREFIX_WORDS):
            tokens.pop(0)
        stripped = " ".join(tokens)
        if _SCISTUDIO_CLI_RE.search(stripped) or _PYTHON_M_SCISTUDIO_RE.search(stripped):
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
    from scistudio.engine.runners.platform import get_platform_ops

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


async def _supervise(job: _Job) -> None:
    """Collect output until the command exits, then record its terminal state."""
    pumps = [
        asyncio.ensure_future(_pump(job.process.stdout, job.stdout)),
        asyncio.ensure_future(_pump(job.process.stderr, job.stderr)),
    ]
    try:
        exit_code = await job.process.wait()
        _done, pending = await asyncio.wait(pumps, timeout=_PIPE_DRAIN_GRACE_SECONDS)
        if pending:
            for pump in pending:
                pump.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            job.note = (
                "The command exited, but a background process it started still holds its output open; "
                "output capture stopped when the command exited."
            )
        job.exit_code = exit_code
        job.state = "cancelled" if job.cancel_requested else "exited"
        logger.info("run_command job=%s outcome=%s exit_code=%s", job.job_id, job.state, exit_code)
    except asyncio.CancelledError:
        # Loop teardown at backend shutdown: the lifespan's terminate_all owns the tree.
        for pump in pumps:
            pump.cancel()
        raise
    finally:
        job.finished_at = time.time()
        job.registry.deregister(COMMAND_REGISTRY_NAMESPACE, job.block_id)
        _evict_finished_jobs()


async def _wait(job: _Job, seconds: float) -> None:
    """Wait up to *seconds* for the job; a timeout or caller abort leaves it running."""
    if job.task is None or job.task.done() or seconds <= 0:
        return
    with contextlib.suppress(TimeoutError):
        # shield: if the waiting request is cancelled, the job is not.
        await asyncio.wait_for(asyncio.shield(job.task), timeout=seconds)


def _report(job: _Job) -> CommandStatusResult:
    running = job.state == "running"
    end = job.finished_at if job.finished_at is not None else time.time()
    if running:
        next_step = (
            f"The command is still running. Poll get_command_status(job_id='{job.job_id}'), or stop it and "
            f"its child processes with cancel_command(job_id='{job.job_id}')."
        )
    else:
        next_step = "The command has finished. Inspect exit_code and the output tails."
    return CommandStatusResult(
        job_id=job.job_id,
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
) -> CommandStatusResult:
    """Run a shell command in the active project as a managed job.

    Runs with the active project as working directory, ``SCISTUDIO_PROJECT_DIR``
    set, and SciStudio's bundled Python first on ``PATH`` — ``pip install``
    lands in the user dependency site SciStudio imports from. The command runs
    with the user's ordinary OS permissions. Output is captured into bounded
    tails. If it is still running after ``wait_seconds``, the result says so
    with a ``job_id``: the job keeps running even if this request ends; use
    get_command_status to follow it and cancel_command to stop it and every
    child process. Commands that invoke the ``scistudio`` CLI are refused — use
    the MCP tools (list_blocks, write_workflow, run_workflow, get_run_status).
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

    from scistudio.engine.runners.process_handle import register_async_process

    cwd = Path(project_dir)
    env = await asyncio.to_thread(build_command_environment, cwd)
    try:
        process = await _spawn(command, cwd, env)
    except OSError as exc:
        return _refused("spawn_failed", f"The command could not be started: {exc.strerror or type(exc).__name__}.")
    job_id = uuid.uuid4().hex[:12]
    handle = register_async_process(
        pid=process.pid,
        block_id=f"command-{job_id}",
        registry=cast("ProcessRegistry", registry),
        workflow_id=COMMAND_REGISTRY_NAMESPACE,
    )
    job = _Job(
        job_id=job_id,
        project_dir=cwd,
        started_at=time.time(),
        registry=registry,
        process=process,
        handle=handle,
        stdout=_BoundedTail(OUTPUT_TAIL_CAP_BYTES),
        stderr=_BoundedTail(OUTPUT_TAIL_CAP_BYTES),
    )
    _JOBS[job_id] = job
    # A task of its own, not part of this request: the request ending does not end the job.
    job.task = asyncio.get_running_loop().create_task(_supervise(job), name=f"mcp-command-{job_id}")
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
    arrived (for example after a browser timeout).
    """
    return ListCommandsResult(
        jobs=[
            CommandSummary(
                job_id=job.job_id,
                state=job.state,
                exit_code=job.exit_code,
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
        Field(description="Seconds to allow a graceful exit before the process tree is killed (0-60)."),
    ] = DEFAULT_CANCEL_GRACE_SECONDS,
) -> CommandStatusResult:
    """Stop a managed command and every process it started.

    Terminates the whole process tree (graceful, then forced after
    ``grace_seconds``) and reports the terminal state. Cancelling a finished
    job just reports it.
    """
    job = _JOBS.get(job_id)
    if job is None:
        return _unknown_job(job_id)
    if job.state != "running":
        result = _report(job)
        result.note = "The command had already finished; nothing to cancel."
        return result
    job.cancel_requested = True
    grace = max(0.0, min(float(grace_seconds), 60.0))
    # terminate_tree sleeps through its grace period; keep it off the event loop.
    await asyncio.to_thread(job.handle.terminate, grace)
    await _wait(job, grace + 5.0)
    result = _report(job)
    if job.state == "running":
        result.note = "Termination was requested but the command has not exited yet; poll get_command_status."
    logger.info("cancel_command job=%s outcome=%s", job.job_id, job.state)
    return result


__all__ = [
    "COMMAND_REGISTRY_NAMESPACE",
    "OUTPUT_TAIL_CAP_BYTES",
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
