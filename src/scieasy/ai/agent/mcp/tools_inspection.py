"""Category (c) MCP tools — run and data inspection (7 tools).

T-ECA-203. See ``docs/specs/embedded-coding-agent-spec.md`` §6 T-ECA-203.

Per the Phase 2 audit checklist, ``inspect_data`` and ``preview_data``
must never load > 8 MiB into RAM. Array previews therefore use
``iter_chunks`` (zarr) rather than ``to_memory()`` so a 4 GB array does
not exhaust memory on Windows / macOS / Linux runners.
"""

from __future__ import annotations

import base64
import contextlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from scieasy.ai.agent.mcp._context import _resolve_project_path, get_context
from scieasy.core.storage.ref import StorageReference

logger = logging.getLogger(__name__)


_LOCK_TIMEOUT_SECONDS = 10.0
_MAX_PREVIEW_BYTES = 8 * 1024 * 1024  # 8 MiB hard cap (Phase 2 audit)
_THUMBNAIL_MAX_DIM = 256
_DATAFRAME_PREVIEW_ROWS = 100
_SERIES_PREVIEW_POINTS = 200
_TEXT_PREVIEW_CHARS = 4096
_BLOCK_LOG_TRUNCATE_BYTES = 16 * 1024  # 16 KiB per stream


def _ref_from_dict(ref: dict[str, Any]) -> StorageReference:
    """Build a :class:`StorageReference` from a JSON-safe dict envelope."""
    return StorageReference(
        backend=str(ref.get("backend", "filesystem")),
        path=str(ref.get("path", "")),
        format=ref.get("format"),
        metadata=ref.get("metadata"),
    )


# ---------------------------------------------------------------------------
# (c.1) get_block_output
# ---------------------------------------------------------------------------


def get_block_output(run_id: str, block_id: str, port: str) -> dict[str, Any]:
    """Resolve the recorded output of one block port from a run.

    Looks up ``runtime.workflow_runs[run_id].scheduler._block_outputs``
    (the engine's in-memory output map). Returns the
    :class:`StorageReference` envelope and the recorded type signature.
    """
    ctx = get_context()
    runs = getattr(ctx, "workflow_runs", None)
    if not isinstance(runs, dict) or run_id not in runs:
        raise KeyError(f"Unknown run: {run_id}")
    run = runs[run_id]
    outputs = getattr(run.scheduler, "_block_outputs", {})
    block_payload = outputs.get(block_id)
    if block_payload is None:
        raise KeyError(f"No output recorded for block '{block_id}' in run '{run_id}'")
    if isinstance(block_payload, dict) and port in block_payload:
        value = block_payload[port]
    else:
        raise KeyError(f"Block '{block_id}' has no output port '{port}' in run '{run_id}'")
    # ``value`` is a wire-format dict per ADR-027.
    type_chain = []
    if isinstance(value, dict):
        meta = value.get("metadata") or {}
        if isinstance(meta, dict):
            chain = meta.get("type_chain")
            if isinstance(chain, list):
                type_chain = [str(x) for x in chain]
    return {
        "ref": value if isinstance(value, dict) else {"value": value},
        "type": {"type_chain": type_chain, "type_name": type_chain[-1] if type_chain else ""},
        "produced_at": "",
    }


# ---------------------------------------------------------------------------
# (c.2) inspect_data
# ---------------------------------------------------------------------------


def inspect_data(ref: dict[str, Any]) -> dict[str, Any]:
    """Return metadata about a stored data reference (no payload).

    Honours the 8 MiB read-cap from the Phase 2 audit checklist: this
    tool only reads metadata, never the payload.
    """
    sref = _ref_from_dict(ref)
    path = Path(sref.path) if sref.path else None
    size = path.stat().st_size if path is not None and path.exists() else 0
    out: dict[str, Any] = {
        "backend": sref.backend,
        "path": sref.path,
        "format": sref.format,
        "size": size,
    }
    md = ref.get("metadata") or {}
    if isinstance(md, dict):
        out["type_chain"] = md.get("type_chain", [])
        out["framework"] = md.get("framework", {})
        out["user_metadata"] = {k: v for k, v in md.items() if k not in {"type_chain", "framework"}}
    # Try MetadataStore lookup for richer fields (ADR-032).
    #
    # Phase 3.5 integration audit P2-4: ``scieasy.core.metadata_store`` is
    # a D38-2.3 deprecation shim that emits ``DeprecationWarning`` on
    # import. MCP tool stderr is forwarded to the agent's PTY, where the
    # warning would surface as noise on every call. Suppress just this
    # warning at the import boundary.
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=DeprecationWarning,
                module=r"scieasy\.core\.metadata_store",
            )
            from scieasy.core.metadata_store import get_metadata_store

            store = get_metadata_store()
        if store is not None and sref.path:
            wire = store.get_wire_by_storage_path(sref.path) if hasattr(store, "get_wire_by_storage_path") else None
            if wire is not None:
                out["metadata_store"] = wire
    except Exception:
        logger.debug("inspect_data: MetadataStore lookup failed", exc_info=True)
    return out


