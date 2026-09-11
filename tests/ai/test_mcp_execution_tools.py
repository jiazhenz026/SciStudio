"""ADR-055 Spec 2 (#2279) — managed ``run_command`` execution.

Spec §2 User Stories 4 and 5: no-project refusal, bundled-Python environment,
bounded output, API responsiveness during a long command, process-tree
cancellation with zero registry residue, request abort vs job lifetime, and
install-then-import parity. The last test runs the tool through the real app
to show the process lands in the registry the lifespan's ``terminate_all``
runs on.

Commands use plain ``python`` / ``pip`` on purpose: resolving them to
SciStudio's bundled interpreter through the provisioned wrappers is part of
what is under test.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import importlib
import importlib.util
import os
import sys
import time
import uuid
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psutil
import pytest

from scistudio.ai.agent.mcp import _context, tools_execution
from scistudio.engine.runners.process_handle import ProcessRegistry


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _sleep_command(seconds: int) -> str:
    return f'python -c "import time; time.sleep({seconds})"'


def _gone(pid: int) -> bool:
    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def _wait_gone(pids: list[int], timeout: float = 15.0) -> list[int]:
    deadline = time.monotonic() + timeout
    alive = list(pids)
    while alive and time.monotonic() < deadline:
        alive = [pid for pid in alive if not _gone(pid)]
        if alive:
            time.sleep(0.1)
    return alive


@dataclass
class _ExecContext:
    _project_dir: Path | None
    process_registry: ProcessRegistry = field(default_factory=ProcessRegistry)
    block_registry: object = field(default_factory=object)
    type_registry: object = field(default_factory=object)
    active_workflow_id: str | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture(autouse=True)
def _isolated_jobs() -> Iterator[None]:
    tools_execution._JOBS.clear()
    yield
    for job in list(tools_execution._JOBS.values()):
        if job.state == "running":
            with contextlib.suppress(Exception):
                job.handle.kill()
    tools_execution._JOBS.clear()


@pytest.fixture
def user_python(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the shared user dependency tree at a temp dir for the test."""
    plugins = tmp_path / "plugins"
    monkeypatch.setattr("scistudio.desktop.paths.plugins_dir", lambda: plugins)
    return plugins


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "exec project é"  # a space and non-ASCII on purpose
    root.mkdir()
    return root


@pytest.fixture
def ctx(project: Path, user_python: Path) -> Iterator[_ExecContext]:
    context = _ExecContext(_project_dir=project)
    _context.set_context(context)
    yield context
    _context.set_context(None)


def test_run_command_without_a_project_is_refused(user_python: Path) -> None:
    """AS3: explicit absent-context error instead of cwd=None."""
    context = _ExecContext(_project_dir=None)
    _context.set_context(context)
    try:
        result = _run(tools_execution.run_command(command="echo hi"))
    finally:
        _context.set_context(None)
    assert result.status == "refused"
    assert result.refusal is not None and result.refusal.code == "no_active_project"
    assert context.process_registry.active_handles() == []
    assert tools_execution._JOBS == {}


@pytest.mark.parametrize(
    "command",
    [
        "scistudio run workflows/main.yaml",
        "  scistudio",
        "/usr/local/bin/scistudio gui",
        "C:\\Tools\\SciStudio.exe run x",
        "cd blocks && scistudio mcp-bridge",
        "FOO=1 scistudio run x",
        "python -m scistudio run x",
        "echo start; scistudio serve",
    ],
)
def test_scistudio_cli_invocations_are_detected(command: str) -> None:
    assert tools_execution.invokes_scistudio_cli(command)


@pytest.mark.parametrize(
    "command",
    [
        "pip install scistudio-blocks-imaging",
        "python -m scistudio_blocks_demo",
        "echo scistudio",
        "cat scistudio.log",
        "ls scistudio/",
        "python script.py --name scistudio",
    ],
)
def test_ordinary_commands_are_not_mistaken_for_the_cli(command: str) -> None:
    assert not tools_execution.invokes_scistudio_cli(command)


