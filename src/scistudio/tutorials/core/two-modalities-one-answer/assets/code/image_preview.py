"""A previewer for this project's ``HEImage`` type: draw the pixels as a picture.

Core tutorial 4 lands this file in the project's ``previewers/`` directory
when it creates the project. Without it an ``HEImage`` has no previewer of its
own, so the preview panel walks up the type chain, finds the core ``Array``
previewer, and shows a slide as a table of numbers. That fallback is correct
— an HEImage *is* an Array — it is just not how anyone wants to look at one.

A previewer is two things: a **spec** saying which type it claims
(:func:`get_previewers`, the same shape a package or a library previewer
uses), and a **render function** that turns a bounded read of the data into an
envelope the preview panel can display.

The slides here are color: an H&E stain is read by eye, and a region mask
says what it means *with* color. So this previewer reads the three channels
and puts them back together, rather than showing one of them and calling it
the picture. The PNG it hands back is encoded here, by hand, with ``struct``
and ``zlib`` from the standard library — so you can see there is no magic
anywhere in the chain from pixels to picture.
"""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path
from typing import Any

import numpy as np

from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewEnvelope,
    PreviewErrorCode,
    PreviewErrorInfo,
    PreviewerSpec,
    PreviewMetadata,
)

# A previewer declares which tier it belongs to, and the registry refuses a
# file whose declaration disagrees with where it actually sits. This file is
# written to travel — it starts in this project's ``previewers/`` and "Move to
# My Library" relocates the same bytes into your library's — so it reads its
# tier off its own location: a project's ``previewers/`` sits beside
# ``project.yaml``, and a library's does not.
_OWNER_KIND = (
    OwnerKind.PROJECT if (Path(__file__).resolve().parent.parent / "project.yaml").is_file() else OwnerKind.USER
)

#: The axis a color picture keeps its channels on, and how many it needs
#: before this previewer will treat it as color rather than as one gray plane.
_CHANNEL_AXIS = "c"
_RGB = 3


def _chunk(tag: bytes, body: bytes) -> bytes:
    """One PNG chunk: length, tag, body, CRC of tag and body."""
    return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)


def _png_data_uri(pixels: np.ndarray) -> str:
    """Encode a ``(y, x)`` gray or ``(y, x, 3)`` RGB uint8 array as a PNG URI.

    Color type 0 is grayscale, one byte a pixel; color type 2 is truecolor,
    three. Either way every row is prefixed with a zero — PNG's "no filter"
    byte — and the whole lot is deflated into one IDAT chunk.
    """
    color_type = 2 if pixels.ndim == _RGB else 0
    height, width = pixels.shape[:2]
    raw = b"".join(b"\x00" + row.tobytes() for row in pixels)
    body = (
        _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + body).decode("ascii")


def _plane_matrix(plane: Any) -> np.ndarray:
    """The plane's values as bytes, with missing entries read as zero."""
    matrix = np.asarray(
        [[0.0 if value is None else float(value) for value in row] for row in plane.matrix],
        dtype=float,
    )
    return np.clip(matrix, 0, 255).astype(np.uint8)


def _channel_count(plane: Any) -> int:
    """How many channels this array carries, or zero if it has no channel axis.

    Asked of the array's own shape and axis names rather than of which block
    produced it: a previewer is handed data, not provenance.
    """
    shape = list(getattr(plane, "shape", []) or [])
    axes = list(getattr(plane, "axes", []) or [])
    if _CHANNEL_AXIS not in axes or len(axes) != len(shape):
        return 0
    return int(shape[axes.index(_CHANNEL_AXIS)])


def _error(request: Any, message: str) -> PreviewEnvelope:
    """A failed preview is an envelope that says so, never an exception."""
    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.ERROR,
        metadata=PreviewMetadata(complete=False, failed=True),
        error=PreviewErrorInfo(code=PreviewErrorCode.PROVIDER_EXCEPTION, message=message),
    )


def render_image(request: Any) -> PreviewEnvelope:
    """Render an ``HEImage`` as a picture.

    Reads through ``request.data_access`` — the bounded reader every previewer
    must use, which downsamples a large slide instead of pulling all of it into
    memory — and returns a plot envelope whose payload is a PNG data URI.

    A plane is one face of the array: ``array_plane`` finds the ``y`` and ``x``
    axes by name and hands back that grid, with every other axis navigable by
    index. For a color slide the only other axis is ``c``, so the three
    channels are three reads of the same face.
    """
    if request.storage is None:
        return _error(request, "no stored data to preview")
    try:
        plane = request.data_access.array_plane(request.storage)
    except Exception as exc:
        return _error(request, f"could not read the image: {exc}")

    first = _plane_matrix(plane)
    if first.size == 0:
        return _error(request, "the image plane is empty")

    channels = _channel_count(plane)
    if channels < _RGB:
        # A single-channel picture is drawn as it is stored. Nothing here
        # invents a color for it.
        pixels = first
        alt = "Slide preview"
    else:
        try:
            rest = [
                _plane_matrix(request.data_access.array_plane(request.storage, slice_index=index)) for index in (1, 2)
            ]
        except Exception as exc:
            return _error(request, f"could not read the color channels: {exc}")
        if any(channel.shape != first.shape for channel in rest):
            return _error(request, "the color channels do not share a shape")
        pixels = np.stack([first, *rest], axis=-1)
        alt = "Slide preview, in color"

    # The bounded reader samples a large plane down to a few hundred pixels a
    # side, so what comes back is an overview of the slide rather than every
    # pixel of it. The envelope has to say so: a preview must never present a
    # sampled picture as the data itself (#1886).
    sampled = bool(getattr(plane, "truncated", False))
    if sampled:
        alt += " (sampled overview)"

    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.PLOT,
        payload={"src": _png_data_uri(pixels), "alt": alt},
        metadata=PreviewMetadata(
            sampled=sampled,
            complete=not sampled,
            extra={"shape": plane.shape, "dtype": plane.dtype},
        ),
    )


def get_previewers() -> list[PreviewerSpec]:
    """Declare this previewer to the registry — the drop-in scan calls this.

    ``target_type`` is the whole connection: from now on, anything that previews
    one of these types resolves here instead of falling back to the Array number
    table, because a previewer for the exact type beats a previewer for its
    parent.

    Two specs rather than one, because a spec claims exactly one type. An
    ``HEMask`` is not an ``HEImage`` — the tutorial keeps them apart on purpose
    — but both are grids of colors, and drawing a grid of colors is the same
    job either way.
    """
    return [
        PreviewerSpec(
            previewer_id=f"project.{name.lower()}.view",
            owner_kind=_OWNER_KIND,
            owner_name="project" if _OWNER_KIND is OwnerKind.PROJECT else "my-library",
            target_type=name,
            capabilities=("raster",),
            backend_provider=render_image,
        )
        for name in ("HEImage", "HEMask")
    ]
