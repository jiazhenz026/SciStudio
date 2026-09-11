"""ADR-055 Spec 4 (#2308) — the stdio MCP adapter over the WebMCP HTTP bridge.

Covers ``docs/specs/adr-055-enterprise-support.md`` FR-008 to FR-011 and
User Story 5:

* catalogue parity with ``GET /api/webmcp/tools``, ``audience:external``
  tools included, and the project snapshot (FR-008);
* the Spec 1 result contract passed through unchanged: ``isError``,
  structured content, marked non-text substitutions (FR-008);
* ``409 stale_project_context``: reported as an error, the catalogue
  re-fetched, ``notifications/tools/list_changed`` sent, never retried
  (FR-008);
* credentials: a bearer token on every request, against a guarded backend
  under a service prefix; the loopback token file for a local backend, and
  its refusal when missing, stale, or not owner-only (FR-009, FR-010);
* a bounded startup wait, and authentication errors that name the base URL;
* logs and stderr that never carry a credential or an argument (FR-011);
* the ``--print-config`` snippets and the CLI wiring (FR-011).

The adapter's HTTP requests reach a real backend built by ``create_app``
through :class:`ForwardingTransport`, which hands them to FastAPI's
``TestClient``; protocol-only cases use ``httpx.MockTransport``.
"""

from __future__ import annotations

import asyncio
import functools
import io
import json
import logging
import os
import pathlib
import shlex
import sys
import time
import tomllib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp.tools.tool import ToolResult
from mcp.types import ImageContent, TextContent
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from typer.testing import CliRunner

from scistudio.ai.agent.mcp.server import AUDIENCE_EXTERNAL_TAG, mcp
from scistudio.api.routes import webmcp as bridge
from scistudio.api.seam import GuardContext, GuardFactory
from scistudio.cli import webmcp_adapter as adapter_module
from scistudio.cli.main import app as cli_app
from scistudio.cli.webmcp_adapter import (
    LOOPBACK_TOKEN_HEADER,
    SUPPORTED_PROTOCOL_VERSIONS,
    TOKEN_ENV,
    TOKEN_PLACEHOLDER,
    AdapterConfigError,
    BridgeTarget,
    TokenFileUnavailableError,
    WebMCPAdapter,
    is_loopback_url,
    normalize_base_url,
    render_config,
    resolve_target,
    run,
    serve_stdio,
)

LIST_CHANGED = {"jsonrpc": "2.0", "method": "notifications/tools/list_changed"}
FIXTURE_TOOLS = (
    "adapter_fixture_write",
    "adapter_fixture_structured",
    "adapter_fixture_mixed",
    "adapter_fixture_raise",
    "adapter_fixture_external",
)


