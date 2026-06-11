"""Router precedence tests (ADR-048 §3 / FR-003 / FR-004 / FR-005)."""

from __future__ import annotations

import pytest

from scistudio.previewers.fallbacks import core_previewer_specs, dataframe_previewer
from scistudio.previewers.models import (
    OwnerKind,
    PreviewerSpec,
    PreviewTarget,
    RoutingAmbiguityError,
    TargetKind,
    UnknownTargetError,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter


def _spec(
    previewer_id: str,
    owner: OwnerKind,
    target: str,
    *,
    collection: bool = False,
    priority: int = 0,
) -> PreviewerSpec:
    return PreviewerSpec(
        previewer_id=previewer_id,
        owner_kind=owner,
        owner_name=owner.value,
        target_type=target,
        supports_collection=collection,
        priority=priority,
        backend_provider=dataframe_previewer,
    )


def _registry(*specs: PreviewerSpec, with_core: bool = True) -> PreviewerRegistry:
    reg = PreviewerRegistry()
    if with_core:
        for s in core_previewer_specs():
            reg.register(s)
    for s in specs:
        reg.register(s)
    return reg


def _data_target(recorded: str, chain: tuple[str, ...]) -> PreviewTarget:
    return PreviewTarget(kind=TargetKind.DATA_REF, ref="r", recorded_type=recorded, type_chain=chain)


def _collection_target(item: str, chain: tuple[str, ...]) -> PreviewTarget:
    return PreviewTarget(
        kind=TargetKind.COLLECTION_REF,
        ref="c",
        collection_item_type=item,
        type_chain=chain,
    )


def test_core_fallback_for_plain_array() -> None:
    router = PreviewRouter(_registry())
    spec = router.resolve(_data_target("Array", ("DataObject", "Array")))
    assert spec.previewer_id == "core.array.basic"


def test_package_exact_wins_over_core_parent() -> None:
    """US2: Image -> package previewer; plain Array -> core (FR-003 tier 4 vs 8)."""
    pkg = _spec("pkg.image", OwnerKind.PACKAGE, "Image")
    router = PreviewRouter(_registry(pkg))
    image = router.resolve(_data_target("Image", ("DataObject", "Array", "Image")))
    assert image.previewer_id == "pkg.image"
    array = router.resolve(_data_target("Array", ("DataObject", "Array")))
    assert array.previewer_id == "core.array.basic"


def test_project_exact_wins_over_package_exact() -> None:
    """US3 scenario 1: project exact beats package exact (FR-003 tier 2 vs 4)."""
    pkg = _spec("pkg.mytype", OwnerKind.PACKAGE, "MyType")
    proj = _spec("project.mytype", OwnerKind.PROJECT, "MyType")
    router = PreviewRouter(_registry(pkg, proj))
    spec = router.resolve(_data_target("MyType", ("DataObject", "MyType")))
    assert spec.previewer_id == "project.mytype"


def test_parent_fallback_when_no_exact() -> None:
    """A child type with no exact previewer falls back to its parent's (FR-003 tier 6)."""
    pkg_parent = _spec("pkg.array", OwnerKind.PACKAGE, "Array")
    router = PreviewRouter(_registry(pkg_parent))
    # FancyImage has no exact previewer; Array (parent) does, at package tier.
    spec = router.resolve(_data_target("FancyImage", ("DataObject", "Array", "FancyImage")))
    assert spec.previewer_id == "pkg.array"


def test_closer_parent_preferred() -> None:
    pkg_array = _spec("pkg.array", OwnerKind.PACKAGE, "Array")
    pkg_image = _spec("pkg.image", OwnerKind.PACKAGE, "Image")
    router = PreviewRouter(_registry(pkg_array, pkg_image))
    # Chain: DataObject -> Array -> Image -> FancyImage. Image is the closer
    # parent and must win over Array.
    spec = router.resolve(_data_target("FancyImage", ("DataObject", "Array", "Image", "FancyImage")))
    assert spec.previewer_id == "pkg.image"


def test_priority_breaks_tie_within_tier() -> None:
    low = _spec("pkg.low", OwnerKind.PACKAGE, "Image", priority=1)
    high = _spec("pkg.high", OwnerKind.PACKAGE, "Image", priority=9)
    router = PreviewRouter(_registry(low, high))
    spec = router.resolve(_data_target("Image", ("DataObject", "Array", "Image")))
    assert spec.previewer_id == "pkg.high"


def test_unresolved_priority_tie_raises_ambiguity() -> None:
    a = _spec("pkg.a", OwnerKind.PACKAGE, "Image", priority=5)
    b = _spec("pkg.b", OwnerKind.PACKAGE, "Image", priority=5)
    router = PreviewRouter(_registry(a, b))
    with pytest.raises(RoutingAmbiguityError) as exc:
        router.resolve(_data_target("Image", ("DataObject", "Array", "Image")))
    assert set(exc.value.detail["candidates"]) == {"pkg.a", "pkg.b"}


def test_project_default_resolves_tie() -> None:
    """US3 scenario 3: a declared project default breaks an otherwise-ambiguous tie."""
    a = _spec("project.a", OwnerKind.PROJECT, "MyType", priority=5)
    b = _spec("project.b", OwnerKind.PROJECT, "MyType", priority=5)
    reg = _registry(a, b)
    reg.set_project_default("MyType", "project.b")
    router = PreviewRouter(reg)
    spec = router.resolve(_data_target("MyType", ("DataObject", "MyType")))
    assert spec.previewer_id == "project.b"


def test_collection_routes_to_collection_capable_previewer() -> None:
    """US4 scenario 1: a collection-capable package previewer wins for Collection[Image]."""
    coll = _spec("pkg.image.collection", OwnerKind.PACKAGE, "Image", collection=True)
    item = _spec("pkg.image", OwnerKind.PACKAGE, "Image", collection=False)
    router = PreviewRouter(_registry(coll, item))
    spec = router.resolve(_collection_target("Image", ("DataObject", "Array", "Image")))
    assert spec.previewer_id == "pkg.image.collection"


def test_collection_falls_back_to_core_collection() -> None:
    """US4 scenario 2: no collection-specific previewer -> core collection fallback."""
    router = PreviewRouter(_registry())
    spec = router.resolve(_collection_target("Image", ("DataObject", "Array", "Image")))
    assert spec.previewer_id == "core.collection.basic"


def test_collection_with_item_previewer_still_falls_back_to_core_collection() -> None:
    """Regression (ADR-048 FR-003 / US4 scenario 2): a single-item previewer must
    NOT capture a collection target. Collection[Image] with an Image *item*
    previewer present (e.g. the imaging package's single-image viewer) but no
    collection-capable previewer must resolve to the core collection fallback,
    not the single-image viewer."""
    item = _spec("pkg.image", OwnerKind.PACKAGE, "Image", collection=False)
    router = PreviewRouter(_registry(item))
    spec = router.resolve(_collection_target("Image", ("DataObject", "Array", "Image")))
    assert spec.previewer_id == "core.collection.basic"


def test_collection_with_item_previewer_and_no_core_raises() -> None:
    """A collection that has only a single-item previewer and no core collection
    fallback must raise UnknownTargetError rather than mis-render as a single item."""
    item = _spec("pkg.image", OwnerKind.PACKAGE, "Image", collection=False)
    router = PreviewRouter(_registry(item, with_core=False))
    with pytest.raises(UnknownTargetError):
        router.resolve(_collection_target("Image", ("DataObject", "Array", "Image")))


def test_unknown_target_with_no_core_raises() -> None:
    router = PreviewRouter(_registry(with_core=False))
    with pytest.raises(UnknownTargetError):
        router.resolve(_data_target("Nothing", ("Nothing",)))


def test_base_fallback_for_unregistered_type() -> None:
    """An unregistered base type still resolves to the universal core fallback (tier 8)."""
    router = PreviewRouter(_registry())
    spec = router.resolve(_data_target("MysteryThing", ("DataObject", "MysteryThing")))
    assert spec.previewer_id == "core.base.fallback"
