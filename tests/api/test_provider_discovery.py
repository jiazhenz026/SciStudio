"""Tests for ``GET /api/ai/status`` (ADR-034 Phase 1.2 + multi-provider).

ADR-034 multi-provider (T-005, T-006) made this endpoint registry-driven. The
assertions below therefore compare against
``providers_registry.agent_keys()`` rather than a frozen literal set: a frozen
set is exactly the duplication FR-001 removes, and spec §4.4 calls the
replacement out explicitly. Every login-state test drives a **fake HOME**, so
nothing here depends on which agent CLIs happen to be installed on the machine
running the suite.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.ai.agent import providers_registry
from scistudio.api.routes import ai as ai_routes

_ENTRY_KEYS = {"name", "available", "version", "logged_in", "label"}


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every ``Path.home()`` lookup at an empty throwaway directory.

    Both the route's credential probes and the registry's well-known-directory
    scan resolve through ``Path.home()``, so patching it here is what keeps
    these tests independent of the developer's real installs.
    """
    home = tmp_path / "discovery_home"
    home.mkdir()
    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    return home


def _which_bare_only(name: str) -> str | None:
    """PATH stub that answers only extension-less names.

    ``resolve_executable`` deliberately prefers an extensioned Windows launcher
    when one is on PATH — npm global installs ship both ``codex`` (a Unix shell
    wrapper pywinpty cannot execute) and ``codex.cmd``. A stub that answered
    *every* spelling would therefore resolve to ``claude.cmd`` on Windows and to
    ``claude`` elsewhere, making the argv assertions below platform-dependent.
    Answering only the bare name models a non-npm install and keeps them stable.
    """
    if Path(name).suffix:
        return None
    return f"/fake/bin/{name}"


def _entry(body: dict[str, object], name: str) -> dict[str, object]:
    providers = body["providers"]
    assert isinstance(providers, list)
    return next(p for p in providers if p["name"] == name)


def test_status_covers_every_registry_agent_in_order(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """One entry per ``agent_keys()``, in registry order, with the FR-008 shape.

    Deliberately not a frozen ``{"claude-code", "codex"}`` literal: adding a
    provider to the registry must extend this endpoint with no test edit
    (User Story 7), and spec §4.4 requires the set to be compared against the
    registry.
    """
    monkeypatch.setattr(ai_routes.shutil, "which", _which_bare_only)
    monkeypatch.setattr(
        ai_routes.subprocess,
        "run",
        lambda argv, **_: subprocess.CompletedProcess(argv, 0, stdout="1.2.3\n", stderr=""),
    )

    res = client.get("/api/ai/status")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"providers"}

    expected = list(providers_registry.agent_keys())
    assert [p["name"] for p in body["providers"]] == expected
    assert len(expected) == 5  # guards against the registry silently shrinking

    for entry in body["providers"]:
        assert set(entry.keys()) == _ENTRY_KEYS
        assert entry["available"] is True
        assert isinstance(entry["version"], str)
        assert entry["version"]


