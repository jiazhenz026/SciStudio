"""ADR-043 explicit format capability tests for imaging IOBlocks.

Per spec adr-043-package-migration FR-004 / FR-005 / FR-008 / FR-015 /
FR-016 the imaging package's :class:`LoadImage` and :class:`SaveImage`
declare explicit ``format_capabilities`` covering:

- TIFF (tifffile; OME-TIFF auto-detected inside the handler).
- Zarr (vanilla; OME-Zarr deferred per spec scope.out).
- PNG / JPEG (Pillow; EXIF DPI mapped to ``Image.Meta.ome``).
- Bio-Formats vendor microscopy family on load only (CZI/ND2/LIF/OIR/OIB).

The Bio-Formats family is intentionally absent from SaveImage because
``cellprofiler/python-bioformats`` is load-only by design.
"""

from __future__ import annotations

import pytest
from scieasy_blocks_imaging.io.load_image import LoadImage
from scieasy_blocks_imaging.io.save_image import SaveImage
from scieasy_blocks_imaging.types import Image

from scieasy.blocks.io.capabilities import FormatCapability, MetadataFidelity

_EXPECTED_LOAD_CAPABILITY_IDS: set[str] = {
    "scieasy-blocks-imaging.image.tiff.load",
    "scieasy-blocks-imaging.image.zarr.load",
    "scieasy-blocks-imaging.image.png.load",
    "scieasy-blocks-imaging.image.jpeg.load",
    "scieasy-blocks-imaging.image.czi.load",
    "scieasy-blocks-imaging.image.nd2.load",
    "scieasy-blocks-imaging.image.lif.load",
    "scieasy-blocks-imaging.image.oir.load",
    "scieasy-blocks-imaging.image.oib.load",
}

_EXPECTED_SAVE_CAPABILITY_IDS: set[str] = {
    "scieasy-blocks-imaging.image.tiff.save",
    "scieasy-blocks-imaging.image.zarr.save",
    "scieasy-blocks-imaging.image.png.save",
    "scieasy-blocks-imaging.image.jpeg.save",
}

_BIOFORMATS_IDS: set[str] = {
    "scieasy-blocks-imaging.image.czi.load",
    "scieasy-blocks-imaging.image.nd2.load",
    "scieasy-blocks-imaging.image.lif.load",
    "scieasy-blocks-imaging.image.oir.load",
    "scieasy-blocks-imaging.image.oib.load",
}


def _capabilities_by_id(block: type) -> dict[str, FormatCapability]:
    return {capability.id: capability for capability in block.get_format_capabilities()}


# ---------------------------------------------------------------------------
# FR-004 LoadImage capability declarations
# ---------------------------------------------------------------------------


def test_load_image_declares_full_capability_set() -> None:
    """LoadImage declares TIFF/Zarr/PNG/JPEG + the Bio-Formats family."""
    capabilities = _capabilities_by_id(LoadImage)
    assert set(capabilities) == _EXPECTED_LOAD_CAPABILITY_IDS
    assert all(not capability.is_synthesized for capability in capabilities.values())


def test_load_image_capability_id_convention() -> None:
    """All LoadImage capability ids follow ``imaging.image.{format}.load``."""
    capabilities = _capabilities_by_id(LoadImage)
    for cap_id, cap in capabilities.items():
        assert cap_id.startswith("scieasy-blocks-imaging.image."), cap_id
        assert cap_id.endswith(".load"), cap_id
        assert cap.direction == "load"
        assert cap.data_type is Image
        assert cap.block_type == "LoadImage"


def test_load_image_tiff_capability_defaults() -> None:
    capabilities = _capabilities_by_id(LoadImage)
    tiff = capabilities["scieasy-blocks-imaging.image.tiff.load"]
    assert tiff.format_id == "tiff"
    assert tiff.extensions == (".tif", ".tiff")
    assert tiff.is_default is True
    assert tiff.roundtrip_group == "scieasy-blocks-imaging.image.tiff"
    assert tiff.metadata_fidelity.level == "format_specific"
    assert "ome" in tiff.metadata_fidelity.format_metadata_reads


def test_load_image_zarr_capability_defaults() -> None:
    capabilities = _capabilities_by_id(LoadImage)
    zarr = capabilities["scieasy-blocks-imaging.image.zarr.load"]
    assert zarr.format_id == "zarr"
    assert zarr.extensions == (".zarr",)
    assert zarr.metadata_fidelity.level == "format_specific"
    assert "ome" in zarr.metadata_fidelity.format_metadata_reads


def test_load_image_png_capability_defaults() -> None:
    capabilities = _capabilities_by_id(LoadImage)
    png = capabilities["scieasy-blocks-imaging.image.png.load"]
    assert png.format_id == "png"
    assert png.extensions == (".png",)
    assert png.handler == "_load_png"
    assert png.metadata_fidelity.level == "format_specific"


def test_load_image_jpeg_capability_defaults() -> None:
    capabilities = _capabilities_by_id(LoadImage)
    jpeg = capabilities["scieasy-blocks-imaging.image.jpeg.load"]
    assert jpeg.format_id == "jpeg"
    assert jpeg.extensions == (".jpg", ".jpeg")
    assert jpeg.handler == "_load_jpeg"


