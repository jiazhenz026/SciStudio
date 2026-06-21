"""Concurrency tests for DAGScheduler (T-001, ADR-018 Addendum 1).

These tests cover the six scenarios required by the T-001 ticket:

1. Independent DAG branches run concurrently (wall clock ≈ max, not sum).
2. ResourceManager throttling retries dispatch when a slot frees.
3. Shutdown cleanup on exception terminates subprocesses and drains tasks.
4. Block cancel before subprocess starts takes the ``task.cancel()`` path.
5. Block cancel during subprocess run takes the ``ProcessHandle.terminate()``
   path.
6. Workflow cancel with a mix of running and ready/idle blocks transitions
   each block through the correct terminal state.

All tests use mock runners and a mock ProcessRegistry; no real subprocesses
are spawned.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.engine.events import (
    BLOCK_DONE,
    BLOCK_RUNNING,
    CANCEL_BLOCK_REQUEST,
    CANCEL_WORKFLOW_REQUEST,
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
    runner: Any,
    resource_manager: Any | None = None,
    process_registry: Any | None = None,
) -> tuple[DAGScheduler, EventBus]:
    """Build a DAGScheduler wired to ``runner`` with mockable supporting parts."""
    event_bus = EventBus()
    if resource_manager is None:
        resource_manager = MagicMock()
        resource_manager.can_dispatch.return_value = True
    if process_registry is None:
        process_registry = MagicMock()
        process_registry.get_handle.return_value = None
    scheduler = DAGScheduler(
        workflow=workflow,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
    )
    return scheduler, event_bus


# ---------------------------------------------------------------------------
# 1. Independent branches run concurrently
# ---------------------------------------------------------------------------


class TestIndependentBranchesConcurrency:
    """Two independent roots must run in parallel under the new scheduler."""

    def test_independent_branches_run_concurrently(self) -> None:
        """Two independent sleep(N) blocks should take ≈ N, not ≈ 2N."""
        sleep_seconds = 0.15

        async def slow_run(block: Any, inputs: dict, config: dict) -> dict:
            await asyncio.sleep(sleep_seconds)
            return {"out": f"result_{block.id}"}

        wf = _wf(nodes=[("A", "proc"), ("B", "proc")])  # no edges → independent

        runner = AsyncMock()
        runner.run.side_effect = slow_run

        scheduler, _event_bus = _make_scheduler(wf, runner)

        start = time.perf_counter()
        asyncio.run(scheduler.execute())
        elapsed = time.perf_counter() - start

        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_states["B"] == BlockState.DONE
        # Concurrent execution should finish well below 2x sleep.
        # Use a loose upper bound to tolerate scheduler overhead on CI.
        assert elapsed < sleep_seconds * 1.8, (
            f"Independent branches appear serialised: elapsed={elapsed:.3f}s "
            f"(expected approx {sleep_seconds:.3f}s, hard limit "
            f"{sleep_seconds * 1.8:.3f}s)"
        )


# ---------------------------------------------------------------------------
# 2. Resource throttling retries dispatch
# ---------------------------------------------------------------------------


class TestResourceThrottlingRetry:
    """READY blocks blocked by can_dispatch must be retried on the next event."""

    def test_resource_throttling_retries_dispatch(self) -> None:
        """With a 1-slot GPU pool and two GPU blocks, the second starts only
        after the first completes.

        We simulate ``ResourceManager.can_dispatch`` with a stateful mock:
        it returns True only when ``slot_in_use`` is False. The runner
        sets the slot busy on entry and clears it on exit, modelling the
        ResourceManager acquire/release that happens during a real
        subprocess run. Because the scheduler calls
        ``_dispatch_newly_ready`` after every BLOCK_DONE, the second
        block is retried and enters RUNNING only once the first has
        finished.
        """
        state = {"slot_in_use": False}
        running_events: list[str] = []
        finish_order: list[str] = []

        def can_dispatch(_request: Any, active_count: int = 0) -> bool:
            return not state["slot_in_use"]

        async def gated_run(block: Any, inputs: dict, config: dict) -> dict:
            # Simulate ResourceManager.acquire by marking the slot busy
            # on entry; release it on exit.
            state["slot_in_use"] = True
            await asyncio.sleep(0.05)
            state["slot_in_use"] = False
            finish_order.append(block.id)
            return {"out": block.id}

        wf = _wf(nodes=[("A", "proc"), ("B", "proc")])  # independent

        resource_manager = MagicMock()
        resource_manager.can_dispatch.side_effect = can_dispatch

        runner = AsyncMock()
        runner.run.side_effect = gated_run

        scheduler, event_bus = _make_scheduler(wf, runner, resource_manager=resource_manager)

        # Record which block enters RUNNING first.
        event_bus.subscribe(
            BLOCK_RUNNING,
            lambda e: running_events.append(e.block_id) if e.block_id else None,
        )

        asyncio.run(scheduler.execute())

        assert scheduler._block_states["A"] == BlockState.DONE
        assert scheduler._block_states["B"] == BlockState.DONE
        # Exactly one block entered RUNNING first; the second followed
        # after the first finished.
        assert len(running_events) == 2, running_events
        # Whichever block was dispatched first must have finished before
        # the other entered RUNNING — the only way that can happen is if
        # the second dispatch waited for the first to release the slot.
        first, second = running_events
        assert finish_order[0] == first
        assert finish_order.index(first) < finish_order.index(second)


# ---------------------------------------------------------------------------
# 3. Shutdown cleanup on exception
# ---------------------------------------------------------------------------


class TestShutdownCleanupOnException:
    """If execute() body raises, active tasks and subprocesses are cleaned up."""

    def test_scheduler_shutdown_cleanup_on_exception(self) -> None:
        """An exception inside a block task triggers the finally path.

        The test forces a RuntimeError in the only block. After execute()
        returns, ``_active_tasks`` must be empty and the mock
        ProcessRegistry's ``terminate_all``/``terminate`` call path must
        have been exercised for any handle still registered.
        """
        wf = _wf(nodes=[("A", "proc"), ("B", "proc")])  # independent

        terminated: list[str] = []

        handle_a = MagicMock()
        handle_a.terminate.side_effect = lambda *a, **k: terminated.append("A")
        handle_b = MagicMock()
        handle_b.terminate.side_effect = lambda *a, **k: terminated.append("B")

        # Registered handle for A and B while the tasks are "running".
        process_registry = MagicMock()
        process_registry.get_handle.side_effect = lambda workflow_id, block_id: {"A": handle_a, "B": handle_b}.get(
            block_id
        )

        started = asyncio.Event()
        unblock = asyncio.Event()

        async def runner_side_effect(block: Any, inputs: dict, config: dict) -> dict:
            # Signal that at least one block is running, then raise.
            if block.id == "A":
                started.set()
                raise RuntimeError("boom from A")
            # B waits until externally unblocked; if cleanup works, it
            # will be cancelled via terminate path before that happens.
            await unblock.wait()
            return {"out": "B"}

        runner = AsyncMock()
        runner.run.side_effect = runner_side_effect

        scheduler, _event_bus = _make_scheduler(wf, runner, process_registry=process_registry)

        async def drive() -> None:
            exec_task = asyncio.create_task(scheduler.execute())
            await started.wait()
            # Inject an exception into the scheduler's completion event
            # handling by cancelling the execute coroutine, which
            # triggers the try/finally shutdown path.
            exec_task.cancel()
            with pytest.raises((asyncio.CancelledError, RuntimeError)):
                await exec_task

        asyncio.run(drive())

        # After execute() unwinds, no tasks may remain.
        assert scheduler._active_tasks == {}
        # At least one terminate call was issued during shutdown (for
        # whichever block was still tracked in the registry when the
        # cancellation occurred).
        assert terminated, (
            "Expected _cancel_active_tasks_on_shutdown to terminate at least one active subprocess handle; got none."
        )


# ---------------------------------------------------------------------------
# 4. Cancel block before subprocess starts — task.cancel() path
# ---------------------------------------------------------------------------


class TestCancelBeforeSubprocessStarts:
    """Cancel during pre-subprocess setup must take the task.cancel() branch."""

    def test_cancel_block_before_subprocess_starts(self) -> None:
        """With no ProcessHandle registered yet, _on_cancel_block uses
        ``task.cancel()`` on the active task.
        """
        wf = _wf(nodes=[("A", "proc")])

        # No handle ever registered — simulates the pre-subprocess window.
        process_registry = MagicMock()
        process_registry.get_handle.return_value = None

        hit_runner = asyncio.Event()
        cancelled_in_runner = asyncio.Event()

        async def slow_run(block: Any, inputs: dict, config: dict) -> dict:
            hit_runner.set()
            try:
                await asyncio.sleep(10.0)  # long sleep, should be cancelled
            except asyncio.CancelledError:
                cancelled_in_runner.set()
                raise
            return {"out": "never"}

        runner = AsyncMock()
        runner.run.side_effect = slow_run

        scheduler, event_bus = _make_scheduler(wf, runner, process_registry=process_registry)

        async def drive() -> None:
            exec_task = asyncio.create_task(scheduler.execute())
            await hit_runner.wait()
            # Verify a task is registered for A.
            assert "A" in scheduler._active_tasks
            await event_bus.emit(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="A"))
            # After cancel, wait for execute() to finish naturally.
            await exec_task

        asyncio.run(drive())

        assert scheduler._block_states["A"] == BlockState.CANCELLED
        assert cancelled_in_runner.is_set(), "Runner did not observe CancelledError — expected task.cancel() path."
        # No handle was ever fetched via terminate because the path was
        # task-cancel, not process-terminate.
        assert process_registry.get_handle.called
        assert scheduler._active_tasks == {}


# ---------------------------------------------------------------------------
# 5. Cancel block during subprocess run — ProcessHandle.terminate() path
# ---------------------------------------------------------------------------


class TestCancelDuringSubprocessRun:
    """Cancel while a subprocess is active must call ``handle.terminate()``."""

    def test_cancel_block_during_subprocess_run(self) -> None:
        """With a ProcessHandle registered, _on_cancel_block calls
        ``handle.terminate()`` instead of ``task.cancel()``.
        """
        wf = _wf(nodes=[("A", "proc")])

        terminated: list[str] = []
        terminate_called = asyncio.Event()
        handle = MagicMock()

        def _on_terminate(*_args: Any, **_kwargs: Any) -> None:
            terminated.append("A")
            terminate_called.set()

        handle.terminate.side_effect = _on_terminate

        process_registry = MagicMock()
        process_registry.get_handle.return_value = handle

        hit_runner = asyncio.Event()

        async def runner_impl(block: Any, inputs: dict, config: dict) -> dict:
            hit_runner.set()
            # Simulate a subprocess that gets terminated externally:
            # wait until handle.terminate() fires, then raise the same
            # kind of error LocalRunner raises when popen exits non-zero.
            await terminate_called.wait()
            raise RuntimeError("terminated by framework")

        runner = AsyncMock()
        runner.run.side_effect = runner_impl

        scheduler, event_bus = _make_scheduler(wf, runner, process_registry=process_registry)

        async def drive() -> None:
            exec_task = asyncio.create_task(scheduler.execute())
            await hit_runner.wait()
            await event_bus.emit(EngineEvent(event_type=CANCEL_BLOCK_REQUEST, block_id="A"))
            await exec_task

        asyncio.run(drive())

        assert scheduler._block_states["A"] == BlockState.CANCELLED
        assert terminated == ["A"], f"Expected ProcessHandle.terminate() to be called; got {terminated}"


# ---------------------------------------------------------------------------
# 6. Cancel workflow with a mix of running and ready blocks
# ---------------------------------------------------------------------------


class TestCancelWorkflowMixed:
    """Workflow cancel while some blocks are running and others idle/ready."""

    def test_cancel_workflow_with_mix_of_running_and_ready_blocks(self) -> None:
        """A → B, A → C. When A is running and B/C are still IDLE, a
        workflow-level cancel must:

        * terminate / cancel the in-flight A task,
        * mark A as CANCELLED,
        * mark B and C as SKIPPED with reason "workflow cancelled".
        """
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("A:out", "C:in")],
        )

        # Register a handle for A so the terminate path is taken. When
        # terminate() is called, flip a flag that A's runner polls to
        # simulate the real-world LocalRunner.popen.communicate()
        # unblocking with a non-zero exit code.
        terminate_called = asyncio.Event()
        handle_a = MagicMock()

        def _on_terminate(*_args: Any, **_kwargs: Any) -> None:
            # asyncio.Event.set is thread-safe and does not need a loop.
            terminate_called.set()

        handle_a.terminate.side_effect = _on_terminate

        process_registry = MagicMock()
        process_registry.get_handle.side_effect = lambda block_id: handle_a if block_id == "A" else None

        hit_runner = asyncio.Event()

        async def runner_impl(block: Any, inputs: dict, config: dict) -> dict:
            if block.id == "A":
                hit_runner.set()
                # Wait until the test-level workflow cancel calls
                # handle.terminate, then raise the same kind of error
                # LocalRunner would raise if popen exits non-zero.
                await terminate_called.wait()
                raise RuntimeError("terminated by framework")
            return {"out": block.id}

        runner = AsyncMock()
        runner.run.side_effect = runner_impl

        scheduler, event_bus = _make_scheduler(wf, runner, process_registry=process_registry)

        async def drive() -> None:
            exec_task = asyncio.create_task(scheduler.execute())
            await hit_runner.wait()
            # At this moment A is RUNNING; B and C are still IDLE
            # (they depend on A).
            assert scheduler._block_states["A"] == BlockState.RUNNING
            assert scheduler._block_states["B"] == BlockState.IDLE
            assert scheduler._block_states["C"] == BlockState.IDLE
            await event_bus.emit(
                EngineEvent(
                    event_type=CANCEL_WORKFLOW_REQUEST,
                    data={"workflow_id": scheduler._workflow.id},
                )
            )
            await exec_task

        asyncio.run(drive())

        assert scheduler._block_states["A"] == BlockState.CANCELLED
        assert scheduler._block_states["B"] == BlockState.SKIPPED
        assert scheduler._block_states["C"] == BlockState.SKIPPED
        assert "workflow cancelled" in scheduler.skip_reasons.get("B", "")
        assert "workflow cancelled" in scheduler.skip_reasons.get("C", "")
        handle_a.terminate.assert_called_once()
        assert scheduler._active_tasks == {}


# ---------------------------------------------------------------------------
# Run-identity isolation (#1517 / #1596): two runs share one EventBus
# ---------------------------------------------------------------------------


class TestRunIdentityIsolation:
    """Events on the shared process-global EventBus must not cross-react."""

    def _scheduler_on_bus(self, workflow: WorkflowDefinition, bus: EventBus) -> DAGScheduler:
        rm = MagicMock()
        rm.can_dispatch.return_value = True
        reg = MagicMock()
        reg.get_handle.return_value = None
        return DAGScheduler(
            workflow=workflow,
            event_bus=bus,
            resource_manager=rm,
            process_registry=reg,
            runner=AsyncMock(),
        )

    def test_cancel_workflow_isolated_across_runs(self) -> None:
        """#1517/#1596: cancelling run A must not cancel run B's running block."""
        bus = EventBus()
        # Same node id "load" on purpose — only workflow_id distinguishes them.
        wf_a = WorkflowDefinition(id="wf-A", nodes=[NodeDef(id="load", block_type="proc")])
        wf_b = WorkflowDefinition(id="wf-B", nodes=[NodeDef(id="load", block_type="proc")])
        sched_a = self._scheduler_on_bus(wf_a, bus)
        sched_b = self._scheduler_on_bus(wf_b, bus)
        sched_a._block_states["load"] = BlockState.RUNNING
        sched_b._block_states["load"] = BlockState.RUNNING

        asyncio.run(bus.emit(EngineEvent(event_type=CANCEL_WORKFLOW_REQUEST, data={"workflow_id": "wf-A"})))

        assert sched_a._block_states["load"] == BlockState.CANCELLED
        assert sched_b._block_states["load"] == BlockState.RUNNING

    def test_block_done_isolated_across_runs(self) -> None:
        """#1517: run B's BLOCK_DONE must not drive run A's scheduler."""
        bus = EventBus()
        wf_a = WorkflowDefinition(
            id="wf-A",
            nodes=[NodeDef(id="x", block_type="proc"), NodeDef(id="y", block_type="proc")],
            edges=[EdgeDef(source="x:out", target="y:in")],
        )
        wf_b = WorkflowDefinition(id="wf-B", nodes=[NodeDef(id="x", block_type="proc")])
        sched_a = self._scheduler_on_bus(wf_a, bus)
        self._scheduler_on_bus(wf_b, bus)
        sched_a._dispatch_newly_ready = AsyncMock()

        asyncio.run(bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="x", data={"workflow_id": "wf-B"})))

        sched_a._dispatch_newly_ready.assert_not_called()

    def test_dispose_unsubscribes(self) -> None:
        """#1517: a disposed scheduler stops receiving events; dispose is idempotent."""
        bus = EventBus()
        wf = WorkflowDefinition(id="wf-A", nodes=[NodeDef(id="a", block_type="proc")])
        sched = self._scheduler_on_bus(wf, bus)
        assert sched._on_block_done in bus._subscribers[BLOCK_DONE]
        sched.dispose()
        assert sched._on_block_done not in bus._subscribers[BLOCK_DONE]
        assert sched._on_cancel_workflow not in bus._subscribers[CANCEL_WORKFLOW_REQUEST]
        sched.dispose()  # idempotent — must not raise
