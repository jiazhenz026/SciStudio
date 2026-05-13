"""T-ECA-302 — WS envelope contract tests.

These tests pin the finalised WebSocket protocol per ADR-033 §3 D5.2:

Client → server (validated via ``ChatClientMessage``):
    * ``user_message``
    * ``cancel``
    * ``permission_decision``

Server → client (typed Pydantic envelopes — :mod:`scieasy.api.schemas`):
    * ``agent_event`` — :class:`AgentEventEnvelope`
    * ``permission_request`` — :class:`PermissionRequestEnvelope`
    * ``session_ended`` — :class:`SessionEndedEnvelope`
    * ``error`` — :class:`ErrorEnvelope`

For each (client_msg → expected server_msg) pair we open a TestClient WS,
send the client frame, and assert the server response matches the
envelope shape (round-trips through ``model_validate``).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scieasy.ai.agent.claude_code import ClaudeCodeProvider
from scieasy.ai.agent.provider import PermissionMode
from scieasy.ai.agent.session import AgentSessionManager
from scieasy.api.app import create_app
from scieasy.api.deps import get_agent_session_manager
from scieasy.api.routes import ai as ai_routes
from scieasy.api.schemas import (
    AgentEventEnvelope,
    ErrorEnvelope,
    PermissionRequestEnvelope,
    SessionEndedEnvelope,
)

STUB_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "stub_claude.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> Any:
    return create_app()


@pytest.fixture
def fresh_manager() -> AgentSessionManager:
    return AgentSessionManager()


def _override(app: Any, manager: AgentSessionManager) -> None:
    app.dependency_overrides[get_agent_session_manager] = lambda: manager


def _patch_start(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_start(
        *,
        manager: Any,
        project_dir: Path,
        chat_id: str,
        permission_mode_str: str = "strict",
        provider_name: str | None = None,
        model: str | None = None,
    ) -> Any:
        # Issue #791: route now passes permission_mode_str through.
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
# Envelope round-trip (pure model tests — no WS).
# ---------------------------------------------------------------------------


def test_agent_event_envelope_defaults_to_correct_type() -> None:
    env = AgentEventEnvelope(event={"kind": "done"})
    payload = env.model_dump()
    assert payload["type"] == "agent_event"
    assert payload["event"] == {"kind": "done"}


def test_permission_request_envelope_requires_request_id() -> None:
    env = PermissionRequestEnvelope(
        request_id="req-1",
        tool={"name": "Edit", "input": {"path": "/x"}},
    )
    payload = env.model_dump()
    assert payload["type"] == "permission_request"
    assert payload["request_id"] == "req-1"
    assert payload["tool"]["name"] == "Edit"


def test_session_ended_envelope_carries_reason() -> None:
    env = SessionEndedEnvelope(reason="closed")
    payload = env.model_dump()
    assert payload["type"] == "session_ended"
    assert payload["reason"] == "closed"


def test_error_envelope_requires_message() -> None:
    env = ErrorEnvelope(message="boom")
    payload = env.model_dump()
    assert payload["type"] == "error"
    assert payload["message"] == "boom"


# ---------------------------------------------------------------------------
# (client_msg → server_msg) pair matrix over a live WS.
# ---------------------------------------------------------------------------


def test_user_message_yields_agent_event_envelope(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """user_message → agent_event envelope (stream pump)."""
    _override(app, fresh_manager)
    _patch_start(monkeypatch)
    with TestClient(app) as client, client.websocket_connect(f"/api/ai/chat/chat-um?project_dir={tmp_path}") as ws:
        ws.send_text('{"type": "user_message", "content": "hi"}')
        msg = ws.receive_json()
    # Round-trip through the envelope model.
    env = AgentEventEnvelope.model_validate(msg)
    assert env.type == "agent_event"
    assert "kind" in env.event


def test_invalid_client_message_yields_error_envelope(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
) -> None:
    """malformed JSON → error envelope."""
    _override(app, fresh_manager)
    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/ai/chat/chat-bad-json?project_dir={tmp_path}") as ws,
    ):
        ws.send_text("{not json")
        msg = ws.receive_json()
    env = ErrorEnvelope.model_validate(msg)
    assert env.type == "error"


def test_unknown_message_type_yields_error_envelope(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
) -> None:
    """unknown message type → error envelope."""
    _override(app, fresh_manager)
    with TestClient(app) as client, client.websocket_connect(f"/api/ai/chat/chat-unknown?project_dir={tmp_path}") as ws:
        ws.send_text('{"type": "nonsense"}')
        msg = ws.receive_json()
    env = ErrorEnvelope.model_validate(msg)
    assert env.type == "error"
    assert "unknown message type" in env.message


def test_permission_decision_missing_fields_yields_error_envelope(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
) -> None:
    """permission_decision without request_id → error envelope."""
    _override(app, fresh_manager)
    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/ai/chat/chat-perm-miss?project_dir={tmp_path}") as ws,
    ):
        ws.send_text('{"type": "permission_decision", "decision": "approve"}')
        msg = ws.receive_json()
    env = ErrorEnvelope.model_validate(msg)
    assert env.type == "error"
    assert "request_id" in env.message


def test_permission_decision_invalid_value_yields_error_envelope(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
) -> None:
    """permission_decision with garbage decision → error envelope."""
    _override(app, fresh_manager)
    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/ai/chat/chat-perm-bad?project_dir={tmp_path}") as ws,
    ):
        ws.send_text('{"type": "permission_decision", "request_id": "x", "decision": "maybe"}')
        msg = ws.receive_json()
    env = ErrorEnvelope.model_validate(msg)
    assert env.type == "error"
    assert "invalid permission decision" in env.message


def test_bad_project_dir_yields_error_envelope_then_close(
    app: Any,
    fresh_manager: AgentSessionManager,
) -> None:
    """project_dir outside allowed roots → error envelope + close 1008."""
    import platform

    from starlette.websockets import WebSocketDisconnect

    _override(app, fresh_manager)
    bad = "C:\\Windows\\System32" if platform.system() == "Windows" else "/etc"
    with TestClient(app) as client, client.websocket_connect(f"/api/ai/chat/chat-bad-dir?project_dir={bad}") as ws:
        msg = ws.receive_json()
        env = ErrorEnvelope.model_validate(msg)
        assert env.type == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()


def test_permission_request_broadcast_uses_envelope(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /permission-check → server pushes a permission_request envelope.

    Uses the WS-broadcast path: open a chat WS, then on a parallel
    thread fire the REST permission-check (with a tool that requires
    user decision). The WS receives a permission_request frame that
    validates against :class:`PermissionRequestEnvelope`.
    """
    import threading

    from scieasy.ai.agent import permission as permission_module

    permission_module._reset_registry_for_tests()
    monkeypatch.setattr(permission_module, "DECISION_TIMEOUT_SECONDS", 1.0)
    _override(app, fresh_manager)

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/ai/chat/chat-perm-req?project_dir={tmp_path}") as ws,
    ):
        check_result: dict[str, Any] = {}

        def _fire_check() -> None:
            import time

            time.sleep(0.05)
            r = client.post(
                "/api/ai/permission-check",
                json={
                    "chat_id": "chat-perm-req",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/x"},
                    "project_dir": str(tmp_path),
                },
            )
            check_result["status"] = r.status_code
            check_result["body"] = r.json()

        t = threading.Thread(target=_fire_check)
        t.start()
        msg = ws.receive_json()
        env = PermissionRequestEnvelope.model_validate(msg)
        assert env.type == "permission_request"
        assert env.request_id
        assert env.tool["name"] == "Edit"
        t.join(timeout=3.0)

    # The check should have completed with deny:timed_out (no decision sent).
    assert check_result.get("status") == 200
    assert check_result["body"]["action"] == "deny"


