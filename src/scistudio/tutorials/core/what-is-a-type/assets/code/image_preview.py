"""A previewer for this project's ``Image`` type: draw the pixels as a picture.

Core tutorial 2 writes this file into the tutorial project's ``previewers/``
directory after you have seen what happens without it: an ``Image`` has no
previewer of its own, so the preview panel walks up the type chain, finds the
core ``Array`` previewer, and shows your micrograph as a table of numbers.
That fallback is correct — an Image *is* an Array — it is just not how anyone
wants to look at one.

A previewer is two things: a **spec** saying which type it claims
(:func:`get_previewers`, the same shape a package or a library previewer
uses), and a **render function** that turns a bounded read of the data into an
envelope the preview panel can display. This one reads the displayed plane,
scales it to one byte per pixel, and encodes a PNG by hand — ``struct``
from the standard library, so you can see there is no magic anywhere in the
chain from pixels to picture.
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


def _lut() -> bytes:
    """A 256-entry green fire ramp, the way a fluorescence channel is shown.

    A micrograph drawn in grey is legible and looks like nothing anybody works
    with; the same pixels through a channel LUT read as a fluorescence image at
    a glance. The ramp climbs green first, brings red and blue in only near the
    top, and so keeps the dim background dark while saturating cell interiors
    towards white — which is what makes the cells' shape readable rather than
    just their presence.

    Returned as a PNG ``PLTE`` body: 256 RGB triples, one per pixel value. The
    image data stays one byte per pixel — the colour costs 768 bytes for the
    whole picture, which is why an indexed PNG is the right encoding here and
    not a three-channel one.
    """
    table = bytearray()
    for value in range(256):
        t = value / 255.0
        green = min(1.0, t * 1.35)
        red = max(0.0, (t - 0.45) / 0.55) ** 1.2
        blue = max(0.0, (t - 0.75) / 0.25) ** 1.6
        table += bytes((int(red * 255), int(green * 255), int(blue * 255)))
    return bytes(table)


def _chunk(tag: bytes, body: bytes) -> bytes:
    """One PNG chunk: length, tag, body, CRC."""
    payload = tag + body
    return struct.pack(">I", len(body)) + payload + struct.pack(">I", zlib.crc32(payload))


def _png_data_uri(gray: np.ndarray) -> str:
    """Encode a 2-D uint8 array as an indexed-colour PNG data URI, dependency-free."""
    height, width = gray.shape
    raw = b"".join(b"\x00" + row.tobytes() for row in gray)
    png = (
        b"\x89PNG\r\n\x1a\n"
        # Colour type 3 is indexed: every pixel is a palette index, and the
        # palette below is what turns the plane into a channel image.
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
        + _chunk(b"PLTE", _lut())
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _rgb_png_data_uri(rgb: np.ndarray) -> str:
    """Encode an (h, w, 3) uint8 array as a truecolour PNG data URI.

    The overlay cannot go through the indexed encoder above: blending a label
    colour into the channel ramp produces colours that are not in the 256-entry
    palette, which is the whole point of blending.
    """
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + row.tobytes() for row in rgb)
    png = (
        b"\x89PNG\r\n\x1a\n"
        # Colour type 2 is truecolour: three bytes a pixel, no palette.
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


#: The mask colour. One colour for every object rather than one per label:
#: the question this picture answers is "did it find the cells", and the answer
#: reads fastest as a single wash that either covers a cell or does not. Red
#: because the micrograph is green — the two are as far apart as this palette
#: goes, so the mask separates from what it covers at a glance.
_MASK_COLOUR = (255, 64, 64)

#: How much of the mask colour to mix in. Enough that the covered area is
#: unmistakable, little enough that the cell underneath still shows through —
#: the reader is judging whether the mask sits on a cell, so both have to be
#: visible in the same pixel.
_OVERLAY_ALPHA = 0.5


def _to_uint8(matrix: np.ndarray) -> np.ndarray:
    """Scale a plane to 0..255, flat planes included."""
    low = float(np.nanmin(matrix))
    high = float(np.nanmax(matrix))
    scaled = np.zeros_like(matrix) if high <= low else (matrix - low) * (255.0 / (high - low))
    return np.clip(scaled, 0, 255).astype(np.uint8)


def _overlay(micrograph: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Draw the mask over the micrograph it came from, semi-transparently.

    The micrograph goes through the same channel ramp it gets on its own, so
    the cells look the way they did one step earlier, and everything the
    segmentation claimed is washed red over them. A reader deciding whether the
    segmentation found cells needs both at once — a mask alone is a set of
    shapes with nothing to be right or wrong about.

    One colour rather than one per label: the interactive panel is where a
    reader tells the objects apart, and it draws them apart. Here they are
    asking a simpler question — did it find the cells — and a single wash
    answers that faster than eight hues do.
    """
    ramp = np.frombuffer(_lut(), dtype=np.uint8).reshape(256, 3)
    rgb = ramp[_to_uint8(micrograph)].astype(float)

    marked = labels.astype(np.int64) > 0
    if marked.any():
        mask_rgb = np.asarray(_MASK_COLOUR, dtype=float)
        rgb[marked] = rgb[marked] * (1.0 - _OVERLAY_ALPHA) + mask_rgb * _OVERLAY_ALPHA
    return np.clip(rgb, 0, 255).astype(np.uint8)


