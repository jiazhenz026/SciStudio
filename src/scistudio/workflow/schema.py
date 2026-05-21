"""Pydantic models for workflow YAML schema validation."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, field_validator

from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition


class NodeModel(BaseModel):
    """Pydantic model for a workflow node entry in YAML."""

    id: str
    block_type: str
    config: dict[str, Any] = {}
    execution_mode: str | None = None
    layout: dict[str, float] | None = None

    @field_validator("id")
    @classmethod
    def id_must_be_nonempty(cls, v: str) -> str:
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
    """Pydantic model for a workflow edge entry in YAML."""

    source: str
    target: str

    @field_validator("source", "target")
    @classmethod
    def must_be_port_reference(cls, v: str) -> str:
        """Enforce ``node_id:port_name`` format."""
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
    """Pydantic model for the workflow body inside the top-level ``workflow:`` key."""

    id: str = ""
    version: str = "1.0.0"
    description: str = ""
    nodes: list[NodeModel] = []
    edges: list[EdgeModel] = []
    metadata: dict[str, Any] = {}

    def to_definition(self) -> WorkflowDefinition:
        """Convert to the runtime :class:`WorkflowDefinition` dataclass."""
        return WorkflowDefinition(
            id=self.id,
            version=self.version,
            description=self.description,
            nodes=[n.to_node_def() for n in self.nodes],
            edges=[e.to_edge_def() for e in self.edges],
            metadata=self.metadata,
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
        )


class WorkflowFileModel(BaseModel):
    """Top-level YAML structure: ``{workflow: {...}}``."""

    workflow: WorkflowModel
