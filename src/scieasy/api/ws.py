"""WebSocket handler — bidirectional real-time block state and cancellation.

ADR-018: WebSocket becomes bidirectional. Server pushes block state changes;
client sends cancel requests and interactive completions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from scieasy.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_PAUSED,
    BLOCK_READY,
    BLOCK_RUNNING,
    BLOCK_SKIPPED,
    CANCEL_BLOCK_REQUEST,
    CANCEL_WORKFLOW_REQUEST,
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    WORKFLOW_CHANGED,
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
    EngineEvent,
    EventBus,
)

logger = logging.getLogger(__name__)

# Event types pushed to the client.
_OUTBOUND_EVENTS = frozenset(
    {
        BLOCK_READY,
        BLOCK_RUNNING,
        BLOCK_PAUSED,
        BLOCK_DONE,
        BLOCK_ERROR,
        BLOCK_CANCELLED,
        BLOCK_SKIPPED,
        WORKFLOW_COMPLETED,
        WORKFLOW_STARTED,
        INTERACTIVE_PROMPT,
        # #718 part (a): forward workflow.changed so connected clients can
        # refresh their cached workflow view when an external writer (another
        # tab, the embedded coding agent, or POST /import-path) mutates the
        # workflow YAML.
        WORKFLOW_CHANGED,
    }
)


def serialise_event(event: EngineEvent) -> dict[str, Any]:
    """Convert an EngineEvent to a JSON-serialisable dict for the WebSocket protocol."""
    return {
        "type": event.event_type,
        "block_id": event.block_id,
        "workflow_id": event.data.get("workflow_id") if isinstance(event.data, dict) else None,
        "data": event.data,
        "timestamp": event.timestamp.isoformat(),
    }


async def websocket_handler(websocket: WebSocket, event_bus: EventBus) -> None:
    """Handle a WebSocket connection for real-time workflow updates.

    ADR-018: Bidirectional protocol.
    - Inbound: client sends cancel_block, cancel_workflow, interactive_complete.
    - Outbound: server pushes all block state changes and workflow completion.
    """
    await websocket.accept()

    outbound_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def _on_event(event: EngineEvent) -> None:
        """Callback for EventBus — enqueue event for outbound delivery."""
        outbound_queue.put_nowait(serialise_event(event))

    # Subscribe to all outbound event types.
    for event_type in _OUTBOUND_EVENTS:
        event_bus.subscribe(event_type, _on_event)

    async def _inbound_loop() -> None:
        """Read messages from the client and dispatch to EventBus."""
        try:
            while True:
                raw = await websocket.receive_text()
                data = json.loads(raw)
                msg_type = data.get("type", "")

                if msg_type == "cancel_block":
                    block_id = data.get("block_id")
                    workflow_id = data.get("workflow_id")
                    if not block_id or not workflow_id:
                        logger.warning("cancel_block message missing block_id or workflow_id")
                        continue
                    await event_bus.emit(
                        EngineEvent(
                            event_type=CANCEL_BLOCK_REQUEST,
                            block_id=block_id,
                            data={"workflow_id": workflow_id},
                        )
                    )
                elif msg_type == "cancel_workflow":
                    workflow_id = data.get("workflow_id")
                    if not workflow_id:
                        logger.warning("cancel_workflow message missing workflow_id")
                        continue
                    await event_bus.emit(
                        EngineEvent(
                            event_type=CANCEL_WORKFLOW_REQUEST,
                            data={"workflow_id": workflow_id},
                        )
                    )
                elif msg_type == "interactive_complete":
                    await event_bus.emit(
                        EngineEvent(
                            event_type=INTERACTIVE_COMPLETE,
                            block_id=data.get("block_id"),
                            data=data.get("data", {}),
                        )
                    )
                else:
                    logger.warning("Unknown WebSocket message type: %s", msg_type)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    async def _outbound_loop() -> None:
        """Send queued events to the client."""
        try:
            while True:
                payload = await outbound_queue.get()
                await websocket.send_json(payload)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    try:
        await asyncio.gather(_inbound_loop(), _outbound_loop())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        for event_type in _OUTBOUND_EVENTS:
            event_bus.unsubscribe(event_type, _on_event)
