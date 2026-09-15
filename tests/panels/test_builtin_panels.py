"""Discovery, descriptor, and routing-shadow coverage for the core-tier panels.

These panels (ADR-054 Phase B, T-014 / FR-040) rewrite the nine compiled core
previewers as core-tier HTML panels. Discovery must find them, they must carry
the same ids as the legacy ``core_previewer_specs`` so they shadow them in one
namespace (FR-007), and each must reference only local assets (FR-042).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.panels.descriptor import parse_descriptor
from scistudio.panels.files import validate_external_references
from scistudio.panels.registry import discover_panels
from scistudio.previewers.fallbacks import core_previewer_specs
from scistudio.previewers.models import OwnerKind
from scistudio.previewers.registry import PreviewerRegistry

BUILTIN_ROOT = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "panels" / "builtin"

# The core previewer id -> declared preview type. ``PlotArtifact`` is a synthetic
# catalog type (plot artifacts carry type_chain ["DataObject", "PlotArtifact"]),
# not a TypeRegistry type, so its panel is validated with an extended type set.
EXPECTED_TYPES = {
    "core.dataframe.basic": "DataFrame",
    "core.array.basic": "Array",
    "core.series.basic": "Series",
    "core.text.basic": "Text",
    "core.artifact.basic": "Artifact",
    "core.composite.basic": "CompositeData",
    "core.collection.basic": "Collection",
    "core.plot.basic": "PlotArtifact",
    "core.base.fallback": "DataObject",
}
# Every core panel's declared type is a real TypeRegistry type or a core-reserved
# sentinel (DataObject/Collection/PlotArtifact), so all nine are discovered live.
REGISTRY_DISCOVERABLE = set(EXPECTED_TYPES)


def _registered_types() -> set[str]:
    from scistudio.core.types.registry import TypeRegistry

    types = TypeRegistry()
    types.scan_all()
    return set(types.all_types().keys())


def test_every_core_previewer_has_a_builtin_panel_folder() -> None:
    for pid in EXPECTED_TYPES:
        folder = BUILTIN_ROOT / pid
        assert (folder / "panel.json").is_file(), f"{pid} missing panel.json"
        assert (folder / "index.html").is_file(), f"{pid} missing index.html"
        assert (folder / "panel.sample.json").is_file(), f"{pid} missing panel.sample.json (#2294)"


@pytest.mark.parametrize("pid", sorted(EXPECTED_TYPES))
def test_descriptor_parses_as_core_preview_panel(pid: str) -> None:
    # PlotArtifact parses without injecting it: it is a core-reserved sentinel.
    types = _registered_types()
    descriptor, notes = parse_descriptor(
        BUILTIN_ROOT / pid, owner_kind=OwnerKind.CORE, owner_name="scistudio", registered_types=types
    )
    assert descriptor.id == pid
    assert descriptor.api_version == "1.0"
    assert descriptor.contexts == ("preview",)
    assert descriptor.types == (EXPECTED_TYPES[pid],)
    assert descriptor.entry == "index.html"
    # No blocking notes; unpinned-CDN informational notes are not expected either.
    assert [n for n in notes if "unpinned" in n] == []


@pytest.mark.parametrize("pid", sorted(EXPECTED_TYPES))
def test_panel_references_only_local_assets(pid: str) -> None:
    # FR-042: raises on any off-allowlist external reference.
    assert validate_external_references(BUILTIN_ROOT / pid) == []


@pytest.mark.parametrize("pid", sorted(EXPECTED_TYPES))
def test_sample_is_well_formed(pid: str) -> None:
    sample = json.loads((BUILTIN_ROOT / pid / "panel.sample.json").read_text())
    assert sample["context"] == "preview"
    assert isinstance(sample.get("input"), dict)
    assert isinstance(sample.get("reads"), dict) and sample["reads"], f"{pid} sample needs reads"
    valid_ops = {
        "metadata",
        "table.page",
        "table.xy",
        "array.plane",
        "array.tile",
        "series.points",
        "text.chunk",
        "artifact.info",
        "artifact.file",
        "composite.slots",
        "collection.items",
    }
    assert set(sample["reads"]).issubset(valid_ops), f"{pid} sample has unknown read ops"


def test_base_fallback_keeps_the_lowest_priority() -> None:
    descriptor, _ = parse_descriptor(
        BUILTIN_ROOT / "core.base.fallback",
        owner_kind=OwnerKind.CORE,
        owner_name="scistudio",
        registered_types=_registered_types(),
    )
    assert descriptor.priority == -100


def test_registry_panels_discovered_as_core_tier() -> None:
    registry = discover_panels()
    for pid in REGISTRY_DISCOVERABLE:
        panel = registry.get(pid)
        assert panel is not None, f"{pid} not discovered"
        assert panel.owner_kind is OwnerKind.CORE
        assert "preview" in panel.contexts


# ADR-054 Phase B / FR-041: the two built-in interactive windows rewritten as
# core-tier interactive panels. They declare the `interactive` context and no
# preview types (types are a preview-only requirement).
INTERACTIVE_PANELS = ("core.interactive.data_router", "core.interactive.pair_editor")


@pytest.mark.parametrize("pid", INTERACTIVE_PANELS)
def test_interactive_panel_folder_and_descriptor(pid: str) -> None:
    folder = BUILTIN_ROOT / pid
    assert (folder / "panel.json").is_file(), f"{pid} missing panel.json"
    assert (folder / "index.html").is_file(), f"{pid} missing index.html"
    assert (folder / "panel.sample.json").is_file(), f"{pid} missing panel.sample.json (#2294)"

    descriptor, notes = parse_descriptor(
        folder, owner_kind=OwnerKind.CORE, owner_name="scistudio", registered_types=_registered_types()
    )
    assert descriptor.id == pid
    assert descriptor.contexts == ("interactive",)
    assert descriptor.types == ()  # interactive panels bind no preview type
    assert descriptor.entry == "index.html"
    assert [n for n in notes if "unpinned" in n] == []


@pytest.mark.parametrize("pid", INTERACTIVE_PANELS)
def test_interactive_panel_references_only_local_assets(pid: str) -> None:
    # FR-042 / SC-007: only the SDK and the panel's own files, no network host.
    assert validate_external_references(BUILTIN_ROOT / pid) == []


@pytest.mark.parametrize("pid", INTERACTIVE_PANELS)
def test_interactive_sample_is_well_formed(pid: str) -> None:
    sample = json.loads((BUILTIN_ROOT / pid / "panel.sample.json").read_text())
    assert sample["context"] == "interactive"
    assert isinstance(sample.get("input"), dict) and sample["input"], f"{pid} sample needs a payload"


def test_interactive_panels_discovered_as_core_tier_interactive() -> None:
    registry = discover_panels()
    for pid in INTERACTIVE_PANELS:
        panel = registry.get(pid)
        assert panel is not None, f"{pid} not discovered"
        assert panel.owner_kind is OwnerKind.CORE
        assert "interactive" in panel.contexts


def test_block_manifests_resolve_to_the_registered_interactive_panels() -> None:
    # FR-023: the block's PanelManifest now resolves to a real registered
    # interactive panel — not the compiled window and not the legacy allowlist.
    from scistudio.blocks.base.interactive import PanelManifest
    from scistudio.panels.validation import validate_interactive_panel

    registry = discover_panels()
    for pid in INTERACTIVE_PANELS:
        validate_interactive_panel(PanelManifest(panel_id=pid), registry)


def test_panels_shadow_the_legacy_core_previewers() -> None:
    # FR-007: a panel and a legacy previewer sharing an id at the same tier resolve
    # to the panel; the legacy spec is shadowed.
    legacy_ids = {spec.previewer_id for spec in core_previewer_specs()}
    assert REGISTRY_DISCOVERABLE.issubset(legacy_ids)

    from scistudio.panels.router import merge_candidates

    preview = PreviewerRegistry()
    preview.load_core()
    panels = discover_panels()
    merged = merge_candidates(panels=panels.panels, shadowed_panels=panels.shadowed, legacy_specs=preview.all_specs())
    for pid in REGISTRY_DISCOVERABLE:
        winners = [s for s in merged.routable if s.previewer_id == pid]
        assert winners, f"{pid} not routable"
        assert all(getattr(s, "panel", None) for s in winners), f"{pid} legacy spec not shadowed by panel"


def test_core_previews_share_the_public_presentation_components() -> None:
    """Core shells must import the same host-independent components as MiniApps."""
    sdk = BUILTIN_ROOT.parent / "sdk" / "1"
    exports = (sdk / "renderers.js").read_text()
    for panel_id in EXPECTED_TYPES:
        shell = (BUILTIN_ROOT / panel_id / "panel.js").read_text()
        kind = panel_id.split(".")[1]
        module = f"renderer-{kind}.js"
        assert module in shell
        assert module in exports
        presentation = (sdk / module).read_text()
        assert "window.scistudio" not in presentation
        assert "api.read(" not in presentation
        assert "api.save(" not in presentation
        assert "api.open(" not in presentation
        assert "<iframe" not in presentation
        assert "renderers.css" in (BUILTIN_ROOT / panel_id / "index.html").read_text()
