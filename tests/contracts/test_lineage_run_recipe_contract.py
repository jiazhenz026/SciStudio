"""Contract tests for the ADR-038 lineage run-recipe surface.

The durable reproducibility contract is the normalized lineage recipe:
``runs`` + ``block_executions`` + ``data_objects`` + ordered ``block_io``.
Checkpoint files may support pause/resume, but they are not the durable
historical run recipe.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from scistudio.core.lineage.record import RunRecord
from scistudio.core.lineage.recorder import LineageRecorder
from scistudio.core.lineage.store import LineageStore
from scistudio.engine.events import (
    BLOCK_CANCELLED,
    BLOCK_DONE,
    BLOCK_ERROR,
    BLOCK_SKIPPED,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition


def _wire_object(object_id: str, *, type_name: str = "Image") -> dict[str, Any]:
    return {
        "backend": "zarr",
        "path": f"/data/zarr/{object_id}.zarr",
        "format": None,
        "metadata": {
            "type_chain": ["DataObject", type_name],
            "framework": {
                "object_id": object_id,
                "derived_from": None,
                "created_at": "2026-05-22T12:00:00+00:00",
                "source": "",
                "lineage_id": None,
            },
            "meta": None,
            "user": {},
        },
    }


def _seed_run(
    store: LineageStore,
    *,
    run_id: str,
    workflow_id: str = "wf-lineage-contract",
    status: str = "running",
    parent_run_id: str | None = None,
) -> None:
    store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id=workflow_id,
            workflow_yaml_snapshot="nodes: []\n",
            started_at="2026-05-22T12:00:00+00:00",
            status=status,
            environment_snapshot={"python": "contract-test"},
            parent_run_id=parent_run_id,
        )
    )


class _Runner:
    def __init__(self, outputs_by_block: dict[str, dict[str, Any]]) -> None:
        self.outputs_by_block = outputs_by_block

    async def run(self, block: NodeDef, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        return self.outputs_by_block[config["block_id"]]


def _scheduler(
    *,
    workflow: WorkflowDefinition,
    event_bus: EventBus,
    recorder: LineageRecorder,
    outputs_by_block: dict[str, dict[str, Any]],
) -> DAGScheduler:
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True

    process_registry = MagicMock()
    process_registry.get_handle.return_value = None

    return DAGScheduler(
        workflow=workflow,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=_Runner(outputs_by_block),
        lineage_recorder=recorder,
    )


def test_scheduler_run_records_four_table_recipe_and_relationships() -> None:
    store = LineageStore(":memory:")
    try:
        run_id = "run-four-table-recipe"
        _seed_run(store, run_id=run_id)
        event_bus = EventBus()
        recorder = LineageRecorder(event_bus, lineage_store=store, run_id=run_id)
        workflow = WorkflowDefinition(
            id="wf-lineage-contract",
            nodes=[
                NodeDef(id="load", block_type="loader", config={"path": "input.zarr"}),
                NodeDef(id="measure", block_type="measure", config={"threshold": 0.7}),
            ],
            edges=[EdgeDef(source="load:out", target="measure:image")],
        )
        scheduler = _scheduler(
            workflow=workflow,
            event_bus=event_bus,
            recorder=recorder,
            outputs_by_block={
                "load": {"out": _wire_object("obj-load")},
                "measure": {"table": _wire_object("obj-measure", type_name="Table")},
            },
        )

        asyncio.run(scheduler.execute())
        recorder.finalize_run(status="completed")
        recorder.dispose()

        run = store.get_run(run_id)
        assert run is not None
        assert run["status"] == "completed"
        assert run["workflow_yaml_snapshot"] == "nodes: []\n"
        assert run["environment_snapshot"]

        block_rows = store.list_block_executions(run_id)
        assert [row["block_id"] for row in block_rows] == ["load", "measure"]
        assert {row["termination"] for row in block_rows} == {"completed"}

        load_exec = next(row for row in block_rows if row["block_id"] == "load")
        measure_exec = next(row for row in block_rows if row["block_id"] == "measure")
        assert store.get_data_object("obj-load")["produced_by_execution"] == load_exec["block_execution_id"]
        assert store.get_data_object("obj-measure")["produced_by_execution"] == measure_exec["block_execution_id"]

        load_edges = store.list_block_io(load_exec["block_execution_id"])
        measure_edges = store.list_block_io(measure_exec["block_execution_id"])
        assert [(edge["direction"], edge["port_name"], edge["object_id"]) for edge in load_edges] == [
            ("output", "out", "obj-load")
        ]
        assert ("input", "image", "obj-load") in {
            (edge["direction"], edge["port_name"], edge["object_id"]) for edge in measure_edges
        }
        assert ("output", "table", "obj-measure") in {
            (edge["direction"], edge["port_name"], edge["object_id"]) for edge in measure_edges
        }

        joined_edges = store.list_block_io_with_objects(run_id)
        assert {edge["object_id"] for edge in joined_edges} == {"obj-load", "obj-measure"}
    finally:
        store.close()


def test_collection_output_records_ordered_item_level_block_io_positions() -> None:
    store = LineageStore(":memory:")
    try:
        run_id = "run-collection-item-edges"
        _seed_run(store, run_id=run_id)
        event_bus = EventBus()
        recorder = LineageRecorder(event_bus, lineage_store=store, run_id=run_id)
        items = [_wire_object(f"collection-item-{position}") for position in range(3)]
        workflow = WorkflowDefinition(
            id="wf-lineage-contract",
            nodes=[NodeDef(id="split", block_type="splitter")],
            edges=[],
        )
        scheduler = _scheduler(
            workflow=workflow,
            event_bus=event_bus,
            recorder=recorder,
            outputs_by_block={
                "split": {
                    "images": {
                        "_collection": True,
                        "items": items,
                        "item_type": "Image",
                    }
                }
            },
        )

        asyncio.run(scheduler.execute())
        recorder.dispose()

        [block_row] = store.list_block_executions(run_id)
        output_edges = [
            edge
            for edge in store.list_block_io(block_row["block_execution_id"])
            if edge["direction"] == "output" and edge["port_name"] == "images"
        ]
        assert [(edge["position"], edge["object_id"]) for edge in output_edges] == [
            (0, "collection-item-0"),
            (1, "collection-item-1"),
            (2, "collection-item-2"),
        ]
        assert store.get_data_object("images") is None
    finally:
        store.close()


def test_terminal_events_distinguish_run_and_block_terminal_statuses() -> None:
    store = LineageStore(":memory:")
    try:
        run_id = "run-terminal-statuses"
        _seed_run(store, run_id=run_id)
        event_bus = EventBus()
        recorder = LineageRecorder(event_bus, lineage_store=store, run_id=run_id)

        async def emit_terminal_events() -> None:
            for event_type, block_id in [
                (BLOCK_DONE, "done-block"),
                (BLOCK_ERROR, "error-block"),
                (BLOCK_CANCELLED, "cancelled-block"),
                (BLOCK_SKIPPED, "skipped-block"),
            ]:
                recorder.record_start(block_id)
                await event_bus.emit(
                    EngineEvent(
                        event_type=event_type,
                        block_id=block_id,
                        data={
                            "workflow_id": "wf-lineage-contract",
                            "block_type": "contract_block",
                            "block_version": "1.2.3",
                            "config": {"block_id": block_id},
                            "error": "boom" if event_type == BLOCK_ERROR else "",
                            "inputs": {},
                            "input_object_ids": {},
                            "outputs": {},
                            "output_object_ids": {},
                        },
                    )
                )

        asyncio.run(emit_terminal_events())
        assert {
            row["block_id"]: row["termination"]
            for row in store.list_block_executions(run_id)
        } == {
            "done-block": "completed",
            "error-block": "error",
            "cancelled-block": "cancelled",
            "skipped-block": "skipped",
        }

        for status in ["completed", "failed", "cancelled"]:
            recorder.finalize_run(status=status)
            assert store.get_run(run_id)["status"] == status

        recorder.dispose()
    finally:
        store.close()


def test_rerun_parent_run_relationship_is_durable_in_runs_table() -> None:
    store = LineageStore(":memory:")
    try:
        _seed_run(
            store,
            run_id="run-parent",
            workflow_id="wf-lineage-contract",
            status="completed",
        )
        _seed_run(
            store,
            run_id="run-child",
            workflow_id="wf-lineage-contract",
            parent_run_id="run-parent",
        )

        child = store.get_run("run-child")
        assert child is not None
        assert child["parent_run_id"] == "run-parent"

        children = store.execute_query(
            "SELECT run_id FROM runs WHERE parent_run_id = ? ORDER BY started_at",
            ("run-parent",),
        )
        assert children == [("run-child",)]
    finally:
        store.close()
