"""Package-owned spectroscopy previewers (ADR-048).

Registers two ``PreviewerSpec`` records via ``get_previewers()``:

- ``spectroscopy.spectrum.viewer`` -> ``Spectrum`` (kind SERIES).
- ``spectroscopy.spectral_dataset.viewer`` -> ``SpectralDataset`` (kind COMPOSITE).

Both ship the same vanilla-ESM ``assets/viewer.js`` and use ``priority=100`` so
the package specs win exact routing yet degrade to the core series/composite
renderers when the package is absent.
"""

from __future__ import annotations

from pathlib import Path

from scistudio.previewers.models import (
    PREVIEWER_API_VERSION,
    FrontendManifest,
    OwnerKind,
    PreviewerSpec,
)
from scistudio_blocks_spectroscopy.previewers.providers import (
    spectral_dataset_provider,
    spectrum_provider,
)

SPECTRUM_PREVIEWER_ID = "spectroscopy.spectrum.viewer"
SPECTRAL_DATASET_PREVIEWER_ID = "spectroscopy.spectral_dataset.viewer"
OWNER_NAME = "scistudio-blocks-spectroscopy"
VIEWER_BUNDLE_VERSION = "0.1.0"
_VIEWER_FILE = "viewer.js"
_ASSET_ROOT = str(Path(__file__).resolve().parent / "assets")


def _module_url(previewer_id: str) -> str:
    return f"/api/previews/assets/{previewer_id}/{_VIEWER_FILE}"


def _frontend_manifest(previewer_id: str) -> FrontendManifest:
    return FrontendManifest(
        previewer_id=previewer_id,
        module_url=_module_url(previewer_id),
        export_name="default",
        css=(),
        version=VIEWER_BUNDLE_VERSION,
        api_version=PREVIEWER_API_VERSION,
        asset_root=_ASSET_ROOT,
    )


def get_previewers() -> list[PreviewerSpec]:
    """Return the package's previewer specs for ``scistudio.previewers``."""
    return [
        PreviewerSpec(
            previewer_id=SPECTRUM_PREVIEWER_ID,
            owner_kind=OwnerKind.PACKAGE,
            owner_name=OWNER_NAME,
            target_type="Spectrum",
            supports_collection=False,
            priority=100,
            capabilities=("plot", "navigate", "diagnostics", "export"),
            backend_provider=spectrum_provider,
            frontend_manifest=_frontend_manifest(SPECTRUM_PREVIEWER_ID),
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
            frontend_manifest=_frontend_manifest(SPECTRAL_DATASET_PREVIEWER_ID),
        ),
    ]


__all__ = [
    "OWNER_NAME",
    "SPECTRAL_DATASET_PREVIEWER_ID",
    "SPECTRUM_PREVIEWER_ID",
    "VIEWER_BUNDLE_VERSION",
    "get_previewers",
    "spectral_dataset_provider",
    "spectrum_provider",
]
