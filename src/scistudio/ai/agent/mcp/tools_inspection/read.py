"""Read-class inspection tools (6 of 7).

Tools: ``get_block_output``, ``inspect_data``, ``preview_data``,
``get_lineage``, ``get_block_config``, ``get_block_logs``.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from scistudio.ai.agent.mcp._context import _resolve_project_path, get_context
from scistudio.ai.agent.mcp.server import mcp
from scistudio.ai.agent.mcp.tools_inspection._helpers import (
    _BLOCK_LOG_TRUNCATE_BYTES,
    _ref_from_dict,
)
from scistudio.ai.agent.mcp.tools_inspection._models import (
    GetBlockConfigResult,
    GetBlockLogsResult,
    GetBlockOutputResult,
    GetLineageResult,
    InspectDataResult,
    LineageEdge,
    LineageNode,
    PreviewDataResult,
    TypeChainInfo,
)
from scistudio.ai.agent.mcp.tools_inspection._preview import (
    _preview_array,
    _preview_artifact,
    _preview_dataframe,
    _preview_series,
    _preview_text,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# (c.1) get_block_output
# ---------------------------------------------------------------------------


@mcp.tool(name="get_block_output", tags={"category:inspection", "read"})
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


@mcp.tool(name="inspect_data", tags={"category:inspection", "read"})
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
    size = path.stat().st_size if path is not None and path.exists() else 0
    md = ref.get("metadata") or {}
    type_chain: list[str] = []
    framework: dict[str, Any] = {}
    user_md: dict[str, Any] = {}
    if isinstance(md, dict):
        raw_chain = md.get("type_chain", [])
        if isinstance(raw_chain, list):
            type_chain = [str(x) for x in raw_chain]
        fmw = md.get("framework", {})
        framework = fmw if isinstance(fmw, dict) else {}
        user_md = {k: v for k, v in md.items() if k not in {"type_chain", "framework"}}

    metadata_store_payload: dict[str, Any] | None = None
    # D38-2.3 deprecation-warning suppression at the import boundary.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", module=r"scistudio\.core\.metadata_store")
        try:
            from scistudio.core.metadata_store import get_metadata_store

            store = get_metadata_store()
            if store is not None and sref.path and hasattr(store, "get_wire_by_storage_path"):
                metadata_store_payload = store.get_wire_by_storage_path(sref.path)
        except Exception:
            logger.debug("inspect_data: MetadataStore lookup failed", exc_info=True)

    return InspectDataResult(
        backend=sref.backend,
        path=sref.path,
        format=sref.format,
        size=size,
        type_chain=type_chain,
        framework=framework,
        user_metadata=user_md,
        metadata_store=metadata_store_payload,
    )


# ---------------------------------------------------------------------------
# (c.3) preview_data
# ---------------------------------------------------------------------------


@mcp.tool(name="preview_data", tags={"category:inspection", "read"})
async def preview_data(
    ref: Annotated[
        dict[str, Any],
        Field(description="StorageReference wire-format dict."),
    ],
    fmt: str = Field(
        description=(
            "Preferred preview format (advisory; the tool dispatches on "
            "the ref's type_chain regardless): table / png_base64 / chart / text / artifact."
        ),
    ),
) -> PreviewDataResult:
    """Compute a canonical bounded MCP preview of stored data.

    Use when:
      - You need to see actual data (rows, thumbnail, samples) for
        diagnosis or QA.

    Do NOT use to:
      - Read full datasets: this tool is capped at 8 MiB per response
        and uses chunked reads (zarr iter_chunks, tifffile memmap) to
        avoid OOM on multi-GB inputs.
      - Inspect metadata only: use ``inspect_data``.

    Dispatch:
      - DataFrame: first 100 rows via streaming Arrow batches.
      - Array: PNG thumbnail clamped to 256x256 via bounded array reads.
      - Series: first 200 entries.
      - Text: first 4096 chars.
      - Artifact: size plus inline image data only when under the cap.
    """
    del fmt  # advisory; dispatch is type-driven below
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
        result = _preview_dataframe(path)
    elif is_series:
        result = _preview_series(path, md if isinstance(md, dict) else {})
    elif is_array:
        result = _preview_array(path)
    elif is_text:
        result = _preview_text(path)
    else:
        result = _preview_artifact(path)
    return PreviewDataResult(**result)


# ---------------------------------------------------------------------------
# (c.4) get_lineage
# ---------------------------------------------------------------------------


@mcp.tool(name="get_lineage", tags={"category:inspection", "read"})
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
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", module=r"scistudio\.core\.metadata_store")
        from scistudio.core.metadata_store import get_metadata_store

        store = get_metadata_store()
        if store is None:
            return GetLineageResult(note="no MetadataStore installed")

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
            return GetLineageResult(note="could not resolve object_id")

        ancestors = store.ancestors(object_id)
        nodes = [
            LineageNode(
                object_id=a["object_id"],
                type_name=a["type_name"],
                block_id=a.get("block_id"),
            )
            for a in ancestors
        ]
        edges = [
            LineageEdge(source=a["derived_from"], target=a["object_id"]) for a in ancestors if a.get("derived_from")
        ]
        return GetLineageResult(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# (c.5) get_block_config
# ---------------------------------------------------------------------------


@mcp.tool(name="get_block_config", tags={"category:inspection", "read"})
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
    from scistudio.workflow.serializer import load_yaml

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
# (c.7) get_block_logs
# ---------------------------------------------------------------------------


@mcp.tool(name="get_block_logs", tags={"category:inspection", "read"})
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

    truncated = (stdout_path.exists() and stdout_path.stat().st_size > _BLOCK_LOG_TRUNCATE_BYTES) or (
        stderr_path.exists() and stderr_path.stat().st_size > _BLOCK_LOG_TRUNCATE_BYTES
    )

    return GetBlockLogsResult(
        stdout=_read_tail(stdout_path),
        stderr=_read_tail(stderr_path),
        truncated=truncated,
        started_at="",
        finished_at=None,
    )


__all__ = [
    "get_block_config",
    "get_block_logs",
    "get_block_output",
    "get_lineage",
    "inspect_data",
    "preview_data",
]
