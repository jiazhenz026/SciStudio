"""Stream-JSON (NDJSON) parser for provider IPC.

The agent provider's subprocess emits one JSON event per stdout line.
This module owns the canonical event-kind taxonomy and the bounded,
defensive parser that translates raw bytes into typed
:class:`scieasy.ai.agent.provider.AgentEvent` instances.

Phase 1 ships only the stubs; T-ECA-103 implements:

* line-buffered NDJSON parsing with a 1 MiB-per-event soft cap;
* canonical event-kind normalisation
  (``init``, ``assistant_text_delta``, ``tool_use``, ``tool_result``,
  ``permission_request``, ``error``, ``done``);
* the ``OtherEvent`` catch-all for unknown kinds (spec §3 OQ5);
* graceful handling of truncated, non-UTF-8, and oversized frames
  (:class:`scieasy.ai.agent.errors.AgentStreamError`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from scieasy.ai.agent.provider import AgentEvent


def parse_event(line: bytes) -> AgentEvent:
    """Parse one NDJSON line into a canonical :class:`AgentEvent`.

    Parameters
    ----------
    line
        One NDJSON line from the provider subprocess stdout. The
        trailing newline may or may not be present; the parser
        tolerates either.

    Returns
    -------
    AgentEvent
        Canonical event. Unknown kinds are normalised to
        ``AgentEvent(kind="other", raw={...})``.

    Raises
    ------
    NotImplementedError
        Always, in Phase 1. Implementation lands in T-ECA-103.
    """
    raise NotImplementedError("parse_event is implemented in T-ECA-103")


async def parse_stream(stream: AsyncIterator[bytes]) -> AsyncIterator[AgentEvent]:
    """Async-generator wrapper around :func:`parse_event` for a byte stream.

    Parameters
    ----------
    stream
        Async iterator yielding chunks of bytes from the provider
        subprocess stdout. Chunks may not be line-aligned; the parser
        buffers internally.

    Yields
    ------
    AgentEvent
        Canonical events, in order of arrival.

    Raises
    ------
    NotImplementedError
        Always, in Phase 1. Implementation lands in T-ECA-103.
    """
    raise NotImplementedError("parse_stream is implemented in T-ECA-103")
    # The unreachable yield below satisfies the async-generator type
    # contract for mypy: it tells the type checker this is an
    # ``AsyncIterator``, not a coroutine.
    yield  # type: ignore[unreachable]
