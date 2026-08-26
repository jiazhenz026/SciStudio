"""Surface 2 (#2196): ``validate_workflow`` Check 11, the interactive panel contract.

The registry refuses a hard-invalid interactive block at scan time, so most of
these never reach a workflow. What Check 11 catches is the case the scan cannot:
a panel is a JavaScript file beside the block, and nothing re-registers the block
when that file changes. A block that registered cleanly can be pointing at a
module that has since been edited into something that will not mount, or deleted
outright — and finding that out at a paused block with an empty modal is exactly
the failure this whole change exists to end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.blocks.registry import BlockRegistry, BlockSpec
from scistudio.workflow.definition import NodeDef, WorkflowDefinition
from scistudio.workflow.validator import validate_workflow

GOOD_PANEL = """
export default {
  apiVersion: "1",
  mount(container, host) {
    container.onclick = () => host.confirm({});
    container.oncontextmenu = () => host.cancel();
    return { unmount() {} };
  },
};
"""


@pytest.fixture
def panel_root(tmp_path: Path) -> Path:
    root = tmp_path / "panel_assets"
    root.mkdir()
    (root / "panel.mjs").write_text(GOOD_PANEL, encoding="utf-8")
    return root


def _registry_with_panel(panel_root: Path | None, *, module_file: str = "panel.mjs") -> BlockRegistry:
    """A spec-only registry carrying one interactive block with a package panel."""
    registry = BlockRegistry()
    registry._registry["PanelBlock"] = BlockSpec(
        name="PanelBlock",
        description="",
        version="0.1.0",
        module_path="tests.synthetic",
        class_name="PanelBlock",
        base_category="process",
        type_name="panel_block",
        execution_mode="interactive",
        panel_manifest={
            "panel_id": "pkg.panel_block",
            "module_url": f"/api/blocks/panels/pkg.panel_block/{module_file}",
            "export_name": "default",
            "css": [],
            "version": "1",
            "api_version": "1",
        },
        panel_asset_root=str(panel_root) if panel_root is not None else None,
    )
    registry._aliases["panel_block"] = "PanelBlock"
    return registry


def _workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        id="wf",
        nodes=[NodeDef(id="n1", block_type="PanelBlock", config={})],
        edges=[],
    )


def _hard_errors(diagnostics: list[str]) -> list[str]:
    return [d for d in diagnostics if not d.startswith("Warning:")]


def test_a_sound_panel_produces_no_diagnostics(panel_root: Path) -> None:
    assert validate_workflow(_workflow(), _registry_with_panel(panel_root)) == []


def test_a_panel_module_deleted_after_registration_invalidates_the_workflow(panel_root: Path) -> None:
    """The case scan-time validation structurally cannot catch."""
    registry = _registry_with_panel(panel_root)
    assert validate_workflow(_workflow(), registry) == []

    (panel_root / "panel.mjs").unlink()

    errors = _hard_errors(validate_workflow(_workflow(), registry))
    assert errors
    assert "n1" in errors[0]
    assert "import_failed" in errors[0]


def test_a_panel_edited_into_a_wrong_api_version_invalidates_the_workflow(panel_root: Path) -> None:
    registry = _registry_with_panel(panel_root)
    (panel_root / "panel.mjs").write_text(
        'export default { apiVersion: "4", mount(c, host) { host.confirm(); host.cancel(); '
        "return { unmount() {} }; } };",
        encoding="utf-8",
    )

    errors = _hard_errors(validate_workflow(_workflow(), registry))
    assert any("api_version_mismatch" in error for error in errors)


def test_a_missing_asset_root_invalidates_the_workflow() -> None:
    errors = _hard_errors(validate_workflow(_workflow(), _registry_with_panel(None)))

    assert any("import_failed" in error for error in errors)


def test_heuristic_findings_are_warnings_and_leave_the_workflow_valid(panel_root: Path) -> None:
    """``Warning:`` is the prefix every consumer splits on (#1988); advisories must use it."""
    (panel_root / "panel.mjs").write_text(
        'export default { apiVersion: "1", mount(container, host) { return {}; } };',
        encoding="utf-8",
    )

    diagnostics = validate_workflow(_workflow(), _registry_with_panel(panel_root))

    assert _hard_errors(diagnostics) == []
    assert diagnostics
    assert all(d.startswith("Warning:") for d in diagnostics)
    assert any("panel_control_missing" in d for d in diagnostics)


def test_the_diagnostic_names_the_node_and_the_repair(panel_root: Path) -> None:
    (panel_root / "panel.mjs").unlink()

    errors = _hard_errors(validate_workflow(_workflow(), _registry_with_panel(panel_root)))

    assert errors[0].startswith("Node 'n1': panel ")
    assert " Fix: " in errors[0]


def test_check_11_also_runs_in_draft_mode(panel_root: Path) -> None:
    """Unlike the completeness checks, a broken panel is not work-in-progress."""
    (panel_root / "panel.mjs").unlink()

    errors = _hard_errors(validate_workflow(_workflow(), _registry_with_panel(panel_root), mode="draft"))

    assert errors


def test_a_non_interactive_block_is_untouched(panel_root: Path) -> None:
    registry = _registry_with_panel(panel_root)
    registry._registry["PanelBlock"].panel_manifest = None

    assert validate_workflow(_workflow(), registry) == []


def test_check_11_is_skipped_without_a_registry() -> None:
    assert validate_workflow(_workflow(), None) == []