# ---------------------------------------------------------------------------
# Fixtures and helpers.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the adapter's logger, credentials, and proxies from leaking between tests."""
    for name in (TOKEN_ENV, "SCISTUDIO_MCP_BASE_URL", "SCISTUDIO_MCP_LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    # httpx mounts environment proxies ahead of an injected transport.
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    log = logging.getLogger(adapter_module.__name__)
    handlers, level, propagate = list(log.handlers), log.level, log.propagate
    yield
    log.handlers[:] = handlers
    log.setLevel(level)
    log.propagate = propagate


@pytest.fixture()
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate ``~/.scistudio`` (project registry and loopback token files)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    return home


@pytest.fixture()
def backend(fake_home: Path) -> Iterator[TestClient]:
    """A default open-source backend (loopback token guard)."""
    from scistudio.api.app import create_app

    with TestClient(create_app()) as client:
        yield client


def _open_project(client: TestClient, parent: Path, name: str) -> str:
    parent.mkdir(exist_ok=True)
    response = client.post("/api/projects/", json={"name": name, "description": "adapter test", "path": str(parent)})
    assert response.status_code == 200
    return str(client.app.state.runtime.active_project.id)


@pytest.fixture()
def opened_project(backend: TestClient, tmp_path: Path) -> str:
    return _open_project(backend, tmp_path / "projects", "Project A")


@pytest.fixture()
def fixture_tools() -> Iterator[dict[str, list[str]]]:
    """Register fixture tools on the shared registry, then remove them."""
    calls: dict[str, list[str]] = {"write": []}

    @mcp.tool(name="adapter_fixture_write", tags={"category:testing", "write"})
    def _write(marker: str = "") -> dict[str, Any]:
        calls["write"].append(marker)
        return {"ok": True, "marker": marker}

    @mcp.tool(name="adapter_fixture_structured", tags={"category:testing", "read"})
    def _structured() -> dict[str, Any]:
        return {"points": [{"x": 1, "y": [2, 3]}], "unit": "nm"}

    @mcp.tool(name="adapter_fixture_mixed", tags={"category:testing", "read"})
    def _mixed() -> ToolResult:
        return ToolResult(
            content=[
                TextContent(type="text", text="before"),
                ImageContent(type="image", data="aGVsbG8=", mimeType="image/png"),
            ],
            structured_content={"frames": 1},
        )

    @mcp.tool(name="adapter_fixture_raise", tags={"category:testing", "read"})
    def _raise() -> dict[str, Any]:
        raise RuntimeError("SECRET-DETAIL-4c1d must not cross the wire")

    @mcp.tool(name="adapter_fixture_external", tags={"category:testing", "read", AUDIENCE_EXTERNAL_TAG})
    def _external() -> dict[str, Any]:
        return {"external": True}

    try:
        yield calls
    finally:
        for name in FIXTURE_TOOLS:
            mcp.local_provider.remove_tool(name)


class ForwardingTransport(httpx.BaseTransport):
    """Hand the adapter's HTTP requests to a FastAPI ``TestClient`` and record them."""

    _DROP_REQUEST = frozenset({"host", "content-length", "transfer-encoding", "connection", "accept-encoding"})
    _DROP_RESPONSE = frozenset({"content-length", "content-encoding", "transfer-encoding"})

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        headers = {k: v for k, v in request.headers.items() if k.lower() not in self._DROP_REQUEST}
        reply = self.client.request(
            request.method, request.url.raw_path.decode("ascii"), headers=headers, content=request.read()
        )
        out = {k: v for k, v in reply.headers.items() if k.lower() not in self._DROP_RESPONSE}
        return httpx.Response(reply.status_code, headers=out, content=reply.content)

    def posts(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "POST"]


def _loopback_resolver(client: TestClient, base_url: str = "http://127.0.0.1:8000") -> Callable[[], BridgeTarget]:
    target = BridgeTarget(base_url, client.app.state.webmcp_session_token, "token-file")
    return lambda: target


def _connected(
    client: TestClient, resolve: Callable[[], BridgeTarget] | None = None
) -> tuple[WebMCPAdapter, ForwardingTransport, list[dict[str, Any]]]:
    transport = ForwardingTransport(client)
    emitted: list[dict[str, Any]] = []
    adapter = WebMCPAdapter(resolve or _loopback_resolver(client), transport=transport, emit=emitted.append)
    adapter.connect(timeout=0)
    return adapter, transport, emitted


def _rpc(adapter: WebMCPAdapter, method: str, params: dict[str, Any] | None = None, req_id: int = 1) -> dict[str, Any]:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        message["params"] = params
    response = adapter.handle(message)
    assert response is not None
    assert response["id"] == req_id
    return response


def _bridge_headers(client: TestClient) -> dict[str, str]:
    return {LOOPBACK_TOKEN_HEADER: client.app.state.webmcp_session_token}


def _bearer_guard(expected: str) -> GuardFactory:
    """A replacement guard that accepts one bearer token, as an edition's guard would."""

    def build(app: ASGIApp, context: GuardContext, /) -> ASGIApp:
        async def guard(scope: Scope, receive: Receive, send: Send) -> None:
            headers = dict(scope.get("headers", []))
            if headers.get(b"authorization") == f"Bearer {expected}".encode():
                await app(scope, receive, send)
                return
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            await JSONResponse({"detail": "login required"}, status_code=401)(scope, receive, send)

        return guard

    return build


def _fake_bridge(
    *, project: str | None = "p1", call: Callable[[httpx.Request], httpx.Response] | None = None
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/api/webmcp/tools"):
            return httpx.Response(200, json={"tools": [], "context": {"projectId": project}})
        if call is not None:
            return call(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "done"}], "isError": False})

    return httpx.MockTransport(handler), seen


def test_adapter_constants_match_the_bridge() -> None:
    """The adapter duplicates two bridge constants to stay light to import; they must agree."""
    assert adapter_module.LOOPBACK_TOKEN_HEADER == bridge.SESSION_TOKEN_HEADER
    assert adapter_module.STALE_PROJECT_CODE == bridge.STALE_PROJECT_CODE


# ---------------------------------------------------------------------------
# FR-008: catalogue parity and the project snapshot.
# ---------------------------------------------------------------------------


