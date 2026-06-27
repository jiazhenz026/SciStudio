"""ADR-051 SC-001: end-to-end two-phase subprocess interactive execution.

Drives a real :class:`DAGScheduler` with a real :class:`LocalRunner` over the
``SelectOptionBlock`` test fixture: the prompt phase builds the panel view in a
worker subprocess, the engine holds the pause, and the compute phase runs the
block in a fresh worker subprocess with the injected decision. Asserts the
pause-decide-compute loop produces the expected output and that the decision is
recorded in the BLOCK_DONE lineage config (FR-011).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import MagicMock

import pytest

from scistudio.engine.events import (
    BLOCK_DONE,
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    EngineEvent,
    EventBus,
)
from scistudio.engine.runners.local import LocalRunner
from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import NodeDef, WorkflowDefinition

pytestmark = pytest.mark.timeout(120)


def _instantiate_select_option(name: str, config: dict[str, Any] | None = None) -> Any:
    from tests.fixtures.interactive_blocks import SelectOptionBlock

    return SelectOptionBlock(config or {})


def _make_scheduler() -> tuple[DAGScheduler, EventBus, list[EngineEvent]]:
    wf = WorkflowDefinition(
        id="wf-two-phase",
        description="ADR-051 two-phase e2e",
        nodes=[NodeDef(id="a", block_type="select-option", config={"options": [0, 1, 2, 3]})],
        edges=[],
    )
    event_bus = EventBus()
    # Real LocalRunner + real ProcessRegistry: both phases run in real worker
    # subprocesses (the point of this e2e). Only the block registry and resource
    # manager are mocked.
    process_registry = ProcessRegistry()
    runner = LocalRunner(event_bus=event_bus, registry=process_registry)
    done_events: list[EngineEvent] = []
    event_bus.subscribe(BLOCK_DONE, lambda e: done_events.append(e))

    registry = MagicMock()
    registry.instantiate.side_effect = _instantiate_select_option
    registry.get_spec.return_value = None
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True

    scheduler = DAGScheduler(
        workflow=wf,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        registry=registry,
    )
    return scheduler, event_bus, done_events


async def _drive(scheduler: DAGScheduler, event_bus: EventBus, choice: int) -> None:
    spawned: list[asyncio.Task] = []
    prompts: list[EngineEvent] = []

    async def _emit_complete(block_id: str | None) -> None:
        # Mirror the real api/ws.py frame shape: run-scoping workflow_id
        # alongside the decision nested under ``response`` (ADR-051 P2-1).
        await event_bus.emit(
            EngineEvent(
                event_type=INTERACTIVE_COMPLETE,
                block_id=block_id,
                data={"workflow_id": scheduler._workflow.id, "response": {"choice": choice}},
            )
        )

    async def _on_prompt(event: EngineEvent) -> None:
        prompts.append(event)
        spawned.append(asyncio.create_task(_emit_complete(event.block_id)))

    event_bus.subscribe(INTERACTIVE_PROMPT, _on_prompt)
    await scheduler.execute()
    if spawned:
        await asyncio.gather(*spawned, return_exceptions=True)
    scheduler._adr051_prompts = prompts  # type: ignore[attr-defined]


def test_two_phase_pause_decide_compute_end_to_end() -> None:
    from scistudio.blocks.base.state import BlockState

    scheduler, event_bus, done_events = _make_scheduler()
    asyncio.run(_drive(scheduler, event_bus, choice=3))

    # The block completed the pause-decide-compute loop.
    assert scheduler._block_states["a"] == BlockState.DONE
    outputs = scheduler._block_outputs["a"]
    assert outputs["selected"] == 3, "compute phase did not run with the injected decision"

    # The prompt carried the panel manifest (FR-007) and nested panel payload.
    prompts = scheduler._adr051_prompts  # type: ignore[attr-defined]
    assert len(prompts) == 1
    pdata = prompts[0].data
    assert pdata["panel_manifest"]["panel_id"] == "test.interactive.select_option"
    assert pdata["panel_payload"]["options"] == [0, 1, 2, 3]
    # panel_payload is nested, not spread, so it cannot clobber identity fields.
    assert "options" not in pdata
    # SC-001 (direct): prepare_prompt ran in a worker subprocess, so the pid it
    # recorded differs from this test/engine process's pid.
    assert pdata["panel_payload"]["prompt_pid"] != os.getpid()

    # FR-011: the decision is recorded in the BLOCK_DONE lineage config, and the
    # environment sidecar is populated (proving the compute ran in a subprocess).
    assert done_events, "no BLOCK_DONE emitted"
    done = done_events[-1].data
    assert done["config"]["interactive_response"] == {"choice": 3}
    assert done["environment"], "compute phase environment sidecar missing (not a subprocess?)"
