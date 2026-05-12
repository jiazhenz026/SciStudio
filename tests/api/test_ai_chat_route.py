"""Tests for the embedded coding agent WebSocket + status endpoints (T-ECA-107).

Exercises both the ``GET /api/ai/status`` route and the
``WS /api/ai/chat/{chat_id}`` route. The WS tests spawn real ``stub_claude.py``
subprocesses by injecting a ``ClaudeCodeProvider(binary_override=...)``
through a monkey-patched ``_start_default_session`` helper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from scieasy.ai.agent.claude_code import ClaudeCodeProvider
from scieasy.ai.agent.provider import PermissionMode, ProviderStatus
from scieasy.ai.agent.session import AgentSessionManager
from scieasy.api.app import create_app
from scieasy.api.deps import get_agent_session_manager
from scieasy.api.routes import ai as ai_routes

STUB_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "stub_claude.py"


@pytest.fixture
def app() -> Any:
    application = create_app()
    return application


@pytest.fixture
def fresh_manager() -> AgentSessionManager:
    return AgentSessionManager()


# ---------------------------------------------------------------------------
# GET /api/ai/status
# ---------------------------------------------------------------------------


def test_status_endpoint_returns_provider_list(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ProviderStatus(
        name="claude-code",
        available=True,
        binary_path=Path("/tmp/fake/claude"),
        version="0.99.0",
        logged_in=True,
        install_hint=None,
    )
    monkeypatch.setattr(
        "scieasy.ai.agent.claude_code.ClaudeCodeProvider.discover",
        classmethod(lambda _cls: fake),
    )
    with TestClient(app) as client:
        response = client.get("/api/ai/status")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body["providers"], list)
        assert body["providers"]
        item = body["providers"][0]
        assert item["name"] == "claude-code"
        assert item["available"] is True
        assert item["version"] == "0.99.0"
        assert item["logged_in"] is True


def test_status_endpoint_reports_missing_binary(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = ProviderStatus(
        name="claude-code",
        available=False,
        binary_path=None,
        version=None,
        logged_in=False,
        install_hint="install claude",
    )
    monkeypatch.setattr(
        "scieasy.ai.agent.claude_code.ClaudeCodeProvider.discover",
        classmethod(lambda _cls: fake),
    )
    with TestClient(app) as client:
        response = client.get("/api/ai/status")
        body = response.json()
        assert body["providers"][0]["available"] is False
        assert body["providers"][0]["install_hint"] == "install claude"


# ---------------------------------------------------------------------------
# WS /api/ai/chat/{chat_id}
# ---------------------------------------------------------------------------


def _override_with_stub(app: Any, manager: AgentSessionManager) -> None:
    """Pin the session-manager dependency to a fresh manager + stub_claude provider."""
    app.dependency_overrides[get_agent_session_manager] = lambda: manager


def _patch_start_default_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the route to use the stub binary instead of the real claude CLI."""

    async def _stub_start(*, manager: Any, project_dir: Path, chat_id: str) -> Any:
        provider = ClaudeCodeProvider(binary_override=STUB_PATH)
        return await manager.start_session(
            project_dir=project_dir,
            chat_id=chat_id,
            provider=provider,
            system_prompt="test",
            mcp_config={},
            permission_mode=PermissionMode.STRICT,
        )

    monkeypatch.setattr(ai_routes, "_start_default_session", _stub_start)


def test_ws_chat_happy_path(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _override_with_stub(app, fresh_manager)
    _patch_start_default_session(monkeypatch)
    with TestClient(app) as client, client.websocket_connect(f"/api/ai/chat/chat-1?project_dir={tmp_path}") as ws:
        ws.send_text('{"type": "user_message", "content": "hello"}')
        events: list[dict[str, Any]] = []
        # Expect: init, 3x assistant_text_delta, tool_use, tool_result, done.
        for _ in range(7):
            msg = ws.receive_json()
            assert msg["type"] == "agent_event"
            events.append(msg["event"])
        # Pump may continue after the connection closes; we already saw enough.
    kinds = [e["kind"] for e in events]
    assert kinds[0] == "init"
    assert "done" in kinds
    assert kinds.count("assistant_text_delta") >= 1
    assert "tool_use" in kinds
    assert "tool_result" in kinds


def test_ws_chat_invalid_message_returns_error(app: Any, fresh_manager: AgentSessionManager, tmp_path: Path) -> None:
    _override_with_stub(app, fresh_manager)
    with TestClient(app) as client, client.websocket_connect(f"/api/ai/chat/chat-invalid?project_dir={tmp_path}") as ws:
        ws.send_text("{ not json")
        response = ws.receive_json()
        assert response["type"] == "error"


def test_ws_chat_cancel_releases_session(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _override_with_stub(app, fresh_manager)
    _patch_start_default_session(monkeypatch)
    with TestClient(app) as client, client.websocket_connect(f"/api/ai/chat/chat-cancel?project_dir={tmp_path}") as ws:
        ws.send_text('{"type": "user_message", "content": "go"}')
        # Drain one event so we know the session is up.
        first = ws.receive_json()
        assert first["type"] == "agent_event"
        ws.send_text('{"type": "cancel"}')
    # After WS close the session has been released.
    assert fresh_manager.get_session(tmp_path, "chat-cancel") is None


def test_ws_chat_disconnect_closes_session(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _override_with_stub(app, fresh_manager)
    _patch_start_default_session(monkeypatch)
    with TestClient(app) as client, client.websocket_connect(f"/api/ai/chat/chat-disco?project_dir={tmp_path}") as ws:
        ws.send_text('{"type": "user_message", "content": "go"}')
        _ = ws.receive_json()
        # Connection scope exited -> finally block ran -> session released.
    assert fresh_manager.get_session(tmp_path, "chat-disco") is None
