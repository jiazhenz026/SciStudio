"""Regression tests for project-scoped MCP transport publication."""

from __future__ import annotations

from pathlib import Path


def _make_project(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    (project / "project.yaml").write_text(
        "project:\n  name: test\n  version: 0.1.0\n",
        encoding="utf-8",
    )
    return project


def test_open_project_publishes_posix_mcp_socket_pointer(tmp_path: Path) -> None:
    """A backend socket bound before project-open is discoverable afterward."""
    from scistudio.api.runtime import ApiRuntime

    runtime = ApiRuntime()
    backend_socket = tmp_path / "backend.sock"
    runtime.set_mcp_port(None, socket_path=backend_socket)

    project = _make_project(tmp_path)
    runtime.open_project(str(project))

    pointer = project / ".scistudio" / "mcp.sock.path"
    assert pointer.read_text(encoding="utf-8") == str(backend_socket)
    assert not (project / ".scistudio" / "mcp.sock.port").exists()


def test_open_project_publishes_tcp_mcp_port(tmp_path: Path) -> None:
    """TCP transport publication remains the preferred Windows path."""
    from scistudio.api.runtime import ApiRuntime

    runtime = ApiRuntime()
    runtime.set_mcp_port(49152, socket_path=tmp_path / "backend.sock")

    project = _make_project(tmp_path)
    runtime.open_project(str(project))

    port_file = project / ".scistudio" / "mcp.sock.port"
    assert port_file.read_text(encoding="utf-8") == "49152"
    assert not (project / ".scistudio" / "mcp.sock.path").exists()
