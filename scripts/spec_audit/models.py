"""Shared dataclasses for spec_audit pipeline.

InterfaceRecord is the normalized currency that all three extractors emit
and that diff.py joins on. Keep this small and stable — adding fields means
regenerating fixtures.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Kind = Literal[
    "abc",  # abstract base class
    "protocol",  # typing.Protocol
    "pydantic",  # pydantic.BaseModel
    "fastapi_route",  # FastAPI endpoint
    "typer_command",  # Typer CLI command
    "entry_point",  # pyproject.toml entry-point
    "mcp_tool",  # FastMCP @mcp.tool (V1: not yet extracted)
    "ws_message",  # WebSocket message type (V1: not yet extracted)
    "convention",  # documented convention (TODO format, branch naming)
]

Status = Literal["a", "b", "c", "d"]


@dataclass
class InterfaceRecord:
    """One interface contract row. Same shape from all 3 extractors."""

    interface_id: str  # canonical id, e.g. "block-abc.Block.run"
    kind: Kind
    module: str  # one of the N module names from Phase 1
    source_file: str | None  # path relative to repo root; None for spec-only / docs-only
    source_lines: str | None  # "Lnn-Lmm"
    signature: dict[str, Any]  # kind-specific structured form
    extras: dict[str, Any] = field(default_factory=dict)
    # Spec-side only (from extract_spec.py):
    status: Status | None = None
    primary_doc_source: str | None = None
    supplementary_doc_source: list[str] | None = None
    issue: str | None = None
    # Docs-side only (from extract_docs.py):
    doc_anchors: list[dict[str, str]] | None = None  # [{"file": ..., "anchor": ..., "snippet": ...}]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiffFinding:
    """One row of the diff report."""

    interface_id: str
    severity: Literal["error", "warn", "info"]
    category: Literal[
        "code-not-in-spec",  # ERROR: code added without spec amendment
        "spec-not-in-code",  # WARN: spec entry references nonexistent code (c-label expected)
        "signature-mismatch",  # ERROR: code + spec disagree
        "doc-orphan",  # WARN: docs mention symbol absent from code & spec
        "label-mismatch",  # WARN: spec status doesn't match observed code/docs state
        "missing-primary-doc",  # WARN: spec entry missing Primary-doc-source field
        "ok",  # INFO: matched
    ]
    detail: str
    code_record: dict[str, Any] | None = None
    spec_record: dict[str, Any] | None = None
    docs_record: dict[str, Any] | None = None
