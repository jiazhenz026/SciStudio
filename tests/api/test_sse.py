"""Tests for SSE log streaming."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from scistudio.api.runtime import ApiRuntime
from scistudio.api.sse import sse_handler


class _FakeRequest:
    """Minimal request-like object for exercising the SSE handler."""

    def __init__(self, app: object, query_params: dict[str, str]) -> None:
        self.app = app
        self.query_params = query_params

    async def is_disconnected(self) -> bool:
        return False


async def _read_first_data_event(iterator: AsyncIterator[str]) -> dict[str, str]:
    async for chunk in iterator:
        if chunk.startswith("event: log\ndata: "):
            payload = chunk.split("data: ", 1)[1].strip()
            return json.loads(payload)
    raise AssertionError("SSE stream ended before delivering a log event.")


def test_sse_stream_filters_logs(client, runtime: ApiRuntime) -> None:
    """SSE should stream matching log events and ignore non-matching ones."""

    async def exercise() -> dict[str, str]:
        request = _FakeRequest(client.app, {"workflow_id": "wf-1", "level": "error"})
        response = await sse_handler(request)

        await runtime.log_broadcaster.publish(level="info", message="ignore", workflow_id="other")
        await runtime.log_broadcaster.publish(
            level="error",
            message="match me",
            workflow_id="wf-1",
            block_id="node-9",
        )

        payload = await _read_first_data_event(response.body_iterator)
        await response.body_iterator.aclose()
        return payload

    payload = asyncio.run(exercise())
    assert payload["message"] == "match me"
    assert payload["workflow_id"] == "wf-1"
    assert payload["block_id"] == "node-9"
