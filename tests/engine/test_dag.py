"""Tests for DAG construction and topological sort -- ADR-018."""

from __future__ import annotations

import pytest

from scistudio.engine.dag import (
    DAG,
    CycleError,
    build_dag,
    get_downstream_blocks,
    get_leaf_nodes,
    get_root_nodes,
    topological_sort,
)
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wf(
    nodes: list[tuple[str, str]],
    edges: list[tuple[str, str]] | None = None,
) -> WorkflowDefinition:
    """Build a minimal WorkflowDefinition from (id, block_type) pairs and edges."""
    node_defs = [NodeDef(id=n_id, block_type=bt) for n_id, bt in nodes]
    edge_defs = [EdgeDef(source=s, target=t) for s, t in (edges or [])]
    return WorkflowDefinition(nodes=node_defs, edges=edge_defs)


# ---------------------------------------------------------------------------
# build_dag tests
# ---------------------------------------------------------------------------


class TestBuildDag:
    """Tests for the build_dag() function."""

    def test_build_dag_linear(self) -> None:
        """A->B->C: 3 nodes, 2 edges, correct adjacency."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        dag = build_dag(wf)

        assert set(dag.nodes.keys()) == {"A", "B", "C"}
        assert dag.adjacency["A"] == ["B"]
        assert dag.adjacency["B"] == ["C"]
        assert dag.adjacency["C"] == []
        assert dag.reverse_adjacency["A"] == []
        assert dag.reverse_adjacency["B"] == ["A"]
        assert dag.reverse_adjacency["C"] == ["B"]
        assert len(dag.edges) == 2

    def test_build_dag_branching(self) -> None:
        """A->B, A->C: fan-out from A."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("A:out2", "C:in")],
        )
        dag = build_dag(wf)

        assert set(dag.adjacency["A"]) == {"B", "C"}
        assert dag.reverse_adjacency["B"] == ["A"]
        assert dag.reverse_adjacency["C"] == ["A"]

    def test_build_dag_diamond(self) -> None:
        """A->B, A->C, B->D, C->D: diamond pattern."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc"), ("D", "proc")],
            edges=[
                ("A:out", "B:in"),
                ("A:out", "C:in"),
                ("B:out", "D:in1"),
                ("C:out", "D:in2"),
            ],
        )
        dag = build_dag(wf)

        assert set(dag.adjacency["A"]) == {"B", "C"}
        assert dag.adjacency["B"] == ["D"]
        assert dag.adjacency["C"] == ["D"]
        assert dag.adjacency["D"] == []
        assert set(dag.reverse_adjacency["D"]) == {"B", "C"}

    def test_build_dag_single_node(self) -> None:
        """Single node, no edges."""
        wf = _wf(nodes=[("A", "proc")])
        dag = build_dag(wf)

        assert set(dag.nodes.keys()) == {"A"}
        assert dag.adjacency["A"] == []
        assert dag.reverse_adjacency["A"] == []
        assert dag.edges == []

    def test_build_dag_empty(self) -> None:
        """Empty workflow: 0 nodes, 0 edges."""
        wf = _wf(nodes=[])
        dag = build_dag(wf)

        assert dag.nodes == {}
        assert dag.adjacency == {}
        assert dag.edges == []

    def test_build_dag_edge_map(self) -> None:
        """Edge map tracks port-level connections."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:output", "B:input")],
        )
        dag = build_dag(wf)

        assert "A:output" in dag.edge_map
        assert dag.edge_map["A:output"] == ["B:input"]

    def test_build_dag_skips_underscore_prefix_nodes(self) -> None:
        """Nodes with block_type starting with '_' are excluded from the DAG."""
        wf = _wf(
            nodes=[
                ("A", "proc"),
                ("B", "proc"),
                ("note1", "_annotation"),
                ("grp1", "_group"),
            ],
            edges=[("A:out", "B:in")],
        )
        dag = build_dag(wf)

        assert set(dag.nodes.keys()) == {"A", "B"}
        assert "note1" not in dag.nodes
        assert "grp1" not in dag.nodes

    def test_build_dag_underscore_nodes_dont_break_topo_sort(self) -> None:
        """Workflow with annotation/group nodes still produces valid topological order."""
        wf = _wf(
            nodes=[
                ("A", "proc"),
                ("B", "proc"),
                ("note1", "_annotation"),
            ],
            edges=[("A:out", "B:in")],
        )
        dag = build_dag(wf)
        order = topological_sort(dag)

        assert order == ["A", "B"]

    def test_build_dag_edges_referencing_skipped_nodes_are_silently_dropped(self) -> None:
        """Edges from/to _annotation or _group nodes must not cause KeyError."""
        wf = _wf(
            nodes=[
                ("A", "proc"),
                ("B", "proc"),
                ("note1", "_annotation"),
                ("grp1", "_group"),
            ],
            edges=[
                ("A:out", "B:in"),
                ("A:out", "note1:in"),  # edge TO a skipped node
                ("note1:out", "B:in2"),  # edge FROM a skipped node
                ("grp1:out", "A:in"),  # edge FROM a skipped group node
            ],
        )
        dag = build_dag(wf)

        # Only the A->B edge should survive
        assert set(dag.nodes.keys()) == {"A", "B"}
        assert dag.adjacency["A"] == ["B"]
        assert dag.reverse_adjacency["B"] == ["A"]
        assert len(dag.edges) == 1
        # Topological sort should still work
        order = topological_sort(dag)
        assert order == ["A", "B"]

    def test_build_dag_no_duplicate_adjacency(self) -> None:
        """Multiple edges between same nodes don't create duplicate adjacency entries."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out1", "B:in1"), ("A:out2", "B:in2")],
        )
        dag = build_dag(wf)

        assert dag.adjacency["A"] == ["B"]
        assert dag.reverse_adjacency["B"] == ["A"]
        # But edge_map should have both
        assert len(dag.edges) == 2


# ---------------------------------------------------------------------------
# topological_sort tests
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    """Tests for topological_sort()."""

    def test_topological_sort_linear(self) -> None:
        """A->B->C: should produce [A, B, C]."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        dag = build_dag(wf)
        order = topological_sort(dag)

        assert order == ["A", "B", "C"]

    def test_topological_sort_diamond(self) -> None:
        """Diamond: A must be first, D must be last."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc"), ("D", "proc")],
            edges=[
                ("A:out", "B:in"),
                ("A:out", "C:in"),
                ("B:out", "D:in1"),
                ("C:out", "D:in2"),
            ],
        )
        dag = build_dag(wf)
        order = topological_sort(dag)

        assert order[0] == "A"
        assert order[-1] == "D"
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_topological_sort_deterministic(self) -> None:
        """Independent nodes are sorted lexicographically for determinism."""
        wf = _wf(
            nodes=[("C", "proc"), ("A", "proc"), ("B", "proc")],
            edges=[],
        )
        dag = build_dag(wf)
        order = topological_sort(dag)

        assert order == ["A", "B", "C"]

    def test_topological_sort_cycle(self) -> None:
        """A->B->C->A: cycle raises CycleError."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in"), ("C:out", "A:in")],
        )
        dag = build_dag(wf)

        with pytest.raises(CycleError, match="cycle"):
            topological_sort(dag)

    def test_topological_sort_self_loop(self) -> None:
        """A->A: self-loop raises CycleError."""
        wf = _wf(
            nodes=[("A", "proc")],
            edges=[("A:out", "A:in")],
        )
        dag = build_dag(wf)

        with pytest.raises(CycleError, match="cycle"):
            topological_sort(dag)

    def test_topological_sort_empty(self) -> None:
        """Empty DAG returns empty list."""
        dag = DAG()
        assert topological_sort(dag) == []

    def test_topological_sort_single_node(self) -> None:
        """Single node returns [node_id]."""
        wf = _wf(nodes=[("X", "proc")])
        dag = build_dag(wf)
        assert topological_sort(dag) == ["X"]


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for get_root_nodes, get_leaf_nodes, get_downstream_blocks."""

    def test_root_nodes_linear(self) -> None:
        """A->B->C: A is root."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        dag = build_dag(wf)
        assert get_root_nodes(dag) == ["A"]

    def test_root_nodes_multiple(self) -> None:
        """A->C, B->C: A and B are roots."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "C:in1"), ("B:out", "C:in2")],
        )
        dag = build_dag(wf)
        assert get_root_nodes(dag) == ["A", "B"]

    def test_leaf_nodes_linear(self) -> None:
        """A->B->C: C is leaf."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in")],
        )
        dag = build_dag(wf)
        assert get_leaf_nodes(dag) == ["C"]

    def test_leaf_nodes_branching(self) -> None:
        """A->B, A->C: B and C are leaves."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc")],
            edges=[("A:out", "B:in"), ("A:out2", "C:in")],
        )
        dag = build_dag(wf)
        assert get_leaf_nodes(dag) == ["B", "C"]

    def test_downstream_blocks(self) -> None:
        """A->B->C, A->D: downstream of A is {B, C, D}."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc"), ("C", "proc"), ("D", "proc")],
            edges=[("A:out", "B:in"), ("B:out", "C:in"), ("A:out2", "D:in")],
        )
        dag = build_dag(wf)
        assert get_downstream_blocks(dag, "A") == ["B", "C", "D"]

    def test_downstream_blocks_leaf(self) -> None:
        """Leaf node has no downstream."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out", "B:in")],
        )
        dag = build_dag(wf)
        assert get_downstream_blocks(dag, "B") == []

    def test_downstream_blocks_does_not_include_self(self) -> None:
        """The starting node is not included in downstream."""
        wf = _wf(
            nodes=[("A", "proc"), ("B", "proc")],
            edges=[("A:out", "B:in")],
        )
        dag = build_dag(wf)
        result = get_downstream_blocks(dag, "A")
        assert "A" not in result
        assert result == ["B"]

    def test_root_nodes_empty(self) -> None:
        """Empty DAG has no roots."""
        dag = DAG()
        assert get_root_nodes(dag) == []

    def test_leaf_nodes_empty(self) -> None:
        """Empty DAG has no leaves."""
        dag = DAG()
        assert get_leaf_nodes(dag) == []
