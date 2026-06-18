"""Previewer registration tests (skeleton-safe).

Asserts the two package previewer specs are well-formed and route to the
correct target types. Provider execution against live storage is covered by
implementation-phase tests.
"""

from __future__ import annotations

from scistudio_blocks_spectroscopy.previewers import (
    SPECTRAL_DATASET_PREVIEWER_ID,
    SPECTRUM_PREVIEWER_ID,
    get_previewers,
)

from scistudio.previewers.models import (
    OwnerKind,
    PreviewTarget,
    TargetKind,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter

_SPECTRUM_CHAIN = ("DataObject", "Series", "Spectrum")
_DATASET_CHAIN = ("DataObject", "CompositeData", "SpectralDataset")


def _router() -> PreviewRouter:
    registry = PreviewerRegistry()
    for spec in get_previewers():
        assert registry.register(spec)
    return PreviewRouter(registry)


def test_get_previewers_returns_two_specs() -> None:
    specs = get_previewers()
    assert {s.previewer_id for s in specs} == {
        SPECTRUM_PREVIEWER_ID,
        SPECTRAL_DATASET_PREVIEWER_ID,
    }


def test_previewer_specs_are_package_owned_and_callable() -> None:
    by_id = {s.previewer_id: s for s in get_previewers()}
    spectrum = by_id[SPECTRUM_PREVIEWER_ID]
    dataset = by_id[SPECTRAL_DATASET_PREVIEWER_ID]

    assert spectrum.target_type == "Spectrum"
    assert dataset.target_type == "SpectralDataset"
    for spec in (spectrum, dataset):
        assert spec.owner_kind is OwnerKind.PACKAGE
        assert spec.owner_name == "scistudio-blocks-spectroscopy"
        assert spec.priority > 0
        assert callable(spec.backend_provider)
        assert spec.frontend_manifest is not None
        assert spec.frontend_manifest.module_url == (f"/api/previews/assets/{spec.previewer_id}/viewer.js")


def test_top_level_reexports_get_previewers() -> None:
    import scistudio_blocks_spectroscopy as pkg

    assert {s.previewer_id for s in pkg.get_previewers()} == {
        SPECTRUM_PREVIEWER_ID,
        SPECTRAL_DATASET_PREVIEWER_ID,
    }


def test_exact_spectrum_ref_routes_to_spectrum_previewer() -> None:
    """SC-004: an exact ``Spectrum`` ref routes to the spectrum previewer."""
    target = PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="r",
        recorded_type="Spectrum",
        type_chain=_SPECTRUM_CHAIN,
    )
    spec = _router().resolve(target)
    assert spec.previewer_id == SPECTRUM_PREVIEWER_ID
    assert spec.target_type == "Spectrum"


def test_exact_dataset_ref_routes_to_dataset_previewer() -> None:
    """SC-004: an exact ``SpectralDataset`` ref routes to the dataset previewer."""
    target = PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="r",
        recorded_type="SpectralDataset",
        type_chain=_DATASET_CHAIN,
    )
    spec = _router().resolve(target)
    assert spec.previewer_id == SPECTRAL_DATASET_PREVIEWER_ID
    assert spec.target_type == "SpectralDataset"


def test_routing_does_not_cross_wire_the_two_previewers() -> None:
    """SC-004: each previewer only routes for its own exact type."""
    router = _router()
    spectrum_target = PreviewTarget(
        kind=TargetKind.DATA_REF, ref="r", recorded_type="Spectrum", type_chain=_SPECTRUM_CHAIN
    )
    dataset_target = PreviewTarget(
        kind=TargetKind.DATA_REF, ref="r", recorded_type="SpectralDataset", type_chain=_DATASET_CHAIN
    )
    assert router.resolve(spectrum_target).previewer_id != router.resolve(dataset_target).previewer_id