@pytest.mark.parametrize("fmt", ["czi", "nd2", "lif", "oir", "oib"])
def test_load_image_bioformats_capability_defaults(fmt: str) -> None:
    capabilities = _capabilities_by_id(LoadImage)
    cap_id = f"scieasy-blocks-imaging.image.{fmt}.load"
    cap = capabilities[cap_id]
    assert cap.format_id == fmt
    assert cap.extensions == (f".{fmt}",)
    assert cap.handler == f"_load_{fmt}"
    assert cap.metadata_fidelity.level == "format_specific"
    assert "ome" in cap.metadata_fidelity.format_metadata_reads


# ---------------------------------------------------------------------------
# FR-005 SaveImage capability declarations (writable only)
# ---------------------------------------------------------------------------


def test_save_image_declares_only_writable_formats() -> None:
    """SaveImage declares TIFF/Zarr/PNG/JPEG; Bio-Formats are absent."""
    capabilities = _capabilities_by_id(SaveImage)
    assert set(capabilities) == _EXPECTED_SAVE_CAPABILITY_IDS
    assert all(not capability.is_synthesized for capability in capabilities.values())


def test_save_image_bioformats_family_is_load_only() -> None:
    """Bio-Formats capabilities never appear with direction='save' (FR-005)."""
    save_ids = {cap.id for cap in SaveImage.get_format_capabilities()}
    assert _BIOFORMATS_IDS.isdisjoint(save_ids)


def test_save_image_capability_id_convention() -> None:
    capabilities = _capabilities_by_id(SaveImage)
    for cap_id, cap in capabilities.items():
        assert cap_id.startswith("scieasy-blocks-imaging.image."), cap_id
        assert cap_id.endswith(".save"), cap_id
        assert cap.direction == "save"
        assert cap.data_type is Image
        assert cap.block_type == "SaveImage"


def test_save_image_png_jpeg_declare_minimal_writable_meta() -> None:
    """PNG/JPEG can persist only EXIF-mappable fields (pixel_size, channels)."""
    capabilities = _capabilities_by_id(SaveImage)
    for fmt in ("png", "jpeg"):
        cap = capabilities[f"scieasy-blocks-imaging.image.{fmt}.save"]
        assert "pixel_size" in cap.metadata_fidelity.typed_meta_writes
        assert "channels" in cap.metadata_fidelity.typed_meta_writes
        assert "ome" in cap.metadata_fidelity.format_metadata_writes


def test_save_image_tiff_zarr_declare_richer_writable_meta() -> None:
    """TIFF / zarr can persist pixel_size + z_spacing + channels + ome."""
    capabilities = _capabilities_by_id(SaveImage)
    for fmt in ("tiff", "zarr"):
        cap = capabilities[f"scieasy-blocks-imaging.image.{fmt}.save"]
        assert {"pixel_size", "z_spacing", "channels"}.issubset(set(cap.metadata_fidelity.typed_meta_writes))
        assert "ome" in cap.metadata_fidelity.format_metadata_writes


# ---------------------------------------------------------------------------
# FR-008 ambiguity + registry round-trip
# ---------------------------------------------------------------------------


def test_load_image_tiff_capability_covers_compound_extensions() -> None:
    """`.tif` and `.tiff` both map to the same tiff capability (no ambiguity).

    OME-TIFF is detected inside the handler; per spec scope it is not
    split into a separate capability id (spec §2.4 Edge Cases).
    """
    capabilities = _capabilities_by_id(LoadImage)
    tiff = capabilities["scieasy-blocks-imaging.image.tiff.load"]
    assert ".tif" in tiff.extensions
    assert ".tiff" in tiff.extensions


def test_all_capabilities_are_format_capability_instances() -> None:
    for block in (LoadImage, SaveImage):
        for cap in block.get_format_capabilities():
            assert isinstance(cap, FormatCapability)
            assert isinstance(cap.metadata_fidelity, MetadataFidelity)


def test_load_image_handlers_resolve_on_class() -> None:
    """The ``handler`` string on each capability resolves to a callable
    on the class. Bio-Formats handlers are bound on the class as lazy-
    import wrappers (so the registry's scan-time
    ``hasattr(cls, capability.handler)`` validation succeeds even when
    the optional ``[bioformats]`` extras are not installed). This
    catches typos at declaration time."""
    capabilities = _capabilities_by_id(LoadImage)
    for cap_id, cap in capabilities.items():
        assert hasattr(LoadImage, cap.handler), (cap_id, cap.handler)
        assert callable(getattr(LoadImage, cap.handler)), (cap_id, cap.handler)


def test_load_image_bioformats_handler_names_match_lazy_module() -> None:
    """The Bio-Formats handler names declared on LoadImage delegate to
    matching names in ``bioformats_handler``. The class-level wrappers
    are lazy-import shims; this test pins the underlying name mapping."""
    from scieasy_blocks_imaging.io import bioformats_handler

    capabilities = _capabilities_by_id(LoadImage)
    for cap_id in _BIOFORMATS_IDS:
        handler_name = capabilities[cap_id].handler
        assert hasattr(bioformats_handler, handler_name), (cap_id, handler_name)


def test_save_image_handlers_resolve_on_class() -> None:
    capabilities = _capabilities_by_id(SaveImage)
    for cap_id, cap in capabilities.items():
        assert hasattr(SaveImage, cap.handler), (cap_id, cap.handler)
