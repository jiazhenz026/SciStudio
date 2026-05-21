"""Tests for DAGScheduler -- ADR-018."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import (
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_READY,
    CANCEL_BLOCK_REQUEST,
    CANCEL_WORKFLOW_REQUEST,
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wf(
    nodes: list[tuple[str, str]],
    edges: list[tuple[str, str]] | None = None,
) -> WorkflowDefinition:
    """Build a minimal WorkflowDefinition."""
    node_defs = [NodeDef(id=n_id, block_type=bt) for n_id, bt in nodes]
    edge_defs = [EdgeDef(source=s, target=t) for s, t in (edges or [])]
    return WorkflowDefinition(nodes=node_defs, edges=edge_defs)


def _make_scheduler(
    workflow: WorkflowDefinition,
    runner_return: dict | None = None,
    runner_side_effect: list | None = None,
) -> tuple[DAGScheduler, EventBus, AsyncMock]:
    """Create a DAGScheduler with mocked dependencies."""
    event_bus = EventBus()
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None

    runner = AsyncMock()
    if runner_side_effect is not None:
        runner.run.side_effect = runner_side_effect
    else:
        runner.run.return_value = runner_return or {"output": "mock_result"}

    scheduler = DAGScheduler(
        workflow=workflow,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
    )
    return scheduler, event_bus, runner


# ---------------------------------------------------------------------------
# Linear execution
# ---------------------------------------------------------------------------


class TestSchedulerLinear:
    """Test basic linear workflow execution."""

    def test_scheduler_linear_all_done(self) -> None:
        """A->B->C: all blocks should reach DONE state."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        scheduler, _event_bus, _runner = _make_scheduler(wf)

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_states["B"] == BlockState.DONE
        assert scheduler._block_states["C"] == BlockState.DONE

    def test_scheduler_emits_block_ready_on_idle_to_ready(self) -> None:
        """Regression #1327: BLOCK_READY fires for every IDLE->READY transition.

        The event is declared in :mod:`scistudio.engine.events`, listed
        in :data:`scistudio.api.ws._OUTBOUND_EVENTS` (so the frontend WS
        forwards it), and the event-routing table in ``events.py``
        names ``DAGScheduler`` as the emitter. Prior to this fix the
        scheduler transitioned blocks to ``READY`` without emitting,
        breaking the documented lifecycle contract.
        """
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        scheduler, event_bus, _runner = _make_scheduler(wf)

        ready_block_ids: list[str] = []
        event_bus.subscribe(BLOCK_READY, lambda e: ready_block_ids.append(e.block_id or ""))

        asyncio.run(scheduler.execute())

        # Every block in topo order must have produced exactly one
        # BLOCK_READY event. Order matters: A becomes ready at initial
        # dispatch; B and C become ready as their predecessors finish.
        assert ready_block_ids == ["A", "B", "C"], (
            f"expected BLOCK_READY for A, B, C in topo order; got {ready_block_ids}"
        )

    def test_scheduler_linear_execution_order(self) -> None:
        """A->B->C: runner.run() called in correct order."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        call_order: list[str] = []

        async def track_run(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            call_order.append(block.id)  # type: ignore[attr-defined]
            return {"output": f"result_{block.id}"}  # type: ignore[attr-defined]

        scheduler, _event_bus, runner = _make_scheduler(wf)
        runner.run.side_effect = track_run

        asyncio.run(scheduler.execute())

        assert call_order == ["A", "B", "C"]

    def test_scheduler_runner_called_with_correct_args(self) -> None:
        """Runner receives node, inputs, and config."""
        wf = _wf(nodes=[("A", "proc")])
        wf.nodes[0].config = {"param": "value"}
        scheduler, _event_bus, runner = _make_scheduler(wf)

        asyncio.run(scheduler.execute())

        runner.run.assert_called_once()
        args = runner.run.call_args
        assert args[0][0].id == "A"
        assert args[0][1] == {}
        config = args[0][2]
        # Original config key preserved; enriched keys injected by #444
        assert config["param"] == "value"
        assert config["block_id"] == "A"
        assert "workflow_id" in config


# ---------------------------------------------------------------------------
# Empty workflow
# ---------------------------------------------------------------------------


class TestSchedulerEmpty:
    """Test empty workflow handling."""

    def test_scheduler_empty_workflow(self) -> None:
        """Empty workflow completes immediately without calling runner."""
        wf = _wf(nodes=[])
        scheduler, event_bus, runner = _make_scheduler(wf)

        events_received: list[str] = []
        event_bus.subscribe(
            WORKFLOW_STARTED,
            lambda e: events_received.append(WORKFLOW_STARTED),
        )
        event_bus.subscribe(
            WORKFLOW_COMPLETED,
            lambda e: events_received.append(WORKFLOW_COMPLETED),
        )

        asyncio.run(scheduler.execute())

        assert WORKFLOW_STARTED in events_received
        assert WORKFLOW_COMPLETED in events_received
        runner.run.assert_not_called()


# ---------------------------------------------------------------------------
# Error and skip propagation
# ---------------------------------------------------------------------------


class TestSchedulerErrorPropagation:
    """Test error handling and skip propagation."""

    def test_scheduler_error_skips_downstream(self) -> None:
        """A(error)->B->C: B and C should be SKIPPED."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )

        async def fail_on_a(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            if block.id == "A":  # type: ignore[attr-defined]
                raise RuntimeError("Block A failed")
            return {"output": "ok"}

        scheduler, _event_bus, runner = _make_scheduler(wf)
        runner.run.side_effect = fail_on_a

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.ERROR
        assert scheduler._block_states["B"] == BlockState.SKIPPED
        assert scheduler._block_states["C"] == BlockState.SKIPPED
        assert "A" in scheduler.skip_reasons["B"]
        assert "A" in scheduler.skip_reasons["C"]

    def test_scheduler_diamond_partial_error(self) -> None:
        """Diamond A->B,C->D: if B errors but C succeeds, D is skipped."""
        wf = _wf(
            nodes=[
                ("A", "proc"),
                ("B", "proc"),
                ("C", "proc"),
                ("D", "proc"),
            ],
            edges=[
                ("A:out", "B:in"),
                ("A:out", "C:in"),
                ("B:out", "D:in1"),
                ("C:out", "D:in2"),
            ],
        )

        async def fail_on_b(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            if block.id == "B":  # type: ignore[attr-defined]
                raise RuntimeError("Block B failed")
            return {"output": "ok"}

        scheduler, _event_bus, runner = _make_scheduler(wf)
        runner.run.side_effect = fail_on_b

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_states["B"] == BlockState.ERROR
        assert scheduler._block_states["C"] == BlockState.DONE
        assert scheduler._block_states["D"] == BlockState.SKIPPED


# ---------------------------------------------------------------------------
# #681: Worker-reported terminal state propagation
# ---------------------------------------------------------------------------


class TestSchedulerWorkerReportedTerminalState:
    """#681: when ``LocalRunner.run()`` raises ``BlockTerminalStateReportedError``,
    the scheduler must record the block in the reported state (CANCELLED /
    ERROR / SKIPPED) rather than ERROR (the default for arbitrary exceptions).
    """

    def test_runner_reports_cancelled_records_cancelled(self) -> None:
        """A block whose worker subprocess reports CANCELLED ends up CANCELLED.

        Regression for #681 / AppBlock cancellation: AppBlock now signals
        cancellation by raising ``BlockCancelledByAppError`` (#1334), which the
        worker translates into a ``final_state="cancelled"`` envelope. The
        scheduler then sees the cancellation via the existing
        ``BlockTerminalStateReportedError`` mechanism instead of treating
        the empty ``return {}`` as DONE.
        """
        from scistudio.engine.runners.terminal_state import BlockTerminalStateReportedError

        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )

        async def reports_cancelled(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            if block.id == "A":  # type: ignore[attr-defined]
                raise BlockTerminalStateReportedError(
                    state=BlockState.CANCELLED,
                    outputs={},
                )
            return {"output": "ok"}

        scheduler, _event_bus, runner = _make_scheduler(wf)
        runner.run.side_effect = reports_cancelled

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.CANCELLED
        assert scheduler._block_states["B"] == BlockState.SKIPPED
        assert scheduler._block_states["C"] == BlockState.SKIPPED

    def test_runner_reports_error_records_error_not_default(self) -> None:
        """``BlockTerminalStateReportedError(ERROR)`` records ERROR via the
        worker-reported path (and emits BLOCK_ERROR + propagates skip),
        equivalent to the generic exception path in observable behaviour.
        """
        from scistudio.engine.runners.terminal_state import BlockTerminalStateReportedError

        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out", "B:in")],
        )

        async def reports_error(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            if block.id == "A":  # type: ignore[attr-defined]
                raise BlockTerminalStateReportedError(
                    state=BlockState.ERROR,
                    outputs={},
                )
            return {"output": "ok"}

        scheduler, _event_bus, runner = _make_scheduler(wf)
        runner.run.side_effect = reports_error

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.ERROR
        assert scheduler._block_states["B"] == BlockState.SKIPPED

    def test_normal_block_returning_dict_still_records_done(self) -> None:
        """Regression: a block that returns ``{outputs}`` without raising
        ``BlockTerminalStateReportedError`` still records DONE — the new exception
        path does not affect the happy path.
        """
        wf = _wf(nodes=[("A", "proc")])
        scheduler, _event_bus, _runner = _make_scheduler(wf, runner_return={"output": "ok"})

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_outputs["A"] == {"output": "ok"}

    def test_runner_reports_cancelled_preserves_partial_outputs(self) -> None:
        """When the worker forwards partial outputs alongside CANCELLED, the
        scheduler stores them in ``_block_outputs`` so checkpoints / lineage
        see the same view.
        """
        from scistudio.engine.runners.terminal_state import BlockTerminalStateReportedError

        wf = _wf(nodes=[("A", "proc")])

        async def reports_cancelled_with_partial(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            raise BlockTerminalStateReportedError(
                state=BlockState.CANCELLED,
                outputs={"partial": "value"},
            )

        scheduler, _event_bus, runner = _make_scheduler(wf)
        runner.run.side_effect = reports_cancelled_with_partial

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.CANCELLED
        assert scheduler._block_outputs.get("A") == {"partial": "value"}

    def test_pre_cancelled_state_preserved_against_worker_error(self) -> None:
        """#689 cancel-race guard: if ``_on_cancel_block`` already pre-set
        the block to CANCELLED while the worker was finalising a different
        terminal state (ERROR / SKIPPED), the CANCELLED state must be
        preserved and the runner's reported state must not overwrite it.

        Exercises ``_run_and_finalize`` directly with a pre-set CANCELLED
        state to simulate the race window between ``_on_cancel_block``
        marking CANCELLED and the worker's ``BlockTerminalStateReportedError``
        unwinding through ``_run_and_finalize``.
        """
        from scistudio.engine.runners.terminal_state import BlockTerminalStateReportedError

        wf = _wf(nodes=[("A", "proc")])
        scheduler, event_bus, runner = _make_scheduler(wf)

        async def reports_error(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            raise BlockTerminalStateReportedError(
                state=BlockState.ERROR,
                outputs={},
            )

        runner.run.side_effect = reports_error

        # Capture any contradictory events that would follow CANCELLED.
        emitted: list[str] = []
        event_bus.subscribe(BLOCK_ERROR, lambda e: emitted.append(BLOCK_ERROR))

        # Pre-set CANCELLED as _on_cancel_block would have done.
        scheduler._block_states["A"] = BlockState.CANCELLED

        block = MagicMock()
        block.id = "A"
        asyncio.run(scheduler._run_and_finalize("A", block, {}, {}))

        # CANCELLED must win and the worker's ERROR must not be emitted.
        assert scheduler._block_states["A"] == BlockState.CANCELLED
        assert BLOCK_ERROR not in emitted


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class TestSchedulerCancellation:
    """Test block and workflow cancellation."""

    def test_scheduler_cancel_block_skips_downstream(self) -> None:
        """Cancel a block -> downstream gets SKIPPED."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        scheduler, event_bus, _runner = _make_scheduler(wf)

        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"out": "data"}
        scheduler._block_states["B"] = BlockState.RUNNING

        asyncio.run(event_bus.emit(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="B")))

        assert scheduler._block_states["B"] == BlockState.CANCELLED
        assert scheduler._block_states["C"] == BlockState.SKIPPED
        assert "B" in scheduler.skip_reasons["C"]

    def test_scheduler_cancel_workflow(self) -> None:
        """Cancel workflow -> non-terminal blocks cancelled/skipped."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        scheduler, event_bus, _runner = _make_scheduler(wf)

        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"out": "data"}
        scheduler._block_states["B"] = BlockState.RUNNING
        scheduler._block_states["C"] = BlockState.IDLE

        asyncio.run(event_bus.emit(EngineEvent(event_type=CANCEL_WORKFLOW_REQUEST)))

        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_states["B"] == BlockState.CANCELLED
        assert scheduler._block_states["C"] == BlockState.SKIPPED


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------


class TestSchedulerPauseResume:
    """Test pause and resume functionality."""

    def test_pause_prevents_dispatch(self) -> None:
        """When paused, _dispatch does not run blocks."""
        wf = _wf(nodes=[("A", "proc")])
        scheduler, _event_bus, runner = _make_scheduler(wf)

        async def _run() -> None:
            await scheduler.pause()
            await scheduler._dispatch("A")

        asyncio.run(_run())

        runner.run.assert_not_called()

    def test_resume_dispatches_ready_blocks(self) -> None:
        """After resume, idle blocks with dependencies met get dispatched."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out", "B:in")],
        )
        scheduler, _event_bus, runner = _make_scheduler(wf)

        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"out": "data"}
        scheduler._block_states["B"] = BlockState.IDLE

        asyncio.run(scheduler.resume())

        assert scheduler._block_states["B"] == BlockState.DONE
        runner.run.assert_called_once()


# ---------------------------------------------------------------------------
# Event emission
# ---------------------------------------------------------------------------


class TestSchedulerEvents:
    """Test that the scheduler emits correct lifecycle events."""

    def test_workflow_events_emitted(self) -> None:
        """WORKFLOW_STARTED and WORKFLOW_COMPLETED are emitted."""
        wf = _wf(nodes=[("A", "proc")])
        scheduler, event_bus, _runner = _make_scheduler(wf)

        events_received: list[str] = []
        event_bus.subscribe(
            WORKFLOW_STARTED,
            lambda e: events_received.append(WORKFLOW_STARTED),
        )
        event_bus.subscribe(
            WORKFLOW_COMPLETED,
            lambda e: events_received.append(WORKFLOW_COMPLETED),
        )

        asyncio.run(scheduler.execute())

        assert events_received == [WORKFLOW_STARTED, WORKFLOW_COMPLETED]

    def test_block_done_event_emitted(self) -> None:
        """BLOCK_DONE event is emitted for each completed block."""
        wf = _wf(nodes=[("A", "proc"), ("B", "proc")])
        scheduler, event_bus, _runner = _make_scheduler(wf)

        done_blocks: list[str] = []
        event_bus.subscribe(
            BLOCK_DONE,
            lambda e: done_blocks.append(e.block_id) if e.block_id else None,
        )

        asyncio.run(scheduler.execute())

        assert "A" in done_blocks
        assert "B" in done_blocks


# ---------------------------------------------------------------------------
# Input gathering
# ---------------------------------------------------------------------------


class TestSchedulerInputGathering:
    """Test that inputs are gathered correctly from upstream outputs."""

    def test_inputs_passed_from_upstream(self) -> None:
        """B receives output from A via edge mapping."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:result", "B:data")],
        )

        received_inputs: list[dict] = []

        async def capture_inputs(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            if block.id == "B":  # type: ignore[attr-defined]
                received_inputs.append(inputs)
            return {"result": f"output_{block.id}"}  # type: ignore[attr-defined]

        scheduler, _event_bus, runner = _make_scheduler(wf)
        runner.run.side_effect = capture_inputs

        asyncio.run(scheduler.execute())

        assert len(received_inputs) == 1
        assert "data" in received_inputs[0]
        assert received_inputs[0]["data"] == "output_A"


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------


class TestSchedulerState:
    """Test state management helpers."""

    def test_set_state(self) -> None:
        """set_state overrides block state."""
        wf = _wf(nodes=[("A", "proc")])
        scheduler, _, _ = _make_scheduler(wf)

        scheduler.set_state("A", BlockState.DONE)
        assert scheduler._block_states["A"] == BlockState.DONE

    def test_save_checkpoint_does_not_raise(self) -> None:
        """save_checkpoint is a no-op placeholder, should not raise."""
        wf = _wf(nodes=[("A", "proc")])
        scheduler, _, _ = _make_scheduler(wf)
        scheduler.save_checkpoint()


# ---------------------------------------------------------------------------
# Registry injection (#119)
# ---------------------------------------------------------------------------


class TestSchedulerRegistryInjection:
    """Test BlockRegistry integration in DAGScheduler."""

    def test_dispatch_uses_registry_to_instantiate_block(self) -> None:
        """When registry is provided, runner receives Block instance, not NodeDef."""
        wf = _wf(nodes=[("A", "proc")])

        mock_block = MagicMock()
        mock_block.name = "MockBlock"

        registry = MagicMock()
        registry.instantiate.return_value = mock_block

        event_bus = EventBus()
        resource_manager = MagicMock()
        resource_manager.can_dispatch.return_value = True

        runner = AsyncMock()
        runner.run.return_value = {"output": "result"}

        scheduler = DAGScheduler(
            workflow=wf,
            event_bus=event_bus,
            resource_manager=resource_manager,
            process_registry=MagicMock(),
            runner=runner,
            registry=registry,
        )
        asyncio.run(scheduler.execute())

        # Registry was called with the block_type from NodeDef
        registry.instantiate.assert_called_once_with("proc", {})
        # Runner received the mock Block, not the NodeDef
        call_args = runner.run.call_args[0]
        assert call_args[0] is mock_block

    def test_dispatch_without_registry_passes_nodedef(self) -> None:
        """When registry is None, runner receives NodeDef (backward compat)."""
        wf = _wf(nodes=[("A", "proc")])
        scheduler, _event_bus, runner = _make_scheduler(wf)

        asyncio.run(scheduler.execute())

        call_args = runner.run.call_args[0]
        assert isinstance(call_args[0], NodeDef)
        assert call_args[0].id == "A"

    def test_dispatch_unregistered_block_type_emits_error(self) -> None:
        """When registry.instantiate raises KeyError, block state becomes error."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out", "B:in")],
        )

        registry = MagicMock()
        registry.instantiate.side_effect = KeyError("Block 'proc' is not registered.")

        event_bus = EventBus()
        resource_manager = MagicMock()
        resource_manager.can_dispatch.return_value = True

        error_blocks: list[str] = []
        event_bus.subscribe(
            BLOCK_ERROR,
            lambda e: error_blocks.append(e.block_id) if e.block_id else None,
        )

        runner = AsyncMock()
        runner.run.return_value = {"output": "result"}

        scheduler = DAGScheduler(
            workflow=wf,
            event_bus=event_bus,
            resource_manager=resource_manager,
            process_registry=MagicMock(),
            runner=runner,
            registry=registry,
        )
        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.ERROR
        assert "A" in error_blocks
        # B should be skipped because A errored
        assert scheduler._block_states["B"] == BlockState.SKIPPED
        # Runner was never called because instantiate failed
        runner.run.assert_not_called()


# ---------------------------------------------------------------------------
# Selective re-run (reset_block)
# ---------------------------------------------------------------------------


class TestResetBlock:
    """Tests for DAGScheduler.reset_block() selective re-run logic."""

    def test_reset_unknown_block_raises(self) -> None:
        """ValueError raised for unknown block_id."""
        wf = _wf(nodes=[("A", "proc")])
        scheduler, _, _ = _make_scheduler(wf)

        with pytest.raises(ValueError, match="Unknown block"):
            asyncio.run(scheduler.reset_block("NONEXISTENT"))

    def test_reset_error_block_to_idle(self) -> None:
        """Reset an ERROR block sets it to idle."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out", "B:in")],
        )
        scheduler, _, _runner = _make_scheduler(wf)
        # Mock _dispatch to prevent actual execution during reset
        scheduler._dispatch = AsyncMock()

        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"out": "data"}
        scheduler._block_states["B"] = BlockState.ERROR
        scheduler._block_outputs["B"] = {"out": "stale"}

        asyncio.run(scheduler.reset_block("B"))

        # B should be dispatched (ready since A is done)
        # After _dispatch mock, B state set to READY before dispatch
        assert scheduler._block_states["B"] == BlockState.READY
        assert "B" not in scheduler._block_outputs  # cleared during reset
        scheduler._dispatch.assert_called()

    def test_reset_cascades_to_skipped_downstream(self) -> None:
        """Reset block also resets SKIPPED downstream blocks."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc"), ("D", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in"), ("C:out", "D:in")],
        )
        scheduler, _, _ = _make_scheduler(wf)
        scheduler._dispatch = AsyncMock()

        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"out": "data"}
        scheduler._block_states["B"] = BlockState.ERROR
        scheduler._block_states["C"] = BlockState.SKIPPED
        scheduler.skip_reasons["C"] = "upstream B error"
        scheduler._block_states["D"] = BlockState.SKIPPED
        scheduler.skip_reasons["D"] = "upstream B error"

        asyncio.run(scheduler.reset_block("B"))

        # B reset to idle then dispatched (A is done), so state is READY
        assert scheduler._block_states["B"] == BlockState.READY
        # C and D should be reset from skipped to idle
        assert scheduler._block_states["C"] == BlockState.IDLE
        assert scheduler._block_states["D"] == BlockState.IDLE
        assert "C" not in scheduler.skip_reasons
        assert "D" not in scheduler.skip_reasons

    def test_reset_with_failed_upstream(self) -> None:
        """Reset walks upstream and resets non-DONE predecessors."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out", "B:in")],
        )
        scheduler, _, _ = _make_scheduler(wf)
        scheduler._dispatch = AsyncMock()

        scheduler._block_states["A"] = BlockState.ERROR
        scheduler._block_states["B"] = BlockState.SKIPPED
        scheduler.skip_reasons["B"] = "upstream A error"

        asyncio.run(scheduler.reset_block("B"))

        # A was reset from error to idle, then dispatched (no predecessors -> ready)
        assert scheduler._block_states["A"] == BlockState.READY
        # B was target, reset to idle; A not yet done so B stays idle
        assert scheduler._block_states["B"] == BlockState.IDLE

    def test_reset_preserves_done_blocks(self) -> None:
        """Done blocks are NOT reset -- only non-DONE upstream and SKIPPED downstream."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        scheduler, _, _ = _make_scheduler(wf)
        scheduler._dispatch = AsyncMock()

        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"out": "data"}
        scheduler._block_states["B"] = BlockState.ERROR
        scheduler._block_outputs["B"] = {"out": "stale"}
        scheduler._block_states["C"] = BlockState.SKIPPED
        scheduler.skip_reasons["C"] = "upstream B error"

        asyncio.run(scheduler.reset_block("B"))

        # A stays done -- it's a DONE upstream, should NOT be reset
        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_outputs["A"] == {"out": "data"}
        # B reset and dispatched (A is done)
        assert scheduler._block_states["B"] == BlockState.READY
        assert "B" not in scheduler._block_outputs
        # C reset from skipped to idle
        assert scheduler._block_states["C"] == BlockState.IDLE
        assert "C" not in scheduler.skip_reasons

    def test_reset_triggers_reexecution(self) -> None:
        """reset_block on errored block causes actual re-execution."""
        wf = _wf(nodes=[("A", "proc")])
        scheduler, _event_bus, runner = _make_scheduler(wf)
        asyncio.run(scheduler.execute())
        assert runner.run.call_count == 1

        # Simulate error state
        scheduler._block_states["A"] = BlockState.ERROR
        scheduler._block_outputs.pop("A", None)

        asyncio.run(scheduler.reset_block("A"))
        assert runner.run.call_count == 2


# ---------------------------------------------------------------------------
# PROCESS_EXITED handling (#163)
# ---------------------------------------------------------------------------


class TestSchedulerProcessExited:
    """Test DAGScheduler reaction to PROCESS_EXITED events."""

    def test_running_block_transitions_to_error(self) -> None:
        """A RUNNING block whose process exits unexpectedly → ERROR + skip downstream."""
        from scistudio.engine.events import PROCESS_EXITED

        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out", "B:in")],
        )
        scheduler, event_bus, _runner = _make_scheduler(wf)

        scheduler._block_states["A"] = BlockState.RUNNING

        asyncio.run(
            event_bus.emit(
                EngineEvent(
                    event_type=PROCESS_EXITED,
                    block_id="A",
                    data={"exit_info": {"exit_code": -9, "signal_number": 9}},
                )
            )
        )

        assert scheduler._block_states["A"] == BlockState.ERROR
        assert scheduler._block_states["B"] == BlockState.SKIPPED
        assert "A" in scheduler.skip_reasons["B"]

    def test_done_block_is_noop(self) -> None:
        """PROCESS_EXITED for an already-DONE block should not change state."""
        from scistudio.engine.events import PROCESS_EXITED

        wf = _wf(nodes=[("A", "proc")])
        scheduler, event_bus, _runner = _make_scheduler(wf)

        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"out": "data"}

        asyncio.run(
            event_bus.emit(
                EngineEvent(
                    event_type=PROCESS_EXITED,
                    block_id="A",
                    data={"exit_info": {"exit_code": 0}},
                )
            )
        )

        assert scheduler._block_states["A"] == BlockState.DONE

    def test_paused_block_is_noop(self) -> None:
        """PROCESS_EXITED for a PAUSED block (AppBlock) should not interfere."""
        from scistudio.engine.events import PROCESS_EXITED

        wf = _wf(nodes=[("A", "app")])
        scheduler, event_bus, _runner = _make_scheduler(wf)

        scheduler._block_states["A"] = BlockState.PAUSED

        asyncio.run(
            event_bus.emit(
                EngineEvent(
                    event_type=PROCESS_EXITED,
                    block_id="A",
                    data={"exit_info": {"exit_code": 0}},
                )
            )
        )

        assert scheduler._block_states["A"] == BlockState.PAUSED

    def test_unknown_block_id_is_safe(self) -> None:
        """PROCESS_EXITED with a block_id not in the DAG should not crash."""
        from scistudio.engine.events import PROCESS_EXITED

        wf = _wf(nodes=[("A", "proc")])
        scheduler, event_bus, _runner = _make_scheduler(wf)

        # Should not raise
        asyncio.run(
            event_bus.emit(
                EngineEvent(
                    event_type=PROCESS_EXITED,
                    block_id="NONEXISTENT",
                    data={"exit_info": {"exit_code": 1}},
                )
            )
        )

        assert scheduler._block_states["A"] == BlockState.IDLE

    def test_error_detail_includes_signal(self) -> None:
        """Error detail should mention the signal number when available."""
        from scistudio.engine.events import PROCESS_EXITED

        wf = _wf(nodes=[("A", "proc")])
        scheduler, event_bus, _runner = _make_scheduler(wf)

        error_events: list[EngineEvent] = []
        event_bus.subscribe(BLOCK_ERROR, lambda e: error_events.append(e))

        scheduler._block_states["A"] = BlockState.RUNNING

        asyncio.run(
            event_bus.emit(
                EngineEvent(
                    event_type=PROCESS_EXITED,
                    block_id="A",
                    data={"exit_info": {"exit_code": -9, "signal_number": 9}},
                )
            )
        )

        assert len(error_events) >= 1
        error_data = error_events[0].data
        assert "signal 9" in error_data.get("error", "")


# ---------------------------------------------------------------------------
# Checkpoint wiring (#164)
# ---------------------------------------------------------------------------


class TestSchedulerCheckpoint:
    """Test CheckpointManager integration with DAGScheduler pause/resume."""

    def test_pause_sets_paused_flag(self) -> None:
        """pause() should set _paused flag.

        PR #160 design: pause() only sets the flag; checkpoint persistence
        happens automatically via save_checkpoint() on block completion events.
        Checkpoint restoration uses execute_from() rather than resume().
        """
        wf = _wf(nodes=[("A", "proc"), ("B", "proc")])
        scheduler, _bus, _runner = _make_scheduler(wf)

        scheduler._block_states["A"] = BlockState.DONE
        scheduler._block_outputs["A"] = {"out": "v"}

        asyncio.run(scheduler.pause())
        assert scheduler._paused is True

    def test_pause_without_checkpoint_manager(self) -> None:
        """pause() without checkpoint_manager should not raise."""
        wf = _wf(nodes=[("A", "proc")])
        scheduler, _bus, _runner = _make_scheduler(wf)

        asyncio.run(scheduler.pause())
        assert scheduler._paused is True

    def test_resume_loads_checkpoint(self, tmp_path: object) -> None:
        """resume() should restore block states from a saved checkpoint."""
        from scistudio.engine.checkpoint import CheckpointManager, WorkflowCheckpoint, save_checkpoint

        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out", "B:in")],
        )
        wf.id = "test-wf"  # type: ignore[attr-defined]

        # Pre-save a checkpoint with A=done.
        cp = WorkflowCheckpoint(
            workflow_id="test-wf",
            timestamp=__import__("datetime").datetime.now(),
            block_states={"A": "done", "B": "idle"},
            intermediate_refs={"A": {"out": "saved_value"}},
        )
        from pathlib import Path

        cp_dir = Path(str(tmp_path))
        save_checkpoint(cp, cp_dir / "checkpoint_test-wf.json")

        checkpoint_mgr = CheckpointManager(checkpoint_dir=str(tmp_path))

        scheduler = DAGScheduler(
            workflow=wf,
            event_bus=EventBus(),
            resource_manager=MagicMock(can_dispatch=MagicMock(return_value=True)),
            process_registry=MagicMock(),
            runner=AsyncMock(run=AsyncMock(return_value={"out": "new"})),
            checkpoint_manager=checkpoint_mgr,
        )
        # Scheduler starts fresh — all IDLE.
        assert scheduler._block_states["A"] == BlockState.IDLE

        asyncio.run(scheduler.resume())

        # A restored to DONE from checkpoint.
        assert scheduler._block_states["A"] == BlockState.DONE
        # A's outputs restored.
        assert "A" in scheduler._block_outputs

    def test_resume_without_checkpoint_manager(self) -> None:
        """resume() without checkpoint_manager should work normally."""
        wf = _wf(nodes=[("A", "proc")])
        scheduler, _bus, _runner = _make_scheduler(wf)

        asyncio.run(scheduler.resume())
        # A has no predecessors, so it should be dispatched.
        assert scheduler._block_states["A"] == BlockState.DONE

    def test_auto_save_on_block_done(self) -> None:
        """Checkpoint should be auto-saved when a block completes."""
        wf = _wf(nodes=[("A", "proc")])
        checkpoint_mgr = MagicMock()
        checkpoint_mgr.save = MagicMock()

        scheduler = DAGScheduler(
            workflow=wf,
            event_bus=EventBus(),
            resource_manager=MagicMock(can_dispatch=MagicMock(return_value=True)),
            process_registry=MagicMock(),
            runner=AsyncMock(run=AsyncMock(return_value={"out": "v"})),
            checkpoint_manager=checkpoint_mgr,
        )

        asyncio.run(scheduler.execute())

        # save_checkpoint calls checkpoint_manager.save() internally
        assert checkpoint_mgr.save.called

    def test_auto_save_on_block_error(self) -> None:
        """Checkpoint should be auto-saved when a block errors."""
        wf = _wf(nodes=[("A", "proc")])
        checkpoint_mgr = MagicMock()
        checkpoint_mgr.save = MagicMock()

        runner = AsyncMock()
        runner.run.side_effect = RuntimeError("fail")

        scheduler = DAGScheduler(
            workflow=wf,
            event_bus=EventBus(),
            resource_manager=MagicMock(can_dispatch=MagicMock(return_value=True)),
            process_registry=MagicMock(),
            runner=runner,
            checkpoint_manager=checkpoint_mgr,
        )

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.ERROR
        assert checkpoint_mgr.save.called


# ---------------------------------------------------------------------------
# Config pre-dispatch validation (#632)
# ---------------------------------------------------------------------------


class TestSchedulerConfigPreCheck:
    """Test that missing required config fields are caught before dispatch."""

    def test_missing_required_config_field_errors_before_dispatch(self) -> None:
        """Block with required config field missing should ERROR without calling runner."""
        wf = _wf(nodes=[("A", "myblock")])
        wf.nodes[0].config = {"params": {}}  # missing 'path' which is required

        # Mock registry that returns a block with a config_schema requiring 'path'
        mock_block = MagicMock()
        mock_block.config_schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

        mock_registry = MagicMock()
        mock_registry.instantiate.return_value = mock_block

        event_bus = EventBus()
        runner = AsyncMock()

        scheduler = DAGScheduler(
            workflow=wf,
            event_bus=event_bus,
            resource_manager=MagicMock(can_dispatch=MagicMock(return_value=True)),
            process_registry=MagicMock(),
            runner=runner,
            registry=mock_registry,
        )

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.ERROR
        runner.run.assert_not_called()

    def test_none_valued_required_config_field_errors(self) -> None:
        """Required config field set to None should ERROR before dispatch."""
        wf = _wf(nodes=[("A", "myblock")])
        wf.nodes[0].config = {"params": {"path": None}}

        mock_block = MagicMock()
        mock_block.config_schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

        mock_registry = MagicMock()
        mock_registry.instantiate.return_value = mock_block

        runner = AsyncMock()

        scheduler = DAGScheduler(
            workflow=wf,
            event_bus=EventBus(),
            resource_manager=MagicMock(can_dispatch=MagicMock(return_value=True)),
            process_registry=MagicMock(),
            runner=runner,
            registry=mock_registry,
        )

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.ERROR
        runner.run.assert_not_called()

    def test_all_required_config_fields_present_dispatches(self) -> None:
        """Block with all required config fields present should dispatch normally."""
        wf = _wf(nodes=[("A", "myblock")])
        wf.nodes[0].config = {"params": {"path": "/data/input.csv"}}

        mock_block = MagicMock()
        mock_block.config_schema = {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

        mock_registry = MagicMock()
        mock_registry.instantiate.return_value = mock_block

        runner = AsyncMock()
        runner.run.return_value = {"output": "ok"}

        scheduler = DAGScheduler(
            workflow=wf,
            event_bus=EventBus(),
            resource_manager=MagicMock(can_dispatch=MagicMock(return_value=True)),
            process_registry=MagicMock(),
            runner=runner,
            registry=mock_registry,
        )

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.DONE
        runner.run.assert_called_once()

    def test_no_required_fields_dispatches_normally(self) -> None:
        """Block with no required fields in config_schema dispatches normally."""
        wf = _wf(nodes=[("A", "myblock")])
        wf.nodes[0].config = {}

        mock_block = MagicMock()
        mock_block.config_schema = {
            "type": "object",
            "properties": {"optional_param": {"type": "string"}},
        }

        mock_registry = MagicMock()
        mock_registry.instantiate.return_value = mock_block

        runner = AsyncMock()
        runner.run.return_value = {"output": "ok"}

        scheduler = DAGScheduler(
            workflow=wf,
            event_bus=EventBus(),
            resource_manager=MagicMock(can_dispatch=MagicMock(return_value=True)),
            process_registry=MagicMock(),
            runner=runner,
            registry=mock_registry,
        )

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.DONE
        runner.run.assert_called_once()
