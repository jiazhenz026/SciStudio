"""Category (c) MCP tools — run and data inspection (7 tools).

ADR-040 §3.1 FastMCP migration. All tool functions are decorated with
``@mcp.tool(name=...)`` and declare Pydantic result models.

The 7 tools are:

Read-class (6): ``get_block_output``, ``inspect_data``, ``preview_data``,
``get_lineage``, ``get_block_config``, ``get_block_logs``.
Write-class (1): ``update_block_config``.

Per the Phase 2 audit checklist, ``inspect_data`` and ``preview_data``
never load > 8 MiB into RAM. Array previews use ``iter_chunks`` (zarr)
or ``tifffile.memmap`` for TIFFs so a 4 GB array does not exhaust memory.
"""

from __future__ import annotations

import base64
import contextlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated, Any

from filelock import FileLock, Timeout
from pydantic import BaseModel, Field

from scieasy.ai.agent.mcp._context import _resolve_project_path, get_context
from scieasy.ai.agent.mcp.server import mcp
from scieasy.core.storage.ref import StorageReference

logger = logging.getLogger(__name__)


_LOCK_TIMEOUT_SECONDS = 10.0  # ADR-033 OQ7
_MAX_PREVIEW_BYTES = 8 * 1024 * 1024  # 8 MiB hard cap (Phase 2 audit)
_THUMBNAIL_MAX_DIM = 256
_DATAFRAME_PREVIEW_ROWS = 100
_SERIES_PREVIEW_POINTS = 200
_TEXT_PREVIEW_CHARS = 4096
_BLOCK_LOG_TRUNCATE_BYTES = 16 * 1024  # 16 KiB per stream


# ---------------------------------------------------------------------------
# Pydantic result models.
# ---------------------------------------------------------------------------


class TypeChainInfo(BaseModel):
    """Type-chain envelope for a stored data reference."""

    type_chain: list[str] = Field(default_factory=list)
    type_name: str = Field(default="")


class GetBlockOutputResult(BaseModel):
    """Result envelope for ``get_block_output``."""

    ref: dict[str, Any] = Field(description="StorageReference wire-format dict (ADR-027).")
    type: TypeChainInfo = Field(default_factory=TypeChainInfo)
    produced_at: str = Field(default="", description="ISO timestamp when the output was produced.")


class InspectDataResult(BaseModel):
    """Result envelope for ``inspect_data`` — metadata only, no payload."""

    backend: str = Field(description="Storage backend name.")
    path: str = Field(description="Storage path of the referenced object.")
    format: str | None = Field(default=None, description="Format hint.")
    size: int = Field(default=0, description="Byte size on disk; 0 if path is a directory.")
    type_chain: list[str] = Field(default_factory=list)
    framework: dict[str, Any] = Field(default_factory=dict)
    user_metadata: dict[str, Any] = Field(default_factory=dict)
    metadata_store: dict[str, Any] | None = Field(
        default=None,
        description="Optional richer metadata from the MetadataStore (ADR-032).",
    )


class PreviewDataResult(BaseModel):
    """Result envelope for ``preview_data``."""

    fmt: str = Field(description="Preview shape identifier.")
    payload: Any = Field(description="Shape-specific payload dict.")
    truncated: bool = Field(description="True if the preview omits content beyond the cap.")


class LineageNode(BaseModel):
    object_id: str
    type_name: str
    block_id: str | None = None


class LineageEdge(BaseModel):
    source: str
    target: str


class GetLineageResult(BaseModel):
    """Result envelope for ``get_lineage``."""

    nodes: list[LineageNode] = Field(default_factory=list)
    edges: list[LineageEdge] = Field(default_factory=list)
    note: str | None = Field(
        default=None,
        description="Diagnostic note when no MetadataStore or object_id is unresolvable.",
    )


class GetBlockConfigResult(BaseModel):
    """Result envelope for ``get_block_config``."""

    block_id: str
    type: str = Field(description="Block type name.")
    params: dict[str, Any] = Field(default_factory=dict)
    workflow_path: str = Field(description="Absolute resolved path of the workflow file.")


class UpdateBlockConfigResult(BaseModel):
    """Result envelope for ``update_block_config``."""

    block_id: str
    diff_summary: str
    bytes_written: int
    workflow_path: str
    next_step: str = Field(
        default=(
            "Call mcp__scieasy__validate_workflow with the workflow_path to confirm the "
            "patched config still satisfies the schema. If the block is in an active run, "
            "the change does NOT affect the running scheduler — re-run via "
            "mcp__scieasy__run_workflow to apply."
        ),
        description="Suggested next MCP call after a config patch.",
    )


