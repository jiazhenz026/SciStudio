"""ADR-051 adversarial timing / ordering / cancellation / concurrency matrix.

NO-IMPLEMENTATION-CONTEXT design driven purely by the ADR-051 contract. This is
the highest-priority surface (response/event timing & ordering, cancellation at
every phase, concurrency run-scoping) where same-author tests are weakest, so the
cells here DELIBERATELY exercise inconvenient orderings: a synchronous response
from inside the prompt handler, a duplicate response, a response for a different
block/run, a cancel racing a response, a response that never comes, and a confirm
that must resolve only its own run.

These cells use a *controllable in-memory runner* (not real subprocesses) so the
relative timing of the prompt phase, the pause, the response, the compute phase,
and the cancel can be pinned exactly. The real-subprocess guarantees live in
``test_interactive_adversarial_e2e.py``. Every wait is bounded by
``asyncio.wait_for`` so a contract violation that would hang fails fast.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.blocks.registry import BlockRegistry
from scistudio.blocks.registry._spec import _spec_from_class
from scistudio.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_PAUSED,
    BLOCK_RUNNING,
    INTERACTIVE_COMPLETE,
    INTERACTIVE_PROMPT,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import NodeDef, WorkflowDefinition
from tests.fixtures.interactive_blocks import SelectOptionBlock

TIMING_TIMEOUT = 20
SETTLE = 0.25  # window to prove a block STAYS paused (no spurious resolution)


class _AllowAll:
    def can_dispatch(self, *_args: object, **_kwargs: object) -> bool:
        return True


class _StubProcessRegistry:
    """No real subprocess handles — cancellation goes through the task path."""

    def get_handle(self, *_args: object, **_kwargs: object) -> None:
        return None

    def register(self, *_args: object, **_kwargs: object) -> None:
        return None

    def deregister(self, *_args: object, **_kwargs: object) -> None:
        return None


class ControllableRunner:
    """In-memory runner whose two phases can be gated and observed precisely."""

    def __init__(self) -> None:
        self.prompt_started = asyncio.Event()
        self.compute_started = asyncio.Event()
        self.prompt_release = asyncio.Event()
        self.compute_release = asyncio.Event()
        # Default: both phases run to completion immediately.
        self.prompt_release.set()
        self.compute_release.set()
        self.prompt_result: dict[str, Any] = {"panel_payload": {"ok": True}, "intermediate": []}
        self.compute_result: dict[str, Any] = {"selected": "computed"}
        self.prompt_calls = 0
        self.compute_calls = 0
        self.cancel_calls: list[tuple[str, str]] = []

    async def run_prompt(self, block: Any, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.prompt_calls += 1
        self.prompt_started.set()
        await self.prompt_release.wait()
        return dict(self.prompt_result)

    async def run(self, block: Any, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.compute_calls += 1
        self.compute_started.set()
        await self.compute_release.wait()
        return dict(self.compute_result)

    async def cancel(self, workflow_id: str, block_id: str) -> None:
        self.cancel_calls.append((workflow_id, block_id))


class _Recorder:
    def __init__(self, bus: EventBus) -> None:
        self.events: list[tuple[str, str | None]] = []
        for etype in (BLOCK_PAUSED, BLOCK_RUNNING, BLOCK_DONE, BLOCK_ERROR, BLOCK_CANCELLED):
            bus.subscribe(etype, self._make(etype))

    def _make(self, etype: str) -> Any:
        async def _cb(event: EngineEvent) -> None:
            self.events.append((etype, event.block_id))

        return _cb

    def count(self, etype: str, block_id: str) -> int:
        return sum(1 for et, bid in self.events if et == etype and bid == block_id)


def _build(
    *,
    workflow_id: str = "wf-1",
    node_config: dict[str, Any] | None = None,
    runner: ControllableRunner | None = None,
    registry: BlockRegistry | None = None,
) -> tuple[DAGScheduler, EventBus, ControllableRunner, WorkflowDefinition, _Recorder]:
    if registry is None:
        registry = BlockRegistry()
        registry._register_spec(_spec_from_class(SelectOptionBlock, source="builtin"))
    bus = EventBus()
    runner = runner or ControllableRunner()
    recorder = _Recorder(bus)
    wf = WorkflowDefinition(
        id=workflow_id,
        nodes=[NodeDef(id="X", block_type=_spec_from_class(SelectOptionBlock).name, config=node_config or {})],
        edges=[],
    )
    scheduler = DAGScheduler(
        workflow=wf,
        event_bus=bus,
        resource_manager=_AllowAll(),
        process_registry=_StubProcessRegistry(),
        runner=runner,
        registry=registry,
    )
    return scheduler, bus, runner, wf, recorder


async def _wait_state(sched: DAGScheduler, node: str, state: BlockState, timeout: float = 5.0) -> None:
    async def _loop() -> None:
        while sched._block_states.get(node) != state:
            await asyncio.sleep(0.005)

    await asyncio.wait_for(_loop(), timeout)


async def _wait_event(event: asyncio.Event, timeout: float = 5.0) -> None:
    await asyncio.wait_for(event.wait(), timeout)


def _complete(bus: EventBus, block_id: str, response: dict[str, Any], *, workflow_id: str | None = "wf-1") -> Any:
    data: dict[str, Any] = {"response": response}
    if workflow_id is not None:
        data["workflow_id"] = workflow_id
    return bus.emit(EngineEvent(event_type=INTERACTIVE_COMPLETE, block_id=block_id, data=data))


# ===========================================================================
# A. Response / event timing & ordering (highest priority).
# ===========================================================================


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_response_delivered_synchronously_from_prompt_handler() -> None:
    """A: a response emitted SYNCHRONOUSLY from inside the prompt handler resolves.

    The runtime registers the rendezvous future BEFORE announcing the prompt, so a
    response delivered during the INTERACTIVE_PROMPT dispatch (a fast client / an
    in-process subscriber) must find a pending future and drive the compute phase
    exactly once — not be dropped, leaving the block hung in PAUSED.
    """

    async def _run() -> None:
        sched, bus, runner, wf, _rec = _build()

        async def _sync_confirm(event: EngineEvent) -> None:
            await _complete(bus, event.block_id or "", {"choice": "B"}, workflow_id=wf.id)

        bus.subscribe(INTERACTIVE_PROMPT, _sync_confirm)
        await asyncio.wait_for(sched.execute(), timeout=10)
        assert sched._block_states["X"] == BlockState.DONE
        assert runner.compute_calls == 1
        assert sched._block_outputs["X"] == {"selected": "computed"}
        sched.dispose()

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_duplicate_response_is_harmless_no_op() -> None:
    """A: a duplicate response must be a harmless no-op, not a double compute."""

    async def _run() -> None:
        sched, bus, runner, wf, _rec = _build()

        async def _double_confirm(event: EngineEvent) -> None:
            await _complete(bus, event.block_id or "", {"choice": "B"}, workflow_id=wf.id)
            await _complete(bus, event.block_id or "", {"choice": "SECOND"}, workflow_id=wf.id)

        bus.subscribe(INTERACTIVE_PROMPT, _double_confirm)
        await asyncio.wait_for(sched.execute(), timeout=10)
        assert sched._block_states["X"] == BlockState.DONE
        assert runner.compute_calls == 1, "duplicate response triggered a second compute"

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_response_arriving_during_prompt_phase_is_delivered_not_dropped() -> None:
    """A (boundary): a response that arrives DURING the prompt phase is delivered.

    The rendezvous future is registered BEFORE the prompt phase even starts, so a
    response that races in WHILE the prompt phase is still running finds a pending
    future and resolves it — it is NOT dropped. When the prompt phase returns, the
    decision is already in: the block skips the (now pointless) pause and computes
    exactly once. A single response is sufficient; the block never hangs. (Fixes
    the adversarial OBS-1 boundary by making a dropped pre-registration response
    structurally impossible.)
    """

    async def _run() -> None:
        runner = ControllableRunner()
        runner.prompt_release.clear()  # hold the prompt phase open
        sched, bus, _runner, wf, rec = _build(runner=runner)
        task = asyncio.create_task(sched.execute())
        await _wait_event(runner.prompt_started)

        # Race a response in WHILE the prompt phase is still running. The future
        # is already registered (before the prompt phase), so this resolves it.
        await _complete(bus, "X", {"choice": "EARLY"}, workflow_id=wf.id)

        # Let the prompt phase finish; the already-resolved decision drives compute.
        runner.prompt_release.set()
        await asyncio.wait_for(task, timeout=5)

        assert sched._block_states["X"] == BlockState.DONE, (
            "early-arriving response was dropped (block did not complete)"
        )
        assert runner.compute_calls == 1, "early response did not drive exactly one compute"
        assert sched._block_outputs["X"] == {"selected": "computed"}
        # A single response sufficed — the block never paused waiting for a second.
        assert rec.count(BLOCK_PAUSED, "X") == 0
        sched.dispose()

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_response_for_different_block_id_does_not_resolve() -> None:
    """A: a response for a DIFFERENT block_id must not resolve this run."""

    async def _run() -> None:
        sched, bus, runner, wf, _rec = _build()
        task = asyncio.create_task(sched.execute())
        await _wait_state(sched, "X", BlockState.PAUSED)

        await _complete(bus, "SOME_OTHER_BLOCK", {"choice": "B"}, workflow_id=wf.id)
        await asyncio.sleep(SETTLE)
        assert sched._block_states["X"] == BlockState.PAUSED, "foreign block_id resolved this run"
        assert runner.compute_calls == 0

        # Cleanly cancelable afterwards (no hang).
        await sched.cancel_block("X")
        await asyncio.wait_for(task, timeout=5)
        assert sched._block_states["X"] == BlockState.CANCELLED
        sched.dispose()

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_response_for_different_workflow_id_does_not_resolve() -> None:
    """A: a response carrying a DIFFERENT workflow_id must not resolve (run-scoping)."""

    async def _run() -> None:
        sched, bus, runner, _wf, _rec = _build(workflow_id="wf-1")
        task = asyncio.create_task(sched.execute())
        await _wait_state(sched, "X", BlockState.PAUSED)

        await _complete(bus, "X", {"choice": "B"}, workflow_id="wf-OTHER")
        await asyncio.sleep(SETTLE)
        assert sched._block_states["X"] == BlockState.PAUSED, "cross-run workflow_id resolved this run"
        assert runner.compute_calls == 0

        # The correctly-scoped response still resolves it.
        await _complete(bus, "X", {"choice": "B"}, workflow_id="wf-1")
        await asyncio.wait_for(task, timeout=5)
        assert sched._block_states["X"] == BlockState.DONE
        assert runner.compute_calls == 1
        sched.dispose()

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_response_that_never_comes_stays_paused_and_is_cancelable() -> None:
    """A / §2: an unanswered interaction stays PAUSED with nothing resident and is cancelable."""

    async def _run() -> None:
        sched, _bus, runner, _wf, _rec = _build()
        task = asyncio.create_task(sched.execute())
        await _wait_state(sched, "X", BlockState.PAUSED)

        await asyncio.sleep(SETTLE)
        assert sched._block_states["X"] == BlockState.PAUSED
        assert runner.compute_calls == 0, "compute ran without a response"
        # execute() must still be waiting — no timeout fires on its own.
        assert not task.done()

        await sched.cancel_block("X")
        await asyncio.wait_for(task, timeout=5)
        assert sched._block_states["X"] == BlockState.CANCELLED
        assert runner.compute_calls == 0
        sched.dispose()

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_cancel_then_late_response_cancel_wins() -> None:
    """A: cancel then a late response — cancel wins, late response is a no-op."""

    async def _run() -> None:
        sched, bus, runner, wf, _rec = _build()
        task = asyncio.create_task(sched.execute())
        await _wait_state(sched, "X", BlockState.PAUSED)

        await sched.cancel_block("X")
        await asyncio.wait_for(task, timeout=5)
        assert sched._block_states["X"] == BlockState.CANCELLED

        # A late response after cancellation must not revive / compute the block.
        await _complete(bus, "X", {"choice": "B"}, workflow_id=wf.id)
        await asyncio.sleep(SETTLE)
        assert sched._block_states["X"] == BlockState.CANCELLED
        assert runner.compute_calls == 0
        sched.dispose()

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_response_then_cancel_during_compute() -> None:
    """A / C: response resolves, then a cancel hits the in-flight compute phase."""

    async def _run() -> None:
        runner = ControllableRunner()
        runner.compute_release.clear()  # hold the compute phase open
        sched, bus, _runner, wf, _rec = _build(runner=runner)
        task = asyncio.create_task(sched.execute())
        await _wait_state(sched, "X", BlockState.PAUSED)

        await _complete(bus, "X", {"choice": "B"}, workflow_id=wf.id)
        # The block transitions to RUNNING and enters compute, which blocks.
        await _wait_event(runner.compute_started)
        await _wait_state(sched, "X", BlockState.RUNNING)

        await sched.cancel_block("X")
        await asyncio.wait_for(task, timeout=5)
        assert sched._block_states["X"] == BlockState.CANCELLED
        assert "X" not in sched._block_outputs, "cancelled compute must not store outputs"
        sched.dispose()

    asyncio.run(_run())


# ===========================================================================
# C. Cancellation at EVERY phase.
# ===========================================================================


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_cancel_during_prompt_phase_before_pause() -> None:
    """C: cancel while the prompt phase is still running — no pause, no compute."""

    async def _run() -> None:
        runner = ControllableRunner()
        runner.prompt_release.clear()  # hold the prompt phase open
        sched, _bus, _runner, _wf, rec = _build(runner=runner)
        task = asyncio.create_task(sched.execute())
        await _wait_event(runner.prompt_started)
        await _wait_state(sched, "X", BlockState.RUNNING)

        await sched.cancel_block("X")
        await asyncio.wait_for(task, timeout=5)
        assert sched._block_states["X"] == BlockState.CANCELLED
        assert rec.count(BLOCK_PAUSED, "X") == 0, "block paused despite cancel during prompt phase"
        assert runner.compute_calls == 0
        sched.dispose()

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_cancel_while_paused_releases_scratch(tmp_path: Path) -> None:
    """C / FR-012: cancel while paused releases intermediate scratch and spawns no compute."""

    async def _run() -> None:
        scratch = tmp_path / "held_scratch.bin"
        scratch.write_text("HELD", encoding="utf-8")
        runner = ControllableRunner()
        runner.prompt_result = {
            "panel_payload": {"ok": True},
            "intermediate": [{"backend": "file", "path": str(scratch).replace("\\", "/")}],
        }
        sched, _bus, _runner, _wf, _rec = _build(runner=runner)
        task = asyncio.create_task(sched.execute())
        await _wait_state(sched, "X", BlockState.PAUSED)
        assert scratch.exists(), "scratch should be held while paused"

        await sched.cancel_block("X")
        await asyncio.wait_for(task, timeout=5)
        assert sched._block_states["X"] == BlockState.CANCELLED
        assert runner.compute_calls == 0, "FR-012: a compute phase was spawned on cancel"
        assert not scratch.exists(), "FR-012: intermediate scratch not released on cancel"
        sched.dispose()

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_workflow_level_cancel_while_paused() -> None:
    """C: workflow-level cancel while a block is paused tears the interaction down."""

    async def _run() -> None:
        sched, _bus, runner, _wf, _rec = _build()
        task = asyncio.create_task(sched.execute())
        await _wait_state(sched, "X", BlockState.PAUSED)

        await sched.cancel_workflow()
        await asyncio.wait_for(task, timeout=5)
        assert sched._block_states["X"] == BlockState.CANCELLED
        assert runner.compute_calls == 0
        sched.dispose()

    asyncio.run(_run())


# ===========================================================================
# B. Response JSON edge values — engine-side rejection (FR-004).
# ===========================================================================


@pytest.mark.timeout(TIMING_TIMEOUT)
@pytest.mark.parametrize("mode", ["nan", "inf", "neg_inf", "non_serialisable"])
def test_non_json_safe_response_rejected(mode: str) -> None:
    """FR-004: a non-JSON-safe interactive_response fails the block; no compute runs."""

    bad_value: Any = {
        "nan": float("nan"),
        "inf": float("inf"),
        "neg_inf": float("-inf"),
        "non_serialisable": {1, 2, 3},
    }[mode]

    async def _run() -> None:
        sched, bus, runner, wf, _rec = _build()

        async def _bad_confirm(event: EngineEvent) -> None:
            await _complete(bus, event.block_id or "", {"value": bad_value}, workflow_id=wf.id)

        bus.subscribe(INTERACTIVE_PROMPT, _bad_confirm)
        await asyncio.wait_for(sched.execute(), timeout=10)
        assert sched._block_states["X"] == BlockState.ERROR, "non-JSON response was accepted"
        assert runner.compute_calls == 0, "compute ran with a non-JSON response"
        sched.dispose()

    asyncio.run(_run())


# ===========================================================================
# D. Concurrency — two runs sharing the SAME node id; run-scoping.
# ===========================================================================


def _build_pair() -> tuple[
    DAGScheduler, DAGScheduler, EventBus, ControllableRunner, ControllableRunner, WorkflowDefinition, WorkflowDefinition
]:
    registry = BlockRegistry()
    registry._register_spec(_spec_from_class(SelectOptionBlock, source="builtin"))
    bus = EventBus()
    runner_a = ControllableRunner()
    runner_b = ControllableRunner()
    block_type = _spec_from_class(SelectOptionBlock).name
    wf_a = WorkflowDefinition(id="wf-alpha", nodes=[NodeDef(id="X", block_type=block_type)], edges=[])
    wf_b = WorkflowDefinition(id="wf-beta", nodes=[NodeDef(id="X", block_type=block_type)], edges=[])
    sched_a = DAGScheduler(
        workflow=wf_a,
        event_bus=bus,
        resource_manager=_AllowAll(),
        process_registry=_StubProcessRegistry(),
        runner=runner_a,
        registry=registry,
    )
    sched_b = DAGScheduler(
        workflow=wf_b,
        event_bus=bus,
        resource_manager=_AllowAll(),
        process_registry=_StubProcessRegistry(),
        runner=runner_b,
        registry=registry,
    )
    return sched_a, sched_b, bus, runner_a, runner_b, wf_a, wf_b


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_scoped_confirm_resolves_only_its_own_run() -> None:
    """D: two paused runs share node id 'X'; a workflow-scoped confirm resolves only one."""

    async def _run() -> None:
        sched_a, sched_b, bus, runner_a, runner_b, _wf_a, _wf_b = _build_pair()
        task_a = asyncio.create_task(sched_a.execute())
        task_b = asyncio.create_task(sched_b.execute())
        await _wait_state(sched_a, "X", BlockState.PAUSED)
        await _wait_state(sched_b, "X", BlockState.PAUSED)

        # Confirm scoped to run A only.
        await _complete(bus, "X", {"choice": "A"}, workflow_id="wf-alpha")
        await asyncio.wait_for(task_a, timeout=5)

        assert sched_a._block_states["X"] == BlockState.DONE
        assert runner_a.compute_calls == 1
        # Run B must be untouched.
        await asyncio.sleep(SETTLE)
        assert sched_b._block_states["X"] == BlockState.PAUSED, "scoped confirm cross-resolved another run"
        assert runner_b.compute_calls == 0

        await sched_b.cancel_workflow()
        await asyncio.wait_for(task_b, timeout=5)
        assert sched_b._block_states["X"] == BlockState.CANCELLED
        sched_a.dispose()
        sched_b.dispose()

    asyncio.run(_run())


@pytest.mark.timeout(TIMING_TIMEOUT)
def test_unscoped_confirm_fans_out_to_all_runs() -> None:
    """D (observation): an UNSCOPED confirm (no workflow_id) fails open and resolves BOTH runs.

    ``_event_is_for_run`` is fail-open on a missing ``workflow_id`` by design, so a
    confirm with no scope and a colliding ``block_id`` resolves every concurrent
    run that holds that block. Production (``api/ws.py``) always carries the
    workflow_id, so the scoped path above is the live behaviour; this documents
    the latent cross-resolution if scoping is ever dropped.
    """

    async def _run() -> None:
        sched_a, sched_b, bus, runner_a, runner_b, _wf_a, _wf_b = _build_pair()
        task_a = asyncio.create_task(sched_a.execute())
        task_b = asyncio.create_task(sched_b.execute())
        await _wait_state(sched_a, "X", BlockState.PAUSED)
        await _wait_state(sched_b, "X", BlockState.PAUSED)

        await _complete(bus, "X", {"choice": "Z"}, workflow_id=None)
        await asyncio.wait_for(task_a, timeout=5)
        await asyncio.wait_for(task_b, timeout=5)

        assert sched_a._block_states["X"] == BlockState.DONE
        assert sched_b._block_states["X"] == BlockState.DONE
        assert runner_a.compute_calls == 1
        assert runner_b.compute_calls == 1
        sched_a.dispose()
        sched_b.dispose()

    asyncio.run(_run())
