"""Panel/legacy candidates share the ADR-048 ladder and namespace."""

from dataclasses import replace

import pytest

from scistudio.panels.registry import PanelRegistry
from scistudio.previewers.models import OwnerKind, PreviewerSpec, PreviewTarget, RoutingAmbiguityError, TargetKind
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter


def test_same_tier_panel_shadows_legacy_and_multi_claims_route(panel_runtime):
    runtime, _ = panel_runtime
    panel = runtime.get_preview_service().registry.panels.get("lab.text")
    registry = PreviewerRegistry()
    registry.register(PreviewerSpec("lab.text", OwnerKind.PROJECT, "project", "Text"))
    panels = PanelRegistry()
    panels.register(replace(panel, types=("Text", "Collection[Image]")))
    registry.install_panels(panels)
    assert registry.catalog_specs()[1][1] is True
    spec = PreviewRouter(registry).resolve(
        PreviewTarget(kind=TargetKind.COLLECTION_REF, ref="r", collection_item_type="Image")
    )
    assert spec.panel is not None and spec.target_type == "Image"
    registry.set_previewer_choices({"Image": "lab.text"})
    assert (
        PreviewRouter(registry).resolve(
            PreviewTarget(kind=TargetKind.COLLECTION_REF, ref="r", collection_item_type="Image")
        )
        == spec
    )


def test_exact_lower_tier_beats_parent_higher_tier_and_ties_error(panel_runtime):
    runtime, _ = panel_runtime
    panel = runtime.get_preview_service().registry.panels.get("lab.text")
    panels = PanelRegistry()
    panels.register(replace(panel, types=("Array",)))
    registry = PreviewerRegistry()
    registry.register(PreviewerSpec("pkg.image", OwnerKind.PACKAGE, "pkg", "Image"))
    registry.install_panels(panels)
    target = PreviewTarget(
        kind=TargetKind.DATA_REF, ref="r", recorded_type="Image", type_chain=("DataObject", "Array", "Image")
    )
    assert PreviewRouter(registry).resolve(target).previewer_id == "pkg.image"
    registry.register(PreviewerSpec("pkg.other", OwnerKind.PACKAGE, "pkg", "Image"))
    with pytest.raises(RoutingAmbiguityError):
        PreviewRouter(registry).resolve(target)


def test_preview_envelope_dispatch_never_calls_python(panel_runtime):
    runtime, _ = panel_runtime
    target = runtime.resolve_session_target(PreviewTarget(kind=TargetKind.DATA_REF, ref="data-a"))
    envelope = runtime.get_preview_service().sessions.create_session(target)
    assert envelope.kind.value == "panel"
    assert envelope.to_dict()["panel"] == {"id": "lab.text", "api_version": "1.0"}
    core = runtime.get_preview_service().sessions._select_spec(target, {"core_only": True})
    assert core.owner_kind is OwnerKind.CORE
