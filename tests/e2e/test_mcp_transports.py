"""The stdio MCP processes an agent launches in front of a running backend (#2398).

``test_mcp_tools.py`` exercises every tool over the WebMCP HTTP bridge. This
module checks the two stdio front doors ``scistudio`` ships, against the same
running ``scistudio serve``:

- ``scistudio mcp-bridge``, which the provisioned agent configs launch with
  ``SCISTUDIO_PROJECT_DIR``. With the backend running it attaches to the
  project's MCP socket and so acts on the backend's own state; with no backend
  it starts a standalone server for the project.
- ``scistudio webmcp-adapter``, which AI apps launch to reach the WebMCP bridge
  over stdio. It keeps no tool list of its own and passes results through.
"""

from __future__ import annotations

import shutil
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e.harness import Backend, Project, ServeProcess, build_tutorial_project, isolated_env, requires_e2e
from tests.e2e.mcp_clients import TOKEN_HEADER, StdioMcpClient, read_loopback_token, text_payload
from tests.e2e.test_tutorial_workflows import WELCOME_WORKFLOW

pytestmark = [requires_e2e, pytest.mark.timeout(300)]

METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

SMALL_WORKFLOW = """workflow:
  id: bridged
  version: "1.0.0"
  description: Load the plate and save a copy, written through the local bridge.
  nodes:
    - id: load
      block_type: load_data
      config:
        core_type: DataFrame
        path: data/raw/cell_viability_fluorescence.csv
    - id: save
      block_type: save_data
      config:
        core_type: DataFrame
        path: data/processed
        filename: bridged.csv
  edges:
    - source: "load:data"
      target: "save:data"
"""


@pytest.fixture(scope="module")
def backend(serve: ServeProcess) -> Iterator[Backend]:
    client = Backend(serve.base_url)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="module")
def project(backend: Backend, tmp_path_factory: pytest.TempPathFactory) -> Project:
    built = build_tutorial_project(
        backend,
        tmp_path_factory.mktemp("mcp-transport-projects"),
        name="mcp-transports",
        tutorial="welcome-to-scistudio",
        copies=[
            ("assets/data", "data/raw"),
            ("assets/code/normalize_fluorescence.py", "blocks/normalize_fluorescence.py"),
        ],
    )
    backend.put_workflow(WELCOME_WORKFLOW)
    return built


@pytest.fixture(scope="module")
def webmcp_catalogue(serve: ServeProcess, project: Project) -> dict[str, dict[str, Any]]:
    """The HTTP bridge's catalogue for the open project, by tool name."""
    token = read_loopback_token(serve.home, serve.port)
    response = httpx.get(f"{serve.base_url}/api/webmcp/tools", headers={TOKEN_HEADER: token})
    assert response.status_code == 200, response.text[:2000]
    body = response.json()
    assert body["context"]["projectId"] == project.id
    return {tool["name"]: tool for tool in body["tools"]}


def bridge_env(serve: ServeProcess, project_dir: Path) -> dict[str, str]:
    env = isolated_env(serve.home)
    env["SCISTUDIO_PROJECT_DIR"] = str(project_dir)
    return env


def call_ok(client: StdioMcpClient, name: str, arguments: dict[str, Any] | None = None) -> Any:
    response = client.call_tool(name, arguments)
    assert "error" not in response, response
    return text_payload(response)


