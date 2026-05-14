"""Behavioural tests for engine.pty_control IPC helpers (ADR-035 §3.10).

Exercises both the in-process handler seam (used by unit tests) and the
HTTP-loopback transport (mocked via httpx). No real PTY is spawned.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from scieasy.engine import pty_control
from scieasy.engine.pty_control import (
    PtyTabSpec,
    notify_block_pty_event,
    request_pty_tab,
    set_in_process_handler,
)


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear handler + env between tests so order is irrelevant."""
    set_in_process_handler(None)
    monkeypatch.delenv("SCIEASY_ENGINE_API_URL", raising=False)
    monkeypatch.delenv("SCIEASY_ENGINE_IPC_TOKEN", raising=False)
    yield
    set_in_process_handler(None)


def _spec() -> PtyTabSpec:
    return PtyTabSpec(
        title="🤖 extract_metadata",
        spawn_argv=["claude", "--append-system-prompt", "@/tmp/p", "--mcp-config", "/tmp/m.json"],
        cwd="/tmp/proj",
        initial_stdin="Read manifest at .scieasy/...\n",
        block_run_id="20260514-001-extract-abc123",
        permission_mode="safe",
    )


# ---------------------------------------------------------------------------
# In-process handler path
# ---------------------------------------------------------------------------


def test_request_pty_tab_in_process_returns_tab_id() -> None:
    captured: dict[str, Any] = {}

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        captured.update(payload)
        return {"tab_id": "tab-abc-123", "error": None}

    set_in_process_handler(handler)
    tab_id = request_pty_tab(_spec())
    assert tab_id == "tab-abc-123"
    assert captured["type"] == "request_pty_tab"
    assert captured["spec"]["block_run_id"] == "20260514-001-extract-abc123"
    assert captured["spec"]["permission_mode"] == "safe"


def test_request_pty_tab_in_process_engine_error_raises() -> None:
    set_in_process_handler(lambda payload: {"tab_id": None, "error": "PTY cap reached"})
    with pytest.raises(RuntimeError, match="PTY cap reached"):
        request_pty_tab(_spec())


def test_request_pty_tab_missing_tab_id_raises() -> None:
    set_in_process_handler(lambda payload: {"tab_id": "", "error": None})
    with pytest.raises(RuntimeError, match="missing tab_id"):
        request_pty_tab(_spec())


def test_request_pty_tab_non_dict_reply_raises() -> None:
    set_in_process_handler(lambda payload: ["nope"])  # type: ignore[return-value,arg-type]
    with pytest.raises(RuntimeError, match="must be a dict"):
        request_pty_tab(_spec())


def test_request_pty_tab_no_handler_no_env_raises() -> None:
    # No env, no handler — RuntimeError with actionable message.
    with pytest.raises(RuntimeError, match="SCIEASY_ENGINE_API_URL"):
        request_pty_tab(_spec())


# ---------------------------------------------------------------------------
# HTTP-loopback path (mocked transport)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, json_body: Any | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = json_body
        self.text = text

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("no json body")
        return self._json


def test_request_pty_tab_http_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_ENGINE_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("SCIEASY_ENGINE_IPC_TOKEN", "secret-token")
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kw: Any) -> _FakeResponse:
        captured["url"] = url
        captured["json"] = kw.get("json")
        captured["headers"] = kw.get("headers")
        captured["timeout"] = kw.get("timeout")
        return _FakeResponse(200, json_body={"tab_id": "tab-http-1", "error": None})

    monkeypatch.setattr(httpx, "post", fake_post)
    tab_id = request_pty_tab(_spec())
    assert tab_id == "tab-http-1"
    assert captured["url"] == "http://127.0.0.1:8000/api/ai/pty/internal/request-tab"
    assert captured["headers"]["X-SciEasy-IPC-Token"] == "secret-token"
    assert captured["json"]["type"] == "request_pty_tab"
    assert captured["timeout"] == pty_control._DEFAULT_REQUEST_TIMEOUT_S