def _plane_matrix(plane: Any) -> np.ndarray:
    """The plane's values as a float array, with missing entries read as zero."""
    return np.asarray(
        [[0.0 if value is None else float(value) for value in row] for row in plane.matrix],
        dtype=float,
    )


def _is_two_channel(plane: Any) -> bool:
    """Is this the micrograph-plus-labels pair Segment Cells emits?

    Asked of the array's own shape and axis names rather than of which block
    produced it: a previewer is handed data, not provenance. A three-axis array
    whose extra axis is ``c`` and has exactly two entries is the pair; anything
    else — a plain micrograph, a z-stack, a four-channel acquisition — takes
    the single-plane path below.
    """
    shape = list(getattr(plane, "shape", []) or [])
    axes = list(getattr(plane, "axes", []) or [])
    return len(shape) == 3 and axes[:1] == ["c"] and shape[0] == 2


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
    """Render one plane of an ``Image`` as a colour picture.

    Reads through ``request.data_access`` — the bounded reader every previewer
    must use — normalizes the plane to 0..255, and returns a plot envelope
    whose payload is a PNG data URI.
    """
    if request.storage is None:
        return _error(request, "no stored data to preview")
    try:
        plane = request.data_access.array_plane(request.storage)
    except Exception as exc:
        return _error(request, f"could not read the image: {exc}")

    matrix = _plane_matrix(plane)
    if matrix.size == 0:
        return _error(request, "the image plane is empty")

    # Segment Cells emits two channels on one grid — the micrograph it read on
    # c=0, the labels it found on c=1 — so that this previewer can draw one
    # over the other. It is the only way to: a previewer is handed exactly one
    # object, so a label map that did not carry its micrograph along could only
    # ever be shown as coloured shapes floating on nothing.
    if _is_two_channel(plane):
        try:
            labels_plane = request.data_access.array_plane(request.storage, slice_index=1)
        except Exception as exc:
            return _error(request, f"could not read the label channel: {exc}")
        rgb = _overlay(matrix, _plane_matrix(labels_plane))
        return PreviewEnvelope(
            previewer_id=request.spec.previewer_id,
            target=request.target,
            kind=EnvelopeKind.PLOT,
            payload={"src": _rgb_png_data_uri(rgb), "alt": "Labels over the micrograph"},
            metadata=PreviewMetadata(extra={"shape": plane.shape, "dtype": plane.dtype}),
        )

    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.PLOT,
        payload={"src": _png_data_uri(_to_uint8(matrix)), "alt": "Image preview"},
        metadata=PreviewMetadata(extra={"shape": plane.shape, "dtype": plane.dtype}),
    )


def get_previewers() -> list[PreviewerSpec]:
    """Declare this previewer to the registry — the drop-in scan calls this.

    ``target_type="Image"`` is the whole connection: from now on, anything that
    previews an Image resolves here instead of falling back to the Array
    number table, because a previewer for the exact type beats a previewer for
    its parent.
    """
    return [
        PreviewerSpec(
            previewer_id="project.image.view",
            owner_kind=_OWNER_KIND,
            owner_name="project" if _OWNER_KIND is OwnerKind.PROJECT else "my-library",
            target_type="Image",
            capabilities=("raster",),
            backend_provider=render_image,
        )
    ]
