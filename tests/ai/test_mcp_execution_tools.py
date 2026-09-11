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