def test_tools_list_matches_bridge_catalogue_including_external_tools(
    backend: TestClient, opened_project: str, fixture_tools: dict[str, list[str]]
) -> None:
    adapter, _, _ = _connected(backend)
    listed = _rpc(adapter, "tools/list")["result"]["tools"]
    catalogue = backend.get("/api/webmcp/tools", headers=_bridge_headers(backend)).json()["tools"]

    assert [tool["name"] for tool in listed] == [entry["name"] for entry in catalogue]
    for tool, entry in zip(listed, catalogue, strict=True):
        assert tool["inputSchema"] == entry["inputSchema"]
        assert tool["description"] == entry["description"]
        assert tool["_meta"] == {"category": entry["category"], "mutation": entry["mutation"]}

    external = {t.name for t in asyncio.run(mcp.list_tools()) if AUDIENCE_EXTERNAL_TAG in (t.tags or set())}
    assert "adapter_fixture_external" in external
    assert external <= {tool["name"] for tool in listed}, "audience:external tools must reach the adapter"
    assert adapter.project_id == opened_project


def test_tools_list_is_fetched_live_every_time(backend: TestClient, opened_project: str) -> None:
    """No registry of its own: a tool registered after the first list appears on the next one."""
    adapter, transport, _ = _connected(backend)
    first = {tool["name"] for tool in _rpc(adapter, "tools/list")["result"]["tools"]}

    @mcp.tool(name="adapter_fixture_late", tags={"category:testing", "read"})
    def _late() -> dict[str, Any]:
        return {}

    try:
        second = {tool["name"] for tool in _rpc(adapter, "tools/list", req_id=2)["result"]["tools"]}
    finally:
        mcp.local_provider.remove_tool("adapter_fixture_late")
    assert "adapter_fixture_late" not in first
    assert "adapter_fixture_late" in second
    assert sum(1 for r in transport.requests if r.method == "GET") == 3  # connect + two lists


def test_snapshot_is_none_without_an_open_project(backend: TestClient) -> None:
    adapter, _, _ = _connected(backend)
    assert adapter.project_id is None


# ---------------------------------------------------------------------------
# FR-008: the Spec 1 result contract, passed through unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["adapter_fixture_structured", "adapter_fixture_mixed", "adapter_fixture_raise"])
def test_call_result_is_the_bridge_result_unchanged(
    backend: TestClient, opened_project: str, fixture_tools: dict[str, list[str]], name: str
) -> None:
    adapter, _, _ = _connected(backend)
    via_adapter = _rpc(adapter, "tools/call", {"name": name, "arguments": {}})["result"]
    direct = backend.post(
        "/api/webmcp/call",
        headers=_bridge_headers(backend),
        json={"name": name, "arguments": {}, "projectId": opened_project},
    ).json()
    assert via_adapter == direct


def test_result_contract_fields_survive(
    backend: TestClient, opened_project: str, fixture_tools: dict[str, list[str]]
) -> None:
    adapter, _, _ = _connected(backend)

    structured = _rpc(adapter, "tools/call", {"name": "adapter_fixture_structured"})["result"]
    assert structured["isError"] is False
    assert structured["structuredContent"] == {"points": [{"x": 1, "y": [2, 3]}], "unit": "nm"}

    mixed = _rpc(adapter, "tools/call", {"name": "adapter_fixture_mixed", "arguments": {}}, req_id=2)["result"]
    assert mixed["content"][0] == {"type": "text", "text": "before"}
    assert mixed["content"][1]["substitutedFrom"] == "image"
    assert mixed["structuredContent"] == {"frames": 1}

    failed = _rpc(adapter, "tools/call", {"name": "adapter_fixture_raise", "arguments": {}}, req_id=3)["result"]
    assert failed["isError"] is True
    assert "SECRET-DETAIL-4c1d" not in json.dumps(failed)


def test_result_fixture_passes_through_verbatim() -> None:
    """Every field of a bridge result, including ones the adapter does not know, is kept."""
    body = {
        "content": [
            {"type": "text", "text": "summary"},
            {"type": "text", "text": "[substituted]", "substitutedFrom": "audio"},
        ],
        "structuredContent": {"rows": [[1, 2], [3, 4]]},
        "isError": True,
        "_meta": {"future": "field"},
    }
    transport, _ = _fake_bridge(call=lambda request: httpx.Response(200, json=body))
    adapter = WebMCPAdapter(functools.partial(resolve_target, "https://lab.example.org", "tok"), transport=transport)
    adapter.connect(timeout=0)
    assert _rpc(adapter, "tools/call", {"name": "anything", "arguments": {"a": 1}})["result"] == body


def test_unknown_tool_is_a_protocol_error(backend: TestClient, opened_project: str) -> None:
    adapter, _, _ = _connected(backend)
    response = _rpc(adapter, "tools/call", {"name": "no_such_tool", "arguments": {}})
    assert response["error"]["code"] == -32602
    assert "no_such_tool" in response["error"]["message"]


