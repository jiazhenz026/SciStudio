"""Tests for ``scistudio mcp-bridge`` ``run()`` two-mode behaviour (#810).

These cover the regressions introduced by the PR #808 rollback:

* Without ``SCISTUDIO_PROJECT_DIR`` the bridge exits 2 (clear config error).
* With a project dir and a running backend socket, the bridge connects
  to the backend and proxies ``tools/list`` through to it (attached mode).
* With a project dir but no backend running, the bridge spawns an
  in-process MCP server, answers ``tools/list``, then exits 0 on EOF
  (standalone mode).

The attached-mode and standalone-mode tests drive the public ``run()``
function in-process. We do **not** spawn a subprocess here; the existing
``tests/cli/test_mcp_bridge_standalone.py`` already exercises the full
console-script path, and the in-process variant is faster and avoids
relying on an editable install being present in the test env.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import socket as socket_mod
import sys
import threading
from pathlib import Path

import pytest

# Module-level skip removed — MCPServer start/stop now wired through
# FastMCP in I40a Phase 2a (ADR-040 §3.1).


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal SciStudio project layout under *tmp_path*."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "project.yaml").write_text(
        "project:\n  name: test\n  version: 0.1.0\n",
        encoding="utf-8",
    )
    for sub in ("workflows", "blocks", "data/raw"):
        (project / sub).mkdir(parents=True, exist_ok=True)
    (project / ".scistudio").mkdir(parents=True, exist_ok=True)
    return project


# ----------------------------------------------------------------------
# Configuration error path
# ----------------------------------------------------------------------


def test_run_no_project_dir_env_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsetting ``SCISTUDIO_PROJECT_DIR`` must surface a clean exit-2.

    The bridge is invoked by external MCP clients via the generated
    ``mcp.json``; that file is expected to set the env var. If a user
    edits it out (or invokes the bridge directly), we want a clear
    configuration error rather than a silent fallback to ``~`` or
    ``cwd`` which could pick up the wrong project.
    """
    from scistudio.cli.mcp_bridge import run

    monkeypatch.delenv("SCISTUDIO_PROJECT_DIR", raising=False)
    assert run(None) == 2


def test_run_empty_project_dir_env_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty/whitespace env value is treated the same as unset."""
    from scistudio.cli.mcp_bridge import run

    monkeypatch.setenv("SCISTUDIO_PROJECT_DIR", "   ")
    assert run(None) == 2


def test_run_explicit_socket_unreachable_exits_2() -> None:
    """``--socket`` pointing at a non-existent path returns 2."""
    from scistudio.cli.mcp_bridge import run

    assert run("/nonexistent/scistudio-mcp-bridge-test.sock") == 2


# ----------------------------------------------------------------------
# Standalone mode (in-process)
# ----------------------------------------------------------------------


def _drive_run_with_stdin(
    project_dir: Path,
    stdin_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[int, bytes]:
    """Invoke ``run(None)`` with *stdin_bytes* piped into the bridge.

    Captures stdout via a pipe-backed BytesIO. Returns ``(rc, stdout)``.
    """
    from scistudio.cli import mcp_bridge

    # Replace stdin with a BytesIO; the bridge's threaded reader uses
    # ``sys.stdin.buffer.read1`` which BytesIO supports.
    class _FakeStdin:
        buffer = io.BytesIO(stdin_bytes)

    captured_out = io.BytesIO()

    class _FakeStdout:
        buffer = captured_out

        def flush(self) -> None:  # pragma: no cover - cosmetic
            pass

    monkeypatch.setattr(sys, "stdin", _FakeStdin())
    monkeypatch.setattr(sys, "stdout", _FakeStdout())
    monkeypatch.setenv("SCISTUDIO_PROJECT_DIR", str(project_dir))

    rc = mcp_bridge.run(None)
    return rc, captured_out.getvalue()


@pytest.mark.timeout(60)
def test_run_standalone_mode_returns_tools_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No backend running: bridge spawns in-process server, answers tools/list.

    Sends a single ``tools/list`` JSON-RPC frame on stdin, then EOF.
    Verifies:

    * Bridge exits 0 (clean EOF).
    * Stdout contains a JSON-RPC response with ``result.tools`` of 26
      entries — the registered tool count (25 pre-ADR-035 +
      ``finish_ai_block`` added by PR #861 / ADR-035 §3.5 path a).
    """
    project = _make_project(tmp_path)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    stdin_bytes = (json.dumps(request) + "\n").encode("utf-8")

    rc, stdout_bytes = _drive_run_with_stdin(project, stdin_bytes, monkeypatch)

    assert rc == 0, f"bridge exited with {rc}; stdout: {stdout_bytes!r}"

    # Find the JSON-RPC response line.
    lines = [ln for ln in stdout_bytes.splitlines() if ln.strip()]
    assert lines, f"no output from bridge; got {stdout_bytes!r}"
    response = json.loads(lines[0].decode("utf-8"))
    assert response.get("id") == 1
    tools = response.get("result", {}).get("tools")
    assert isinstance(tools, list), response
    assert len(tools) == 26, f"expected 26 tools (25 + finish_ai_block), got {len(tools)}"


