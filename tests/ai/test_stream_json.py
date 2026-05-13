"""Unit tests for :mod:`scieasy.ai.agent.stream_json`.

Targets 100% line coverage on ``stream_json.py`` per spec §5 T-ECA-103.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from scieasy.ai.agent.errors import AgentStreamError
from scieasy.ai.agent.provider import (
    AgentEvent,
    AssistantTextDeltaEvent,
    DoneEvent,
    ErrorEvent,
    InitEvent,
    OtherEvent,
    PermissionRequestEvent,
    ToolResultEvent,
    ToolUseEvent,
)
from scieasy.ai.agent.stream_json import MAX_LINE_BYTES, parse_event, parse_stream

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "stream_json"


# ---------------------------------------------------------------------------
# parse_event — happy paths per canonical kind
# ---------------------------------------------------------------------------


def _line(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload) + "\n").encode("utf-8")


def test_parse_init_event_kind_field() -> None:
    event = parse_event(_line({"kind": "init", "session_id": "s1", "model": "claude"}))
    assert isinstance(event, InitEvent)
    assert event.session_id == "s1"
    assert event.model == "claude"
    assert event.kind == "init"


def test_parse_init_event_type_field_fallback() -> None:
    """Real CC currently uses ``type`` not ``kind``; both spellings are accepted."""
    event = parse_event(_line({"type": "init", "session_id": "s2", "schema_version": "1.0"}))
    assert isinstance(event, InitEvent)
    assert event.session_id == "s2"
    assert event.schema_version == "1.0"


def test_parse_assistant_text_delta() -> None:
    event = parse_event(_line({"kind": "assistant_text_delta", "delta": "hello"}))
    assert isinstance(event, AssistantTextDeltaEvent)
    assert event.delta == "hello"


def test_parse_assistant_text_delta_text_alias() -> None:
    """Some providers use ``text`` instead of ``delta``; the parser accepts both."""
    event = parse_event(_line({"kind": "assistant_text_delta", "text": "yo"}))
    assert isinstance(event, AssistantTextDeltaEvent)
    assert event.delta == "yo"


def test_parse_tool_use() -> None:
    event = parse_event(
        _line(
            {
                "kind": "tool_use",
                "tool_name": "Read",
                "tool_input": {"file_path": "/tmp/x"},
                "tool_use_id": "tu1",
            }
        )
    )
    assert isinstance(event, ToolUseEvent)
    assert event.tool_name == "Read"
    assert event.tool_input == {"file_path": "/tmp/x"}
    assert event.tool_use_id == "tu1"


def test_parse_tool_use_alias_fields() -> None:
    """`name` / `input` / `id` are accepted as aliases for tool_name / tool_input / tool_use_id."""
    event = parse_event(
        _line(
            {
                "kind": "tool_use",
                "name": "Grep",
                "input": {"pattern": "foo"},
                "id": "tu2",
            }
        )
    )
    assert isinstance(event, ToolUseEvent)
    assert event.tool_name == "Grep"
    assert event.tool_use_id == "tu2"


def test_parse_tool_result() -> None:
    event = parse_event(
        _line(
            {
                "kind": "tool_result",
                "tool_use_id": "tu1",
                "output": "file contents",
                "is_error": False,
            }
        )
    )
    assert isinstance(event, ToolResultEvent)
    assert event.tool_use_id == "tu1"
    assert event.output == "file contents"
    assert event.is_error is False


def test_parse_tool_result_content_alias() -> None:
    event = parse_event(_line({"kind": "tool_result", "tool_use_id": "tu1", "content": "result"}))
    assert isinstance(event, ToolResultEvent)
    assert event.output == "result"


def test_parse_tool_result_coerces_non_str_dict_output() -> None:
    """List output is JSON-coerced to a string for forensic safety."""
    event = parse_event(_line({"kind": "tool_result", "tool_use_id": "tu1", "output": [1, 2]}))
    assert isinstance(event, ToolResultEvent)
    assert isinstance(event.output, str)
    assert "1" in event.output and "2" in event.output


def test_parse_permission_request() -> None:
    event = parse_event(
        _line(
            {
                "kind": "permission_request",
                "tool_name": "Edit",
                "tool_input": {"file_path": "/x"},
                "request_id": "r1",
            }
        )
    )
    assert isinstance(event, PermissionRequestEvent)
    assert event.tool_name == "Edit"
    assert event.request_id == "r1"


def test_parse_error_event() -> None:
    event = parse_event(_line({"kind": "error", "message": "boom", "error_type": "AuthError"}))
    assert isinstance(event, ErrorEvent)
    assert event.message == "boom"
    assert event.error_type == "AuthError"


def test_parse_error_event_string_alias() -> None:
    event = parse_event(_line({"kind": "error", "error": "auth failed"}))
    assert isinstance(event, ErrorEvent)
    assert event.message == "auth failed"


def test_parse_error_event_empty_message_default() -> None:
    """`error` with no message/error fields still produces an ErrorEvent (empty message)."""
    event = parse_event(_line({"kind": "error"}))
    assert isinstance(event, ErrorEvent)
    assert event.message == ""


def test_parse_done_event() -> None:
    event = parse_event(_line({"kind": "done"}))
    assert isinstance(event, DoneEvent)


# ---------------------------------------------------------------------------
# Unknown / degraded
# ---------------------------------------------------------------------------


def test_parse_unknown_kind_yields_other_event(caplog: pytest.LogCaptureFixture) -> None:
    """Unknown kinds route to OtherEvent and log INFO."""
    caplog.set_level("INFO", logger="scieasy.ai.agent.stream_json")
    event = parse_event(_line({"kind": "weird_kind", "stuff": 1}))
    assert isinstance(event, OtherEvent)
    assert event.kind == "weird_kind"
    assert event.raw == {"kind": "weird_kind", "stuff": 1}
    assert any("Unknown event kind" in rec.message or "unknown event kind" in rec.message for rec in caplog.records)


def test_parse_missing_kind_field() -> None:
    """Payload with neither `kind` nor `type` yields OtherEvent(kind='other')."""
    event = parse_event(_line({"random": "data"}))
    assert isinstance(event, OtherEvent)
    assert event.kind == "other"


def test_init_missing_session_id_degrades_to_other() -> None:
    event = parse_event(_line({"kind": "init"}))
    assert isinstance(event, OtherEvent)
    assert event.kind == "init"


def test_assistant_text_delta_missing_delta_degrades() -> None:
    event = parse_event(_line({"kind": "assistant_text_delta"}))
    assert isinstance(event, OtherEvent)


def test_tool_use_missing_fields_degrades() -> None:
    event = parse_event(_line({"kind": "tool_use", "tool_name": "Read"}))
    assert isinstance(event, OtherEvent)


def test_tool_result_missing_id_degrades() -> None:
    event = parse_event(_line({"kind": "tool_result", "output": "x"}))
    assert isinstance(event, OtherEvent)


def test_permission_request_missing_fields_degrades() -> None:
    event = parse_event(_line({"kind": "permission_request", "tool_name": "Edit"}))
    assert isinstance(event, OtherEvent)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_empty_line_raises() -> None:
    with pytest.raises(AgentStreamError, match="empty"):
        parse_event(b"")


def test_whitespace_only_line_raises() -> None:
    with pytest.raises(AgentStreamError, match="empty"):
        parse_event(b"   \t\n")


def test_invalid_json_raises() -> None:
    with pytest.raises(AgentStreamError, match="invalid JSON"):
        parse_event(b'{"kind": "init"')


def test_non_object_payload_raises() -> None:
    """Arrays / primitives at the top level are not valid stream-json events."""
    with pytest.raises(AgentStreamError, match="not a JSON object"):
        parse_event(b"[1, 2, 3]")


def test_oversized_line_raises() -> None:
    huge = b'{"kind":"x","data":"' + b"A" * (MAX_LINE_BYTES + 1) + b'"}'
    with pytest.raises(AgentStreamError, match="exceeds"):
        parse_event(huge)


def test_non_bytes_input_raises() -> None:
    with pytest.raises(AgentStreamError, match="expected bytes"):
        parse_event("not bytes")  # type: ignore[arg-type]


def test_non_utf8_bytes_are_replaced_then_parsed() -> None:
    """Single byte glitch survives via the replace error handler, but bad JSON still raises."""
    # 0xff is invalid utf-8 — `errors="replace"` swaps it for U+FFFD then JSON parsing
    # will fail because that character isn't valid JSON syntax.
    bad = b'{"kind":\xff"init"}'
    with pytest.raises(AgentStreamError):
        parse_event(bad)


# ---------------------------------------------------------------------------
# Fixture round-trip
# ---------------------------------------------------------------------------


def _read_lines(path: Path) -> list[bytes]:
    return [ln.encode("utf-8") for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_happy_path_fixture_roundtrip() -> None:
    lines = _read_lines(FIXTURES / "happy_path.ndjson")
    events = [parse_event(line) for line in lines]
    assert isinstance(events[0], InitEvent)
    assert events[0].session_id == "sess-abc-001"
    assert sum(isinstance(e, AssistantTextDeltaEvent) for e in events) == 5
    tool_use = next(e for e in events if isinstance(e, ToolUseEvent))
    assert tool_use.tool_name == "Read"
    tool_result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert tool_result.tool_use_id == tool_use.tool_use_id
    assert isinstance(events[-1], DoneEvent)


def test_unknown_kind_fixture_roundtrip() -> None:
    lines = _read_lines(FIXTURES / "unknown_kind.ndjson")
    events = [parse_event(line) for line in lines]
    assert any(isinstance(e, OtherEvent) and e.kind == "synthetic_unknown" for e in events)


def test_top_level_empty_thinking_frame_parses_as_thinking_other() -> None:
    """Issue #804 / #9: empty signature-only thinking frames must NOT
    fall through to ``kind='other'``.

    Real claude streams ``{"type":"thinking","thinking":"","signature":"..."}``
    at the top level (not nested in an assistant frame). The parser must
    route this to ``OtherEvent(kind='thinking')`` so the renderer's
    thinking branch handles it (showing the animated indicator) rather
    than the legacy "Unrecognised event" raw fallback.
    """
    event = parse_event(
        _line(
            {
                "type": "thinking",
                "text": "",
                "thinking": "",
                "signature": "EtABcDeF",
            }
        )
    )
    assert isinstance(event, OtherEvent), f"expected OtherEvent, got {type(event).__name__}"
    assert event.kind == "thinking", f"expected kind='thinking' for top-level thinking frame, got {event.kind!r}"


def test_malformed_fixture_truncated_line_raises() -> None:
    lines = _read_lines(FIXTURES / "malformed.ndjson")
    # The truncated middle line should fail to parse.
    parsed: list[AgentEvent] = []
    saw_error = False
    for line in lines:
        try:
            parsed.append(parse_event(line))
        except AgentStreamError:
            saw_error = True
    assert saw_error, "truncated fixture line should raise AgentStreamError"


# ---------------------------------------------------------------------------
# parse_stream
# ---------------------------------------------------------------------------


async def _async_iter(chunks: list[bytes]) -> AsyncIterator[bytes]:
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
async def test_parse_stream_happy_path() -> None:
    raw = (FIXTURES / "happy_path.ndjson").read_bytes()
    events: list[AgentEvent] = []
    async for event in parse_stream(_async_iter([raw])):
        events.append(event)
    assert len(events) == 9
    assert isinstance(events[0], InitEvent)
    assert isinstance(events[-1], DoneEvent)


@pytest.mark.asyncio
async def test_parse_stream_split_across_chunks() -> None:
    """A single line split across two chunks must still parse as one event."""
    line = b'{"kind":"assistant_text_delta","delta":"hello"}\n'
    chunks = [line[:20], line[20:]]
    events: list[AgentEvent] = []
    async for event in parse_stream(_async_iter(chunks)):
        events.append(event)
    assert len(events) == 1
    assert isinstance(events[0], AssistantTextDeltaEvent)
    assert events[0].delta == "hello"


@pytest.mark.asyncio
async def test_parse_stream_ignores_blank_lines() -> None:
    chunks = [b'{"kind":"done"}\n\n\n{"kind":"done"}\n']
    events: list[AgentEvent] = []
    async for event in parse_stream(_async_iter(chunks)):
        events.append(event)
    assert len(events) == 2


@pytest.mark.asyncio
async def test_parse_stream_skips_empty_chunks() -> None:
    chunks = [b"", b'{"kind":"done"}\n', b""]
    events: list[AgentEvent] = []
    async for event in parse_stream(_async_iter(chunks)):
        events.append(event)
    assert len(events) == 1


@pytest.mark.asyncio
async def test_parse_stream_flushes_trailing_partial_line() -> None:
    """A residual line without a trailing newline at stream end is still emitted."""
    chunks = [b'{"kind":"done"}']  # no trailing newline
    events: list[AgentEvent] = []
    async for event in parse_stream(_async_iter(chunks)):
        events.append(event)
    assert len(events) == 1
    assert isinstance(events[0], DoneEvent)


@pytest.mark.asyncio
async def test_parse_stream_oversized_line_raises() -> None:
    """A chunk exceeding the buffer cap without any newline raises before yielding."""
    huge = b"A" * (MAX_LINE_BYTES + 16)
    with pytest.raises(AgentStreamError, match="exceeds"):
        async for _ in parse_stream(_async_iter([huge])):
            pass


@pytest.mark.asyncio
async def test_parse_stream_propagates_invalid_json() -> None:
    chunks = [b'{"kind":"init"\n']  # malformed JSON in a complete line
    with pytest.raises(AgentStreamError, match="invalid JSON"):
        async for _ in parse_stream(_async_iter(chunks)):
            pass


# ---------------------------------------------------------------------------
# classify_for_display — issue #788 (display_class taxonomy)
# ---------------------------------------------------------------------------


def test_classify_hidden_via_chat_hidden_flag() -> None:
    """The internal `_chat_hidden=True` marker always wins."""
    from scieasy.ai.agent.stream_json import classify_for_display

    assert classify_for_display("anything", {"_chat_hidden": True, "text": "irrelevant"}) == "hidden"


def test_classify_hidden_via_kind_name() -> None:
    from scieasy.ai.agent.stream_json import classify_for_display

    assert classify_for_display("heartbeat", {}) == "hidden"
    assert classify_for_display("ping", {}) == "hidden"
    assert classify_for_display("rate_limit_event", {}) == "hidden"
    assert classify_for_display("assistant_empty", {}) == "hidden"
    assert classify_for_display("user_echo", {}) == "hidden"


def test_classify_meta_via_kind_name() -> None:
    from scieasy.ai.agent.stream_json import classify_for_display

    assert classify_for_display("system", {}) == "meta"
    assert classify_for_display("system/hook_started", {}) == "meta"
    assert classify_for_display("result", {}) == "meta"
    assert classify_for_display("model_info", {}) == "meta"


def test_classify_text_like_when_payload_has_text() -> None:
    from scieasy.ai.agent.stream_json import classify_for_display

    assert classify_for_display("future_kind", {"text": "hello"}) == "text-like"
    assert classify_for_display("future_kind", {"content": "hi there"}) == "text-like"
    assert classify_for_display("future_kind", {"message": "greetings"}) == "text-like"
    # Empty strings should not qualify
    assert classify_for_display("future_kind", {"text": "   "}) == "raw"


def test_classify_tool_like_when_payload_has_tool_shape() -> None:
    from scieasy.ai.agent.stream_json import classify_for_display

    assert classify_for_display("future_tool", {"tool_name": "Bash", "input": {"command": "ls"}}) == "tool-like"
    assert classify_for_display("future_tool", {"name": "Edit", "input": {"file_path": "/a"}}) == "tool-like"
    # Tool-name without input does NOT qualify as tool-like
    assert classify_for_display("future_tool", {"tool_name": "Bash"}) == "raw"


def test_classify_raw_default_fallback() -> None:
    from scieasy.ai.agent.stream_json import classify_for_display

    assert classify_for_display("future_unknown", {}) == "raw"
    assert classify_for_display("future_unknown", {"random_field": 42}) == "raw"


def test_unknown_kind_carries_display_class_on_other_event() -> None:
    """`parse_event` on an unknown kind returns an OtherEvent with a classified
    display_class — not the legacy unclassified default."""
    event = parse_event(_line({"kind": "future_kind", "text": "hello"}))
    assert isinstance(event, OtherEvent)
    assert event.display_class == "text-like"


def test_rate_limit_event_classified_hidden() -> None:
    """The existing rate_limit_event lambda still produces a hidden OtherEvent."""
    event = parse_event(_line({"kind": "rate_limit_event"}))
    assert isinstance(event, OtherEvent)
    assert event.display_class == "hidden"


def test_system_hook_subtype_classified_meta() -> None:
    """`system/hook_started` is meta (the _chat_hidden suppression is layered
    on top by the existing dispatch — classification itself says meta)."""
    from scieasy.ai.agent.stream_json import classify_for_display

    assert classify_for_display("system/hook_started", {}) == "meta"
