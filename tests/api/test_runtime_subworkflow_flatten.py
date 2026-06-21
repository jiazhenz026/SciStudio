"""ADR-044 — runtime + route behaviour for SubWorkflowBlock flattening.

Covers FR-002 (``load_workflow`` returns the authored graph unchanged — no
flatten), FR-003 (``start_workflow`` flattens before dispatch and rejects
unresolved / cyclic references), FR-004 / D4 (``GET /api/workflows/{id}``
delivers ``resolved_ports`` for subworkflow nodes), and FR-011 (external-file
import to ``<project>/subworkflows/``).
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api.runtime import ApiRuntime


def _write_workflow(runtime: ApiRuntime, workflow_id: str, body: str) -> None:
    path = runtime.workflow_path(workflow_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")


def _write_subworkflow(project: Path, name: str, body: str) -> Path:
    sub = project / "subworkflows"
    sub.mkdir(parents=True, exist_ok=True)
    path = sub / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


_CHILD = """
workflow:
  id: child
  nodes:
    - id: load
      block_type: load_block
      config: {}
    - id: proc
      block_type: process_block
      config: {}
  edges:
    - source: "load:data"
      target: "proc:in"
  exposed_ports:
    inputs:
      - name: raw_in
        internal: load.in
    outputs:
      - name: report
        internal: proc.out
"""


def _parent(ref: str) -> str:
    return f"""
    workflow:
      id: parent
      nodes:
        - id: sw1
          block_type: subworkflow_block
          config:
            ref:
              path: {ref}
      edges: []
    """


def test_load_workflow_does_not_flatten(runtime: ApiRuntime, opened_project: Path) -> None:
    """FR-002: the editor load path returns the SubWorkflowBlock node intact."""
    _write_subworkflow(opened_project, "child.yaml", _CHILD)
    _write_workflow(runtime, "parent", _parent("subworkflows/child.yaml"))

    definition = runtime.load_workflow("parent")

    assert [n.block_type for n in definition.nodes] == ["subworkflow_block"]
    assert definition.nodes[0].id == "sw1"  # not flattened/prefixed


def test_start_workflow_rejects_broken_ref(runtime: ApiRuntime, opened_project: Path) -> None:
    """FR-003 / FR-010: an unresolved reference is rejected at run start."""
    _write_workflow(runtime, "parent", _parent("subworkflows/missing.yaml"))

    with pytest.raises(ValueError, match="could not be resolved"):
        runtime.start_workflow("parent")


def test_start_workflow_rejects_cyclic_refs(runtime: ApiRuntime, opened_project: Path) -> None:
    """FR-003 / FR-007: a reference cycle is rejected at run start."""
    _write_workflow(
        runtime,
        "a",
        """
        workflow:
          id: a
          nodes:
            - id: sb
              block_type: subworkflow_block
              config:
                ref:
                  path: workflows/b.yaml
          edges: []
        """,
    )
    _write_workflow(
        runtime,
        "b",
        """
        workflow:
          id: b
          nodes:
            - id: sb
              block_type: subworkflow_block
              config:
                ref:
                  path: workflows/a.yaml
          edges: []
        """,
    )

    with pytest.raises(ValueError, match="Cyclic subworkflow"):
        runtime.start_workflow("a")


def test_get_workflow_returns_resolved_ports(client: TestClient, opened_project: Path) -> None:
    """FR-004 / D4: the workflow GET response carries resolved_ports for sw nodes."""
    runtime = client.app.state.runtime
    _write_subworkflow(opened_project, "child.yaml", _CHILD)
    _write_workflow(runtime, "parent", _parent("subworkflows/child.yaml"))

    response = client.get("/api/workflows/parent")
    assert response.status_code == 200, response.text
    nodes = response.json()["nodes"]
    sw_node = next(n for n in nodes if n["block_type"] == "subworkflow_block")
    assert sw_node["resolved_ports"] is not None
    assert [p["name"] for p in sw_node["resolved_ports"]["inputs"]] == ["raw_in"]
    assert [p["name"] for p in sw_node["resolved_ports"]["outputs"]] == ["report"]
    assert sw_node["resolved_ports"]["broken"] is False


def test_get_workflow_marks_broken_ref(client: TestClient, opened_project: Path) -> None:
    """FR-010: a node referencing a missing file reports broken resolved_ports."""
    runtime = client.app.state.runtime
    _write_workflow(runtime, "parent", _parent("subworkflows/missing.yaml"))

    response = client.get("/api/workflows/parent")
    assert response.status_code == 200, response.text
    sw_node = next(n for n in response.json()["nodes"] if n["block_type"] == "subworkflow_block")
    assert sw_node["resolved_ports"]["broken"] is True


def test_import_subworkflow_copies_into_project(client: TestClient, opened_project: Path, tmp_path: Path) -> None:
    """FR-011: an external file is copied into <project>/subworkflows/ with a project-relative ref."""
    external = tmp_path / "external_source.yaml"
    external.write_text(_CHILD, encoding="utf-8")

    response = client.post("/api/workflows/import-subworkflow", json={"source_path": str(external)})
    assert response.status_code == 200, response.text
    ref_path = response.json()["ref_path"]
    assert ref_path == "subworkflows/external_source.yaml"
    assert (opened_project / "subworkflows" / "external_source.yaml").is_file()

    # Second import of the same file produces a distinct copy (US5 AS2).
    response2 = client.post("/api/workflows/import-subworkflow", json={"source_path": str(external)})
    assert response2.status_code == 200, response2.text
    assert response2.json()["ref_path"] == "subworkflows/external_source_1.yaml"
