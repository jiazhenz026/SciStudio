"""Block dispatch loop implementations for :class:`DAGScheduler`.

ADR-046 §3 (Block dispatch group): extracted verbatim from the
original ``engine/scheduler.py`` god-file. Pure structural move per
umbrella #1427 Phase 3 — no behavior changes. ADR-018 Addendum 1
task-per-block dispatch semantics and the #1330/#1370 ADR-020
output-normalization callsites are preserved byte-identically.

Each function is a free function whose first parameter is ``self`` —
they are bound onto :class:`DAGScheduler` in
``scheduler/__init__.py`` via class-body static assignment so griffe
emits the canonical ``scistudio.engine.scheduler.DAGScheduler.<method>``
fact (see ADR-042 + the doc/closure audit walker).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from scistudio.blocks.base.state import BlockState, ExecutionMode
from scistudio.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_PAUSED,
    BLOCK_READY,
    BLOCK_RUNNING,
    BLOCK_SKIPPED,
    INTERACTIVE_PROMPT,
    EngineEvent,
)
from scistudio.engine.resources import ResourceRequest
from scistudio.engine.runners.terminal_state import BlockTerminalStateReportedError

if TYPE_CHECKING:
    from . import DAGScheduler

logger = logging.getLogger("scistudio.engine.scheduler")


async def _emit_block_ready(self: DAGScheduler, node_id: str) -> None:
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


async def _dispatch(self: DAGScheduler, node_id: str) -> None:
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

    # TODO(#887): ADR-022 L1 GPU/CPU slot gating is not wired — this passes a
    #   default ``ResourceRequest()`` instead of the block's real request, so
    #   the discrete GPU/CPU counters never gate dispatch (only the psutil
    #   memory watermark + active-task count do). Confirmed low-risk at present
    #   per the owner decision on #887 (cloud-LLM AI blocks, chunked large
    #   data); see also #1595. Deferred until a real local-GPU contention
    #   trigger.
    if not self._resource_manager.can_dispatch(ResourceRequest(), active_count=len(self._active_tasks)):
        # Stay READY; retried by _dispatch_newly_ready on the next
        # resource-freeing event (BLOCK_DONE).
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

    # ADR-051: interactive blocks run as two worker subprocesses around an
    # engine-held pause (prompt phase builds the panel view, the engine holds
    # the wait with nothing resident, the compute phase runs with the user's
    # decision). They are no longer the in-process exception to ADR-017.
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
    self: DAGScheduler,
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
                    "Block %s reported terminal state %s from worker but was already CANCELLED; preserving CANCELLED",
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


def _release_intermediate_refs(refs: list[dict[str, Any]]) -> None:
    """Delete the on-disk scratch behind ADR-051 intermediate storage references.

    The prompt phase may persist heavy intermediate work via the storage layer
    and hand its references forward (ADR-051 §3). That work is scratch, not
    provenance: it is released after the compute phase completes or on
    cancellation. Best-effort — a missing or unreadable path is logged at debug
    and skipped; storage backends have no first-class delete, so we remove the
    referenced filesystem path directly.
    """
    import shutil
    from pathlib import Path

    for ref in refs:
        if not isinstance(ref, dict):
            continue
        raw_path = ref.get("path")
        if not raw_path or not isinstance(raw_path, str):
            continue
        try:
            target = Path(raw_path)
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink()
        except OSError:
            logger.debug("Failed to release interactive intermediate scratch %s", raw_path, exc_info=True)


async def _run_interactive(
    self: DAGScheduler,
    node_id: str,
    block: Any,
    inputs: dict[str, Any],
    config: dict[str, Any],
) -> None:
    """Execute an interactive block as two worker subprocesses around a pause (ADR-051).

    ADR-051 §3 replaces the former in-process interactive path. An interactive
    block stays as isolated as any other block even while a human is in the
    loop: it is only ever running inside a subprocess that runs to completion,
    never while paused. The flow is:

    1. **Prompt phase** (subprocess): ``block.prepare_prompt`` runs in an
       isolated worker, builds the JSON-safe panel view, and exits. Optional
       heavy intermediate work crosses the pause as engine-held storage
       references (never in memory, never to the browser).
    2. Transition to PAUSED (nothing resident); emit BLOCK_PAUSED and
       INTERACTIVE_PROMPT carrying the panel manifest (FR-007/FR-015) and the
       panel payload; await the user's decision via an asyncio.Future.
    3. **Compute phase** (fresh subprocess): on confirmation, ``block.run``
       runs in a new worker with the decision (and any intermediate references)
       merged into config. The decision is recorded in lineage; the
       intermediate scratch is released after the run (ADR-051 §3 / FR-011/FR-012).

    Cancelling while paused transitions to CANCELLED, releases any intermediate
    scratch, and spawns no compute phase (FR-012).
    """
    from scistudio.blocks.base.interactive import (
        INTERACTIVE_INTERMEDIATE_KEY,
        INTERACTIVE_RESPONSE_KEY,
    )

    intermediate: list[dict[str, Any]] = []
    try:
        try:
            # Phase 1 (subprocess): build the panel view. The block runs to
            # completion in an isolated worker (ADR-051 §3); nothing of it
            # survives into the pause.
            prompt_result = await self._runner.run_prompt(block, inputs, config)
            panel_payload = prompt_result.get("panel_payload", {}) or {}
            raw_intermediate = prompt_result.get("intermediate") or []
            intermediate = list(raw_intermediate) if isinstance(raw_intermediate, list) else []
            self._interactive_intermediate[node_id] = intermediate

            # The user may have cancelled while the build subprocess ran.
            if self._block_states.get(node_id) == BlockState.CANCELLED:
                logger.info("Interactive block %s cancelled during prompt phase", node_id)
                return

            # Transition to PAUSED: the block now waits on a human with nothing
            # resident. PAUSED is the cancellable state for the wait (ADR-018/019).
            self._block_states[node_id] = BlockState.PAUSED
            await self._event_bus.emit(
                EngineEvent(
                    event_type=BLOCK_PAUSED,
                    block_id=node_id,
                    data={"workflow_id": self._workflow.id},
                )
            )

            # Emit INTERACTIVE_PROMPT. The panel manifest lets the frontend
            # resolve the window without a hardcoded block-type branch (FR-007);
            # block_type stays for identity (FR-015). The panel payload is
            # nested (not spread) so it can never clobber the identity fields.
            manifest = block.get_panel_manifest() if hasattr(block, "get_panel_manifest") else None
            panel_manifest = manifest.to_dict() if manifest is not None else None
            await self._event_bus.emit(
                EngineEvent(
                    event_type=INTERACTIVE_PROMPT,
                    block_id=node_id,
                    data={
                        "workflow_id": self._workflow.id,
                        "block_type": config.get("block_type", type(block).__name__),
                        "panel_manifest": panel_manifest,
                        "panel_payload": panel_payload,
                    },
                )
            )

            # Await interactive_complete via a future keyed by block_id.
            loop = asyncio.get_running_loop()
            future: asyncio.Future[dict[str, Any]] = loop.create_future()
            self._interactive_futures[node_id] = future

            response_data = await future

            # Cancellation may have resolved between the await and here.
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

            # Phase 2 (fresh subprocess): compute. The decision and any
            # intermediate references are merged into config; block.run reads
            # ``interactive_response`` (and may load ``interactive_intermediate``
            # by reference). Reuses the standard subprocess run path.
            compute_config = dict(config)
            compute_config[INTERACTIVE_RESPONSE_KEY] = response_data
            if intermediate:
                compute_config[INTERACTIVE_INTERMEDIATE_KEY] = intermediate

            result = await self._runner.run(block, inputs, compute_config)

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

        # Finalize. The compute phase ran in a subprocess, so the result carries
        # the ADR-038 ``__scistudio_env__`` environment sidecar like any block.
        env_payload: dict[str, Any] | None = None
        if isinstance(result, dict) and "__scistudio_env__" in result:
            env_candidate = result.pop("__scistudio_env__")
            if isinstance(env_candidate, dict):
                env_payload = env_candidate

        # #1370: ADR-020 §3 contract enforcement. The compute worker already
        # normalises, so this is an idempotent no-op on wire-format dicts; kept
        # for parity with the in-process boundary.
        if isinstance(result, dict):
            from scistudio.engine.runners.worker import _normalize_outputs

            try:
                effective_output_ports = block.get_effective_output_ports()
            except AttributeError:
                effective_output_ports = list(getattr(type(block), "output_ports", []))
            _normalize_outputs(result, effective_output_ports)

        self._block_outputs[node_id] = result
        self._persist_output_metadata(node_id, result, self._workflow.id)
        self._block_states[node_id] = BlockState.DONE
        # ADR-051 / FR-011: record the user's decision in lineage by passing the
        # response-merged config to ``_build_block_done_data`` (the former
        # in-process path passed the pre-response config, dropping the
        # decision). ``_build_block_done_data`` excludes the ephemeral
        # ``interactive_intermediate`` scratch from the recorded config.
        lineage_config = dict(config)
        lineage_config[INTERACTIVE_RESPONSE_KEY] = response_data
        await self._event_bus.emit(
            EngineEvent(
                event_type=BLOCK_DONE,
                block_id=node_id,
                data=self._build_block_done_data(
                    node_id=node_id,
                    block=block,
                    inputs=inputs,
                    config=lineage_config,
                    outputs=result,
                    environment=env_payload,
                ),
            )
        )
        self.save_checkpoint(self._checkpoint_manager)
    finally:
        # ADR-051 §3 / FR-012: the intermediate scratch is ephemeral, not
        # provenance — release it after the run completes OR on cancellation
        # (this finally runs on success, error, and CancelledError alike).
        leftover = self._interactive_intermediate.pop(node_id, None)
        if leftover:
            _release_intermediate_refs(leftover)
        self._interactive_futures.pop(node_id, None)
        self._active_tasks.pop(node_id, None)
        self._check_completion()


def _instantiate_block(self: DAGScheduler, node_id: str) -> Any:
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


def _gather_inputs(self: DAGScheduler, node_id: str) -> dict[str, Any]:
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


async def _dispatch_newly_ready(self: DAGScheduler) -> None:
    """Dispatch blocks that became ready or were previously throttled.

    Called from ``_on_block_done`` after
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
