"""SVG sanitization (FR-019) and bounded core Array read tests.

Covers the two audit P2 findings on the SPEC 1 umbrella: the SVG sanitizer must
strip script blocks even with malformed/unterminated closers and active-scheme
hrefs (defense-in-depth behind the frontend iframe sandbox), and core Array
handles must remain bounded without depending on package-owned image decoders.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from scistudio.core.storage.ref import StorageReference
from scistudio.previewers.data_access import PreviewDataAccess
from scistudio.previewers.helpers import sanitize_svg


def test_sanitize_svg_back_compat_reexport_from_fallbacks() -> None:
    """#1823: sanitize_svg relocated to the public helpers home (ADR-052 §8).

    The legacy ``scistudio.previewers.fallbacks`` import path is kept as a
    back-compat re-export (out of ``__all__``) so out-of-tree packages do not
    hard-break before migrating; it must resolve to the same function.
    """
    from scistudio.previewers import fallbacks, helpers

    assert fallbacks.sanitize_svg is helpers.sanitize_svg
    assert "sanitize_svg" not in fallbacks.__all__
    assert "sanitize_svg" in helpers.__all__


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


def test_zarr_handle_uses_lazy_core_array_storage(tmp_path: Path) -> None:
    """FR-010/SC-004: core preview reads Zarr handles without image decoders."""
    import zarr

    path = tmp_path / "array.zarr"
    z = zarr.open(str(path), mode="w", shape=(4, 4), chunks=(2, 2), dtype="uint8")
    z[:] = np.ones((4, 4), dtype=np.uint8)
    ref = StorageReference(backend="zarr", path=str(path), format="zarr")
    access = PreviewDataAccess()
    handle, shape, _dtype = access._open_array_handle(ref)
    assert shape == [4, 4]
    assert tuple(getattr(handle, "shape", ())) == (4, 4)
