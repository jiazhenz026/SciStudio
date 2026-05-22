"""Raster preview encoding helpers + type-name inference.

Issue #1430 / umbrella #1427: extracted verbatim from the original
``api/runtime.py`` god-file. The functions ``_image_data_uri_from_matrix``,
``_load_preview_matrix``, ``_downsample_matrix``, and
``_infer_type_name_from_ref`` keep their behavior and are re-exported by
``runtime/__init__.py``.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.text import Text


def _infer_type_name_from_ref(ref: StorageReference) -> str:
    # ADR-027 D2 / #407: prefer the type_chain written by the worker subprocess
    # via _serialise_one().  The rightmost (most specific) entry is the
    # canonical type name.  Fall through to the extension heuristic only when
    # metadata is absent (e.g. file uploads that have no type_chain yet).
    if ref.metadata:
        type_chain = ref.metadata.get("type_chain")
        if type_chain and isinstance(type_chain, list) and type_chain:
            return str(type_chain[-1])

    fmt = (ref.format or "").lower()
    if fmt in {"csv", "parquet"}:
        return DataFrame.__name__
    if fmt in {"txt", "json", "yaml", "yml", "md"}:
        return Text.__name__
    # T-006 / ADR-027 D2: ``Image`` lives in the imaging plugin, not
    # core. Imaging payloads are modelled as generic ``Array`` with
    # ``axes=["y", "x"]`` here; the frontend preview hook still handles
    # the "image" kind via the TIFF/PNG data-URI path below.
    if fmt in {"png", "jpg", "jpeg", "tif", "tiff"}:
        return Array.__name__
    if fmt == "zarr":
        return Array.__name__
    return Artifact.__name__


def _image_data_uri_from_matrix(values: list[list[float]]) -> str:
    """Encode a 2D float matrix as a grayscale PNG data URI.

    Uses stdlib struct + zlib to produce a minimal valid PNG.
    No external dependencies.  Universal browser support.
    """
    import struct
    import zlib

    height = len(values)
    width = len(values[0]) if values and values[0] else 0
    if width == 0 or height == 0:
        return ""
    max_val = max((v for row in values for v in row), default=1.0) or 1.0

    # Build raw scanlines: each row has a filter byte (0 = None) followed by pixel bytes.
    raw = b""
    for row in values:
        raw += b"\x00"  # PNG filter: None
        raw += bytes(max(0, min(255, int(v / max_val * 255))) for v in row)

    def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        body = chunk_type + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    # IHDR: width, height, bit-depth=8, color-type=0 (grayscale)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", ihdr_data)
    png += _png_chunk(b"IDAT", zlib.compress(raw))
    png += _png_chunk(b"IEND", b"")

    return f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"


def _load_preview_matrix(ref: StorageReference) -> Any:
    """Load a raster payload for preview generation."""
    path = Path(ref.path)
    suffix = path.suffix.lower()

    if suffix in {".tif", ".tiff"}:
        import tifffile

        return tifffile.imread(str(path))

    if suffix == ".zarr":
        import zarr

        node: Any = zarr.open(str(path), mode="r")
        if isinstance(node, zarr.Array):
            return node[...]
        if "data" in node:
            data_array: Any = node["data"]
            return data_array[...]
        raise ValueError(f"Zarr preview store at {path} has no top-level array or 'data' dataset")

    raise ValueError(f"Unsupported raster preview format for {path}")


def _downsample_matrix(matrix: Any, max_dim: int = 256) -> Any:
    """Downsample a 2-D matrix to at most *max_dim* on the longest side.

    Uses nearest-neighbour sampling via ``numpy.linspace`` indices so the
    full spatial extent of the image is preserved in the thumbnail.
    """
    import numpy as np

    h, w = int(matrix.shape[0]), int(matrix.shape[1])
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        new_h, new_w = max(1, int(h * scale)), max(1, int(w * scale))
        row_idx = np.linspace(0, h - 1, new_h, dtype=int)
        col_idx = np.linspace(0, w - 1, new_w, dtype=int)
        thumbnail_arr = matrix[np.ix_(row_idx, col_idx)]
    else:
        thumbnail_arr = matrix
    return thumbnail_arr.tolist()
