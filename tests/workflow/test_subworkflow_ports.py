"""ADR-044 FR-004 — resolve_port_surface effective-port resolution.

Covers the exposed-port surface used to deliver a SubWorkflowBlock's effective
ports to the editor (the ``resolved_ports`` workflow-GET field), including
``accepted_types`` inheritance from the inner block port when a registry is
supplied (P2-2), the accept-any fallback without a registry, and broken refs.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.subworkflow_ports import derive_exposed_ports, resolve_port_surface


class _AlphaType:
    pass


class _FakePort:
    def __init__(self, name: str, accepted_types: list[type]) -> None:
        self.name = name
        self.accepted_types = accepted_types


class _FakeBlock:
    def __init__(self, outputs: list[_FakePort]) -> None:
        self._outputs = outputs

    def get_effective_input_ports(self) -> list[_FakePort]:
        return []

    def get_effective_output_ports(self) -> list[_FakePort]:
        return self._outputs


class _FakeRegistry:
    def instantiate(self, block_type: str, config: object = None) -> _FakeBlock:
        return _FakeBlock([_FakePort("out", [_AlphaType])])


def _write_child(tmp_path: Path) -> None:
    (tmp_path / "subworkflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / "subworkflows" / "child.yaml").write_text(
        textwrap.dedent(
            """
            workflow:
              id: child
              nodes:
                - id: proc
                  block_type: process_block
                  config: {}
              edges: []
              exposed_ports:
                outputs:
                  - name: report
                    internal: proc.out
            """
        ),
        encoding="utf-8",
    )


def test_accepted_types_inherited_from_inner_port_with_registry(tmp_path: Path) -> None:
    """P2-2 / FR-004: accepted_types come from the inner block's effective port."""
    _write_child(tmp_path)
    surface = resolve_port_surface("subworkflows/child.yaml", tmp_path, registry=_FakeRegistry())

    assert surface["broken"] is False
    [out] = surface["outputs"]
    assert out["name"] == "report"
    assert out["accepted_types"] == ["_AlphaType"]


class _SpecRegistry(_FakeRegistry):
    """Registry that also answers ``get_spec`` with a display name."""

    class _Spec:
        name = "Process Block"

    def get_spec(self, block_type: str) -> _Spec:
        return self._Spec()


def test_resolve_surface_carries_block_provenance(tmp_path: Path) -> None:
    """ADR-044 hotfix5: each exposed port carries its owning inner block id/type/
    label and inner port so the editor can show which block it belongs to."""
    _write_child(tmp_path)
    surface = resolve_port_surface("subworkflows/child.yaml", tmp_path, registry=_SpecRegistry())

    [out] = surface["outputs"]
    assert out["block_id"] == "proc"
    assert out["port"] == "out"
    assert out["block_type"] == "process_block"
    assert out["block_label"] == "Process Block"


def test_provenance_label_falls_back_to_block_type_without_get_spec(tmp_path: Path) -> None:
    """Without a registry display name the label falls back to the block type."""
    _write_child(tmp_path)
    surface = resolve_port_surface("subworkflows/child.yaml", tmp_path, registry=_FakeRegistry())

    [out] = surface["outputs"]
    assert out["block_type"] == "process_block"
    assert out["block_label"] == "process_block"


def test_accepted_types_accept_any_without_registry(tmp_path: Path) -> None:
    """Without a registry the names resolve but types default to accept-any."""
    _write_child(tmp_path)
    surface = resolve_port_surface("subworkflows/child.yaml", tmp_path, registry=None)

    [out] = surface["outputs"]
    assert out["name"] == "report"
    assert out["accepted_types"] == []
    # Provenance (id/port/type) still resolves from the file without a registry;
    # only the human label is unavailable, so it falls back to the block type.
    assert out["block_id"] == "proc"
    assert out["port"] == "out"
    assert out["block_type"] == "process_block"


