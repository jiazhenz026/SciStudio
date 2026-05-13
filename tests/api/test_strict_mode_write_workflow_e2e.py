"""End-to-end regression test for #790 + #791 interaction.

Verifies that the combined fix delivers the user-visible behaviour:

1. The WS query-string ``permission_mode=strict`` propagates through
   :func:`_start_default_session` into ``SessionMetadata.bypass_mode``,
   so the hook-bridge's ``/api/ai/permission-check`` correctly
   identifies the session as STRICT (issue #791).
2. A STRICT-mode check for a write-class MCP tool emits a
   ``permission_request`` frame on the chat WebSocket (issue #791).
3. When the user approves, the workflow file actually lands at the
   resolved absolute path under ``project_dir`` — exercising the path
   resolution fix from issue #790. The response from
   :func:`tools_workflow.write_workflow` carries the absolute path.

Both bugs are interrelated: without #790 the file would land in the
wrong place even after the user approves; without #791 the approval
prompt would never appear and BYPASS would silently execute. This
test guards against either regression.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scieasy.ai.agent import permission as permission_module
from scieasy.ai.agent.claude_code import ClaudeCodeProvider
from scieasy.ai.agent.mcp import _context, tools_workflow
from scieasy.ai.agent.provider import PermissionMode
from scieasy.ai.agent.session import AgentSessionManager
from scieasy.api.app import create_app
from scieasy.api.deps import get_agent_session_manager
from scieasy.api.routes import ai as ai_routes
from scieasy.blocks.registry import BlockRegistry
from scieasy.core.types.registry import TypeRegistry

STUB_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "stub_claude.py"


@dataclass
class _StubRuntime:
    """Minimal MCPContext stub for the write_workflow leg."""

    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def app() -> Any:
    return create_app()


@pytest.fixture
def fresh_manager() -> AgentSessionManager:
    return AgentSessionManager()


@pytest.fixture(autouse=True)
def _reset_permission_registry() -> None:
    """Clean module-level pending-decision registry between tests."""
    permission_module._reset_registry_for_tests()
    yield
    permission_module._reset_registry_for_tests()


def _patch_start_with_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch ``_start_default_session`` to use stub_claude but plumb the mode through."""

    async def _stub_start(
        *,
        manager: Any,
        project_dir: Path,
        chat_id: str,
        permission_mode_str: str = "strict",
    ) -> Any:
        mode = PermissionMode.BYPASS if permission_mode_str == "bypass" else PermissionMode.STRICT
        provider = ClaudeCodeProvider(binary_override=STUB_PATH)
        return await manager.start_session(
            project_dir=project_dir,
            chat_id=chat_id,
            provider=provider,
            system_prompt="test",
            mcp_config={},
            permission_mode=mode,
        )

    monkeypatch.setattr(ai_routes, "_start_default_session", _stub_start)


# ---------------------------------------------------------------------------
# Test 1: permission_mode query param propagates into session metadata.
# ---------------------------------------------------------------------------


