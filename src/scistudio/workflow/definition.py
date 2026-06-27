"""WorkflowDefinition, NodeDef, EdgeDef dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.blocks.registry import BlockRegistry


@dataclass
class ExposedPort:
    """One entry in a subworkflow file's ``exposed_ports`` section (ADR-044 §6).

    ``internal`` references a block and port *inside the same file* using the
    dot form ``"block_id.port"`` (distinct from :class:`EdgeDef`'s colon
    ``"node_id:port_name"`` wire form). The dot form is the on-disk authoring
    convention for exposed ports; the inline flattener (ADR-044 §4) translates
    it to the colon wire form when rewriting parent edges.
    """

    name: str
    internal: str  # "block_id.port" (DOT)


@dataclass
class ExposedPorts:
    """Optional top-level ``exposed_ports`` section of a workflow YAML file.

    Present when a workflow is intended to be referenced as a subworkflow
    (ADR-044 §6). Absent/empty means the file exposes zero ports to a parent
    but is still referenceable and still runnable standalone (FR-008).
    """

    inputs: list[ExposedPort] = field(default_factory=list)
    outputs: list[ExposedPort] = field(default_factory=list)


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
    # ADR-044 §6: optional exposed-port surface when this file is referenced as
    # a subworkflow. ``None`` (not an empty :class:`ExposedPorts`) so files
    # without the section round-trip byte-for-byte (serializer ``exclude_none``).
    exposed_ports: ExposedPorts | None = None

    def flatten_subworkflows(
        self,
        base_dir: str | Path,
        *,
        registry: BlockRegistry | None = None,
    ) -> WorkflowDefinition:
        """Return a copy with every ``SubWorkflowBlock`` reference inlined.

        Thin forwarding shim for the ADR-044 §4 contract
        ``WorkflowDefinition.flatten_subworkflows(self)``. The real
        implementation is the pure free function
        :func:`scistudio.workflow.flatten.flatten_subworkflows`, which lives
        outside this dataclass module because flattening must read *other*
        workflow YAML files (a serializer-layer concern) and would otherwise
        invert the ``serializer -> definition`` dependency direction.
        """
        from scistudio.workflow.flatten import flatten_subworkflows

        return flatten_subworkflows(self, base_dir, registry=registry)
