"""Stream-JSON (NDJSON) parser for provider IPC.

The agent provider's subprocess emits one JSON event per stdout line.
This module owns the parser that translates raw bytes into typed
:class:`scieasy.ai.agent.provider.AgentEvent` instances.

Behaviours implemented (spec §5 T-ECA-103, ADR-033 §3 OQ5):

* Line-buffered NDJSON parsing with a 1 MiB-per-event hard cap; oversized
  frames raise :class:`scieasy.ai.agent.errors.AgentStreamError`.
* Canonical event-kind normalisation. The wire kind is read from the
  ``kind`` field first, falling back to ``type`` if absent — Claude Code's
  current CLI uses ``type`` while the ADR specifies ``kind`` as the
  canonical name. Both spellings are tolerated.
* The known canonical kinds are: ``init``, ``assistant_text_delta``,
  ``tool_use``, ``tool_result``, ``permission_request``, ``error``,
  ``done``. Required-field absence on a known kind degrades gracefully to
  ``OtherEvent`` with a WARNING log.
* Unknown kinds → :class:`OtherEvent` with an INFO log (spec §3 OQ5).
* Truncated / non-UTF-8 / oversized frames →
  :class:`AgentStreamError`. UTF-8 decoding uses ``errors="replace"`` so
  individual byte-level glitches surface as the Unicode replacement
  character rather than blowing up the whole stream, but a JSON parse
  failure on the result still raises.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

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

logger = logging.getLogger(__name__)

MAX_LINE_BYTES = 1024 * 1024
"""Hard cap on the size of a single stream-json frame (1 MiB)."""


def _extract_kind(payload: dict[str, Any]) -> str | None:
    """Return the canonical event kind from a parsed payload.

    Preference order: ``kind`` (ADR canonical name) then ``type`` (the
    field name Claude Code currently uses on the wire).
    """
    raw_kind = payload.get("kind")
    if isinstance(raw_kind, str) and raw_kind:
        return raw_kind
    raw_type = payload.get("type")
    if isinstance(raw_type, str) and raw_type:
        return raw_type
    return None


def _make_init(payload: dict[str, Any]) -> AgentEvent:
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        logger.warning("stream_json: init event missing session_id; falling back to OtherEvent")
        return OtherEvent(kind="init", raw=payload)
    schema_version = payload.get("schema_version")
    model = payload.get("model")
    return InitEvent(
        kind="init",
        raw=payload,
        session_id=session_id,
        schema_version=schema_version if isinstance(schema_version, str) else None,
        model=model if isinstance(model, str) else None,
    )


def _make_assistant_text_delta(payload: dict[str, Any]) -> AgentEvent:
    delta = payload.get("delta")
    if delta is None:
        delta = payload.get("text")
    if not isinstance(delta, str):
        logger.warning("stream_json: assistant_text_delta missing delta/text; OtherEvent")
        return OtherEvent(kind="assistant_text_delta", raw=payload)
    return AssistantTextDeltaEvent(kind="assistant_text_delta", raw=payload, delta=delta)


def _make_tool_use(payload: dict[str, Any]) -> AgentEvent:
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        tool_name = payload.get("name") if isinstance(payload.get("name"), str) else None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = payload.get("input") if isinstance(payload.get("input"), dict) else None
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        tool_use_id = payload.get("id") if isinstance(payload.get("id"), str) else None
    if tool_name is None or tool_input is None or tool_use_id is None:
        logger.warning("stream_json: tool_use missing required fields; OtherEvent")
        return OtherEvent(kind="tool_use", raw=payload)
    return ToolUseEvent(
        kind="tool_use",
        raw=payload,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_use_id=tool_use_id,
    )


def _make_tool_result(payload: dict[str, Any]) -> AgentEvent:
    tool_use_id = payload.get("tool_use_id")
    if not isinstance(tool_use_id, str) or not tool_use_id:
        logger.warning("stream_json: tool_result missing tool_use_id; OtherEvent")
        return OtherEvent(kind="tool_result", raw=payload)
    output = payload.get("output")
    if output is None:
        output = payload.get("content", "")
    if not isinstance(output, (str, dict)):
        # Coerce list/number/bool to string for forensic safety.
        output = json.dumps(output)
    is_error = bool(payload.get("is_error", False))
    return ToolResultEvent(
        kind="tool_result",
        raw=payload,
        tool_use_id=tool_use_id,
        output=output,
        is_error=is_error,
    )


def _make_permission_request(payload: dict[str, Any]) -> AgentEvent:
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    request_id = payload.get("request_id")
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict) or not isinstance(request_id, str):
        logger.warning("stream_json: permission_request missing required fields; OtherEvent")
        return OtherEvent(kind="permission_request", raw=payload)
    return PermissionRequestEvent(
        kind="permission_request",
        raw=payload,
        tool_name=tool_name,
        tool_input=tool_input,
        request_id=request_id,
    )


def _make_error(payload: dict[str, Any]) -> AgentEvent:
    message = payload.get("message")
    if not isinstance(message, str):
        message = payload.get("error") if isinstance(payload.get("error"), str) else ""
    error_type = payload.get("error_type")
    return ErrorEvent(
        kind="error",
        raw=payload,
        message=message or "",
        error_type=error_type if isinstance(error_type, str) else None,
    )


def _make_done(payload: dict[str, Any]) -> AgentEvent:
    return DoneEvent(kind="done", raw=payload)


def _make_system(payload: dict[str, Any]) -> AgentEvent:
    """Map claude's `{type:system, subtype:init|hook_*|...}` frames.

    `init` carries session_id + model; surface as InitEvent. Other
    subtypes (hook_started / hook_response / etc.) are infrastructural
    and degrade to OtherEvent with a marker `_chat_hidden=true` in raw
    so the frontend filter can suppress them from the conversation feed.
    """
    subtype = payload.get("subtype")
    if subtype == "init":
        return _make_init(payload)
    hidden_raw = dict(payload)
    hidden_raw["_chat_hidden"] = True
    return OtherEvent(kind=f"system/{subtype}" if subtype else "system", raw=hidden_raw)


def _make_assistant(payload: dict[str, Any]) -> AgentEvent | list[AgentEvent]:
    """Map claude's `{type:assistant, message:{...}}` frame to one or more
    canonical events.

    The message.content can be a string or a list of content blocks. We
    fan-out one canonical event per *content* block:

    * ``text`` blocks → :class:`AssistantTextDeltaEvent` (only if the
      text is non-empty; previously we always emitted an empty delta
      event when the assistant turn carried only tool calls or thinking,
      which produced rows of blank bubbles in the chat panel — #775
      follow-up after live Phase 5 testing).
    * ``tool_use`` blocks → :class:`ToolUseEvent` so the chat shows the
      tool name + inputs collapsibly.
    * ``thinking`` blocks → OtherEvent kind=``thinking`` carrying the
      text in ``raw.text`` so the renderer can show a folded preview.

    Returns a single event if exactly one was produced, a list if
    multiple, or a hidden OtherEvent if nothing meaningful was found
    (avoids the empty-text-bubble bug).
    """
    message = payload.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None

    events: list[AgentEvent] = []

    if isinstance(content, str):
        if content:
            events.append(AssistantTextDeltaEvent(kind="assistant_text_delta", raw=payload, delta=content))
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                t = block.get("text")
                if isinstance(t, str) and t:
                    events.append(AssistantTextDeltaEvent(kind="assistant_text_delta", raw=payload, delta=t))
            elif btype == "tool_use":
                name = block.get("name")
                tool_input = block.get("input")
                tool_use_id = block.get("id")
                if isinstance(name, str) and isinstance(tool_input, dict) and isinstance(tool_use_id, str):
                    events.append(
                        ToolUseEvent(
                            kind="tool_use",
                            raw=block,
                            tool_name=name,
                            tool_input=tool_input,
                            tool_use_id=tool_use_id,
                        )
                    )
            elif btype == "thinking":
                t = block.get("thinking") or block.get("text")
                events.append(
                    OtherEvent(
                        kind="thinking",
                        raw={"text": t if isinstance(t, str) else "", **block},
                    )
                )
            elif btype == "tool_result":
                tool_use_id = block.get("tool_use_id")
                output = block.get("content") or block.get("output")
                is_error = bool(block.get("is_error"))
                if isinstance(tool_use_id, str):
                    events.append(
                        ToolResultEvent(
                            kind="tool_result",
                            raw=block,
                            tool_use_id=tool_use_id,
                            output=output if output is not None else "",
                            is_error=is_error,
                        )
                    )

    if not events:
        # Nothing renderable in this assistant turn (e.g. content was
        # an empty list or a kind we don't yet know). Hide it from the
        # chat feed rather than emit a blank delta.
        hidden = {**payload, "_chat_hidden": True}
        return OtherEvent(kind="assistant_empty", raw=hidden)
    if len(events) == 1:
        return events[0]
    return events


def _make_user_echo(payload: dict[str, Any]) -> AgentEvent | list[AgentEvent]:
    """Map claude's `{type:user, message:{role:user, content:[...]}}` echo
    frames into :class:`ToolResultEvent`s so the GUI can show each tool's
    return value.

    These ``user`` frames are how Claude Code re-injects tool_result blocks
    after the agent has called an MCP tool. They are NOT chat input — the
    user never typed anything; claude is just echoing the tool output back
    to itself. We surface the tool_result content so the chat UI can show
    a collapsible "Tool result" tile under each call.
    """
    message = payload.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    events: list[AgentEvent] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result":
                tool_use_id = block.get("tool_use_id")
                output = block.get("content") or block.get("output")
                is_error = bool(block.get("is_error"))
                if isinstance(tool_use_id, str):
                    events.append(
                        ToolResultEvent(
                            kind="tool_result",
                            raw=block,
                            tool_use_id=tool_use_id,
                            output=output if output is not None else "",
                            is_error=is_error,
                        )
                    )
    if not events:
        return OtherEvent(kind="user_echo", raw={**payload, "_chat_hidden": True})
    if len(events) == 1:
        return events[0]
    return events


def _make_result(payload: dict[str, Any]) -> AgentEvent:
    """Map claude's `{type:result, subtype:success|error|..., result, stop_reason}` frame to Done.

    DoneEvent has no extra fields; we keep stop_reason / result in `raw`
    for downstream consumers that want to inspect them.
    """
    return DoneEvent(kind="done", raw=payload)


_DISPATCH: dict[str, Any] = {
    "init": _make_init,
    "assistant_text_delta": _make_assistant_text_delta,
    "tool_use": _make_tool_use,
    "tool_result": _make_tool_result,
    "permission_request": _make_permission_request,
    "error": _make_error,
    "done": _make_done,
    # Claude Code wire-format mappings (issue #775 follow-up):
    "system": _make_system,
    "assistant": _make_assistant,
    "result": _make_result,
    # `user` frames carry tool_result blocks the agent received. We
    # extract them as ToolResultEvents so the GUI can show what each
    # tool returned; if no tool_result is found we hide the echo.
    "user": _make_user_echo,
    "rate_limit_event": lambda p: OtherEvent(kind="rate_limit_event", raw={**p, "_chat_hidden": True}),
}


def parse_event(line: bytes) -> AgentEvent | list[AgentEvent]:
    """Parse one NDJSON line into a canonical :class:`AgentEvent` or list.

    Most kinds fan out 1:1, but some (notably claude's ``assistant``
    frames carrying multiple content blocks — see :func:`_make_assistant`)
    can emit multiple canonical events per line. Callers should treat the
    return value uniformly via :func:`parse_stream`, which flattens the
    list path.

    Parameters
    ----------
    line
        One NDJSON line from the provider subprocess stdout. The trailing
        newline may or may not be present.

    Returns
    -------
    AgentEvent | list[AgentEvent]
        Canonical event(s). Unknown kinds yield :class:`OtherEvent`.

    Raises
    ------
    AgentStreamError
        If the line is empty after whitespace stripping, exceeds
        ``MAX_LINE_BYTES``, or is not valid JSON. UTF-8 decoding uses
        ``errors="replace"`` so byte-level glitches surface as a
        replacement character rather than raising — but if the resulting
        text fails to parse as JSON, the failure does propagate.
    """
    if not isinstance(line, (bytes, bytearray)):
        raise AgentStreamError(f"expected bytes line, got {type(line).__name__}")
    if len(line) > MAX_LINE_BYTES:
        raise AgentStreamError(f"stream-json frame exceeds {MAX_LINE_BYTES} bytes ({len(line)} bytes)")
    try:
        text = bytes(line).decode("utf-8", errors="replace").strip()
    except (UnicodeDecodeError, AttributeError) as exc:  # pragma: no cover - safety
        raise AgentStreamError(f"failed to decode stream-json line: {exc}") from exc
    if not text:
        raise AgentStreamError("empty stream-json line")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentStreamError(f"invalid JSON in stream-json line: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise AgentStreamError(f"stream-json line is not a JSON object: {type(payload).__name__}")

    kind = _extract_kind(payload)
    if kind is None:
        logger.info("stream_json: payload missing kind/type; routing to OtherEvent")
        return OtherEvent(kind="other", raw=payload)

    builder = _DISPATCH.get(kind)
    if builder is None:
        logger.info("stream_json: unknown event kind %r; routing to OtherEvent", kind)
        return OtherEvent(kind=kind, raw=payload)

    logger.debug("stream_json: parsed event kind=%s", kind)
    return builder(payload)  # type: ignore[no-any-return]


async def parse_stream(stream: AsyncIterator[bytes]) -> AsyncIterator[AgentEvent]:
    """Yield canonical :class:`AgentEvent`s from a byte chunk stream.

    Implements line-buffered NDJSON splitting with a 1 MiB hard cap.
    Partial lines are buffered across chunks until a newline arrives;
    trailing data without a newline at stream end is emitted as a final
    line (if non-empty).

    Parameters
    ----------
    stream
        Async iterator yielding bytes chunks. Chunks may carry any number
        of newlines (zero or many).

    Yields
    ------
    AgentEvent
        Canonical events in order of arrival.

    Raises
    ------
    AgentStreamError
        On oversized line or JSON / UTF-8 failure inside a complete line.
    """
    buffer = bytearray()
    async for chunk in stream:
        if not chunk:
            continue
        buffer.extend(chunk)
        if len(buffer) > MAX_LINE_BYTES and b"\n" not in buffer:
            raise AgentStreamError(
                f"stream-json line buffer exceeds {MAX_LINE_BYTES} bytes ({len(buffer)} bytes) without a newline"
            )
        while True:
            newline_index = buffer.find(b"\n")
            if newline_index < 0:
                break
            line = bytes(buffer[:newline_index])
            del buffer[: newline_index + 1]
            if not line.strip():
                # Tolerate blank separator lines silently.
                continue
            parsed = parse_event(line)
            if isinstance(parsed, list):
                for ev in parsed:
                    yield ev
            else:
                yield parsed

    if buffer.strip():
        # Stream ended without a trailing newline; flush the residual line.
        parsed = parse_event(bytes(buffer))
        if isinstance(parsed, list):
            for ev in parsed:
                yield ev
        else:
            yield parsed
