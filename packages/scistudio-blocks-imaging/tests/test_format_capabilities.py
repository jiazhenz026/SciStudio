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
from scistudio_blocks_imaging.io.load_image import LoadImage
from scistudio_blocks_imaging.io.save_image import SaveImage
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity

_EXPECTED_LOAD_CAPABILITY_IDS: set[str] = {
    "scistudio-blocks-imaging.image.tiff.load",
    "scistudio-blocks-imaging.image.zarr.load",
    "scistudio-blocks-imaging.image.png.load",
    "scistudio-blocks-imaging.image.jpeg.load",
    "scistudio-blocks-imaging.image.czi.load",
    "scistudio-blocks-imaging.image.nd2.load",
    "scistudio-blocks-imaging.image.lif.load",
    "scistudio-blocks-imaging.image.oir.load",
    "scistudio-blocks-imaging.image.oib.load",
}

_EXPECTED_SAVE_CAPABILITY_IDS: set[str] = {
    "scistudio-blocks-imaging.image.tiff.save",
    "scistudio-blocks-imaging.image.zarr.save",
    "scistudio-blocks-imaging.image.png.save",
    "scistudio-blocks-imaging.image.jpeg.save",
}

_BIOFORMATS_IDS: set[str] = {
    "scistudio-blocks-imaging.image.czi.load",
    "scistudio-blocks-imaging.image.nd2.load",
    "scistudio-blocks-imaging.image.lif.load",
    "scistudio-blocks-imaging.image.oir.load",
    "scistudio-blocks-imaging.image.oib.load",
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
        assert cap_id.startswith("scistudio-blocks-imaging.image."), cap_id
        assert cap_id.endswith(".load"), cap_id
        assert cap.direction == "load"
        assert cap.data_type is Image
        assert cap.block_type == "LoadImage"


def test_load_image_tiff_capability_defaults() -> None:
    capabilities = _capabilities_by_id(LoadImage)
    tiff = capabilities["scistudio-blocks-imaging.image.tiff.load"]
    assert tiff.format_id == "tiff"
    assert tiff.extensions == (".tif", ".tiff")
    assert tiff.is_default is True
    assert tiff.roundtrip_group == "scistudio-blocks-imaging.image.tiff"
    assert tiff.metadata_fidelity.level == "format_specific"
    assert "ome" in tiff.metadata_fidelity.format_metadata_reads


def test_load_image_zarr_capability_defaults() -> None:
    """Issue #1371: zarr load declares ``pixel_only`` — the handler reads
    array + axes only, never OME metadata."""
    capabilities = _capabilities_by_id(LoadImage)
    zarr = capabilities["scistudio-blocks-imaging.image.zarr.load"]
    assert zarr.format_id == "zarr"
    assert zarr.extensions == (".zarr",)
    assert zarr.metadata_fidelity.level == "pixel_only"
    # pixel_only forbids any declared meta fields — guard against
    # accidental re-introduction of overclaiming declarations.
    assert zarr.metadata_fidelity.format_metadata_reads == ()
    assert zarr.metadata_fidelity.typed_meta_reads == ()


def test_load_image_png_capability_defaults() -> None:
    """Issue #1371: PNG load declares only the OME fields actually
    populated from EXIF DPI."""
    capabilities = _capabilities_by_id(LoadImage)
    png = capabilities["scistudio-blocks-imaging.image.png.load"]
    assert png.format_id == "png"
    assert png.extensions == (".png",)
    assert png.handler == "_load_png"
    assert png.metadata_fidelity.level == "format_specific"
    assert png.metadata_fidelity.format_metadata_reads == (
        "ome.pixels.physical_size_x",
        "ome.pixels.physical_size_y",
    )
    # No broad ``ome`` token — would re-introduce the overclaim.
    assert "ome" not in png.metadata_fidelity.format_metadata_reads


def test_load_image_jpeg_capability_defaults() -> None:
    """Issue #1371: JPEG load declares only the OME fields actually
    populated from EXIF DPI."""
    capabilities = _capabilities_by_id(LoadImage)
    jpeg = capabilities["scistudio-blocks-imaging.image.jpeg.load"]
    assert jpeg.format_id == "jpeg"
    assert jpeg.extensions == (".jpg", ".jpeg")
    assert jpeg.handler == "_load_jpeg"
    assert jpeg.metadata_fidelity.format_metadata_reads == (
        "ome.pixels.physical_size_x",
        "ome.pixels.physical_size_y",
    )
    assert "ome" not in jpeg.metadata_fidelity.format_metadata_reads


@pytest.mark.parametrize("fmt", ["czi", "nd2", "lif", "oir", "oib"])
def test_load_image_bioformats_capability_defaults(fmt: str) -> None:
    capabilities = _capabilities_by_id(LoadImage)
    cap_id = f"scistudio-blocks-imaging.image.{fmt}.load"
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
        assert cap_id.startswith("scistudio-blocks-imaging.image."), cap_id
        assert cap_id.endswith(".save"), cap_id
        assert cap.direction == "save"
        assert cap.data_type is Image
        assert cap.block_type == "SaveImage"


def test_save_image_png_jpeg_declare_minimal_writable_meta() -> None:
    """PNG/JPEG persist only EXIF-mappable fields.

    Issue #1371: ``format_metadata_writes`` declares the precise OME
    field paths (``ome.pixels.physical_size_x`` / ``physical_size_y``)
    rather than the broad ``"ome"`` token, so the lossy-save warning
    chip can correctly identify what's preserved versus dropped.
    """
    capabilities = _capabilities_by_id(SaveImage)
    for fmt in ("png", "jpeg"):
        cap = capabilities[f"scistudio-blocks-imaging.image.{fmt}.save"]
        assert "pixel_size" in cap.metadata_fidelity.typed_meta_writes
        assert "channels" in cap.metadata_fidelity.typed_meta_writes
        # Issue #1371: precise OME field paths, not a broad ``"ome"``.
        assert cap.metadata_fidelity.format_metadata_writes == (
            "ome.pixels.physical_size_x",
            "ome.pixels.physical_size_y",
        )
        assert "ome" not in cap.metadata_fidelity.format_metadata_writes


def test_save_image_tiff_declares_richer_writable_meta() -> None:
    """TIFF persists pixel_size + z_spacing + channels + full OME."""
    capabilities = _capabilities_by_id(SaveImage)
    cap = capabilities["scistudio-blocks-imaging.image.tiff.save"]
    assert {"pixel_size", "z_spacing", "channels"}.issubset(set(cap.metadata_fidelity.typed_meta_writes))
    assert "ome" in cap.metadata_fidelity.format_metadata_writes


def test_save_image_zarr_declares_pixel_only() -> None:
    """Issue #1371: zarr save is ``pixel_only`` — the writer persists
    array data + ``axes`` group attribute, never OME or typed Meta."""
    capabilities = _capabilities_by_id(SaveImage)
    cap = capabilities["scistudio-blocks-imaging.image.zarr.save"]
    assert cap.metadata_fidelity.level == "pixel_only"
    assert cap.metadata_fidelity.format_metadata_writes == ()
    assert cap.metadata_fidelity.typed_meta_writes == ()


# ---------------------------------------------------------------------------
# FR-008 ambiguity + registry round-trip
# ---------------------------------------------------------------------------


def test_load_image_tiff_capability_covers_compound_extensions() -> None:
    """`.tif` and `.tiff` both map to the same tiff capability (no ambiguity).

    OME-TIFF is detected inside the handler; per spec scope it is not
    split into a separate capability id (spec §2.4 Edge Cases).
    """
    capabilities = _capabilities_by_id(LoadImage)
    tiff = capabilities["scistudio-blocks-imaging.image.tiff.load"]
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
    from scistudio_blocks_imaging.io import bioformats_handler

    capabilities = _capabilities_by_id(LoadImage)
    for cap_id in _BIOFORMATS_IDS:
        handler_name = capabilities[cap_id].handler
        assert hasattr(bioformats_handler, handler_name), (cap_id, handler_name)


def test_save_image_handlers_resolve_on_class() -> None:
    capabilities = _capabilities_by_id(SaveImage)
    for cap_id, cap in capabilities.items():
        assert hasattr(SaveImage, cap.handler), (cap_id, cap.handler)


# ---------------------------------------------------------------------------
# P2-03 (Phase C1 audit, issue #1296): SaveImage._resolve_format walks
# format_capabilities, not the legacy supported_extensions ClassVar.
# ---------------------------------------------------------------------------


def test_save_image_extension_map_is_derived_from_format_capabilities() -> None:
    """``_save_image_extension_map`` walks ``SaveImage.format_capabilities``.

    P2-03 (Phase C1 audit, issue #1296) / ADR-043 FR-005: the canonical
    source of truth for SaveImage's writable formats is
    ``format_capabilities``. The map must contain exactly the extensions
    declared by the capability records, mapped to their declared
    ``format_id`` values.
    """
    from scistudio_blocks_imaging.io.save_image import _save_image_extension_map

    mapping = _save_image_extension_map()
    expected: dict[str, str] = {}
    for capability in SaveImage.format_capabilities:
        for ext in capability.extensions:
            expected[ext.lower()] = capability.format_id
    assert mapping == expected
    # Spot-check a couple of well-known entries so regressions surface
    # with a meaningful error rather than a long dict diff.
    assert mapping[".tif"] == "tiff"
    assert mapping[".tiff"] == "tiff"
    assert mapping[".zarr"] == "zarr"
    assert mapping[".png"] == "png"
    assert mapping[".jpg"] == "jpeg"


def test_save_image_resolve_format_uses_format_capabilities(tmp_path) -> None:
    """``_resolve_format`` derives every recognised extension from
    ``format_capabilities`` and rejects unknowns with the canonical
    list of supported format ids."""
    from scistudio_blocks_imaging.io.save_image import _resolve_format

    assert _resolve_format(tmp_path / "a.tif", None) == "tiff"
    assert _resolve_format(tmp_path / "a.TIFF", None) == "tiff"
    assert _resolve_format(tmp_path / "a.zarr", None) == "zarr"
    assert _resolve_format(tmp_path / "a.png", None) == "png"
    assert _resolve_format(tmp_path / "a.jpg", None) == "jpeg"
    assert _resolve_format(tmp_path / "a.jpeg", None) == "jpeg"

    # Explicit format string is still cross-checked against
    # format_capabilities (not the legacy supported_extensions ClassVar).
    assert _resolve_format(tmp_path / "ignored.bin", "tiff") == "tiff"
    assert _resolve_format(tmp_path / "ignored.bin", "tif") == "tiff"
    assert _resolve_format(tmp_path / "ignored.bin", "jpg") == "jpeg"
    with pytest.raises(ValueError, match="unsupported format"):
        _resolve_format(tmp_path / "ignored.bin", "bogus")
    with pytest.raises(ValueError, match="cannot infer format"):
        _resolve_format(tmp_path / "a.unknown", None)


# ---------------------------------------------------------------------------
# P2-05 + SC-003 (Phase C1 audit, issue #1296): end-to-end OME-XML
# round-trip through SaveImage TIFF → LoadImage TIFF preserves
# Image.Meta.ome.images[0].pixels.physical_size_x.
# ---------------------------------------------------------------------------


def _ome_with_physical_size(physical_size_x: float, physical_size_y: float):
    """Build a minimal OME object suitable for the SC-003 round-trip."""
    from ome_types.model import OME, Pixels, PixelType
    from ome_types.model import Image as OMEImage

    return OME(
        images=[
            OMEImage(
                pixels=Pixels(
                    size_x=4,
                    size_y=3,
                    size_c=1,
                    size_z=1,
                    size_t=1,
                    dimension_order="XYCZT",
                    type=PixelType.UINT16,
                    physical_size_x=physical_size_x,
                    physical_size_y=physical_size_y,
                )
            )
        ]
    )


def _ome_xml_round_trip_available() -> bool:
    """Probe whether ``ome_types.to_xml`` + ``from_xml`` work in this env.

    Python 3.14 + xsdata < some-future-release have a known
    ``XmlContextError: Failed to detect the declared class for field
    rights`` bug that breaks ome_types serialization. CI runs on Python
    3.11/3.13 where the round-trip works; this probe lets the SC-003
    regression test gracefully skip on broken local environments
    without masking real regressions in CI.
    """
    try:
        from ome_types import from_xml, to_xml
    except Exception:
        return False
    try:
        xml = to_xml(_ome_with_physical_size(0.5, 0.7))
        recovered = from_xml(xml)
    except Exception:
        return False
    return bool(getattr(recovered, "images", None))


def test_sc_003_ome_metadata_survives_tiff_round_trip(tmp_path) -> None:
    """SC-003 end-to-end: build Image with OME → SaveImage(.ome.tif) →
    LoadImage → assert ``physical_size_x`` preserved.

    P2-05 / ADR-043 FR-005 + SC-003 (Phase C1 audit, issue #1296): the
    ``scistudio-blocks-imaging.image.tiff.save`` capability advertises
    ``format_metadata_writes=("ome",)`` and the notes say "OME-XML
    written to the ImageDescription tag when Image.Meta.ome is
    populated". This test closes the previously broken link in the
    SC-003 golden path: prior to the fix, ``_write_tiff`` wrote only
    the axes string, so the saved TIFF lost OME on a round-trip.
    """
    import numpy as np
    from scistudio_blocks_imaging.io.load_image import LoadImage
    from scistudio_blocks_imaging.io.save_image import SaveImage

    from scistudio.blocks.base.config import BlockConfig

    if not _ome_xml_round_trip_available():
        pytest.skip(
            "ome_types.to_xml/from_xml round-trip is unavailable in this Python "
            "environment (known xsdata bug on Python 3.14); CI on 3.11/3.13 "
            "exercises this test path."
        )

    physical_size_x = 0.5
    physical_size_y = 0.7
    ome = _ome_with_physical_size(physical_size_x, physical_size_y)

    arr = np.arange(12, dtype=np.uint16).reshape(3, 4)
    img = Image(
        axes=["y", "x"],
        shape=arr.shape,
        dtype=str(arr.dtype),
        meta=Image.Meta(ome=ome),
    )
    img._data = arr  # type: ignore[attr-defined]

    out_path = tmp_path / "out.ome.tif"
    SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))
    assert out_path.is_file(), "SaveImage did not produce the TIFF file"

    # Reload via LoadImage and assert the physical pixel sizes survived
    # through the TIFF ImageDescription tag.
    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    reloaded = loaded[0] if hasattr(loaded, "__getitem__") else loaded
    assert reloaded.meta is not None, "Reloaded Image has no Meta"
    assert reloaded.meta.ome is not None, "Reloaded Image.Meta.ome is None — OME-XML was not persisted to TIFF"
    assert reloaded.meta.ome.images, "Reloaded OME has no images entry"
    reloaded_pixels = reloaded.meta.ome.images[0].pixels
    assert reloaded_pixels.physical_size_x == pytest.approx(physical_size_x), (
        f"physical_size_x changed across TIFF round-trip: "
        f"source={physical_size_x}, reloaded={reloaded_pixels.physical_size_x}"
    )
    assert reloaded_pixels.physical_size_y == pytest.approx(physical_size_y), (
        f"physical_size_y changed across TIFF round-trip: "
        f"source={physical_size_y}, reloaded={reloaded_pixels.physical_size_y}"
    )