# ---------------------------------------------------------------------------
# FR-008 / Spec 1 FR-005: stale project context.
# ---------------------------------------------------------------------------


def test_stale_project_call_is_reported_refetched_and_never_retried(
    backend: TestClient, opened_project: str, fixture_tools: dict[str, list[str]], tmp_path: Path
) -> None:
    adapter, transport, emitted = _connected(backend)
    assert adapter.project_id == opened_project

    # A second page opens project B: the backend's active project changes.
    project_b = _open_project(backend, tmp_path / "projects", "Project B")
    assert project_b != opened_project

    result = _rpc(adapter, "tools/call", {"name": "adapter_fixture_write", "arguments": {"marker": "stale"}})["result"]
    assert result["isError"] is True
    assert result["structuredContent"] == {
        "error": "stale_project_context",
        "presentedProjectId": opened_project,
        "activeProjectId": project_b,
    }
    assert "NOT executed" in result["content"][0]["text"]
    assert fixture_tools["write"] == [], "the stale mutation must not execute"
    assert len(transport.posts()) == 1, "the stale call must not be retried"
    assert emitted == [LIST_CHANGED]
    assert adapter.project_id == project_b, "the catalogue must be re-fetched"

    # The model re-issues the call deliberately: it now runs against B.
    again = _rpc(adapter, "tools/call", {"name": "adapter_fixture_write", "arguments": {"marker": "b"}}, 2)["result"]
    assert again["isError"] is False
    assert fixture_tools["write"] == ["b"]


def test_list_changed_is_sent_before_the_stale_response_on_stdio() -> None:
    stale = {
        "detail": {
            "error": "stale_project_context",
            "message": "re-fetch",
            "presentedProjectId": "p1",
            "activeProjectId": "p2",
        }
    }
    transport, _ = _fake_bridge(call=lambda request: httpx.Response(409, json=stale))
    adapter = WebMCPAdapter(functools.partial(resolve_target, "https://lab.example.org", "tok"), transport=transport)
    adapter.connect(timeout=0)
    stdin = io.BytesIO(
        b'{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"write_file","arguments":{}}}\n'
    )
    stdout = io.BytesIO()
    assert serve_stdio(adapter, stdin, stdout) == 0
    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert lines[0] == LIST_CHANGED
    assert lines[1]["id"] == 7
    assert lines[1]["result"]["isError"] is True


# ---------------------------------------------------------------------------
# FR-009: credentials and the service prefix.
# ---------------------------------------------------------------------------


def test_bearer_token_is_sent_on_every_request_under_the_service_prefix() -> None:
    transport, seen = _fake_bridge()
    adapter = WebMCPAdapter(
        functools.partial(resolve_target, "https://lab.example.org/user/alice/scistudio/", "hub-token-123"),
        transport=transport,
    )
    adapter.connect(timeout=0)
    _rpc(adapter, "tools/list")
    _rpc(adapter, "tools/call", {"name": "list_types", "arguments": {"k": "v"}}, req_id=2)

    assert [r.url.path for r in seen] == [
        "/user/alice/scistudio/api/webmcp/tools",
        "/user/alice/scistudio/api/webmcp/tools",
        "/user/alice/scistudio/api/webmcp/call",
    ]
    for request in seen:
        assert request.headers["authorization"] == "Bearer hub-token-123"
        assert LOOPBACK_TOKEN_HEADER not in request.headers
    assert json.loads(seen[-1].content) == {"name": "list_types", "arguments": {"k": "v"}, "projectId": "p1"}


def test_round_trip_against_a_guarded_backend_under_a_prefix(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch, fixture_tools: dict[str, list[str]]
) -> None:
    """SC-005: an edition's guard accepts the bearer token; the prefix is honored."""
    from scistudio.api.app import create_app

    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", "/user/alice/scistudio")
    with TestClient(create_app(guard=_bearer_guard("lab-token-abc"))) as guarded:
        assert guarded.app.state.webmcp_session_token == ""
        base = "http://lab.test/user/alice/scistudio"
        adapter, transport, _ = _connected(guarded, functools.partial(resolve_target, base, "lab-token-abc"))
        names = {tool["name"] for tool in _rpc(adapter, "tools/list")["result"]["tools"]}
        assert "adapter_fixture_external" in names
        result = _rpc(adapter, "tools/call", {"name": "adapter_fixture_structured", "arguments": {}}, 2)["result"]
        assert result["isError"] is False
        assert all(r.url.path.startswith("/user/alice/scistudio/api/webmcp/") for r in transport.requests)

        wrong = WebMCPAdapter(
            functools.partial(resolve_target, base, "not-the-token"), transport=ForwardingTransport(guarded)
        )
        with pytest.raises(AdapterConfigError) as excinfo:
            wrong.connect(timeout=0)
        assert f"SciStudio at {base} rejected the credential (HTTP 401)" in str(excinfo.value)
        assert "not-the-token" not in str(excinfo.value)


