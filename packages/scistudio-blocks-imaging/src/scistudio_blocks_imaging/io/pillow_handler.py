"""PNG/JPEG handlers via Pillow for the imaging plugin.

ADR-043 / spec adr-043-package-migration FR-004 / FR-005:

* ``_load_png`` / ``_load_jpeg`` — load a PNG / JPEG file into an
  :class:`Image`. EXIF DPI is mapped onto :class:`ome_types.model.OME`
  ``physical_size_x`` / ``physical_size_y`` when present.

* ``_save_png`` / ``_save_jpeg`` — save a 2D or 3D (channel-last) Image
  to PNG / JPEG. When ``Image.Meta.ome`` carries a non-None
  ``physical_size_x`` and ``physical_size_y``, those values are written
  to the file as EXIF DPI on save.

The handlers are kept narrow: PNG/JPEG do not carry rich OME metadata,
so the fidelity of the round-trip is intentionally
``MetadataFidelity(level="format_specific", ...)`` with
``typed_meta_writes=("pixel_size", "channels")`` — anything richer is
the source format's responsibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from ome_types.model import OME, Pixels, PixelType
from ome_types.model import Image as OMEImage

from scistudio.core.meta.framework import FrameworkMeta
from scistudio_blocks_imaging.types import Image

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL.Image import Image as PILImage

# Pillow uses inches for EXIF DPI; OME physical_size_x is in micrometers
# by default. 1 inch = 25400 micrometers.
_INCH_TO_MICROMETER: float = 25400.0


def _dtype_to_pixel_type(dtype: np.dtype) -> PixelType:
    """Map a numpy dtype to the closest :class:`ome_types.PixelType` value.

    Falls back to ``UINT8`` for non-standard dtypes — PNG/JPEG handlers
    write 8-bit-per-channel raster anyway, so this fallback is also
    semantically correct for the save path.
    """
    mapping = {
        np.uint8: PixelType.UINT8,
        np.uint16: PixelType.UINT16,
        np.uint32: PixelType.UINT32,
        np.int8: PixelType.INT8,
        np.int16: PixelType.INT16,
        np.int32: PixelType.INT32,
        np.float32: PixelType.FLOAT,
        np.float64: PixelType.DOUBLE,
    }
    for npt, pxt in mapping.items():
        if np.dtype(dtype) == np.dtype(npt):
            return pxt
    return PixelType.UINT8


def _exif_dpi_to_micrometers(dpi_value: float | int | tuple[Any, Any]) -> float | None:
    """Convert a Pillow EXIF DPI tuple/scalar to physical_size in micrometers.

    EXIF stores DPI as dots-per-inch; OME ``physical_size_x`` defaults to
    micrometers. ``1 inch / dpi`` gives inches-per-dot; multiply by
    25400 to get micrometers-per-dot. Returns ``None`` when the input
    is not a positive number.
    """
    if isinstance(dpi_value, tuple):
        if len(dpi_value) == 0:
            return None
        dpi_value = dpi_value[0]
    try:
        dpi = float(dpi_value)
    except (TypeError, ValueError):
        return None
    if dpi <= 0:
        return None
    return _INCH_TO_MICROMETER / dpi


def _ome_from_pil(pil_image: PILImage, array: np.ndarray, axes: list[str]) -> OME:
    """Build a minimal :class:`OME` from a Pillow image and the loaded array.

    Populates ``size_x`` / ``size_y`` / ``size_c`` / ``size_z`` / ``size_t``
    from the array shape and ``physical_size_x`` / ``physical_size_y`` from
    Pillow's ``info["dpi"]`` (set on PNG / JPEG with DPI metadata).
    """
    # Axis sizes
    shape = array.shape
    axis_sizes: dict[str, int] = {a: shape[i] for i, a in enumerate(axes)}
    size_x = axis_sizes.get("x", 1)
    size_y = axis_sizes.get("y", 1)
    size_c = axis_sizes.get("c", 1)
    size_z = axis_sizes.get("z", 1)
    size_t = axis_sizes.get("t", 1)

    info = getattr(pil_image, "info", {}) or {}
    dpi = info.get("dpi")
    physical_size_x: float | None = None
    physical_size_y: float | None = None
    if isinstance(dpi, tuple) and len(dpi) >= 2:
        physical_size_x = _exif_dpi_to_micrometers(dpi[0])
        physical_size_y = _exif_dpi_to_micrometers(dpi[1])
    elif dpi is not None:
        v = _exif_dpi_to_micrometers(dpi)
        physical_size_x = v
        physical_size_y = v

    pixels = Pixels(
        size_x=size_x,
        size_y=size_y,
        size_c=size_c,
        size_z=size_z,
        size_t=size_t,
        dimension_order="XYCZT",
        type=_dtype_to_pixel_type(array.dtype),
        physical_size_x=physical_size_x,
        physical_size_y=physical_size_y,
    )
    return OME(images=[OMEImage(pixels=pixels)])


def _axes_for_pil_array(array: np.ndarray) -> list[str]:
    """Return SciStudio axis labels for a Pillow-decoded numpy array.

    Pillow returns 2-D for L (luminance) mode, 3-D ``(H, W, C)`` for RGB
    / RGBA. SciStudio convention puts channel before spatial axes; the
    result is ``["y", "x"]`` for 2-D, ``["c", "y", "x"]`` for 3-D after
    a ``moveaxis`` swap that the caller performs.
    """
    if array.ndim == 2:
        return ["y", "x"]
    if array.ndim == 3:
        return ["c", "y", "x"]
    raise ValueError(f"PIL-loaded array has unsupported ndim={array.ndim} (shape={array.shape!r})")


def _load_pil(path: Path, *, format_label: str) -> Image:
    """Common load path for PNG / JPEG via Pillow.

    Caller passes ``format_label`` purely for the error message; both
    PNG and JPEG decode the same way through ``PIL.Image.open``.
    """
    from PIL import Image as _PILImageMod

    with _PILImageMod.open(str(path)) as pil_image:
        pil_image.load()
        array = np.asarray(pil_image)
        # Pillow returns (H, W, C); move channel axis to the front to
        # match SciStudio ["c", "y", "x"] convention for multi-channel.
        if array.ndim == 3:
            array = np.moveaxis(array, -1, 0)
        axes = _axes_for_pil_array(array)
        ome = _ome_from_pil(pil_image, array, axes)

    img = Image(
        axes=axes,
        shape=tuple(array.shape),
        dtype=str(array.dtype),
        framework=FrameworkMeta(source=str(path)),
        meta=Image.Meta(source_file=str(path), ome=ome),
    )
    img._data = array  # type: ignore[attr-defined]
    return img


def _load_png(path: Path, axes_override: list[str] | None = None, **_: Any) -> Image:
    """Load a PNG file into an :class:`Image`.

    ``axes_override`` lets a caller overwrite the axis labels chosen by
    the decoded array shape (default 2D → ``["y", "x"]``, 3D →
    ``["c", "y", "x"]``). Length must match the array's ndim. The pixel
    buffer is preserved unchanged — only the labels are rewritten.
    """
    img = _load_pil(path, format_label="PNG")
    if axes_override is not None and axes_override != img.axes:
        # Permit the caller to overwrite labels (e.g. for grayscale that
        # the workflow wants tagged differently). Length must match.
        if len(axes_override) != len(img.axes):
            raise ValueError(
                f"_load_png: axes override {axes_override!r} does not match ndim={len(img.axes)} for {path}"
            )
        # P2-01 (Phase C1 audit, issue #1296): capture the pixel buffer
        # before reconstructing `img` so the rewritten-labels Image
        # carries the decoded pixels rather than `np.asarray([])`.
        source_data = img._data  # type: ignore[attr-defined]
        img = Image(
            axes=axes_override,
            shape=img.shape,
            dtype=img.dtype,
            framework=img.framework,
            meta=img.meta,
        )
        img._data = source_data  # type: ignore[attr-defined]
    return img


def _load_jpeg(path: Path, axes_override: list[str] | None = None, **_: Any) -> Image:
    """Load a JPEG file into an :class:`Image` (see :func:`_load_png`)."""
    img = _load_pil(path, format_label="JPEG")
    if axes_override is not None and axes_override != img.axes:
        if len(axes_override) != len(img.axes):
            raise ValueError(
                f"_load_jpeg: axes override {axes_override!r} does not match ndim={len(img.axes)} for {path}"
            )
        # P2-01 (Phase C1 audit, issue #1296): preserve decoded pixels —
        # see `_load_png` for context.
        source_data = img._data  # type: ignore[attr-defined]
        img = Image(
            axes=axes_override,
            shape=img.shape,
            dtype=img.dtype,
            framework=img.framework,
            meta=img.meta,
        )
        img._data = source_data  # type: ignore[attr-defined]
    return img


def _ome_dpi_value(image: Image) -> tuple[float, float] | None:
    """Return ``(dpi_x, dpi_y)`` from ``Image.Meta.ome.physical_size_*`` if set."""
    if image.meta is None or image.meta.ome is None:
        return None
    if not image.meta.ome.images:
        return None
    pixels = image.meta.ome.images[0].pixels
    psx = pixels.physical_size_x
    psy = pixels.physical_size_y
    if psx is None and psy is None:
        return None
    # physical_size_* is micrometers per pixel by default. DPI = 25400 / um.
    dpi_x = _INCH_TO_MICROMETER / float(psx) if psx and float(psx) > 0 else None
    dpi_y = _INCH_TO_MICROMETER / float(psy) if psy and float(psy) > 0 else None
    if dpi_x is None and dpi_y is None:
        return None
    return (dpi_x or dpi_y or 72.0, dpi_y or dpi_x or 72.0)


def _to_pil_array(image: Image) -> np.ndarray:
    """Materialise *image* as a numpy array suitable for ``PIL.Image.fromarray``.

    Accepts 2-D images directly. For 3-D images with a ``c`` axis,
    moves the channel axis to the last position (PIL convention).
    """
    arr = np.asarray(image.to_memory())
    if arr.ndim == 2:
        return arr
    if arr.ndim == 3:
        # If axes are ["c", "y", "x"], move c to last.
        if "c" in image.axes:
            c_idx = image.axes.index("c")
            if c_idx != arr.ndim - 1:
                arr = np.moveaxis(arr, c_idx, -1)
        return arr
    raise ValueError(f"Pillow save: only 2D or 3D (channel-last) images are supported; got shape {arr.shape!r}")


def _save_png(image: Image, path: Path, **_: Any) -> None:
    """Save *image* as PNG via Pillow.

    Writes EXIF DPI when ``Image.Meta.ome.images[0].pixels.physical_size_*``
    is populated.
    """
    from PIL import Image as _PILImageMod

    arr = _to_pil_array(image)
    pil_img = _PILImageMod.fromarray(arr)
    dpi = _ome_dpi_value(image)
    save_kwargs: dict[str, Any] = {}
    if dpi is not None:
        save_kwargs["dpi"] = dpi
    pil_img.save(str(path), format="PNG", **save_kwargs)


def _save_jpeg(image: Image, path: Path, **_: Any) -> None:
    """Save *image* as JPEG via Pillow.

    Writes EXIF DPI when ``Image.Meta.ome.images[0].pixels.physical_size_*``
    is populated. JPEG cannot store alpha; if input has 4 channels (RGBA)
    the alpha channel is silently dropped.
    """
    from PIL import Image as _PILImageMod

    arr = _to_pil_array(image)
    if arr.ndim == 3 and arr.shape[-1] == 4:
        arr = arr[..., :3]
    pil_img = _PILImageMod.fromarray(arr)
    if pil_img.mode not in ("L", "RGB"):
        pil_img = pil_img.convert("RGB")
    dpi = _ome_dpi_value(image)
    save_kwargs: dict[str, Any] = {}
    if dpi is not None:
        save_kwargs["dpi"] = dpi
    pil_img.save(str(path), format="JPEG", **save_kwargs)


__all__ = [
    "_exif_dpi_to_micrometers",
    "_load_jpeg",
    "_load_png",
    "_ome_from_pil",
    "_save_jpeg",
    "_save_png",
]
