"""Pydantic result-model envelopes for the ``tools_inspection`` tools.

Extracted from the original single-file ``tools_inspection.py`` (#1431,
umbrella #1427). No behavior change.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
            "Call mcp__scistudio__validate_workflow with the workflow_path to confirm the patched config "
            "still satisfies the schema. If the block is in an active run, the change does NOT affect "
            "the running scheduler — re-run via mcp__scistudio__run_workflow to apply."
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


__all__ = [
    "GetBlockConfigResult",
    "GetBlockLogsResult",
    "GetBlockOutputResult",
    "GetLineageResult",
    "InspectDataResult",
    "LineageEdge",
    "LineageNode",
    "PreviewDataResult",
    "TypeChainInfo",
    "UpdateBlockConfigResult",
]
