"""Executable scheduler state-machine contract.

The architecture state table is small enough to keep as a table-driven test:

* ``cancel_block`` may only produce ``CANCELLED`` from ``RUNNING``/``PAUSED``.
* ``cancel_workflow`` cancels active blocks and skips not-yet-started blocks.
* ``PROCESS_EXITED`` only turns ``RUNNING`` into ``ERROR``.
* Scheduler-owned readiness transitions must emit ``BLOCK_READY`` exactly once.

Rows marked ``xfail`` are known drift from issue #1376. They stay visible here
so the suite describes the full desired contract without requiring product-code
changes in this test-only PR.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_READY,
    BLOCK_RUNNING,
    BLOCK_SKIPPED,
    CANCEL_BLOCK_REQUEST,
    CANCEL_WORKFLOW_REQUEST,
    PROCESS_EXITED,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

TERMINAL_STATES = {
    BlockState.DONE,
    BlockState.ERROR,
    BlockState.CANCELLED,
    BlockState.SKIPPED,
}


@dataclass(frozen=True)
class EventCapture:
    """Lifecycle events emitted during one scheduler operation."""

    event_type: str
    block_id: str | None


def _workflow() -> WorkflowDefinition:
    """Three-node chain: A -> B -> C."""
    return WorkflowDefinition(
        id="state-machine-contract",
        nodes=[
            NodeDef(id="A", block_type="type.a", config={"role": "root"}),
            NodeDef(id="B", block_type="type.b", config={"role": "middle"}),
            NodeDef(id="C", block_type="type.c", config={"role": "leaf"}),
        ],
        edges=[
            EdgeDef(source="A:out", target="B:in"),
            EdgeDef(source="B:out", target="C:in"),
        ],
    )


def _make_scheduler() -> tuple[DAGScheduler, EventBus]:
    """Build a scheduler with mocked dependencies and deterministic runner."""
    bus = EventBus()
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None
    runner = AsyncMock()
    runner.run.return_value = {"out": "ok"}
    scheduler = DAGScheduler(
        workflow=_workflow(),
        event_bus=bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
    )
    return scheduler, bus


def _capture_lifecycle(bus: EventBus) -> list[EventCapture]:
    """Capture scheduler lifecycle events relevant to the state table."""
    seen: list[EventCapture] = []

    def _append(event: EngineEvent) -> None:
        seen.append(EventCapture(event_type=event.event_type, block_id=event.block_id))

    for event_type in (
        BLOCK_READY,
        BLOCK_RUNNING,
        BLOCK_DONE,
        BLOCK_ERROR,
        BLOCK_CANCELLED,
        BLOCK_SKIPPED,
    ):
        bus.subscribe(event_type, _append)
    return seen


def _event_pairs(seen: list[EventCapture]) -> list[tuple[str, str | None]]:
    """Return the captured event stream as comparable tuples."""
    return [(event.event_type, event.block_id) for event in seen]


def _block_events(seen: list[EventCapture], block_id: str) -> list[str]:
    """Return lifecycle event names observed for one block."""
    return [event.event_type for event in seen if event.block_id == block_id]


def _state_map(
    *,
    a: BlockState = BlockState.DONE,
    b: BlockState,
    c: BlockState = BlockState.IDLE,
) -> dict[str, BlockState]:
    """Compact state setup for the A -> B -> C workflow."""
    return {"A": a, "B": b, "C": c}


async def _emit(
    bus: EventBus, event_type: str, block_id: str | None = None, data: dict[str, Any] | None = None
) -> None:
    await bus.emit(EngineEvent(event_type=event_type, block_id=block_id, data=data or {}))


@pytest.mark.parametrize(
    ("initial", "expected_b", "expected_c", "expected_events"),
    [
        pytest.param(
            BlockState.IDLE,
            BlockState.IDLE,
            BlockState.IDLE,
            [],
            marks=pytest.mark.xfail(reason="#1376: cancel_block currently cancels IDLE blocks", strict=True),
            id="IDLE-noop",
        ),
        pytest.param(
            BlockState.READY,
            BlockState.READY,
            BlockState.IDLE,
            [],
            marks=pytest.mark.xfail(reason="#1376: cancel_block currently cancels READY blocks", strict=True),
            id="READY-noop",
        ),
        pytest.param(
            BlockState.RUNNING,
            BlockState.CANCELLED,
            BlockState.SKIPPED,
            [(BLOCK_CANCELLED, "B"), (BLOCK_SKIPPED, "C")],
            id="RUNNING-cancelled",
        ),
        pytest.param(
            BlockState.PAUSED,
            BlockState.CANCELLED,
            BlockState.SKIPPED,
            [(BLOCK_CANCELLED, "B"), (BLOCK_SKIPPED, "C")],
            id="PAUSED-cancelled",
        ),
        pytest.param(
            BlockState.DONE,
            BlockState.DONE,
            BlockState.IDLE,
            [],
            marks=pytest.mark.xfail(reason="#1376: cancel_block currently cancels DONE blocks", strict=True),
            id="DONE-noop",
        ),
        pytest.param(
            BlockState.ERROR,
            BlockState.ERROR,
            BlockState.IDLE,
            [],
            marks=pytest.mark.xfail(reason="#1376: cancel_block currently cancels ERROR blocks", strict=True),
            id="ERROR-noop",
        ),
        pytest.param(
            BlockState.CANCELLED,
            BlockState.CANCELLED,
            BlockState.IDLE,
            [],
            marks=pytest.mark.xfail(reason="#1376: cancel_block currently re-emits CANCELLED", strict=True),
            id="CANCELLED-noop",
        ),
        pytest.param(
            BlockState.SKIPPED,
            BlockState.SKIPPED,
            BlockState.IDLE,
            [],
            marks=pytest.mark.xfail(reason="#1376: cancel_block currently cancels SKIPPED blocks", strict=True),
            id="SKIPPED-noop",
        ),
    ],
)
def test_cancel_block_state_table(
    initial: BlockState,
    expected_b: BlockState,
    expected_c: BlockState,
    expected_events: list[tuple[str, str]],
) -> None:
    """``cancel_block`` follows the architecture state table for all states."""
    scheduler, bus = _make_scheduler()
    seen = _capture_lifecycle(bus)
    scheduler._block_states.update(_state_map(b=initial))
    scheduler._block_outputs["A"] = {"out": "done"}

    asyncio.run(_emit(bus, CANCEL_BLOCK_REQUEST, block_id="B"))

    assert scheduler._block_states["B"] == expected_b
    assert scheduler._block_states["C"] == expected_c
    assert [(event.event_type, event.block_id) for event in seen] == expected_events


@pytest.mark.parametrize(
    ("initial", "expected_b", "expected_events"),
    [
        (BlockState.IDLE, BlockState.SKIPPED, [(BLOCK_SKIPPED, "B")]),
        (BlockState.READY, BlockState.SKIPPED, [(BLOCK_SKIPPED, "B")]),
        (BlockState.RUNNING, BlockState.CANCELLED, [(BLOCK_CANCELLED, "B")]),
        (BlockState.PAUSED, BlockState.CANCELLED, [(BLOCK_CANCELLED, "B")]),
        (BlockState.DONE, BlockState.DONE, []),
        (BlockState.ERROR, BlockState.ERROR, []),
        (BlockState.CANCELLED, BlockState.CANCELLED, []),
        (BlockState.SKIPPED, BlockState.SKIPPED, []),
    ],
    ids=lambda value: value.name if isinstance(value, BlockState) else None,
)
def test_cancel_workflow_state_table(
    initial: BlockState,
    expected_b: BlockState,
    expected_events: list[tuple[str, str]],
) -> None:
    """``cancel_workflow`` cancels active states and skips not-yet-started states."""
    scheduler, bus = _make_scheduler()
    seen = _capture_lifecycle(bus)
    scheduler._block_states.update(_state_map(b=initial, c=BlockState.DONE))
    scheduler._block_outputs["A"] = {"out": "done"}
    if initial == BlockState.DONE:
        scheduler._block_outputs["B"] = {"out": "done"}

    asyncio.run(_emit(bus, CANCEL_WORKFLOW_REQUEST))

    assert scheduler._block_states["B"] == expected_b
    assert scheduler._block_states["C"] == BlockState.DONE
    assert [(event.event_type, event.block_id) for event in seen] == expected_events


@pytest.mark.parametrize(
    ("initial", "expected", "expected_events"),
    [
        (BlockState.IDLE, BlockState.IDLE, []),
        (BlockState.READY, BlockState.READY, []),
        (BlockState.RUNNING, BlockState.ERROR, [(BLOCK_ERROR, "B")]),
        (BlockState.PAUSED, BlockState.PAUSED, []),
        (BlockState.DONE, BlockState.DONE, []),
        (BlockState.ERROR, BlockState.ERROR, []),
        (BlockState.CANCELLED, BlockState.CANCELLED, []),
        (BlockState.SKIPPED, BlockState.SKIPPED, []),
    ],
    ids=lambda value: value.name if isinstance(value, BlockState) else None,
)
def test_process_exited_state_table(
    initial: BlockState,
    expected: BlockState,
    expected_events: list[tuple[str, str]],
) -> None:
    """Unexpected process exit is only meaningful for ``RUNNING`` blocks."""
    scheduler, bus = _make_scheduler()
    seen = _capture_lifecycle(bus)
    scheduler._block_states.update(_state_map(b=initial, c=BlockState.DONE))
    scheduler._block_outputs["A"] = {"out": "done"}

    asyncio.run(
        _emit(
            bus,
            PROCESS_EXITED,
            block_id="B",
            data={"exit_info": {"exit_code": -9, "signal_number": 9}},
        )
    )

    assert scheduler._block_states["B"] == expected
    assert scheduler._block_states["C"] == BlockState.DONE
    assert [(event.event_type, event.block_id) for event in seen] == expected_events


@pytest.mark.parametrize("terminal_state", sorted(TERMINAL_STATES, key=lambda state: state.value))
def test_reset_block_terminal_to_idle_then_ready_contract(terminal_state: BlockState) -> None:
    """Resetting a terminal block re-enters the scheduler via ``IDLE -> READY``."""
    scheduler, bus = _make_scheduler()
    seen = _capture_lifecycle(bus)
    scheduler._dispatch = AsyncMock()
    scheduler._block_states.update(_state_map(b=terminal_state))
    scheduler._block_outputs["A"] = {"out": "done"}
    if terminal_state == BlockState.SKIPPED:
        scheduler.skip_reasons["B"] = "upstream A test"
    else:
        scheduler._block_outputs["B"] = {"out": "stale"}

    asyncio.run(scheduler.reset_block("B"))

    assert scheduler._block_states["B"] == BlockState.READY
    assert scheduler._block_states["C"] == BlockState.IDLE
    assert "B" not in scheduler._block_outputs
    assert "B" not in scheduler.skip_reasons
    assert [(event.event_type, event.block_id) for event in seen] == [(BLOCK_READY, "B")]


def test_execute_happy_path_emits_ready_running_done_once_per_block() -> None:
    """Normal execution emits each block's lifecycle triple exactly once.

    The EventBus invokes scheduler-internal subscribers before the test capture
    subscriber for ``BLOCK_DONE``. Successor ``BLOCK_READY`` events can therefore
    be captured before the predecessor ``BLOCK_DONE`` capture. That callback
    ordering is not part of the public contract; the public contract is the
    per-block lifecycle sequence and exact event cardinality.
    """
    scheduler, bus = _make_scheduler()
    seen = _capture_lifecycle(bus)

    asyncio.run(scheduler.execute())

    assert scheduler._block_states == {
        "A": BlockState.DONE,
        "B": BlockState.DONE,
        "C": BlockState.DONE,
    }
    assert _event_pairs(seen).count((BLOCK_READY, "A")) == 1
    assert _event_pairs(seen).count((BLOCK_READY, "B")) == 1
    assert _event_pairs(seen).count((BLOCK_READY, "C")) == 1
    assert _block_events(seen, "A") == [BLOCK_READY, BLOCK_RUNNING, BLOCK_DONE]
    assert _block_events(seen, "B") == [BLOCK_READY, BLOCK_RUNNING, BLOCK_DONE]
    assert _block_events(seen, "C") == [BLOCK_READY, BLOCK_RUNNING, BLOCK_DONE]


def test_runner_error_emits_error_and_downstream_skip_once() -> None:
    """A failed block emits one ``BLOCK_ERROR`` and skips each downstream block once.

    As with the happy path, EventBus callback order can capture the downstream
    skip before the failed block's error capture. The state-machine contract is
    exact cardinality and per-block lifecycle order.
    """
    scheduler, bus = _make_scheduler()
    seen = _capture_lifecycle(bus)

    async def _run(block: Any, inputs: dict[str, Any], config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        if block.id == "B":
            raise RuntimeError("B failed")
        return {"out": "ok"}

    scheduler._runner.run.side_effect = _run

    asyncio.run(scheduler.execute())

    assert scheduler._block_states == {
        "A": BlockState.DONE,
        "B": BlockState.ERROR,
        "C": BlockState.SKIPPED,
    }
    assert _block_events(seen, "A") == [BLOCK_READY, BLOCK_RUNNING, BLOCK_DONE]
    assert _block_events(seen, "B") == [BLOCK_READY, BLOCK_RUNNING, BLOCK_ERROR]
    assert _block_events(seen, "C") == [BLOCK_SKIPPED]
