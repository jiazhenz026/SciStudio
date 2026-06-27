"""ADR-044 — SubWorkflowBlock authoring-only container.

Replaces the pre-ADR-044 stub tests (sequential executor + scheduler-factory
injection). Covers FR-004 (effective ports derived from the referenced file's
``exposed_ports``), FR-010 (broken ref -> no ports), FR-012 / SC-005 (the
nested-execution stub symbols are gone), and the authoring-only ``run()`` guard.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from scistudio.blocks.subworkflow.subworkflow_block import SubWorkflowBlock, SubWorkflowBroken


def _write_child(tmp_path: Path) -> None:
    (tmp_path / "subworkflows").mkdir(parents=True, exist_ok=True)
    (tmp_path / "subworkflows" / "child.yaml").write_text(
        textwrap.dedent(
            """
            workflow:
              id: child
              nodes:
                - id: load
                  block_type: load_block
                  config: {}
                - id: proc
                  block_type: process_block
                  config: {}
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
        ),
        encoding="utf-8",
    )


def _block(tmp_path: Path, ref: str = "subworkflows/child.yaml") -> SubWorkflowBlock:
    return SubWorkflowBlock(config={"ref": {"path": ref}, "params": {"project_dir": str(tmp_path)}})


def test_effective_ports_derived_from_exposed_ports(tmp_path: Path) -> None:
    """FR-004: port names come from the referenced file's exposed_ports."""
    _write_child(tmp_path)
    block = _block(tmp_path)

    assert [p.name for p in block.get_effective_input_ports()] == ["raw_in"]
    assert [p.name for p in block.get_effective_output_ports()] == ["report"]


def test_effective_ports_empty_for_unresolved_ref(tmp_path: Path) -> None:
    """FR-010: a missing referenced file yields no ports (no exception)."""
    block = _block(tmp_path, ref="subworkflows/missing.yaml")

    assert block.get_effective_input_ports() == []
    assert block.get_effective_output_ports() == []


def test_run_is_authoring_only_and_raises(tmp_path: Path) -> None:
    """The container is flattened away before dispatch; run() must never execute."""
    block = _block(tmp_path)
    with pytest.raises(RuntimeError, match="authoring-only"):
        block.run({}, block.config)


def test_subworkflow_broken_exposes_no_ports() -> None:
    """SubWorkflowBroken marker has a stable type_name and no ports."""
    broken = SubWorkflowBroken(config={})
    assert broken.type_name == "subworkflow_broken"
    assert broken.get_effective_input_ports() == []
    assert broken.get_effective_output_ports() == []


@pytest.mark.parametrize(
    "symbol",
    [
        "_scheduler_factory",
        "_cleanup_callback",
        "_run_with_scheduler",
        "_sequential_execute",
        "input_mapping",
        "output_mapping",
        "workflow_ref",
    ],
)
def test_stub_symbols_removed(symbol: str) -> None:
    """SC-005 / FR-012: the nested-execution stub surface is deleted."""
    assert not hasattr(SubWorkflowBlock, symbol), f"{symbol} should be removed from SubWorkflowBlock"


def test_module_level_sequential_execute_removed() -> None:
    """SC-005: the module-level sequential fallback executor is gone."""
    import scistudio.blocks.subworkflow.subworkflow_block as mod

    assert not hasattr(mod, "_sequential_execute")