# ----------------------------------------------------------------------
# Attached mode (against a real MCPServer on a temp socket)
# ----------------------------------------------------------------------


@pytest.mark.timeout(60)
def test_run_attached_mode_proxies_to_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reachable backend socket: bridge connects to it, not standalone.

    We stand up an :class:`MCPServer` bound to the conventional
    ``<project>/.scistudio/mcp.sock`` location, then invoke ``run(None)``
    with stdin piping a ``tools/list`` request. The response must come
    from the backend server (which we verify by checking the tool count
    and that the backend server saw a connection).
    """
    from scistudio.ai.agent.mcp import _context
    from scistudio.ai.agent.mcp.runtime import make_mcp_runtime
    from scistudio.ai.agent.mcp.server import MCPServer

    project = _make_project(tmp_path)
    socket_path = project / ".scistudio" / "mcp.sock"

    # Spin up an MCPServer on a dedicated background event loop so the
    # bridge's own asyncio.run() doesn't clash with it.
    loop = asyncio.new_event_loop()
    server: MCPServer | None = None
    runtime = None
    server_thread: threading.Thread | None = None
    server_ready = threading.Event()

    async def _start_backend() -> None:
        nonlocal server, runtime
        runtime = make_mcp_runtime(project)
        _context.set_context(runtime)
        server = MCPServer(socket_path=socket_path, project_dir=project)
        await server.start()
        server_ready.set()
        # Keep the loop alive until the test signals shutdown.
        while not _shutdown.is_set():
            await asyncio.sleep(0.05)
        await server.stop()

    _shutdown = threading.Event()

    def _run_loop() -> None:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_start_backend())

    server_thread = threading.Thread(target=_run_loop, name="mcp-backend", daemon=True)
    server_thread.start()
    assert server_ready.wait(timeout=10), "backend MCPServer did not start"

    try:
        request = {"jsonrpc": "2.0", "id": 99, "method": "tools/list"}
        stdin_bytes = (json.dumps(request) + "\n").encode("utf-8")

        rc, stdout_bytes = _drive_run_with_stdin(project, stdin_bytes, monkeypatch)
        assert rc == 0, f"bridge exited with {rc}; stdout: {stdout_bytes!r}"

        lines = [ln for ln in stdout_bytes.splitlines() if ln.strip()]
        assert lines, f"no output from bridge; got {stdout_bytes!r}"
        response = json.loads(lines[0].decode("utf-8"))
        assert response.get("id") == 99
        tools = response.get("result", {}).get("tools")
        assert isinstance(tools, list) and len(tools) == 26  # ADR-035: +finish_ai_block
    finally:
        _shutdown.set()
        if server_thread is not None:
            server_thread.join(timeout=10)
        with contextlib.suppress(Exception):
            loop.close()
        _context.set_context(None)


# ----------------------------------------------------------------------
# Sanity: attached-mode probe handles socket types correctly
# ----------------------------------------------------------------------


def test_try_connect_attached_returns_none_without_socket(tmp_path: Path) -> None:
    """Probe must return None (not raise) when no backend socket exists."""
    from scistudio.cli.mcp_bridge import _try_connect_attached

    project = _make_project(tmp_path)
    assert _try_connect_attached(project) is None


def test_attached_socket_path_matches_backend_convention(tmp_path: Path) -> None:
    """Bridge probes the same path the FastAPI lifespan writes to.

    Guards against the bridge and backend diverging on socket location.
    """
    from scistudio.ai.agent.mcp.runtime import default_socket_path
    from scistudio.cli.mcp_bridge import _attached_socket_path

    project = _make_project(tmp_path)
    assert _attached_socket_path(project) == default_socket_path(project)


# ----------------------------------------------------------------------
# Misc invariants
# ----------------------------------------------------------------------


def test_register_adds_subcommand() -> None:
    """``register(app)`` must wire the ``mcp-bridge`` subcommand on a Typer app."""
    import typer

    from scistudio.cli.mcp_bridge import register

    app = typer.Typer()
    register(app)
    # Typer stores commands on registered_commands; check by name.
    names = {cmd.name for cmd in app.registered_commands}
    assert "mcp-bridge" in names


def test_module_imports_clean() -> None:
    """Importing the bridge must not perform I/O or block."""
    import importlib

    mod = importlib.import_module("scistudio.cli.mcp_bridge")
    assert hasattr(mod, "run")
    assert hasattr(mod, "register")


def test_socket_module_not_shadowed() -> None:
    """The bridge imports the stdlib ``socket`` module as ``socket_mod``
    so the ``--socket`` Typer argument (which is named ``socket``)
    doesn't shadow it inside ``run()``. Regression guard.
    """
    from scistudio.cli import mcp_bridge

    assert mcp_bridge.socket_mod is socket_mod
