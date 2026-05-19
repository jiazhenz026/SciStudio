"""ADR-043 explicit format capability tests for imaging IOBlocks."""

from __future__ import annotations

from scieasy_blocks_imaging.io.load_image import LoadImage
from scieasy_blocks_imaging.io.save_image import SaveImage
from scieasy_blocks_imaging.types import Image


def _capabilities_by_id(block: type) -> dict[str, object]:
    return {capability.id: capability for capability in block.get_format_capabilities()}


def test_load_image_declares_explicit_tiff_and_zarr_capabilities() -> None:
    capabilities = _capabilities_by_id(LoadImage)

    assert set(capabilities) == {
        "scieasy-blocks-imaging.image.tiff.load",
        "scieasy-blocks-imaging.image.zarr.load",
    }
    assert all(not capability.is_synthesized for capability in capabilities.values())

    tiff = capabilities["scieasy-blocks-imaging.image.tiff.load"]
    assert tiff.direction == "load"
    assert tiff.data_type is Image
    assert tiff.format_id == "tiff"
    assert tiff.extensions == (".tif", ".tiff")
    assert tiff.roundtrip_group == "scieasy-blocks-imaging.image.tiff"
    assert tiff.metadata_fidelity.level == "pixel_only"
    assert tiff.metadata_fidelity.typed_meta_fields == ()

    zarr = capabilities["scieasy-blocks-imaging.image.zarr.load"]
    assert zarr.direction == "load"
    assert zarr.data_type is Image
    assert zarr.format_id == "zarr"
    assert zarr.extensions == (".zarr",)
    assert zarr.roundtrip_group == "scieasy-blocks-imaging.image.zarr"
    assert zarr.metadata_fidelity.level == "pixel_only"


def test_save_image_declares_explicit_tiff_and_zarr_capabilities() -> None:
    capabilities = _capabilities_by_id(SaveImage)

    assert set(capabilities) == {
        "scieasy-blocks-imaging.image.tiff.save",
        "scieasy-blocks-imaging.image.zarr.save",
    }
    assert all(not capability.is_synthesized for capability in capabilities.values())

    tiff = capabilities["scieasy-blocks-imaging.image.tiff.save"]
    assert tiff.direction == "save"
    assert tiff.data_type is Image
    assert tiff.format_id == "tiff"
    assert tiff.extensions == (".tif", ".tiff")
    assert tiff.roundtrip_group == "scieasy-blocks-imaging.image.tiff"
    assert tiff.metadata_fidelity.level == "pixel_only"

    zarr = capabilities["scieasy-blocks-imaging.image.zarr.save"]
    assert zarr.direction == "save"
    assert zarr.data_type is Image
    assert zarr.format_id == "zarr"
    assert zarr.extensions == (".zarr",)
    assert zarr.roundtrip_group == "scieasy-blocks-imaging.image.zarr"
    assert zarr.metadata_fidelity.level == "pixel_only"
