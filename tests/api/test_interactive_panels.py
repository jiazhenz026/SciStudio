"""ADR-051: the interactive panel manifest is surfaced on block metadata.

Second-audit P1-B: the interactive panel manifest must be exposed for
registry/API consumption (not only read off a live block at prompt time). Since
#2493 every interactive window is an HTML panel opened in the interactive
context; the legacy module asset route is gone.
"""

from __future__ import annotations

import json
from pathlib import Path

from scistudio.api.routes.blocks import _summary
from scistudio.api.routes.blocks import router as blocks_router
from scistudio.blocks.registry import BlockRegistry


def test_panel_manifest_surfaced_on_block_metadata() -> None:
    registry = BlockRegistry()
    registry.scan()

    dr = registry.get_spec("Data Router")
    assert dr is not None
    # On the BlockSpec (registry consumption).
    assert dr.execution_mode == "interactive"
    assert dr.panel_manifest is not None
    assert dr.panel_manifest == {"panel_id": "core.interactive.data_router", "api_version": "1"}
    assert not hasattr(dr, "panel_asset_root")

    # On the API palette summary (API consumption).
    summary = _summary(dr, registry)
    assert summary.execution_mode == "interactive"
    assert summary.panel_manifest is not None
    assert summary.panel_manifest["panel_id"] == "core.interactive.data_router"

    # A non-interactive block carries no manifest.
    load = registry.get_spec("Load")
    assert load is not None
    assert load.execution_mode == "auto"
    assert load.panel_manifest is None
    assert _summary(load, registry).panel_manifest is None


def test_the_legacy_panel_module_asset_route_is_gone() -> None:
    paths = {getattr(route, "path", "") for route in blocks_router.routes}
    assert "/api/blocks/panels/{panel_id}/{asset_path:path}" not in paths


# A project-local (tier-1) interactive block whose window is a panel folder in
# the project's ``panels/`` tier, declared by ``panel_id`` alone.
_PROJECT_LOCAL_PANEL_BLOCK = """
from scistudio.blocks.base import (
    ExecutionMode, InteractiveMixin, InteractivePrompt, PanelManifest,
)
from scistudio.blocks.process import ProcessBlock


class ProjectLocalPanelBlock(InteractiveMixin, ProcessBlock):
    name = "ProjectLocalPanelBlock"
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(panel_id="proj.pick_baseline")

    def prepare_prompt(self, inputs, config):
        return InteractivePrompt(panel_payload={"ok": True})

    def run(self, inputs, config):
        return {}
"""


def test_project_local_interactive_block_resolves_its_project_panel(tmp_path: Path) -> None:
    """A tier-1 drop-in names a panel in ``<project>/panels``; the scan registers it."""
    scan_dir = tmp_path / "blocks"
    scan_dir.mkdir()
    (scan_dir / "project_local_panel.py").write_text(_PROJECT_LOCAL_PANEL_BLOCK, encoding="utf-8")
    panel_dir = tmp_path / "panels" / "proj.pick_baseline"
    panel_dir.mkdir(parents=True)
    (panel_dir / "panel.json").write_text(
        json.dumps({"id": "proj.pick_baseline", "api_version": "1.0", "contexts": ["interactive"]}),
        encoding="utf-8",
    )
    (panel_dir / "index.html").write_text("<p>pick</p>", encoding="utf-8")

    from scistudio.panels.validation import panel_scan_scope

    registry = BlockRegistry()
    registry.add_scan_dir(scan_dir)
    with panel_scan_scope([scan_dir]):
        registry._scan_tier1()

    spec = registry.get_spec("ProjectLocalPanelBlock")
    assert spec is not None, "project-local interactive block did not register"
    assert spec.execution_mode == "interactive"
    assert spec.panel_manifest == {"panel_id": "proj.pick_baseline", "api_version": "1"}
