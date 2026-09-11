"""ADR-055 Spec 1 — WebMCP bridge tests (spec §4.4 verification plan).

Covers:

* session substrate (FR-006 / US5): bridge endpoints reject calls without
  the loopback session token, accept the injected token, leave non-bridge
  routes untouched, and keep CORS preflight handling intact;
* catalogue parity (FR-001 / SC-001): ``GET /api/webmcp/tools`` matches
  ``mcp.list_tools()`` and carries the active-project context snapshot;
* dispatch + adapter contract (FR-002/FR-003 / US1/US2): unknown-tool 404,
  structured content preserved, non-text blocks substituted explicitly,
  top-level error flag propagation, thrown exceptions mapped to ``isError``
  content rather than HTTP 5xx;
* project binding (FR-005 / US4): stale mutation calls rejected, re-fetch
  and retry succeeds, read calls follow the declared read policy;
* bounded logging (FR-007 / SC-005): logs carry tool name and outcome but
  never full argument bodies;
* the loopback token file (ADR-055 Spec 4 FR-010, #2308): written owner-only
  by the default guard while a launcher arms it, removed when the server
  stops, never written under a replacement guard, one file per port with the
  newest running backend chosen, and refused when missing, stale, unsafe, or
  malformed.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.types import ASGIApp

from scistudio.ai.agent.mcp.server import adapt_tool_result, mcp
from scistudio.api.routes import webmcp as webmcp_routes
from scistudio.api.runtime import ApiRuntime
from scistudio.api.seam import GuardContext


def _token_headers(client: TestClient) -> dict[str, str]:
    return {"X-SciStudio-WebMCP-Token": client.app.state.webmcp_session_token}


@pytest.fixture()
def fixture_tools() -> Iterator[dict[str, list[str]]]:
    """Register write/read fixture tools on the shared registry, then remove them.

    The global registry must return to its baseline afterwards — the parity
    tests in ``tests/ai/test_mcp_fastmcp.py`` assert the exact tool count.
    """
    calls: dict[str, list[str]] = {"write": [], "read": []}

    @mcp.tool(name="webmcp_fixture_write", tags={"category:testing", "write"})
    def _fixture_write(marker: str = "") -> dict[str, Any]:
        calls["write"].append(marker)
        return {"ok": True, "marker": marker}

    @mcp.tool(name="webmcp_fixture_read", tags={"category:testing", "read"})
    def _fixture_read() -> dict[str, Any]:
        calls["read"].append("called")
        return {"ok": True}

    @mcp.tool(name="webmcp_fixture_raise", tags={"category:testing", "read"})
    def _fixture_raise() -> dict[str, Any]:
        raise RuntimeError("SECRET-DETAIL-9f2b /abs/internal/path must not cross the wire")

    try:
        yield calls
    finally:
        mcp.local_provider.remove_tool("webmcp_fixture_write")
        mcp.local_provider.remove_tool("webmcp_fixture_read")
        mcp.local_provider.remove_tool("webmcp_fixture_raise")


# ---------------------------------------------------------------------------
# FR-006 / US5: session substrate.
# ---------------------------------------------------------------------------


def test_bridge_requires_session_token(client: TestClient) -> None:
    """No token and a wrong token are both authentication rejections, not dispatches."""
    assert client.get("/api/webmcp/tools").status_code == 401
    assert client.get("/api/webmcp/tools", headers={"X-SciStudio-WebMCP-Token": "wrong"}).status_code == 401
    assert client.post("/api/webmcp/call", json={"name": "list_types", "arguments": {}}).status_code == 401


def test_bridge_accepts_injected_session_token(client: TestClient) -> None:
    response = client.get("/api/webmcp/tools", headers=_token_headers(client))
    assert response.status_code == 200


def test_session_middleware_leaves_other_routes_untouched(client: TestClient) -> None:
    assert client.get("/api/version").status_code == 200


def test_cors_preflight_still_handled_by_cors_layer(client: TestClient) -> None:
    """The session middleware sits inside the CORS layer: preflight never reaches it."""
    response = client.options(
        "/api/webmcp/call",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_served_page_bootstrap_carries_session_token(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """US5 AS2: the served index.html carries the token the bridge accepts."""
    from scistudio.api import app as app_module

    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>',
        encoding="utf-8",
    )
    monkeypatch.setattr(app_module, "_resolve_spa_static_dir", lambda: static_dir)
    app = app_module.create_app()
    with TestClient(app) as spa_client:
        shell = spa_client.get("/")
        assert shell.status_code == 200
        token = app.state.webmcp_session_token
        assert f"window.__SCISTUDIO_WEBMCP_TOKEN__ = {json.dumps(token)};" in shell.text
        assert shell.headers["cache-control"] == "no-cache"
        # The injected token actually authenticates bridge calls (US5 AS2).
        response = spa_client.get("/api/webmcp/tools", headers={"X-SciStudio-WebMCP-Token": token})
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# FR-001 / SC-001: catalogue parity and context snapshot.
# ---------------------------------------------------------------------------


def test_catalogue_matches_registry(client: TestClient, runtime: ApiRuntime, opened_project: Path) -> None:
    import asyncio

    registry_tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    response = client.get("/api/webmcp/tools", headers=_token_headers(client))
    assert response.status_code == 200
    body = response.json()

    catalogue = {entry["name"]: entry for entry in body["tools"]}
    assert set(catalogue) == set(registry_tools)
    for name, entry in catalogue.items():
        assert entry["inputSchema"] == registry_tools[name].parameters
        assert entry["description"] == (registry_tools[name].description or "")
        assert entry["category"]
        assert entry["mutation"] in ("read", "write")

    # Context snapshot identifies the active project (FR-001/FR-005).
    assert runtime.active_project is not None
    assert body["context"] == {"projectId": runtime.active_project.id}


def test_catalogue_context_snapshot_without_project(client: TestClient) -> None:
    body = client.get("/api/webmcp/tools", headers=_token_headers(client)).json()
    assert body["context"] == {"projectId": None}


# ---------------------------------------------------------------------------
# FR-002: dispatch.
# ---------------------------------------------------------------------------


def test_unknown_tool_returns_404(client: TestClient, opened_project: Path) -> None:
    response = client.post(
        "/api/webmcp/call",
        headers=_token_headers(client),
        json={"name": "no_such_tool", "arguments": {}},
    )
    assert response.status_code == 404
    assert "unknown tool" in response.json()["detail"]


def test_read_tool_dispatches_through_bridge(
    client: TestClient, opened_project: Path, fixture_tools: dict[str, list[str]]
) -> None:
    snapshot = client.get("/api/webmcp/tools", headers=_token_headers(client)).json()
    response = client.post(
        "/api/webmcp/call",
        headers=_token_headers(client),
        json={
            "name": "webmcp_fixture_read",
            "arguments": {},
            "projectId": snapshot["context"]["projectId"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is False
    assert fixture_tools["read"] == ["called"]


# ---------------------------------------------------------------------------
# FR-003 / US2: the adapter contract.
# ---------------------------------------------------------------------------


class _TextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _ImageBlock:
    type = "image"

    def __init__(self) -> None:
        self.data = "aGVsbG8="
        self.mimeType = "image/png"


class _FakeResult:
    def __init__(
        self,
        *,
        content: list[object] | None = None,
        structured: dict[str, Any] | None = None,
        is_error: bool = False,
    ) -> None:
        self.content = content
        self.structured_content = structured
        self.isError = is_error


def test_adapter_preserves_structured_content() -> None:
    """SC-002: structured content survives in its declared field, no text round-trip."""
    structured = {"points": [{"x": 1, "y": [2, 3]}], "unit": "nm"}
    result = _FakeResult(content=[_TextBlock("summary")], structured=structured)
    adapted = adapt_tool_result(result)
    assert adapted["structuredContent"] == structured
    assert adapted["content"] == [{"type": "text", "text": "summary"}]
    assert adapted["isError"] is False


def test_adapter_substitutes_non_text_blocks_with_marker() -> None:
    result = _FakeResult(content=[_TextBlock("before"), _ImageBlock()])
    adapted = adapt_tool_result(result)
    assert adapted["content"][0] == {"type": "text", "text": "before"}
    substituted = adapted["content"][1]
    assert substituted["type"] == "text"
    assert substituted["substitutedFrom"] == "image"
    assert "image" in substituted["text"]


def test_adapter_propagates_top_level_error_flag() -> None:
    result = _FakeResult(content=[_TextBlock("boom")], is_error=True)
    adapted = adapt_tool_result(result)
    assert adapted["isError"] is True
    assert adapted["content"] == [{"type": "text", "text": "boom"}]


def test_adapter_wraps_primitive_result() -> None:
    adapted = adapt_tool_result({"plain": "dict"})
    assert adapted["content"] == [{"type": "text", "text": json.dumps({"plain": "dict"})}]
    assert adapted["isError"] is False


def test_thrown_exception_maps_to_iserror_not_5xx(client: TestClient, opened_project: Path) -> None:
    """A tool call that fails argument validation surfaces as isError content."""
    response = client.post(
        "/api/webmcp/call",
        headers=_token_headers(client),
        # get_block_schema requires block_name; omitting it makes FastMCP raise.
        json={"name": "get_block_schema", "arguments": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is True
    assert body["content"][0]["type"] == "text"


def test_exception_mapping_is_bounded_no_internals_exposed(
    client: TestClient, opened_project: Path, fixture_tools: dict[str, list[str]]
) -> None:
    """CodeQL py/stack-trace-exposure (PR #2275 review): the exception mapping
    carries the exception TYPE name and a generic message only — never the
    exception message, which can embed argument values, paths, or internals."""
    response = client.post(
        "/api/webmcp/call",
        headers=_token_headers(client),
        json={"name": "webmcp_fixture_raise", "arguments": {}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["isError"] is True
    assert len(body["content"]) == 1
    text = body["content"][0]["text"]
    # Bounded type name only: FastMCP wraps tool exceptions in ToolError.
    assert "ToolError" in text or "RuntimeError" in text
    assert "SECRET-DETAIL-9f2b" not in text
    assert "/abs/internal/path" not in text
    assert "Traceback" not in text


# ---------------------------------------------------------------------------
# FR-005 / US4: project binding.
# ---------------------------------------------------------------------------


def _create_project(client: TestClient, parent: Path, name: str) -> dict[str, Any]:
    response = client.post(
        "/api/projects/",
        json={"name": name, "description": "webmcp test", "path": str(parent)},
    )
    assert response.status_code == 200
    return response.json()


def test_stale_project_mutation_rejected_then_refetch_succeeds(
    client: TestClient,
    runtime: ApiRuntime,
    project_parent: Path,
    opened_project: Path,
    fixture_tools: dict[str, list[str]],
) -> None:
    headers = _token_headers(client)
    project_a = runtime.active_project
    assert project_a is not None

    snapshot_a = client.get("/api/webmcp/tools", headers=headers).json()
    assert snapshot_a["context"]["projectId"] == project_a.id

    # Baseline: a mutation call matching the snapshot dispatches.
    ok = client.post(
        "/api/webmcp/call",
        headers=headers,
        json={"name": "webmcp_fixture_write", "arguments": {"marker": "a"}, "projectId": project_a.id},
    )
    assert ok.status_code == 200
    assert fixture_tools["write"] == ["a"]

    # A second page opens project B — the backend's active project changes.
    _create_project(client, project_parent, "Project B")
    assert runtime.active_project is not None
    assert runtime.active_project.id != project_a.id

    # The in-flight write with A's snapshot is rejected and does NOT execute.
    stale = client.post(
        "/api/webmcp/call",
        headers=headers,
        json={"name": "webmcp_fixture_write", "arguments": {"marker": "stale"}, "projectId": project_a.id},
    )
    assert stale.status_code == 409
    detail = stale.json()["detail"]
    assert detail["error"] == "stale_project_context"
    assert detail["presentedProjectId"] == project_a.id
    assert detail["activeProjectId"] == runtime.active_project.id
    assert fixture_tools["write"] == ["a"], "stale mutation must not execute"

    # Re-fetch the catalogue and retry: the call dispatches against B.
    snapshot_b = client.get("/api/webmcp/tools", headers=headers).json()
    retry = client.post(
        "/api/webmcp/call",
        headers=headers,
        json={
            "name": "webmcp_fixture_write",
            "arguments": {"marker": "b"},
            "projectId": snapshot_b["context"]["projectId"],
        },
    )
    assert retry.status_code == 200
    assert fixture_tools["write"] == ["a", "b"]


def test_read_calls_follow_declared_policy(
    client: TestClient,
    runtime: ApiRuntime,
    project_parent: Path,
    opened_project: Path,
    fixture_tools: dict[str, list[str]],
) -> None:
    """Read-tagged calls are dispatched without the staleness check (FR-005 read policy)."""
    headers = _token_headers(client)
    project_a = runtime.active_project
    assert project_a is not None
    _create_project(client, project_parent, "Project B")

    response = client.post(
        "/api/webmcp/call",
        headers=headers,
        json={"name": "webmcp_fixture_read", "arguments": {}, "projectId": project_a.id},
    )
    assert response.status_code == 200
    assert fixture_tools["read"] == ["called"]


# ---------------------------------------------------------------------------
# FR-007 / SC-005: bounded logging.
# ---------------------------------------------------------------------------


def test_logs_never_contain_argument_bodies(
    client: TestClient,
    opened_project: Path,
    fixture_tools: dict[str, list[str]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "SECRET-FILE-BODY-7f3a9c-lorem-ipsum-dolor"
    with caplog.at_level("INFO", logger="scistudio.api.routes.webmcp"):
        response = client.post(
            "/api/webmcp/call",
            headers=_token_headers(client),
            json={"name": "webmcp_fixture_write", "arguments": {"marker": secret}, "projectId": None},
        )
        # projectId None vs active project A -> stale rejection, also logged.
        assert response.status_code == 409
        ok = client.post(
            "/api/webmcp/call",
            headers=_token_headers(client),
            json={
                "name": "webmcp_fixture_write",
                "arguments": {"marker": secret},
                "projectId": client.app.state.runtime.active_project.id,
            },
        )
        assert ok.status_code == 200

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "webmcp_fixture_write" in rendered, "tool name must be logged"
    assert secret not in rendered, "argument bodies must never be logged"


# ---------------------------------------------------------------------------
# ADR-055 Spec 4 FR-010 (#2308): the loopback token file.
# ---------------------------------------------------------------------------


@pytest.fixture()
def token_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "token-home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def _plant_token_file(
    directory: Path,
    *,
    port: int,
    pid: int,
    started_at: float,
    token: str = "t",
    create_time: float | None = None,
) -> Path:
    """Write a token file by hand, owner-only, as another backend would have."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = webmcp_routes.loopback_token_path(port, directory)
    payload: dict[str, Any] = {
        "version": 1,
        "token": token,
        "pid": pid,
        "port": port,
        "baseUrl": f"http://127.0.0.1:{port}",
        "startedAt": started_at,
    }
    if create_time is not None:
        payload["createTime"] = create_time
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


def _passthrough_guard(app: ASGIApp, context: GuardContext, /) -> ASGIApp:
    return app


def test_default_guard_writes_owner_only_token_file_and_removes_it_on_shutdown(token_home: Path) -> None:
    from scistudio.api.app import create_app

    with webmcp_routes.loopback_token_file(port=8123, base_url="http://127.0.0.1:8123/p"):
        app = create_app()
        with TestClient(app):
            path = webmcp_routes.loopback_token_path(8123)
            assert path.parent == token_home / ".scistudio" / "webmcp"
            record = webmcp_routes.read_loopback_token_file(path)
            assert record.token == app.state.webmcp_session_token
            assert record.pid == os.getpid()
            assert record.port == 8123
            assert record.base_url == "http://127.0.0.1:8123/p"
            assert record.token not in repr(record)
            assert not list(path.parent.glob("*.tmp")), "the atomic write leaves no temporary file"
            if sys.platform != "win32":
                assert stat.S_IMODE(path.stat().st_mode) == 0o600
                assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    # The launcher's context closes after uvicorn.run returns, that is, after
    # the server has stopped: the file goes with it.
    assert not path.exists()


def test_replacement_guard_never_writes_a_token_file(token_home: Path) -> None:
    from scistudio.api.app import create_app

    with webmcp_routes.loopback_token_file(port=8124, base_url="http://127.0.0.1:8124"):
        app = create_app(guard=_passthrough_guard)
        with TestClient(app):
            assert app.state.webmcp_session_token == ""
            assert not list((token_home / ".scistudio" / "webmcp").glob("loopback-*.json"))


def test_backend_without_a_launcher_writes_no_token_file(client: TestClient, tmp_path: Path) -> None:
    """Tests and a bare ``uvicorn`` run build the default guard without arming the file."""
    assert client.get("/api/webmcp/tools", headers=_token_headers(client)).status_code == 200
    assert not (tmp_path / "home" / ".scistudio" / "webmcp").exists()


def test_several_backends_newest_running_one_wins(token_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = webmcp_routes.loopback_token_dir()
    _plant_token_file(directory, port=8001, pid=os.getpid(), started_at=100.0)
    _plant_token_file(directory, port=8002, pid=os.getpid(), started_at=200.0)
    assert webmcp_routes.find_loopback_token_file().port == 8002
    assert webmcp_routes.find_loopback_token_file(8001).port == 8001

    # The newest backend was killed without removing its file: it is skipped.
    _plant_token_file(directory, port=8002, pid=424242, started_at=300.0)
    monkeypatch.setattr(webmcp_routes, "_pid_alive", lambda pid: pid == os.getpid())
    assert webmcp_routes.find_loopback_token_file().port == 8001


def test_no_running_backend_is_a_retryable_refusal(token_home: Path) -> None:
    with pytest.raises(webmcp_routes.LoopbackTokenFileError) as excinfo:
        webmcp_routes.find_loopback_token_file()
    assert excinfo.value.retryable is True
    assert "no token file of a running SciStudio backend" in str(excinfo.value)


def test_writer_prunes_files_of_backends_that_are_gone(token_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = webmcp_routes.loopback_token_dir()
    stale = _plant_token_file(directory, port=8003, pid=424242, started_at=1.0)
    monkeypatch.setattr(webmcp_routes, "_pid_alive", lambda pid: pid == os.getpid())
    written = webmcp_routes.write_loopback_token_file(token="x", port=8004, base_url="http://127.0.0.1:8004")
    assert not stale.exists()
    assert written.exists()


def test_remove_leaves_another_backends_file(tmp_path: Path) -> None:
    path = _plant_token_file(tmp_path / "webmcp", port=8005, pid=424242, started_at=1.0)
    webmcp_routes.remove_loopback_token_file(path)
    assert path.exists()


def test_reader_refuses_missing_stale_and_malformed_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    directory = tmp_path / "webmcp"
    with pytest.raises(webmcp_routes.LoopbackTokenFileError, match="does not exist") as missing:
        webmcp_routes.read_loopback_token_file(webmcp_routes.loopback_token_path(8006, directory))
    assert missing.value.retryable is True

    stale_path = _plant_token_file(directory, port=8007, pid=424242, started_at=1.0, token="stale-secret-9")
    monkeypatch.setattr(webmcp_routes, "_pid_alive", lambda pid: False)
    with pytest.raises(webmcp_routes.LoopbackTokenFileError, match="is stale") as stale:
        webmcp_routes.read_loopback_token_file(stale_path)
    assert stale.value.retryable is True
    assert "stale-secret-9" not in str(stale.value)

    garbage = _plant_token_file(directory, port=8008, pid=os.getpid(), started_at=1.0)
    garbage.write_text("{not json", encoding="utf-8")
    with pytest.raises(webmcp_routes.LoopbackTokenFileError, match="not valid JSON") as malformed:
        webmcp_routes.read_loopback_token_file(garbage)
    assert malformed.value.retryable is False


def test_reader_refuses_a_symbolic_link(tmp_path: Path) -> None:
    real = _plant_token_file(tmp_path / "webmcp", port=8009, pid=os.getpid(), started_at=1.0)
    link = webmcp_routes.loopback_token_path(8010, tmp_path / "webmcp")
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("creating symbolic links needs a privilege this account lacks")
    with pytest.raises(webmcp_routes.LoopbackTokenFileError, match="symbolic link") as excinfo:
        webmcp_routes.read_loopback_token_file(link)
    assert excinfo.value.retryable is False


def test_permission_rule_requires_owner_only() -> None:
    """The POSIX rule, exercised on every platform with explicit stat values."""

    def fake_stat(mode: int, uid: int) -> os.stat_result:
        return os.stat_result((stat.S_IFREG | mode, 0, 0, 1, uid, uid, 10, 0, 0, 0))

    assert webmcp_routes.token_file_permission_problem(fake_stat(0o600, 1000), uid=1000) is None
    world = webmcp_routes.token_file_permission_problem(fake_stat(0o644, 1000), uid=1000)
    assert world is not None and "mode 0644" in world and "owner-only (0600)" in world
    group = webmcp_routes.token_file_permission_problem(fake_stat(0o640, 1000), uid=1000)
    assert group is not None
    foreign = webmcp_routes.token_file_permission_problem(fake_stat(0o600, 1001), uid=1000)
    assert foreign is not None and "not by the current user" in foreign


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX owner and mode bits; Windows relies on the profile ACL")
def test_reader_refuses_a_file_other_users_can_read(tmp_path: Path) -> None:
    path = webmcp_routes.write_loopback_token_file(
        token="perm-secret-1", port=8011, base_url="http://127.0.0.1:8011", directory=tmp_path / "webmcp"
    )
    path.chmod(0o644)
    with pytest.raises(webmcp_routes.LoopbackTokenFileError, match=r"owner-only \(0600\)") as excinfo:
        webmcp_routes.read_loopback_token_file(path)
    assert excinfo.value.retryable is False
    assert "perm-secret-1" not in str(excinfo.value)
    with pytest.raises(webmcp_routes.LoopbackTokenFileError):
        webmcp_routes.find_loopback_token_file(directory=tmp_path / "webmcp")


def test_a_reused_pid_does_not_make_a_leftover_file_look_live(tmp_path: Path) -> None:
    """The file records the process create time; the same PID with another create time is stale."""
    path = _plant_token_file(tmp_path / "webmcp", port=8012, pid=os.getpid(), started_at=1.0, create_time=12345.0)
    with pytest.raises(webmcp_routes.LoopbackTokenFileError, match="is stale") as excinfo:
        webmcp_routes.read_loopback_token_file(path)
    assert excinfo.value.retryable is True


_RUNNING_BACKEND = (
    "import sys\n"
    "from pathlib import Path\n"
    "from scistudio.api.routes import webmcp\n"
    "port = int(sys.argv[2])\n"
    "webmcp.write_loopback_token_file(token='token-A', port=port, base_url=f'http://127.0.0.1:{port}', "
    "directory=Path(sys.argv[1]))\n"
    "print('ready', flush=True)\n"
    "sys.stdin.readline()\n"
)


def test_a_second_backend_on_a_busy_port_leaves_the_running_backends_file_alone(tmp_path: Path) -> None:
    """No-context audit P2-1, with a real second process holding the port's file.

    uvicorn starts the application, and so writes the token file, before it
    binds. A second backend on a busy port must neither replace the running
    backend's file nor remove it when its own run ends.
    """
    directory = tmp_path / "webmcp"
    src = str(Path(webmcp_routes.__file__).resolve().parents[3])
    running = subprocess.Popen(
        [sys.executable, "-c", _RUNNING_BACKEND, str(directory), "8013"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        env={**os.environ, "PYTHONPATH": src},
    )
    try:
        assert running.stdout is not None
        assert running.stdout.readline().strip() == b"ready"
        path = webmcp_routes.loopback_token_path(8013, directory)
        with webmcp_routes.loopback_token_file(port=8013, base_url="http://127.0.0.1:8013", directory=directory):
            # What the second backend's default guard does as it starts.
            webmcp_routes._publish_loopback_token("token-B")
            assert webmcp_routes.read_loopback_token_file(path).token == "token-A"
        # Its run ended (it could not bind): the running backend's file is untouched.
        # (On Windows a venv's python.exe launches the interpreter as a child, so
        # the recorded PID is not necessarily ``running.pid``.)
        record = webmcp_routes.read_loopback_token_file(path)
        assert record.token == "token-A"
        assert record.pid != os.getpid()
    finally:
        if running.stdin is not None:
            running.stdin.close()
        running.wait(timeout=60)


def test_removal_needs_this_process_and_its_token(tmp_path: Path) -> None:
    path = webmcp_routes.write_loopback_token_file(
        token="mine", port=8014, base_url="http://127.0.0.1:8014", directory=tmp_path / "webmcp"
    )
    webmcp_routes.remove_loopback_token_file(path, token="someone-else")
    assert path.exists()
    webmcp_routes.remove_loopback_token_file(path, token="mine")
    assert not path.exists()


def test_malformed_or_newer_files_do_not_block_discovery(token_home: Path, caplog: pytest.LogCaptureFixture) -> None:
    """No-context audit P3-4: one bad file must not hide the other backends."""
    directory = webmcp_routes.loopback_token_dir()
    _plant_token_file(directory, port=8015, pid=os.getpid(), started_at=100.0)
    newer = _plant_token_file(directory, port=8016, pid=os.getpid(), started_at=200.0)
    newer.write_text('{"version": 2}', encoding="utf-8")
    corrupt = _plant_token_file(directory, port=8017, pid=os.getpid(), started_at=300.0)
    corrupt.write_text("{not json", encoding="utf-8")
    with caplog.at_level("WARNING", logger="scistudio.api.routes.webmcp"):
        assert webmcp_routes.find_loopback_token_file().port == 8015
    assert "loopback-8016.json" in caplog.text
    assert "loopback-8017.json" in caplog.text
