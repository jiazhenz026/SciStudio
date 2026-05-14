"""ADR-034 Phase 1.2: tests for GET /api/ai/status."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scieasy.api.routes import ai as ai_routes


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


def test_status_windows_pathext_fallback(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: ``shutil.which("codex")`` on Windows can return the bare
    npm wrapper (no .exe/.cmd) which raises ``WinError 193`` when run.
    The probe must fall back through PATHEXT-style suffixes so the
    ``.cmd`` wrapper is found instead. Without this, codex installed via
    ``npm i -g`` shows up as ``available=False`` even though it works
    perfectly in a shell.
    """
    monkeypatch.setattr(ai_routes.sys, "platform", "win32")

    def fake_which(name: str) -> str | None:
        # First call (no ext) returns the bash wrapper; .cmd variant
        # returns the executable wrapper; everything else is missing.
        if name in ("claude", "codex"):
            return f"C:/fake/npm/{name}"
        if name in ("claude.cmd", "codex.cmd"):
            return f"C:/fake/npm/{name}"
        return None

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        # The bare wrapper raises just like Windows does for a Unix script;
        # the .cmd variant succeeds and prints a version.
        if argv[0].endswith(".cmd"):
            return subprocess.CompletedProcess(argv, 0, stdout="codex-cli 0.130.0\n", stderr="")
        raise OSError("[WinError 193] %1 is not a valid Win32 application")

    monkeypatch.setattr(ai_routes.shutil, "which", fake_which)
    monkeypatch.setattr(ai_routes.subprocess, "run", fake_run)

    res = client.get("/api/ai/status")
    body = res.json()
    codex = next(p for p in body["providers"] if p["name"] == "codex")
    assert codex["available"] is True, body
    assert codex["version"] == "codex-cli 0.130.0"


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