def test_ws_strict_mode_propagates_to_session_metadata(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #791: ?permission_mode=strict → SessionMetadata.bypass_mode=False."""
    app.dependency_overrides[get_agent_session_manager] = lambda: fresh_manager
    _patch_start_with_mode(monkeypatch)

    project_dir = tmp_path.resolve()
    with (
        TestClient(app) as client,
        client.websocket_connect(
            f"/api/ai/chat/strict-1?project_dir={project_dir}&permission_mode=strict",
        ) as ws,
    ):
        ws.send_text('{"type": "user_message", "content": "hello"}')
        # Drain init event so the session is materialised.
        msg = ws.receive_json()
        assert msg["type"] == "agent_event"

    # After WS closes, the session metadata must reflect STRICT.
    metadata = fresh_manager.load_metadata(project_dir, "strict-1")
    assert metadata is not None
    assert metadata.bypass_mode is False, "STRICT mode should not be recorded as bypass"


def test_ws_bypass_mode_propagates_to_session_metadata(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #791: ?permission_mode=bypass → SessionMetadata.bypass_mode=True."""
    app.dependency_overrides[get_agent_session_manager] = lambda: fresh_manager
    _patch_start_with_mode(monkeypatch)

    project_dir = tmp_path.resolve()
    with (
        TestClient(app) as client,
        client.websocket_connect(
            f"/api/ai/chat/bypass-1?project_dir={project_dir}&permission_mode=bypass",
        ) as ws,
    ):
        ws.send_text('{"type": "user_message", "content": "hello"}')
        msg = ws.receive_json()
        assert msg["type"] == "agent_event"

    metadata = fresh_manager.load_metadata(project_dir, "bypass-1")
    assert metadata is not None
    assert metadata.bypass_mode is True


def test_ws_default_permission_mode_is_strict(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #791: omitting permission_mode defaults to STRICT, not BYPASS.

    Pre-fix behaviour hardcoded BYPASS regardless of the query string;
    this test guards against any regression to that default.
    """
    app.dependency_overrides[get_agent_session_manager] = lambda: fresh_manager
    _patch_start_with_mode(monkeypatch)

    project_dir = tmp_path.resolve()
    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/ai/chat/default-1?project_dir={project_dir}") as ws,
    ):
        ws.send_text('{"type": "user_message", "content": "hi"}')
        ws.receive_json()

    metadata = fresh_manager.load_metadata(project_dir, "default-1")
    assert metadata is not None
    assert metadata.bypass_mode is False, "default mode must be STRICT (issue #791)"


def test_ws_rejects_invalid_permission_mode(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
) -> None:
    """An unknown permission_mode value is rejected via WS close.

    FastAPI's pattern validator rejects at handshake time (HTTP 403 or
    WebSocket protocol error). The test asserts the connection cannot
    be opened with a bogus mode rather than asserting a specific
    close code, since Starlette's behaviour differs between versions.
    """
    app.dependency_overrides[get_agent_session_manager] = lambda: fresh_manager
    project_dir = tmp_path.resolve()
    with TestClient(app) as client:
        # Any exception here is acceptable — the precise close path varies
        # between Starlette versions (HTTP 403 vs WebSocketDisconnect).
        try:
            with client.websocket_connect(
                f"/api/ai/chat/bad-1?project_dir={project_dir}&permission_mode=elevated",
            ) as ws:
                # If somehow the connection opens, the next receive must
                # surface the error envelope from the close path.
                ws.receive_json()
        except Exception:
            return
        pytest.fail("websocket_connect should have raised for invalid permission_mode")


# ---------------------------------------------------------------------------
# Test 2: strict-mode policy escalates for write_workflow, approve completes the write.
# ---------------------------------------------------------------------------


def test_strict_mode_permission_check_emits_request_for_write_workflow(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """STRICT + write_workflow tool call → permission_request frame on WS.

    Approving the request should fall through ``signal_decision`` and
    return ``action=approve``. This is the protocol contract; the
    actual MCP tool execution is exercised separately via the direct
    call test below to avoid the complexity of orchestrating the full
    hook-bridge subprocess inside an in-process test.
    """
    monkeypatch.setattr(permission_module, "DECISION_TIMEOUT_SECONDS", 3.0)
    app.dependency_overrides[get_agent_session_manager] = lambda: fresh_manager
    _patch_start_with_mode(monkeypatch)

    project_dir = tmp_path.resolve()
    with (
        TestClient(app) as client,
        client.websocket_connect(
            f"/api/ai/chat/strict-pc-1?project_dir={project_dir}&permission_mode=strict",
        ) as ws,
    ):
        # Materialise the session so _active_chat_sockets has our WS.
        ws.send_text('{"type": "user_message", "content": "hi"}')
        ws.receive_json()  # init event

        # Now POST a permission-check for a write tool. The handler will
        # broadcast permission_request and await our decision. Run the
        # POST in a thread because the WS receive is blocking.
        check_result: dict[str, Any] = {}

        def _do_check() -> None:
            resp = client.post(
                "/api/ai/permission-check",
                json={
                    "tool_name": "mcp__scieasy__write_workflow",
                    "tool_input": {
                        "path": "workflows/test.yaml",
                        "yaml": "workflow: {}\n",
                    },
                    "chat_id": "strict-pc-1",
                    "project_dir": str(project_dir),
                },
            )
            check_result["status"] = resp.status_code
            check_result["body"] = resp.json()

        t = threading.Thread(target=_do_check)
        t.start()

        # Expect a permission_request frame.
        permission_frame: dict[str, Any] | None = None
        # Loop briefly because there could be stray pump events first.
        for _ in range(10):
            frame = ws.receive_json()
            if frame.get("type") == "permission_request":
                permission_frame = frame
                break
        assert permission_frame is not None, "no permission_request on STRICT mode"
        assert permission_frame["tool"]["name"] == "mcp__scieasy__write_workflow"
        request_id = permission_frame["request_id"]
        assert request_id

        # Approve via WS.
        ws.send_text(f'{{"type": "permission_decision", "request_id": "{request_id}", "decision": "approve"}}')

        t.join(timeout=5.0)
        assert check_result.get("status") == 200
        assert check_result["body"]["action"] == "approve"


# ---------------------------------------------------------------------------
# Test 3: with project_dir set, write_workflow on a relative path lands
# at the correct absolute location (issue #790 leg of the combined fix).
# ---------------------------------------------------------------------------


def test_write_workflow_after_approval_lands_at_project_relative_path(
    tmp_path: Path,
) -> None:
    """Issue #790: post-approval write places the file inside project_dir.

    This is the disk-state half of the combined regression. The
    permission flow is covered above; here we directly call the MCP
    tool to assert the path-resolution contract.
    """
    project_dir = (tmp_path / "proj").resolve()
    project_dir.mkdir()

    runtime = _StubRuntime(_project_dir=project_dir)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    try:
        result = tools_workflow.write_workflow(
            path="workflows/test.yaml",
            yaml="workflow:\n  id: e2e_test\n  version: 1.0.0\n  nodes: []\n  edges: []\n",
        )
    finally:
        _context.set_context(None)

    expected = (project_dir / "workflows" / "test.yaml").resolve()
    assert expected.is_file()
    assert Path(result["path"]).resolve() == expected
    assert Path(result["path"]).is_absolute()