def test_run_command_denies_the_scistudio_cli_with_mcp_alternatives(ctx: _ExecContext) -> None:
    result = _run(tools_execution.run_command(command="scistudio run workflows/main.yaml"))
    assert result.status == "refused"
    assert result.refusal is not None
    assert result.refusal.code == "scistudio_cli_denied"
    assert {"list_blocks", "write_workflow", "run_workflow", "get_run_status"} <= set(result.refusal.use_instead)
    assert ctx.process_registry.active_handles() == []


def test_command_runs_in_the_project_with_the_bundled_python(
    ctx: _ExecContext, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-010: cwd = project, SCISTUDIO_PROJECT_DIR set, python = SciStudio's interpreter."""
    monkeypatch.setenv("SCISTUDIO_ENGINE_IPC_TOKEN", "backend-only-secret")
    command = (
        "python -c \"import os, sys; print(os.getcwd()); print(os.environ['SCISTUDIO_PROJECT_DIR']); "
        "print(sys.executable); print(os.environ.get('SCISTUDIO_ENGINE_IPC_TOKEN', 'absent'))\""
    )
    result = _run(tools_execution.run_command(command=command, wait_seconds=60))
    assert result.status == "ok", result.refusal
    assert result.state == "exited" and result.exit_code == 0, result.stderr_tail
    cwd, project_env, executable, token = result.stdout_tail.strip().splitlines()[-4:]
    assert os.path.samefile(cwd, project)
    assert os.path.samefile(project_env, project)
    assert os.path.samefile(executable, sys.executable)
    assert token == "absent"
    assert ctx.process_registry.active_handles() == []


def test_output_is_bounded_during_capture(ctx: _ExecContext) -> None:
    """FR-011 / SC-002: output 4x the cap keeps only the tail, with accurate totals."""
    cap = tools_execution.OUTPUT_TAIL_CAP_BYTES
    total = 4 * cap
    command = f"python -c \"import sys; sys.stdout.write('x' * {total} + 'END')\""
    result = _run(tools_execution.run_command(command=command, wait_seconds=60))
    assert result.exit_code == 0, result.stderr_tail
    assert result.stdout_bytes == total + 3
    assert result.stdout_truncated is True
    assert result.stdout_tail.endswith("END")
    assert len(result.stdout_tail.encode()) <= cap
    job = tools_execution._JOBS[result.job_id or ""]
    assert len(job.stdout._buffer) <= cap


def test_the_event_loop_stays_responsive_while_a_command_runs(ctx: _ExecContext) -> None:
    """AS2: a sibling task keeps running on time while run_command waits."""

    async def scenario() -> tuple[list[float], Any]:
        caller = asyncio.create_task(tools_execution.run_command(command=_sleep_command(30), wait_seconds=2.0))
        lags: list[float] = []
        for _ in range(20):
            start = time.monotonic()
            await asyncio.sleep(0.05)
            lags.append(time.monotonic() - start - 0.05)
        result = await caller
        await tools_execution.cancel_command(job_id=result.job_id, grace_seconds=1)
        return lags, result

    lags, result = _run(scenario())
    assert result.state == "running"  # returned at wait_seconds, not at command end
    assert max(lags) < 0.5, lags


_TREE_SCRIPT = """\
import os, subprocess, sys, time
depth = int(sys.argv[1]) if len(sys.argv) > 1 else 0
with open("pids.txt", "a", encoding="utf-8") as fh:
    fh.write(f"{os.getpid()}\\n")
if depth < 2:
    subprocess.Popen([sys.executable, "tree.py", str(depth + 1)])
time.sleep(120)
"""


def test_cancel_terminates_the_process_tree_and_clears_the_registry(ctx: _ExecContext, project: Path) -> None:
    """AS1 / SC-004: zero live descendants and zero registry residue after cancel."""
    (project / "tree.py").write_text(_TREE_SCRIPT, encoding="utf-8")
    pid_file = project / "pids.txt"

    async def scenario() -> tuple[Any, Any, list[int]]:
        started = await tools_execution.run_command(command="python tree.py", wait_seconds=0)
        assert started.state == "running"
        assert [h.pid for h in ctx.process_registry.active_handles()] == [started.pid]
        deadline = time.monotonic() + 30
        pids: list[int] = []
        while time.monotonic() < deadline:
            if pid_file.exists():
                pids = [int(line) for line in pid_file.read_text(encoding="utf-8").split()]
                if len(pids) >= 3:
                    break
            await asyncio.sleep(0.1)
        assert len(pids) == 3, pids
        cancelled = await tools_execution.cancel_command(job_id=started.job_id, grace_seconds=2)
        return started, cancelled, pids

    started, cancelled, pids = _run(scenario())
    assert cancelled.state == "cancelled"
    assert cancelled.running is False
    assert ctx.process_registry.active_handles() == []
    assert _wait_gone([started.pid, *pids]) == []


def test_request_abort_does_not_kill_the_job(ctx: _ExecContext) -> None:
    """US5 AS1/AS2: the caller going away leaves the job observable and cancellable."""

    async def scenario() -> tuple[Any, Any]:
        caller = asyncio.create_task(tools_execution.run_command(command=_sleep_command(60), wait_seconds=60))
        deadline = time.monotonic() + 20
        while not tools_execution._JOBS and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.3)
        caller.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await caller

        listed = await tools_execution.list_commands()
        assert [job.state for job in listed.jobs] == ["running"]
        status = await tools_execution.get_command_status(job_id=listed.jobs[0].job_id, wait_seconds=0.5)
        assert status.running and status.pid is not None and not _gone(status.pid)
        cancelled = await tools_execution.cancel_command(job_id=status.job_id, grace_seconds=1)
        return status, cancelled

    status, cancelled = _run(scenario())
    assert cancelled.state == "cancelled"
    assert ctx.process_registry.active_handles() == []
    assert _wait_gone([status.pid]) == []


