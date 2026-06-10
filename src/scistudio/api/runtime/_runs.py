"""Workflow execution + lineage method implementations.

Issue #1430 / umbrella #1427: behavior unchanged.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from datetime import UTC
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import yaml

from scistudio.engine.checkpoint import CheckpointManager
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import WorkflowDefinition

from ._helpers import _now_iso

if TYPE_CHECKING:
    from . import ApiRuntime, WorkflowRun

logger = logging.getLogger(__name__)


def _ancestors_of(self: ApiRuntime, workflow: WorkflowDefinition, block_id: str) -> set[str]:
    from scistudio.engine.dag import build_dag

    dag = build_dag(workflow)
    visited: set[str] = set()
    queue = list(dag.reverse_adjacency.get(block_id, []))
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        queue.extend(dag.reverse_adjacency.get(current, []))
    return visited


def checkpoint_dir_for(self: ApiRuntime, workflow_id: str) -> Path:
    """Return the per-workflow pause/resume checkpoint directory.

    Per ADR-038 §5.2 (Phase D38-2.3) the checkpoint files relocate
    from ``<project>/checkpoints/<workflow_id>/`` to
    ``<project>/.scistudio/pause/<workflow_id>/``.
    """
    project = self.require_active_project()
    return Path(project.path) / ".scistudio" / "pause" / workflow_id


def _build_lineage_recorder(
    self: ApiRuntime,
    *,
    workflow_id: str,
    workflow: WorkflowDefinition,
    execute_from: str | None,
    parent_run_id: str | None = None,
    workflow_git_commit: str | None = None,
    workflow_dirty: bool = False,
) -> Any:
    """Construct a per-run :class:`LineageRecorder` and seed its ``runs`` row.

    Returns ``None`` when the lineage store is unavailable.
    """
    if self.lineage_store is None:
        return None
    try:
        from scistudio.core.lineage.environment import EnvironmentSnapshot
        from scistudio.core.lineage.record import RunRecord
        from scistudio.core.lineage.recorder import LineageRecorder

        run_id = uuid4().hex
        workflow_yaml_snapshot = self._serialise_workflow_snapshot(workflow_id, workflow)
        env_snapshot = EnvironmentSnapshot.capture(full=True).to_dict()
        triggered_by = "execute_from" if execute_from is not None else "user"
        run = RunRecord(
            run_id=run_id,
            workflow_id=workflow_id,
            workflow_yaml_snapshot=workflow_yaml_snapshot,
            started_at=_now_iso(),
            status="running",
            environment_snapshot=env_snapshot,
            triggered_by=triggered_by,
            execute_from_block_id=execute_from,
            parent_run_id=parent_run_id,
            workflow_git_commit=workflow_git_commit,
            workflow_dirty=1 if workflow_dirty else 0,
        )
        recorder = LineageRecorder(self.event_bus, self.lineage_store, run_id=run_id)
        recorder.begin_run(run)
        return recorder
    except Exception:
        logger.warning("ADR-038: failed to construct LineageRecorder (non-fatal)", exc_info=True)
        return None


def _serialise_workflow_snapshot(self: ApiRuntime, workflow_id: str, workflow: WorkflowDefinition) -> str:
    """Return the on-disk workflow YAML, falling back to a re-serialisation."""
    try:
        path = self.workflow_path(workflow_id)
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception:
        logger.debug("ADR-038: workflow yaml snapshot disk read failed", exc_info=True)
    try:
        return yaml.safe_dump(
            {
                "id": workflow.id,
                "nodes": [{"id": n.id, "block_type": n.block_type, "config": n.config} for n in workflow.nodes],
                "edges": [{"source": e.source, "target": e.target} for e in workflow.edges],
            },
            default_flow_style=False,
            sort_keys=False,
        )
    except Exception:
        return ""


def _derive_lineage_run_status(
    self: ApiRuntime,
    scheduler: DAGScheduler,
    task: asyncio.Task[None],
) -> str:
    """Return the ADR-038 ``runs.status`` for a finished workflow task."""
    if task.cancelled():
        return "cancelled"

    exc = task.exception()
    if exc is not None:
        return "failed"

    state_values = {str(getattr(state, "value", state)) for state in scheduler.block_states().values()}
    if "error" in state_values:
        return "failed"
    if "cancelled" in state_values:
        return "cancelled"
    return "completed"


def _finalize_lineage_run(
    self: ApiRuntime,
    recorder: Any,
    task: asyncio.Task[None],
    scheduler: DAGScheduler,
) -> None:
    """Update the ``runs`` row when the workflow task finishes.

    #1527 (BUG-6): ``recorder.finalize_run`` now persists the recorder's
    accumulated ``provenance_degraded`` latch onto the ``runs`` row, so a run
    whose lineage / block_io writes silently failed can no longer be read
    back as a clean "completed". We additionally emit a warning here when the
    derived status would otherwise be a clean completion but provenance is
    degraded, so the loss is visible in logs and not only in the DB column.
    """
    try:
        status = self._derive_lineage_run_status(scheduler, task)
        if getattr(recorder, "provenance_degraded", False):
            logger.warning(
                "ADR-038/#1527: run %s finished with status=%s but one or more "
                "provenance writes failed; runs.provenance_degraded will be set.",
                getattr(recorder, "run_id", "<unknown>"),
                status,
            )
        recorder.finalize_run(status=status)
    except Exception:
        logger.debug("ADR-038: lineage run finalisation failed", exc_info=True)
    try:
        recorder.dispose()
    except Exception:
        logger.debug("ADR-038: lineage recorder dispose failed", exc_info=True)


def start_workflow(
    self: ApiRuntime,
    workflow_id: str,
    *,
    execute_from: str | None = None,
    parent_run_id: str | None = None,
    overwrite_node_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Schedule a workflow run.

    D38-3.2 (closes D38-3.1a P2 / D38-3.1b P2-4): ``parent_run_id``
    is a new optional parameter used by the ``/api/runs/{run_id}/rerun``
    endpoint to stamp the new run's ``runs.parent_run_id`` column
    pointing at the historical run that triggered the rerun.

    Phase 3.5 integration: also drives the ADR-039 §3.4 pre-run
    auto-commit path. The captured SHA + the post-commit dirty
    flag are threaded into :func:`_build_lineage_recorder` so the
    ADR-038 ``runs`` row carries ``workflow_git_commit`` /
    ``workflow_dirty`` at INSERT time.
    """
    from . import WorkflowRun

    # ADR-039 §3.4 pre-run auto-commit
    workflow_git_commit: str | None = None
    workflow_dirty: bool = False
    try:
        if self.active_project is not None:
            from datetime import datetime

            from scistudio.core.versioning.git_engine import GitEngine

            project_path = Path(self.active_project.path)
            engine = GitEngine(project_path)
            if engine.is_repository(project_path):
                state = engine.head_state()
                if state.dirty:
                    short_id = uuid4().hex[:8]
                    ts = datetime.now(UTC).isoformat()
                    msg = f"pre-run @ {ts} (run={short_id}, workflow={workflow_id})"
                    try:
                        new_sha = engine.commit(msg, prefix="auto")
                        workflow_git_commit = new_sha
                        workflow_dirty = False
                    except Exception:
                        # Codex P1 on PR #959: when the dirty-tree
                        # auto-commit fails we MUST NOT fall back to
                        # the prior HEAD SHA.
                        logger.warning(
                            "ADR-039: pre-run auto-commit failed for %s — "
                            "treating run as degraded (workflow_git_commit=None, "
                            "workflow_dirty=1)",
                            workflow_id,
                            exc_info=True,
                        )
                        workflow_git_commit = None
                        workflow_dirty = True
                else:
                    workflow_git_commit = state.commit_sha or None
                    workflow_dirty = False
    except Exception:
        logger.warning(
            "ADR-039: pre-run auto-commit path errored for %s",
            workflow_id,
            exc_info=True,
        )

    if workflow_git_commit:
        logger.debug(
            "ADR-039: captured workflow_git_commit=%s for workflow %s (workflow_dirty=%s)",
            workflow_git_commit,
            workflow_id,
            workflow_dirty,
        )

    workflow = self.load_workflow(workflow_id)

    # #1518 (DSN-2): ``start_workflow`` previously scheduled the run without
    # ever calling ``validate_workflow``, so a graph that bypassed save-time
    # validation (e.g. an externally edited YAML, or one saved before #1518)
    # would fail deep inside a block at run time instead of being rejected up
    # front. Re-run validation on the loaded definition and refuse to start
    # on a hard error. ``"Warning:"``-prefixed diagnostics (unknown block
    # type / missing port) remain non-fatal, matching ``save_workflow``.
    from scistudio.workflow.validator import validate_workflow

    diagnostics = validate_workflow(workflow, registry=self.block_registry)
    hard_errors = [d for d in diagnostics if not str(d).startswith("Warning:")]
    if hard_errors:
        raise ValueError("Cannot start workflow; validation failed: " + "; ".join(str(e) for e in hard_errors))

    if overwrite_node_ids:
        workflow = copy.deepcopy(workflow)
        for node in workflow.nodes:
            if node.id in overwrite_node_ids:
                params = node.config.setdefault("params", {})
                if isinstance(params, dict):
                    params["overwrite"] = True
    checkpoint_manager = CheckpointManager(self.checkpoint_dir_for(workflow_id))
    checkpoint = checkpoint_manager.load(workflow_id) if execute_from is not None else None
    if execute_from is not None and checkpoint is None:
        raise ValueError("Run the full workflow at least once before using 'Run from here'")

    lineage_recorder = self._build_lineage_recorder(
        workflow_id=workflow_id,
        workflow=workflow,
        execute_from=execute_from,
        parent_run_id=parent_run_id,
        workflow_git_commit=workflow_git_commit,
        workflow_dirty=workflow_dirty,
    )

    scheduler = DAGScheduler(
        workflow=workflow,
        event_bus=self.event_bus,
        resource_manager=self.resource_manager,
        process_registry=self.process_registry,
        runner=self.runner,
        registry=self.block_registry,
        checkpoint_manager=checkpoint_manager,
        lineage_recorder=lineage_recorder,
        project_dir=str(self.active_project.path) if self.active_project else None,
    )

    async def _run() -> None:
        if execute_from is not None:
            await self.log_broadcaster.publish(
                level="info",
                message=f"execute from {execute_from}",
                workflow_id=workflow_id,
            )
            await scheduler.execute_from(execute_from)
        else:
            await self.log_broadcaster.publish(
                level="info",
                message="workflow execution started",
                workflow_id=workflow_id,
            )
            await scheduler.execute()

    task = asyncio.create_task(_run())
    task.add_done_callback(lambda finished: asyncio.create_task(self._log_workflow_task_failure(workflow_id, finished)))
    if lineage_recorder is not None:
        recorder_for_callback = lineage_recorder

        def _on_done(finished: asyncio.Task[None]) -> None:
            self._finalize_lineage_run(recorder_for_callback, finished, scheduler)

        task.add_done_callback(_on_done)
    self.workflow_runs[workflow_id] = WorkflowRun(
        scheduler=scheduler,
        task=task,
        checkpoint_manager=checkpoint_manager,
        workflow_git_commit=workflow_git_commit,
    )

    reused_blocks: list[str] = []
    if execute_from is not None:
        reused_blocks = sorted(self._ancestors_of(workflow, execute_from))

    reset_blocks = sorted(set(node.id for node in workflow.nodes) - set(reused_blocks))
    return {
        "workflow_id": workflow_id,
        "status": "started",
        "message": "Workflow execution has been scheduled.",
        "reused_blocks": reused_blocks,
        "reset_blocks": reset_blocks,
    }


async def _log_workflow_task_failure(self: ApiRuntime, workflow_id: str, task: asyncio.Task[None]) -> None:
    """Surface unexpected workflow task failures to logs and SSE clients."""
    if task.cancelled():
        return
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is None:
        return
    logger.error(
        "Workflow %s task failed: %s",
        workflow_id,
        exc,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    await self.log_broadcaster.publish(
        level="error",
        message=str(exc),
        workflow_id=workflow_id,
    )


def get_run(self: ApiRuntime, workflow_id: str) -> WorkflowRun:
    if workflow_id not in self.workflow_runs:
        raise KeyError(f"Workflow is not running: {workflow_id}")
    return self.workflow_runs[workflow_id]
