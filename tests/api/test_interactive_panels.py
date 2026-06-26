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
