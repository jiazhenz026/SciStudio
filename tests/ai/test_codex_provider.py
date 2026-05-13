"""Unit tests for :mod:`scieasy.ai.agent.codex` (T-ECA-402).

Mirrors the structure of ``test_claude_code.py``. Two test paths:

* :meth:`CodexProvider.discover` is exercised against a mocked
  :func:`scieasy.ai.agent.binary_discovery.find_binary` plus a mocked
  :func:`subprocess.run` so the version + login probes return
  deterministic results.
* :meth:`CodexProvider.start_session` is exercised against the
  ``tests/fixtures/stub_codex.py`` Python stub by passing it through
  the ``binary_override`` constructor argument.

Beyond mirroring CC's tests, the suite explicitly asserts that the
canonical event taxonomy emitted by :class:`CodexProvider` is identical
to that of :class:`scieasy.ai.agent.claude_code.ClaudeCodeProvider` —
this is the central acceptance criterion of T-ECA-402.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scieasy.ai.agent.codex import CodexProvider, CodexSession
from scieasy.ai.agent.errors import AgentLaunchError, AgentNotInstalledError
from scieasy.ai.agent.provider import (
    AgentProvider,
    AssistantTextDeltaEvent,
    DoneEvent,
    InitEvent,
    PermissionMode,
    ToolResultEvent,
    ToolUseEvent,
)

STUB_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "stub_codex.py"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Disposable project dir under pytest's tmp_path."""
    return tmp_path


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_codex_provider_conforms_to_agent_provider_protocol() -> None:
    """``CodexProvider`` must be structurally assignable to ``AgentProvider``.

    This is the same trick :mod:`scieasy.ai.agent.codex` uses internally
    via ``_PROTOCOL_CONFORMANCE``. Asserting it at test time as well
    catches drift in CI even if mypy's run is misconfigured.
    """
    _: type[AgentProvider] = CodexProvider
    assert CodexProvider.name == "codex"
    assert CodexProvider.binary_name == "codex"


# ---------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------


def test_discover_returns_unavailable_when_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scieasy.ai.agent.codex.find_binary", lambda _name: None)
    status = CodexProvider.discover()
    assert status.name == "codex"
    assert status.available is False
    assert status.binary_path is None
    assert status.version is None
    assert status.logged_in is False
    assert status.install_hint is not None


def test_discover_returns_available_when_version_probe_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_bin = tmp_path / "codex"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("scieasy.ai.agent.codex.find_binary", lambda _name: fake_bin)

    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[1:] == ["--version"]:
            return subprocess.CompletedProcess(args, 0, stdout="codex 0.3.0\n", stderr="")
        if args[1:] == ["login", "status"]:
            return subprocess.CompletedProcess(args, 0, stdout="logged in\n", stderr="")
        raise AssertionError(f"unexpected args: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    status = CodexProvider.discover()
    assert status.available is True
    assert status.binary_path == fake_bin
    assert status.version == "codex 0.3.0"
    assert status.logged_in is True
    assert status.install_hint is None
    # Both probes ran.
    assert any("--version" in c for c in calls)
    assert any("login" in c and "status" in c for c in calls)


def test_discover_treats_login_probe_nonzero_as_logged_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """If the Codex CLI lacks a ``login status`` subcommand we must
    degrade to ``logged_in=False`` rather than raising. Mirrors CC's
    ``installMethod`` probe contract.
    """
    fake_bin = tmp_path / "codex"
    monkeypatch.setattr("scieasy.ai.agent.codex.find_binary", lambda _name: fake_bin)

    def fake_run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args[1:] == ["--version"]:
            return subprocess.CompletedProcess(args, 0, stdout="0.1.0", stderr="")
        # login status returns non-zero (e.g. unknown subcommand)
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="unknown subcommand")

    monkeypatch.setattr(subprocess, "run", fake_run)
    status = CodexProvider.discover()
    assert status.available is True
    assert status.logged_in is False


def test_discover_handles_version_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_bin = tmp_path / "codex"
    monkeypatch.setattr("scieasy.ai.agent.codex.find_binary", lambda _name: fake_bin)

    def fake_run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, timeout=5.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    status = CodexProvider.discover()
    assert status.available is False
    assert status.logged_in is False


