"""Pydantic models for workflow YAML schema validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from scistudio.workflow.definition import (
    EdgeDef,
    ExposedPort,
    ExposedPorts,
    NodeDef,
    WorkflowDefinition,
)


class ExposedPortModel(BaseModel):
    """One port a workflow offers to a parent workflow that references it.

    ``internal`` names the port inside this file with a dot
    (``node_id.port_name``), unlike an edge, which uses a colon.
    """

    # Development references: ADR-044.

    name: str = Field(
        description=(
            "Port name the parent workflow sees on the subworkflow node. A parent edge addresses it as "
            "``subworkflow_node_id:name``. Give each port a distinct name within ``inputs`` and within ``outputs``."
        ),
    )
    internal: str = Field(
        description=(
            "The port inside this file that the exposed port stands for, written ``node_id.port_name`` with "
            "a dot. The node may itself be a subworkflow node, in which case ``port_name`` is one of that "
            "subworkflow's exposed ports. When a run starts, an ``internal`` value naming a node or port "
            "that does not exist stops the run."
        ),
    )

    @field_validator("name", "internal")
    @classmethod
    def must_be_nonempty(cls, v: str) -> str:
        """``name`` and ``internal`` must not be empty or whitespace."""
        if not v.strip():
            raise ValueError("exposed_ports entries require non-empty 'name' and 'internal'")
        return v

    @field_validator("internal")
    @classmethod
    def internal_must_be_block_dot_port(cls, v: str) -> str:
        """``internal`` is ``node_id.port_name``: exactly one dot with a non-empty value on each side."""
        parts = v.split(".")
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(f"exposed_ports.internal must be 'block_id.port', got '{v}'")
        return v

    def to_exposed_port(self) -> ExposedPort:
        return ExposedPort(name=self.name, internal=self.internal)

    @classmethod
    def from_exposed_port(cls, ep: ExposedPort) -> ExposedPortModel:
        return cls(name=ep.name, internal=ep.internal)


class ExposedPortsModel(BaseModel):
    """The ports a workflow offers when another workflow references it as a subworkflow."""

    # Development references: ADR-044.

    inputs: list[ExposedPortModel] = Field(
        default=[],
        description="Input ports of the subworkflow node, each bound to an input port inside this file.",
    )
    outputs: list[ExposedPortModel] = Field(
        default=[],
        description="Output ports of the subworkflow node, each bound to an output port inside this file.",
    )

    def to_exposed_ports(self) -> ExposedPorts:
        return ExposedPorts(
            inputs=[p.to_exposed_port() for p in self.inputs],
            outputs=[p.to_exposed_port() for p in self.outputs],
        )

    @classmethod
    def from_exposed_ports(cls, ep: ExposedPorts) -> ExposedPortsModel:
        return cls(
            inputs=[ExposedPortModel.from_exposed_port(p) for p in ep.inputs],
            outputs=[ExposedPortModel.from_exposed_port(p) for p in ep.outputs],
        )


class NodeModel(BaseModel):
    """One block in the workflow graph."""

    id: str = Field(
        description=(
            "Node id. Edges and ``exposed_ports`` refer to the node by this value. Must not be empty; "
            "validation reports a duplicate id within the same workflow."
        ),
    )
    block_type: str = Field(
        description=(
            "Registered block type name, as the block registry lists it (for example ``load_data``). "
            "The ``write_workflow`` agent tool refuses a type the registry cannot resolve; validation "
            "reports an unregistered type as a warning. A node that references another workflow file "
            "uses ``subworkflow_block``."
        ),
    )
    config: dict[str, Any] = Field(
        default={},
        description=(
            "Block configuration, checked against the block's config schema. When the canvas saves, file "
            "and directory fields that point inside the project are written as project-relative paths "
            "with forward slashes. A "
            "``subworkflow_block`` node names the referenced workflow file, relative to the project, "
            "in ``ref.path``."
        ),
    )
    execution_mode: str | None = Field(
        default=None,
        description=(
            "Execution mode recorded with the node: ``auto``, ``interactive``, or ``external``. The "
            "engine runs a block in the mode its block class declares. Left out of the file when unset."
        ),
    )
    layout: dict[str, float] | None = Field(
        default=None,
        description=(
            "Canvas position of the node as numbers, for example ``{x: 120.0, y: 80.0}``. It has no "
            "effect on execution. Left out of the file when unset."
        ),
    )

    @field_validator("id")
    @classmethod
    def id_must_be_nonempty(cls, v: str) -> str:
        """``id`` must not be empty or whitespace."""
        if not v.strip():
            raise ValueError("Node id must not be empty")
        return v

    def to_node_def(self) -> NodeDef:
        """Convert to the runtime dataclass."""
        return NodeDef(
            id=self.id,
            block_type=self.block_type,
            config=self.config,
            execution_mode=self.execution_mode,
            layout=self.layout,
        )

    @classmethod
    def from_node_def(cls, node: NodeDef) -> NodeModel:
        """Create from the runtime dataclass."""
        return cls(
            id=node.id,
            block_type=node.block_type,
            config=node.config,
            execution_mode=node.execution_mode,
            layout=node.layout,
        )


class EdgeModel(BaseModel):
    """A directed connection from an output port of one node to an input port of another.

    Several edges may share a ``source``: one output feeds several inputs. The
    edges must not form a cycle, both ends must name nodes in the same workflow,
    and, when the block registry is available, validation checks that the ports
    exist and that the output type is accepted by the input.
    """

    source: str = Field(description="Output port the data leaves from, written ``node_id:port_name``.")
    target: str = Field(description="Input port the data arrives at, written ``node_id:port_name``.")

    @field_validator("source", "target")
    @classmethod
    def must_be_port_reference(cls, v: str) -> str:
        """``source`` and ``target`` are ``node_id:port_name``: exactly one colon with a non-empty value on each side."""
        parts = v.split(":")
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            raise ValueError(f"Port reference must be 'node_id:port_name', got '{v}'")
        return v

    def to_edge_def(self) -> EdgeDef:
        """Convert to the runtime dataclass."""
        return EdgeDef(source=self.source, target=self.target)

    @classmethod
    def from_edge_def(cls, edge: EdgeDef) -> EdgeModel:
        """Create from the runtime dataclass."""
        return cls(source=edge.source, target=edge.target)


class WorkflowModel(BaseModel):
    """The workflow body: everything under the top-level ``workflow`` key."""

    id: str = Field(
        default="",
        description=(
            "Workflow id. It must equal the file name without its suffix: ``workflows/main.yaml`` declares "
            "``main``. The ``write_workflow`` agent tool refuses a file whose name and id differ, and "
            "moving or renaming a workflow file rewrites the id to the new name (a ``.swf`` marker is "
            "dropped, so ``qc.swf.yaml`` declares ``qc``). A run is identified by its file, not by this value."
        ),
    )
    version: str = Field(
        default="1.0.0",
        description="Version label of this workflow, kept as written. SciStudio does not interpret it.",
    )
    description: str = Field(default="", description="Human-readable summary of what the workflow does.")
    nodes: list[NodeModel] = Field(
        default=[],
        description="The blocks in the graph. A workflow with no nodes is valid.",
    )
    edges: list[EdgeModel] = Field(
        default=[],
        description="Connections between node ports. Leave empty for a workflow with a single block.",
    )
    metadata: dict[str, Any] = Field(
        default={},
        description=(
            "Free-form mapping kept with the workflow. When it holds ``project_dir``, validation resolves "
            "project-relative paths in node configuration against that directory."
        ),
    )
    # ADR-044 §6: optional. Defaults to None so files without the section
    # serialise without an ``exposed_ports`` key (model_dump exclude_none),
    # preserving the byte-for-byte save round-trip (Codex P1 on PR #1359).
    exposed_ports: ExposedPortsModel | None = Field(
        default=None,
        description=(
            "Ports this workflow offers when another workflow references it as a subworkflow. Without "
            "this section the file still runs on its own and exposes no ports."
        ),
    )

    def to_definition(self) -> WorkflowDefinition:
        """Convert to the runtime :class:`WorkflowDefinition` dataclass."""
        return WorkflowDefinition(
            id=self.id,
            version=self.version,
            description=self.description,
            nodes=[n.to_node_def() for n in self.nodes],
            edges=[e.to_edge_def() for e in self.edges],
            metadata=self.metadata,
            exposed_ports=(self.exposed_ports.to_exposed_ports() if self.exposed_ports is not None else None),
        )

    @classmethod
    def from_definition(cls, wf: WorkflowDefinition) -> WorkflowModel:
        """Create from the runtime :class:`WorkflowDefinition` dataclass."""
        return cls(
            id=wf.id,
            version=wf.version,
            description=wf.description,
            nodes=[NodeModel.from_node_def(n) for n in wf.nodes],
            edges=[EdgeModel.from_edge_def(e) for e in wf.edges],
            metadata=wf.metadata,
            exposed_ports=(
                ExposedPortsModel.from_exposed_ports(wf.exposed_ports) if wf.exposed_ports is not None else None
            ),
        )


class WorkflowFileModel(BaseModel):
    """A workflow YAML file: one mapping whose only key is ``workflow``.

    Workflow files live in the project's ``workflows/`` directory, one workflow
    per file, with a ``.yaml`` or ``.yml`` suffix; subworkflow files may live elsewhere in the
    project. SciStudio writes the keys in the order this reference lists them and
    leaves out optional keys whose value is null.
    """

    workflow: WorkflowModel = Field(description="The workflow definition.")