def test_mcp_bridge_attaches_to_the_running_backend(
    serve: ServeProcess, backend: Backend, project: Project, webmcp_catalogue: dict[str, dict[str, Any]]
) -> None:
    client = StdioMcpClient(
        [sys.executable, "-m", "scistudio", "mcp-bridge"], env=bridge_env(serve, project.path), cwd=project.path
    )
    try:
        info = client.initialize()
        assert info["serverInfo"]["name"] == "scistudio-mcp"
        assert "tools" in info["capabilities"]

        listed = client.request("tools/list")["result"]["tools"]
        # The notification sent after initialize got no response of its own.
        assert client.skipped == []
        socket_tools = {tool["name"]: tool for tool in listed}
        assert set(socket_tools) < set(webmcp_catalogue), sorted(set(socket_tools) - set(webmcp_catalogue))
        for name, tool in socket_tools.items():
            bridged = webmcp_catalogue[name]
            # One registry, two front doors: the same schema and classification.
            assert tool["inputSchema"] == bridged["inputSchema"], name
            assert tool["_meta"] == {"category": bridged["category"], "mutation": bridged["mutation"]}, name
        # The external-audience tools are neither listed nor callable here.
        for name in sorted(set(webmcp_catalogue) - set(socket_tools)):
            refused = client.call_tool(name, {})
            assert refused["error"]["code"] == METHOD_NOT_FOUND, refused
            assert "WebMCP bridge" in refused["error"]["message"], refused

        unknown = client.call_tool("no_such_tool", {})
        assert unknown["error"]["code"] == METHOD_NOT_FOUND
        # Unlike the HTTP bridge, the local socket reports the tool's own error text.
        raised = client.call_tool("get_block_schema", {"type_name": "no_such_block"})
        assert raised["error"]["code"] == INVALID_PARAMS
        assert "not registered" in raised["error"]["message"]

        # Attached, not standalone: what the agent does here is the backend's state.
        info = call_ok(client, "get_project_info")
        assert Path(info["path"]) == project.path
        assert info["project"]["id"] == project.id
        call_ok(client, "list_blocks")
        written = call_ok(client, "write_workflow", {"path": "workflows/bridged.yaml", "yaml": SMALL_WORKFLOW})
        assert Path(written["path"]) == project.path / "workflows" / "bridged.yaml"
        assert backend.call("GET", "/api/workflows/bridged")["id"] == "bridged"

        run_id = call_ok(client, "run_workflow", {"path": "workflows/bridged.yaml"})["run_id"]
        deadline = time.monotonic() + 120
        status = call_ok(client, "get_run_status", {"run_id": run_id})
        while status["state"] not in {"succeeded", "failed", "cancelled"}:
            assert time.monotonic() < deadline, status
            time.sleep(0.25)
            status = call_ok(client, "get_run_status", {"run_id": run_id})
        assert status["progress"]["block_states"] == {"load": "DONE", "save": "DONE"}, status
        assert (project.path / "data" / "processed" / "bridged.csv").is_file()
        runs = backend.call("GET", "/api/runs", params={"workflow_id": "bridged", "limit": 50})["runs"]
        assert [row["status"] for row in runs] == ["completed"], runs
    finally:
        exit_code = client.close()
    assert exit_code == 0, client.stderr[-3000:]


def test_mcp_bridge_without_a_backend_serves_the_project_standalone(
    serve: ServeProcess, project: Project, tmp_path: Path
) -> None:
    # A copy of the project that no backend has open: the bridge finds no
    # socket and starts its own server. open_gui is the tool whose documented
    # refusal needs exactly this situation (no published GUI address).
    detached = tmp_path / "detached-project"
    shutil.copytree(project.path, detached, ignore=shutil.ignore_patterns("mcp.sock*"))
    client = StdioMcpClient(
        [sys.executable, "-m", "scistudio", "mcp-bridge"], env=bridge_env(serve, detached), cwd=detached
    )
    try:
        client.initialize()
        info = call_ok(client, "get_project_info")
        assert Path(info["path"]) == detached
        blocks = {row["type_name"] for row in call_ok(client, "list_blocks")["blocks"]}
        assert {"load_data", "save_data", "normalize_fluorescence"} <= blocks
        workflow = call_ok(client, "get_workflow", {"path": "workflows/main.yaml"})
        assert [node["id"] for node in workflow["nodes"]] == ["load", "norm", "save"]

        refused = client.call_tool("open_gui", {})
        assert refused["error"]["code"] == INVALID_PARAMS, refused
        assert "open_gui" in refused["error"]["message"], refused
        assert "No running SciStudio GUI" in refused["error"]["message"], refused
    finally:
        exit_code = client.close()
    assert exit_code == 0, client.stderr[-3000:]


def test_webmcp_adapter_passes_the_bridge_through_over_stdio(
    serve: ServeProcess, project: Project, webmcp_catalogue: dict[str, dict[str, Any]]
) -> None:
    client = StdioMcpClient(
        [sys.executable, "-m", "scistudio", "webmcp-adapter", "--base-url", serve.base_url],
        env=isolated_env(serve.home),
        cwd=project.path,
    )
    try:
        info = client.initialize()
        assert info["serverInfo"]["name"] == "scistudio"

        listed = client.request("tools/list")["result"]["tools"]
        # No tool list of its own: exactly the HTTP bridge's catalogue, external tools included.
        assert {tool["name"] for tool in listed} == set(webmcp_catalogue)
        for tool in listed:
            assert tool["inputSchema"] == webmcp_catalogue[tool["name"]]["inputSchema"], tool["name"]

        result = client.call_tool("get_project_info")["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["project"]["id"] == project.id

        # Results pass through unchanged, refusals included.
        refused = client.call_tool("write_file", {"path": "data/raw/extra.csv", "content": "a,b\n"})["result"]
        assert refused["isError"] is True
        assert refused["structuredContent"]["refusal"]["code"] == "protected_data_dir"
        assert not (project.path / "data" / "raw" / "extra.csv").exists()
        listing = client.call_tool("list_directory", {"path": "data/raw"})["result"]
        assert [entry["name"] for entry in listing["structuredContent"]["entries"]] == [
            "cell_viability_fluorescence.csv"
        ]
    finally:
        exit_code = client.close()
    assert exit_code == 0, client.stderr[-3000:]
