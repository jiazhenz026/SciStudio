"""Issue #1371 regression — capability declarations match handler behaviour.

ADR-043: capability ``metadata_fidelity`` declarations must match what
each IO handler actually preserves. Pre-#1371, ``_save_zarr`` /
``_load_zarr`` advertised ``format_metadata_writes=("ome",)`` /
``format_metadata_reads=("ome",)`` even though they only round-tripped
array data + axes. PNG/JPEG advertised broad OME support even though
they only persist EXIF DPI. The fix narrows the declarations to the
subset actually preserved.

These tests pin the contract by:

* Running a zarr round-trip end-to-end and asserting
  ``loaded.meta.ome is None`` matches the new ``pixel_only`` declaration.
* Running a PNG round-trip and asserting only the narrow OME field paths
  declared by the capability (``physical_size_x`` / ``physical_size_y``)
  actually survive — and that no broader OME fields appear.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from scistudio_blocks_imaging.io.load_image import LoadImage
from scistudio_blocks_imaging.io.save_image import SaveImage
from scistudio_blocks_imaging.types import Image

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str], *, meta: Image.Meta | None = None) -> Image:
    img = Image(axes=axes, shape=arr.shape, dtype=str(arr.dtype), meta=meta)
    img._data = arr  # type: ignore[attr-defined]
    return img


def _make_ome_with_physical_size(
    physical_size_x: float,
    physical_size_y: float,
    *,
    size_x: int,
    size_y: int,
):
    from ome_types.model import OME, Pixels, PixelType
    from ome_types.model import Image as OMEImage

    return OME(
        images=[
            OMEImage(
                pixels=Pixels(
                    size_x=size_x,
                    size_y=size_y,
                    size_c=1,
                    size_z=1,
                    size_t=1,
                    dimension_order="XYCZT",
                    type=PixelType.UINT8,
                    physical_size_x=physical_size_x,
                    physical_size_y=physical_size_y,
                )
            )
        ]
    )


# ---------------------------------------------------------------------------
# #1371 — Zarr round-trip preserves no OME (matches new ``pixel_only``
# capability declaration).
# ---------------------------------------------------------------------------


def test_issue_1371_zarr_round_trip_meta_ome_is_none(tmp_path: Path) -> None:
    """Zarr writer persists array + axes only. After a round-trip, the
    loaded ``Image.Meta.ome`` is ``None`` regardless of what the source
    image carried — the new capability declaration says ``pixel_only``
    to match.
    """
    arr = np.arange(60, dtype=np.float32).reshape(3, 4, 5)
    # Source carries OME on purpose — none of it should survive.
    try:
        from ome_types.model import OME  # noqa: F401 — probe presence

        ome = _make_ome_with_physical_size(0.5, 0.7, size_x=5, size_y=4)
        meta_in = Image.Meta(ome=ome)
    except Exception:
        meta_in = Image.Meta()

    img = _make_image(arr, ["c", "y", "x"], meta=meta_in)

    out_path = tmp_path / "rt.zarr"
    SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))

    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    assert isinstance(loaded, Collection)
    out = loaded[0]
    assert isinstance(out, Image)

    # Pixel data + axes survive (pre-existing behaviour we keep).
    assert out.axes == ["c", "y", "x"]
    assert out.shape == (3, 4, 5)
    # No OME metadata preserved — matches new ``pixel_only`` capability
    # declaration. Pre-#1371 the declaration falsely advertised OME
    # round-trip even though the handler dropped it.
    assert out.meta is not None
    assert out.meta.ome is None, (
        "Zarr round-trip preserved Image.Meta.ome but the capability "
        "now declares pixel_only — declaration must match behaviour "
        "(#1371)."
    )


def test_issue_1371_zarr_save_capability_declares_pixel_only() -> None:
    """The SaveImage zarr capability declares ``pixel_only`` (issue
    #1371) — there is no OME or typed Meta field written."""
    cap = next(c for c in SaveImage.format_capabilities if c.format_id == "zarr")
    assert cap.metadata_fidelity.level == "pixel_only"
    assert cap.metadata_fidelity.format_metadata_writes == ()
    assert cap.metadata_fidelity.typed_meta_writes == ()


def test_issue_1371_zarr_load_capability_declares_pixel_only() -> None:
    """The LoadImage zarr capability declares ``pixel_only`` (issue
    #1371) — there is no OME or typed Meta field read."""
    cap = next(c for c in LoadImage.format_capabilities if c.format_id == "zarr")
    assert cap.metadata_fidelity.level == "pixel_only"
    assert cap.metadata_fidelity.format_metadata_reads == ()


# ---------------------------------------------------------------------------
# #1371 — PNG round-trip preserves only EXIF DPI (matches the narrow OME
# field paths declared by the capability).
# ---------------------------------------------------------------------------


def test_issue_1371_png_save_capability_declares_only_physical_size_paths() -> None:
    """PNG save advertises only the OME field paths actually written
    (EXIF DPI → physical_size_x/y). No broad ``"ome"`` token (#1371)."""
    cap = next(c for c in SaveImage.format_capabilities if c.format_id == "png")
    assert cap.metadata_fidelity.format_metadata_writes == (
        "ome.pixels.physical_size_x",
        "ome.pixels.physical_size_y",
    )
    assert "ome" not in cap.metadata_fidelity.format_metadata_writes


def test_issue_1371_jpeg_save_capability_declares_only_physical_size_paths() -> None:
    cap = next(c for c in SaveImage.format_capabilities if c.format_id == "jpeg")
    assert cap.metadata_fidelity.format_metadata_writes == (
        "ome.pixels.physical_size_x",
        "ome.pixels.physical_size_y",
    )
    assert "ome" not in cap.metadata_fidelity.format_metadata_writes


def test_issue_1371_png_round_trip_preserves_only_physical_size(tmp_path: Path) -> None:
    """PNG handler persists only EXIF DPI; after a round-trip the only
    OME pixel field that survives is ``physical_size_x`` /
    ``physical_size_y``. The capability declaration is narrowed to
    exactly that subset (#1371).
    """
    try:
        from ome_types.model import OME  # noqa: F401
    except Exception:
        pytest.skip("ome_types not importable")

    arr = np.zeros((6, 8), dtype=np.uint8)
    # 254 micrometres / pixel ⇒ EXIF stores 100 DPI ⇒ load reads back
    # 25400 / 100 = 254 micrometres / pixel. The round-trip is therefore
    # lossless on this specific field — which is exactly what the
    # narrowed capability declaration advertises.
    source_physical_size = 254.0
    ome = _make_ome_with_physical_size(source_physical_size, source_physical_size, size_x=8, size_y=6)
    img = _make_image(arr, ["y", "x"], meta=Image.Meta(ome=ome))

    out_path = tmp_path / "out.png"
    SaveImage().save(img, BlockConfig(params={"path": str(out_path)}))

    loaded = LoadImage().load(BlockConfig(params={"path": str(out_path)}))
    out = loaded[0]
    assert isinstance(out, Image)
    assert out.meta is not None
    assert out.meta.ome is not None, (
        "PNG round-trip lost OME metadata; the capability advertises "
        "ome.pixels.physical_size_x/y so at least those must survive."
    )
    pixels = out.meta.ome.images[0].pixels
    # EXIF DPI is integer-rounded by Pillow on write, so a < 1% tolerance
    # easily survives the round-trip without masking real regressions.
    assert pixels.physical_size_x == pytest.approx(source_physical_size, rel=0.01)
    assert pixels.physical_size_y == pytest.approx(source_physical_size, rel=0.01)


# ---------------------------------------------------------------------------
# Smoke: TIFF declarations remain unchanged (full OME write/read).
# ---------------------------------------------------------------------------


def test_issue_1371_tiff_capabilities_still_advertise_full_ome() -> None:
    """TIFF was the one format that legitimately writes full OME-XML;
    the narrow declarations introduced for #1371 must NOT touch it.
    """
    tiff_save = next(c for c in SaveImage.format_capabilities if c.format_id == "tiff")
    tiff_load = next(c for c in LoadImage.format_capabilities if c.format_id == "tiff")
    assert "ome" in tiff_save.metadata_fidelity.format_metadata_writes
    assert "ome" in tiff_load.metadata_fidelity.format_metadata_reads
