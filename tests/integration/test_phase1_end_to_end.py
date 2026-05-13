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
