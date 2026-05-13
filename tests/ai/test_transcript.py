"""Unit tests for :mod:`scieasy.ai.agent.transcript` (T-ECA-106)."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pytest

from scieasy.ai.agent.provider import (
    AgentEvent,
    AssistantTextDeltaEvent,
    InitEvent,
)
from scieasy.ai.agent.transcript import TranscriptWriter


@pytest.mark.asyncio
async def test_write_event_appends_one_jsonl_line(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "c1" / "transcript.jsonl"
    writer = TranscriptWriter(path)
    try:
        await writer.write_event(InitEvent(kind="init", raw={}, session_id="s1"))
        await writer.write_event(AssistantTextDeltaEvent(kind="assistant_text_delta", raw={}, delta="hi"))
    finally:
        writer.close()

    assert path.is_file()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["kind"] == "init"
    assert first["session_id"] == "s1"
    second = json.loads(lines[1])
    assert second["kind"] == "assistant_text_delta"
    assert second["delta"] == "hi"


@pytest.mark.asyncio
async def test_write_event_appends_across_writers(tmp_path: Path) -> None:
    path = tmp_path / "transcript.jsonl"
    w1 = TranscriptWriter(path)
    await w1.write_event(AgentEvent(kind="x"))
    w1.close()
    w2 = TranscriptWriter(path)
    await w2.write_event(AgentEvent(kind="y"))
    w2.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["kind"] for line in lines] == ["x", "y"]


@pytest.mark.asyncio
async def test_close_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    writer = TranscriptWriter(path)
    await writer.write_event(AgentEvent(kind="x"))
    writer.close()
    # Double close — no exception.
    writer.close()


@pytest.mark.asyncio
async def test_write_failure_logs_warning_and_swallows(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """On Windows a read-only file is the most reliable failure trigger.

    Strategy: point the writer at a path whose *parent* is a file rather
    than a directory, so ``parent.mkdir(parents=True, exist_ok=True)``
    raises ``OSError`` (NotADirectoryError on POSIX, OSError on Windows).
    """
    # Create a regular file that we then try to use as a directory.
    parent_as_file = tmp_path / "not_a_dir"
    parent_as_file.write_text("oops", encoding="utf-8")
    target = parent_as_file / "transcript.jsonl"
    writer = TranscriptWriter(target)
    caplog.set_level(logging.WARNING, logger="scieasy.ai.agent.transcript")
    # Must not raise; should log a WARNING instead.
    await writer.write_event(AgentEvent(kind="init"))
    writer.close()
    assert any("write failed" in record.getMessage() for record in caplog.records), (
        "expected a WARNING about write failure"
    )


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="chmod read-only behaviour differs on Windows")
async def test_write_failure_to_readonly_dir(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    readonly_dir = tmp_path / "ro"
    readonly_dir.mkdir()
    os.chmod(readonly_dir, 0o500)
    try:
        writer = TranscriptWriter(readonly_dir / "transcript.jsonl")
        caplog.set_level(logging.WARNING, logger="scieasy.ai.agent.transcript")
        await writer.write_event(AgentEvent(kind="x"))
        writer.close()
        assert any("write failed" in r.getMessage() for r in caplog.records)
    finally:
        os.chmod(readonly_dir, 0o700)


@pytest.mark.asyncio
async def test_write_after_failure_is_silent(tmp_path: Path) -> None:
    """After the first failure the writer is disabled — subsequent writes are no-ops."""
    parent_as_file = tmp_path / "blocked"
    parent_as_file.write_text("oops", encoding="utf-8")
    target = parent_as_file / "transcript.jsonl"
    writer = TranscriptWriter(target)
    await writer.write_event(AgentEvent(kind="a"))
    # Second event silently dropped — no exception, no log spam.
    await writer.write_event(AgentEvent(kind="b"))
    writer.close()