def test_status_excludes_the_user_terminal_pseudo_provider(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """FR-003: ``user-terminal`` is a shell, not a selectable chat agent."""
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    body = client.get("/api/ai/status").json()
    names = {p["name"] for p in body["providers"]}
    assert "user-terminal" not in names
    assert "user-terminal" in providers_registry.provider_keys()


def test_status_label_comes_from_the_registry(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """FR-020b: labels are backend-supplied so the frontend needs no label map."""
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    body = client.get("/api/ai/status").json()
    labels = {p["name"]: p["label"] for p in body["providers"]}
    assert labels == {d.key: d.label for d in providers_registry.agent_descriptors()}
    # The two Qoder channels must be distinguishable in the picker (FR-025).
    assert labels["qoder"] != labels["qoder-cn"]


def test_status_handles_missing_binaries(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """No binary anywhere → ``available=False, version=None``, no exception."""
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    res = client.get("/api/ai/status")
    assert res.status_code == 200
    body = res.json()
    assert body["providers"]
    for entry in body["providers"]:
        assert entry["available"] is False
        assert entry["version"] is None


def test_status_version_timeout(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    fake_home: Path,
) -> None:
    """A hanging ``--version`` times out at 2 s and reports unavailable.

    Spec §2 Edge Cases: the probe must never block the endpoint, so a provider
    whose binary exists but hangs is reported ``available: false`` rather than
    stalling the response.
    """
    monkeypatch.setattr(ai_routes.shutil, "which", _which_bare_only)

    seen_timeouts: list[object] = []

    def hanging_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen_timeouts.append(kwargs.get("timeout"))
        raise subprocess.TimeoutExpired(cmd=argv[0], timeout=2)

    monkeypatch.setattr(ai_routes.subprocess, "run", hanging_run)

    res = client.get("/api/ai/status")
    assert res.status_code == 200
    body = res.json()
    for entry in body["providers"]:
        assert entry["available"] is False
        assert entry["version"] is None
    assert seen_timeouts
    assert set(seen_timeouts) == {2}


# ---------------------------------------------------------------------------
# FR-005 — off-PATH discovery agrees with the AI Block path
# ---------------------------------------------------------------------------


def test_status_finds_a_provider_installed_only_off_path(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A CLI present only in its well-known dir must report ``available: true``.

    None of Kimi Code or either Qoder channel is on PATH by default, so a status
    endpoint that only consulted ``shutil.which`` would report every one of them
    uninstalled. This is the FR-005 agreement between the chat path and the AI
    Block path: both go through ``providers_registry.resolve_binary``.
    """
    home = tmp_path / "offpath_home"
    kimi_bin = home / ".kimi-code" / "bin"
    kimi_bin.mkdir(parents=True)
    installed = kimi_bin / "kimi.cmd"
    installed.write_text("@echo kimi", encoding="utf-8")
    # A non-Windows run resolves the extension-less name instead.
    (kimi_bin / "kimi").write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)  # nothing on PATH

    probed: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        probed.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="0.33.0\n", stderr="")

    monkeypatch.setattr(ai_routes.subprocess, "run", fake_run)

    body = client.get("/api/ai/status").json()
    kimi = _entry(body, "kimi-code")
    assert kimi["available"] is True
    assert kimi["version"] == "0.33.0"
    # The version probe ran against the off-PATH binary, not a bare name.
    assert any(str(kimi_bin) in argv[0] for argv in probed)

    # A provider with nothing installed anywhere stays unavailable.
    assert _entry(body, "qoder")["available"] is False


def test_status_prefers_the_cmd_launcher_over_a_bare_npm_wrapper(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """npm ships both ``codex`` and ``codex.cmd``; the probe must use the ``.cmd``.

    The bare file is a Unix shell wrapper that pywinpty's CreateProcess spawn
    path cannot execute, so a status probe that reported the bare wrapper would
    disagree with what the spawn path actually runs. Kept here, at the endpoint's
    own helper, because ``_binary_status`` is the caller that has to preserve it
    now that discovery is descriptor-driven.
    """
    home = tmp_path / "npm_home"
    home.mkdir()
    npm_dir = "C:/Users/dev/AppData/Roaming/npm"
    shims = {"codex": f"{npm_dir}/codex", "codex.cmd": f"{npm_dir}/codex.cmd"}

    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="codex 0.1.0\n", stderr="")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.shutil, "which", shims.get)
    monkeypatch.setattr(ai_routes.subprocess, "run", fake_run)

    expected_binary = str(Path(f"{npm_dir}/codex.cmd"))
    assert ai_routes._binary_status(providers_registry.get("codex")) == (
        expected_binary,
        True,
        "codex 0.1.0",
    )
    assert calls == [[expected_binary, "--version"]]


def test_status_honours_kimi_code_home_override(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """``KIMI_CODE_HOME`` relocates both Kimi's install dir and its credentials.

    Kimi's own documentation instructs callers never to assume ``~/.kimi-code``
    (spec §2 Edge Cases), and the descriptor hangs both paths off the resolved
    config root so one environment variable moves them together.
    """
    home = tmp_path / "empty_home"
    home.mkdir()
    kimi_home = tmp_path / "elsewhere" / "kimi"
    (kimi_home / "bin").mkdir(parents=True)
    (kimi_home / "bin" / "kimi").write_text("#!/bin/sh\n", encoding="utf-8")
    (kimi_home / "bin" / "kimi.cmd").write_text("@echo kimi", encoding="utf-8")
    (kimi_home / "credentials").mkdir(parents=True)
    (kimi_home / "credentials" / "kimi-code.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)
    monkeypatch.setenv("KIMI_CODE_HOME", str(kimi_home))
    monkeypatch.setattr(
        ai_routes.subprocess,
        "run",
        lambda argv, **_: subprocess.CompletedProcess(argv, 0, stdout="0.33.0\n", stderr=""),
    )

    kimi = _entry(client.get("/api/ai/status").json(), "kimi-code")
    assert kimi["available"] is True
    assert kimi["logged_in"] is True


# ---------------------------------------------------------------------------
# FR-009 — descriptor-driven credential probes, per provider
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("provider", "credential_relpath"),
    [
        ("claude-code", (".claude", ".credentials.json")),
        ("codex", (".codex", "auth.json")),
        ("kimi-code", (".kimi-code", "credentials", "kimi-code.json")),
        ("qoder", (".qoder", ".auth")),
        ("qoder-cn", (".qoder-cn", ".auth")),
    ],
)
def test_status_logged_in_via_credential_file(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    credential_relpath: tuple[str, ...],
) -> None:
    """Each provider's own credential file — and only its own — flips it logged in.

    Driven off a fake HOME rather than the machine's real one, so the result is
    identical on a developer box with five CLIs installed and in CI with none.
    The parametrised paths double as an executable transcription of the spec §1
    credential-path row.
    """
    home = tmp_path / f"home_{provider}"
    credential = home.joinpath(*credential_relpath)
    credential.parent.mkdir(parents=True)
    credential.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    body = client.get("/api/ai/status").json()
    logged_in = {p["name"]: p["logged_in"] for p in body["providers"]}
    assert logged_in[provider] is True
    others = {name: value for name, value in logged_in.items() if name != provider}
    assert others == dict.fromkeys(others, False)


def test_status_qoder_channels_do_not_share_login_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Each Qoder channel reads ``.auth`` under its **own** config root (FR-025).

    Neither channel exposes a machine-readable auth status command, so the file
    check is the only signal — which makes cross-channel leakage the specific
    failure mode worth pinning.
    """
    home = tmp_path / "qoder_home"
    (home / ".qoder-cn").mkdir(parents=True)
    (home / ".qoder-cn" / ".auth").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.shutil, "which", lambda _name: None)

    body = client.get("/api/ai/status").json()
    assert _entry(body, "qoder-cn")["logged_in"] is True
    assert _entry(body, "qoder")["logged_in"] is False


@pytest.mark.parametrize(
    ("provider", "auth_argv"),
    [
        ("claude-code", ["auth", "status", "--json"]),
        ("codex", ["login", "status"]),
        ("kimi-code", ["doctor"]),
    ],
)
def test_status_logged_in_via_provider_auth_status_command(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    auth_argv: list[str],
) -> None:
    """With no credential file, the descriptor's auth status command decides.

    This is what lets SciStudio see keychain/keyring-stored credentials (current
    Codex builds) without probing the OS keychain itself. Exit 0 means logged in;
    every other provider's command exits non-zero here, so a passing assertion
    proves the *right* command ran.
    """
    home = tmp_path / f"authcmd_home_{provider}"
    home.mkdir()
    descriptor = providers_registry.get(provider)
    # ``resolve_binary`` returns a ``Path``, so the argv the route builds carries
    # the platform's own separators rather than the stub's forward slashes.
    binary = str(Path(f"/fake/bin/{descriptor.binary_candidates[0]}"))

    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.shutil, "which", _which_bare_only)

    seen: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        if argv[1:] == ["--version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="1.2.3\n", stderr="")
        if argv == [binary, *auth_argv]:
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not logged in")

    monkeypatch.setattr(ai_routes.subprocess, "run", fake_run)

    body = client.get("/api/ai/status").json()
    logged_in = {p["name"]: p["logged_in"] for p in body["providers"]}
    assert logged_in[provider] is True
    assert [binary, *auth_argv] in seen
    # Neither Qoder channel declares an auth status command; with no ``.auth``
    # file they must stay logged out rather than borrowing another CLI's result.
    assert logged_in["qoder"] is False
    assert logged_in["qoder-cn"] is False


def test_status_qoder_channels_run_no_auth_status_command(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """No auth status command was observed on either channel at 1.1.15.

    A probe that invented one would run an unknown subcommand on a user's CLI on
    every Setup-screen render.
    """
    home = tmp_path / "no_auth_cmd_home"
    home.mkdir()

    monkeypatch.setattr(ai_routes.Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setattr(ai_routes.shutil, "which", _which_bare_only)

    seen: list[list[str]] = []

    def fake_run(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="1.1.15\n", stderr="")

    monkeypatch.setattr(ai_routes.subprocess, "run", fake_run)

    body = client.get("/api/ai/status").json()
    assert _entry(body, "qoder")["available"] is True
    assert _entry(body, "qoder")["logged_in"] is False
    qoder_calls = [argv for argv in seen if "qodercli" in argv[0]]
    assert qoder_calls
    assert all(argv[1:] == ["--version"] for argv in qoder_calls)
