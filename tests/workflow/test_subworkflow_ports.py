"""ADR-044 FR-004 — resolve_port_surface effective-port resolution.

Covers the exposed-port surface used to deliver a SubWorkflowBlock's effective
ports to the editor (the ``resolved_ports`` workflow-GET field), including
``accepted_types`` inheritance from the inner block port when a registry is
supplied (P2-2), the accept-any fallback without a registry, and broken refs.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from scistudio.workflow.subworkflow_ports import resolve_port_surface


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
    assert surface["outputs"] == [{"name": "report", "accepted_types": ["_AlphaType"]}]


def test_accepted_types_accept_any_without_registry(tmp_path: Path) -> None:
    """Without a registry the names resolve but types default to accept-any."""
    _write_child(tmp_path)
    surface = resolve_port_surface("subworkflows/child.yaml", tmp_path, registry=None)

    assert surface["outputs"] == [{"name": "report", "accepted_types": []}]


def test_broken_ref_surface(tmp_path: Path) -> None:
    """FR-010: an unresolved ref yields broken=True with no ports."""
    surface = resolve_port_surface("subworkflows/missing.yaml", tmp_path, registry=None)
    assert surface["broken"] is True
    assert surface["inputs"] == [] and surface["outputs"] == []


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