def test_loopback_token_file_authenticates_a_local_backend(fake_home: Path) -> None:
    """US5 AS1: no credential configured; the adapter reads the per-user token file."""
    from scistudio.api.app import create_app

    with (
        bridge.loopback_token_file(port=8765, base_url="http://127.0.0.1:8765"),
        TestClient(create_app()) as client,
    ):
        target = resolve_target(None, None)
        assert target.source == "token-file"
        assert target.base_url == "http://127.0.0.1:8765"
        assert target.credential == client.app.state.webmcp_session_token
        assert target.credential not in repr(target)
        assert resolve_target("http://localhost:8765/", None) == BridgeTarget(
            "http://localhost:8765", target.credential, "token-file"
        )

        adapter, transport, _ = _connected(client, functools.partial(resolve_target, None, None))
        assert _rpc(adapter, "tools/list")["result"]["tools"]
        for request in transport.requests:
            assert request.headers[LOOPBACK_TOKEN_HEADER] == target.credential
            assert "authorization" not in request.headers


def test_token_file_is_never_used_for_a_remote_url(fake_home: Path) -> None:
    with pytest.raises(AdapterConfigError, match=r"no credential for https://lab\.example\.org"):
        resolve_target("https://lab.example.org", None)


def test_token_without_a_base_url_is_refused() -> None:
    with pytest.raises(AdapterConfigError, match="needs --base-url"):
        resolve_target(None, "tok")


def test_missing_token_file_is_refused_with_a_clear_message(fake_home: Path, capsys: pytest.CaptureFixture) -> None:
    assert run(base_url="http://127.0.0.1:8124", startup_timeout=0) == 2
    err = capsys.readouterr().err
    assert "loopback-8124.json does not exist; is SciStudio running?" in err


def test_stale_token_file_is_refused(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    bridge.write_loopback_token_file(token="stale-token-5e1", port=8125, base_url="http://127.0.0.1:8125")
    monkeypatch.setattr(bridge, "_pid_alive", lambda pid: False)
    with pytest.raises(TokenFileUnavailableError) as excinfo:
        resolve_target("http://127.0.0.1:8125", None)
    assert excinfo.value.retryable is True
    assert run(base_url="http://127.0.0.1:8125", startup_timeout=0) == 2
    err = capsys.readouterr().err
    assert "is stale" in err
    assert "stale-token-5e1" not in err


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX owner and mode bits; Windows relies on the profile ACL")
def test_non_owner_only_token_file_is_refused_without_waiting(fake_home: Path, capsys: pytest.CaptureFixture) -> None:
    path = bridge.write_loopback_token_file(token="tok-perm-2b", port=8126, base_url="http://127.0.0.1:8126")
    path.chmod(0o644)
    started = time.monotonic()
    assert run(base_url="http://127.0.0.1:8126", startup_timeout=10) == 2
    assert time.monotonic() - started < 5, "an unsafe token file is not waited out"
    err = capsys.readouterr().err
    assert "owner-only (0600)" in err
    assert "tok-perm-2b" not in err


def test_adapter_follows_a_local_backend_that_restarted() -> None:
    """A token-file target that stops answering is re-resolved; the call is reported, not re-sent."""
    targets = [BridgeTarget("http://127.0.0.1:8001", "old", "token-file")]
    live = {"token": "old"}
    posts: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get(LOOPBACK_TOKEN_HEADER) != live["token"]:
            return httpx.Response(401, json={"detail": "webmcp bridge calls require a valid session token"})
        if request.method == "POST":
            posts.append(request)
            return httpx.Response(200, json={"content": [], "isError": False})
        return httpx.Response(200, json={"tools": [], "context": {"projectId": "p1"}})

    emitted: list[dict[str, Any]] = []
    adapter = WebMCPAdapter(lambda: targets[-1], transport=httpx.MockTransport(handler), emit=emitted.append)
    adapter.connect(timeout=0)

    # SciStudio restarts on another port with a new token.
    live["token"] = "new"
    targets.append(BridgeTarget("http://127.0.0.1:8002", "new", "token-file"))
    result = _rpc(adapter, "tools/call", {"name": "write_file", "arguments": {}})["result"]
    assert result["isError"] is True
    assert "NOT executed" in result["content"][0]["text"]
    assert posts == [], "the refused call is not re-sent to the new backend"
    assert emitted == [LIST_CHANGED]
    assert adapter.base_url == "http://127.0.0.1:8002"

    assert _rpc(adapter, "tools/call", {"name": "write_file", "arguments": {}}, req_id=2)["result"]["isError"] is False
    assert len(posts) == 1


def test_bearer_target_unreachable_mid_session_is_an_error_naming_the_url() -> None:
    state = {"up": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if not state["up"]:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={"tools": [], "context": {"projectId": None}})

    adapter = WebMCPAdapter(
        functools.partial(resolve_target, "https://lab.example.org", "tok"), transport=httpx.MockTransport(handler)
    )
    adapter.connect(timeout=0)
    state["up"] = False
    response = _rpc(adapter, "tools/call", {"name": "x", "arguments": {}})
    assert response["error"]["code"] == -32002
    assert "https://lab.example.org" in response["error"]["message"]
    assert "not delivered" in response["error"]["message"]


# ---------------------------------------------------------------------------
# Startup: bounded wait and authentication errors.
# ---------------------------------------------------------------------------


def test_startup_waits_for_the_backend_within_the_bound() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise httpx.ConnectError("refused", request=request)
        if attempts["n"] == 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"tools": [], "context": {"projectId": None}})

    now = [0.0]
    adapter = WebMCPAdapter(
        functools.partial(resolve_target, "http://127.0.0.1:8000", "tok"), transport=httpx.MockTransport(handler)
    )
    adapter.connect(timeout=10, interval=0.5, sleep=lambda s: now.__setitem__(0, now[0] + s), clock=lambda: now[0])
    assert attempts["n"] == 3
    assert now[0] == 1.0


