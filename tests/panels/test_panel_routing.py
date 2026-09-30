"""Panel candidates share one ADR-048 ladder and one namespace (#2465, #2493)."""

from dataclasses import replace

import pytest
from tests.panels.conftest import core_panels

from scistudio.panels.models import (
    OwnerKind,
    PreviewTarget,
    RoutingAmbiguityError,
    TargetKind,
    UnknownPreviewerError,
)
from scistudio.panels.registry import PanelRegistry
from scistudio.panels.router import PanelRouter, merge_candidates, specificity_chain

IMAGE = PreviewTarget(
    kind=TargetKind.DATA_REF, ref="r", recorded_type="Image", type_chain=("DataObject", "Array", "Image")
)
IMAGES = PreviewTarget(
    kind=TargetKind.COLLECTION_REF, ref="c", collection_item_type="Image", type_chain=("DataObject", "Array", "Image")
)


def _panel(runtime, panel_id="lab.text", **fields):
    return replace(runtime.get_panel_service().panel("lab.text"), id=panel_id, **fields)


def _router(panels, *, choices=None, core=False):
    registry = core_panels() if core else PanelRegistry()
    for panel in panels:
        registry.register(panel)
    merged = merge_candidates(
        panels=registry.panels, shadowed_panels=registry.shadowed, panel_diagnostics=registry.diagnostics
    )
    return PanelRouter(merged.routable, choices=choices), merged


def test_a_multi_claim_panel_routes_every_claim(panel_runtime):
    runtime, _ = panel_runtime
    panel = _panel(runtime, types=("Text", "Collection[Image]"))
    router, merged = _router([panel])
    assert merged.panels == {"lab.text": panel}
    spec = router.resolve(IMAGES)
    assert spec.panel is not None and spec.target_type == "Image"
    chosen, _ = _router([panel], choices={"Image": "lab.text"})
    assert chosen.resolve(IMAGES) == spec


def test_a_higher_tier_panel_shadows_the_same_id(panel_runtime):
    runtime, _ = panel_runtime
    user = _panel(runtime, owner_kind=OwnerKind.USER)
    project = _panel(runtime, owner_kind=OwnerKind.PROJECT)
    router, merged = _router([user, project])
    assert merged.panels == {"lab.text": project}
    assert merged.shadowed_panels == (user,)
    assert (merged.by_id["lab.text"], False) in merged.catalog_specs()
    assert any(shadowed and spec.owner_kind is OwnerKind.USER for spec, shadowed in merged.catalog_specs())
    target = PreviewTarget(kind=TargetKind.DATA_REF, ref="t", recorded_type="Text", type_chain=("DataObject", "Text"))
    assert router.resolve(target).owner_kind is OwnerKind.PROJECT


def test_an_exact_type_beats_a_parent_type_across_tiers(panel_runtime):
    runtime, _ = panel_runtime
    parent = _panel(runtime, "project.array", types=("Array",), owner_kind=OwnerKind.PROJECT)
    exact = _panel(runtime, "pkg.image", types=("Image",), owner_kind=OwnerKind.PACKAGE)
    router, _ = _router([parent, exact])
    assert router.resolve(IMAGE).previewer_id == "pkg.image"
    other = _panel(runtime, "pkg.other", types=("Image",), owner_kind=OwnerKind.PACKAGE)
    tied, _ = _router([parent, exact, other])
    with pytest.raises(RoutingAmbiguityError):
        tied.resolve(IMAGE)


@pytest.mark.parametrize("chosen", ["lab.text", "pkg.image"])
def test_a_choice_names_any_panel(panel_runtime, chosen):
    runtime, _ = panel_runtime
    project = _panel(runtime, types=("Image",), owner_kind=OwnerKind.PROJECT, priority=50)
    package = _panel(runtime, "pkg.image", types=("Image",), owner_kind=OwnerKind.PACKAGE)
    router, _ = _router([project, package], choices={"Image": chosen})
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
    assert service.read_session(envelope.session_id).session_id == envelope.session_id
    core = service.route(target, {"core_only": True})
    assert core.owner_kind is OwnerKind.CORE


def test_without_a_project_panel_the_core_panel_serves_the_type(panel_runtime):
    runtime, _ = panel_runtime
    service = runtime.get_panel_service()
    runtime.test_panels[0] = PanelRegistry()
    service.rescan(force=True)
    target = runtime.resolve_session_target(PreviewTarget(kind=TargetKind.DATA_REF, ref="data-a"))
    envelope = service.create_preview_session(target)
    assert envelope.previewer_id == "core.text.basic"
    assert envelope.kind.value == "panel"
    assert service.patch_session(envelope.session_id, {"page": 1}).session_id == envelope.session_id


def test_a_collection_child_routes_to_the_panel_claiming_its_type(panel_runtime):
    # A collection preview opens its item through the one router, so the item
    # lands in the panel that claims its type.
    from scistudio.panels.targets import register_collection

    runtime, _ = panel_runtime
    service = runtime.get_panel_service()
    group = register_collection(runtime, {"count": 1, "item_type": "Text", "items": [{"data_ref": "data-a"}]})
    target = PreviewTarget(kind=TargetKind.COLLECTION_REF, ref=group["collection_ref"], collection_item_type="Text")
    envelope = service.create_preview_session(target, {"_collection_items": group["items"], "_collection_count": 1})
    assert envelope.previewer_id == "core.collection.basic"
    child = service.read_resource(envelope.session_id, "item:0", {"ref": "data-a", "type_name": "Text"})
    assert child["kind"] == "panel" and child["panel"]["id"] == "lab.text"


def test_every_routing_candidate_is_a_panel_claim(panel_runtime):
    runtime, _ = panel_runtime
    candidates = runtime.get_panel_service().all_specs()
    assert candidates
    assert all(spec.panel is not None for spec in candidates)
    assert {"core.text.basic", "core.collection.basic", "lab.text"} <= {spec.previewer_id for spec in candidates}
