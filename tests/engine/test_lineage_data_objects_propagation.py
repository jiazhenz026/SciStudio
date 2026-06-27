"""Regression: scheduler run populates ``data_objects`` + ``block_io`` rows.

ADR-038 §6 Phase 2 (Phase D38-2.3) acceptance test for #929: a real
:class:`~scistudio.engine.scheduler.DAGScheduler` run with a one-block
workflow and a wired :class:`~scistudio.core.lineage.LineageRecorder` must
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

from scistudio.core.lineage.record import RunRecord
from scistudio.core.lineage.recorder import LineageRecorder
from scistudio.core.lineage.store import LineageStore
from scistudio.engine.events import EngineEvent, EventBus
from scistudio.engine.scheduler import DAGScheduler
from scistudio.workflow.definition import NodeDef, WorkflowDefinition


def _wire_dict(object_id: str, type_chain: list[str] | None = None) -> dict[str, Any]:
    """Build a wire-format dict that mirrors the worker subprocess envelope.

    Per ``scistudio.core.types.base.TypeSignature``, ``type_chain`` is ordered
    from most general to most specific (e.g. ``["DataObject", "Array",
    "FluorImage"]``). The leaf — the concrete type lineage queries care
    about — is the LAST element. Phase 3.5 Codex P1 reconcile on PR #979
    corrected ``_extract_type_name`` to read ``type_chain[-1]`` instead of
    the previous ``type_chain[0]``; the fixture default below is now
    aligned with production convention.
    """
    if type_chain is None:
        type_chain = ["DataObject", "Array", "Image"]
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

    def test_registered_collection_kind_form_types_every_item(
        self,
        event_bus: EventBus,
        lineage_store: LineageStore,
        recorder: LineageRecorder,
    ) -> None:
        """#1757: recorder must unroll the ApiRuntime-registered ``kind`` form.

        In a desktop / ApiRuntime run, ``register_output_payload`` mutates
        the BLOCK_DONE event's ``outputs`` in place, rewriting the worker's
        ``{"_collection": True, ...}`` wrapper into the data-catalog
        ``{"kind": "collection", ...}`` form — while ``output_object_ids``
        was already computed from the ``_collection`` form (N ids).

        Pre-fix, ``_wire_items_for_port`` only recognised ``_collection`` and
        returned the whole ``kind`` dict as a single item: position 0 was
        typed (via the whole-collection short-circuit) and positions 1..N-1
        fell to ``wire_dict=None`` → empty ``DataObject`` placeholders,
        losing type AND metadata for every item after the first.

        This emits the mismatched event directly (N object_ids vs the
        ``kind`` wrapper) and asserts every item is recorded with its
        concrete type and non-empty wire payload.
        """
        n = 4
        object_ids = [f"reg-item-{i}" for i in range(n)]
        registered_items = [
            {
                "data_ref": f"data-{i}",
                "type_name": "Image",
                "metadata": {
                    "type_chain": ["DataObject", "Array", "Image"],
                    "framework": {"object_id": object_ids[i]},
                    "backend": "zarr",
                    "path": f"/data/zarr/{object_ids[i]}.zarr",
                },
            }
            for i in range(n)
        ]
        event = EngineEvent(
            event_type="block_done",
            block_id="D",
            data={
                "workflow_id": "wf-regression",
                "block_type": "proc",
                "block_version": "1",
                "config": {},
                # Computed from the pre-mutation ``_collection`` form → N ids.
                "output_object_ids": {"images": list(object_ids)},
                # The ApiRuntime-mutated, data-catalog ``kind`` form.
                "outputs": {
                    "images": {
                        "kind": "collection",
                        "count": n,
                        "item_type": "Image",
                        "items": registered_items,
                    }
                },
            },
        )

        asyncio.run(event_bus.emit(event))

        # Every item — not just index 0 — keeps its concrete type and a
        # populated wire payload (no empty ``{}`` placeholder).
        for object_id in object_ids:
            row = lineage_store.get_data_object(object_id)
            assert row is not None, f"{object_id} must have a data_objects row"
            assert row["type_name"] == "Image", (
                f"{object_id} lost its type (#1757 regression: only the first "
                f"collection item was typed, the rest degraded to DataObject)"
            )
            assert row["wire_payload"] not in (None, {}, "{}"), (
                f"{object_id} must retain its metadata, not an empty placeholder"
            )

        execs = lineage_store.list_block_executions("run-d38-2-3-regression")
        assert len(execs) == 1
        io_rows = lineage_store.list_block_io(execs[0]["block_execution_id"])
        output_edges = [r for r in io_rows if r["direction"] == "output"]
        assert len(output_edges) == n, f"registered collection of {n} → {n} block_io rows"
        assert {r["position"] for r in output_edges} == set(range(n))


class TestSchedulerNoRecorderLeafType:
    """#1757: scheduler/no-recorder write path records the concrete leaf type."""

    def test_upsert_wire_row_records_leaf_not_base(self, lineage_store: LineageStore) -> None:
        """``_upsert_wire_row`` must read ``type_chain[-1]`` (concrete leaf).

        This is the scheduler-side write path used when no LineageRecorder is
        bound (CLI / direct runners that bypass ApiRuntime). It previously
        read ``type_chain[0]`` — the most general base — and recorded every
        object as the bare ``DataObject``, inconsistent with the recorder's
        ``_extract_type_name`` which already used ``type_chain[-1]``.
        """
        from scistudio.engine.scheduler import _lineage

        wire = _wire_dict("cli-obj-1", type_chain=["DataObject", "Array", "Image"])
        # ``_upsert_wire_row`` does not touch ``self``; pass None for it.
        _lineage._upsert_wire_row(None, lineage_store, wire, "node-A", "out")

        row = lineage_store.get_data_object("cli-obj-1")
        assert row is not None
        assert row["type_name"] == "Image", (
            "scheduler/no-recorder path must record the concrete leaf type, not the base DataObject (#1757)"
        )
