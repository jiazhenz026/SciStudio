"""SVG sanitization (FR-019) and TIFF bounded-read (FR-010/SC-004) tests.

Covers the two audit P2 findings on the SPEC 1 umbrella: the SVG sanitizer must
strip script blocks even with malformed/unterminated closers and active-scheme
hrefs (defense-in-depth behind the frontend iframe sandbox), and the TIFF raster
handle must read only the first IFD page rather than the whole multi-page stack.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scistudio.core.storage.ref import StorageReference
from scistudio.previewers.data_access import PreviewDataAccess
from scistudio.previewers.fallbacks import sanitize_svg


def test_sanitize_svg_strips_well_formed_script() -> None:
    svg = "<svg><script>alert(1)</script><rect/></svg>"
    out, removed = sanitize_svg(svg)
    assert "alert(1)" not in out
    assert "<script" not in out
    assert removed is True
    assert "<rect/>" in out  # legitimate content preserved


def test_sanitize_svg_strips_malformed_closing_tag() -> None:
    # Audit P2-1: `</script\t\nbar>` previously survived the `</script\s*>` close.
    svg = "<svg><script>evil()</script\t\nbar><rect/></svg>"
    out, removed = sanitize_svg(svg)
    assert "evil()" not in out
    assert "<script" not in out
    assert removed is True


def test_sanitize_svg_strips_unterminated_script() -> None:
    svg = "<svg><script>evil()  // no closing tag"
    out, removed = sanitize_svg(svg)
    assert "evil()" not in out
    assert "<script" not in out
    assert removed is True


def test_sanitize_svg_strips_event_handlers_and_active_hrefs() -> None:
    svg = (
        "<svg><rect onload=\"x()\" onclick='y()'/>"
        '<a href="javascript:steal()"/><a xlink:href="vbscript:bad()"/>'
        '<a href="https://evil.test/x"/></svg>'
    )
    out, _ = sanitize_svg(svg)
    assert "onload" not in out
    assert "onclick" not in out
    assert "javascript:" not in out
    assert "vbscript:" not in out
    assert "https://evil.test" not in out


def test_sanitize_svg_keeps_clean_svg_and_data_uris() -> None:
    svg = '<svg><image href="data:image/png;base64,AAAA"/><rect/></svg>'
    out, removed = sanitize_svg(svg)
    # data: URIs are inert under the iframe sandbox and are preserved.
    assert "data:image/png" in out
    assert removed is False


def test_tiff_handle_reads_only_first_page(tmp_path: Path) -> None:
    """FR-010/SC-004: a multi-page TIFF yields a single-page handle, not the stack."""
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "multi.tif"
    # Genuine multi-page TIFF: two separate 4x4 IFD pages (TiffWriter appends
    # each write() as its own page). `imread(key=0)` must return only page 0.
    with tifffile.TiffWriter(str(path)) as tw:
        tw.write(np.zeros((4, 4), dtype=np.uint8))
        tw.write(np.ones((4, 4), dtype=np.uint8))
    ref = StorageReference(backend="filesystem", path=str(path), format="tiff")
    access = PreviewDataAccess()
    handle, shape, _dtype = access._open_array_handle(ref)
    # Only the first page is read: shape is (4, 4), not a (2, 4, 4) stack.
    assert shape == [4, 4]
    assert tuple(getattr(handle, "shape", ())) == (4, 4)
