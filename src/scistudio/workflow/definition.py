"""WorkflowDefinition, NodeDef, EdgeDef dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeDef:
    """A single node in a workflow graph.

    Each node references a block type and carries configuration that will
    be forwarded to the block at execution time.
    """

    id: str
    block_type: str
    config: dict[str, Any] = field(default_factory=dict)
    execution_mode: str | None = None
    layout: dict[str, float] | None = None
    # ADR-020: batch_mode REMOVED — engine no longer iterates collections.


@dataclass
class EdgeDef:
    """A directed edge connecting two ports in the workflow graph.

    Port references use the format ``"node_id:port_name"``.
    """

    source: str  # "node_id:port_name"
    target: str  # "node_id:port_name"


@dataclass
class WorkflowDefinition:
    """Top-level description of a workflow graph.

    Contains the full set of nodes, edges, and metadata required to
    construct a DAG and execute it.
    """

    id: str = ""
    version: str = "1.0.0"
    description: str = ""
    nodes: list[NodeDef] = field(default_factory=list)
    edges: list[EdgeDef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