def test_startup_gives_up_with_a_configuration_error(capsys: pytest.CaptureFixture) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    started = time.monotonic()
    code = run(base_url="http://127.0.0.1:9", token="tok", startup_timeout=0.2, transport=httpx.MockTransport(refuse))
    assert code == 2
    assert time.monotonic() - started < 5
    err = capsys.readouterr().err
    assert "gave up waiting for SciStudio after 0.2 s" in err
    assert "http://127.0.0.1:9" in err


@pytest.mark.parametrize(
    ("status", "phrase"),
    [(401, "rejected the credential (HTTP 401)"), (403, "(HTTP 403)"), (302, "redirected the request (HTTP 302)")],
)
def test_startup_authentication_error_names_the_base_url(
    capsys: pytest.CaptureFixture, status: int, phrase: str
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, headers={"location": "/hub/login"}))
    code = run(
        base_url="https://lab.example.org/user/alice/scistudio",
        token="SECRET-HUB-TOKEN-11",
        startup_timeout=5,
        transport=transport,
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "SciStudio at https://lab.example.org/user/alice/scistudio" in err
    assert phrase in err
    assert "SECRET-HUB-TOKEN-11" not in err


def test_wrong_prefix_is_a_configuration_error(capsys: pytest.CaptureFixture) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404, json={"detail": "Not Found"}))
    assert run(base_url="https://lab.example.org/wrong", token="t", transport=transport) == 2
    assert "check --base-url and its service prefix" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# FR-011: logs and stderr never carry a credential or an argument.
# ---------------------------------------------------------------------------


def test_logs_and_stderr_never_carry_credentials_or_arguments(
    fake_home: Path,
    tmp_path: Path,
    fixture_tools: dict[str, list[str]],
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture,
) -> None:
    from scistudio.api.app import create_app

    secret_argument = "SECRET-ARGUMENT-BODY-91ab"
    bearer = "BEARER-SECRET-7d2e"
    caplog.set_level(logging.DEBUG)

    call = {"name": "adapter_fixture_write", "arguments": {"marker": secret_argument}}
    with (
        bridge.loopback_token_file(port=8766, base_url="http://127.0.0.1:8766"),
        TestClient(create_app()) as client,
    ):
        loopback_token = client.app.state.webmcp_session_token
        _open_project(client, tmp_path / "projects", "Project A")
        adapter, _, _ = _connected(client, functools.partial(resolve_target, None, None))
        _rpc(adapter, "tools/list")
        assert _rpc(adapter, "tools/call", call)["result"]["isError"] is False
        _open_project(client, tmp_path / "projects", "Project B")
        assert _rpc(adapter, "tools/call", call, req_id=2)["result"]["isError"] is True

    with TestClient(create_app(guard=_bearer_guard("the-right-one"))) as guarded:
        code = run(
            base_url="http://lab.test",
            token=bearer,
            startup_timeout=0,
            log_level="DEBUG",
            transport=ForwardingTransport(guarded),
        )
    assert code == 2

    captured = capsys.readouterr()
    rendered = "\n".join([caplog.text, captured.err, captured.out])
    assert "adapter_fixture_write" in caplog.text, "operation identifiers are logged"
    assert "stale_project_context" in caplog.text, "outcomes are logged"
    assert "http://lab.test" in captured.err
    for secret in (loopback_token, bearer, secret_argument):
        assert secret not in rendered


