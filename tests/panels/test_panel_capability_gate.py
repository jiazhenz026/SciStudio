"""The capability gate, backend half (T-006 backend side, T-016).

The gate itself is enforced by the host — SC-007 says so explicitly, because a
test that only checked the declaration would pass against an implementation that
trusts the panel — and its tests live in
``frontend/src/panels/panelCapability.test.ts``. What this file covers is the
backend's two obligations towards it:

* **FR-050 / SC-016**: a panel declared on a block class must declare the
  producing capability, and the check happens when the block is *discovered*,
  with a diagnostic naming the block and the panel. Not when the block first
  pauses — by then the person is already waiting on a dialog that will never
  open.
* **D-016.3**: the descriptor the backend sends carries the accepted API version
  and the read limits. The host refuses to mount without either rather than
  inventing a bound or a version, so a descriptor missing them is a backend
  defect and this is where it is caught.
"""

from __future__ import annotations

import pytest

from scistudio.blocks.base.interactive import InteractiveMixin, PanelManifest
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.registry._capability import _validate_interactive_capability
from scistudio.core.panels import PANEL_API_VERSION, PanelCapability
from scistudio.panels.descriptor import PANEL_ASSET_ROUTE_PREFIX, panel_asset_base_url, panel_descriptor

# ---------------------------------------------------------------------------
# FR-050 / SC-016 — the block-declared panel must be producing
# ---------------------------------------------------------------------------


def _interactive_block(manifest: PanelManifest) -> type:
    class Probe(InteractiveMixin):
        execution_mode = ExecutionMode.INTERACTIVE
        interactive_panel = manifest

        def prepare_prompt(self, inputs, config):
            return {}

    Probe.__name__ = "ProbeBlock"
    return Probe


def test_a_block_declaring_a_producing_panel_is_admitted() -> None:
    manifest = PanelManifest(panel_id="core.interactive.data_router", capability=PanelCapability.PRODUCING)

    _validate_interactive_capability(_interactive_block(manifest))


def test_a_block_declaring_a_displaying_only_panel_is_refused_at_discovery() -> None:
    """SC-016: refused at discovery, with a diagnostic naming the block."""
    manifest = PanelManifest(panel_id="core.plot.basic", capability=PanelCapability.DISPLAYING)

    with pytest.raises(ValueError) as caught:
        _validate_interactive_capability(_interactive_block(manifest))

    message = str(caught.value)
    assert "ProbeBlock" in message
    assert "core.plot.basic" in message
    assert "producing" in message


def test_a_block_declared_manifest_is_producing_by_construction() -> None:
    """The only caller that builds a manifest in Python is a block class naming
    the window it opens, and such a panel exists to take a decision back. An
    on-disk declaration never reaches this default: ``capability`` is required
    there, so a ``panel.json`` that omits it is refused rather than granted an
    outbound path it never claimed."""
    assert PanelManifest(panel_id="x").capability is PanelCapability.PRODUCING


def test_the_check_runs_before_the_block_ever_pauses() -> None:
    """The refusal is a registry-scan refusal, so nothing has to be executed for
    it to fire — which is the whole of FR-050's 'rather than when the block
    first pauses'."""
    manifest = PanelManifest(panel_id="acme.viewer", capability=PanelCapability.DISPLAYING)
    cls = _interactive_block(manifest)

    with pytest.raises(ValueError):
        _validate_interactive_capability(cls)


# ---------------------------------------------------------------------------
# D-016.3 — the descriptor the host is handed
# ---------------------------------------------------------------------------


def _manifest() -> PanelManifest:
    from scistudio.core.panels import manifest_from_declaration

    return manifest_from_declaration(
        {
            "panel_id": "core.plot.basic",
            "display_name": "Plot",
            "target_types": ["PlotArtifact"],
            "capability": "displaying",
            "entry": "index.html",
            "api_version": "1",
            "features": ["png", "export"],
        },
        "core.plot.basic",
    )


def test_the_descriptor_carries_the_accepted_version_and_the_read_limits() -> None:
    descriptor = panel_descriptor(_manifest()).to_dict()

    assert descriptor["accepted_api_version"] == PANEL_API_VERSION
    assert descriptor["api_version"] == "1"
    assert descriptor["read_limits"]["max_rows"] > 0
    assert descriptor["read_limits"]["max_bytes"] > 0


def test_the_descriptor_addresses_the_document_through_the_merged_asset_route() -> None:
    """D-008/FR-021: one route, four roots, the same URL shape for every tier."""
    descriptor = panel_descriptor(_manifest()).to_dict()

    assert descriptor["asset_base_url"] == f"{PANEL_ASSET_ROUTE_PREFIX}/core.plot.basic/"
    assert descriptor["document_url"] == f"{PANEL_ASSET_ROUTE_PREFIX}/core.plot.basic/index.html"


def test_a_panel_id_is_percent_encoded_into_the_asset_base() -> None:
    assert panel_asset_base_url("acme/../etc") == f"{PANEL_ASSET_ROUTE_PREFIX}/acme%2F..%2Fetc/"


def test_the_descriptor_carries_the_granted_capability_not_the_declared_one() -> None:
    """FR-049: a producing panel opened from the preview surface is granted
    display, and the panel never negotiates its way out of that."""
    manifest = PanelManifest(
        panel_id="acme.editor",
        display_name="Editor",
        capability=PanelCapability.PRODUCING,
        target_types=("DataFrame",),
    )

    granted = panel_descriptor(manifest, granted_capability=PanelCapability.DISPLAYING).to_dict()

    assert granted["capability"] == "displaying"


def test_the_descriptor_defaults_to_the_declared_capability() -> None:
    manifest = PanelManifest(panel_id="acme.editor", capability=PanelCapability.PRODUCING)

    assert panel_descriptor(manifest).to_dict()["capability"] == "producing"


def test_a_discovered_panel_descriptor_names_the_tier_it_resolved_from(tmp_path) -> None:
    from scistudio.core.panels import PanelTier
    from scistudio.panels.discovery import discover_tier
    from tests.panels.conftest import write_panel

    root = tmp_path / "project"
    root.mkdir()
    write_panel(root, "acme.table")
    panels, _ = discover_tier(PanelTier.PROJECT, (root,))

    assert panel_descriptor(panels[0]).to_dict()["tier"] == "project"
