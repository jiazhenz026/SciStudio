"""ADR-051 audit P2-1 / #1517: interactive_complete is run-scoped.

The process-global EventBus fans every event to every live scheduler. An
``interactive_complete`` carrying a ``workflow_id`` must be honoured only by the
matching run, so a browser confirm cannot resolve a colliding ``block_id``
future in a different concurrent run. A frame without ``workflow_id`` is
fail-open (legacy), and the scoping ``workflow_id`` never leaks into the
recorded decision.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from scistudio.engine.events import INTERACTIVE_COMPLETE, EngineEvent, EventBus
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import WorkflowDefinition


def _make_scheduler(wf_id: str) -> tuple[DAGScheduler, EventBus]:
    wf = WorkflowDefinition(id=wf_id, description="scoping", nodes=[], edges=[])
    event_bus = EventBus()
    scheduler = DAGScheduler(
        workflow=wf,
        event_bus=event_bus,
        resource_manager=MagicMock(),
        process_registry=MagicMock(),
        runner=AsyncMock(),
        registry=MagicMock(),
    )
    return scheduler, event_bus


def test_mismatched_workflow_id_does_not_resolve_future() -> None:
    async def go() -> None:
        scheduler, event_bus = _make_scheduler("wf-A")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict] = loop.create_future()
        scheduler._interactive_futures["node1"] = future

        # A confirm for a DIFFERENT run with the same block_id must be ignored.
        await event_bus.emit(
            EngineEvent(
                event_type=INTERACTIVE_COMPLETE,
                block_id="node1",
                data={"workflow_id": "wf-OTHER", "response": {"choice": 9}},
            )
        )
        assert not future.done(), "a foreign run's confirm must not resolve this run's future"

        # The matching run resolves it, with the decision only (no workflow_id leak).
        await event_bus.emit(
            EngineEvent(
                event_type=INTERACTIVE_COMPLETE,
                block_id="node1",
                data={"workflow_id": "wf-A", "response": {"choice": 3}},
            )
        )
        assert future.done()
        assert future.result() == {"choice": 3}

    asyncio.run(go())


def test_absent_workflow_id_is_fail_open_and_strips_scoping() -> None:
    async def go() -> None:
        scheduler, event_bus = _make_scheduler("wf-A")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict] = loop.create_future()
        scheduler._interactive_futures["node1"] = future

        # Legacy flat frame (no workflow_id) resolves fail-open; a stray
        # workflow_id in a flat frame is stripped from the recorded decision.
        await event_bus.emit(
            EngineEvent(
                event_type=INTERACTIVE_COMPLETE,
                block_id="node1",
                data={"workflow_id": "wf-A", "choice": 7},
            )
        )
        assert future.result() == {"choice": 7}

    asyncio.run(go())
