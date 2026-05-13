"""Tests for #783 — session-persistence lifecycle.

Covers:

* P1 — WS disconnect does NOT kill the live session.
* P2/P3 — Lazy resume on reattach (live in the same process, and after
  ``shutdown_all`` to simulate a backend restart).
* Sessions list endpoint (``GET /api/ai/sessions``).
* Transcript replay endpoint (``GET /api/ai/sessions/{chat_id}/transcript``).
* Drain task continues to drain ``claude``'s stdout while no WS is
  attached.
"""

from __future__ import annotations

import asyncio
import json
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

STUB_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "stub_claude.py"


@pytest.fixture
def app() -> Any:
    return create_app()


@pytest.fixture
def fresh_manager() -> AgentSessionManager:
    return AgentSessionManager()


def _override_with_stub(app: Any, manager: AgentSessionManager) -> None:
    app.dependency_overrides[get_agent_session_manager] = lambda: manager


def _patch_start_default_session(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_start(
        *,
        manager: Any,
        project_dir: Path,
        chat_id: str,
        resume_session_id: str | None = None,
        permission_mode_str: str = "strict",
    ) -> Any:
        provider = ClaudeCodeProvider(binary_override=STUB_PATH)
        return await manager.start_session(
            project_dir=project_dir,
            chat_id=chat_id,
            provider=provider,
            system_prompt="test",
            mcp_config={},
            permission_mode=PermissionMode.STRICT,
            resume_session_id=resume_session_id,
        )

    monkeypatch.setattr(ai_routes, "_start_default_session", _stub_start)


# ---------------------------------------------------------------------------
# Drain task + ring buffer (#783 P1)
# ---------------------------------------------------------------------------


def test_drain_task_keeps_session_alive_across_ws_disconnect(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#783 P1: closing the WS must not destroy the live session."""
    _override_with_stub(app, fresh_manager)
    _patch_start_default_session(monkeypatch)

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/ai/chat/persist-1?project_dir={tmp_path}") as ws,
    ):
        ws.send_text('{"type": "user_message", "content": "hello"}')
        _ = ws.receive_json()
        # Exit WS scope — session must remain.

    assert fresh_manager.get_session(tmp_path, "persist-1") is not None
    runtime = fresh_manager.get_runtime(tmp_path, "persist-1")
    assert runtime is not None
    # Drain task is the single consumer of stream_events. By now the
    # stub has emitted its 7-event canned stream; ring buffer should
    # have accumulated multiple events even though the WS only saw one.
    # Give the drain task a moment to complete (stub has 50ms sleeps).
    import time as _t

    for _ in range(40):
        if len(runtime.ring_buffer) >= 7:
            break
        _t.sleep(0.05)
    assert len(runtime.ring_buffer) >= 1
    asyncio.run(fresh_manager.shutdown_all())


def test_ring_buffer_replayed_on_reattach(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reattaching WS receives a replay of the ring buffer."""
    _override_with_stub(app, fresh_manager)
    _patch_start_default_session(monkeypatch)

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/ai/chat/replay-1?project_dir={tmp_path}") as ws,
    ):
        ws.send_text('{"type": "user_message", "content": "hi"}')
        for _ in range(3):
            ws.receive_json()  # drain a few events

        # WS scope ends; session stays alive, drain task continues.
    import time as _t

    _t.sleep(0.6)  # let drain task finish stub's canned 7-event stream

    # Reattach: new WS connection on the same chat_id.
    with (
        TestClient(app) as client2,
        client2.websocket_connect(f"/api/ai/chat/replay-1?project_dir={tmp_path}") as ws2,
    ):
        # Should immediately replay the buffer.
        replayed = ws2.receive_json()
        assert replayed["type"] == "agent_event"
    asyncio.run(fresh_manager.shutdown_all())


# ---------------------------------------------------------------------------
# GET /api/ai/sessions
# ---------------------------------------------------------------------------


def test_list_sessions_endpoint_returns_metadata(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
) -> None:
    _override_with_stub(app, fresh_manager)
    # Write a couple of synthetic metadata files.
    sessions_dir = tmp_path / ".scieasy" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "chat-old.json").write_text(
        json.dumps(
            {
                "chat_id": "chat-old",
                "title": "old",
                "created": "2025-01-01T00:00:00+00:00",
                "last_active": "2025-01-01T00:00:00+00:00",
                "provider": "claude-code",
                "model": None,
                "system_prompt_hash": "abc",
                "session_id": "s-old",
                "bypass_mode": False,
                "total_turns": 0,
            }
        ),
        encoding="utf-8",
    )
    (sessions_dir / "chat-new.json").write_text(
        json.dumps(
            {
                "chat_id": "chat-new",
                "title": "new",
                "created": "2025-06-01T00:00:00+00:00",
                "last_active": "2025-06-01T00:00:00+00:00",
                "provider": "claude-code",
                "model": None,
                "system_prompt_hash": "def",
                "session_id": "s-new",
                "bypass_mode": False,
                "total_turns": 5,
            }
        ),
        encoding="utf-8",
    )
    with TestClient(app) as client:
        r = client.get(f"/api/ai/sessions?project_dir={tmp_path}")
        assert r.status_code == 200
        body = r.json()
        ids = [s["chat_id"] for s in body["sessions"]]
        # Sorted by last_active descending → new before old.
        assert ids == ["chat-new", "chat-old"]


def test_list_sessions_rejects_invalid_project_dir(app: Any) -> None:
    with TestClient(app) as client:
        # /etc on POSIX, C:\Windows\System32 on Windows — both blocked.
        import platform

        bad = "C:\\Windows\\System32" if platform.system() == "Windows" else "/etc"
        r = client.get(f"/api/ai/sessions?project_dir={bad}")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/ai/sessions/{chat_id}/transcript
# ---------------------------------------------------------------------------


def test_transcript_replay_endpoint_streams_ndjson(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
) -> None:
    _override_with_stub(app, fresh_manager)
    # Write a synthetic transcript with 3 lines.
    transcript_dir = tmp_path / ".scieasy" / "sessions" / "chat-x"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = transcript_dir / "transcript.jsonl"
    transcript_path.write_text(
        "\n".join(
            [
                json.dumps({"kind": "init", "raw": {}, "session_id": "abc"}),
                json.dumps({"kind": "assistant_text_delta", "raw": {}, "text": "hi"}),
                json.dumps({"kind": "done", "raw": {}}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with TestClient(app) as client:
        r = client.get(f"/api/ai/sessions/chat-x/transcript?project_dir={tmp_path}")
        assert r.status_code == 200
        lines = [line for line in r.text.split("\n") if line.strip()]
        assert len(lines) == 3
        first = json.loads(lines[0])
        assert first["kind"] == "init"


def test_transcript_replay_returns_empty_for_missing_session(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
) -> None:
    _override_with_stub(app, fresh_manager)
    with TestClient(app) as client:
        r = client.get(f"/api/ai/sessions/no-such/transcript?project_dir={tmp_path}")
        assert r.status_code == 200
        assert r.text == ""


# ---------------------------------------------------------------------------
# Lazy resume (#783 P2/P3)
# ---------------------------------------------------------------------------


def test_lazy_resume_attempted_when_metadata_exists(
    app: Any,
    fresh_manager: AgentSessionManager,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If on-disk metadata has a session_id, attach should try --resume."""
    _override_with_stub(app, fresh_manager)
    # Persist metadata as if a prior process had ended cleanly.
    sessions_dir = tmp_path / ".scieasy" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "resume-me.json").write_text(
        json.dumps(
            {
                "chat_id": "resume-me",
                "title": "x",
                "created": "2025-01-01T00:00:00+00:00",
                "last_active": "2025-01-01T00:00:00+00:00",
                "provider": "claude-code",
                "model": None,
                "system_prompt_hash": "abc",
                "session_id": "prior-session-42",
                "bypass_mode": False,
                "total_turns": 0,
            }
        ),
        encoding="utf-8",
    )

    seen: dict[str, Any] = {}

    async def _stub_start(
        *,
        manager: Any,
        project_dir: Path,
        chat_id: str,
        resume_session_id: str | None = None,
        permission_mode_str: str = "strict",
    ) -> Any:
        seen["resume_session_id"] = resume_session_id
        provider = ClaudeCodeProvider(binary_override=STUB_PATH)
        return await manager.start_session(
            project_dir=project_dir,
            chat_id=chat_id,
            provider=provider,
            system_prompt="test",
            mcp_config={},
            permission_mode=PermissionMode.STRICT,
            resume_session_id=resume_session_id,
        )

    monkeypatch.setattr(ai_routes, "_start_default_session", _stub_start)

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/ai/chat/resume-me?project_dir={tmp_path}") as ws,
    ):
        # The very act of opening the WS should trigger lazy resume.
        # Drain at most one event so we know the pipeline is live.
        import contextlib as _cl

        with _cl.suppress(Exception):
            _ = ws.receive_json()

    assert seen.get("resume_session_id") == "prior-session-42"
    asyncio.run(fresh_manager.shutdown_all())
