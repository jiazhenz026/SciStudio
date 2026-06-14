from __future__ import annotations

from scistudio_blocks_spectroscopy.previewers import (
    OWNER_NAME,
    SPECTRAL_DATASET_PREVIEWER_ID,
    SPECTRUM_PREVIEWER_ID,
    get_previewers,
)

from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewLimits,
    PreviewRequest,
    PreviewTarget,
    TargetKind,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter


def test_package_registers_exact_spectrum_and_dataset_previewers() -> None:
    specs = {spec.previewer_id: spec for spec in get_previewers()}

    assert set(specs) == {SPECTRUM_PREVIEWER_ID, SPECTRAL_DATASET_PREVIEWER_ID}
    assert specs[SPECTRUM_PREVIEWER_ID].owner_kind is OwnerKind.PACKAGE
    assert specs[SPECTRUM_PREVIEWER_ID].owner_name == OWNER_NAME
    assert specs[SPECTRUM_PREVIEWER_ID].target_type == "Spectrum"
    assert specs[SPECTRUM_PREVIEWER_ID].supports_collection is False
    assert specs[SPECTRUM_PREVIEWER_ID].backend_provider is not None
    assert specs[SPECTRAL_DATASET_PREVIEWER_ID].target_type == "SpectralDataset"


def test_router_selects_package_previewers_for_exact_types() -> None:
    registry = PreviewerRegistry()
    registry.load_core()
    for spec in get_previewers():
        assert registry.register(spec)
    router = PreviewRouter(registry)

    spectrum_target = PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="data/spectrum",
        recorded_type="Spectrum",
        type_chain=("DataObject", "Series", "Spectrum"),
    )
    dataset_target = PreviewTarget(
        kind=TargetKind.DATA_REF,
        ref="data/dataset",
        recorded_type="SpectralDataset",
        type_chain=("DataObject", "CompositeData", "SpectralDataset"),
    )

    assert router.resolve(spectrum_target).previewer_id == SPECTRUM_PREVIEWER_ID
    assert router.resolve(dataset_target).previewer_id == SPECTRAL_DATASET_PREVIEWER_ID


def test_backend_providers_return_core_compatible_envelopes() -> None:
    for spec in get_previewers():
        assert callable(spec.backend_provider)
        target = PreviewTarget(
            kind=TargetKind.DATA_REF,
            ref="data/object",
            recorded_type=spec.target_type,
            type_chain=("DataObject", spec.target_type),
        )
        envelope = spec.backend_provider(  # type: ignore[misc]
            PreviewRequest(
                target=target,
                spec=spec,
                query={"_record_metadata": {"sample": "A"}},
                data_access=None,  # type: ignore[arg-type]
                limits=PreviewLimits(),
            )
        )

        assert envelope.previewer_id == spec.previewer_id
        assert envelope.metadata.complete is True
        assert envelope.payload["metadata"] == {"sample": "A"}
        assert envelope.kind in {EnvelopeKind.SERIES, EnvelopeKind.COMPOSITE}
