"""Unit tests for ``tests/e2e/harness.py``.

These tests pin the API-wiring contract of :class:`MicroplasticsHarness`
so the three P1 defects from #771 cannot regress silently:

1. ``server_cmd`` must launch a runnable backend (uvicorn factory),
   not the dead-end ``python -m scieasy.api.app`` shape.
2. ``create_project`` must POST the real ``ProjectCreate`` payload
   (``name``/``description``/``path``), not ``{"workspace": ...}``.
3. Chat I/O must go over the WebSocket at ``/api/ai/chat/{chat_id}``
   with a ``project_dir`` query, not the non-existent
   ``/api/chats/{id}/messages`` and ``/events`` REST paths.

These tests are intentionally unmarked so they run in the default unit
test suite (``pytest -m 'not e2e'``). A separate e2e-marked smoke
test exercises the full setup→done loop against a stub backend.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from tests.e2e.harness import (
    HarnessConfig,
    MicroplasticsHarness,
    _default_server_cmd,
)

# ---------------------------------------------------------------------------
# P1 #1: server_cmd is a real, runnable backend invocation.
# ---------------------------------------------------------------------------


class TestServerCmd:
    """Pin the server entrypoint shape (P1 #1 from #771)."""

    def test_default_uses_uvicorn_factory(self) -> None:
        cmd = _default_server_cmd("127.0.0.1", 8765)
        assert cmd[0] == sys.executable
        assert "-m" in cmd
        # The argv must invoke uvicorn against the create_app *factory*.
        assert "uvicorn" in cmd
        assert "scieasy.api.app:create_app" in cmd
        assert "--factory" in cmd

    def test_default_passes_host_and_port(self) -> None:
        cmd = _default_server_cmd("127.0.0.1", 8765)
        assert "--host" in cmd
        assert "127.0.0.1" in cmd
        assert "--port" in cmd
        assert "8765" in cmd

    def test_default_does_not_use_dead_module(self) -> None:
        """Guardrail: the previous P1 shape must not silently come back."""
        cmd = _default_server_cmd("127.0.0.1", 8000)
        joined = " ".join(cmd)
        # ``python -m scieasy.api.app`` was the original P1: no __main__ exists.
        assert "scieasy.api.app " not in joined + " ", joined
        assert cmd[-1] != "scieasy.api.app"

    def test_config_lets_caller_override(self) -> None:
        custom = ("python", "stub_server.py")
        config = HarnessConfig(server_cmd=custom)
        assert config.server_cmd == custom

    def test_config_default_is_none_so_setup_picks_port_first(self) -> None:
        """``HarnessConfig.server_cmd`` defaults to ``None`` so the harness
        can fold in the post-``_pick_free_port`` port before launch."""
        config = HarnessConfig()
        assert config.server_cmd is None


# ---------------------------------------------------------------------------
# P1 #2: create_project posts the real ProjectCreate shape.
# ---------------------------------------------------------------------------


class _StubResponse:
    """Minimal urllib response stand-in: context manager + ``read()``."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def __enter__(self) -> _StubResponse:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class TestCreateProject:
    """Pin the create_project payload + URL (P1 #2 from #771)."""

    def _harness(self, tmp_path: Path) -> MicroplasticsHarness:
        h = MicroplasticsHarness(HarnessConfig(project_workspace=tmp_path))
        return h

    def test_posts_project_create_schema(self, tmp_path: Path) -> None:
        h = self._harness(tmp_path)
        captured: dict[str, Any] = {}

        def _fake_urlopen(req: Any, timeout: float = 0) -> _StubResponse:
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            captured["headers"] = {k.lower(): v for k, v in req.header_items()}
            return _StubResponse(json.dumps({"id": "proj-xyz", "name": "n", "path": str(tmp_path)}).encode())

        with mock.patch("tests.e2e.harness._http_open", side_effect=_fake_urlopen):
            chat_id = h.create_project()

        # Real route is /api/projects/ (FastAPI router prefix + @router.post("/")).
        assert captured["url"].endswith("/api/projects/")
        body = captured["body"]
        # ProjectCreate fields, NOT {"workspace": ...}.
        assert "workspace" not in body
        assert "name" in body and isinstance(body["name"], str) and body["name"]
        assert "path" in body and body["path"] == str(tmp_path)
        assert "description" in body
        # Content-Type must be JSON so FastAPI parses ProjectCreate.
        assert captured["headers"].get("content-type") == "application/json"

        # The backend returns ``id``; the harness exposes it as project_id
        # and mints a separate WebSocket chat_id.
        assert h.project_id == "proj-xyz"
        assert chat_id and chat_id.startswith("e2e-")
        assert h.chat_id == chat_id

    def test_uses_provided_name_and_description(self, tmp_path: Path) -> None:
        h = self._harness(tmp_path)
        captured_body: dict[str, Any] = {}

        def _fake(req: Any, timeout: float = 0) -> _StubResponse:
            captured_body.update(json.loads(req.data.decode()))
            return _StubResponse(b'{"id": "proj-1", "name": "alpha", "path": "/p"}')

        with mock.patch("tests.e2e.harness._http_open", side_effect=_fake):
            h.create_project(name="alpha", description="hello")

        assert captured_body["name"] == "alpha"
        assert captured_body["description"] == "hello"

    def test_create_project_before_setup_raises(self) -> None:
        h = MicroplasticsHarness(HarnessConfig(project_workspace=None))
        with pytest.raises(RuntimeError, match="before setup"):
            h.create_project()


# ---------------------------------------------------------------------------
# P1 #3: chat I/O goes over the WebSocket, not REST.
# ---------------------------------------------------------------------------


class TestChatTransport:
    """Pin the WebSocket URL + frame shape (P1 #3 from #771)."""

    def _ready_harness(self, tmp_path: Path) -> MicroplasticsHarness:
        h = MicroplasticsHarness(HarnessConfig(project_workspace=tmp_path))
        h._chat_id = "e2e-fixed-chat"
        return h

    def test_chat_ws_url_shape(self, tmp_path: Path) -> None:
        h = self._ready_harness(tmp_path)
        url = h.chat_ws_url()
        parsed = urllib.parse.urlparse(url)
        assert parsed.scheme == "ws"
        # Path must be the real AI WebSocket, not /api/chats/...
        assert parsed.path == "/api/ai/chat/e2e-fixed-chat"
        assert "/api/chats/" not in url
        # project_dir is a required query per ai.chat_ws.
        qs = urllib.parse.parse_qs(parsed.query)
        assert qs.get("project_dir") == [str(tmp_path)]

    def test_chat_ws_url_before_create_project_raises(self, tmp_path: Path) -> None:
        h = MicroplasticsHarness(HarnessConfig(project_workspace=tmp_path))
        with pytest.raises(RuntimeError, match="before create_project"):
            h.chat_ws_url()

    def test_send_prompt_opens_ws_and_emits_user_message(self, tmp_path: Path) -> None:
        h = self._ready_harness(tmp_path)

        class _FakeConn:
            def __init__(self) -> None:
                self.sent: list[str] = []
                self.closed = False

            def send(self, payload: str) -> None:
                self.sent.append(payload)

            def recv(self, timeout: float | None = None) -> str:
                raise TimeoutError

            def close(self) -> None:
                self.closed = True

        fake_conn = _FakeConn()
        captured_url: dict[str, str] = {}

        def _fake_connect(url: str, **_: Any) -> _FakeConn:
            captured_url["url"] = url
            return fake_conn

        with mock.patch("websockets.sync.client.connect", side_effect=_fake_connect):
            h.send_prompt("hello world")

        # URL is the real AI WS endpoint.
        assert "/api/ai/chat/e2e-fixed-chat" in captured_url["url"]
        assert "project_dir=" in captured_url["url"]
        # Frame shape matches ChatClientMessage (user_message, content).
        assert len(fake_conn.sent) == 1
        msg = json.loads(fake_conn.sent[0])
        assert msg == {"type": "user_message", "content": "hello world"}

    def test_wait_for_done_returns_on_inner_done_kind(self, tmp_path: Path) -> None:
        """Terminal signal is the inner ``event.kind == 'done'``."""
        h = self._ready_harness(tmp_path)

        frames = [
            json.dumps({"type": "agent_event", "event": {"kind": "init", "session_id": "s"}}),
            json.dumps({"type": "agent_event", "event": {"kind": "assistant_text_delta", "delta": "hi"}}),
            json.dumps({"type": "agent_event", "event": {"kind": "done"}}),
        ]

        class _FakeConn:
            def __init__(self, payloads: list[str]) -> None:
                self._payloads = list(payloads)
                self.closed = False

            def send(self, _payload: str) -> None:
                pass

            def recv(self, timeout: float | None = None) -> str:
                if not self._payloads:
                    raise TimeoutError
                return self._payloads.pop(0)

            def close(self) -> None:
                self.closed = True

        with mock.patch("websockets.sync.client.connect", return_value=_FakeConn(frames)):
            h.send_prompt("go")
            terminal = h.wait_for_done(timeout=5.0)

        # Terminal envelope is the last one.
        assert terminal["event"]["kind"] == "done"
        # Full transcript captured.
        assert len(h.transcript) == 3
        assert [e["event"]["kind"] for e in h.transcript] == ["init", "assistant_text_delta", "done"]

    def test_wait_for_done_returns_on_error_envelope(self, tmp_path: Path) -> None:
        """Top-level ``type == 'error'`` envelopes are also terminal."""
        h = self._ready_harness(tmp_path)
        frames = [json.dumps({"type": "error", "message": "boom"})]

        class _FakeConn:
            def __init__(self, payloads: list[str]) -> None:
                self._payloads = list(payloads)

            def send(self, _p: str) -> None:
                pass

            def recv(self, timeout: float | None = None) -> str:
                if not self._payloads:
                    raise TimeoutError
                return self._payloads.pop(0)

            def close(self) -> None:
                pass

        with mock.patch("websockets.sync.client.connect", return_value=_FakeConn(frames)):
            h.send_prompt("go")
            terminal = h.wait_for_done(timeout=5.0)

        assert terminal["type"] == "error"
