"""Canonical bounded preview helpers for the ``tools_inspection`` package.

The public ``preview_data`` MCP tool is SciStudio's AI-agent data-inspection
read surface. The removed REST preview APIs are unrelated to this MCP contract.
These helpers return small ``PreviewDataResult``-shaped payloads and enforce the MCP
response budget via bounded reads (Zarr slicing, TIFF memmap/skip guards,
Parquet/CSV batch iteration) so previews never intentionally load a whole large
payload.

The cap constant ``_MAX_PREVIEW_BYTES`` is resolved lazily through the
parent ``tools_inspection`` package at call time so tests that
monkeypatch the package-level binding (see
``test_mcp_tools_inspection.test_preview_data_tiff_oversize_does_not_load_full_page``) reach the real
call sites.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from scistudio.ai.agent.mcp.tools_inspection._helpers import (
    _DATAFRAME_PREVIEW_ROWS,
    _SERIES_PREVIEW_POINTS,
    _TEXT_PREVIEW_CHARS,
    _THUMBNAIL_MAX_DIM,
)


def _max_preview_bytes() -> int:
    """Return the active 8 MiB cap, honouring runtime monkeypatches.

    Tests rebind ``tools_inspection._MAX_PREVIEW_BYTES`` to exercise the
    cap on small fixtures; deferring the lookup keeps that contract.
    """
    from scistudio.ai.agent.mcp import tools_inspection as _pkg

    return int(_pkg._MAX_PREVIEW_BYTES)


def _grayscale_png(matrix: Any) -> bytes:
    """Encode a 2D numpy array as an 8-bit grayscale PNG (stdlib only)."""
    import struct
    import zlib

    import numpy as np

    arr = np.asarray(matrix, dtype=np.float64)
    if arr.size == 0:
        return b""
    arr_min, arr_max = float(arr.min()), float(arr.max())
    if arr_max == arr_min:
        scaled = np.zeros_like(arr, dtype=np.uint8)
    else:
        scaled = ((arr - arr_min) / (arr_max - arr_min) * 255.0).clip(0, 255).astype(np.uint8)
    h, w = scaled.shape
    raw = b"".join(b"\x00" + scaled[row].tobytes() for row in range(h))

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        body = ctype + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")


def _preview_dataframe(path: Path) -> dict[str, Any]:
    """Read at most ``_DATAFRAME_PREVIEW_ROWS`` via streaming, never the full table.

    Regression guard (PR #1053): do not use ``pq.read_table().slice(...)`` or
    ``pcsv.read_csv().slice(...)`` here; those patterns materialize the entire
    file before slicing and defeat the MCP preview cap for large datasets.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    suffix = path.suffix.lower()
    if suffix == ".parquet":
        # Iterate row-batches and concatenate just enough rows for the preview.
        pf = pq.ParquetFile(path)
        batches: list[pa.RecordBatch] = []
        collected = 0
        # batch_size hint to keep memory bounded even on huge files.
        for batch in pf.iter_batches(batch_size=_DATAFRAME_PREVIEW_ROWS):
            need = _DATAFRAME_PREVIEW_ROWS - collected
            if need <= 0:
                break
            if batch.num_rows > need:
                batch = batch.slice(0, need)
            batches.append(batch)
            collected += batch.num_rows
            if collected >= _DATAFRAME_PREVIEW_ROWS:
                break
        if not batches:
            return {
                "fmt": "table",
                "payload": {"columns": pf.schema_arrow.names, "rows": []},
                "truncated": False,
            }
        table = pa.Table.from_batches(batches)
        truncated = pf.metadata.num_rows > _DATAFRAME_PREVIEW_ROWS if pf.metadata else False
    elif suffix == ".csv":
        import pyarrow.csv as pcsv

        # open_csv yields batches incrementally — read only the first chunk
        # that satisfies the preview, never the full file.
        with pcsv.open_csv(str(path)) as reader:
            batches = []
            collected = 0
            try:
                while collected < _DATAFRAME_PREVIEW_ROWS:
                    batch = reader.read_next_batch()
                    need = _DATAFRAME_PREVIEW_ROWS - collected
                    if batch.num_rows > need:
                        batch = batch.slice(0, need)
                    batches.append(batch)
                    collected += batch.num_rows
            except StopIteration:
                pass
            schema_names = reader.schema.names
        if not batches:
            return {
                "fmt": "table",
                "payload": {"columns": schema_names, "rows": []},
                "truncated": False,
            }
        table = pa.Table.from_batches(batches)
        # We can't cheaply know total CSV row count without reading the
        # rest; assume truncated if we filled the buffer.
        truncated = collected >= _DATAFRAME_PREVIEW_ROWS
    else:
        raise ValueError(f"Unsupported dataframe format: {path.suffix}")
    return {
        "fmt": "table",
        "payload": {"columns": table.column_names, "rows": table.to_pylist()},
        "truncated": truncated,
    }


def _preview_array(path: Path) -> dict[str, Any]:
    """Preview an array using chunked reads (8 MiB cap)."""
    max_bytes = _max_preview_bytes()
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        import tifffile

        # PR #744 Codex P1 (discussion_r3231046699): never blindly call
        # page.asarray() on multi-GB TIFFs — use memmap or skip.
        with tifffile.TiffFile(str(path)) as tf:
            page = tf.pages[0]
            try:
                page_nbytes = int(page.size) * int(page.dtype.itemsize) if page.dtype is not None else 0
            except (AttributeError, TypeError):
                page_nbytes = 0
            arr: Any
            if page_nbytes and page_nbytes > max_bytes:
                try:
                    arr = tifffile.memmap(str(path), page=0, mode="r")
                except (ValueError, OSError, MemoryError):
                    return {
                        "fmt": "skipped",
                        "payload": {
                            "reason": "tiff_page_exceeds_cap_and_not_memmappable",
                            "page_nbytes": page_nbytes,
                            "cap_bytes": max_bytes,
                            "shape": list(page.shape),
                        },
                        "truncated": True,
                    }
            else:
                arr = page.asarray()
    elif suffix == ".zarr" or path.is_dir():
        import zarr

        node: Any = zarr.open(str(path), mode="r")
        if isinstance(node, zarr.Array):
            arr = node
        elif "data" in node:
            arr = node["data"]
        else:
            raise ValueError(f"Zarr store at {path} has no top-level array or 'data' dataset")
    else:
        raise ValueError(f"Unsupported array format: {suffix}")

    import numpy as np

    shape = tuple(int(d) for d in arr.shape)
    while len(shape) > 2:
        arr = arr[0]
        shape = tuple(int(d) for d in arr.shape)
    if not shape:
        return {"fmt": "scalar", "payload": float(arr), "truncated": False}
    h, w = shape[0], shape[1] if len(shape) > 1 else 1
    step_h = max(1, h // _THUMBNAIL_MAX_DIM)
    step_w = max(1, w // _THUMBNAIL_MAX_DIM)
    if len(shape) == 1:
        thumbnail = np.asarray(arr[::step_h], dtype=np.float64)[:_THUMBNAIL_MAX_DIM]
        thumbnail = thumbnail[None, :]
    else:
        thumbnail = np.asarray(arr[::step_h, ::step_w], dtype=np.float64)
        thumbnail = thumbnail[:_THUMBNAIL_MAX_DIM, :_THUMBNAIL_MAX_DIM]

    png_bytes = _grayscale_png(thumbnail)
    payload_b64 = base64.b64encode(png_bytes).decode("ascii")
    if len(png_bytes) > max_bytes:
        raise RuntimeError(f"preview_data: thumbnail exceeds {max_bytes}-byte cap")
    return {
        "fmt": "png_base64",
        "payload": {
            "data": payload_b64,
            "shape": list(shape),
            "thumbnail_shape": list(thumbnail.shape),
        },
        "truncated": list(shape) != list(thumbnail.shape),
    }


def _preview_series(path: Path, ref_md: dict[str, Any]) -> dict[str, Any]:
    values = ref_md.get("values", []) if isinstance(ref_md, dict) else []
    if not values and path.exists() and path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq

        table = pq.read_table(path)
        if table.num_columns:
            values = table.column(0).to_pylist()
    points = [{"x": i, "y": v} for i, v in enumerate(values[:_SERIES_PREVIEW_POINTS])]
    return {
        "fmt": "chart",
        "payload": {"points": points},
        "truncated": len(values) > _SERIES_PREVIEW_POINTS,
    }


def _preview_text(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        raw = fh.read(_TEXT_PREVIEW_CHARS)
    text = raw.decode("utf-8", errors="replace")
    return {
        "fmt": "text",
        "payload": {"content": text},
        "truncated": path.stat().st_size > _TEXT_PREVIEW_CHARS,
    }


def _preview_artifact(path: Path) -> dict[str, Any]:
    max_bytes = _max_preview_bytes()
    size = path.stat().st_size if path.exists() else 0
    payload: dict[str, Any] = {"path": str(path), "size_bytes": size}
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"} and size <= max_bytes:
        payload["data_uri"] = "data:image/{};base64,{}".format(
            path.suffix.lower().lstrip("."),
            base64.b64encode(path.read_bytes()).decode("ascii"),
        )
    return {"fmt": "artifact", "payload": payload, "truncated": False}


__all__ = [
    "_grayscale_png",
    "_preview_array",
    "_preview_artifact",
    "_preview_dataframe",
    "_preview_series",
    "_preview_text",
]