def test_concurrent_commands_are_independent_registry_entries(ctx: _ExecContext) -> None:
    async def scenario() -> tuple[Any, Any, int]:
        first = await tools_execution.run_command(command=_sleep_command(30), wait_seconds=0)
        second = await tools_execution.run_command(command=_sleep_command(30), wait_seconds=0)
        live = len(ctx.process_registry.active_handles())
        await tools_execution.cancel_command(job_id=first.job_id, grace_seconds=1)
        still = await tools_execution.get_command_status(job_id=second.job_id)
        assert still.running
        await tools_execution.cancel_command(job_id=second.job_id, grace_seconds=1)
        return first, second, live

    first, second, live = _run(scenario())
    assert first.job_id != second.job_id
    assert live == 2
    assert ctx.process_registry.active_handles() == []


def test_unknown_job_explains_memory_only_state(ctx: _ExecContext) -> None:
    result = _run(tools_execution.get_command_status(job_id="nope"))
    assert result.status == "refused"
    assert result.refusal is not None and result.refusal.code == "unknown_job"
    assert "memory" in result.refusal.message and "restart" in result.refusal.message


def test_install_location_is_the_one_scistudio_imports_from(ctx: _ExecContext, user_python: Path) -> None:
    """AS4 / SC-005 (stdlib form): what a command installs into PIP_TARGET, SciStudio imports.

    Always runs, with or without pip: the command writes a module to the
    directory its environment names as pip's install target, and both the
    command's own ``python`` and SciStudio's import path resolve that file.
    """
    from scistudio.desktop.paths import prepended_sys_paths, user_python_import_roots, user_python_site_dir

    name = f"scistudio_env_probe_{uuid.uuid4().hex[:8]}"
    write = (
        "python -c \"import os, pathlib; target = pathlib.Path(os.environ['PIP_TARGET']); "
        f"target.mkdir(parents=True, exist_ok=True); (target / '{name}.py').write_text('VALUE = 7')\""
    )
    written = _run(tools_execution.run_command(command=write, wait_seconds=60))
    assert written.exit_code == 0, written.stderr_tail
    assert (user_python_site_dir() / f"{name}.py").is_file()

    imported = _run(
        tools_execution.run_command(
            command=f'python -c "import {name} as m; print(m.VALUE); print(m.__file__)"', wait_seconds=60
        )
    )
    assert imported.exit_code == 0, imported.stderr_tail
    value, module_file = imported.stdout_tail.strip().splitlines()[-2:]
    assert value == "7"

    try:
        with prepended_sys_paths(user_python_import_roots()):
            module = importlib.import_module(name)
            assert module.VALUE == 7
            assert os.path.samefile(module.__file__ or "", module_file)
    finally:
        sys.modules.pop(name, None)


