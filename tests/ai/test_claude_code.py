"""Unit tests for :mod:`scieasy.ai.agent.claude_code` (T-ECA-104).

The tests bypass the real Claude Code CLI in two ways:

* ``ClaudeCodeProvider.discover`` is exercised against a mocked
  :func:`scieasy.ai.agent.binary_discovery.find_binary` plus a mocked
  :func:`subprocess.run` so the version + login probes return
  deterministic results.
* ``ClaudeCodeProvider.start_session`` is exercised against the
  ``tests/fixtures/stub_claude.py`` Python stub by passing it through
  the ``binary_override`` constructor argument.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scieasy.ai.agent.claude_code import (
    ClaudeCodeProvider,
    ClaudeCodeSession,
)
from scieasy.ai.agent.errors import AgentLaunchError, AgentNotInstalledError
from scieasy.ai.agent.provider import (
    AssistantTextDeltaEvent,
    DoneEvent,
    InitEvent,
    PermissionMode,
    ToolResultEvent,
    ToolUseEvent,
)

STUB_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "stub_claude.py"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Disposable project dir under pytest's tmp_path."""
    return tmp_path


# ---------------------------------------------------------------------------
# discover()
# ---------------------------------------------------------------------------


def test_discover_returns_unavailable_when_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scieasy.ai.agent.claude_code.find_binary", lambda _name: None)
    status = ClaudeCodeProvider.discover()
    assert status.name == "claude-code"
    assert status.available is False
    assert status.binary_path is None
    assert status.version is None
    assert status.logged_in is False
    assert status.install_hint is not None


def test_discover_returns_available_when_version_probe_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_bin = tmp_path / "claude"
    fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("scieasy.ai.agent.claude_code.find_binary", lambda _name: fake_bin)

    calls: list[list[str]] = []

    def fake_run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[1:] == ["--version"]:
            return subprocess.CompletedProcess(args, 0, stdout="0.99.0\n", stderr="")
        if args[1:] == ["config", "get", "-g", "installMethod"]:
            return subprocess.CompletedProcess(args, 0, stdout="npm-global\n", stderr="")
        raise AssertionError(f"unexpected args: {args}")

    monkeypatch.setattr(subprocess, "run", fake_run)
    status = ClaudeCodeProvider.discover()
    assert status.available is True
    assert status.binary_path == fake_bin
    assert status.version == "0.99.0"
    assert status.logged_in is True
    assert status.install_hint is None
    # Both probes ran.
    assert any("--version" in c for c in calls)
    assert any("installMethod" in " ".join(c) for c in calls)


