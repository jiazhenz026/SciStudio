"""ADR-051: panel manifest is surfaced on block metadata + the panel asset route.

Second-audit P1-B: the interactive panel manifest must be exposed for
registry/API consumption (not only read off a live block at prompt time), and a
package panel's assets must be servable (path-confined, suffix-allowlisted) so a
non-core interactive block actually has a loadable window.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from scistudio.api.routes.blocks import _summary, serve_panel_asset
from scistudio.blocks.registry import BlockRegistry


def test_panel_manifest_surfaced_on_block_metadata() -> None:
    registry = BlockRegistry()
    registry.scan()

    dr = registry.get_spec("Data Router")
    assert dr is not None
    # On the BlockSpec (registry consumption).
    assert dr.execution_mode == "interactive"
    assert dr.panel_manifest is not None
    assert dr.panel_manifest["panel_id"] == "core.interactive.data_router"
    # Core panel: bundled, no asset_root (resolved from the frontend registry).
    assert dr.panel_asset_root is None

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


def _registry_with_panel(panel_id: str, asset_root: str | None) -> Any:
    spec = SimpleNamespace(panel_manifest={"panel_id": panel_id}, panel_asset_root=asset_root)
    return SimpleNamespace(all_specs=lambda: {"PkgPanelBlock": spec})


def test_panel_asset_route_serves_confined_package_asset(tmp_path: Path) -> None:
    (tmp_path / "panel.js").write_text("export default {};", encoding="utf-8")
    registry = _registry_with_panel("pkg.interactive.panel", str(tmp_path))

    response = asyncio.run(serve_panel_asset("pkg.interactive.panel", "panel.js", registry))
    assert Path(response.path) == (tmp_path / "panel.js")
    assert response.media_type in {"text/javascript", "application/javascript"}


def test_panel_asset_route_404_for_unknown_panel(tmp_path: Path) -> None:
    registry = _registry_with_panel("pkg.interactive.panel", str(tmp_path))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(serve_panel_asset("does.not.exist", "panel.js", registry))
    assert exc.value.status_code == 404


def test_panel_asset_route_404_for_core_panel_without_asset_root() -> None:
    # A core panel (asset_root=None) is bundled, not served by this route.
    registry = _registry_with_panel("core.interactive.data_router", None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(serve_panel_asset("core.interactive.data_router", "panel.js", registry))
    assert exc.value.status_code == 404


def test_panel_asset_route_rejects_path_escape(tmp_path: Path) -> None:
    (tmp_path / "panel.js").write_text("export default {};", encoding="utf-8")
    registry = _registry_with_panel("pkg.interactive.panel", str(tmp_path))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(serve_panel_asset("pkg.interactive.panel", "../secret.js", registry))
    assert exc.value.status_code == 404


# A project-local (tier-1) interactive block whose custom panel lives beside the
# block .py (asset_root = Path(__file__).parent / "<dir>") — the exact shape the
# scistudio-write-block skill teaches agents to author. The cases above cover
# tier-1 registration and packaged-panel serving separately, against a faked
# registry; this proves the combination end to end through a REAL tier-1 scan.
_PROJECT_LOCAL_PANEL_BLOCK = """
from pathlib import Path
from scistudio.blocks.base import (
    ExecutionMode, InteractiveMixin, InteractivePrompt, PanelManifest,
)
from scistudio.blocks.process import ProcessBlock


class ProjectLocalPanelBlock(InteractiveMixin, ProcessBlock):
    name = "ProjectLocalPanelBlock"
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(
        panel_id="proj.pick_baseline",
        module_url="/api/blocks/panels/proj.pick_baseline/index.js",
        asset_root=str(Path(__file__).parent / "pick_baseline"),
        version="1",
    )

    def prepare_prompt(self, inputs, config):
        return InteractivePrompt(panel_payload={"ok": True})

    def run(self, inputs, config):
        return {}
"""


def test_project_local_interactive_block_panel_registers_and_serves(tmp_path: Path) -> None:
    """#1882: a tier-1 dropin with a project-relative asset_root registers and serves its panel.

    The write-block skill tells agents to author a project-local interactive
    block whose custom panel sits next to the block .py. Prove that path: a real
    tier-1 scan registers the block with ``panel_asset_root`` resolving into the
    project (and off the wire), and ``serve_panel_asset`` serves ``index.js``
    from it through the real registry.
    """
    scan_dir = tmp_path / "blocks"
    scan_dir.mkdir()
    (scan_dir / "project_local_panel.py").write_text(_PROJECT_LOCAL_PANEL_BLOCK, encoding="utf-8")
    panel_dir = scan_dir / "pick_baseline"
    panel_dir.mkdir()
    (panel_dir / "index.js").write_text("export default { apiVersion: '1', mount() {} };", encoding="utf-8")

    registry = BlockRegistry()
    registry.add_scan_dir(scan_dir)
    registry._scan_tier1()

    spec = registry.get_spec("ProjectLocalPanelBlock")
    assert spec is not None, "project-local interactive block did not register"
    assert spec.execution_mode == "interactive"
    # Server-only asset_root resolves into the project; never serialized to the wire.
    assert spec.panel_asset_root == str(panel_dir)
    assert "asset_root" not in (spec.panel_manifest or {})

    # The panel route serves the project-local index.js through the real registry.
    response = asyncio.run(serve_panel_asset("proj.pick_baseline", "index.js", registry))
    assert Path(response.path) == (panel_dir / "index.js").resolve()
    assert response.media_type in {"text/javascript", "application/javascript"}
