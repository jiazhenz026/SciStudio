"""Behavior tests for ``ai_pty._internal_routes`` (issue #1432).

Direct unit tests on ``_ensure_ipc_token`` / ``_check_ipc_token``
without touching the FastAPI request path. The HTTP-level behaviour
is already covered by ``tests/api/test_ai_pty_audit_fixes.py`` and
``tests/api/test_ai_pty_engine_spawn.py``; this file pins the helpers
that those tests depend on.
"""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

from scistudio.api.routes.ai_pty.internal_routes import (
    _check_ipc_token,
    _ensure_ipc_token,
)


@pytest.fixture(autouse=True)
def _isolate_ipc_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wipe ``SCISTUDIO_ENGINE_IPC_TOKEN`` so each test starts fresh."""
    monkeypatch.delenv("SCISTUDIO_ENGINE_IPC_TOKEN", raising=False)


def test_ensure_ipc_token_generates_on_first_call() -> None:
    """When the env var is unset, ``_ensure_ipc_token`` mints one."""
    assert os.environ.get("SCISTUDIO_ENGINE_IPC_TOKEN", "") == ""
    tok = _ensure_ipc_token()
    assert tok
    # Side-effect: env var is now populated so child workers can inherit.
    assert os.environ["SCISTUDIO_ENGINE_IPC_TOKEN"] == tok


def test_ensure_ipc_token_idempotent_with_existing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the env var is already set, the existing value is returned."""
    monkeypatch.setenv("SCISTUDIO_ENGINE_IPC_TOKEN", "pre-existing-token")
    assert _ensure_ipc_token() == "pre-existing-token"
    # Second call still returns the same value, never mints a new one.
    assert _ensure_ipc_token() == "pre-existing-token"


def test_check_ipc_token_rejects_missing_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``None`` header against a configured engine token raises 401."""
    monkeypatch.setenv("SCISTUDIO_ENGINE_IPC_TOKEN", "engine-secret")
    with pytest.raises(HTTPException) as exc_info:
        _check_ipc_token(None)
    assert exc_info.value.status_code == 401


def test_check_ipc_token_rejects_wrong_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mismatched header raises 401."""
    monkeypatch.setenv("SCISTUDIO_ENGINE_IPC_TOKEN", "engine-secret")
    with pytest.raises(HTTPException) as exc_info:
        _check_ipc_token("attacker-guess")
    assert exc_info.value.status_code == 401


def test_check_ipc_token_rejects_when_engine_unconfigured() -> None:
    """If the engine never set a token, no client header may pass.

    Defends against a worker accidentally authenticating against a
    half-initialised engine process.
    """
    # ``_isolate_ipc_token_env`` already deleted the env var.
    with pytest.raises(HTTPException) as exc_info:
        _check_ipc_token("anything")
    assert exc_info.value.status_code == 401


def test_check_ipc_token_accepts_matching_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A matching token returns silently (no exception)."""
    monkeypatch.setenv("SCISTUDIO_ENGINE_IPC_TOKEN", "engine-secret")
    # Should not raise.
    _check_ipc_token("engine-secret")
