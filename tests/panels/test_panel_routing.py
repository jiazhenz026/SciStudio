"""Panel and legacy candidates share one ADR-048 ladder and one namespace (#2465)."""

from dataclasses import replace

import pytest

from scistudio.panels.registry import PanelRegistry
from scistudio.panels.router import PanelRouter, merge_candidates, specificity_chain
from scistudio.previewers.fallbacks import core_previewer_specs
from scistudio.previewers.models import (
    OwnerKind,
    PreviewerSpec,
    PreviewTarget,
    RoutingAmbiguityError,
    TargetKind,
    UnknownPreviewerError,
)
from scistudio.previewers.registry import PreviewerRegistry

IMAGE = PreviewTarget(
    kind=TargetKind.DATA_REF, ref="r", recorded_type="Image", type_chain=("DataObject", "Array", "Image")
)
IMAGES = PreviewTarget(
    kind=TargetKind.COLLECTION_REF, ref="c", collection_item_type="Image", type_chain=("DataObject", "Array", "Image")
)


def _panel(runtime, panel_id="lab.text", **fields):
    return replace(runtime.get_panel_service().panel("lab.text"), id=panel_id, **fields)


def _router(panels, *legacy, choices=None, core=False):
    registry = PreviewerRegistry()
    if core:
        registry.load_core()
    for spec in legacy:
        registry.register(spec)
    merged = merge_candidates(
        panels={panel.id: panel for panel in panels},
        legacy_specs=registry.all_specs(),
        legacy_shadowed=registry.shadowed_specs(),
    )
    return PanelRouter(merged.routable, choices=choices, project_default=registry.project_default_for), merged


def test_same_tier_panel_shadows_legacy_and_multi_claims_route(panel_runtime):
    runtime, _ = panel_runtime
    panel = _panel(runtime, types=("Text", "Collection[Image]"))
    legacy = PreviewerSpec("lab.text", OwnerKind.PROJECT, "project", "Text")
    router, merged = _router([panel], legacy)
    assert (legacy, True) in merged.catalog_specs()
    spec = router.resolve(IMAGES)
    assert spec.panel is not None and spec.target_type == "Image"
    chosen, _ = _router([panel], choices={"Image": "lab.text"})
    assert chosen.resolve(IMAGES) == spec


def test_higher_tier_legacy_shadows_a_panel_with_the_same_id(panel_runtime):
    runtime, _ = panel_runtime
    panel = _panel(runtime, owner_kind=OwnerKind.USER)
    legacy = PreviewerSpec("lab.text", OwnerKind.PROJECT, "project", "Text")
    router, merged = _router([panel], legacy)
    assert merged.panels == {}
    assert merged.shadowed_panels == (panel,)
    target = PreviewTarget(kind=TargetKind.DATA_REF, ref="t", recorded_type="Text", type_chain=("DataObject", "Text"))
    assert router.resolve(target) is legacy


def test_legacy_exact_type_beats_a_panel_parent_type(panel_runtime):
    runtime, _ = panel_runtime
    panel = _panel(runtime, types=("Array",))
    router, _ = _router([panel], PreviewerSpec("pkg.image", OwnerKind.PACKAGE, "pkg", "Image"))
    assert router.resolve(IMAGE).previewer_id == "pkg.image"
    tied, _ = _router(
        [panel],
        PreviewerSpec("pkg.image", OwnerKind.PACKAGE, "pkg", "Image"),
        PreviewerSpec("pkg.other", OwnerKind.PACKAGE, "pkg", "Image"),
    )
    with pytest.raises(RoutingAmbiguityError):
        tied.resolve(IMAGE)


def test_a_panel_exact_type_beats_a_legacy_parent_type(panel_runtime):
    runtime, _ = panel_runtime
    panel = _panel(runtime, types=("Image",), owner_kind=OwnerKind.PACKAGE)
    router, _ = _router([panel], PreviewerSpec("project.array", OwnerKind.PROJECT, "project", "Array"))
    assert router.resolve(IMAGE).previewer_id == "lab.text"


@pytest.mark.parametrize("chosen", ["lab.text", "pkg.image"])
def test_a_choice_names_a_panel_or_a_legacy_previewer(panel_runtime, chosen):
    runtime, _ = panel_runtime
    panel = _panel(runtime, types=("Image",), owner_kind=OwnerKind.PROJECT, priority=50)
    router, _ = _router(
        [panel], PreviewerSpec("pkg.image", OwnerKind.PACKAGE, "pkg", "Image"), choices={"Image": chosen}
    )
    assert router.resolve(IMAGE).previewer_id == chosen


