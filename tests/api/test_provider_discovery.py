"""ADR-034 Phase 1.2: tests for GET /api/ai/status."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes import ai as ai_routes


def test_status_returns_locked_shape(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Response must match the ADR-034 locked contract exactly."""

    def fake_which(name: str) -> str | None:
        return f"/fake/bin/{name}"

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if "claude" in argv[0]:
            return subprocess.CompletedProcess(argv, 0, stdout="2.1.141\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="0.118.0\n", stderr="")

    monkeypatch.setattr(ai_routes.shutil, "which", fake_which)
    monkeypatch.setattr(ai_routes.subprocess, "run", fake_run)

    res = client.get("/api/ai/status")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"providers"}
    names = {p["name"] for p in body["providers"]}
    assert names == {"claude-code", "codex"}
    for entry in body["providers"]:
        assert set(entry.keys()) == {"name", "available", "version", "logged_in"}
        assert entry["available"] is True
        assert isinstance(entry["version"], str)
        assert entry["version"]  # non-empty


def test_status_handles_missing_binaries(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """No binary on PATH → ``available=False, version=None``, no exception."""
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    res = client.get("/api/ai/status")
    assert res.status_code == 200
    body = res.json()
    for entry in body["providers"]:
        assert entry["available"] is False
        assert entry["version"] is None


def test_status_version_timeout(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """A hanging --version must time out cleanly (available=False)."""
    monkeypatch.setattr(ai_routes.shutil, "which", lambda name: f"/fake/{name}")

    def hanging_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=2)

    monkeypatch.setattr(ai_routes.subprocess, "run", hanging_run)

    res = client.get("/api/ai/status")
    assert res.status_code == 200
    body = res.json()
    for entry in body["providers"]:
        assert entry["available"] is False
        assert entry["version"] is None


def test_status_claude_logged_in_via_credentials_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Presence of ``~/.claude/.credentials.json`` flips logged_in for claude."""
    # Construct a fake HOME with a credentials.json present.
    fake_home = tmp_path / "discovery_home"
    fake_home.mkdir()
    (fake_home / ".claude").mkdir()
    (fake_home / ".claude" / ".credentials.json").write_text("{}")

    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: fake_home))
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    res = client.get("/api/ai/status")
    body = res.json()
    claude = next(p for p in body["providers"] if p["name"] == "claude-code")
    codex = next(p for p in body["providers"] if p["name"] == "codex")
    assert claude["logged_in"] is True
    # Codex has no auth.json in this fake HOME.
    assert codex["logged_in"] is False


def test_status_codex_logged_in_via_auth_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Presence of ``~/.codex/auth.json`` flips logged_in for codex."""
    fake_home = tmp_path / "discovery_home"
    fake_home.mkdir()
    (fake_home / ".codex").mkdir()
    (fake_home / ".codex" / "auth.json").write_text("{}")

    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: fake_home))
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    res = client.get("/api/ai/status")
    body = res.json()
    codex = next(p for p in body["providers"] if p["name"] == "codex")
    assert codex["logged_in"] is True


def test_status_logged_in_via_macos_keychain(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """On macOS, a Keychain hit must mark claude as logged in."""
    fake_home = tmp_path / "discovery_home"
    fake_home.mkdir()
    # Pretend we're on macOS and credentials.json is absent.
    monkeypatch.setattr(ai_routes.sys, "platform", "darwin")
    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: fake_home))
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    def fake_security(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        # `security find-generic-password -s Claude Code-credentials` returns 0
        # when the entry exists.
        if "security" in argv[0]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")

    monkeypatch.setattr(ai_routes.subprocess, "run", fake_security)

    res = client.get("/api/ai/status")
    body = res.json()
    claude = next(p for p in body["providers"] if p["name"] == "claude-code")
    assert claude["logged_in"] is True