def _probe_wheel(directory: Path, name: str) -> Path:
    """A minimal pure-Python wheel for an offline ``pip install``."""
    dist_info = f"{name}-0.1.dist-info"
    files = {
        f"{name}/__init__.py": b"VALUE = 42\n",
        f"{dist_info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1\n".encode(),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: scistudio-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record_lines = []
    for path, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        record_lines.append(f"{path},sha256={digest},{len(data)}")
    record_lines.append(f"{dist_info}/RECORD,,")
    wheel = directory / f"{name}-0.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path, data in files.items():
            archive.writestr(path, data)
        archive.writestr(f"{dist_info}/RECORD", "\n".join(record_lines) + "\n")
    return wheel


@pytest.mark.skipif(
    importlib.util.find_spec("pip") is None,
    reason=(
        "pip is not installed in this interpreter (uv-managed venvs omit it), so an offline wheel install "
        "cannot run here; the stdlib parity test above covers the environment contract and CI's "
        "setup-python interpreter ships pip"
    ),
)
@pytest.mark.timeout(300)  # an offline pip install can exceed the suite's 60 s default on a cold runner
def test_pip_install_through_run_command_is_importable_by_scistudio(
    ctx: _ExecContext, user_python: Path, tmp_path: Path
) -> None:
    """AS4 / SC-005: ``pip install`` via run_command, then a SciStudio-side import."""
    from scistudio.desktop.paths import prepended_sys_paths, user_python_import_roots

    name = f"scistudio_wheel_probe_{uuid.uuid4().hex[:8]}"
    wheel = _probe_wheel(tmp_path, name)
    installed = _run(
        tools_execution.run_command(
            command=f'pip install --no-index --no-deps --disable-pip-version-check "{wheel}"', wait_seconds=240
        )
    )
    assert installed.exit_code == 0, installed.stdout_tail + installed.stderr_tail
    try:
        with prepended_sys_paths(user_python_import_roots()):
            module = importlib.import_module(name)
            assert module.VALUE == 42
    finally:
        sys.modules.pop(name, None)


def test_run_command_lands_in_the_registry_the_lifespan_terminates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, user_python: Path
) -> None:
    """#2279 decision 6: app.state.registry, so backend shutdown's terminate_all stops the command."""
    from fastapi.testclient import TestClient

    from scistudio.api import runtime as runtime_module
    from scistudio.api.app import create_app

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    parent = tmp_path / "projects"
    parent.mkdir()

    with TestClient(create_app()) as client:
        created = client.post("/api/projects/", json={"name": "Exec", "description": "", "path": str(parent)})
        assert created.status_code == 200, created.text
        app_state = client.app.state  # type: ignore[attr-defined]
        response = client.post(
            "/api/webmcp/call",
            headers={"X-SciStudio-WebMCP-Token": app_state.webmcp_session_token},
            json={
                "name": "run_command",
                "arguments": {"command": _sleep_command(120), "wait_seconds": 0},
                "projectId": app_state.runtime.active_project.id,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()["structuredContent"]
        assert body["state"] == "running", body
        pid = body["pid"]
        command_handles = [
            handle
            for handle in app_state.registry.active_handles()
            if handle.workflow_id == tools_execution.COMMAND_REGISTRY_NAMESPACE
        ]
        assert [handle.pid for handle in command_handles] == [pid]
        # Not the workflow runner's registry, which the lifespan does not terminate.
        assert app_state.runtime.process_registry.active_handles() == []
        assert not _gone(pid)

    # Leaving the client ran the lifespan shutdown: terminate_all stopped the tree.
    assert _wait_gone([pid]) == []


# ---------------------------------------------------------------------------
# A1-fix1 (#2279 audits AU3 P1-2 / P2-2 / P2-5, AU4 P1-1): the whole job.
# ---------------------------------------------------------------------------

# Starts a long-lived child that inherits (and so holds) stdout/stderr, records its
# PID, and exits at once: `cmd &`, `start /b`, or a launcher that detaches.
_LAUNCHER_SCRIPT = """\
import subprocess, sys
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(120)"],
    stdout=sys.stdout, stderr=sys.stderr, close_fds=False,
)
with open("bg.pid", "w", encoding="utf-8") as fh:
    fh.write(str(child.pid))
print("launcher done", flush=True)
"""

# Starts a long-lived grandchild that holds no pipes, records its PID, and exits.
_SPAWNER_SCRIPT = """\
import subprocess, sys
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(120)"],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
with open("orphan.pid", "w", encoding="utf-8") as fh:
    fh.write(str(child.pid))
"""


async def _pid_from(path: Path, timeout: float = 30.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return int(path.read_text(encoding="utf-8"))
        await asyncio.sleep(0.1)
    raise AssertionError(f"{path.name} was never written")


def test_background_child_holding_the_pipes_does_not_keep_the_job_running(ctx: _ExecContext, project: Path) -> None:
    """AU4 P1-1 / AU3 P2-2: exit is detected apart from pipe EOF; drain is bounded; cancel stops the child."""
    (project / "launcher.py").write_text(_LAUNCHER_SCRIPT, encoding="utf-8")

    async def scenario() -> tuple[Any, float, int, list[str], Any]:
        started = time.monotonic()
        result = await tools_execution.run_command(command="python launcher.py", wait_seconds=30)
        elapsed = time.monotonic() - started
        background_pid = await _pid_from(project / "bg.pid")
        registered = [handle.block_id for handle in ctx.process_registry.active_handles()]
        cancelled = await tools_execution.cancel_command(job_id=result.job_id, grace_seconds=1)
        return result, elapsed, background_pid, registered, cancelled

    result, elapsed, background_pid, registered, cancelled = _run(scenario())
    assert result.state == "exited" and result.exit_code == 0, result
    assert elapsed < 15, elapsed
    assert "launcher done" in result.stdout_tail
    assert result.output_incomplete is True
    assert result.background_processes_running is True
    assert result.note is not None and "may be incomplete" in result.note
    # Still owned while the background child lives, so cancel and shutdown can reach it.
    assert registered == [f"command-{result.job_id}"]
    assert cancelled.background_processes_running is False
    assert _wait_gone([background_pid]) == []
    assert ctx.process_registry.active_handles() == []


def test_cancel_reaches_a_grandchild_whose_parent_already_exited(ctx: _ExecContext, project: Path) -> None:
    """AU3 P1-2: Windows does not reparent orphans; the Job Object (POSIX: process group) still covers them."""
    (project / "spawner.py").write_text(_SPAWNER_SCRIPT, encoding="utf-8")

    async def scenario() -> tuple[Any, Any, int]:
        started = await tools_execution.run_command(
            command='python spawner.py && python -c "import time; time.sleep(90)"', wait_seconds=0
        )
        orphan = await _pid_from(project / "orphan.pid")
        await asyncio.sleep(0.5)  # the spawner has exited; its child is now an orphan
        cancelled = await tools_execution.cancel_command(job_id=started.job_id, grace_seconds=1)
        return started, cancelled, orphan

    started, cancelled, orphan = _run(scenario())
    assert cancelled.state == "cancelled", cancelled
    assert _wait_gone([orphan, started.pid]) == []
    assert ctx.process_registry.active_handles() == []


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell background syntax; Windows runs `start /b` below")
def test_posix_background_job_is_reported_exited_and_cancellable(ctx: _ExecContext, project: Path) -> None:
    async def scenario() -> tuple[Any, Any]:
        result = await tools_execution.run_command(
            command='python -c "import time; time.sleep(120)" & echo started', wait_seconds=30
        )
        cancelled = await tools_execution.cancel_command(job_id=result.job_id, grace_seconds=1)
        return result, cancelled

    result, cancelled = _run(scenario())
    assert result.state == "exited" and result.background_processes_running is True
    assert cancelled.background_processes_running is False
    assert ctx.process_registry.active_handles() == []


@pytest.mark.skipif(sys.platform != "win32", reason="`start /b` is the Windows command processor's background form")
def test_windows_start_b_job_is_reported_exited_and_cancellable(ctx: _ExecContext, project: Path) -> None:
    async def scenario() -> tuple[Any, Any]:
        result = await tools_execution.run_command(
            command='start /b python -c "import time; time.sleep(120)"', wait_seconds=30
        )
        cancelled = await tools_execution.cancel_command(job_id=result.job_id, grace_seconds=1)
        return result, cancelled

    result, cancelled = _run(scenario())
    assert result.state == "exited" and result.background_processes_running is True
    assert cancelled.background_processes_running is False
    assert ctx.process_registry.active_handles() == []


def test_backend_shutdown_stops_background_processes_of_an_exited_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, user_python: Path
) -> None:
    """AU4 P1-1: terminate_all still reaches the job after its shell has exited."""
    from fastapi.testclient import TestClient

    from scistudio.api import runtime as runtime_module
    from scistudio.api.app import create_app

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    parent = tmp_path / "projects"
    parent.mkdir()

    with TestClient(create_app()) as client:
        created = client.post("/api/projects/", json={"name": "Leftovers", "description": "", "path": str(parent)})
        assert created.status_code == 200, created.text
        project_root = Path(created.json()["path"])
        (project_root / "launcher.py").write_text(_LAUNCHER_SCRIPT, encoding="utf-8")
        app_state = client.app.state  # type: ignore[attr-defined]
        response = client.post(
            "/api/webmcp/call",
            headers={"X-SciStudio-WebMCP-Token": app_state.webmcp_session_token},
            json={
                "name": "run_command",
                "arguments": {"command": "python launcher.py", "wait_seconds": 30},
                "projectId": app_state.runtime.active_project.id,
            },
        )
        body = response.json()["structuredContent"]
        assert body["state"] == "exited" and body["background_processes_running"] is True, body
        background_pid = int((project_root / "bg.pid").read_text(encoding="utf-8"))
        assert [
            handle
            for handle in app_state.registry.active_handles()
            if handle.workflow_id == tools_execution.COMMAND_REGISTRY_NAMESPACE
        ]
        assert not _gone(background_pid)

    assert _wait_gone([background_pid]) == []


def test_http_request_abort_through_the_bridge_leaves_the_job_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, user_python: Path
) -> None:
    """AU3 P2-5: a real HTTP client gives up mid-call; the job keeps running and stays manageable."""
    import threading

    import httpx
    import uvicorn

    from scistudio.api import runtime as runtime_module
    from scistudio.api.app import create_app

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    parent = tmp_path / "projects"
    parent.mkdir()
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    headers = {"X-SciStudio-WebMCP-Token": app.state.webmcp_session_token}
    pid = None
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30.0) as http:
            created = http.post("/api/projects/", json={"name": "Abort", "description": "", "path": str(parent)})
            assert created.status_code == 200, created.text
            project_id = app.state.runtime.active_project.id

            def call(name: str, **arguments: Any) -> dict[str, Any]:
                reply = http.post(
                    "/api/webmcp/call",
                    headers=headers,
                    json={"name": name, "arguments": arguments, "projectId": project_id},
                )
                assert reply.status_code == 200, reply.text
                return reply.json()["structuredContent"]  # type: ignore[no-any-return]

            with pytest.raises(httpx.ReadTimeout):
                http.post(
                    "/api/webmcp/call",
                    headers=headers,
                    json={
                        "name": "run_command",
                        "arguments": {"command": _sleep_command(120), "wait_seconds": 60, "label": "abort me"},
                        "projectId": project_id,
                    },
                    timeout=3.0,
                )
            jobs = call("list_commands")["jobs"]
            assert [(job["label"], job["state"]) for job in jobs] == [("abort me", "running")]
            status = call("get_command_status", job_id=jobs[0]["job_id"], wait_seconds=1)
            assert status["running"] is True
            pid = status["pid"]
            assert not _gone(pid)
            cancelled = call("cancel_command", job_id=jobs[0]["job_id"], grace_seconds=1)
            assert cancelled["state"] == "cancelled"
    finally:
        server.should_exit = True
        thread.join(timeout=30)
    assert pid is not None and _wait_gone([pid]) == []