def test_core_only_and_requested_ids(panel_runtime):
    runtime, _ = panel_runtime
    panel = _panel(runtime, types=("Image", "Collection[Image]"))
    router, _ = _router([panel], core=True)
    assert router.select(IMAGE).previewer_id == "lab.text"
    assert router.select(IMAGE, {"core_only": True}).owner_kind is OwnerKind.CORE
    assert router.select(IMAGES, {"panel_id": "lab.text"}).supports_collection
    assert router.select(IMAGES, {"panel_id": "core.collection.basic"}).target_type == "Collection"
    with pytest.raises(UnknownPreviewerError):
        router.select(IMAGE, {"panel_id": "core.collection.basic"})


def test_a_collection_only_reaches_collection_candidates(panel_runtime):
    runtime, _ = panel_runtime
    item_panel = _panel(runtime, types=("Image",), priority=99)
    router, _ = _router([item_panel], core=True)
    assert router.resolve(IMAGES).previewer_id == "core.collection.basic"
    assert router.resolve(IMAGE).previewer_id == "lab.text"


def test_specificity_chain_is_item_first_for_collections():
    assert specificity_chain(IMAGES) == ["Image", "Array", "DataObject"]
    assert specificity_chain(IMAGE) == ["Image", "Array", "DataObject"]
    assert specificity_chain(PreviewTarget(kind=TargetKind.DATA_REF, ref="x", recorded_type="Text")) == ["Text"]


def test_preview_envelope_dispatch_never_calls_python(panel_runtime):
    runtime, _ = panel_runtime
    service = runtime.get_panel_service()
    target = runtime.resolve_session_target(PreviewTarget(kind=TargetKind.DATA_REF, ref="data-a"))
    envelope = service.create_preview_session(target)
    assert envelope.kind.value == "panel"
    assert envelope.to_dict()["panel"] == {"id": "lab.text", "api_version": "1.0"}
    assert service.sessions.owns(envelope.session_id)
    assert not service.legacy.owns(envelope.session_id)
    assert service.read_session(envelope.session_id).session_id == envelope.session_id
    core = service.route(target, {"core_only": True})
    assert core.owner_kind is OwnerKind.CORE


def test_a_legacy_winner_renders_through_the_legacy_manager(panel_runtime):
    runtime, _ = panel_runtime
    service = runtime.get_panel_service()
    runtime.test_panels[0] = PanelRegistry()
    service.rescan(force=True)
    target = runtime.resolve_session_target(PreviewTarget(kind=TargetKind.DATA_REF, ref="data-a"))
    envelope = service.create_preview_session(target)
    assert envelope.previewer_id == "core.text.basic"
    assert envelope.kind.value != "panel"
    assert service.legacy.owns(envelope.session_id)
    assert service.patch_session(envelope.session_id, {"page": 1}).session_id == envelope.session_id


def test_a_legacy_collection_child_routes_back_to_a_panel(panel_runtime):
    # A legacy collection preview opens its item through the one router, so the
    # item lands in the panel that claims its type.
    from scistudio.panels.targets import register_collection

    runtime, _ = panel_runtime
    service = runtime.get_panel_service()
    group = register_collection(runtime, {"count": 1, "item_type": "Text", "items": [{"data_ref": "data-a"}]})
    target = PreviewTarget(kind=TargetKind.COLLECTION_REF, ref=group["collection_ref"], collection_item_type="Text")
    envelope = service.create_preview_session(target, {"_collection_items": group["items"], "_collection_count": 1})
    assert service.legacy.owns(envelope.session_id)
    child = service.read_resource(envelope.session_id, "item:0", {"ref": "data-a", "type_name": "Text"})
    assert child["kind"] == "panel" and child["panel"]["id"] == "lab.text"


def test_legacy_python_previewers_are_deprecated_fallbacks_only():
    # The legacy registry holds no panels and knows nothing about them.
    registry = PreviewerRegistry()
    for spec in core_previewer_specs():
        registry.register(spec)
    assert not hasattr(registry, "install_panels")
    assert all(spec.panel is None for spec in registry.all_specs())
