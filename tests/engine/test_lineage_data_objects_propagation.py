"""Regression: scheduler run populates ``data_objects`` + ``block_io`` rows.

ADR-038 §6 Phase 2 (Phase D38-2.3) acceptance test for #929: a real
:class:`~scieasy.engine.scheduler.DAGScheduler` run with a one-block
workflow and a wired :class:`~scieasy.core.lineage.LineageRecorder` must
populate

* at least one row in ``data_objects`` (the produced object identity), and
* at least one row in ``block_io`` (the port → object_id edge),

with ``block_io.block_execution_id`` matching the recorder-allocated
``block_executions.block_execution_id``.

This was the failure mode pre-D38-2.3: the legacy
``_persist_output_metadata`` wrote to ``metadata.db`` and the new
``lineage.db`` stayed empty for ``data_objects``. The fix routes both
writes through the unified :class:`LineageStore`.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from scieasy.core.lineage.record import RunRecord
from scieasy.core.lineage.recorder import LineageRecorder
from scieasy.core.lineage.store import LineageStore
from scieasy.engine.events import EventBus
from scieasy.engine.scheduler import DAGScheduler
from scieasy.workflow.definition import NodeDef, WorkflowDefinition


def _wire_dict(object_id: str, type_chain: list[str] | None = None) -> dict[str, Any]:
    """Build a wire-format dict that mirrors the worker subprocess envelope."""
    if type_chain is None:
        type_chain = ["Image", "Array", "DataObject"]
    return {
        "backend": "zarr",
        "path": f"/data/zarr/{object_id}.zarr",
        "format": None,
        "metadata": {
            "type_chain": type_chain,
            "framework": {
                "object_id": object_id,
                "derived_from": None,
                "created_at": "2026-05-15T12:00:00+00:00",
                "source": "",
                "lineage_id": None,
            },
            "meta": None,
            "user": {},
        },
    }


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def lineage_store() -> LineageStore:
    store = LineageStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def recorder(event_bus: EventBus, lineage_store: LineageStore) -> LineageRecorder:
    run_id = "run-d38-2-3-regression"
    lineage_store.insert_run(
        RunRecord(
            run_id=run_id,
            workflow_id="wf-regression",
            workflow_yaml_snapshot="",
            started_at="2026-05-15T12:00:00",
            status="running",
            environment_snapshot={},
        )
    )
    return LineageRecorder(event_bus, lineage_store=lineage_store, run_id=run_id)


def _make_scheduler(
    workflow: WorkflowDefinition,
    event_bus: EventBus,
    runner_return: dict[str, Any],
    recorder: LineageRecorder,
) -> DAGScheduler:
    resource_manager = MagicMock()
    resource_manager.can_dispatch.return_value = True
    process_registry = MagicMock()
    process_registry.get_handle.return_value = None

    runner = AsyncMock()
    runner.run.return_value = runner_return

    return DAGScheduler(
        workflow=workflow,
        event_bus=event_bus,
        resource_manager=resource_manager,
        process_registry=process_registry,
        runner=runner,
        lineage_recorder=recorder,
    )


class TestDataObjectsBlockIoPropagation:
    """ADR-038 §6 Phase 2 acceptance: a scheduler run populates both tables."""

    def test_single_block_run_populates_data_objects_and_block_io(
        self,
        event_bus: EventBus,
        lineage_store: LineageStore,
        recorder: LineageRecorder,
    ) -> None:
        wire = _wire_dict("regression-obj-1")
        workflow = WorkflowDefinition(
            id="wf-regression",
            nodes=[NodeDef(id="A", block_type="proc")],
            edges=[],
        )
        scheduler = _make_scheduler(
            workflow=workflow,
            event_bus=event_bus,
            runner_return={"out": wire},
            recorder=recorder,
        )

        asyncio.run(scheduler.execute())

        # ── data_objects ─────────────────────────────────────────────
        row = lineage_store.get_data_object("regression-obj-1")
        assert row is not None, "recorder must upsert a data_objects row"
        assert row["type_name"] == "Image"
        assert row["storage_path"] == "/data/zarr/regression-obj-1.zarr"

        # ── block_io ─────────────────────────────────────────────────
        execs = lineage_store.list_block_executions("run-d38-2-3-regression")
        assert len(execs) == 1, "recorder must insert exactly one block_executions row"
        block_execution_id = execs[0]["block_execution_id"]

        io_rows = lineage_store.list_block_io(block_execution_id)
        output_edges = [r for r in io_rows if r["direction"] == "output"]
        assert output_edges, "recorder must insert ≥1 output block_io row"

        # block_io edge points at the same object_id (FK invariant —
        # block_io.object_id → data_objects.object_id).
        assert output_edges[0]["object_id"] == "regression-obj-1"
        assert output_edges[0]["port_name"] == "out"

        # Codex P1 #931 regression: ``produced_by_execution`` must be the
        # recorder-allocated ``block_execution_id`` (not NULL). The
        # pre-Codex-fix bug pre-upserted with ``produced_by_execution=None``
        # and ``INSERT OR IGNORE`` made the recorder's later write a no-op,
        # leaving the producer FK permanently NULL.
        assert row["produced_by_execution"] == block_execution_id, (
            "data_objects.produced_by_execution must match the recorder-allocated "
            "block_execution_id (regression for Codex P1 on #931)"
        )

    def test_collection_outputs_unroll_into_multiple_rows(
        self,
        event_bus: EventBus,
        lineage_store: LineageStore,
        recorder: LineageRecorder,
    ) -> None:
        """ADR-038 §3.1 Collection unrolling — one row per item."""
        items = [_wire_dict(f"coll-item-{i}") for i in range(3)]
        runner_return = {
            "images": {
                "_collection": True,
                "items": items,
                "item_type": "Image",
            }
        }
        workflow = WorkflowDefinition(
            id="wf-collection",
            nodes=[NodeDef(id="B", block_type="proc")],
            edges=[],
        )
        scheduler = _make_scheduler(
            workflow=workflow,
            event_bus=event_bus,
            runner_return=runner_return,
            recorder=recorder,
        )

        asyncio.run(scheduler.execute())

        # Each item should have its own data_objects row.
        for i in range(3):
            assert lineage_store.get_data_object(f"coll-item-{i}") is not None

        execs = lineage_store.list_block_executions("run-d38-2-3-regression")
        assert len(execs) == 1
        block_execution_id = execs[0]["block_execution_id"]
        io_rows = lineage_store.list_block_io(block_execution_id)
        output_edges = [r for r in io_rows if r["direction"] == "output"]
        assert len(output_edges) == 3, "Collection of 3 items → 3 block_io rows"
        assert {r["position"] for r in output_edges} == {0, 1, 2}