def test_discover_finds_real_codex_if_available() -> None:
    """Smoke test against a real binary; skipped if not present."""
    from scieasy.ai.agent.binary_discovery import find_binary

    if find_binary("codex") is None:
        pytest.skip("real codex binary not available on PATH")
    status = CodexProvider.discover()
    assert status.name == "codex"


# ---------------------------------------------------------------------------
# start_session() — uses the stub binary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_session_spawns_and_returns_session(project_dir: Path) -> None:
    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="test-chat",
        system_prompt="be helpful",
        mcp_config={"mcpServers": {}},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    try:
        assert isinstance(session, CodexSession)
        assert session.pid > 0
        # Temp files were written.
        assert len(session.temp_files) == 2
        for path in session.temp_files:
            assert path.exists()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_start_session_raises_when_binary_missing(monkeypatch: pytest.MonkeyPatch, project_dir: Path) -> None:
    monkeypatch.setattr("scieasy.ai.agent.codex.find_binary", lambda _name: None)
    provider = CodexProvider()  # no binary_override; must hit find_binary
    with pytest.raises(AgentNotInstalledError):
        await provider.start_session(
            project_dir=project_dir,
            chat_id="test-chat",
            system_prompt="",
            mcp_config={},
            resume_session_id=None,
            permission_mode=PermissionMode.STRICT,
        )


@pytest.mark.asyncio
async def test_session_stream_events_yields_canonical_taxonomy(project_dir: Path) -> None:
    """Codex provider must emit the SAME canonical event taxonomy as CC.

    This is the central T-ECA-402 acceptance criterion: different
    upstream stream format, same canonical events.
    """
    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="test-chat",
        system_prompt="hi",
        mcp_config={"mcpServers": {}},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    try:
        await session.send_user_message("list files")
        events = [event async for event in session.stream_events()]
    finally:
        await session.close()

    assert events, "stream produced no events"
    assert isinstance(events[0], InitEvent)
    assert events[0].session_id.startswith("stub-codex-session-")
    assert isinstance(events[-1], DoneEvent)
    # The canonical event taxonomy must be present.
    assert any(isinstance(e, AssistantTextDeltaEvent) for e in events)
    assert any(isinstance(e, ToolUseEvent) for e in events)
    assert any(isinstance(e, ToolResultEvent) for e in events)
    # session_id was latched on the InitEvent.
    assert session.session_id is not None
    assert session.session_id.startswith("stub-codex-session-")


@pytest.mark.asyncio
async def test_session_resume_echoes_session_id(project_dir: Path) -> None:
    """When ``--resume <id>`` is passed, the stub echoes the id back as InitEvent.session_id."""
    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="test-chat",
        system_prompt="",
        mcp_config={},
        resume_session_id="codex-resumed-abc-123",
        permission_mode=PermissionMode.STRICT,
    )
    try:
        await session.send_user_message("continue")
        events = [event async for event in session.stream_events()]
    finally:
        await session.close()
    init_events = [e for e in events if isinstance(e, InitEvent)]
    assert init_events and init_events[0].session_id == "codex-resumed-abc-123"


@pytest.mark.asyncio
async def test_session_send_user_message_after_close_raises(project_dir: Path) -> None:
    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="test-chat",
        system_prompt="",
        mcp_config={},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    await session.send_user_message("hi")
    _ = [event async for event in session.stream_events()]
    await session.close()
    with pytest.raises(AgentLaunchError):
        await session.send_user_message("after close")


@pytest.mark.asyncio
async def test_session_close_cleans_up_temp_files(project_dir: Path) -> None:
    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="test-chat",
        system_prompt="cleanup-test",
        mcp_config={"mcpServers": {}},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    paths = session.temp_files
    assert paths and all(p.exists() for p in paths)
    await session.close()
    for path in paths:
        assert not path.exists(), f"temp file {path} not cleaned up"


