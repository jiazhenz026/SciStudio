"""Unit tests for :mod:`scieasy.ai.agent.session` (T-ECA-106).

The manager is exercised against the ``stub_claude.py`` test fixture
(via :class:`scieasy.ai.agent.claude_code.ClaudeCodeProvider`'s
``binary_override``) so no real ``claude`` binary is required.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scieasy.ai.agent.claude_code import ClaudeCodeProvider
from scieasy.ai.agent.errors import AgentSessionError
from scieasy.ai.agent.provider import PermissionMode
from scieasy.ai.agent.session import (
    AgentSessionManager,
    SessionMetadata,
    get_session_manager,
    set_session_manager,
)

STUB_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "stub_claude.py"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def provider() -> ClaudeCodeProvider:
    return ClaudeCodeProvider(binary_override=STUB_PATH)


@pytest.mark.asyncio
async def test_start_session_writes_metadata_and_returns_session(
    project_dir: Path, provider: ClaudeCodeProvider
) -> None:
    manager = AgentSessionManager()
    session = await manager.start_session(
        project_dir=project_dir,
        chat_id="chat-1",
        provider=provider,
        system_prompt="prompt-1",
        mcp_config={"mcpServers": {}},
        permission_mode=PermissionMode.STRICT,
    )
    try:
        # Metadata file exists at the spec'd path.
        meta_path = project_dir / ".scieasy" / "sessions" / "chat-1.json"
        assert meta_path.is_file()
        loaded = SessionMetadata.model_validate(json.loads(meta_path.read_text(encoding="utf-8")))
        assert loaded.chat_id == "chat-1"
        assert loaded.provider == "claude-code"
        assert loaded.system_prompt_hash  # sha256 hex
        assert loaded.bypass_mode is False
        # Manager tracks the session.
        assert manager.get_session(project_dir, "chat-1") is session
        assert manager.live_count == 1
    finally:
        await manager.close_session(project_dir, "chat-1")


@pytest.mark.asyncio
async def test_start_session_concurrent_cap_exceeded(project_dir: Path, provider: ClaudeCodeProvider) -> None:
    manager = AgentSessionManager(concurrent_cap=2)
    for i in range(2):
        await manager.start_session(
            project_dir=project_dir,
            chat_id=f"chat-{i}",
            provider=provider,
            system_prompt="p",
            mcp_config={},
            permission_mode=PermissionMode.STRICT,
        )
    try:
        with pytest.raises(AgentSessionError, match="concurrent chat cap"):
            await manager.start_session(
                project_dir=project_dir,
                chat_id="chat-overflow",
                provider=provider,
                system_prompt="p",
                mcp_config={},
                permission_mode=PermissionMode.STRICT,
            )
    finally:
        await manager.shutdown_all()


@pytest.mark.asyncio
async def test_start_session_duplicate_chat_id_raises(project_dir: Path, provider: ClaudeCodeProvider) -> None:
    manager = AgentSessionManager()
    await manager.start_session(
        project_dir=project_dir,
        chat_id="dup",
        provider=provider,
        system_prompt="p",
        mcp_config={},
        permission_mode=PermissionMode.STRICT,
    )
    try:
        with pytest.raises(AgentSessionError, match="already exists"):
            await manager.start_session(
                project_dir=project_dir,
                chat_id="dup",
                provider=provider,
                system_prompt="p",
                mcp_config={},
                permission_mode=PermissionMode.STRICT,
            )
    finally:
        await manager.close_session(project_dir, "dup")


@pytest.mark.asyncio
async def test_close_session_preserves_metadata_file(project_dir: Path, provider: ClaudeCodeProvider) -> None:
    manager = AgentSessionManager()
    await manager.start_session(
        project_dir=project_dir,
        chat_id="chat-preserve",
        provider=provider,
        system_prompt="p",
        mcp_config={},
        permission_mode=PermissionMode.STRICT,
    )
    meta_path = project_dir / ".scieasy" / "sessions" / "chat-preserve.json"
    assert meta_path.is_file()
    await manager.close_session(project_dir, "chat-preserve")
    # Metadata file remains; live session is gone.
    assert meta_path.is_file()
    assert manager.get_session(project_dir, "chat-preserve") is None
    assert manager.live_count == 0


@pytest.mark.asyncio
async def test_close_session_unknown_is_noop(project_dir: Path) -> None:
    manager = AgentSessionManager()
    # Should not raise.
    await manager.close_session(project_dir, "never-started")


@pytest.mark.asyncio
async def test_shutdown_all_closes_every_session(project_dir: Path, provider: ClaudeCodeProvider) -> None:
    manager = AgentSessionManager()
    for chat_id in ("a", "b", "c"):
        await manager.start_session(
            project_dir=project_dir,
            chat_id=chat_id,
            provider=provider,
            system_prompt="p",
            mcp_config={},
            permission_mode=PermissionMode.STRICT,
        )
    assert manager.live_count == 3
    await manager.shutdown_all()
    assert manager.live_count == 0


def test_load_metadata_returns_none_when_missing(tmp_path: Path) -> None:
    manager = AgentSessionManager()
    assert manager.load_metadata(tmp_path, "no-such-chat") is None


def test_session_metadata_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        SessionMetadata.model_validate(
            {
                "chat_id": "c",
                "provider": "claude-code",
                "system_prompt_hash": "h",
                "rogue": "x",
            }
        )


def test_session_metadata_round_trip() -> None:
    meta = SessionMetadata(
        chat_id="c1",
        provider="claude-code",
        system_prompt_hash="h",
        bypass_mode=True,
    )
    payload = meta.model_dump()
    loaded = SessionMetadata.model_validate(payload)
    assert loaded == meta


def test_get_session_manager_returns_singleton() -> None:
    set_session_manager(None)
    a = get_session_manager()
    b = get_session_manager()
    assert a is b
    set_session_manager(None)


# ---------------------------------------------------------------------------
# T-ECA-106 closeout (#778): TranscriptWriter lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_session_attaches_transcript_writer(project_dir: Path, provider: ClaudeCodeProvider) -> None:
    """A live session must have an associated TranscriptWriter rooted at
    ``{project_dir}/.scieasy/sessions/<chat_id>/transcript.jsonl``."""
    manager = AgentSessionManager()
    await manager.start_session(
        project_dir=project_dir,
        chat_id="chat-transcript",
        provider=provider,
        system_prompt="p",
        mcp_config={},
        permission_mode=PermissionMode.STRICT,
    )
    try:
        writer = manager.get_transcript_writer(project_dir, "chat-transcript")
        assert writer is not None, "expected a TranscriptWriter for live session"
        expected = project_dir.resolve() / ".scieasy" / "sessions" / "chat-transcript" / "transcript.jsonl"
        assert writer.path == expected
    finally:
        await manager.close_session(project_dir, "chat-transcript")


@pytest.mark.asyncio
async def test_close_session_closes_transcript_writer(project_dir: Path, provider: ClaudeCodeProvider) -> None:
    """close_session must drop the TranscriptWriter from the registry."""
    manager = AgentSessionManager()
    await manager.start_session(
        project_dir=project_dir,
        chat_id="chat-close-transcript",
        provider=provider,
        system_prompt="p",
        mcp_config={},
        permission_mode=PermissionMode.STRICT,
    )
    assert manager.get_transcript_writer(project_dir, "chat-close-transcript") is not None
    await manager.close_session(project_dir, "chat-close-transcript")
    assert manager.get_transcript_writer(project_dir, "chat-close-transcript") is None


@pytest.mark.asyncio
async def test_transcript_writer_records_events_when_written(project_dir: Path, provider: ClaudeCodeProvider) -> None:
    """Round-trip: writing events through the attached writer lands on disk."""
    from scieasy.ai.agent.provider import (
        AssistantTextDeltaEvent,
        DoneEvent,
        InitEvent,
    )

    manager = AgentSessionManager()
    await manager.start_session(
        project_dir=project_dir,
        chat_id="chat-rt",
        provider=provider,
        system_prompt="p",
        mcp_config={},
        permission_mode=PermissionMode.STRICT,
    )
    try:
        writer = manager.get_transcript_writer(project_dir, "chat-rt")
        assert writer is not None
        await writer.write_event(InitEvent(kind="init", raw={}, session_id="s1"))
        await writer.write_event(AssistantTextDeltaEvent(kind="assistant_text_delta", raw={}, delta="hi"))
        await writer.write_event(DoneEvent(kind="done", raw={}))
    finally:
        await manager.close_session(project_dir, "chat-rt")

    transcript_path = project_dir / ".scieasy" / "sessions" / "chat-rt" / "transcript.jsonl"
    assert transcript_path.is_file()
    lines = transcript_path.read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(line)["kind"] for line in lines]
    assert kinds == ["init", "assistant_text_delta", "done"]


@pytest.mark.asyncio
async def test_start_session_forwards_model_to_provider(project_dir: Path) -> None:
    """Regression for Codex P2: ``model`` kwarg must flow through to
    ``provider.start_session``, not just into the metadata file.
    """

    captured: dict[str, object] = {}

    class _SpyProvider:
        name = "spy"

        async def start_session(self, **kwargs: object) -> object:
            captured.update(kwargs)

            class _FakeSession:
                pid = 1
                session_id = None

                async def close(self) -> None:
                    return None

            return _FakeSession()

    manager = AgentSessionManager()
    await manager.start_session(
        project_dir=project_dir,
        chat_id="model-pass-through",
        provider=_SpyProvider(),  # type: ignore[arg-type]
        system_prompt="p",
        mcp_config={},
        permission_mode=PermissionMode.STRICT,
        model="claude-opus-4-7",
    )

    assert captured.get("model") == "claude-opus-4-7", (
        "AgentSessionManager.start_session dropped the model kwarg before reaching the provider"
    )
    await manager.shutdown_all()