class GetBlockLogsResult(BaseModel):
    """Result envelope for ``get_block_logs``."""

    stdout: str = Field(default="", description="Tail of captured stdout (truncated to 16 KiB).")
    stderr: str = Field(default="", description="Tail of captured stderr (truncated to 16 KiB).")
    truncated: bool = Field(description="True if either stream was truncated.")
    started_at: str = Field(default="", description="ISO timestamp when the block started.")
    finished_at: str | None = Field(default=None, description="ISO timestamp when the block finished.")


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _ref_from_dict(ref: dict[str, Any]) -> StorageReference:
    """Build a :class:`StorageReference` from a JSON-safe dict envelope."""
    return StorageReference(
        backend=str(ref.get("backend", "filesystem")),
        path=str(ref.get("path", "")),
        format=ref.get("format"),
        metadata=ref.get("metadata"),
    )


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

    8 MiB cap honoured by checking page nbytes before any blind asarray()
    call (PR #744 Codex P1).
    """
    import numpy as np

    suffix = path.suffix.lower()
    arr: Any
    if suffix in {".tif", ".tiff"}:
        import tifffile

        with tifffile.TiffFile(str(path)) as tf:
            page = tf.pages[0]
            try:
                dtype = page.dtype
                page_nbytes = int(page.size) * int(dtype.itemsize) if dtype is not None else 0
            except (AttributeError, TypeError):
                page_nbytes = 0
            if page_nbytes and page_nbytes > _MAX_PREVIEW_BYTES:
                try:
                    arr = tifffile.memmap(str(path), page=0, mode="r")
                except (ValueError, OSError, MemoryError):
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
    if len(png_bytes) > _MAX_PREVIEW_BYTES:
        raise RuntimeError(f"preview_data: thumbnail exceeds {_MAX_PREVIEW_BYTES}-byte cap")
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
    size = path.stat().st_size if path.exists() else 0
    payload: dict[str, Any] = {"path": str(path), "size_bytes": size}
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"} and size <= _MAX_PREVIEW_BYTES:
        payload["data_uri"] = "data:image/{};base64,{}".format(
            path.suffix.lower().lstrip("."),
            base64.b64encode(path.read_bytes()).decode("ascii"),
        )
    return {"fmt": "artifact", "payload": payload, "truncated": False}


# ---------------------------------------------------------------------------
# (c.1) get_block_output
# ---------------------------------------------------------------------------


@mcp.tool(name="get_block_output")
async def get_block_output(
    run_id: str = Field(description="Run identifier from run_workflow."),
    block_id: str = Field(description="Block id within the workflow."),
    port: str = Field(description="Output port name to resolve."),
) -> GetBlockOutputResult:
    """Resolve the recorded output of one block port from a run.

    Use when:
      - A run has succeeded and you want to inspect a specific block's
        output reference before previewing it.
      - You're debugging by tracing what was produced at each stage.

    Do NOT use to:
      - Read the payload — use ``preview_data`` with the returned ref.
      - Read raw block logs — use ``get_block_logs``.

    Raises ``KeyError`` if the run, block, or port is unknown.
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

    type_chain: list[str] = []
    if isinstance(value, dict):
        meta = value.get("metadata") or {}
        if isinstance(meta, dict):
            chain = meta.get("type_chain")
            if isinstance(chain, list):
                type_chain = [str(x) for x in chain]
    return GetBlockOutputResult(
        ref=value if isinstance(value, dict) else {"value": value},
        type=TypeChainInfo(
            type_chain=type_chain,
            type_name=type_chain[-1] if type_chain else "",
        ),
        produced_at="",
    )


# ---------------------------------------------------------------------------
# (c.2) inspect_data
# ---------------------------------------------------------------------------


@mcp.tool(name="inspect_data")
async def inspect_data(
    ref: Annotated[
        dict[str, Any],
        Field(description="StorageReference wire-format dict (from get_block_output)."),
    ],
) -> InspectDataResult:
    """Return metadata about a stored data reference (no payload).

    Use when:
      - You need to know a reference's type/size/format before previewing.

    Do NOT use to:
      - Read the payload — use ``preview_data``.

    Honours the Phase 2 audit 8 MiB read-cap — this tool ONLY reads
    metadata, never the payload.
    """
    sref = _ref_from_dict(ref)
    path = Path(sref.path) if sref.path else None
    size = path.stat().st_size if path is not None and path.exists() and path.is_file() else 0
    type_chain: list[str] = []
    framework: dict[str, Any] = {}
    user_metadata: dict[str, Any] = {}
    md = ref.get("metadata") or {}
    if isinstance(md, dict):
        chain = md.get("type_chain", [])
        type_chain = [str(x) for x in chain] if isinstance(chain, list) else []
        framework = md.get("framework", {}) if isinstance(md.get("framework"), dict) else {}
        user_metadata = {k: v for k, v in md.items() if k not in {"type_chain", "framework"}}

    metadata_store: dict[str, Any] | None = None
    try:
        from scieasy.core.metadata_store import get_metadata_store

        store = get_metadata_store()
        if store is not None and sref.path and hasattr(store, "get_wire_by_storage_path"):
            wire = store.get_wire_by_storage_path(sref.path)
            if wire is not None and isinstance(wire, dict):
                metadata_store = wire
    except Exception:
        logger.debug("inspect_data: MetadataStore lookup failed", exc_info=True)

    return InspectDataResult(
        backend=sref.backend,
        path=sref.path,
        format=sref.format,
        size=size,
        type_chain=type_chain,
        framework=framework,
        user_metadata=user_metadata,
        metadata_store=metadata_store,
    )


# ---------------------------------------------------------------------------
# (c.3) preview_data
# ---------------------------------------------------------------------------


@mcp.tool(name="preview_data")
async def preview_data(
    ref: Annotated[
        dict[str, Any],
        Field(description="StorageReference wire-format dict."),
    ],
    fmt: str = Field(
        description=(
            "Preferred preview format (advisory; the tool dispatches on the ref's "
            "type_chain regardless): table / png_base64 / chart / text / artifact."
        ),
    ),
) -> PreviewDataResult:
    """Compute a small preview of stored data without OOM risk.

    Use when:
      - You need to see actual data (rows, thumbnail, samples) for
        diagnosis or QA.

    Do NOT use to:
      - Read full datasets — this tool is capped at 8 MiB per response
        and uses chunked reads (zarr step slicing, tifffile memmap) to
        avoid OOM on multi-GB inputs.
      - Inspect metadata only — use ``inspect_data``.

    Dispatch:
      - DataFrame → first 100 rows via Arrow slice.
      - Array → PIL-free PNG thumbnail clamped to 256x256; chunked read.
      - Series → first 200 entries.
      - Text → first 4096 chars.
      - Artifact → size + (for images) base64 data URI under the cap.
    """
    _ = fmt  # advisory; dispatch is type_chain-first.
    sref = _ref_from_dict(ref)
    if not sref.path:
        return PreviewDataResult(fmt="empty", payload={}, truncated=False)
    path = Path(sref.path)
    if not path.exists():
        raise FileNotFoundError(f"Data path does not exist: {sref.path}")

    md = ref.get("metadata") or {}
    type_chain = md.get("type_chain", []) if isinstance(md, dict) else []
    top = type_chain[-1] if type_chain else ""
    suffix = path.suffix.lower()

    is_dataframe = top == "DataFrame" or suffix in {".csv", ".parquet"}
    is_array = top in {"Array", "Image"} or suffix in {".tif", ".tiff", ".zarr"} or path.is_dir()
    is_series = top in {"Series", "Spectrum"}
    is_text = top == "Text" or suffix in {".txt", ".json", ".yaml", ".yml", ".md"}

    if is_dataframe:
        return PreviewDataResult(**_preview_dataframe(path))
    if is_series:
        return PreviewDataResult(**_preview_series(path, md if isinstance(md, dict) else {}))
    if is_array:
        return PreviewDataResult(**_preview_array(path))
    if is_text:
        return PreviewDataResult(**_preview_text(path))
    return PreviewDataResult(**_preview_artifact(path))


# ---------------------------------------------------------------------------
# (c.4) get_lineage
# ---------------------------------------------------------------------------


@mcp.tool(name="get_lineage")
async def get_lineage(
    ref: Annotated[
        dict[str, Any],
        Field(description="StorageReference wire-format dict."),
    ],
) -> GetLineageResult:
    """Return the transitive lineage ancestors of a data reference.

    Use when:
      - You need to trace where a data object came from across multiple
        block runs (ADR-038 lineage).
      - You're auditing reproducibility — full ancestry from raw to result.

    Do NOT use to:
      - Inspect the object itself — use ``inspect_data`` / ``preview_data``.

    Returns empty nodes/edges with a diagnostic ``note`` when no
    MetadataStore is installed or object_id cannot be resolved.
    """
    from scieasy.core.metadata_store import get_metadata_store

    store = get_metadata_store()
    if store is None:
        return GetLineageResult(nodes=[], edges=[], note="no MetadataStore installed")

    md = ref.get("metadata") or {}
    framework = md.get("framework") if isinstance(md, dict) else None
    object_id = framework.get("object_id") if isinstance(framework, dict) else None
    if not object_id:
        sref = _ref_from_dict(ref)
        if sref.path:
            try:
                obj = store.get_by_storage_path(sref.path)
            except Exception:
                obj = None
            if obj is not None:
                fmw = getattr(obj.metadata, "framework", None)
                if fmw is not None:
                    object_id = fmw.object_id
    if not object_id:
        return GetLineageResult(nodes=[], edges=[], note="could not resolve object_id")

    ancestors = store.ancestors(object_id)
    nodes = [
        LineageNode(
            object_id=a["object_id"],
            type_name=a["type_name"],
            block_id=a.get("block_id"),
        )
        for a in ancestors
    ]
    edges = [LineageEdge(source=a["derived_from"], target=a["object_id"]) for a in ancestors if a.get("derived_from")]
    return GetLineageResult(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# (c.5) get_block_config
# ---------------------------------------------------------------------------


@mcp.tool(name="get_block_config")
async def get_block_config(
    workflow_path: str = Field(description="Project-relative path under workflows/."),
    block_id: str = Field(description="Block id within the workflow."),
) -> GetBlockConfigResult:
    """Return the static configuration of one block in a workflow file.

    Use when:
      - You need to read a block's params before patching them.

    Do NOT use to:
      - Patch params — use ``update_block_config``.
      - Inspect runtime state — use ``get_run_status`` /
        ``get_block_output``.

    Raises ``KeyError`` if the block_id is not in the workflow.
    """
    from scieasy.workflow.serializer import load_yaml

    p = _resolve_project_path(workflow_path)
    if not p.exists():
        raise FileNotFoundError(f"Workflow file not found: {p}")
    definition = load_yaml(p)
    for node in definition.nodes:
        if node.id == block_id:
            return GetBlockConfigResult(
                block_id=block_id,
                type=node.block_type,
                params=dict(node.config),
                workflow_path=str(p),
            )
    raise KeyError(f"Block '{block_id}' not found in workflow {p}")


# ---------------------------------------------------------------------------
# (c.6) update_block_config  (write-class, ruamel round-trip)
# ---------------------------------------------------------------------------


@mcp.tool(name="update_block_config")
async def update_block_config(
    workflow_path: Annotated[str, Field(description="Project-relative path under workflows/.")],
    block_id: Annotated[str, Field(description="Block id within the workflow.")],
    params: Annotated[
        dict[str, Any],
        Field(description="Dict of param keys to set or overwrite on the block's config."),
    ],
) -> UpdateBlockConfigResult:
    """Patch one block's configuration in a workflow YAML (preserves comments).

    Use when:
      - You want to change one block's params without re-emitting the
        whole workflow YAML.
      - You need to preserve user comments and key order.

    Do NOT use to:
      - Rewrite an entire workflow — use ``write_workflow`` (whole-file
        replace).
      - Edit ``workflows/*.yaml`` via Bash/Edit/Write — the
        protect_workflow_yaml hook (ADR-040 §3.6) will block such calls.
        This tool is the ONLY supported per-block-patch path.

    Uses ruamel.yaml round-trip mode to preserve formatting.
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

            # Atomic write.
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
    return UpdateBlockConfigResult(
        block_id=block_id,
        diff_summary=diff_summary,
        bytes_written=bytes_written,
        workflow_path=str(p),
    )


# ---------------------------------------------------------------------------
# (c.7) get_block_logs
# ---------------------------------------------------------------------------


@mcp.tool(name="get_block_logs")
async def get_block_logs(
    run_id: str = Field(description="Run identifier from run_workflow."),
    block_id: str = Field(description="Block id within the workflow."),
) -> GetBlockLogsResult:
    """Return captured stdout/stderr from a block's execution.

    Use when:
      - A run has failed and the ``errors`` list in ``get_run_status``
        is not enough — you need the block's print/log output.
      - You're diagnosing slow blocks via their stderr.

    Do NOT use to:
      - Get tracebacks — ``get_run_status`` carries the full traceback
        in its ``errors`` list.

    Tails are truncated to 16 KiB per stream to keep MCP frames small.
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

    def _read_tail(pth: Path) -> str:
        if not pth.exists():
            return ""
        size = pth.stat().st_size
        if size <= _BLOCK_LOG_TRUNCATE_BYTES:
            return pth.read_text(encoding="utf-8", errors="replace")
        with pth.open("rb") as fh:
            fh.seek(size - _BLOCK_LOG_TRUNCATE_BYTES)
            tail = fh.read()
        return "...\n" + tail.decode("utf-8", errors="replace")

    return GetBlockLogsResult(
        stdout=_read_tail(stdout_path),
        stderr=_read_tail(stderr_path),
        truncated=(
            (stdout_path.exists() and stdout_path.stat().st_size > _BLOCK_LOG_TRUNCATE_BYTES)
            or (stderr_path.exists() and stderr_path.stat().st_size > _BLOCK_LOG_TRUNCATE_BYTES)
        ),
        started_at="",
        finished_at=None,
    )