# ---------------------------------------------------------------------------
# (c.3) preview_data
# ---------------------------------------------------------------------------


def _preview_dataframe(path: Path) -> dict[str, Any]:
    import pyarrow.parquet as pq

    if path.suffix.lower() == ".parquet":
        table = pq.read_table(path).slice(0, _DATAFRAME_PREVIEW_ROWS)
    elif path.suffix.lower() == ".csv":
        import pyarrow.csv as pcsv

        table = pcsv.read_csv(str(path)).slice(0, _DATAFRAME_PREVIEW_ROWS)
    else:
        raise ValueError(f"Unsupported dataframe format: {path.suffix}")
    return {
        "fmt": "table",
        "payload": {"columns": table.column_names, "rows": table.to_pylist()},
        "truncated": table.num_rows >= _DATAFRAME_PREVIEW_ROWS,
    }


def _preview_array(path: Path) -> dict[str, Any]:
    """Preview an array using chunked reads.

    Hard cap: a 256x256 PNG thumbnail. We compute the downsample stride
    from the array's stored shape rather than materialising the full
    array — that is how the 8 MiB cap is honoured even on 4 GB inputs.
    """
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        import tifffile

        # Per PR #744 Codex P1 (discussion_r3231046699): never call
        # ``page.asarray()`` blindly — for a multi-GB single-IFD TIFF
        # that materialises the full page into RAM long before the
        # 8 MiB output cap is checked. Instead, prefer a memmap view
        # when the file format supports it; fall back to a bounded
        # read only when the page is small enough.
        with tifffile.TiffFile(str(path)) as tf:
            page = tf.pages[0]
            try:
                page_nbytes = int(page.size) * int(page.dtype.itemsize)
            except (AttributeError, TypeError):
                page_nbytes = 0
            if page_nbytes and page_nbytes > _MAX_PREVIEW_BYTES:
                # Try a zero-copy memmap so we can stride-read below
                # without holding the whole IFD in RAM. tifffile.memmap
                # only succeeds for uncompressed striped/tiled TIFFs.
                try:
                    arr = tifffile.memmap(str(path), page=0, mode="r")
                except (ValueError, OSError, MemoryError):
                    # Compressed or otherwise non-memmappable. Refuse
                    # rather than blow up memory; the agent receives a
                    # clear stub instead of a crash.
                    return {
                        "fmt": "skipped",
                        "payload": {
                            "reason": "tiff_page_exceeds_cap_and_not_memmappable",
                            "page_nbytes": page_nbytes,
                            "cap_bytes": _MAX_PREVIEW_BYTES,
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

    # Compute strides so the thumbnail fits in 256x256 without ever
    # materialising the full array. For zarr we slice with steps to
    # trigger chunked reads.
    import numpy as np

    shape = tuple(int(d) for d in arr.shape)
    while len(shape) > 2:
        # Reduce leading axes by taking index 0 — chunked read for zarr.
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

    # Encode as a grayscale PNG via stdlib (avoid PIL dependency).
    png_bytes = _grayscale_png(thumbnail)
    payload_b64 = base64.b64encode(png_bytes).decode("ascii")
    if len(png_bytes) > _MAX_PREVIEW_BYTES:
        # Should never happen given the 256x256 cap; defensive.
        raise RuntimeError(f"preview_data: thumbnail exceeds {_MAX_PREVIEW_BYTES}-byte cap")
    return {
        "fmt": "png_base64",
        "payload": {"data": payload_b64, "shape": list(shape), "thumbnail_shape": list(thumbnail.shape)},
        "truncated": list(shape) != list(thumbnail.shape),
    }


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
    # Read only the first chunk; never load the entire file.
    with path.open("rb") as fh:
        raw = fh.read(_TEXT_PREVIEW_CHARS)
    text = raw.decode("utf-8", errors="replace")
    return {
        "fmt": "text",
        "payload": {"content": text},
        "truncated": path.stat().st_size > _TEXT_PREVIEW_CHARS,
    }


def _preview_artifact(path: Path) -> dict[str, Any]:
    size = path.stat().st_size if path.exists() else 0
    payload: dict[str, Any] = {"path": str(path), "size_bytes": size}
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"} and size <= _MAX_PREVIEW_BYTES:
        # Stream the raw bytes back if they fit under the cap.
        payload["data_uri"] = "data:image/{};base64,{}".format(
            path.suffix.lower().lstrip("."),
            base64.b64encode(path.read_bytes()).decode("ascii"),
        )
    return {"fmt": "artifact", "payload": payload, "truncated": False}


def preview_data(ref: dict[str, Any], fmt: str) -> dict[str, Any]:
    """Compute a small preview of stored data without OOM risk.

    Type dispatch (per T-ECA-203 contract):

    * DataFrame → first 100 rows via Arrow slice.
    * Array → PIL-free PNG thumbnail clamped to 256x256; chunked read.
    * Series → first 200 entries.
    * Text → first 4096 chars.
    * Artifact → size + (for images) base64 data URI under the 8 MiB cap.
    """
    sref = _ref_from_dict(ref)
    if not sref.path:
        return {"fmt": "empty", "payload": {}, "truncated": False}
    path = Path(sref.path)
    if not path.exists():
        raise FileNotFoundError(f"Data path does not exist: {sref.path}")

    md = ref.get("metadata") or {}
    type_chain = md.get("type_chain", []) if isinstance(md, dict) else []
    top = type_chain[-1] if type_chain else ""
    suffix = path.suffix.lower()

    # Type-chain-first dispatch with format-suffix fallback for refs
    # that have not yet been routed through the worker (e.g. file
    # uploads that have no type_chain).
    is_dataframe = top == "DataFrame" or suffix in {".csv", ".parquet"}
    is_array = top in {"Array", "Image"} or suffix in {".tif", ".tiff", ".zarr"} or path.is_dir()
    is_series = top in {"Series", "Spectrum"}
    is_text = top == "Text" or suffix in {".txt", ".json", ".yaml", ".yml", ".md"}

    if is_dataframe:
        return _preview_dataframe(path)
    if is_series:
        return _preview_series(path, md)
    if is_array:
        return _preview_array(path)
    if is_text:
        return _preview_text(path)
    return _preview_artifact(path)


# ---------------------------------------------------------------------------
# (c.4) get_lineage
# ---------------------------------------------------------------------------


def get_lineage(ref: dict[str, Any]) -> dict[str, Any]:
    """Return the transitive lineage ancestors of a data reference."""
    # Phase 3.5 audit P2-4: suppress D38-2.3 deprecation-warning leak
    # into MCP-tool stderr (see comment in inspect_data above).
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            module=r"scieasy\.core\.metadata_store",
        )
        from scieasy.core.metadata_store import get_metadata_store

        store = get_metadata_store()
    if store is None:
        return {"nodes": [], "edges": [], "note": "no MetadataStore installed"}

    md = ref.get("metadata") or {}
    framework = md.get("framework") if isinstance(md, dict) else None
    object_id = framework.get("object_id") if isinstance(framework, dict) else None
    if not object_id:
        sref = _ref_from_dict(ref)
        if sref.path:
            obj = store.get_by_storage_path(sref.path)
            if obj is not None:
                fmw = getattr(obj.metadata, "framework", None)
                if fmw is not None:
                    object_id = fmw.object_id
    if not object_id:
        return {"nodes": [], "edges": [], "note": "could not resolve object_id"}

    ancestors = store.ancestors(object_id)
    nodes = [{"object_id": a["object_id"], "type_name": a["type_name"], "block_id": a["block_id"]} for a in ancestors]
    edges = [{"source": a["derived_from"], "target": a["object_id"]} for a in ancestors if a.get("derived_from")]
    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# (c.5) get_block_config
# ---------------------------------------------------------------------------


def get_block_config(workflow_path: str, block_id: str) -> dict[str, Any]:
    """Return the static configuration of one block in a workflow file.

    Path handling (issue #790): *workflow_path* is resolved against the
    active project root. Relative paths are interpreted relative to
    ``ctx.project_dir``; absolute paths must already be under the
    project root.
    """
    from scieasy.workflow.serializer import load_yaml

    p = _resolve_project_path(workflow_path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {p}")
    definition = load_yaml(p)
    for node in definition.nodes:
        if node.id == block_id:
            return {
                "block_id": block_id,
                "type": node.block_type,
                "params": dict(node.config),
                "workflow_path": str(p),
            }
    raise KeyError(f"Block '{block_id}' not found in workflow {p}")


# ---------------------------------------------------------------------------
# (c.6) update_block_config  (write-class, OQ7 file-locked, ruamel round-trip)
# ---------------------------------------------------------------------------


def update_block_config(
    workflow_path: str,
    block_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Patch one block's configuration in a workflow YAML on disk.

    Uses ``ruamel.yaml`` to preserve comments and key order. Acquires
    the OQ7 file lock around the read-modify-write.

    Path handling (issue #790): *workflow_path* is resolved against the
    active project root. Relative paths are interpreted relative to
    ``ctx.project_dir``; absolute paths must already be under the
    project root or :class:`PermissionError` is raised. The returned
    envelope carries the absolute resolved ``workflow_path``.

    TODO(#732): once the workflow versioning API ships, the same lock
    boundary should also send the version header to the runtime so the
    canvas's optimistic-concurrency model and the agent share one
    arbitrator. Today the filelock is the only arbitrator.
    """
    from ruamel.yaml import YAML

    p = _resolve_project_path(workflow_path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {p}")
    lock_path = str(p) + ".lock"
    yaml_rt = YAML(typ="rt")
    yaml_rt.preserve_quotes = True

    try:
        with FileLock(lock_path, timeout=_LOCK_TIMEOUT_SECONDS):
            old = p.read_text(encoding="utf-8")
            with p.open("r", encoding="utf-8") as fh:
                doc = yaml_rt.load(fh)
            if not isinstance(doc, dict):
                raise ValueError(f"Workflow YAML at {p} is not a mapping")
            wf_block = doc.get("workflow") or doc
            nodes = wf_block.get("nodes")
            if not isinstance(nodes, list):
                raise ValueError(f"Workflow YAML at {p} has no nodes list")
            target = None
            for node in nodes:
                if isinstance(node, dict) and node.get("id") == block_id:
                    target = node
                    break
            if target is None:
                raise KeyError(f"Block '{block_id}' not found in workflow {p}")
            config_node = target.get("config")
            if not isinstance(config_node, dict):
                target["config"] = dict(params)
            else:
                for key, value in params.items():
                    config_node[key] = value

            # Atomic write: ruamel → tmp → rename.
            fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=str(p.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as out_fh:
                    yaml_rt.dump(doc, out_fh)
                bytes_written = Path(tmp).stat().st_size
                os.replace(tmp, p)
            except Exception:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise
    except Timeout as exc:
        raise TimeoutError(f"update_block_config: could not acquire lock for {p}") from exc

    new = p.read_text(encoding="utf-8")
    diff_summary = f"{len(new.encode('utf-8'))} bytes (was {len(old.encode('utf-8'))})"
    logger.info("update_block_config: %s block=%s (%s)", p, block_id, diff_summary)
    return {
        "block_id": block_id,
        "diff_summary": diff_summary,
        "bytes_written": bytes_written,
        "workflow_path": str(p),
    }


# ---------------------------------------------------------------------------
# (c.7) get_block_logs
# ---------------------------------------------------------------------------


def get_block_logs(run_id: str, block_id: str) -> dict[str, Any]:
    """Return captured stdout/stderr from a block's execution.

    Logs are sourced from the project's ``logs/`` directory by
    convention: ``{project}/logs/{run_id}/{block_id}.stdout`` and
    ``.stderr``. Truncated to keep the MCP frame small.
    """
    ctx = get_context()
    project_dir = ctx.project_dir
    if project_dir is None:
        raise RuntimeError("No project is currently open")

    log_root = project_dir / "logs" / run_id
    stdout_path = log_root / f"{block_id}.stdout"
    stderr_path = log_root / f"{block_id}.stderr"
    if not log_root.exists():
        raise KeyError(f"No log directory for run '{run_id}'")

    def _read_tail(p: Path) -> str:
        if not p.exists():
            return ""
        size = p.stat().st_size
        if size <= _BLOCK_LOG_TRUNCATE_BYTES:
            return p.read_text(encoding="utf-8", errors="replace")
        with p.open("rb") as fh:
            fh.seek(size - _BLOCK_LOG_TRUNCATE_BYTES)
            tail = fh.read()
        return "...\n" + tail.decode("utf-8", errors="replace")

    return {
        "stdout": _read_tail(stdout_path),
        "stderr": _read_tail(stderr_path),
        "truncated": (
            (stdout_path.exists() and stdout_path.stat().st_size > _BLOCK_LOG_TRUNCATE_BYTES)
            or (stderr_path.exists() and stderr_path.stat().st_size > _BLOCK_LOG_TRUNCATE_BYTES)
        ),
        "started_at": "",
        "finished_at": None,
    }
