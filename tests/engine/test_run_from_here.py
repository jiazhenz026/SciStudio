"""#2448: "Run from here" reuses only upstream outputs it can prove are current."""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.engine.checkpoint import (
    CHECKPOINT_FORMAT_VERSION,
    CheckpointManager,
    WorkflowCheckpoint,
    load_checkpoint,
    save_checkpoint,
)
from scistudio.engine.dag import build_dag
from scistudio.engine.events import EventBus
from scistudio.engine.run_from_here import (
    REASON_DEFINITION_CHANGED,
    REASON_DEFINITION_UNKNOWN,
    REASON_NEVER_RAN,
    REASON_OUTPUT_MISSING,
    RunFromHereRefusedError,
    definition_fingerprints,
    lineage_fingerprints,
    plan_run_from_here,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition


def _wf(nodes: dict[str, dict[str, Any]], edges: list[tuple[str, str]]) -> WorkflowDefinition:
    return WorkflowDefinition(
        id="wf",
        nodes=[
            NodeDef(id=node_id, block_type="proc", config=copy.deepcopy(config)) for node_id, config in nodes.items()
        ],
        edges=[EdgeDef(source=source, target=target) for source, target in edges],
    )


def _linear() -> WorkflowDefinition:
    return _wf(
        {"A": {"params": {"k": 1}}, "B": {"params": {"k": 2}}, "C": {"params": {"k": 3}}},
        [("A:out", "B:in"), ("B:out", "C:in")],
    )


def _checkpoint(
    workflow: WorkflowDefinition,
    tmp_path: Path,
    *,
    ran: list[str] | None = None,
    with_fingerprints: bool = True,
) -> WorkflowCheckpoint:
    """A checkpoint as a full run of *workflow* would leave it, with real data files."""
    dag = build_dag(workflow)
    ran = ran if ran is not None else list(dag.nodes)
    refs: dict[str, Any] = {}
    for node_id in ran:
        data = tmp_path / f"{node_id}.parquet"
        data.write_text("x", encoding="utf-8")
        refs[node_id] = {"out": {"backend": "arrow", "path": str(data), "format": "parquet", "metadata": {}}}
    definitions = definition_fingerprints(workflow, dag=dag)
    lineage = lineage_fingerprints(dag, definitions)
    fingerprints = (
        {node_id: {"definition": definitions[node_id], "lineage": lineage[node_id]} for node_id in ran}
        if with_fingerprints
        else {}
    )
    return WorkflowCheckpoint(
        workflow_id=workflow.id,
        timestamp=datetime(2026, 9, 15),
        block_states={node_id: "done" for node_id in ran},
        intermediate_refs=refs,
        node_fingerprints=fingerprints,
    )


def _refusal(workflow: WorkflowDefinition, block_id: str, checkpoint: WorkflowCheckpoint | None) -> dict[str, Any]:
    with pytest.raises(RunFromHereRefusedError) as info:
        plan_run_from_here(workflow, block_id, checkpoint)
    return {item.node_id: item for item in info.value.unmet}


# ---------------------------------------------------------------------------
# Planning rules
# ---------------------------------------------------------------------------


def test_target_without_upstream_runs_without_a_checkpoint() -> None:
    plan = plan_run_from_here(_linear(), "A", None)
    assert plan.run_set == {"A", "B", "C"}
    assert plan.required == frozenset()
    assert plan.reused == frozenset()


def test_unchanged_upstream_with_existing_data_is_reused(tmp_path: Path) -> None:
    workflow = _linear()
    plan = plan_run_from_here(workflow, "C", _checkpoint(workflow, tmp_path))
    assert plan.run_set == {"C"}
    assert plan.required == {"B"}
    assert plan.reused == {"A", "B"}


def test_never_ran_without_checkpoint(tmp_path: Path) -> None:
    unmet = _refusal(_linear(), "C", None)
    assert list(unmet) == ["B"]
    assert unmet["B"].reason == REASON_NEVER_RAN


def test_never_ran_when_checkpoint_lacks_the_output(tmp_path: Path) -> None:
    workflow = _linear()
    unmet = _refusal(workflow, "C", _checkpoint(workflow, tmp_path, ran=["A"]))
    assert unmet["B"].reason == REASON_NEVER_RAN


def test_output_missing_when_data_file_was_deleted(tmp_path: Path) -> None:
    workflow = _linear()
    checkpoint = _checkpoint(workflow, tmp_path)
    (tmp_path / "B.parquet").unlink()
    unmet = _refusal(workflow, "C", checkpoint)
    assert unmet["B"].reason == REASON_OUTPUT_MISSING
    assert "B.parquet" in unmet["B"].detail


def test_definition_changed_on_the_required_block(tmp_path: Path) -> None:
    workflow = _linear()
    checkpoint = _checkpoint(workflow, tmp_path)
    workflow.nodes[1].config["params"]["k"] = 99
    unmet = _refusal(workflow, "C", checkpoint)
    assert unmet["B"].reason == REASON_DEFINITION_CHANGED


def test_definition_changed_further_upstream_names_the_changed_block(tmp_path: Path) -> None:
    workflow = _linear()
    checkpoint = _checkpoint(workflow, tmp_path)
    workflow.nodes[0].config["params"]["k"] = 99
    unmet = _refusal(workflow, "C", checkpoint)
    assert unmet["B"].reason == REASON_DEFINITION_CHANGED
    assert "A" in unmet["B"].detail


def test_old_checkpoint_without_fingerprints_is_definition_unknown(tmp_path: Path) -> None:
    workflow = _linear()
    unmet = _refusal(workflow, "C", _checkpoint(workflow, tmp_path, with_fingerprints=False))
    assert unmet["B"].reason == REASON_DEFINITION_UNKNOWN


def test_descendant_other_branch_inputs_are_checked(tmp_path: Path) -> None:
    """T -> D <- S: running from T needs S's output even though S is not T's ancestor."""
    workflow = _wf(
        {"R": {}, "T": {}, "S": {}, "D": {}},
        [("R:out", "T:in"), ("T:out", "D:left"), ("S:out", "D:right")],
    )
    checkpoint = _checkpoint(workflow, tmp_path, ran=["R", "T", "D"])
    unmet = _refusal(workflow, "T", checkpoint)
    assert list(unmet) == ["S"]
    assert unmet["S"].reason == REASON_NEVER_RAN

    ok = plan_run_from_here(workflow, "T", _checkpoint(workflow, tmp_path))
    assert ok.required == {"R", "S"}


def test_every_unmet_block_is_listed(tmp_path: Path) -> None:
    workflow = _wf({"X": {}, "Y": {}, "Z": {}}, [("X:out", "Z:a"), ("Y:out", "Z:b")])
    checkpoint = _checkpoint(workflow, tmp_path)
    (tmp_path / "X.parquet").unlink()
    workflow.nodes[1].config["params"] = {"k": 5}
    unmet = _refusal(workflow, "Z", checkpoint)
    assert {node_id: item.reason for node_id, item in unmet.items()} == {
        "X": REASON_OUTPUT_MISSING,
        "Y": REASON_DEFINITION_CHANGED,
    }


def test_unknown_block_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown block"):
        plan_run_from_here(_linear(), "nope", None)


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------


def test_fingerprint_ignores_label_overwrite_and_interactive_memory() -> None:
    base = _linear()
    before = definition_fingerprints(base)
    edited = _linear()
    edited.nodes[1].config["label"] = "renamed"
    edited.nodes[1].config["interactive_memory"] = {"enabled": True}
    edited.nodes[1].config["params"]["overwrite"] = True
    edited.nodes[1].config["params"]["interactive_memory"] = {"enabled": True}
    assert definition_fingerprints(edited) == before


def test_fingerprint_changes_with_block_type_params_and_wiring() -> None:
    before = definition_fingerprints(_linear())

    retyped = _linear()
    retyped.nodes[1].block_type = "other"
    assert definition_fingerprints(retyped)["B"] != before["B"]

    rewired = _linear()
    rewired.edges[0] = EdgeDef(source="A:other_port", target="B:in")
    assert definition_fingerprints(rewired)["B"] != before["B"]


def test_fingerprint_includes_registry_block_version() -> None:
    def registry(version: str) -> Any:
        reg = MagicMock()
        reg.get_spec.return_value = MagicMock(version=version)
        return reg

    workflow = _linear()
    assert definition_fingerprints(workflow, registry=registry("1.0")) != definition_fingerprints(
        workflow, registry=registry("2.0")
    )


def test_checkpoint_round_trips_fingerprints_and_tolerates_old_and_new_files(tmp_path: Path) -> None:
    workflow = _linear()
    checkpoint = _checkpoint(workflow, tmp_path)
    path = tmp_path / "cp.json"
    save_checkpoint(checkpoint, path)
    loaded = load_checkpoint(path)
    assert loaded.node_fingerprints == checkpoint.node_fingerprints
    assert loaded.version == CHECKPOINT_FORMAT_VERSION == 2

    raw = json.loads(path.read_text())
    raw.pop("node_fingerprints")
    raw["version"] = 1
    raw["field_from_a_newer_release"] = True
    path.write_text(json.dumps(raw))
    legacy = load_checkpoint(path)
    assert legacy.node_fingerprints == {}
    assert legacy.version == 1


# ---------------------------------------------------------------------------
# Scheduler integration
# ---------------------------------------------------------------------------


def _scheduler(workflow: WorkflowDefinition, tmp_path: Path, outputs: dict[str, Any]) -> tuple[DAGScheduler, AsyncMock]:
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None
    runner = AsyncMock()

    async def run(block: Any, inputs: Any, config: Any, **_: Any) -> dict[str, Any]:
        return outputs[block.id]

    runner.run.side_effect = run
    scheduler = DAGScheduler(
        workflow=workflow,
        event_bus=EventBus(),
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        checkpoint_manager=CheckpointManager(tmp_path / "pause"),
    )
    return scheduler, runner


def _outputs(tmp_path: Path, node_ids: list[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for node_id in node_ids:
        data = tmp_path / f"{node_id}.zarr"
        data.mkdir(exist_ok=True)
        result[node_id] = {"out": {"backend": "zarr", "path": str(data), "format": "zarr", "metadata": {}}}
    return result


def test_full_run_records_fingerprints_that_permit_run_from_here(tmp_path: Path) -> None:
    workflow = _linear()
    outputs = _outputs(tmp_path, ["A", "B", "C"])
    scheduler, _ = _scheduler(workflow, tmp_path, outputs)
    asyncio.run(scheduler.execute())

    saved = CheckpointManager(tmp_path / "pause").load("wf")
    assert saved is not None
    assert set(saved.node_fingerprints) == {"A", "B", "C"}

    rerun, runner = _scheduler(copy.deepcopy(workflow), tmp_path, outputs)
    asyncio.run(rerun.execute_from("C"))
    assert [call.args[0].id for call in runner.run.call_args_list] == ["C"]
    assert rerun.block_states()["C"] == BlockState.DONE

    # The reused outputs keep their recorded fingerprints in the new checkpoint.
    again = CheckpointManager(tmp_path / "pause").load("wf")
    assert again is not None
    assert again.node_fingerprints["B"] == saved.node_fingerprints["B"]


def test_scheduler_runs_a_root_target_with_no_checkpoint_and_other_blocks_idle(tmp_path: Path) -> None:
    """A dependency-free target runs; blocks outside the run never hold it open."""
    workflow = _wf({"A": {}, "B": {}, "N": {}}, [("A:out", "B:in")])
    scheduler, runner = _scheduler(workflow, tmp_path, _outputs(tmp_path, ["A", "B", "N"]))

    asyncio.run(asyncio.wait_for(scheduler.execute_from("N"), timeout=5))

    assert [call.args[0].id for call in runner.run.call_args_list] == ["N"]
    assert scheduler.block_states()["N"] == BlockState.DONE


def test_scheduler_refuses_stale_upstream_without_dispatching(tmp_path: Path) -> None:
    workflow = _linear()
    outputs = _outputs(tmp_path, ["A", "B", "C"])
    scheduler, _ = _scheduler(workflow, tmp_path, outputs)
    asyncio.run(scheduler.execute())

    edited = copy.deepcopy(workflow)
    edited.nodes[0].config["params"]["k"] = 42
    rerun, runner = _scheduler(edited, tmp_path, outputs)
    with pytest.raises(RunFromHereRefusedError) as info:
        asyncio.run(rerun.execute_from("C"))
    assert [(item.node_id, item.reason) for item in info.value.unmet] == [("B", REASON_DEFINITION_CHANGED)]
    runner.run.assert_not_called()


def test_output_reused_without_a_record_is_never_laundered(tmp_path: Path) -> None:
    """An output reused from an old checkpoint keeps an unknown definition in the next checkpoint."""
    workflow = _wf({"A": {}, "N": {}}, [])
    outputs = _outputs(tmp_path, ["A", "N"])
    old = WorkflowCheckpoint(
        workflow_id="wf",
        timestamp=datetime(2026, 9, 15),
        block_states={"A": "done", "N": "done"},
        intermediate_refs={"A": outputs["A"], "N": outputs["N"]},
    )
    CheckpointManager(tmp_path / "pause").save(old)

    scheduler, _ = _scheduler(workflow, tmp_path, outputs)
    asyncio.run(scheduler.execute_from("N"))

    saved = CheckpointManager(tmp_path / "pause").load("wf")
    assert saved is not None
    assert "A" not in saved.node_fingerprints
    assert "N" in saved.node_fingerprints
