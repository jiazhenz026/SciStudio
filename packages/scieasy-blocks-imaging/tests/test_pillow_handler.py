"""Regression tests for the Pillow PNG/JPEG load/save handlers.

P2-01 (Phase C1 audit, issue #1296): the ``axes_override`` branch in
``_load_png`` / ``_load_jpeg`` previously silently zeroed the pixel
buffer because it reassigned ``img`` to a freshly constructed
``Image`` and then evaluated ``img._data if hasattr(img, "_data")
else []`` — the new ``img`` does not yet have ``_data``, so the
conditional collapsed to ``np.asarray([])``. The fix captures the
source pixel buffer before reassigning ``img`` so the override only
rewrites the axis labels.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

# Pillow is an explicit dependency of scieasy-blocks-imaging; skip
# politely if the install is incomplete rather than erroring at import.
pytest.importorskip("PIL.Image")
from PIL import Image as PILImage
from scieasy_blocks_imaging.io.pillow_handler import _load_jpeg, _load_png


def _write_grayscale_png(path: Path, height: int = 4, width: int = 6) -> np.ndarray:
    """Write a deterministic grayscale PNG and return the source array."""
    arr = np.arange(height * width, dtype=np.uint8).reshape(height, width)
    PILImage.fromarray(arr, mode="L").save(str(path), format="PNG")
    return arr


def _write_grayscale_jpeg(path: Path, height: int = 4, width: int = 6) -> np.ndarray:
    """Write a deterministic grayscale JPEG and return the source array."""
    # JPEG is lossy but at quality=100 a uniform-ish ramp survives ~exactly
    # enough for "non-zero buffer" + "shape match" assertions.
    arr = np.arange(height * width, dtype=np.uint8).reshape(height, width)
    PILImage.fromarray(arr, mode="L").save(str(path), format="JPEG", quality=100)
    return arr


def test_load_png_default_axes_returns_decoded_pixels(tmp_path: Path) -> None:
    """Baseline: without ``axes_override``, ``_load_png`` returns the decoded
    array exactly as Pillow reads it (sanity check before the
    axes-override regression test)."""
    src = _write_grayscale_png(tmp_path / "img.png")
    img = _load_png(tmp_path / "img.png")
    assert img.axes == ["y", "x"]
    assert tuple(img.shape) == src.shape
    np.testing.assert_array_equal(img._data, src)  # type: ignore[attr-defined]


def test_load_png_axes_override_preserves_pixel_buffer(tmp_path: Path) -> None:
    """P2-01 regression (Phase C1 audit, issue #1296): when ``axes_override``
    is provided, the returned :class:`Image` must carry the decoded
    pixel data, not a zero-length / zero-filled buffer.

    Before the fix the ``axes_override`` branch reassigned ``img`` to a
    new instance without ``_data`` set, then wrote
    ``np.asarray(img._data if hasattr(img, "_data") else [])`` —
    collapsing to ``np.asarray([])``. This test pins the corrected
    behaviour: ``img._data`` (and ``img.to_memory()``) returns the
    decoded array with the requested axis labels.
    """
    src = _write_grayscale_png(tmp_path / "img.png")
    override = ["x", "y"]  # deliberately swap labels to take the override path
    img = _load_png(tmp_path / "img.png", axes_override=override)
    assert img.axes == override
    # Pixel buffer must be preserved (the bug returned an empty array).
    data = img._data  # type: ignore[attr-defined]
    assert data is not None, "axes_override returned an Image with no _data"
    assert data.size > 0, "axes_override returned a zero-length pixel buffer (P2-01 regression)"
    assert data.shape == src.shape, f"axes_override mutated the array shape: {data.shape} != {src.shape}"
    np.testing.assert_array_equal(data, src)


def test_load_jpeg_axes_override_preserves_pixel_buffer(tmp_path: Path) -> None:
    """P2-01 regression for ``_load_jpeg`` — see ``_load_png`` test."""
    src = _write_grayscale_jpeg(tmp_path / "img.jpg")
    override = ["x", "y"]
    img = _load_jpeg(tmp_path / "img.jpg", axes_override=override)
    assert img.axes == override
    data = img._data  # type: ignore[attr-defined]
    assert data is not None, "axes_override returned an Image with no _data"
    assert data.size > 0, "axes_override returned a zero-length pixel buffer (P2-01 regression)"
    assert data.shape == src.shape


def test_load_png_axes_override_length_mismatch_raises(tmp_path: Path) -> None:
    """Mismatched override length keeps raising the diagnostic ``ValueError``."""
    _write_grayscale_png(tmp_path / "img.png")
    with pytest.raises(ValueError, match=r"does not match ndim"):
        _load_png(tmp_path / "img.png", axes_override=["y", "x", "c"])
