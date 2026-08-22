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
scales it to greyscale, and encodes a PNG by hand — ``struct`` and ``zlib``
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


def _png_data_uri(gray: np.ndarray) -> str:
    """Encode a 2-D uint8 array as a greyscale PNG data URI, dependency-free."""

    def chunk(tag: bytes, body: bytes) -> bytes:
        payload = tag + body
        return struct.pack(">I", len(body)) + payload + struct.pack(">I", zlib.crc32(payload))

    height, width = gray.shape
    raw = b"".join(b"\x00" + row.tobytes() for row in gray)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


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
    """Render one plane of an ``Image`` as a greyscale picture.

    Reads through ``request.data_access`` — the bounded reader every previewer
    must use — normalises the plane to 0..255, and returns a plot envelope
    whose payload is a PNG data URI.
    """
    if request.storage is None:
        return _error(request, "no stored data to preview")
    try:
        plane = request.data_access.array_plane(request.storage)
    except Exception as exc:
        return _error(request, f"could not read the image: {exc}")

    matrix = np.asarray(
        [[0.0 if value is None else float(value) for value in row] for row in plane.matrix],
        dtype=float,
    )
    if matrix.size == 0:
        return _error(request, "the image plane is empty")
    low = float(np.nanmin(matrix))
    high = float(np.nanmax(matrix))
    scaled = np.zeros_like(matrix) if high <= low else (matrix - low) * (255.0 / (high - low))
    gray = np.clip(scaled, 0, 255).astype(np.uint8)

    return PreviewEnvelope(
        previewer_id=request.spec.previewer_id,
        target=request.target,
        kind=EnvelopeKind.PLOT,
        payload={"src": _png_data_uri(gray), "alt": "Image preview"},
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
