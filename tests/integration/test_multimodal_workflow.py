"""Integration tests: full pipeline DAG, EventBus, Collection transport.

These tests exercise multiple engine subsystems together to verify that the
DAG construction, event bus, Collection transport, and block utilities work
correctly when integrated.

ADR-027 D2 / phase10-implementation-standards.md T-008 (Question 2): this
module exercises an image-typed multimodal pipeline whose ``Image`` data
type lives in the ``scistudio-blocks-imaging`` plugin package. The entire
module is therefore gated behind ``pytest.importorskip`` so that when the
plugin is not installed (the current state of the core repository) the
tests are skipped at collection time rather than failing.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

# T-008 / ADR-027 D2: skip the entire module unless the imaging plugin
# is installed. The plugin provides the typed ``Image`` class these
# tests reference; in its absence the multimodal workflow has no
# Image-typed data to flow through it.
pytest.importorskip(
    "scistudio_blocks_imaging",
    reason="requires scistudio-blocks-imaging plugin",
)

# Module-level marker so test runs can opt out of imaging-plugin tests
# via ``pytest -m "not requires_imaging"``.
pytestmark = pytest.mark.requires_imaging

# The plugin's Image type. The import below only runs when
# ``pytest.importorskip`` above succeeded.
from scistudio_blocks_imaging.types import Image  # type: ignore[import-not-found]  # noqa: E402

from scistudio.blocks.base.block import Block  # noqa: E402
from scistudio.blocks.base.state import BlockState  # noqa: E402
from scistudio.core.types.collection import Collection  # noqa: E402
from scistudio.engine.dag import build_dag, topological_sort  # noqa: E402
from scistudio.engine.events import (  # noqa: E402
    BLOCK_DONE,
    WORKFLOW_STARTED,
    EngineEvent,
    EventBus,
)
from scistudio.engine.scheduler import DAGScheduler  # noqa: E402
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition  # noqa: E402

# ---------------------------------------------------------------------------
# DAG construction + topological sort for a multimodal pipeline
# ---------------------------------------------------------------------------


class TestMultimodalDAG:
    """Build a multi-block workflow and verify DAG construction + sort."""

    def test_build_and_sort_multimodal_workflow(self) -> None:
        """Build a load->process->merge->export pipeline and verify order."""
        workflow = WorkflowDefinition(
            id="multimodal-test",
            nodes=[
                NodeDef(
                    id="load_images",
                    block_type="io_block",
                    config={"path": "/data/images"},
                ),
                NodeDef(id="process", block_type="process_block", config={}),
                NodeDef(id="merge", block_type="merge_collection", config={}),
                NodeDef(
                    id="export",
                    block_type="io_block",
                    config={"path": "/output", "direction": "output"},
                ),
            ],
            edges=[
                EdgeDef(source="load_images:data", target="process:data"),
                EdgeDef(source="process:output", target="merge:input_a"),
                EdgeDef(source="load_images:data", target="merge:input_b"),
                EdgeDef(source="merge:output", target="export:data"),
            ],
        )
        dag = build_dag(workflow)
        assert len(dag.nodes) == 4

        order = topological_sort(dag)
        assert order[0] == "load_images"  # must be first (only root)
        assert order[-1] == "export"  # must be last (only leaf)
        # process and merge must both come before export
        assert order.index("process") < order.index("export")
        assert order.index("merge") < order.index("export")

    def test_multimodal_dag_edge_map(self) -> None:
        """Verify port-level edge map is populated correctly."""
        workflow = WorkflowDefinition(
            id="edge-map-test",
            nodes=[
                NodeDef(id="load", block_type="io_block"),
                NodeDef(id="proc", block_type="process_block"),
                NodeDef(id="save", block_type="io_block"),
            ],
            edges=[
                EdgeDef(source="load:data", target="proc:input"),
                EdgeDef(source="proc:output", target="save:data"),
            ],
        )
        dag = build_dag(workflow)

        assert "proc:input" in dag.edge_map["load:data"]
        assert "save:data" in dag.edge_map["proc:output"]

    def test_multimodal_dag_reverse_adjacency(self) -> None:
        """Verify reverse adjacency for dependency tracking."""
        workflow = WorkflowDefinition(
            id="reverse-adj-test",
            nodes=[
                NodeDef(id="A", block_type="io_block"),
                NodeDef(id="B", block_type="process_block"),
                NodeDef(id="C", block_type="merge_block"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
                EdgeDef(source="A:out", target="C:in1"),
                EdgeDef(source="B:out", target="C:in2"),
            ],
        )
        dag = build_dag(workflow)

        assert dag.reverse_adjacency["A"] == []
        assert dag.reverse_adjacency["B"] == ["A"]
        assert sorted(dag.reverse_adjacency["C"]) == ["A", "B"]


# ---------------------------------------------------------------------------
# EventBus integration
# ---------------------------------------------------------------------------


class TestEventBusIntegration:
    """EventBus connects scheduler components via pub/sub."""

    def test_event_bus_multi_subscribe_emit(self) -> None:
        """EventBus delivers events to multiple subscribers of different types."""
        bus = EventBus()
        events_received: list[EngineEvent] = []

        bus.subscribe(BLOCK_DONE, lambda e: events_received.append(e))
        bus.subscribe(WORKFLOW_STARTED, lambda e: events_received.append(e))

        async def run() -> None:
            await bus.emit(EngineEvent(event_type=WORKFLOW_STARTED))
            await bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="block_1"))

        asyncio.run(run())

        assert len(events_received) == 2
        assert events_received[0].event_type == WORKFLOW_STARTED
        assert events_received[1].event_type == BLOCK_DONE
        assert events_received[1].block_id == "block_1"

    def test_event_bus_async_callback(self) -> None:
        """EventBus correctly awaits async callbacks."""
        bus = EventBus()
        results: list[str] = []

        async def async_handler(event: EngineEvent) -> None:
            results.append(f"async:{event.event_type}")

        bus.subscribe(BLOCK_DONE, async_handler)

        async def run() -> None:
            await bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="x"))

        asyncio.run(run())

        assert results == ["async:block_done"]

    def test_event_bus_error_isolation(self) -> None:
        """A failing callback does not prevent other callbacks from running."""
        bus = EventBus()
        results: list[str] = []

        def bad_handler(event: EngineEvent) -> None:
            raise RuntimeError("handler error")

        def good_handler(event: EngineEvent) -> None:
            results.append("ok")

        bus.subscribe(BLOCK_DONE, bad_handler)
        bus.subscribe(BLOCK_DONE, good_handler)

        async def run() -> None:
            await bus.emit(EngineEvent(event_type=BLOCK_DONE, block_id="x"))

        asyncio.run(run())

        assert results == ["ok"]


# ---------------------------------------------------------------------------
# Collection transport through block utilities
# ---------------------------------------------------------------------------


class TestCollectionThroughPipeline:
    """Collection transport works through Block.pack / unpack / map_items."""

    def test_pack_unpack_roundtrip(self) -> None:
        """pack() creates a Collection, unpack() extracts items."""
        imgs = [Image(shape=(i, i), ndim=2, dtype="uint8") for i in range(1, 4)]
        coll = Block.pack(imgs, item_type=Image)

        assert isinstance(coll, Collection)
        assert len(coll) == 3

        items = Block.unpack(coll)
        assert len(items) == 3
        for item in items:
            assert isinstance(item, Image)

    def test_map_items_preserves_collection(self) -> None:
        """map_items applies a function to each item and returns a Collection."""
        imgs = [Image(shape=(i, i), ndim=2, dtype="uint8") for i in range(1, 4)]
        coll = Block.pack(imgs, item_type=Image)

        result = Block.map_items(
            lambda x: Image(shape=(10, 10), ndim=2, dtype="uint8"),
            coll,
        )

        assert isinstance(result, Collection)
        assert len(result) == 3
        for item in result:
            assert isinstance(item, Image)
            assert item.shape == (10, 10)

    def test_unpack_single(self) -> None:
        """unpack_single extracts the only item from a length-1 Collection."""
        img = Image(shape=(5, 5), ndim=2, dtype="float32")
        coll = Block.pack([img], item_type=Image)

        item = Block.unpack_single(coll)
        assert isinstance(item, Image)
        assert item.shape == (5, 5)

    def test_unpack_single_rejects_multi(self) -> None:
        """unpack_single raises ValueError for collections with != 1 item."""
        import pytest

        imgs = [Image(shape=(i, i), ndim=2, dtype="uint8") for i in range(1, 3)]
        coll = Block.pack(imgs, item_type=Image)

        with pytest.raises(ValueError, match="single-item"):
            Block.unpack_single(coll)

    def test_collection_iteration_protocol(self) -> None:
        """Collection supports __iter__, __len__, __getitem__."""
        imgs = [Image(shape=(i, i), ndim=2, dtype="uint8") for i in range(1, 5)]
        coll = Block.pack(imgs, item_type=Image)

        # __len__
        assert len(coll) == 4

        # __iter__
        iterated = list(coll)
        assert len(iterated) == 4

        # __getitem__
        assert coll[0].shape == (1, 1)
        assert coll[-1].shape == (4, 4)

    def test_collection_homogeneity_enforced(self) -> None:
        """Collection rejects heterogeneous items."""
        import pytest

        from scistudio.core.types.base import DataObject

        img = Image(shape=(2, 2), ndim=2, dtype="uint8")
        obj = DataObject()

        with pytest.raises(TypeError, match="homogeneous"):
            Collection([img, obj], item_type=Image)


# ---------------------------------------------------------------------------
# DAGScheduler + EventBus end-to-end
# ---------------------------------------------------------------------------


class TestSchedulerEventBusEndToEnd:
    """DAGScheduler dispatches blocks and emits lifecycle events via EventBus."""

    @staticmethod
    def _make_scheduler(
        workflow: WorkflowDefinition,
    ) -> tuple[DAGScheduler, EventBus, AsyncMock]:
        """Create a DAGScheduler with mocked runner/resource manager."""
        event_bus = EventBus()
        resource_manager = MagicMock()
        resource_manager.can_dispatch.return_value = True
        process_registry = MagicMock()
        process_registry.get_handle.return_value = None

        runner = AsyncMock()
        runner.run.return_value = {"output": "mock_result"}

        scheduler = DAGScheduler(
            workflow=workflow,
            event_bus=event_bus,
            resource_manager=resource_manager,
            process_registry=process_registry,
            runner=runner,
        )
        return scheduler, event_bus, runner

    def test_multimodal_pipeline_execution(self) -> None:
        """Full load->process->merge->export pipeline executes all blocks."""
        workflow = WorkflowDefinition(
            id="pipeline-e2e",
            nodes=[
                NodeDef(id="load", block_type="io_block"),
                NodeDef(id="process", block_type="process_block"),
                NodeDef(id="merge", block_type="merge_block"),
                NodeDef(id="export", block_type="io_block"),
            ],
            edges=[
                EdgeDef(source="load:data", target="process:input"),
                EdgeDef(source="process:output", target="merge:input_a"),
                EdgeDef(source="load:data", target="merge:input_b"),
                EdgeDef(source="merge:output", target="export:data"),
            ],
        )
        scheduler, event_bus, runner = self._make_scheduler(workflow)

        execution_order: list[str] = []

        async def track_run(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            execution_order.append(block.id)  # type: ignore[attr-defined]
            return {"output": f"result_{block.id}"}  # type: ignore[attr-defined]

        runner.run.side_effect = track_run

        lifecycle_events: list[str] = []
        event_bus.subscribe(
            "workflow_started",
            lambda e: lifecycle_events.append("started"),
        )
        event_bus.subscribe(
            "workflow_completed",
            lambda e: lifecycle_events.append("completed"),
        )

        asyncio.run(scheduler.execute())

        # All blocks should be done
        for node_id in ("load", "process", "merge", "export"):
            assert scheduler._block_states[node_id] == BlockState.DONE

        # load must be first, export must be last
        assert execution_order[0] == "load"
        assert execution_order[-1] == "export"

        # Lifecycle events
        assert lifecycle_events == ["started", "completed"]

    def test_parallel_branches_both_execute(self) -> None:
        """A -> (B, C) -> D: both B and C execute before D."""
        workflow = WorkflowDefinition(
            id="parallel-branches",
            nodes=[
                NodeDef(id="A", block_type="io_block"),
                NodeDef(id="B", block_type="process_block"),
                NodeDef(id="C", block_type="process_block"),
                NodeDef(id="D", block_type="io_block"),
            ],
            edges=[
                EdgeDef(source="A:out", target="B:in"),
                EdgeDef(source="A:out", target="C:in"),
                EdgeDef(source="B:out", target="D:in1"),
                EdgeDef(source="C:out", target="D:in2"),
            ],
        )
        scheduler, _event_bus, runner = self._make_scheduler(workflow)

        call_order: list[str] = []

        async def track_run(block: object, inputs: dict, config: dict, **kwargs: object) -> dict:
            call_order.append(block.id)  # type: ignore[attr-defined]
            return {"out": f"result_{block.id}"}  # type: ignore[attr-defined]

        runner.run.side_effect = track_run

        asyncio.run(scheduler.execute())

        assert call_order[0] == "A"
        assert call_order[-1] == "D"
        assert set(call_order[1:3]) == {"B", "C"}

        for node_id in ("A", "B", "C", "D"):
            assert scheduler._block_states[node_id] == BlockState.DONE