@pytest.mark.parametrize(
    "command",
    [
        '"scistudio" run x',
        "sh -c 'scistudio run x'",
        'bash -c "cd blocks; scistudio gui"',
        "cmd /c scistudio run x",
        'start "" /b scistudio gui',
        "nice -n 5 scistudio run x",
        "timeout 10 scistudio run x",
        "env -i scistudio run x",
        "xargs scistudio run",
        "python -m scistudio.cli.main run x",
        'python -c "from scistudio.cli.main import app; app()"',
    ],
)
def test_wrapped_and_launched_cli_invocations_are_detected(command: str) -> None:
    """AU3 P3-1: launchers, shell wrappers, and module forms are caught too."""
    assert tools_execution.invokes_scistudio_cli(command)


@pytest.mark.parametrize(
    "command",
    ["bash build.sh", 'python -c "import scistudio_blocks_x"', "nice -n 5 python train.py", 'sh -c "echo scistudio"'],
)
def test_wrappers_around_ordinary_commands_are_allowed(command: str) -> None:
    assert not tools_execution.invokes_scistudio_cli(command)


def test_list_commands_tells_jobs_apart_by_label_and_preview(ctx: _ExecContext) -> None:
    """AU3 P3-10."""

    async def scenario() -> tuple[Any, Any, Any]:
        labelled = await tools_execution.run_command(command=_sleep_command(30), wait_seconds=0, label="training run")
        plain = await tools_execution.run_command(command='python -c "print(1)"', wait_seconds=30)
        listed = await tools_execution.list_commands()
        await tools_execution.cancel_command(job_id=labelled.job_id, grace_seconds=1)
        return labelled, plain, listed

    labelled, plain, listed = _run(scenario())
    by_id = {job.job_id: job for job in listed.jobs}
    assert by_id[labelled.job_id].label == "training run"
    assert by_id[plain.job_id].label is None
    assert "print(1)" in by_id[plain.job_id].command_preview