def test_request_pty_tab_http_503_cap_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_ENGINE_API_URL", "http://127.0.0.1:8000")

    def fake_post(url: str, **kw: Any) -> _FakeResponse:
        return _FakeResponse(503, text="cap reached")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(RuntimeError, match="cap reached"):
        request_pty_tab(_spec())


def test_request_pty_tab_http_timeout_raises_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_ENGINE_API_URL", "http://127.0.0.1:8000")

    def fake_post(url: str, **kw: Any) -> _FakeResponse:
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(TimeoutError, match="timeout"):
        request_pty_tab(_spec())


def test_request_pty_tab_http_transport_error_raises_broken_pipe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_ENGINE_API_URL", "http://127.0.0.1:8000")

    def fake_post(url: str, **kw: Any) -> _FakeResponse:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(BrokenPipeError):
        request_pty_tab(_spec())


# ---------------------------------------------------------------------------
# notify_block_pty_event
# ---------------------------------------------------------------------------


def test_notify_completed_in_process() -> None:
    captured: list[dict[str, Any]] = []

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return {}

    set_in_process_handler(handler)
    notify_block_pty_event("rid-1", "completed", detail={"outputs": 2})
    assert len(captured) == 1
    msg = captured[0]
    assert msg["type"] == "notify_block_pty_event"
    assert msg["block_run_id"] == "rid-1"
    assert msg["event"] == "completed"
    assert msg["detail"] == {"outputs": 2}


def test_notify_cancelled_in_process() -> None:
    captured: list[dict[str, Any]] = []
    set_in_process_handler(lambda p: captured.append(p) or {})  # type: ignore[func-returns-value]
    notify_block_pty_event("rid-2", "cancelled_by_user_close")
    assert captured[0]["event"] == "cancelled_by_user_close"
    assert captured[0]["detail"] == {}


def test_notify_error_includes_detail() -> None:
    captured: list[dict[str, Any]] = []
    set_in_process_handler(lambda p: captured.append(p) or {})  # type: ignore[func-returns-value]
    notify_block_pty_event("rid-3", "error", detail={"stderr": "boom"})
    assert captured[0]["event"] == "error"
    assert captured[0]["detail"] == {"stderr": "boom"}


def test_notify_unknown_event_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown event"):
        notify_block_pty_event("rid", "bogus")  # type: ignore[arg-type]


def test_notify_swallows_in_process_handler_exception(caplog: pytest.LogCaptureFixture) -> None:
    def boom(payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("handler exploded")

    set_in_process_handler(boom)
    # Should NOT raise — fire-and-forget contract.
    notify_block_pty_event("rid-x", "completed")
    assert any("notify_block_pty_event" in rec.message for rec in caplog.records)


def test_notify_no_env_no_handler_logs_and_returns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # No env, no handler — should log and return cleanly (NOT raise).
    notify_block_pty_event("rid-no-env", "completed")
    assert any("SCIEASY_ENGINE_API_URL" in rec.message for rec in caplog.records)


def test_notify_http_swallows_transport_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_ENGINE_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectError("nope")),
    )
    # Must NOT raise.
    notify_block_pty_event("rid-fail", "completed")


# ---------------------------------------------------------------------------
# Dataclass shape — also covered by the skeleton test, but kept here so
# this file is self-contained.
# ---------------------------------------------------------------------------


def test_pty_tab_spec_fields() -> None:
    fields = PtyTabSpec.__dataclass_fields__
    # ``run_dir_path`` was added by the audit P1-E fix so the engine can
    # locate the AI Block run dir when handling ``block_user_marked_done``
    # WS frames (ADR-035 §3.5 path c).
    assert set(fields) == {
        "title",
        "spawn_argv",
        "cwd",
        "initial_stdin",
        "block_run_id",
        "permission_mode",
        "run_dir_path",
    }
