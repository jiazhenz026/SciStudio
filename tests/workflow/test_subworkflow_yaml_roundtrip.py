"""ADR-044 — exposed_ports + SubWorkflowBlock YAML round-trip.

Codex P1 on PR #1359: opening and saving a workflow without edits must leave the
on-disk YAML byte-for-byte identical. ``exposed_ports`` therefore defaults to
``None`` and is omitted (``exclude_none``) when absent, and a SubWorkflowBlock
node's ``config.ref.path`` survives a save/load cycle unchanged.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from scistudio.workflow.definition import ExposedPort, ExposedPorts, NodeDef, WorkflowDefinition
from scistudio.workflow.serializer import dump_yaml_str, load_yaml, save_yaml


def test_exposed_ports_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "child.yaml"
    path.write_text(
        textwrap.dedent(
            """
            workflow:
              id: child
              nodes:
                - id: load
                  block_type: load_block
                  config: {}
              edges: []
              exposed_ports:
                inputs:
                  - name: raw_in
                    internal: load.in
                outputs:
                  - name: report
                    internal: load.out
            """
        ),
        encoding="utf-8",
    )

    definition = load_yaml(path)
    assert definition.exposed_ports is not None
    assert [p.name for p in definition.exposed_ports.inputs] == ["raw_in"]
    assert definition.exposed_ports.inputs[0].internal == "load.in"
    assert [p.name for p in definition.exposed_ports.outputs] == ["report"]

    # Save then reload: exposed_ports is preserved.
    out = tmp_path / "child_out.yaml"
    save_yaml(definition, out)
    reloaded = load_yaml(out)
    assert reloaded.exposed_ports is not None
    assert reloaded.exposed_ports.inputs[0].internal == "load.in"
    assert reloaded.exposed_ports.outputs[0].name == "report"


def test_no_exposed_ports_key_when_absent() -> None:
    """A workflow without exposed_ports must not gain an ``exposed_ports`` key."""
    definition = WorkflowDefinition(
        id="plain",
        nodes=[NodeDef(id="a", block_type="process_block", config={})],
        edges=[],
    )
    assert definition.exposed_ports is None
    text = dump_yaml_str(definition)
    assert "exposed_ports" not in text


def test_subworkflow_node_ref_round_trips(tmp_path: Path) -> None:
    """A SubWorkflowBlock node's config.ref.path survives save/load unchanged."""
    definition = WorkflowDefinition(
        id="parent",
        nodes=[
            NodeDef(
                id="sw1",
                block_type="subworkflow_block",
                config={"ref": {"path": "subworkflows/child.yaml"}},
            )
        ],
        edges=[],
    )
    out = tmp_path / "parent.yaml"
    save_yaml(definition, out)
    reloaded = load_yaml(out)
    assert reloaded.nodes[0].block_type == "subworkflow_block"
    assert reloaded.nodes[0].config["ref"]["path"] == "subworkflows/child.yaml"


def test_exposed_ports_dataclass_dump() -> None:
    """from_definition -> dump includes the exposed section verbatim."""
    definition = WorkflowDefinition(
        id="child",
        nodes=[NodeDef(id="load", block_type="load_block", config={})],
        edges=[],
        exposed_ports=ExposedPorts(
            inputs=[ExposedPort(name="raw_in", internal="load.in")],
            outputs=[ExposedPort(name="report", internal="load.out")],
        ),
    )
    text = dump_yaml_str(definition)
    assert "exposed_ports" in text
    assert "raw_in" in text
    assert "load.in" in text