# ---------------------------------------------------------------------------
# MCP protocol handling and the stdio transport.
# ---------------------------------------------------------------------------


@pytest.fixture()
def lab_adapter() -> WebMCPAdapter:
    transport, _ = _fake_bridge()
    adapter = WebMCPAdapter(functools.partial(resolve_target, "https://lab.example.org", "tok"), transport=transport)
    adapter.connect(timeout=0)
    return adapter


def test_initialize_negotiates_the_protocol_version(lab_adapter: WebMCPAdapter) -> None:
    for requested in SUPPORTED_PROTOCOL_VERSIONS:
        result = _rpc(lab_adapter, "initialize", {"protocolVersion": requested, "capabilities": {}})["result"]
        assert result["protocolVersion"] == requested
    newest = _rpc(lab_adapter, "initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert newest["protocolVersion"] == SUPPORTED_PROTOCOL_VERSIONS[0]
    assert newest["capabilities"] == {"tools": {"listChanged": True}}
    assert newest["serverInfo"]["name"] == "scistudio"


def test_protocol_edge_cases(lab_adapter: WebMCPAdapter) -> None:
    assert _rpc(lab_adapter, "ping")["result"] == {}
    assert _rpc(lab_adapter, "resources/list")["error"]["code"] == -32601
    assert lab_adapter.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert lab_adapter.handle({"jsonrpc": "2.0", "id": 3, "result": {}}) is None
    assert lab_adapter.handle([{"jsonrpc": "2.0", "id": 1, "method": "ping"}])["error"]["code"] == -32600  # type: ignore[index]
    assert lab_adapter.handle({"jsonrpc": "2.0", "id": 4})["error"]["code"] == -32600  # type: ignore[index]
    bad = lab_adapter.handle({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": []})
    assert bad is not None and bad["error"]["code"] == -32602
    no_name = _rpc(lab_adapter, "tools/call", {"arguments": {}})
    assert no_name["error"]["code"] == -32602
    bad_args = _rpc(lab_adapter, "tools/call", {"name": "x", "arguments": [1]})
    assert bad_args["error"]["code"] == -32602


def test_cancelled_request_gets_no_response(lab_adapter: WebMCPAdapter) -> None:
    lab_adapter.handle({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 9}})
    assert lab_adapter.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "x"}}) is None
    assert lab_adapter.handle({"jsonrpc": "2.0", "id": 9, "method": "ping"}) is not None


def test_stdio_carries_only_newline_delimited_json(lab_adapter: WebMCPAdapter) -> None:
    stdin = io.BytesIO(
        b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18"}}\n'
        b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        b"\n"
        b"this is not json\n"
        b'{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
    )
    stdout = io.BytesIO()
    assert serve_stdio(lab_adapter, stdin, stdout) == 0
    raw = stdout.getvalue()
    assert raw.endswith(b"\n")
    messages = [json.loads(line) for line in raw.splitlines()]
    by_id = {message["id"]: message for message in messages}
    assert set(by_id) == {None, 1, 2}
    assert by_id[None]["error"]["code"] == -32700
    assert by_id[1]["result"]["protocolVersion"] == "2025-06-18"
    assert by_id[2]["result"] == {"tools": []}


# ---------------------------------------------------------------------------
# Base URL rules.
# ---------------------------------------------------------------------------


def test_base_url_normalization_keeps_the_service_prefix() -> None:
    assert normalize_base_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert (
        normalize_base_url(" https://lab.example.org//user/alice/scistudio/ ")
        == "https://lab.example.org/user/alice/scistudio"
    )


@pytest.mark.parametrize(
    "raw",
    ["https://alice:pw-SECRET-3@lab.example.org", "https://lab.example.org/?token=pw-SECRET-3", "ftp://x", "nonsense"],
)
def test_base_url_refusals_never_echo_a_secret(raw: str) -> None:
    with pytest.raises(AdapterConfigError) as excinfo:
        normalize_base_url(raw)
    assert "pw-SECRET-3" not in str(excinfo.value)


