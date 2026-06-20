"""Regression tests for project-scoped MCP transport publication."""

from __future__ import annotations

import socket
from pathlib import Path

from fastapi.testclient import TestClient


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


def test_open_project_clears_pointer_for_conventional_posix_socket(tmp_path: Path) -> None:
    """Project-local POSIX sockets do not need an extra pointer file."""
    from scistudio.api.runtime import ApiRuntime

    runtime = ApiRuntime()
    project = _make_project(tmp_path)
    runtime.set_mcp_port(None, socket_path=project / ".scistudio" / "mcp.sock")

    runtime.open_project(str(project))

    assert not (project / ".scistudio" / "mcp.sock.path").exists()


def _mcp_connect_path(project: Path) -> Path:
    socket_path = project / ".scistudio" / "mcp.sock"
    pointer_path = project / ".scistudio" / "mcp.sock.path"
    if pointer_path.exists():
        return Path(pointer_path.read_text(encoding="utf-8").strip())
    return socket_path


def test_project_open_route_starts_project_mcp_socket(client: TestClient, project_parent: Path) -> None:
    """Packaged desktop opens a project after startup; MCP must bind there."""
    response = client.post(
        "/api/projects/",
        json={"name": "MCP Project", "description": "", "path": str(project_parent)},
    )
    assert response.status_code == 200
    project = Path(response.json()["path"])
    connect_path = _mcp_connect_path(project)

    assert connect_path.exists()

    client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client_sock.settimeout(2.0)
        client_sock.connect(str(connect_path))
    finally:
        client_sock.close()


def test_project_open_route_rebinds_missing_project_mcp_socket(client: TestClient, project_parent: Path) -> None:
    """If a stale process unlinks the socket path, reopening repairs it."""
    response = client.post(
        "/api/projects/",
        json={"name": "MCP Rebind", "description": "", "path": str(project_parent)},
    )
    assert response.status_code == 200
    payload = response.json()
    project = Path(payload["path"])
    original_connect_path = _mcp_connect_path(project)
    original_connect_path.unlink()

    reopened = client.get(f"/api/projects/{payload['id']}")

    assert reopened.status_code == 200
    assert _mcp_connect_path(project).exists()
