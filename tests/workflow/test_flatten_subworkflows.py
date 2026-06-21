"""ADR-044 §4/§7 — inline flattening of SubWorkflowBlock references.

Covers FR-001 (pure flattener), FR-005 (id prefixing), FR-006 (edge rewrite),
FR-007 (cycle detection), FR-008 (no exposed_ports), FR-010 (broken-ref
placeholder), SC-001 (no SubWorkflowBlock survives), and SC-003 (direct / 2- /
3-cycles). Uses the REAL graph representation: ``WorkflowDefinition.nodes`` and
colon-form edge refs ``"node_id:port_name"``; only ``exposed_ports.internal``
uses the dot form ``"block_id.port"``.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scistudio.workflow.flatten import (
    SUBWORKFLOW_BROKEN_TYPE,
    SUBWORKFLOW_TYPE,
    CyclicSubworkflowError,
    flatten_subworkflows,
)
from scistudio.workflow.serializer import load_yaml


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _child(name: str = "child") -> str:
    return f"""
    workflow:
      id: {name}
      nodes:
        - id: load
          block_type: load_block
          config: {{}}
        - id: proc
          block_type: process_block
          config: {{}}
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


def _parent_referencing(ref: str, *, parent_id: str = "main") -> str:
    return f"""
    workflow:
      id: {parent_id}
      nodes:
        - id: src
          block_type: load_block
          config: {{}}
        - id: sw1
          block_type: subworkflow_block
          config:
            ref:
              path: {ref}
        - id: sink
          block_type: save_block
          config: {{}}
      edges:
        - source: "src:data"
          target: "sw1:raw_in"
        - source: "sw1:report"
          target: "sink:in"
    """


def test_flatten_replaces_subworkflow_with_prefixed_inner_nodes(tmp_path: Path) -> None:
    """FR-005 / SC-001: the SubWorkflowBlock is gone; inner nodes are prefixed."""
    _write(tmp_path / "subworkflows" / "child.yaml", _child())
    parent = load_yaml(_write(tmp_path / "main.yaml", _parent_referencing("subworkflows/child.yaml")))

    flat = flatten_subworkflows(parent, base_dir=tmp_path, self_path=tmp_path / "main.yaml")

    ids = {n.id for n in flat.nodes}
    assert ids == {"src", "sw1__load", "sw1__proc", "sink"}
    assert all(n.block_type != SUBWORKFLOW_TYPE for n in flat.nodes)  # SC-001


def test_flatten_rewrites_inner_and_parent_edges(tmp_path: Path) -> None:
    """FR-006: inner edges prefixed; parent edges resolved through exposed_ports."""
    _write(tmp_path / "subworkflows" / "child.yaml", _child())
    parent = load_yaml(_write(tmp_path / "main.yaml", _parent_referencing("subworkflows/child.yaml")))

    flat = flatten_subworkflows(parent, base_dir=tmp_path, self_path=tmp_path / "main.yaml")

    edges = {(e.source, e.target) for e in flat.edges}
    assert ("sw1__load:data", "sw1__proc:in") in edges  # inner edge prefixed
    assert ("src:data", "sw1__load:in") in edges  # parent -> exposed input raw_in -> load.in
    assert ("sw1__proc:out", "sink:in") in edges  # exposed output report -> proc.out -> parent


def test_flatten_is_pure_and_deterministic(tmp_path: Path) -> None:
    """FR-001: same inputs -> identical flat DAG; original is not mutated."""
    _write(tmp_path / "subworkflows" / "child.yaml", _child())
    parent = load_yaml(_write(tmp_path / "main.yaml", _parent_referencing("subworkflows/child.yaml")))
    original_ids = [n.id for n in parent.nodes]

    flat_a = flatten_subworkflows(parent, base_dir=tmp_path)
    flat_b = flatten_subworkflows(parent, base_dir=tmp_path)

    assert [n.id for n in flat_a.nodes] == [n.id for n in flat_b.nodes]
    assert [(e.source, e.target) for e in flat_a.edges] == [(e.source, e.target) for e in flat_b.edges]
    assert [n.id for n in parent.nodes] == original_ids  # original untouched


def test_flatten_nested_subworkflows_compose_prefixes(tmp_path: Path) -> None:
    """FR-005: sw1 contains sw2 contains load -> sw1__sw2__load."""
    _write(
        tmp_path / "subworkflows" / "inner.yaml",
        """
        workflow:
          id: inner
          nodes:
            - id: load
              block_type: load_block
              config: {}
          edges: []
          exposed_ports:
            outputs:
              - name: out
                internal: load.data
        """,
    )
    _write(
        tmp_path / "subworkflows" / "mid.yaml",
        """
        workflow:
          id: mid
          nodes:
            - id: sw2
              block_type: subworkflow_block
              config:
                ref:
                  path: subworkflows/inner.yaml
          edges: []
          exposed_ports:
            outputs:
              - name: passthrough
                internal: sw2.out
        """,
    )
    parent = load_yaml(
        _write(
            tmp_path / "main.yaml",
            """
            workflow:
              id: main
              nodes:
                - id: sw1
                  block_type: subworkflow_block
                  config:
                    ref:
                      path: subworkflows/mid.yaml
              edges: []
            """,
        )
    )

    flat = flatten_subworkflows(parent, base_dir=tmp_path, self_path=tmp_path / "main.yaml")

    assert [n.id for n in flat.nodes] == ["sw1__sw2__load"]
    assert all(n.block_type != SUBWORKFLOW_TYPE for n in flat.nodes)


