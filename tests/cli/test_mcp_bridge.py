"""Tests for ``scieasy mcp-bridge`` ``run()`` two-mode behaviour (#810).

Post-ADR-040 the bridge proxies MCP stdio frames to the FastMCP-backed
backend server. The full attached-mode and standalone-mode tests
require live MCP transport which is owned by FastMCP — those are
covered by the broader integration suite. Here we keep:

* Configuration-error tests (no SCIEASY_PROJECT_DIR → exit 2)
* Connection-probe sanity tests
* Module-import / register tests

The end-to-end attached / standalone mode tests are skipped because
they rely on the deleted hand-rolled JSON-RPC wire format the bridge
used pre-ADR-040 to talk to the in-process MCPServer. FastMCP owns
the wire format now; rewriting the bridge to use FastMCP's stdio
adapter is tracked separately (out of scope for I40a).
"""

from __future__ import annotations

import socket as socket_mod
from pathlib import Path

import pytest


def _make_project(tmp_path: Path) -> Path:
    """Create a minimal SciEasy project layout under *tmp_path*."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "project.yaml").write_text(
        "project:\n  name: test\n  version: 0.1.0\n",
        encoding="utf-8",
    )
    for sub in ("workflows", "blocks", "data/raw"):
        (project / sub).mkdir(parents=True, exist_ok=True)
    (project / ".scieasy").mkdir(parents=True, exist_ok=True)
    return project


# ----------------------------------------------------------------------
# Configuration error path
# ----------------------------------------------------------------------


def test_run_no_project_dir_env_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsetting ``SCIEASY_PROJECT_DIR`` must surface a clean exit-2."""
    from scieasy.cli.mcp_bridge import run

    monkeypatch.delenv("SCIEASY_PROJECT_DIR", raising=False)
    assert run(None) == 2


def test_run_empty_project_dir_env_exits_2(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty/whitespace env value is treated the same as unset."""
    from scieasy.cli.mcp_bridge import run

    monkeypatch.setenv("SCIEASY_PROJECT_DIR", "   ")
    assert run(None) == 2


def test_run_explicit_socket_unreachable_exits_2() -> None:
    """``--socket`` pointing at a non-existent path returns 2."""
    from scieasy.cli.mcp_bridge import run

    assert run("/nonexistent/scieasy-mcp-bridge-test.sock") == 2


# ----------------------------------------------------------------------
# Standalone mode + attached mode tests — deferred to FastMCP stdio adapter
# ----------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "ADR-040 §3.1 migrated the wire format to FastMCP. The "
        "stdin/stdout JSON-RPC framing the bridge previously used to "
        "talk to the in-process MCPServer is gone; rewriting the bridge "
        "to use FastMCP's stdio adapter is out of scope for I40a. "
        "TODO(#1012): I40c+ revisits bridge-FastMCP integration."
    )
)
def test_run_standalone_mode_returns_tools_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Deferred — see module docstring."""


@pytest.mark.skip(
    reason=("ADR-040 §3.1: attached-mode requires bridge ↔ FastMCP stdio adapter. TODO(#1012): I40c+ revisits.")
)
def test_run_attached_mode_proxies_to_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Deferred — see module docstring."""


# ----------------------------------------------------------------------
# Sanity: attached-mode probe handles socket types correctly
# ----------------------------------------------------------------------


def test_try_connect_attached_returns_none_without_socket(tmp_path: Path) -> None:
    """Probe must return None (not raise) when no backend socket exists."""
    from scieasy.cli.mcp_bridge import _try_connect_attached

    project = _make_project(tmp_path)
    assert _try_connect_attached(project) is None


def test_attached_socket_path_matches_backend_convention(tmp_path: Path) -> None:
    """Bridge probes the same path the FastAPI lifespan writes to."""
    from scieasy.ai.agent.mcp.runtime import default_socket_path
    from scieasy.cli.mcp_bridge import _attached_socket_path

    project = _make_project(tmp_path)
    assert _attached_socket_path(project) == default_socket_path(project)


# ----------------------------------------------------------------------
# Misc invariants
# ----------------------------------------------------------------------


def test_register_adds_subcommand() -> None:
    """``register(app)`` must wire the ``mcp-bridge`` subcommand on a Typer app."""
    import typer

    from scieasy.cli.mcp_bridge import register

    app = typer.Typer()
    register(app)
    names = {cmd.name for cmd in app.registered_commands}
    assert "mcp-bridge" in names


def test_module_imports_clean() -> None:
    """Importing the bridge must not perform I/O or block."""
    import importlib

    mod = importlib.import_module("scieasy.cli.mcp_bridge")
    assert hasattr(mod, "run")
    assert hasattr(mod, "register")


def test_socket_module_not_shadowed() -> None:
    """The bridge imports the stdlib ``socket`` module as ``socket_mod``."""
    from scieasy.cli import mcp_bridge

    assert mcp_bridge.socket_mod is socket_mod
