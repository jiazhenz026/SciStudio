"""Package-owned spectroscopy previewer registration."""

from __future__ import annotations

from typing import Any

from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewEnvelope,
    PreviewerSpec,
    PreviewMetadata,
    PreviewRequest,
)

OWNER_NAME = "scistudio-blocks-spectroscopy"
SPECTRUM_PREVIEWER_ID = "spectroscopy.spectrum.viewer"
SPECTRAL_DATASET_PREVIEWER_ID = "spectroscopy.spectral_dataset.viewer"


def spectrum_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Return a lightweight core-compatible Spectrum preview envelope."""

    record_md = request.query.get("_record_metadata")
    metadata = record_md if isinstance(record_md, dict) else {}
    payload: dict[str, Any] = {
        "index_name": "lambda",
        "value_name": "intensity",
        "metadata": metadata,
        "display": "line",
        "export": ("figure", "visible_points"),
    }
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.SERIES,
        payload=payload,
        metadata=PreviewMetadata(complete=True, extra={"axis": "lambda", "value": "intensity"}),
    )


def spectral_dataset_provider(request: PreviewRequest) -> PreviewEnvelope:
    """Return a lightweight SpectralDataset slot-inventory preview envelope."""

    record_md = request.query.get("_record_metadata")
    metadata = record_md if isinstance(record_md, dict) else {}
    payload: dict[str, Any] = {
        "slots": {"index": "DataFrame", "spectra": "DataFrame"},
        "metadata": metadata,
        "display": "spectral_dataset",
        "export": ("figure", "visible_spectra", "selected_index", "grouped_summary"),
    }
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.COMPOSITE,
        payload=payload,
        metadata=PreviewMetadata(complete=True, extra={"slots": ["index", "spectra"]}),
    )


def get_previewers() -> list[PreviewerSpec]:
    """Return package previewer specs for ADR-048 discovery."""

    return [
        PreviewerSpec(
            previewer_id=SPECTRUM_PREVIEWER_ID,
            owner_kind=OwnerKind.PACKAGE,
            owner_name=OWNER_NAME,
            target_type="Spectrum",
            supports_collection=False,
            priority=100,
            capabilities=("plot", "zoom", "hover", "metadata", "export"),
            backend_provider=spectrum_provider,
        ),
        PreviewerSpec(
            previewer_id=SPECTRAL_DATASET_PREVIEWER_ID,
            owner_kind=OwnerKind.PACKAGE,
            owner_name=OWNER_NAME,
            target_type="SpectralDataset",
            supports_collection=False,
            priority=100,
            capabilities=("table", "filter", "group", "plot", "diagnostics", "export"),
            backend_provider=spectral_dataset_provider,
        ),
    ]


__all__ = [
    "OWNER_NAME",
    "SPECTRAL_DATASET_PREVIEWER_ID",
    "SPECTRUM_PREVIEWER_ID",
    "get_previewers",
    "spectral_dataset_provider",
    "spectrum_provider",
]