def test_background_tasks_do_not_inherit_the_bridge_marker() -> None:
    """AU3 P3-7: a supervisor spawned inside a bridge call does not look like a bridge call."""
    from scistudio.ai.agent.mcp._context import bridge_call_scope, invoked_through_bridge, outside_bridge_context

    with bridge_call_scope():
        assert invoked_through_bridge() is True
        detached = outside_bridge_context()
    assert detached.run(invoked_through_bridge) is False


def test_command_failures_reach_the_host_as_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, user_python: Path
) -> None:
    """Owner decision 2026-09-11 (AU4 P3-5): non-zero exit, CLI denial, and a cancel that did not stop."""
    from fastapi.testclient import TestClient

    from scistudio.api import runtime as runtime_module
    from scistudio.api.app import create_app
    from scistudio.engine.runners.exit_info import ProcessExitInfo

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    parent = tmp_path / "projects"
    parent.mkdir()

    with TestClient(create_app()) as client:
        assert (
            client.post("/api/projects/", json={"name": "Flags", "description": "", "path": str(parent)}).status_code
            == 200
        )
        app_state = client.app.state  # type: ignore[attr-defined]

        def call(name: str, **arguments: Any) -> tuple[bool, dict[str, Any]]:
            reply = client.post(
                "/api/webmcp/call",
                headers={"X-SciStudio-WebMCP-Token": app_state.webmcp_session_token},
                json={"name": name, "arguments": arguments, "projectId": app_state.runtime.active_project.id},
            )
            body = reply.json()
            return bool(body["isError"]), body["structuredContent"]

        is_error, ok = call("run_command", command='python -c "print(1)"', wait_seconds=30)
        assert is_error is False and ok["exit_code"] == 0

        is_error, failed = call("run_command", command='python -c "import sys; sys.exit(3)"', wait_seconds=30)
        assert is_error is True
        assert failed["state"] == "exited" and failed["exit_code"] == 3 and failed["status"] == "ok"

        is_error, denied = call("run_command", command="scistudio run workflows/main.yaml")
        assert is_error is True and denied["refusal"]["code"] == "scistudio_cli_denied"

        _running_error, running = call("run_command", command=_sleep_command(60), wait_seconds=0)
        with monkeypatch.context() as patched:
            patched.setattr(
                tools_execution._CommandHandle,
                "terminate",
                lambda self, grace_period_sec=5.0: ProcessExitInfo(exit_code=None, platform_detail="ignored"),
            )
            is_error, unstopped = call("cancel_command", job_id=running["job_id"], grace_seconds=0)
        assert is_error is True and unstopped["running"] is True

        is_error, stopped = call("cancel_command", job_id=running["job_id"], grace_seconds=1)
        assert is_error is False and stopped["state"] == "cancelled"
