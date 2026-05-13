"""Phase-1 end-to-end integration test (T-ECA-109).

Drives :func:`scieasy.ai.agent.demo.main` against the
``tests/fixtures/stub_claude.py`` Python stub and asserts the canonical
event sequence.

This is the runtime acceptance gate for Phase 1: if the provider, the
session manager, the stream-json parser, and the demo can ALL produce a
clean ``init → assistant_text_delta+ → tool_use → tool_result → done``
sequence end-to-end, the embedded coding agent backbone is wired
correctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.ai.agent.demo import main as demo_main
from scieasy.ai.agent.provider import (
    AssistantTextDeltaEvent,
    DoneEvent,
    InitEvent,
    ToolResultEvent,
    ToolUseEvent,
)

STUB_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "stub_claude.py"


@pytest.mark.asyncio
async def test_phase1_demo_event_sequence(tmp_path: Path) -> None:
    captured = await demo_main(
        project_dir=tmp_path,
        binary_override=STUB_PATH,
        user_message="list files",
    )

    # Stream must start with InitEvent and end with DoneEvent.
    assert captured, "demo produced no events"
    assert isinstance(captured[0], InitEvent)
    assert isinstance(captured[-1], DoneEvent)

    kinds = [event.kind for event in captured]
    assert "assistant_text_delta" in kinds
    assert "tool_use" in kinds
    assert "tool_result" in kinds

    # At least one of each typed event matches the expected dataclass.
    assert any(isinstance(e, AssistantTextDeltaEvent) for e in captured)
    assert any(isinstance(e, ToolUseEvent) for e in captured)
    assert any(isinstance(e, ToolResultEvent) for e in captured)

    # T-ECA-108 config files must have been emitted under .scieasy/.
    scieasy_dir = tmp_path / ".scieasy"
    assert (scieasy_dir / "mcp.json").is_file()
    assert (scieasy_dir / "claude-hooks.json").is_file()


@pytest.mark.asyncio
async def test_phase1_demo_writes_session_metadata(tmp_path: Path) -> None:
    await demo_main(
        project_dir=tmp_path,
        binary_override=STUB_PATH,
        user_message="hi",
    )
    sessions_dir = tmp_path / ".scieasy" / "sessions"
    assert sessions_dir.is_dir()
    metadata_files = list(sessions_dir.glob("*.json"))
    assert metadata_files, "expected at least one session metadata file"


@pytest.mark.asyncio
async def test_phase1_demo_writes_transcript_jsonl(tmp_path: Path) -> None:
    """T-ECA-106 closeout (#778): every WS-style event lands on disk as JSONL.

    The Phase-1 demo runs the canonical
    ``init -> assistant_text_delta+ -> tool_use -> tool_result -> done``
    sequence through the same session-manager + provider stack the
    real WebSocket uses. Once the WS pump is wired to the
    :class:`TranscriptWriter` (this issue), demos that exercise the
    pump must drop a ``transcript.jsonl`` next to the metadata file.

    Note: the Phase-1 demo iterates ``stream_events`` directly rather
    than going through the WS handler, so this test exercises the
    manager-level lifecycle (writer created + closed) by writing the
    captured events through the writer manually. The WS-end pump
    integration is covered by the unit tests in
    ``tests/ai/test_session_manager.py`` and a future Phase-5 e2e.
    """
    import json

    from scieasy.ai.agent.session import AgentSessionManager
    from scieasy.ai.agent.transcript import TranscriptWriter

    # Capture the session's chat_id so we can locate the transcript file.
    started: dict[str, str] = {}
    original_start = AgentSessionManager.start_session

    async def _capturing_start(self: AgentSessionManager, **kwargs: object) -> object:
        started["chat_id"] = str(kwargs["chat_id"])
        return await original_start(self, **kwargs)  # type: ignore[arg-type]

    AgentSessionManager.start_session = _capturing_start  # type: ignore[method-assign]
    try:
        # Run a session manually so we can drive the writer the same way
        # the WS pump will: capture events, then mirror each to the
        # attached writer.
        from scieasy.ai.agent.claude_code import ClaudeCodeProvider
        from scieasy.ai.agent.config_files import write_hook_config, write_mcp_config
        from scieasy.ai.agent.provider import PermissionMode

        chat_id = "demo-transcript"
        provider = ClaudeCodeProvider(binary_override=STUB_PATH)
        write_mcp_config(tmp_path, chat_id=chat_id)
        write_hook_config(tmp_path, permission_mode=PermissionMode.STRICT)
        manager = AgentSessionManager()
        session = await manager.start_session(
            project_dir=tmp_path,
            chat_id=chat_id,
            provider=provider,
            system_prompt="p",
            mcp_config={"mcpServers": {}},
            permission_mode=PermissionMode.STRICT,
        )
        writer = manager.get_transcript_writer(tmp_path, chat_id)
        assert isinstance(writer, TranscriptWriter)
        try:
            await session.send_user_message("list files")
            async for event in session.stream_events():
                await writer.write_event(event)
        finally:
            await manager.close_session(tmp_path, chat_id)

        transcript_path = tmp_path / ".scieasy" / "sessions" / chat_id / "transcript.jsonl"
        assert transcript_path.is_file(), "transcript.jsonl must be written by the pump"
        lines = transcript_path.read_text(encoding="utf-8").splitlines()
        kinds = [json.loads(line)["kind"] for line in lines]
        assert "init" in kinds
        assert "done" in kinds
        assert "assistant_text_delta" in kinds
    finally:
        AgentSessionManager.start_session = original_start  # type: ignore[method-assign]
        # Quiet the unused-variable warning if started was never used.
        started.pop("chat_id", None)
