"""DAGScheduler — event-driven workflow execution with cancellation and skip propagation.

ADR-046 / umbrella #1427 Phase 3: the original god-file
``engine/scheduler.py`` (~1744 LOC) was split into this sub-package.
The full public surface from before the split is preserved here:

* :class:`DAGScheduler` (canonical class symbol stays at
  ``scistudio.engine.scheduler.DAGScheduler``)
* :class:`RunHandle`
* :data:`logger`
* the three module-level helpers ``_extract_error_summary``,
  ``_collect_object_ids``, ``_object_ids_for_value``

Method implementations live in concern-grouped private sibling
modules and are bound onto :class:`DAGScheduler` via class-body
static assignment — the Path D pattern established by PR #1445
(:mod:`scistudio.api.runtime`) and PR #1460
(:mod:`scistudio.blocks.io`). The split is **structural-only** with
zero behavior change; #1449 scheduler state-machine contract test
passes byte-identically.

Sub-module layout:

* :mod:`_helpers`    — three module-level helper functions re-exported here
* :mod:`_dispatch`   — block dispatch loop                 (~440 LOC)
* :mod:`_events`     — EventBus subscriber handlers        (~240 LOC)
* :mod:`_lineage`    — output + lineage persistence        (~330 LOC)
* :mod:`_state`      — state-machine helpers (ADR-046 §5)  (~75 LOC)
* :mod:`_rerun`      — rerun / reset / graph-traversal     (~165 LOC)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from scistudio.blocks.base.state import BlockState
from scistudio.engine.dag import build_dag, get_downstream_blocks, topological_sort
from scistudio.engine.events import (
    BLOCK_DONE,
    BLOCK_ERROR,
    CANCEL_BLOCK_REQUEST,
    CANCEL_WORKFLOW_REQUEST,
    INTERACTIVE_COMPLETE,
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
    EngineEvent,
    EventBus,
)
from scistudio.workflow.definition import WorkflowDefinition

from . import _dispatch as _dispatch_mod
from . import _events as _events_mod
from . import _lineage as _lineage_mod
from . import _rerun as _rerun_mod
from . import _state as _state_mod
from ._helpers import (
    _MAX_ERROR_SUMMARY_LEN,
    _collect_object_ids,
    _extract_error_summary,
    _object_ids_for_value,
)

if TYPE_CHECKING:
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core.lineage.recorder import LineageRecorder

logger = logging.getLogger(__name__)

# Re-export the module-level helpers and the truncation constant so the
# ``scistudio.engine.scheduler.<name>`` import path keeps resolving for
# audit tooling and any external caller that still imports them by name.
__all__ = [
    "_MAX_ERROR_SUMMARY_LEN",
    "DAGScheduler",
    "RunHandle",
    "_collect_object_ids",
    "_extract_error_summary",
    "_object_ids_for_value",
    "logger",
]


@dataclass
class RunHandle:
    """Handle for a single block execution in progress."""

    run_id: str = ""
    process_handle: Any = None
    result: Any = None


class DAGScheduler:
    """Execute a workflow by reacting to EventBus events.

    The scheduler builds a DAG from the workflow definition, computes
    topological order, and dispatches blocks as their predecessors complete.
    On error or cancellation, downstream blocks are marked SKIPPED.

    Parameters
    ----------
    workflow:
        The workflow to execute.
    event_bus:
        EventBus instance for publish/subscribe coordination.
    resource_manager:
        ResourceManager for dispatch gating (can_dispatch check).
    process_registry:
        ProcessRegistry for active subprocess tracking.
    runner:
        BlockRunner implementation (e.g. LocalRunner) for executing blocks.
    registry:
        Optional BlockRegistry for resolving NodeDef.block_type to Block
        instances.  When provided, _dispatch instantiates a real Block
        before passing it to the runner.  When None (default), the raw
        NodeDef is forwarded.
    checkpoint_manager:
        Optional checkpoint manager for persisting execution state.
    """

    def __init__(
        self,
        workflow: WorkflowDefinition,
        event_bus: EventBus,
        resource_manager: Any,
        process_registry: Any,
        runner: Any,
        registry: BlockRegistry | None = None,
        checkpoint_manager: Any | None = None,
        lineage_recorder: LineageRecorder | None = None,
        project_dir: str | None = None,
    ) -> None:
        self._workflow = workflow
        self._event_bus = event_bus
        self._resource_manager = resource_manager
        self._process_registry = process_registry
        self._runner = runner
        self._registry = registry
        self._checkpoint_manager = checkpoint_manager
        self._lineage_recorder = lineage_recorder
        self._project_dir = project_dir

        self._dag = build_dag(workflow)
        self._order = topological_sort(self._dag)

        # Block state tracking: IDLE -> READY -> RUNNING -> DONE/ERROR/CANCELLED/SKIPPED
        self._block_states: dict[str, BlockState] = {n: BlockState.IDLE for n in self._dag.nodes}
        self._block_outputs: dict[str, Any] = {}
        self.skip_reasons: dict[str, str] = {}

        # Active asyncio.Task per block (ADR-018 Addendum 1). Populated by
        # ``_dispatch`` when a block's ``_run_and_finalize`` task is created
        # and popped by that task's ``finally`` clause on exit.
        self._active_tasks: dict[str, asyncio.Task[None]] = {}

        self._completed_event = asyncio.Event()
        self._paused = False
        self._reset_lock = asyncio.Lock()

        # #591/#594: Pending interactive responses. Maps block_id to an
        # asyncio.Future that is resolved when the frontend sends an
        # interactive_complete message for that block.
        self._interactive_futures: dict[str, asyncio.Future[dict[str, Any]]] = {}

        self._disposed = False
        self._event_bus.subscribe(BLOCK_DONE, self._on_block_done)
        self._event_bus.subscribe(BLOCK_ERROR, self._on_block_error)
        self._event_bus.subscribe(CANCEL_BLOCK_REQUEST, self._on_cancel_block)
        self._event_bus.subscribe(CANCEL_WORKFLOW_REQUEST, self._on_cancel_workflow)
        self._event_bus.subscribe(INTERACTIVE_COMPLETE, self._on_interactive_complete)

    def dispose(self) -> None:
        """Unsubscribe this scheduler's handlers from the shared EventBus.

        #1517: ``ApiRuntime`` owns one process-global ``EventBus`` and builds a
        fresh ``DAGScheduler`` per run. Without symmetric teardown a finished
        run's scheduler keeps reacting to later runs' events (stale checkpoint
        overwrites, cross-run dispatch). Call this once the run task is done,
        alongside ``LineageRecorder.dispose()``. Idempotent.
        """
        if self._disposed:
            return
        self._event_bus.unsubscribe(BLOCK_DONE, self._on_block_done)
        self._event_bus.unsubscribe(BLOCK_ERROR, self._on_block_error)
        self._event_bus.unsubscribe(CANCEL_BLOCK_REQUEST, self._on_cancel_block)
        self._event_bus.unsubscribe(CANCEL_WORKFLOW_REQUEST, self._on_cancel_workflow)
        self._event_bus.unsubscribe(INTERACTIVE_COMPLETE, self._on_interactive_complete)
        self._disposed = True

    async def execute(self) -> None:
        """Begin executing the workflow from its current state.

        Independent DAG branches run concurrently: ``_dispatch`` creates an
        ``asyncio.Task`` per block (ADR-018 Addendum 1). The method body is
        wrapped in ``try/finally`` so that any exception triggers
        ``_cancel_active_tasks_on_shutdown`` to terminate subprocess
        handles and cancel pre-subprocess tasks, preventing zombie
        processes on engine-level failure.
        """
        await self._event_bus.emit(EngineEvent(event_type=WORKFLOW_STARTED, data={"workflow_id": self._workflow.id}))

        if not self._dag.nodes:
            self._completed_event.set()
            await self._event_bus.emit(
                EngineEvent(event_type=WORKFLOW_COMPLETED, data={"workflow_id": self._workflow.id})
            )
            return

        try:
            # Initial dispatch of root-ready blocks. Each _dispatch call
            # creates a task and returns immediately; successor dispatches
            # are triggered by _on_block_done -> _dispatch_newly_ready.
            for node_id in self._order:
                if self._block_states[node_id] == BlockState.IDLE and self._check_readiness(node_id):
                    self._block_states[node_id] = BlockState.READY
                    await self._emit_block_ready(node_id)
                    await self._dispatch(node_id)
            await self._completed_event.wait()
        finally:
            await self._cancel_active_tasks_on_shutdown()

        await self._event_bus.emit(EngineEvent(event_type=WORKFLOW_COMPLETED, data={"workflow_id": self._workflow.id}))

    async def pause(self) -> None:
        """Request a graceful pause after current blocks complete."""
        self._paused = True

    async def resume(self) -> None:
        """Resume a previously paused workflow execution."""
        self._paused = False
        for node_id in self._order:
            if self._block_states[node_id] == BlockState.READY:
                await self._dispatch(node_id)
            elif self._block_states[node_id] == BlockState.IDLE and self._check_readiness(node_id):
                # #1367: every scheduler-owned IDLE->READY transition must
                # emit ``BLOCK_READY`` exactly once. The execute() and
                # _dispatch_newly_ready() paths already do so; resume()
                # used to flip the state silently, causing frontend WS
                # subscribers to miss readiness events on resume.
                self._block_states[node_id] = BlockState.READY
                await self._emit_block_ready(node_id)
                await self._dispatch(node_id)
        await self._drain_active_tasks()

    async def cancel_workflow(self) -> None:
        """Cancel the current workflow execution."""
        await self._on_cancel_workflow(
            EngineEvent(
                event_type=CANCEL_WORKFLOW_REQUEST,
                data={"workflow_id": self._workflow.id},
            )
        )

    async def cancel_block(self, block_id: str) -> None:
        """Cancel a single block inside the current workflow."""
        await self._on_cancel_block(
            EngineEvent(
                event_type=CANCEL_BLOCK_REQUEST,
                block_id=block_id,
                data={"workflow_id": self._workflow.id},
            )
        )

    def block_states(self) -> dict[str, BlockState]:
        """Return a snapshot of current block execution states."""
        return dict(self._block_states)

    def set_state(self, block_id: str, state: BlockState) -> None:
        """Manually override the execution state of a single block.

        Parameters
        ----------
        block_id:
            The block whose state to override.
        state:
            The new BlockState value.
        """
        self._block_states[block_id] = state

    async def rerun_block(self, block_id: str) -> None:
        """Re-run a block, terminating any active subprocess first.

        If *block_id* is currently RUNNING, the existing task and subprocess
        are cancelled via ``_cancel_if_active`` before the block is
        re-dispatched.  This prevents orphan processes and duplicate block
        executions that would otherwise arise when a caller re-dispatches a
        block while the old run is still alive (bug #424).

        Unlike ``reset_block``, ``rerun_block`` does **not** walk the upstream
        or downstream dependency chain — it only resets and re-dispatches the
        target block itself.

        Parameters
        ----------
        block_id:
            The block to re-run.

        Raises
        ------
        ValueError
            If *block_id* is not part of the current workflow.
        """
        if block_id not in self._block_states:
            raise ValueError(f"Unknown block: {block_id}")

        # Step 2: cancel any active run, waiting for it to exit fully.
        await self._cancel_if_active(block_id)

        # Step 3: reset to IDLE so the block can be re-dispatched.
        self._block_states[block_id] = BlockState.IDLE
        self._block_outputs.pop(block_id, None)
        self.skip_reasons.pop(block_id, None)

        # Step 4: dispatch if ready.
        if self._check_readiness(block_id):
            # #1367: emit BLOCK_READY on the rerun IDLE->READY transition so
            # frontend WS subscribers observe readiness consistently with
            # execute() and _dispatch_newly_ready().
            self._block_states[block_id] = BlockState.READY
            await self._emit_block_ready(block_id)
            await self._dispatch(block_id)

        await self._drain_active_tasks()

    async def reset_block(self, block_id: str) -> None:
        """Reset a block and its dependency chain for selective re-run.

        Algorithm (ADR-018):
            1. Validate block exists.
            1b. Cancel active task/subprocess if the block is RUNNING (#424).
            2. Set target block to IDLE, clear cached outputs and skip reasons.
            3. Walk upstream: recursively reset non-DONE predecessors to IDLE.
            4. Walk downstream: reset SKIPPED blocks to IDLE.
            5. Re-evaluate readiness and batch-dispatch ready blocks.
        """
        async with self._reset_lock:
            if block_id not in self._block_states:
                raise ValueError(f"Unknown block: {block_id}")

            # Step 1b: Cancel active task/subprocess before resetting (#424).
            await self._cancel_if_active(block_id)

            # Step 2: Reset target block.
            self._block_states[block_id] = BlockState.IDLE
            self._block_outputs.pop(block_id, None)
            self.skip_reasons.pop(block_id, None)

            # Step 3: Walk upstream -- recursively reset non-DONE predecessors.
            self._reset_upstream(block_id, visited=set())

            # Step 4: Walk downstream -- reset SKIPPED blocks.
            self._reset_downstream_skipped(block_id)

            # Step 5: Re-evaluate readiness, collect ready IDs, then dispatch.
            # #1367: every scheduler-owned IDLE->READY transition emits
            # ``BLOCK_READY`` exactly once. The reset path used to flip
            # state silently for every block that became ready after the
            # reset, breaking frontend WS readiness visibility for
            # selectively re-run subgraphs.
            ready_ids: list[str] = []
            for node_id in self._order:
                if self._block_states[node_id] == BlockState.IDLE and self._check_readiness(node_id):
                    self._block_states[node_id] = BlockState.READY
                    await self._emit_block_ready(node_id)
                    ready_ids.append(node_id)
            for node_id in ready_ids:
                await self._dispatch(node_id)

        # Drain outside the reset lock: _run_and_finalize → _on_block_done
        # acquires no locks but still touches scheduler state, and the
        # caller expects reset_block to return only after the dispatched
        # tasks have finished.
        await self._drain_active_tasks()

    def save_checkpoint(self, checkpoint_manager: Any = None) -> None:
        """Persist the current execution state to durable storage."""
        if checkpoint_manager is None:
            return

        from datetime import datetime

        from scistudio.engine.checkpoint import WorkflowCheckpoint, serialize_intermediate_refs

        checkpoint = WorkflowCheckpoint(
            workflow_id=self._workflow.id if hasattr(self._workflow, "id") else "unknown",
            timestamp=datetime.now(),
            block_states={k: v.value for k, v in self._block_states.items()},
            intermediate_refs=serialize_intermediate_refs(self._block_outputs),
            skip_reasons=dict(self.skip_reasons),
        )
        checkpoint_manager.save(checkpoint)

    async def execute_from(self, block_id: str) -> None:
        """Re-run the workflow from *block_id* using checkpointed upstream outputs."""
        if block_id not in self._block_states:
            raise ValueError(f"Unknown block: {block_id}")
        if self._checkpoint_manager is None:
            raise ValueError("Selective execution requires a checkpoint manager.")

        checkpoint = self._checkpoint_manager.load(self._workflow.id)
        if checkpoint is None:
            raise FileNotFoundError("No checkpoint is available for this workflow.")

        ancestors = self._ancestors_of(block_id)
        missing = [ancestor for ancestor in ancestors if ancestor not in checkpoint.intermediate_refs]
        if missing:
            raise ValueError("Cannot execute from block without cached upstream outputs: " + ", ".join(sorted(missing)))

        descendants = set(get_downstream_blocks(self._dag, block_id)) | {block_id}

        # Cancel any active tasks for the target block and its descendants
        # before resetting them (#424).
        for node_id in descendants:
            await self._cancel_if_active(node_id)

        self._completed_event = asyncio.Event()

        # ADR-027 Addendum 1 / #408: Wire-format dicts ({"backend": ...,
        # "path": ..., "format": ..., "metadata": {"type_chain": [...], ...}})
        # are assigned directly to _block_outputs WITHOUT calling
        # deserialize_intermediate_refs().  This is intentional:
        #
        #   1. Wire-format dicts are already JSON-serialisable and can be
        #      shipped to a worker subprocess via spawn_block_process() / stdin.
        #   2. The worker's _reconstruct_one() reads metadata.type_chain and
        #      reconstructs the correct typed DataObject instance inside the
        #      sandboxed subprocess, preserving plugin type identity.
        #   3. deserialize_intermediate_refs() is not called here because
        #      the wire-format dicts must remain JSON-serialisable for
        #      spawn_block_process().
        #
        # See checkpoint.py for the deprecated deserialize_intermediate_refs()
        # function and the full rationale.
        # #404 / #408 / ADR-027 Addendum 1 / ADR-031 D8: Wire-format dicts
        # from the checkpoint are assigned directly to _block_outputs
        # WITHOUT calling deserialize_intermediate_refs().  The wire-format
        # dict carries a metadata.type_chain field that _reconstruct_one()
        # inside the worker subprocess uses to instantiate the correct
        # typed DataObject.
        for node_id in self._order:
            if node_id in ancestors:
                self._block_states[node_id] = BlockState.DONE
                self._block_outputs[node_id] = checkpoint.intermediate_refs[node_id]
                self.skip_reasons.pop(node_id, None)
            elif node_id in descendants:
                self._block_states[node_id] = BlockState.IDLE
                self._block_outputs.pop(node_id, None)
                self.skip_reasons.pop(node_id, None)
            else:
                self._block_states[node_id] = BlockState(checkpoint.block_states.get(node_id, "idle"))
                if node_id in checkpoint.intermediate_refs:
                    self._block_outputs[node_id] = checkpoint.intermediate_refs[node_id]

        # ADR-038 §5.2 (supersedes ADR-032 Phase 2a): backfill lineage
        # ``data_objects`` from checkpoint data on resume. Only inserts
        # missing entries (no overwrites).
        self._sync_checkpoint_to_store()

        await self._event_bus.emit(
            EngineEvent(
                event_type=WORKFLOW_STARTED,
                data={"workflow_id": self._workflow.id, "mode": "execute_from", "block_id": block_id},
            )
        )

        try:
            for node_id in self._order:
                if self._block_states[node_id] == BlockState.IDLE and self._check_readiness(node_id):
                    self._block_states[node_id] = BlockState.READY
                    await self._emit_block_ready(node_id)
                    await self._dispatch(node_id)
            await self._completed_event.wait()
        finally:
            await self._cancel_active_tasks_on_shutdown()

        await self._event_bus.emit(
            EngineEvent(
                event_type=WORKFLOW_COMPLETED,
                data={"workflow_id": self._workflow.id, "mode": "execute_from", "block_id": block_id},
            )
        )

    # ------------------------------------------------------------------
    # Path D method bindings (ADR-046 §4).
    #
    # Each method body lives in a private sibling module as a free
    # function whose first parameter is ``self``. The class-body
    # assignment publishes the function under its canonical method
    # name so griffe emits the
    # ``scistudio.engine.scheduler.DAGScheduler.<method>`` fact and
    # callers (`tests/`, `scistudio.api.runtime`, ...) see no public
    # surface change.
    # ------------------------------------------------------------------

    # Block dispatch (see ``_dispatch.py``)
    _emit_block_ready = _dispatch_mod._emit_block_ready
    _dispatch = _dispatch_mod._dispatch
    _run_and_finalize = _dispatch_mod._run_and_finalize
    _run_interactive = _dispatch_mod._run_interactive
    _dispatch_newly_ready = _dispatch_mod._dispatch_newly_ready
    _instantiate_block = _dispatch_mod._instantiate_block
    _gather_inputs = _dispatch_mod._gather_inputs

    # Event handlers (see ``_events.py``)
    _on_block_done = _events_mod._on_block_done
    _on_block_error = _events_mod._on_block_error
    _on_cancel_block = _events_mod._on_cancel_block
    _on_cancel_workflow = _events_mod._on_cancel_workflow
    _on_interactive_complete = _events_mod._on_interactive_complete

    # Lineage + output (see ``_lineage.py``)
    _persist_output_metadata = _lineage_mod._persist_output_metadata
    _resolve_lineage_store = _lineage_mod._resolve_lineage_store
    _persist_single_output = _lineage_mod._persist_single_output
    _upsert_wire_row = _lineage_mod._upsert_wire_row
    _sync_checkpoint_to_store = _lineage_mod._sync_checkpoint_to_store
    _build_block_done_data = _lineage_mod._build_block_done_data
    _build_block_terminal_data = _lineage_mod._build_block_terminal_data
    _resolve_block_type = _lineage_mod._resolve_block_type
    _resolve_block_version = _lineage_mod._resolve_block_version

    # State machine (see ``_state.py``; ADR-046 §5 only-move)
    _check_readiness = _state_mod._check_readiness
    _check_completion = _state_mod._check_completion
    _propagate_skip = _state_mod._propagate_skip

    # Rerun / graph traversal (see ``_rerun.py``)
    _cancel_if_active = _rerun_mod._cancel_if_active
    _ancestors_of = _rerun_mod._ancestors_of
    _reset_upstream = _rerun_mod._reset_upstream
    _reset_downstream_skipped = _rerun_mod._reset_downstream_skipped
    _drain_active_tasks = _rerun_mod._drain_active_tasks
    _cancel_active_tasks_on_shutdown = _rerun_mod._cancel_active_tasks_on_shutdown