def test_loopback_detection() -> None:
    assert is_loopback_url("http://127.0.0.1:8000")
    assert is_loopback_url("http://localhost:8000/p")
    assert is_loopback_url("http://[::1]:8000")
    assert not is_loopback_url("https://lab.example.org")
    assert not is_loopback_url("http://192.168.1.5:8000")


# ---------------------------------------------------------------------------
# FR-011: configuration snippets.
# ---------------------------------------------------------------------------


def test_claude_desktop_snippet() -> None:
    snippet = json.loads(render_config("claude-desktop", base_url=None, needs_token=False))
    assert snippet == {
        "mcpServers": {"scistudio": {"command": sys.executable, "args": ["-m", "scistudio", "webmcp-adapter"]}}
    }
    lab = json.loads(render_config("claude-desktop", base_url="https://lab.example.org/u/a", needs_token=True))
    server = lab["mcpServers"]["scistudio"]
    assert server["args"][-2:] == ["--base-url", "https://lab.example.org/u/a"]
    assert server["env"] == {TOKEN_ENV: TOKEN_PLACEHOLDER}


def test_codex_snippet_is_valid_toml() -> None:
    parsed = tomllib.loads(render_config("codex", base_url="https://lab.example.org", needs_token=True))
    server = parsed["mcp_servers"]["scistudio"]
    assert server["command"] == sys.executable
    assert server["args"] == ["-m", "scistudio", "webmcp-adapter", "--base-url", "https://lab.example.org"]
    assert server["env"] == {TOKEN_ENV: TOKEN_PLACEHOLDER}
    assert server["startup_timeout_sec"] > adapter_module.DEFAULT_STARTUP_TIMEOUT


def test_claude_code_snippet() -> None:
    snippet = render_config("claude-code", base_url=None, needs_token=True)
    assert snippet.startswith("claude mcp add --transport stdio --env ")
    assert f"{TOKEN_ENV}={TOKEN_PLACEHOLDER}" in snippet
    if os.name != "nt":
        argv = shlex.split(snippet)
        assert argv[argv.index("--") + 1 :] == [sys.executable, "-m", "scistudio", "webmcp-adapter"]


def test_print_config_command_never_prints_the_token() -> None:
    result = CliRunner().invoke(
        cli_app,
        [
            "webmcp-adapter",
            "--print-config",
            "claude-desktop",
            "--base-url",
            "https://lab.example.org/user/alice/scistudio",
            "--token",
            "SECRET-PRINTED-4f",
        ],
    )
    assert result.exit_code == 0
    assert "SECRET-PRINTED-4f" not in result.output
    assert TOKEN_PLACEHOLDER in result.output
    assert "https://lab.example.org/user/alice/scistudio" in result.output


def test_webmcp_adapter_subcommand_is_registered() -> None:
    result = CliRunner().invoke(cli_app, ["webmcp-adapter", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# FR-010: `serve` and `gui` publish the token file for the port they bind.
# ---------------------------------------------------------------------------


def _capture_armed_request(seen: dict[str, Any]) -> Callable[..., None]:
    def fake_run(app_target: str, **kwargs: Any) -> None:
        request = bridge._token_file_request
        seen.update(
            app_target=app_target,
            port=request.port if request is not None else None,
            base_url=request.base_url if request is not None else None,
        )

    return fake_run


def test_serve_publishes_the_token_file_while_uvicorn_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr("uvicorn.run", _capture_armed_request(seen))
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", "")
    monkeypatch.delenv("SCISTUDIO_ENGINE_API_URL", raising=False)
    result = CliRunner().invoke(cli_app, ["serve", "--port", "8123", "--root-path", "/p"])
    assert result.exit_code == 0
    assert seen == {"app_target": "scistudio.api.app:create_app", "port": 8123, "base_url": "http://127.0.0.1:8123/p"}
    assert bridge._token_file_request is None, "disarmed once the server stops"


def test_gui_publishes_the_token_file_while_uvicorn_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    monkeypatch.setattr("uvicorn.run", _capture_armed_request(seen))
    monkeypatch.setenv("SCISTUDIO_ROOT_PATH", "")
    monkeypatch.delenv("SCISTUDIO_ENGINE_API_URL", raising=False)
    result = CliRunner().invoke(cli_app, ["gui", "--no-browser", "--port", "8124"])
    assert result.exit_code == 0
    assert seen == {"app_target": "scistudio.api.app:create_app", "port": 8124, "base_url": "http://127.0.0.1:8124"}
    assert bridge._token_file_request is None