def test_flatten_no_exposed_ports_is_legal(tmp_path: Path) -> None:
    """FR-008: a referenced file with no exposed_ports flattens; exposes zero ports."""
    _write(
        tmp_path / "subworkflows" / "plain.yaml",
        """
        workflow:
          id: plain
          nodes:
            - id: only
              block_type: process_block
              config: {}
          edges: []
        """,
    )
    parent = load_yaml(
        _write(
            tmp_path / "main.yaml",
            """
            workflow:
              id: main
              nodes:
                - id: sw1
                  block_type: subworkflow_block
                  config:
                    ref:
                      path: subworkflows/plain.yaml
              edges: []
            """,
        )
    )

    flat = flatten_subworkflows(parent, base_dir=tmp_path)

    assert [n.id for n in flat.nodes] == ["sw1__only"]


def test_flatten_broken_ref_emits_placeholder(tmp_path: Path) -> None:
    """FR-010: an unresolved ref becomes a subworkflow_broken placeholder; siblings survive."""
    parent = load_yaml(
        _write(
            tmp_path / "main.yaml",
            """
            workflow:
              id: main
              nodes:
                - id: keep
                  block_type: process_block
                  config: {}
                - id: sw_bad
                  block_type: subworkflow_block
                  config:
                    ref:
                      path: subworkflows/missing.yaml
              edges: []
            """,
        )
    )

    flat = flatten_subworkflows(parent, base_dir=tmp_path)

    by_id = {n.id: n for n in flat.nodes}
    assert by_id["keep"].block_type == "process_block"  # sibling survives
    assert by_id["sw_bad"].block_type == SUBWORKFLOW_BROKEN_TYPE  # placeholder


def test_flatten_missing_ref_path_is_broken(tmp_path: Path) -> None:
    """FR-010: a SubWorkflowBlock with no config.ref.path becomes a placeholder."""
    parent = load_yaml(
        _write(
            tmp_path / "main.yaml",
            """
            workflow:
              id: main
              nodes:
                - id: sw_empty
                  block_type: subworkflow_block
                  config: {}
              edges: []
            """,
        )
    )
    flat = flatten_subworkflows(parent, base_dir=tmp_path)
    assert flat.nodes[0].block_type == SUBWORKFLOW_BROKEN_TYPE


@pytest.mark.parametrize("length", [1, 2, 3])
def test_flatten_detects_cycles(tmp_path: Path, length: int) -> None:
    """SC-003 / FR-007: direct (A->A), 2-cycle (A->B->A), 3-cycle (A->B->C->A)."""
    sub = tmp_path / "subworkflows"
    names = [chr(ord("a") + i) for i in range(length)]  # a / a,b / a,b,c
    for i, name in enumerate(names):
        nxt = names[(i + 1) % length]
        _write(
            sub / f"{name}.yaml",
            f"""
            workflow:
              id: {name}
              nodes:
                - id: sb
                  block_type: subworkflow_block
                  config:
                    ref:
                      path: subworkflows/{nxt}.yaml
              edges: []
            """,
        )

    root = load_yaml(sub / "a.yaml")
    with pytest.raises(CyclicSubworkflowError) as excinfo:
        flatten_subworkflows(root, base_dir=tmp_path, self_path=sub / "a.yaml")

    chain = excinfo.value.chain
    assert chain[0].name == "a.yaml"
    assert chain[-1].name == "a.yaml"  # closes the loop back to the root


def test_flatten_exposed_internal_unknown_block_raises(tmp_path: Path) -> None:
    """ADR §9.1: exposed_ports.internal referencing a missing block is rejected."""
    _write(
        tmp_path / "subworkflows" / "bad.yaml",
        """
        workflow:
          id: bad
          nodes:
            - id: real
              block_type: process_block
              config: {}
          edges: []
          exposed_ports:
            outputs:
              - name: out
                internal: ghost.data
        """,
    )
    parent = load_yaml(
        _write(
            tmp_path / "main.yaml",
            """
            workflow:
              id: main
              nodes:
                - id: sw1
                  block_type: subworkflow_block
                  config:
                    ref:
                      path: subworkflows/bad.yaml
              edges: []
            """,
        )
    )
    with pytest.raises(ValueError, match="unknown block 'ghost'"):
        flatten_subworkflows(parent, base_dir=tmp_path)
