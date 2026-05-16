"""Category (c) MCP tools — run and data inspection (7 tools).

ADR-040 §3.1 FastMCP migration, S40a skeleton phase. All tool functions
are decorated with ``@mcp.tool(name=...)`` and declare Pydantic result
models. Bodies raise :class:`NotImplementedError` with a detailed
``# TODO(#1012)`` comment block describing the impl approach for I40a
Phase 2a.

The 7 tools are:

Read-class (6): ``get_block_output``, ``inspect_data``, ``preview_data``,
``get_lineage``, ``get_block_config``, ``get_block_logs``.
Write-class (1): ``update_block_config``.

Per the Phase 2 audit checklist, ``inspect_data`` and ``preview_data``
must never load > 8 MiB into RAM. Preserving that contract is a hard
invariant for I40a Phase 2a impl.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from pydantic import BaseModel, Field

from scieasy.ai.agent.mcp.server import mcp

logger = logging.getLogger(__name__)


# Constants preserved for I40a Phase 2a impl reference.
_LOCK_TIMEOUT_SECONDS = 10.0  # ADR-033 OQ7
_MAX_PREVIEW_BYTES = 8 * 1024 * 1024  # 8 MiB hard cap (Phase 2 audit)
_THUMBNAIL_MAX_DIM = 256
_DATAFRAME_PREVIEW_ROWS = 100
_SERIES_PREVIEW_POINTS = 200
_TEXT_PREVIEW_CHARS = 4096
_BLOCK_LOG_TRUNCATE_BYTES = 16 * 1024  # 16 KiB per stream


# ---------------------------------------------------------------------------
# Pydantic result models — ADR-040 §3.1 typed envelopes.
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

    backend: str = Field(description="Storage backend name (filesystem/zarr/parquet/...).")
    path: str = Field(description="Storage path of the referenced object.")
    format: str | None = Field(default=None, description="Format hint (csv/parquet/zarr/...).")
    size: int = Field(default=0, description="Byte size on disk; 0 if path is a directory.")
    type_chain: list[str] = Field(default_factory=list)
    framework: dict[str, Any] = Field(default_factory=dict)
    user_metadata: dict[str, Any] = Field(default_factory=dict)
    metadata_store: dict[str, Any] | None = Field(
        default=None,
        description="Optional richer metadata from the MetadataStore (ADR-032).",
    )


class PreviewDataResult(BaseModel):
    """Result envelope for ``preview_data``.

    The ``fmt`` field signals which preview shape was rendered:
      - ``table`` — dataframe first-N rows.
      - ``png_base64`` — array thumbnail.
      - ``chart`` — series first-N points.
      - ``text`` — text first-N chars.
      - ``artifact`` — image data URI or just size metadata.
      - ``scalar`` — degenerate 0-d array.
      - ``empty`` — no data path.
      - ``skipped`` — content exceeded the 8 MiB cap and was not safely
        previewable (e.g. compressed multi-GB TIFF).
    """

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
        description="Diagnostic note when no MetadataStore is installed or object_id is unresolvable.",
    )


class GetBlockConfigResult(BaseModel):
    """Result envelope for ``get_block_config``."""

    block_id: str
    type: str = Field(description="Block type name.")
    params: dict[str, Any] = Field(default_factory=dict, description="Static config params for the block.")
    workflow_path: str = Field(description="Absolute resolved path of the workflow file.")


class UpdateBlockConfigResult(BaseModel):
    """Result envelope for ``update_block_config``."""

    block_id: str
    diff_summary: str
    bytes_written: int
    workflow_path: str
    next_step: str = Field(
        default=(
            "Call mcp__scieasy__validate_workflow with the workflow_path to confirm the patched config "
            "still satisfies the schema. If the block is in an active run, the change does NOT affect "
            "the running scheduler — re-run via mcp__scieasy__run_workflow to apply."
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
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #   1. runtime.workflow_runs[run_id] lookup → KeyError if absent.
    #   2. run.scheduler._block_outputs[block_id] → dict[port, wire-format].
    #   3. Extract type_chain from value["metadata"]["type_chain"] when present.
    #   4. Return GetBlockOutputResult(ref=value, type=TypeChainInfo(...)).
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (c.2) inspect_data
# ---------------------------------------------------------------------------


@mcp.tool(name="inspect_data")
async def inspect_data(
    ref: Annotated[dict[str, Any], Field(description="StorageReference wire-format dict (from get_block_output).")],
) -> InspectDataResult:
    """Return metadata about a stored data reference (no payload).

    Use when:
      - You need to know a reference's type/size/format before previewing.

    Do NOT use to:
      - Read the payload — use ``preview_data``.

    Honours the Phase 2 audit 8 MiB read-cap — this tool ONLY reads
    metadata, never the payload. Cap-honouring is a hard invariant for
    I40a Phase 2a impl.
    """
    # TODO(#1012): port from ADR-033-era impl preserving the 8 MiB cap.
    #   Reference:
    #   1. _ref_from_dict(ref) → StorageReference.
    #   2. path.stat().st_size for size.
    #   3. Project ref["metadata"] into type_chain, framework, user_metadata.
    #   4. Best-effort MetadataStore lookup via get_metadata_store() with
    #      D38-2.3 deprecation-warning suppression at the import boundary
    #      (warnings.filterwarnings ignore module=r"scieasy\.core\.metadata_store").
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (c.3) preview_data
# ---------------------------------------------------------------------------


@mcp.tool(name="preview_data")
async def preview_data(
    ref: Annotated[dict[str, Any], Field(description="StorageReference wire-format dict.")],
    fmt: str = Field(
        description=(
            "Preferred preview format (advisory; the tool dispatches on "
            "the ref's type_chain regardless): table / png_base64 / chart / text / artifact."
        ),
    ),
) -> PreviewDataResult:
    """Compute a small preview of stored data without OOM risk.

    Use when:
      - You need to see actual data (rows, thumbnail, samples) for
        diagnosis or QA.

    Do NOT use to:
      - Read full datasets — this tool is capped at 8 MiB per response
        and uses chunked reads (zarr iter_chunks, tifffile memmap) to
        avoid OOM on multi-GB inputs.
      - Inspect metadata only — use ``inspect_data``.

    Dispatch:
      - DataFrame → first 100 rows via Arrow slice.
      - Array → PIL-free PNG thumbnail clamped to 256x256; chunked read.
      - Series → first 200 entries.
      - Text → first 4096 chars.
      - Artifact → size + (for images) base64 data URI under the cap.
    """
    # TODO(#1012): port from ADR-033-era impl preserving:
    #   1. _MAX_PREVIEW_BYTES = 8 MiB hard cap.
    #   2. _THUMBNAIL_MAX_DIM = 256.
    #   3. _DATAFRAME_PREVIEW_ROWS = 100, _SERIES_PREVIEW_POINTS = 200,
    #      _TEXT_PREVIEW_CHARS = 4096.
    #   4. Type-chain-first dispatch (DataFrame / Array / Image / Series /
    #      Spectrum / Text) with suffix fallback (.csv/.parquet/.tif/...).
    #   5. _preview_array uses tifffile.memmap for large uncompressed
    #      TIFFs; refuses with fmt="skipped" for compressed multi-GB.
    #   6. _grayscale_png stdlib-only encoder (zlib + struct).
    #
    #   PR #744 Codex P1 (discussion_r3231046699) MUST be preserved:
    #   never call page.asarray() blindly — check page_nbytes vs cap
    #   first, then memmap or skip.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (c.4) get_lineage
# ---------------------------------------------------------------------------


@mcp.tool(name="get_lineage")
async def get_lineage(
    ref: Annotated[dict[str, Any], Field(description="StorageReference wire-format dict.")],
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
    # TODO(#1012): port from ADR-033-era impl preserving the
    #   D38-2.3 deprecation-warning suppression at the metadata_store
    #   import boundary. Reference:
    #   1. get_metadata_store() (with warnings suppressed).
    #   2. Try ref["metadata"]["framework"]["object_id"] first.
    #   3. Fall back to store.get_by_storage_path(sref.path).
    #   4. store.ancestors(object_id) → list of {object_id, type_name,
    #      block_id, derived_from} dicts.
    #   5. Build nodes (LineageNode) + edges (LineageEdge).
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


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
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #   1. _resolve_project_path(workflow_path) for issue #790 semantics.
    #   2. load_yaml(p) → WorkflowDefinition.
    #   3. Iterate definition.nodes; match node.id == block_id.
    #   4. Return GetBlockConfigResult(block_id, type=node.block_type,
    #      params=dict(node.config), workflow_path=str(p)).
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (c.6) update_block_config  (write-class, ruamel round-trip)
# ---------------------------------------------------------------------------


@mcp.tool(name="update_block_config")
async def update_block_config(
    workflow_path: Annotated[str, Field(description="Project-relative path under workflows/.")],
    block_id: Annotated[str, Field(description="Block id within the workflow.")],
    params: Annotated[
        dict[str, Any], Field(description="Dict of param keys to set or overwrite on the block's config.")
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
    # TODO(#1012): port from ADR-033-era impl preserving:
    #   1. _resolve_project_path(workflow_path) for issue #790.
    #   2. FileLock(lock_path, timeout=10.0) per ADR-033 OQ7.
    #   3. YAML(typ="rt") + yaml_rt.preserve_quotes = True (ruamel).
    #   4. Locate target node by id in doc["workflow"]["nodes"] or doc["nodes"].
    #   5. Merge or replace config dict (preserves keys not in params).
    #   6. Atomic write via tempfile + os.replace.
    #
    #   TODO(#732): once workflow versioning API ships, share the lock
    #   boundary with the canvas's optimistic-concurrency model.
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


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
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #   1. project_dir = ctx.project_dir; raise RuntimeError if None.
    #   2. log_root = project_dir / "logs" / run_id.
    #   3. Read tail of {block_id}.stdout / .stderr (last 16 KiB).
    #   4. Truncated flag set if either stream exceeds the cap.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")
