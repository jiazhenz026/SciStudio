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
