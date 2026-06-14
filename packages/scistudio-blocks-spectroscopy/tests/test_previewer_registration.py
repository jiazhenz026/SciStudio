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

from scistudio.previewers.models import OwnerKind


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
