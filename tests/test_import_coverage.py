"""Import coverage for Phase 5+ modules — ensures class/dataclass definitions are counted.

These modules are mostly NotImplementedError stubs (excluded from coverage),
but their class definitions, dataclass fields, Pydantic model fields, and enum
values are executable lines that need to be imported to count.
"""

from __future__ import annotations

from datetime import datetime

import pytest


class TestImportEngineModules:
    """Engine modules — import and instantiate key types."""

    def test_import_dag(self) -> None:
        from scieasy.engine import dag  # noqa: F401

    def test_import_scheduler(self) -> None:
        from scieasy.engine import scheduler  # noqa: F401

    # ADR-020: batch module deleted — test removed.
    # def test_import_batch(self) -> None:
    #     from scieasy.engine import batch

    def test_import_checkpoint(self) -> None:
        from scieasy.engine import checkpoint  # noqa: F401

    def test_import_events(self) -> None:
        from scieasy.engine import events  # noqa: F401

    def test_import_resources(self) -> None:
        from scieasy.engine import resources  # noqa: F401

    def test_import_engine_runners(self) -> None:
        from scieasy.engine.runners import (
            base,  # noqa: F401
            local,  # noqa: F401
        )

    def test_instantiate_checkpoint(self) -> None:
        from scieasy.engine.checkpoint import WorkflowCheckpoint

        cp = WorkflowCheckpoint(
            workflow_id="wf-1",
            timestamp=datetime(2026, 1, 1),
            block_states={"b1": "done"},
        )
        assert cp.workflow_id == "wf-1"
        assert cp.block_states == {"b1": "done"}
        assert cp.pending_block is None

    def test_instantiate_engine_event(self) -> None:
        from scieasy.engine.events import EngineEvent

        ev = EngineEvent(
            event_type="block_state_changed",
            block_id="b1",
            data={"state": "running"},
        )
        assert ev.event_type == "block_state_changed"
        assert ev.block_id == "b1"

    def test_instantiate_resource_request(self) -> None:
        from scieasy.engine.resources import ResourceRequest

        # ADR-022: estimated_memory_gb removed. Only GPU/CPU fields remain.
        req = ResourceRequest(cpu_cores=2)
        assert req.cpu_cores == 2
        assert req.requires_gpu is False

    def test_instantiate_resource_snapshot(self) -> None:
        from scieasy.engine.resources import ResourceSnapshot

        # ADR-022: available_memory_gb replaced with system_memory_percent.
        snap = ResourceSnapshot(
            available_gpu_slots=1,
            available_cpu_workers=4,
            system_memory_percent=0.45,
        )
        assert snap.available_cpu_workers == 4
        assert snap.system_memory_percent == 0.45


class TestImportAPIModules:
    """API modules — import and instantiate Pydantic schemas."""

    def test_import_app(self) -> None:
        from scieasy.api import app  # noqa: F401

    def test_import_schemas(self) -> None:
        from scieasy.api import schemas  # noqa: F401

    def test_import_deps(self) -> None:
        from scieasy.api import deps  # noqa: F401

    def test_import_sse(self) -> None:
        from scieasy.api import sse  # noqa: F401

    def test_import_ws(self) -> None:
        from scieasy.api import ws  # noqa: F401

    def test_import_routes(self) -> None:
        try:
            from scieasy.api.routes import (
                ai,  # noqa: F401
                blocks,  # noqa: F401
                data,  # noqa: F401
                projects,  # noqa: F401
                workflows,  # noqa: F401
            )
        except RuntimeError as exc:
            if "python-multipart" in str(exc):
                pytest.skip("python-multipart not installed")
            raise

    def test_instantiate_workflow_create(self) -> None:
        from scieasy.api.schemas import WorkflowCreate

        wc = WorkflowCreate(id="wf-test")
        assert wc.id == "wf-test"
        assert wc.description == ""
        assert wc.nodes == []

    def test_instantiate_workflow_response(self) -> None:
        from scieasy.api.schemas import WorkflowResponse

        wr = WorkflowResponse(id="wf-test")
        assert wr.id == "wf-test"
        assert wr.version == "1.0.0"

    def test_instantiate_block_list_response(self) -> None:
        from scieasy.api.schemas import BlockListResponse

        blr = BlockListResponse(blocks=[])
        assert blr.blocks == []

    def test_instantiate_data_upload_response(self) -> None:
        from scieasy.api.schemas import DataUploadResponse

        dur = DataUploadResponse(ref="ref-1", type_name="Array")
        assert dur.ref == "ref-1"
        assert dur.type_name == "Array"

    def test_instantiate_ai_generate_request(self) -> None:
        from scieasy.api.schemas import AIGenerateBlockRequest

        req = AIGenerateBlockRequest(description="denoise block")
        assert req.description == "denoise block"


class TestImportWorkflowModules:
    """Workflow modules — import and instantiate dataclasses."""

    def test_import_definition(self) -> None:
        from scieasy.workflow import definition  # noqa: F401

    def test_import_layout(self) -> None:
        from scieasy.workflow import layout  # noqa: F401

    def test_import_serializer(self) -> None:
        from scieasy.workflow import serializer  # noqa: F401

    def test_import_validator(self) -> None:
        from scieasy.workflow import validator  # noqa: F401

    def test_instantiate_node_def(self) -> None:
        from scieasy.workflow.definition import NodeDef

        node = NodeDef(id="n1", block_type="IOBlock")
        assert node.id == "n1"
        assert node.config == {}
        assert node.execution_mode is None

    def test_instantiate_edge_def(self) -> None:
        from scieasy.workflow.definition import EdgeDef

        edge = EdgeDef(source="n1:output", target="n2:input")
        assert edge.source == "n1:output"

    def test_instantiate_workflow_definition(self) -> None:
        from scieasy.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

        wf = WorkflowDefinition(
            id="wf-1",
            nodes=[NodeDef(id="n1", block_type="IOBlock")],
            edges=[EdgeDef(source="n1:out", target="n2:in")],
        )
        assert wf.id == "wf-1"
        assert len(wf.nodes) == 1
        assert len(wf.edges) == 1

    def test_instantiate_layout_info(self) -> None:
        from scieasy.workflow.layout import LayoutInfo

        li = LayoutInfo(node_positions={"n1": {"x": 100.0, "y": 200.0}})
        assert li.node_positions["n1"]["x"] == 100.0
        assert li.zoom == 1.0


class TestImportCLI:
    """CLI module — import coverage."""

    def test_import_cli_main(self) -> None:
        from scieasy.cli import main  # noqa: F401
