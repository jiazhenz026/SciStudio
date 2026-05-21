"""DAG construction from workflow definition (topological sort, dependency resolution).

ADR-018: DAG supports querying downstream dependents for skip propagation.
DAGScheduler._propagate_skip() walks downstream from a failed/cancelled block
and marks blocks SKIPPED if all required inputs are unsatisfiable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scistudio.workflow.definition import EdgeDef, WorkflowDefinition


class CycleError(Exception):
    """Raised when a cycle is detected in the workflow graph."""


@dataclass
class DAG:
    """Internal directed acyclic graph representation of a workflow.

    Built from a ``WorkflowDefinition`` by :func:`build_dag`.

    Attributes
    ----------
    nodes:
        Mapping of node ID to ``NodeDef`` instance.
    adjacency:
        Forward edge mapping: node_id -> list of successor node_ids.
    reverse_adjacency:
        Reverse edge mapping: node_id -> list of predecessor node_ids.
    edges:
        Flat list of all ``EdgeDef`` instances.
    edge_map:
        Port-level mapping: ``"source_node:port"`` -> list of ``"target_node:port"``.
    """

    nodes: dict[str, Any] = field(default_factory=dict)
    adjacency: dict[str, list[str]] = field(default_factory=dict)
    reverse_adjacency: dict[str, list[str]] = field(default_factory=dict)
    edges: list[EdgeDef] = field(default_factory=list)
    edge_map: dict[str, list[str]] = field(default_factory=dict)


def build_dag(workflow: WorkflowDefinition) -> DAG:
    """Construct a DAG from a :class:`WorkflowDefinition`.

    Populates ``nodes``, ``adjacency``, ``reverse_adjacency``, ``edges``,
    and ``edge_map`` by iterating over the workflow's nodes and edges.

    Parameters
    ----------
    workflow:
        A ``WorkflowDefinition`` instance describing nodes and edges.

    Returns
    -------
    DAG
        The constructed graph ready for topological sorting and scheduling.
    """
    dag = DAG()

    for node in workflow.nodes:
        # Skip non-executing annotation/group nodes (block_type starts with "_").
        if node.block_type.startswith("_"):
            continue
        dag.nodes[node.id] = node
        dag.adjacency.setdefault(node.id, [])
        dag.reverse_adjacency.setdefault(node.id, [])

    for edge in workflow.edges:
        # EdgeDef has source and target as "node_id:port_name"
        src_node = edge.source.split(":")[0]
        tgt_node = edge.target.split(":")[0]

        # Skip edges that reference filtered-out nodes (e.g., _annotation, _group)
        if src_node not in dag.nodes or tgt_node not in dag.nodes:
            continue

        if tgt_node not in dag.adjacency[src_node]:
            dag.adjacency[src_node].append(tgt_node)
        if src_node not in dag.reverse_adjacency[tgt_node]:
            dag.reverse_adjacency[tgt_node].append(src_node)

        dag.edges.append(edge)
        dag.edge_map.setdefault(edge.source, []).append(edge.target)

    return dag


def topological_sort(dag: DAG) -> list[str]:
    """Return node IDs in topological order using Kahn's algorithm.

    Deterministic: when multiple nodes have in-degree zero, they are
    processed in sorted (lexicographic) order.

    Parameters
    ----------
    dag:
        A DAG instance produced by :func:`build_dag`.

    Returns
    -------
    list[str]
        Node IDs ordered so that every dependency appears before its dependents.

    Raises
    ------
    CycleError
        If the graph contains a cycle (not all nodes can be reached).
    """
    in_degree = {n: len(dag.reverse_adjacency.get(n, [])) for n in dag.nodes}
    queue = sorted(n for n, d in in_degree.items() if d == 0)
    result: list[str] = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for successor in dag.adjacency.get(node, []):
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                # Insert in sorted position for determinism
                queue.append(successor)
                queue.sort()

    if len(result) != len(dag.nodes):
        raise CycleError("Workflow contains a cycle")

    return result


def get_root_nodes(dag: DAG) -> list[str]:
    """Return node IDs that have no predecessors (in-degree zero).

    Parameters
    ----------
    dag:
        A DAG instance.

    Returns
    -------
    list[str]
        Sorted list of root node IDs.
    """
    return sorted(n for n in dag.nodes if not dag.reverse_adjacency.get(n, []))


def get_leaf_nodes(dag: DAG) -> list[str]:
    """Return node IDs that have no successors (out-degree zero).

    Parameters
    ----------
    dag:
        A DAG instance.

    Returns
    -------
    list[str]
        Sorted list of leaf node IDs.
    """
    return sorted(n for n in dag.nodes if not dag.adjacency.get(n, []))


def get_downstream_blocks(dag: DAG, node_id: str) -> list[str]:
    """Return all node IDs reachable downstream from *node_id* (BFS).

    Does not include *node_id* itself in the result.

    Parameters
    ----------
    dag:
        A DAG instance.
    node_id:
        The starting node ID.

    Returns
    -------
    list[str]
        All transitive successors of *node_id*, sorted for determinism.
    """
    visited: set[str] = set()
    queue = list(dag.adjacency.get(node_id, []))

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        queue.extend(dag.adjacency.get(current, []))

    return sorted(visited)