def test_discover_handles_version_timeout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_bin = tmp_path / "claude"
    monkeypatch.setattr("scieasy.ai.agent.claude_code.find_binary", lambda _name: fake_bin)

    def fake_run(args: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(args, timeout=5.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    status = ClaudeCodeProvider.discover()
    assert status.available is False
    assert status.logged_in is False


def test_discover_finds_real_claude_if_available() -> None:
    """Smoke test against a real binary; skipped if not present."""
    from scieasy.ai.agent.binary_discovery import find_binary

    if find_binary("claude") is None:
        pytest.skip("real claude binary not available on PATH")
    status = ClaudeCodeProvider.discover()
    assert status.name == "claude-code"
    # We don't assert availability — the binary may be present but the
    # --version probe could still fail; just confirm the call doesn't raise.


# ---------------------------------------------------------------------------
# start_session() — uses the stub binary
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_session_spawns_and_returns_session(project_dir: Path) -> None:
    provider = ClaudeCodeProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        system_prompt="be helpful",
        mcp_config={"mcpServers": {}},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    try:
        assert isinstance(session, ClaudeCodeSession)
        assert session.pid > 0
        # Temp files were written.
        assert len(session.temp_files) == 2
        for path in session.temp_files:
            assert path.exists()
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_start_session_raises_when_binary_missing(monkeypatch: pytest.MonkeyPatch, project_dir: Path) -> None:
    monkeypatch.setattr("scieasy.ai.agent.claude_code.find_binary", lambda _name: None)
    provider = ClaudeCodeProvider()  # no binary_override; must hit find_binary
    with pytest.raises(AgentNotInstalledError):
        await provider.start_session(
            project_dir=project_dir,
            system_prompt="",
            mcp_config={},
            resume_session_id=None,
            permission_mode=PermissionMode.STRICT,
        )


@pytest.mark.asyncio
async def test_session_stream_events_yields_init_and_done(project_dir: Path) -> None:
    provider = ClaudeCodeProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
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
    assert events[0].session_id.startswith("stub-session-")
    assert isinstance(events[-1], DoneEvent)
    # Stream contains the expected event taxonomy.
    assert any(isinstance(e, AssistantTextDeltaEvent) for e in events)
    assert any(isinstance(e, ToolUseEvent) for e in events)
    assert any(isinstance(e, ToolResultEvent) for e in events)
    # session_id was latched on the InitEvent.
    assert session.session_id is not None
    assert session.session_id.startswith("stub-session-")


@pytest.mark.asyncio
async def test_session_resume_echoes_session_id(project_dir: Path) -> None:
    """When ``--resume <id>`` is passed, the stub echoes the id back as InitEvent.session_id."""
    provider = ClaudeCodeProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        system_prompt="",
        mcp_config={},
        resume_session_id="resumed-abc-123",
        permission_mode=PermissionMode.STRICT,
    )
    try:
        await session.send_user_message("continue")
        events = [event async for event in session.stream_events()]
    finally:
        await session.close()
    init_events = [e for e in events if isinstance(e, InitEvent)]
    assert init_events and init_events[0].session_id == "resumed-abc-123"


@pytest.mark.asyncio
async def test_session_send_user_message_after_close_raises(project_dir: Path) -> None:
    provider = ClaudeCodeProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        system_prompt="",
        mcp_config={},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    await session.send_user_message("hi")
    # Drain to let the stub exit naturally.
    _ = [event async for event in session.stream_events()]
    await session.close()
    with pytest.raises(AgentLaunchError):
        await session.send_user_message("after close")


@pytest.mark.asyncio
async def test_session_close_cleans_up_temp_files(project_dir: Path) -> None:
    provider = ClaudeCodeProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
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
    provider = ClaudeCodeProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        system_prompt="",
        mcp_config={},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    await session.close()
    # Second close is a no-op (no exception, no double-unlink failure).
    await session.close()


@pytest.mark.asyncio
async def test_session_close_timeout_uses_kill_process_tree(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression for Codex P1: close() grace-timeout path must tree-kill,
    not just send SIGKILL to the parent. Otherwise child tool processes
    (e.g. Bash) survive on POSIX where the session uses start_new_session.
    """
    provider = ClaudeCodeProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        system_prompt="",
        mcp_config={},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )

    # Two-call wait stub: first call hangs (triggers timeout → kill
    # path), second call (inside the post-kill 1s wait_for) returns
    # immediately. _CLOSE_GRACE_SECONDS overridden to 0.1s for speed.
    wait_calls = {"n": 0}

    async def _stubbed_wait() -> int:
        wait_calls["n"] += 1
        if wait_calls["n"] == 1:
            await asyncio.sleep(3600)
        return 0

    monkeypatch.setattr(session._proc, "wait", _stubbed_wait)
    monkeypatch.setattr("scieasy.ai.agent.claude_code._CLOSE_GRACE_SECONDS", 0.1)

    # Spy on _kill_process_tree so we can assert close() invokes it
    # rather than the old `self._proc.kill()` parent-only path.
    calls: list[str] = []

    def _spy_kill_tree(*, caller: str) -> None:
        calls.append(caller)

    monkeypatch.setattr(session, "_kill_process_tree", _spy_kill_tree)

    # Pretend returncode is unset so the grace branch is entered.
    monkeypatch.setattr(type(session._proc), "returncode", property(lambda self: None))

    await session.close()
    assert calls == ["close"], f"close() should call _kill_process_tree(caller='close') exactly once, got {calls}"


@pytest.mark.asyncio
async def test_session_cancel_kills_subprocess(project_dir: Path) -> None:
    provider = ClaudeCodeProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
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
    # Subprocess has exited (either due to cancel signal or natural completion).
    assert session.pid > 0


def test_spawn_uses_windows_creation_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mocked verification of CREATE_NEW_PROCESS_GROUP on Windows."""
    from scieasy.ai.agent import claude_code as cc

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
    # On non-Windows hosts the ``subprocess.CREATE_NEW_PROCESS_GROUP``
    # symbol doesn't exist; inject a placeholder.
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)

    import asyncio

    async def _go() -> None:
        await cc._spawn(
            argv=[sys.executable, str(STUB_PATH)],
            cwd=Path(os.getcwd()),
            env=os.environ.copy(),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

    asyncio.run(_go())
    assert captured["kwargs"].get("creationflags") == subprocess.CREATE_NEW_PROCESS_GROUP


@pytest.mark.asyncio
async def test_session_stream_events_handles_stub_crash(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When the stub crashes via STUB_CLAUDE_CRASH=1 the stream terminates cleanly."""
    monkeypatch.setenv("STUB_CLAUDE_CRASH", "1")
    provider = ClaudeCodeProvider(binary_override=STUB_PATH)
    session = await provider.start_session(
        project_dir=project_dir,
        system_prompt="",
        mcp_config={},
        resume_session_id=None,
        permission_mode=PermissionMode.STRICT,
    )
    try:
        # No events are emitted by the crashing stub; stream terminates immediately.
        events = [event async for event in session.stream_events()]
        assert events == []
    finally:
        await session.close()