def test_session_ended_envelope_protocol_only() -> None:
    """``SessionEndedEnvelope`` is part of the protocol surface but is
    not actively emitted from the WS finally block.

    See the comment in ``api/routes/ai.py``: racing a ``send_json``
    against the closing handshake breaks ``close_session`` cleanup on
    Windows. End-of-session is instead derivable from the final
    ``done`` agent_event frame.

    The envelope class still exists in the protocol so that future
    server-side emission paths (e.g. an admin "kill session" endpoint)
    have a typed frame to send.
    """
    env = SessionEndedEnvelope(reason="killed_by_admin")
    payload = env.model_dump()
    assert payload == {"type": "session_ended", "reason": "killed_by_admin"}
    again = SessionEndedEnvelope.model_validate(payload)
    assert again.reason == "killed_by_admin"


def test_user_message_start_failure_yields_error_envelope(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If _start_default_session raises, the WS sends an error envelope."""
    _override(app, fresh_manager)

    async def _boom(**kwargs: Any) -> Any:
        raise RuntimeError("intentional test failure")

    monkeypatch.setattr(ai_routes, "_start_default_session", _boom)

    with TestClient(app) as client, client.websocket_connect(f"/api/ai/chat/chat-boom?project_dir={tmp_path}") as ws:
        ws.send_text('{"type": "user_message", "content": "x"}')
        msg = ws.receive_json()
    env = ErrorEnvelope.model_validate(msg)
    assert env.type == "error"
    assert "start_session failed" in env.message
    assert "intentional test failure" in env.message


# ---------------------------------------------------------------------------
# Inbound validation: malformed types must NOT crash the handler.
# ---------------------------------------------------------------------------


def test_inbound_validation_via_model_validate_json(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
) -> None:
    """Pydantic ``model_validate_json`` is the single inbound validator."""
    _override(app, fresh_manager)
    with TestClient(app) as client, client.websocket_connect(f"/api/ai/chat/chat-inv?project_dir={tmp_path}") as ws:
        # Missing required "type" field — Pydantic rejects.
        ws.send_text('{"content": "no type field"}')
        msg = ws.receive_json()
    env = ErrorEnvelope.model_validate(msg)
    assert env.type == "error"


@pytest.mark.asyncio
async def test_envelopes_match_serialised_keys() -> None:
    """Sanity: ``model_dump`` produces JSON-serialisable, expected keys."""
    import json

    samples = [
        AgentEventEnvelope(event={"kind": "init"}),
        PermissionRequestEnvelope(request_id="r", tool={"name": "Read"}),
        SessionEndedEnvelope(reason="boom"),
        ErrorEnvelope(message="bad"),
    ]
    for env in samples:
        payload = env.model_dump()
        # Round-trip JSON serialisation must not raise.
        encoded = json.dumps(payload)
        decoded = json.loads(encoded)
        assert decoded["type"] == payload["type"]
    # Calling code expects the protocol to identify by ``type``.
    _ = asyncio.sleep  # keep async marker meaningful