def test_broken_ref_surface(tmp_path: Path) -> None:
    """FR-010: an unresolved ref yields broken=True with no ports."""
    surface = resolve_port_surface("subworkflows/missing.yaml", tmp_path, registry=None)
    assert surface["broken"] is True
    assert surface["inputs"] == [] and surface["outputs"] == []


class _IOBlock:
    """Fake block with arbitrary effective input/output ports keyed by name."""

    def __init__(self, inputs: list[str], outputs: list[str]) -> None:
        self._inputs = [_FakePort(n, []) for n in inputs]
        self._outputs = [_FakePort(n, []) for n in outputs]

    def get_effective_input_ports(self) -> list[_FakePort]:
        return self._inputs

    def get_effective_output_ports(self) -> list[_FakePort]:
        return self._outputs


class _IORegistry:
    """Registry returning per-block-type effective ports from a fixed map."""

    def __init__(self, ports_by_type: dict[str, tuple[list[str], list[str]]]) -> None:
        self._ports = ports_by_type

    def instantiate(self, block_type: str, config: object = None) -> _IOBlock:
        ins, outs = self._ports[block_type]
        return _IOBlock(ins, outs)


def test_derive_exposes_only_open_ports() -> None:
    """ADR-044 Addendum 1: expose every unconnected input and unconnected output.

    ``a:out`` -> ``b:in1`` is wired, so neither is exposed. ``b.in2`` (no
    incoming) and ``a.out`` is consumed but ``b.result`` (no outgoing) is open.
    """
    definition = WorkflowDefinition(
        nodes=[
            NodeDef(id="a", block_type="src", config={}),
            NodeDef(id="b", block_type="proc", config={}),
        ],
        edges=[EdgeDef(source="a:out", target="b:in1")],
    )
    registry = _IORegistry({"src": ([], ["out"]), "proc": (["in1", "in2"], ["result"])})

    exposed = derive_exposed_ports(definition, registry=registry)

    # in1 is fed by a:out (connected); in2 is open.
    assert [(p.name, p.internal) for p in exposed.inputs] == [("b.in2", "b.in2")]
    # a:out feeds b (connected); b:result has no outgoing edge (open).
    assert [(p.name, p.internal) for p in exposed.outputs] == [("b.result", "b.result")]


def test_derive_disambiguates_shared_port_names() -> None:
    """Two inner nodes with the same open port name get distinct exposed names."""
    definition = WorkflowDefinition(
        nodes=[
            NodeDef(id="d_bl", block_type="proc", config={}),
            NodeDef(id="u_bl", block_type="proc", config={}),
        ],
        edges=[],
    )
    registry = _IORegistry({"proc": (["spectra"], [])})

    exposed = derive_exposed_ports(definition, registry=registry)

    assert [p.name for p in exposed.inputs] == ["d_bl.spectra", "u_bl.spectra"]


def test_derive_without_registry_yields_empty_surface() -> None:
    """No registry means inner ports cannot be read, so nothing is exposed."""
    definition = WorkflowDefinition(nodes=[NodeDef(id="a", block_type="src", config={})], edges=[])
    exposed = derive_exposed_ports(definition, registry=None)
    assert exposed.inputs == [] and exposed.outputs == []


def test_no_exposed_ports_is_not_broken(tmp_path: Path) -> None:
    """FR-008: a referenced file with no exposed_ports is legal (zero ports, not broken)."""
    (tmp_path / "subworkflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / "subworkflows" / "plain.yaml").write_text(
        textwrap.dedent(
            """
            workflow:
              id: plain
              nodes:
                - id: only
                  block_type: process_block
                  config: {}
              edges: []
            """
        ),
        encoding="utf-8",
    )
    surface = resolve_port_surface("subworkflows/plain.yaml", tmp_path, registry=None)
    assert surface["broken"] is False
    assert surface["inputs"] == [] and surface["outputs"] == []
