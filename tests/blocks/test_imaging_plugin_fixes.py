"""Integration tests for imaging plugin fixes #432, #434, #439.

These tests verify the three fixes bundled in PR #440:
- #432: _open_file_manager helper exists and is callable
- #434: SaveImage._write_single exists as a method
- #439: CellposeSegment declares dual output ports (labels + masks)
"""

from __future__ import annotations


def test_open_file_manager_is_importable() -> None:
    """#432: _open_file_manager is a callable module-level helper."""
    from scieasy_blocks_imaging.interactive import _open_file_manager

    assert callable(_open_file_manager)


def test_save_image_has_write_single_method() -> None:
    """#434: SaveImage has a _write_single helper for batch support."""
    from scieasy_blocks_imaging.io.save_image import SaveImage

    assert hasattr(SaveImage, "_write_single")
    assert callable(SaveImage._write_single)


def test_cellpose_segment_has_masks_output_port() -> None:
    """#439: CellposeSegment declares both 'labels' and 'masks' output ports."""
    from scieasy_blocks_imaging.segmentation.cellpose_segment import CellposeSegment

    port_names = [p.name for p in CellposeSegment.output_ports]
    assert "labels" in port_names
    assert "masks" in port_names


def test_load_image_supported_extensions_classvar() -> None:
    """#1075: LoadImage declares ``supported_extensions`` (ADR-028 §D8).

    Cross-package integration check: from the core test suite we can
    inspect the imaging plugin's ClassVar to ensure #1075 landed.
    """
    from scieasy_blocks_imaging.io.load_image import LoadImage

    assert LoadImage.supported_extensions == {
        ".tif": "tiff",
        ".tiff": "tiff",
        ".zarr": "zarr",
    }


def test_save_image_supported_extensions_classvar() -> None:
    """#1075: SaveImage declares ``supported_extensions`` (ADR-028 §D8)."""
    from scieasy_blocks_imaging.io.save_image import SaveImage

    assert SaveImage.supported_extensions == {
        ".tif": "tiff",
        ".tiff": "tiff",
        ".zarr": "zarr",
    }


def test_load_image_save_image_supported_extensions_mirror() -> None:
    """#1075: SaveImage.supported_extensions mirrors LoadImage's for round-trip
    discoverability via BlockRegistry (#1077)."""
    from scieasy_blocks_imaging.io.load_image import LoadImage
    from scieasy_blocks_imaging.io.save_image import SaveImage

    assert SaveImage.supported_extensions == LoadImage.supported_extensions


def test_imaging_legacy_extension_constants_removed() -> None:
    """#1075: Module-level legacy extension constants are gone after
    routing dispatch through the ClassVar."""
    from scieasy_blocks_imaging.io import load_image, save_image

    for attr in ("_TIFF_EXTS", "_ZARR_EXTS", "_SUPPORTED_EXTS"):
        assert not hasattr(load_image, attr), f"{attr} must be removed per #1075"
    for attr in ("_TIFF_FORMAT", "_ZARR_FORMAT", "_SUPPORTED_FORMATS", "_EXT_TO_FORMAT"):
        assert not hasattr(save_image, attr), f"{attr} must be removed per #1075"
