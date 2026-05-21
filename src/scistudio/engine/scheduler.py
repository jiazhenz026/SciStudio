"""DAGScheduler -- event-driven workflow execution with cancellation and skip propagation."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from scistudio.blocks.base.state import BlockState, ExecutionMode
from scistudio.engine.dag import build_dag, get_downstream_blocks, topological_sort
from scistudio.engine.events import (
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
    PROCESS_EXITED,
    WORKFLOW_COMPLETED,
    WORKFLOW_STARTED,
    EngineEvent,
    EventBus,
)
from scistudio.engine.resources import ResourceRequest
from scistudio.engine.runners.terminal_state import BlockTerminalStateReportedError
from scistudio.workflow.definition import WorkflowDefinition

if TYPE_CHECKING:
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core.lineage.recorder import LineageRecorder

logger = logging.getLogger(__name__)

_MAX_ERROR_SUMMARY_LEN = 120


def _extract_error_summary(error_text: str) -> str:
    """Return a short summary from an error/traceback string.

    Uses the last non-empty line (typically the actual exception message),
    truncated to ``_MAX_ERROR_SUMMARY_LEN`` characters.
    """
    lines = [ln.strip() for ln in error_text.splitlines() if ln.strip()]
    summary = lines[-1] if lines else error_text
    if len(summary) > _MAX_ERROR_SUMMARY_LEN:
        summary = summary[: _MAX_ERROR_SUMMARY_LEN - 1] + "\u2026"
    return summary


def _collect_object_ids(payload: Any) -> dict[str, list[str]]:
    """Extract ``{port_name: [object_id, ...]}`` from a wire-format dict.

    ADR-038 §3.2 expects the scheduler to feed the LineageRecorder a
    pre-computed object-id map so it can write ``block_io`` rows without
    re-parsing the wire format. Scalars and Collection items are both
    flattened to a list per port. Ports whose values are not DataObject
    wire payloads (e.g. plain ints) are skipped silently.
    """
    if not isinstance(payload, dict):
        return {}

    result: dict[str, list[str]] = {}
    for port_name, value in payload.items():
        if port_name == "__scistudio_env__":
            continue
        ids = _object_ids_for_value(value)
        if ids:
            result[str(port_name)] = ids
    return result


def _object_ids_for_value(value: Any) -> list[str]:
    """Recursively extract object_ids from a single wire-format port value."""
    if isinstance(value, dict):
        if value.get("_collection"):
            ids: list[str] = []
            for item in value.get("items", []) or []:
                ids.extend(_object_ids_for_value(item))
            return ids
        framework = (value.get("metadata") or {}).get("framework") or {}
        candidate = framework.get("object_id")
        if isinstance(candidate, str) and candidate:
            return [candidate]
    return []


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

        self._event_bus.subscribe(BLOCK_DONE, self._on_block_done)
        self._event_bus.subscribe(BLOCK_ERROR, self._on_block_error)
        self._event_bus.subscribe(CANCEL_BLOCK_REQUEST, self._on_cancel_block)
        self._event_bus.subscribe(CANCEL_WORKFLOW_REQUEST, self._on_cancel_workflow)
        self._event_bus.subscribe(PROCESS_EXITED, self._on_process_exited)
        self._event_bus.subscribe(INTERACTIVE_COMPLETE, self._on_interactive_complete)

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

    async def _emit_block_ready(self, node_id: str) -> None:
        """Emit ``BLOCK_READY`` after a block's IDLE->READY transition.

        ``BLOCK_READY`` is declared in :mod:`scistudio.engine.events`,
        listed in ``scistudio.api.ws._OUTBOUND_EVENTS`` so the frontend
        WS forwards it, and named in the event-routing table
        (``events.py:69-72``) as a ``DAGScheduler``-emitted lifecycle
        event. Prior to issue #1327 the scheduler transitioned blocks
        to ``READY`` without ever emitting the event, breaking the
        documented contract — frontend subscribers never fired.

        The emit shape mirrors :data:`BLOCK_RUNNING` for consistency
        with the rest of the lifecycle events.
        """
        await self._event_bus.emit(
            EngineEvent(
                event_type=BLOCK_READY,
                block_id=node_id,
                data={"workflow_id": self._workflow.id},
            )
        )

    async def _dispatch(self, node_id: str) -> None:
        """Synchronous prelude for dispatching a single block.

        Per ADR-018 Addendum 1, this method performs only the work that
        must run on the scheduler coroutine itself — paused/resource
        checks, state transition to RUNNING, BLOCK_RUNNING emission,
        lineage start, input gathering, and block instantiation — and
        then wraps the long-running ``runner.run`` call in an
        ``asyncio.Task`` via ``_run_and_finalize``. The task is stored in
        ``self._active_tasks`` and the method returns immediately so
        that independent branches can run concurrently.

        If ``_paused`` is True or ``ResourceManager.can_dispatch`` returns
        False, the block stays in its current state (READY) and the
        method returns without creating a task — it will be retried on
        the next successor event via ``_dispatch_newly_ready``.
        """
        if self._paused:
            return

        if not self._resource_manager.can_dispatch(ResourceRequest(), active_count=len(self._active_tasks)):
            # Stay READY; retried by _dispatch_newly_ready on the next
            # resource-freeing event (BLOCK_DONE / PROCESS_EXITED).
            return

        # A task already exists for this block — guard against double
        # dispatch that could otherwise replace the live task reference.
        if node_id in self._active_tasks:
            return

        self._block_states[node_id] = BlockState.RUNNING
        await self._event_bus.emit(
            EngineEvent(
                event_type=BLOCK_RUNNING,
                block_id=node_id,
                data={"workflow_id": self._workflow.id},
            )
        )

        if self._lineage_recorder is not None:
            self._lineage_recorder.record_start(node_id)

        inputs = self._gather_inputs(node_id)
        node = self._dag.nodes[node_id]

        try:
            block = self._instantiate_block(node_id)
        except Exception as exc:
            # Block instantiation failed before a task could be created.
            # Transition directly to ERROR and emit BLOCK_ERROR so that
            # skip propagation fires via the normal event path.
            logger.exception("Block %s failed to instantiate", node_id)
            self._block_states[node_id] = BlockState.ERROR
            error_str = str(exc)
            await self._event_bus.emit(
                EngineEvent(
                    event_type=BLOCK_ERROR,
                    block_id=node_id,
                    data=self._build_block_terminal_data(node_id=node_id, error=error_str),
                )
            )
            self.save_checkpoint(self._checkpoint_manager)
            return

        # #632: Pre-dispatch config validation — check required fields
        # from the block's config_schema before handing off to a subprocess.
        # This catches the most common misconfiguration (missing required
        # fields) with a clean error instead of a traceback in the worker.
        # Config values may live in node.config["params"] (BlockConfig's
        # params dict) OR at the top level of node.config (extras readable
        # via BlockConfig(**config).get(key)).  Check both locations.
        config_schema = getattr(block, "config_schema", None)
        if isinstance(config_schema, dict) and config_schema.get("required"):
            required_fields = config_schema["required"]
            properties = config_schema.get("properties", {})
            params = node.config.get("params", {}) if isinstance(node.config.get("params"), dict) else {}
            top_level = node.config if isinstance(node.config, dict) else {}
            missing = [
                f
                for f in required_fields
                if (params.get(f) is None and top_level.get(f) is None and "default" not in properties.get(f, {}))
            ]
            if missing:
                error_str = f"Block '{node_id}' config is missing required field(s): {', '.join(sorted(missing))}"
                logger.error("Pre-dispatch config validation failed for %s: %s", node_id, error_str)
                self._block_states[node_id] = BlockState.ERROR
                await self._event_bus.emit(
                    EngineEvent(
                        event_type=BLOCK_ERROR,
                        block_id=node_id,
                        data=self._build_block_terminal_data(node_id=node_id, error=error_str),
                    )
                )
                self.save_checkpoint(self._checkpoint_manager)
                return

        # Enrich the block config with runtime context (#444).
        enriched_config = dict(node.config)
        enriched_config["block_id"] = node_id
        enriched_config["workflow_id"] = self._workflow.id
        if self._project_dir:
            enriched_config["project_dir"] = self._project_dir

        # #591/#594: Interactive blocks run in-process (no subprocess) because
        # they need bidirectional communication with the frontend. The block
        # pauses, sends data to the frontend, waits for user response, then
        # produces outputs.
        is_interactive = getattr(block, "execution_mode", None) == ExecutionMode.INTERACTIVE

        if is_interactive:
            task = asyncio.create_task(
                self._run_interactive(node_id, block, inputs, enriched_config),
                name=f"dispatch-interactive:{node_id}",
            )
        else:
            task = asyncio.create_task(
                self._run_and_finalize(node_id, block, inputs, enriched_config),
                name=f"dispatch:{node_id}",
            )
        self._active_tasks[node_id] = task

    async def _run_and_finalize(
        self,
        node_id: str,
        block: Any,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        """Long-running task body for a single block (ADR-018 Addendum 1).

        Awaits ``runner.run``, transitions state to DONE (or ERROR on
        exception, unless the block was already CANCELLED), emits the
        terminal event, and always removes the block from
        ``self._active_tasks`` in its ``finally`` clause.
        """
        try:
            try:
                result = await self._runner.run(block, inputs, config)
            except asyncio.CancelledError:
                # Task was cancelled externally (e.g. via _on_cancel_block
                # pre-subprocess path). State transition to CANCELLED is
                # handled by the caller; re-raise so asyncio can finalise.
                raise
            except BlockTerminalStateReportedError as terminal:
                # #681: the worker subprocess observed that the block ended
                # in a non-DONE terminal state (CANCELLED / ERROR / SKIPPED)
                # via ``self.transition()`` inside ``run()``. Honour that
                # state directly — do NOT overwrite it with ERROR like the
                # generic ``except Exception`` branch below.
                #
                # #689 cancel-race guard: if ``_on_cancel_block`` already
                # pre-set the block to CANCELLED while the worker was
                # finalising its own terminal state (e.g. ERROR / SKIPPED),
                # the CANCELLED state takes precedence. Mirror the generic
                # ``except Exception`` branch's cancellation guard below —
                # do not overwrite the state or emit a contradictory event
                # sequence (BLOCK_CANCELLED followed by BLOCK_ERROR).
                if self._block_states.get(node_id) == BlockState.CANCELLED:
                    logger.info(
                        "Block %s reported terminal state %s from worker "
                        "but was already CANCELLED; preserving CANCELLED",
                        node_id,
                        terminal.state.value,
                    )
                    self.save_checkpoint(self._checkpoint_manager)
                    return
                logger.info(
                    "Block %s reported terminal state %s from worker",
                    node_id,
                    terminal.state.value,
                )
                self._block_states[node_id] = terminal.state
                # Persist any partial outputs the block returned alongside
                # the terminal state, so downstream lineage and re-runs see
                # the same view as the worker.
                if terminal.outputs:
                    self._block_outputs[node_id] = terminal.outputs
                if terminal.state == BlockState.CANCELLED:
                    await self._event_bus.emit(
                        EngineEvent(
                            event_type=BLOCK_CANCELLED,
                            block_id=node_id,
                            data=self._build_block_terminal_data(node_id=node_id),
                        )
                    )
                    await self._propagate_skip(node_id, "cancelled")
                elif terminal.state == BlockState.ERROR:
                    error_str = f"Block reported terminal state {terminal.state.value} from worker"
                    await self._event_bus.emit(
                        EngineEvent(
                            event_type=BLOCK_ERROR,
                            block_id=node_id,
                            data=self._build_block_terminal_data(node_id=node_id, error=error_str),
                        )
                    )
                    await self._propagate_skip(node_id, "error")
                else:
                    # SKIPPED: the block reported it cannot continue; emit
                    # BLOCK_SKIPPED and propagate downstream.
                    self.skip_reasons[node_id] = "block reported skipped"
                    await self._event_bus.emit(
                        EngineEvent(
                            event_type=BLOCK_SKIPPED,
                            block_id=node_id,
                            data=self._build_block_terminal_data(node_id=node_id),
                        )
                    )
                    await self._propagate_skip(node_id, "skipped")
                self.save_checkpoint(self._checkpoint_manager)
                return
            except Exception as exc:
                if self._block_states.get(node_id) == BlockState.CANCELLED:
                    logger.info("Block %s exited after cancellation", node_id)
                    self.save_checkpoint(self._checkpoint_manager)
                    return
                logger.exception("Block %s failed with exception", node_id)
                self._block_states[node_id] = BlockState.ERROR
                error_str = str(exc)
                await self._event_bus.emit(
                    EngineEvent(
                        event_type=BLOCK_ERROR,
                        block_id=node_id,
                        data=self._build_block_terminal_data(node_id=node_id, error=error_str),
                    )
                )
                self.save_checkpoint(self._checkpoint_manager)
                return

            # ADR-038 §5.2: lift the per-block ``environment`` sidecar
            # injected by ``runners/local.py`` into the BLOCK_DONE event data.
            # Strip the sentinel key so downstream blocks never observe it on
            # their input ports.
            env_payload: dict[str, Any] | None = None
            if isinstance(result, dict) and "__scistudio_env__" in result:
                env_candidate = result.pop("__scistudio_env__")
                if isinstance(env_candidate, dict):
                    env_payload = env_candidate

            # #1330: ADR-020 §3 contract enforcement at the in-process
            # boundary. Subprocess execution already normalises inside
            # ``worker.py`` before ``serialise_outputs``; this second call
            # site is a belt-and-suspenders no-op for the wire-format
            # dict path and a meaningful wrap for any future runner that
            # returns raw Python DataObjects directly (e.g. in-process
            # path or partial outputs from BlockTerminalStateReportedError).
            if isinstance(result, dict):
                from scistudio.engine.runners.worker import _normalize_outputs

                try:
                    effective_output_ports = block.get_effective_output_ports()
                except AttributeError:
                    effective_output_ports = list(getattr(type(block), "output_ports", []))
                _normalize_outputs(result, effective_output_ports)

            self._block_outputs[node_id] = result
            # ADR-038 §5.2: persist DataObject identity to the unified
            # ``data_objects`` table via :class:`LineageStore`. The
            # LineageRecorder additionally writes ``block_io`` rows when
            # it observes the BLOCK_DONE event emitted below — running
            # this step first ensures the ``produced_by_execution`` FK
            # on the recorder's ``block_io`` insert is already valid.
            self._persist_output_metadata(node_id, result, self._workflow.id)
            self._block_states[node_id] = BlockState.DONE
            await self._event_bus.emit(
                EngineEvent(
                    event_type=BLOCK_DONE,
                    block_id=node_id,
                    data=self._build_block_done_data(
                        node_id=node_id,
                        block=block,
                        inputs=inputs,
                        config=config,
                        outputs=result,
                        environment=env_payload,
                    ),
                )
            )
            self.save_checkpoint(self._checkpoint_manager)
        finally:
            # Always pop the task entry so _check_completion can observe
            # "no active tasks" once the final block finalises.
            self._active_tasks.pop(node_id, None)
            self._check_completion()

    async def _run_interactive(
        self,
        node_id: str,
        block: Any,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> None:
        """Execute an interactive block: PAUSE, prompt frontend, await response, run.

        #591/#594: Interactive blocks (DataRouter, PairEditor) run in-process
        because they need bidirectional WebSocket communication. The flow is:

        1. Transition to PAUSED, emit BLOCK_PAUSED
        2. Call ``block.prepare_prompt(inputs, config)`` to get data for the UI
        3. Emit INTERACTIVE_PROMPT with the prepared data
        4. Await the user's response via an asyncio.Future
        5. Call ``block.run(inputs, config)`` with the response merged into config
        6. Transition to DONE, emit BLOCK_DONE with outputs
        """
        try:
            try:
                # Step 1: Transition to PAUSED.
                self._block_states[node_id] = BlockState.PAUSED
                await self._event_bus.emit(
                    EngineEvent(
                        event_type=BLOCK_PAUSED,
                        block_id=node_id,
                        data={"workflow_id": self._workflow.id},
                    )
                )

                # Step 2: Prepare the interactive prompt data.
                prompt_data = {}
                if hasattr(block, "prepare_prompt"):
                    from scistudio.blocks.base.config import BlockConfig

                    prompt_data = block.prepare_prompt(inputs, BlockConfig(**config))

                # Step 3: Emit INTERACTIVE_PROMPT for the frontend.
                await self._event_bus.emit(
                    EngineEvent(
                        event_type=INTERACTIVE_PROMPT,
                        block_id=node_id,
                        data={
                            "workflow_id": self._workflow.id,
                            "block_type": config.get("block_type", type(block).__name__),
                            **prompt_data,
                        },
                    )
                )

                # Step 4: Create a future and wait for interactive_complete.
                loop = asyncio.get_running_loop()
                future: asyncio.Future[dict[str, Any]] = loop.create_future()
                self._interactive_futures[node_id] = future

                response_data = await future

                # Step 5: Run the block with the user's response.
                # Check for cancellation before running.
                if self._block_states.get(node_id) == BlockState.CANCELLED:
                    logger.info("Interactive block %s was cancelled while paused", node_id)
                    return

                self._block_states[node_id] = BlockState.RUNNING
                await self._event_bus.emit(
                    EngineEvent(
                        event_type=BLOCK_RUNNING,
                        block_id=node_id,
                        data={"workflow_id": self._workflow.id},
                    )
                )

                # Merge the user response into config for the block's run().
                enriched_config = dict(config)
                enriched_config["interactive_response"] = response_data

                from scistudio.blocks.base.config import BlockConfig

                result = block.run(inputs, BlockConfig(**enriched_config))

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._block_states.get(node_id) == BlockState.CANCELLED:
                    logger.info("Interactive block %s exited after cancellation", node_id)
                    self.save_checkpoint(self._checkpoint_manager)
                    return
                logger.exception("Interactive block %s failed with exception", node_id)
                self._block_states[node_id] = BlockState.ERROR
                error_str = str(exc)
                await self._event_bus.emit(
                    EngineEvent(
                        event_type=BLOCK_ERROR,
                        block_id=node_id,
                        data=self._build_block_terminal_data(node_id=node_id, error=error_str),
                    )
                )
                self.save_checkpoint(self._checkpoint_manager)
                return

            # Step 6: Transition to DONE.
            # ADR-038 §5.2: interactive blocks run in-process so they have no
            # worker-supplied environment sidecar; pass None and the recorder
            # will fall back to inserting an empty environment for the row.
            env_payload: dict[str, Any] | None = None
            if isinstance(result, dict) and "__scistudio_env__" in result:
                env_candidate = result.pop("__scistudio_env__")
                if isinstance(env_candidate, dict):
                    env_payload = env_candidate

            # #1370: ADR-020 §3 contract enforcement at the interactive
            # in-process boundary. The worker-subprocess path normalises
            # inside ``worker.py`` and the regular in-process path does so
            # in ``_run_and_finalize``; the interactive path used to skip
            # the wrap, so a custom interactive block returning a bare
            # ``DataObject`` or ``list[DataObject]`` on an
            # ``is_collection=True`` port could leak through unwrapped.
            if isinstance(result, dict):
                from scistudio.engine.runners.worker import _normalize_outputs

                try:
                    effective_output_ports = block.get_effective_output_ports()
                except AttributeError:
                    effective_output_ports = list(getattr(type(block), "output_ports", []))
                _normalize_outputs(result, effective_output_ports)

            self._block_outputs[node_id] = result
            # ADR-038 §5.2: persist DataObject identity to the unified
            # ``data_objects`` table. See the parallel callsite in
            # :meth:`_run_and_finalize` for the rationale.
            self._persist_output_metadata(node_id, result, self._workflow.id)
            self._block_states[node_id] = BlockState.DONE
            await self._event_bus.emit(
                EngineEvent(
                    event_type=BLOCK_DONE,
                    block_id=node_id,
                    data=self._build_block_done_data(
                        node_id=node_id,
                        block=block,
                        inputs=inputs,
                        config=config,
                        outputs=result,
                        environment=env_payload,
                    ),
                )
            )
            self.save_checkpoint(self._checkpoint_manager)
        finally:
            self._interactive_futures.pop(node_id, None)
            self._active_tasks.pop(node_id, None)
            self._check_completion()

    # -- ADR-038 §5.2: DataObject identity persistence -----------------------

    def _persist_output_metadata(
        self,
        node_id: str,
        result: dict[str, Any] | Any,
        workflow_id: str,
    ) -> None:
        """Persist DataObject identity rows to the unified ``data_objects`` table.

        Phase D38-2.3 (ADR-038 §6 Phase 2): replaces the pre-ADR-038
        ``metadata.db`` write path. Writes go to the active
        :class:`~scistudio.core.lineage.LineageStore`.

        **Recorder-aware split (Codex P1 #931):** when a
        :class:`LineageRecorder` is bound to this scheduler, the recorder
        owns the authoritative write of every ``data_objects`` row from
        its ``BLOCK_DONE`` handler. The recorder stamps the
        ``produced_by_execution`` foreign key with the same
        ``block_execution_id`` it writes to ``block_executions``. Letting
        the scheduler also pre-write would call ``upsert_data_object()``
        (which uses ``INSERT OR IGNORE``), permanently fixing the row's
        ``produced_by_execution`` to ``NULL`` and breaking the ADR §3.7
        Q4b join. So when a recorder is present this method is a no-op —
        the recorder's pass writes the row with the correct producer.

        When the scheduler is constructed *without* a recorder (CLI /
        direct test runners that bypass :class:`ApiRuntime`), this method
        is the only writer. In that mode the row's
        ``produced_by_execution`` is legitimately ``NULL`` because no
        ``block_executions`` row exists to reference.

        The method is **non-fatal**: any exception is logged as a warning
        and does not crash the workflow.
        """
        # Recorder owns the write path when bound — see docstring.
        if self._lineage_recorder is not None:
            return
        try:
            store = self._resolve_lineage_store()
            if store is None:
                return
            if not isinstance(result, dict):
                return
            for port_name, value in result.items():
                self._persist_single_output(store, value, workflow_id, node_id, port_name)
        except Exception:
            logger.warning(
                "ADR-038: data_objects persist failed for node %s (non-fatal)",
                node_id,
                exc_info=True,
            )

    def _resolve_lineage_store(self) -> Any:
        """Return the active :class:`LineageStore`, or ``None``.

        Looks first at the lineage recorder bound to this scheduler, then
        falls back to the deprecation shim's module-level handle which
        :meth:`ApiRuntime._init_lineage_store` publishes on project open.
        The lazy import keeps the scheduler usable outside the API server
        (CLI / direct test invocation that bypasses :class:`ApiRuntime`).
        """
        recorder = self._lineage_recorder
        if recorder is not None:
            store = getattr(recorder, "_store", None)
            if store is not None:
                return store
        try:
            from scistudio.core.metadata_store import _active_lineage_store

            return _active_lineage_store()
        except Exception:
            return None

    def _persist_single_output(
        self,
        store: Any,
        value: Any,
        workflow_id: str,
        node_id: str,
        port_name: str,
    ) -> None:
        """Upsert one output port's wire payload(s) into ``data_objects``."""
        if not isinstance(value, dict):
            return
        # Collection: {"_collection": True, "items": [...], "item_type": "..."}
        if value.get("_collection"):
            for item in value.get("items", []):
                if isinstance(item, dict) and "metadata" in item:
                    self._upsert_wire_row(store, item, node_id, port_name)
        elif "metadata" in value:
            self._upsert_wire_row(store, value, node_id, port_name)

    def _upsert_wire_row(
        self,
        store: Any,
        wire_dict: dict[str, Any],
        node_id: str,
        port_name: str,
    ) -> None:
        """Materialise one ``DataObjectRow`` for a wire payload and upsert."""
        try:
            from datetime import datetime

            from scistudio.core.lineage.record import DataObjectRow
        except Exception:
            logger.debug(
                "ADR-038: lineage record import failed for %s/%s (non-fatal)",
                node_id,
                port_name,
                exc_info=True,
            )
            return
        metadata = wire_dict.get("metadata") or {}
        framework = metadata.get("framework") or {}
        object_id = framework.get("object_id") if isinstance(framework, dict) else None
        if not isinstance(object_id, str) or not object_id:
            return

        type_chain = metadata.get("type_chain")
        type_name = "DataObject"
        if isinstance(type_chain, list) and type_chain:
            leaf = type_chain[0]
            if isinstance(leaf, str):
                type_name = leaf
        elif isinstance(wire_dict.get("type_name"), str):
            type_name = wire_dict["type_name"]

        created_at = framework.get("created_at") if isinstance(framework, dict) else None
        if not isinstance(created_at, str) or not created_at:
            created_at = datetime.now().isoformat()

        row = DataObjectRow(
            object_id=object_id,
            type_name=type_name,
            wire_payload=wire_dict,
            created_at=created_at,
            backend=wire_dict.get("backend") if isinstance(wire_dict.get("backend"), str) else None,
            storage_path=wire_dict.get("path") if isinstance(wire_dict.get("path"), str) else None,
            derived_from=framework.get("derived_from") if isinstance(framework, dict) else None,
            # ``produced_by_execution`` is FK to ``block_executions``.
            # The LineageRecorder owns that table and back-stamps the
            # column from the BLOCK_DONE event handler. We leave it None
            # here and rely on the recorder's INSERT OR IGNORE — but the
            # recorder also re-inserts with ``produced_by_execution`` set
            # for output direction, so the join key gets populated on the
            # recorder's pass.
            produced_by_execution=None,
        )
        try:
            store.upsert_data_object(row)
        except Exception:
            logger.warning(
                "ADR-038: upsert_data_object failed for %s/%s (non-fatal)",
                node_id,
                port_name,
            )

    def _sync_checkpoint_to_store(self) -> None:
        """Backfill ``data_objects`` rows from checkpoint data on resume.

        ADR-038 §5.2: when ``execute_from()`` reloads intermediate refs
        from a checkpoint, the referenced DataObjects may not yet exist
        in ``lineage.db`` (the checkpoint pre-dates the run). Iterate the
        rehydrated outputs and upsert each one so downstream
        ``block_io`` FK constraints succeed when the resumed run emits
        BLOCK_DONE.
        """
        try:
            store = self._resolve_lineage_store()
            if store is None:
                return
            workflow_id = self._workflow.id
            for node_id, outputs in self._block_outputs.items():
                if not isinstance(outputs, dict):
                    continue
                for port_name, value in outputs.items():
                    self._persist_single_output(store, value, workflow_id, node_id, port_name)
        except Exception:
            logger.warning(
                "ADR-038: checkpoint-to-store sync failed (non-fatal)",
                exc_info=True,
            )

    # -- ADR-038 §3.2: lineage event-data extension --------------------------

    def _build_block_done_data(
        self,
        *,
        node_id: str,
        block: Any,
        inputs: dict[str, Any],
        config: dict[str, Any],
        outputs: dict[str, Any] | Any,
        environment: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Assemble the BLOCK_DONE event payload (ADR-038 §3.2).

        In addition to the legacy ``workflow_id`` + ``outputs`` keys this
        emits the fields that :class:`LineageRecorder` needs to write the
        ``block_executions`` / ``data_objects`` / ``block_io`` rows:

        * ``config``               — resolved config dict (post-template expansion)
        * ``block_type``           — registry type name for the block
        * ``block_version``        — registry-resolved version per ADR-038 §3.3
        * ``environment``          — full env snapshot from the worker
        * ``input_object_ids``     — ``{port: [object_id, ...]}`` derived from inputs
        * ``output_object_ids``    — same shape for outputs
        * ``inputs``               — raw wire-format inputs (fallback for the recorder)
        """
        block_type = self._resolve_block_type(node_id, block)
        block_version = self._resolve_block_version(block, block_type)
        return {
            "workflow_id": self._workflow.id,
            "outputs": outputs,
            "inputs": inputs,
            "config": dict(config) if isinstance(config, dict) else {},
            "block_type": block_type,
            "block_version": block_version,
            "environment": environment,
            "input_object_ids": _collect_object_ids(inputs),
            "output_object_ids": _collect_object_ids(outputs),
        }

    def _build_block_terminal_data(
        self,
        *,
        node_id: str,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Assemble the BLOCK_ERROR / BLOCK_CANCELLED / BLOCK_SKIPPED payload.

        D38-3.2 (closes audit D38-3.1a P1-1 + D38-3.1b P1-3): all four
        terminal events must carry the ADR-038 §3.2 metadata so the
        recorder writes non-empty ``block_type`` / ``block_version`` /
        ``block_config_resolved`` columns into ``block_executions``.
        Without this, ADR §3.7 Q3 ("which blocks ran in run X") returns
        empty strings for any non-completed block, breaking methods
        export and downstream queries.

        Best-effort: block instantiation may have failed *before* the
        block object exists (the pre-dispatch error paths). In that
        case the registry NodeDef still carries ``block_type``, so we
        look up the version from the registry by type alone.
        ``inputs`` is sampled at terminal time from ``_block_outputs``
        of upstream nodes (read-only via ``_gather_inputs``); when that
        sample fails (e.g. cancel during dispatch) we fall back to an
        empty dict.
        """
        node = self._dag.nodes.get(node_id)
        block_type = ""
        if node is not None:
            block_type = str(getattr(node, "block_type", "") or "")

        block_version = ""
        config: dict[str, Any] = {}
        if node is not None:
            cfg = getattr(node, "config", None)
            if isinstance(cfg, dict):
                config = dict(cfg)
            # Registry-resolved version (ADR-038 §3.3 force-injection at
            # scan time). When the registry isn't wired (mock-runner
            # tests) fall back to a blank string — the recorder writes
            # the empty string into the NOT NULL column without raising.
            if self._registry is not None and block_type:
                try:
                    spec = self._registry.get_spec(block_type)
                    if spec is not None and getattr(spec, "version", None):
                        block_version = str(spec.version)
                except Exception:
                    logger.debug(
                        "Block version registry lookup failed for terminal-event %s/%s",
                        node_id,
                        block_type,
                    )

        try:
            inputs = self._gather_inputs(node_id)
        except Exception:
            inputs = {}

        data: dict[str, Any] = {
            "workflow_id": self._workflow.id,
            "block_type": block_type,
            "block_version": block_version,
            "config": config,
            "inputs": inputs,
            "input_object_ids": _collect_object_ids(inputs),
            "output_object_ids": {},
        }
        if error is not None:
            data["error"] = error
            data["error_summary"] = _extract_error_summary(error)
        if extra:
            data.update(extra)
        return data

    def _resolve_block_type(self, node_id: str, block: Any) -> str:
        """Return the registry type name for ``block``, falling back to NodeDef."""
        node = self._dag.nodes.get(node_id)
        block_type = getattr(node, "block_type", None) if node is not None else None
        if block_type:
            return str(block_type)
        return type(block).__name__

    def _resolve_block_version(self, block: Any, block_type: str) -> str:
        """Return the version stamped on the block spec at registry scan time.

        Per ADR-038 §3.3 the registry force-injects this from
        ``importlib.metadata`` at scan time. When the registry is not wired
        up (mock-runner tests), fall back to the block class's ``version``
        attribute and then to ``scistudio.__version__``.
        """
        if self._registry is not None:
            try:
                spec = self._registry.get_spec(block_type)
                if spec is not None and getattr(spec, "version", None):
                    return str(spec.version)
            except Exception:
                logger.debug("Block version registry lookup failed for %s", block_type)
        explicit = getattr(block, "version", None)
        if isinstance(explicit, str) and explicit:
            return explicit
        try:
            from scistudio import __version__ as scistudio_version

            return str(scistudio_version)
        except Exception:
            return "unknown"

    async def _on_interactive_complete(self, event: EngineEvent) -> None:
        """Handle an interactive_complete event from the frontend.

        Resolves the pending future for the block so that
        ``_run_interactive`` can proceed with the user's response.
        """
        block_id = event.block_id
        if block_id is None:
            return

        future = self._interactive_futures.get(block_id)
        if future is not None and not future.done():
            future.set_result(event.data)
        else:
            logger.warning(
                "Received interactive_complete for block %s but no pending future found",
                block_id,
            )

    def _instantiate_block(self, node_id: str) -> Any:
        """Instantiate the concrete block for a DAG node.

        Uses the BlockRegistry when available. Falls back to the raw
        NodeDef for backward compatibility with tests using mock runners.
        """
        node = self._dag.nodes[node_id]
        if self._registry is not None:
            block = self._registry.instantiate(node.block_type, node.config)
            block.id = node_id
            return block
        node.id = node_id
        return node

    def _gather_inputs(self, node_id: str) -> dict[str, Any]:
        """Collect inputs for *node_id* from upstream block outputs."""
        inputs: dict[str, Any] = {}
        for edge in self._dag.edges:
            tgt_node, tgt_port = edge.target.split(":", 1)
            if tgt_node != node_id:
                continue

            src_node, src_port = edge.source.split(":", 1)
            upstream_outputs = self._block_outputs.get(src_node, {})
            if isinstance(upstream_outputs, dict) and src_port in upstream_outputs:
                inputs[tgt_port] = upstream_outputs[src_port]
            elif isinstance(upstream_outputs, dict):
                # #435: src_port not found in upstream outputs — skip rather
                # than passing the entire dict, which would violate the port
                # contract and confuse downstream blocks.
                logger.warning(
                    "Port '%s' not found in outputs of block '%s' (available: %s); skipping input '%s' for block '%s'",
                    src_port,
                    src_node,
                    list(upstream_outputs.keys()),
                    tgt_port,
                    node_id,
                )
        return inputs

    async def _dispatch_newly_ready(self) -> None:
        """Dispatch blocks that became ready or were previously throttled.

        Called from ``_on_block_done`` and ``_on_process_exited`` after
        a terminal event. Scans the topological order for:

        * IDLE blocks whose predecessors are all DONE — transition to
          READY and dispatch.
        * READY blocks with no active task — previously refused by
          ``ResourceManager.can_dispatch`` and now eligible for a retry.

        ``_dispatch`` is itself idempotent: if ``can_dispatch`` still
        returns False, the block stays READY and no task is created.
        """
        for node_id in self._order:
            state = self._block_states[node_id]
            if state == BlockState.IDLE and self._check_readiness(node_id):
                self._block_states[node_id] = BlockState.READY
                await self._emit_block_ready(node_id)
                await self._dispatch(node_id)
            elif state == BlockState.READY and node_id not in self._active_tasks:
                # Previously blocked by can_dispatch / paused; retry now.
                await self._dispatch(node_id)

    async def _on_block_done(self, event: EngineEvent) -> None:
        """Handle a block completion and dispatch newly ready blocks."""
        if event.block_id is None:
            return

        await self._dispatch_newly_ready()

        self._check_completion()
        self.save_checkpoint(self._checkpoint_manager)

    async def _on_block_error(self, event: EngineEvent) -> None:
        """Handle a block error and propagate skips downstream."""
        if event.block_id is None:
            return

        self._block_states[event.block_id] = BlockState.ERROR
        await self._propagate_skip(event.block_id, "error")
        self._check_completion()
        self.save_checkpoint(self._checkpoint_manager)

    async def _on_cancel_block(self, event: EngineEvent) -> None:
        """Handle a block cancellation request.

        Per ADR-018 Addendum 1, cancellation branches on whether a
        ``ProcessHandle`` has been registered for the block yet:

        * **Handle present** (block is executing inside a subprocess):
          call ``handle.terminate()`` and let the worker unwind
          naturally. ``_run_and_finalize`` observes the CANCELLED state
          on its exception path and exits without emitting BLOCK_ERROR.
        * **Handle absent** (block is still in its pre-subprocess setup
          window or has no subprocess at all): call ``task.cancel()``
          on the active task. ``_run_and_finalize`` receives a
          ``CancelledError`` and unwinds via its ``finally`` clause.
        * **No handle, no active task**: the block is pre-dispatch or
          was set externally (e.g. tests that pre-assign RUNNING). In
          that case we simply transition to CANCELLED without
          terminating or cancelling anything.
        """
        if event.block_id is None:
            return

        block_id = event.block_id
        handle = None
        if self._process_registry is not None:
            handle = self._process_registry.get_handle(block_id)

        # Mark CANCELLED before terminating/cancelling so that
        # _run_and_finalize's exception path sees the CANCELLED state
        # and does not re-emit BLOCK_ERROR.
        self._block_states[block_id] = BlockState.CANCELLED

        # #591/#594: Cancel pending interactive future so _run_interactive
        # receives CancelledError and unwinds.
        interactive_future = self._interactive_futures.pop(block_id, None)
        if interactive_future is not None and not interactive_future.done():
            interactive_future.cancel()

        if handle is not None:
            # Authoritative path per ADR-019 — SIGTERM/SIGKILL the worker.
            try:
                handle.terminate()
            except Exception:
                logger.exception("Failed to terminate subprocess for block %s", block_id)
        else:
            # No subprocess handle yet: cancel the pre-subprocess task
            # so that the setup phase aborts with CancelledError.
            task = self._active_tasks.get(block_id)
            if task is not None and not task.done():
                task.cancel()

        if hasattr(self._runner, "cancel"):
            try:
                await self._runner.cancel(block_id)
            except Exception:
                logger.exception("Failed to cancel block %s via runner", block_id)

        await self._event_bus.emit(
            EngineEvent(
                event_type=BLOCK_CANCELLED,
                block_id=block_id,
                data=self._build_block_terminal_data(node_id=block_id),
            )
        )
        await self._propagate_skip(block_id, "cancelled")
        self._check_completion()
        self.save_checkpoint(self._checkpoint_manager)

    async def _on_cancel_workflow(self, event: EngineEvent) -> None:
        """Handle a workflow cancellation: cancel all running blocks.

        Applies the same handle-vs-task branch as ``_on_cancel_block``
        (ADR-018 Addendum 1). Any block still IDLE/READY at the time of
        the cancel request is transitioned to SKIPPED with reason
        "workflow cancelled".
        """
        # Include both RUNNING and PAUSED blocks — interactive blocks
        # (DataRouter, PairEditor) sit in PAUSED while waiting for user
        # input via an asyncio.Future. They must also be cancelled.
        cancelable_blocks = [
            bid for bid, state in self._block_states.items() if state in (BlockState.RUNNING, BlockState.PAUSED)
        ]

        for block_id in cancelable_blocks:
            handle = None
            if self._process_registry is not None:
                handle = self._process_registry.get_handle(block_id)

            # Mark CANCELLED before terminating/cancelling so that
            # _run_and_finalize observes the CANCELLED state.
            self._block_states[block_id] = BlockState.CANCELLED

            if handle is not None:
                try:
                    handle.terminate()
                except Exception:
                    logger.exception(
                        "Failed to terminate subprocess for block %s during workflow cancel",
                        block_id,
                    )
            else:
                task = self._active_tasks.get(block_id)
                if task is not None and not task.done():
                    task.cancel()

            # Cancel interactive future if the block is PAUSED waiting
            # for user input (DataRouter/PairEditor).
            interactive_future = self._interactive_futures.pop(block_id, None)
            if interactive_future is not None and not interactive_future.done():
                interactive_future.cancel()

            if hasattr(self._runner, "cancel"):
                try:
                    await self._runner.cancel(block_id)
                except Exception:
                    logger.exception("Failed to cancel block %s during workflow cancel", block_id)

            await self._event_bus.emit(
                EngineEvent(
                    event_type=BLOCK_CANCELLED,
                    block_id=block_id,
                    data=self._build_block_terminal_data(node_id=block_id),
                )
            )

        for block_id, state in list(self._block_states.items()):
            if state in (BlockState.IDLE, BlockState.READY):
                self._block_states[block_id] = BlockState.SKIPPED
                self.skip_reasons[block_id] = "workflow cancelled"
                await self._event_bus.emit(
                    EngineEvent(
                        event_type=BLOCK_SKIPPED,
                        block_id=block_id,
                        data=self._build_block_terminal_data(node_id=block_id),
                    )
                )

        self._check_completion()
        self.save_checkpoint(self._checkpoint_manager)

    async def _on_process_exited(self, event: EngineEvent) -> None:
        """Handle an unexpected subprocess exit detected by ProcessMonitor.

        If the block is RUNNING and not yet in a terminal state, transition
        to ERROR and emit BLOCK_ERROR so that skip propagation and completion
        checks fire through the normal path.

        PAUSED blocks (AppBlock case) are left alone \u2014 the FileWatcher
        manages output collection and will handle the process exit.
        """
        block_id = event.block_id
        if block_id is None or block_id not in self._block_states:
            return

        current = self._block_states[block_id]

        # Already in a terminal state \u2014 ignore.
        terminal = {BlockState.DONE, BlockState.ERROR, BlockState.CANCELLED, BlockState.SKIPPED}
        if current in terminal:
            return

        # PAUSED: AppBlock subprocess exited. FileWatcher handles it.
        if current == BlockState.PAUSED:
            return

        # RUNNING: subprocess crashed / OOM-killed / externally terminated.
        if current == BlockState.RUNNING:
            exit_info = event.data.get("exit_info")
            error_detail = "Process exited unexpectedly"
            if isinstance(exit_info, dict):
                sig = exit_info.get("signal_number")
                code = exit_info.get("exit_code")
                if sig:
                    error_detail = f"Process killed by signal {sig}"
                elif code is not None:
                    error_detail = f"Process exited with code {code}"
            elif exit_info is not None:
                sig = getattr(exit_info, "signal_number", None)
                code = getattr(exit_info, "exit_code", None)
                if sig:
                    error_detail = f"Process killed by signal {sig}"
                elif code is not None:
                    error_detail = f"Process exited with code {code}"

            self._block_states[block_id] = BlockState.ERROR
            await self._event_bus.emit(
                EngineEvent(
                    event_type=BLOCK_ERROR,
                    block_id=block_id,
                    data=self._build_block_terminal_data(node_id=block_id, error=error_detail),
                )
            )
            # Retry any READY blocks that were previously throttled and
            # dispatch successors whose predecessors are now all DONE.
            await self._dispatch_newly_ready()
            self._check_completion()

    async def _propagate_skip(self, failed_id: str, reason: str) -> None:
        """Breadth-first skip propagation downstream from *failed_id*."""
        queue = list(self._dag.adjacency.get(failed_id, []))

        while queue:
            node_id = queue.pop(0)
            if self._block_states[node_id] in (
                BlockState.DONE,
                BlockState.ERROR,
                BlockState.CANCELLED,
                BlockState.SKIPPED,
            ):
                continue

            predecessors = self._dag.reverse_adjacency.get(node_id, [])
            all_satisfied = all(self._block_states[p] == BlockState.DONE for p in predecessors)

            if not all_satisfied:
                self._block_states[node_id] = BlockState.SKIPPED
                self.skip_reasons[node_id] = f"upstream {failed_id} {reason}"
                await self._event_bus.emit(
                    EngineEvent(
                        event_type=BLOCK_SKIPPED,
                        block_id=node_id,
                        data=self._build_block_terminal_data(node_id=node_id),
                    )
                )
                queue.extend(self._dag.adjacency.get(node_id, []))

    def _check_readiness(self, node_id: str) -> bool:
        """Return True if all predecessors of *node_id* are in DONE state."""
        predecessors = self._dag.reverse_adjacency.get(node_id, [])
        return all(self._block_states[p] == BlockState.DONE for p in predecessors)

    def _check_completion(self) -> None:
        """Set the completed event when every block has reached a terminal
        state **and** no dispatched task is still running.

        The ``_active_tasks`` guard (ADR-018 Addendum 1) prevents
        ``execute()`` from returning before the final
        ``_run_and_finalize`` coroutine has finished its cleanup.
        """
        terminal = {BlockState.DONE, BlockState.ERROR, BlockState.CANCELLED, BlockState.SKIPPED}
        if all(s in terminal for s in self._block_states.values()) and not self._active_tasks:
            self._completed_event.set()

    async def _cancel_active_tasks_on_shutdown(self) -> None:
        """Best-effort cleanup of any tasks still running on shutdown.

        Called from ``execute()``'s ``finally`` block (ADR-018
        Addendum 1). Iterates every entry in ``self._active_tasks``:

        1. If a ``ProcessHandle`` is registered, terminate the
           subprocess via the ADR-019 path.
        2. If the task is still not done, cancel it and await its
           completion. Swallows any exception because this runs inside
           a ``finally`` clause and must not mask the original error.
        """
        for block_id, task in list(self._active_tasks.items()):
            handle = None
            if self._process_registry is not None:
                handle = self._process_registry.get_handle(block_id)
            if handle is not None:
                try:
                    handle.terminate()
                except Exception:
                    logger.exception(
                        "Shutdown: failed to terminate process for block %s",
                        block_id,
                    )
            if not task.done():
                task.cancel()
                # Shutdown path: swallow any exception (including the
                # ``CancelledError`` raised by ``task.cancel()``) so the
                # original exception that triggered ``finally`` is not
                # masked.
                with contextlib.suppress(BaseException):
                    await task

    async def pause(self) -> None:
        """Request a graceful pause after current blocks complete."""
        self._paused = True

    async def _drain_active_tasks(self) -> None:
        """Await all dispatched tasks, including any successors they trigger.

        Used by callers that do not otherwise wait on
        ``self._completed_event`` (``resume``, ``reset_block``) but must
        still block until the tasks they just scheduled have finished.
        A snapshot is awaited in each iteration because ``_on_block_done``
        can add new entries to ``_active_tasks`` while we wait.
        """
        while self._active_tasks:
            tasks = list(self._active_tasks.values())
            await asyncio.gather(*tasks, return_exceptions=True)

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

    async def _cancel_if_active(self, block_id: str) -> None:
        """Cancel the active task/subprocess for *block_id* if one exists.

        This is the pre-reset counterpart of ``_on_cancel_block``: it
        terminates the subprocess handle (when present) or cancels the
        asyncio task, then awaits its completion so the task entry is
        removed from ``_active_tasks`` before the caller re-dispatches
        the block.  Introduced to fix #424 — rerunning a RUNNING block
        must kill the previous subprocess first.
        """
        if self._block_states.get(block_id) != BlockState.RUNNING:
            return
        task = self._active_tasks.get(block_id)
        if task is None:
            return

        # Terminate subprocess if one is tracked.
        handle = None
        if self._process_registry is not None:
            handle = self._process_registry.get_handle(block_id)
        if handle is not None:
            try:
                handle.terminate()
            except Exception:
                logger.exception("Failed to terminate subprocess for block %s during rerun", block_id)

        # Always cancel the asyncio task so _run_and_finalize can unwind.
        # When a subprocess handle is present, terminate() sends SIGTERM to
        # the worker but the wrapping asyncio task still needs cancellation
        # to stop awaiting the (now-dead) process (#424).
        if not task.done():
            task.cancel()

        if hasattr(self._runner, "cancel"):
            try:
                await self._runner.cancel(block_id)
            except Exception:
                logger.exception("Failed to cancel block %s via runner during rerun", block_id)

        # Yield once so the event loop can deliver the CancelledError into
        # the task coroutine, then await completion.
        await asyncio.sleep(0)
        with contextlib.suppress(asyncio.CancelledError, TimeoutError, Exception):
            await task
        # Ensure the task entry is removed (normally done by _run_and_finalize).
        self._active_tasks.pop(block_id, None)

        logger.info("Cancelled active block %s before rerun", block_id)

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

    def _reset_upstream(self, block_id: str, visited: set[str]) -> None:
        """Recursively reset non-DONE upstream blocks to IDLE."""
        if block_id in visited:
            return
        visited.add(block_id)
        predecessors = self._dag.reverse_adjacency.get(block_id, [])
        for pred in predecessors:
            if self._block_states[pred] != BlockState.DONE:
                self._block_states[pred] = BlockState.IDLE
                self._block_outputs.pop(pred, None)
                self.skip_reasons.pop(pred, None)
                self._reset_upstream(pred, visited)

    def _reset_downstream_skipped(self, block_id: str) -> None:
        """Breadth-first reset of downstream SKIPPED blocks."""
        queue = list(self._dag.adjacency.get(block_id, []))
        visited: set[str] = set()
        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            if self._block_states[node_id] == BlockState.SKIPPED:
                self._block_states[node_id] = BlockState.IDLE
                self._block_outputs.pop(node_id, None)
                self.skip_reasons.pop(node_id, None)
                queue.extend(self._dag.adjacency.get(node_id, []))

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

    def _ancestors_of(self, block_id: str) -> set[str]:
        """Return all upstream nodes for *block_id*."""
        visited: set[str] = set()
        queue = list(self._dag.reverse_adjacency.get(block_id, []))
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            queue.extend(self._dag.reverse_adjacency.get(current, []))
        return visited

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