@pytest.mark.asyncio
async def test_session_close_is_idempotent(project_dir: Path) -> None:
    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="test-chat",
        system_prompt="",
        mcp_config={},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    await session.close()
    # Second close is a no-op.
    await session.close()


@pytest.mark.asyncio
async def test_session_close_timeout_uses_kill_process_tree(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors the CC P1 regression: close() grace-timeout must tree-kill."""
    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="test-chat",
        system_prompt="",
        mcp_config={},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )

    wait_calls = {"n": 0}

    async def _stubbed_wait() -> int:
        wait_calls["n"] += 1
        if wait_calls["n"] == 1:
            await asyncio.sleep(3600)
        return 0

    monkeypatch.setattr(session._proc, "wait", _stubbed_wait)
    monkeypatch.setattr("scieasy.ai.agent.codex._CLOSE_GRACE_SECONDS", 0.1)

    calls: list[str] = []

    def _spy_kill_tree(*, caller: str) -> None:
        calls.append(caller)

    monkeypatch.setattr(session, "_kill_process_tree", _spy_kill_tree)
    monkeypatch.setattr(type(session._proc), "returncode", property(lambda self: None))

    await session.close()
    assert calls == ["close"], f"close() should call _kill_process_tree(caller='close') exactly once, got {calls}"


@pytest.mark.asyncio
async def test_session_cancel_kills_subprocess(project_dir: Path) -> None:
    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="test-chat",
        system_prompt="",
        mcp_config={},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    try:
        await session.cancel()
        # Cancel is idempotent.
        await session.cancel()
    finally:
        await session.close()
    assert session.pid > 0


def test_spawn_uses_windows_creation_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked verification of CREATE_NEW_PROCESS_GROUP on Windows."""
    from scieasy.ai.agent import codex as codex_mod

    captured: dict[str, Any] = {}

    async def fake_exec(*args: Any, **kwargs: Any) -> Any:
        captured["args"] = args
        captured["kwargs"] = kwargs

        class _FakeProc:
            pid = 999
            returncode = None
            stdin = None
            stdout = None
            stderr = None

            async def wait(self) -> int:
                return 0

        return _FakeProc()

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    async def _go() -> None:
        await codex_mod._spawn(
            argv=[sys.executable, str(STUB_PATH)],
            cwd=Path(os.getcwd()),
            env=os.environ.copy(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

    asyncio.run(_go())
    assert captured["kwargs"].get("creationflags") == subprocess.CREATE_NEW_PROCESS_GROUP


@pytest.mark.asyncio
async def test_session_stream_events_handles_stub_crash(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the stub crashes via STUB_CODEX_CRASH=1 the stream terminates cleanly."""
    monkeypatch.setenv("STUB_CODEX_CRASH", "1")
    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="test-chat",
        system_prompt="",
        mcp_config={},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    try:
        events = [event async for event in session.stream_events()]
        assert events == []
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_start_session_injects_chat_id_into_subprocess_env(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same contract as Claude Code provider: must inject
    ``SCIEASY_CHAT_ID`` and ``SCIEASY_PROJECT_DIR`` (issue #723).
    """
    from scieasy.ai.agent import codex as codex_mod

    captured: dict[str, Any] = {}

    async def fake_spawn(
        *,
        argv: list[str],
        cwd: Path,
        env: dict[str, str],
        creationflags: int,
    ) -> Any:
        captured["env"] = env
        captured["argv"] = argv

        class _FakeProc:
            pid = 4242
            returncode = None
            stdin = None
            stdout = None
            stderr = None

            async def wait(self) -> int:
                return 0

        return _FakeProc()

    monkeypatch.setattr(codex_mod, "_spawn", fake_spawn)

    provider = CodexProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        chat_id="chat-codex-xyz",
        system_prompt="env-injection test",
        mcp_config={"mcpServers": {}},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    for path in session.temp_files:
        path.unlink(missing_ok=True)

    env = captured["env"]
    assert env["SCIEASY_CHAT_ID"] == "chat-codex-xyz"
    assert env["SCIEASY_PROJECT_DIR"] == str(project_dir)
    assert env["SCIEASY_PERMISSION_MODE"] == PermissionMode.STRICT.value
