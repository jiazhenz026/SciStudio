"""#1518 (DSN-2): save/start must reject workflows that fail validation.

Before #1518 ``save_workflow`` only ``logger.warning``-ed on validation
errors and saved anyway, and ``start_workflow`` never validated at all — so
an ill-typed / cyclic graph persisted cleanly and failed deep inside a block
at run time. These tests assert the gate now rejects hard errors while
leaving ``"Warning:"``-prefixed (non-fatal) diagnostics non-blocking.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime


def _cyclic_payload() -> dict:
    """A two-node graph with a cycle — a registry-independent hard error."""
    return {
        "id": "cyclic_wf",
        "nodes": [
            {"id": "A", "block_type": "loader"},
            {"id": "B", "block_type": "writer"},
        ],
        "edges": [
            {"source": "A:out", "target": "B:in"},
            {"source": "B:out", "target": "A:in"},
        ],
    }


def test_save_workflow_rejects_cycle(runtime: ApiRuntime, opened_project: Path) -> None:
    with pytest.raises(ValueError, match="validation failed"):
        runtime.save_workflow(_cyclic_payload())
    # Nothing was written to disk.
    assert not runtime.workflow_path("cyclic_wf").exists()


def test_save_workflow_allows_valid_graph(runtime: ApiRuntime, opened_project: Path) -> None:
    payload = {
        "id": "linear_wf",
        "nodes": [
            {"id": "A", "block_type": "loader"},
            {"id": "B", "block_type": "writer"},
        ],
        "edges": [{"source": "A:out", "target": "B:in"}],
    }
    definition = runtime.save_workflow(payload)
    assert definition.id == "linear_wf"
    assert runtime.workflow_path("linear_wf").exists()


def test_create_workflow_route_returns_422_on_cycle(client: TestClient, opened_project: Path) -> None:
    response = client.post("/api/workflows/", json=_cyclic_payload())
    assert response.status_code == 422


def test_start_workflow_rejects_cycle_on_disk(runtime: ApiRuntime, opened_project: Path) -> None:
    """A workflow YAML that bypassed save-time validation (written directly to
    disk via the serializer) must still be rejected by ``start_workflow``."""
    from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
    from scistudio.workflow.serializer import save_yaml

    definition = WorkflowDefinition(
        id="sneaky_wf",
        nodes=[
            NodeDef(id="A", block_type="loader"),
            NodeDef(id="B", block_type="writer"),
        ],
        edges=[
            EdgeDef(source="A:out", target="B:in"),
            EdgeDef(source="B:out", target="A:in"),
        ],
    )
    # Write directly with the serializer, bypassing ``save_workflow``'s gate.
    save_yaml(definition, runtime.workflow_path("sneaky_wf"))

    with pytest.raises(ValueError, match="validation failed"):
        runtime.start_workflow("sneaky_wf")
