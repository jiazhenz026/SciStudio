"""Server-Sent Events for execution log streaming."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse


async def sse_handler(request: Request) -> StreamingResponse:
    """Stream execution logs to the client via Server-Sent Events."""
    runtime = request.app.state.runtime
    queue = runtime.log_broadcaster.subscribe()
    workflow_filter = request.query_params.get("workflow_id")
    # #2433: ``run_id`` narrows the stream to one run of a workflow.
    run_filter = request.query_params.get("run_id")
    block_filter = request.query_params.get("block_id")
    level_filter = request.query_params.get("level")

    async def _stream() -> Any:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=1.0)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if item is runtime.log_broadcaster.END:
                    # The backend is stopping. Ending the stream lets the web
                    # server's wait for open connections finish (#2327).
                    break
                if workflow_filter and item.get("workflow_id") != workflow_filter:
                    continue
                if run_filter and item.get("run_id") != run_filter:
                    continue
                if block_filter and item.get("block_id") != block_filter:
                    continue
                if level_filter and item.get("level") != level_filter:
                    continue

                yield f"event: log\ndata: {json.dumps(item)}\n\n"
        finally:
            runtime.log_broadcaster.unsubscribe(queue)

    return StreamingResponse(_stream(), media_type="text/event-stream")
