"""Category (d) MCP tools — documentation and project Q&A (4 tools).

ADR-040 §3.1 FastMCP migration, S40a skeleton phase. All tool functions
are decorated with ``@mcp.tool(name=...)`` and declare Pydantic result
models. Bodies raise :class:`NotImplementedError` with a detailed
``# TODO(#1012)`` comment block describing the impl approach for I40a
Phase 2a.

The 4 tools (all read-class) are:

``search_docs``, ``get_doc``, ``list_data``, ``get_project_info``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from scieasy.ai.agent.mcp.server import mcp

logger = logging.getLogger(__name__)


# Constants preserved for I40a Phase 2a impl reference.
_SEARCH_MAX_RESULTS = 20
_SEARCH_SNIPPET_CHARS = 200
_DATA_LIST_MAX_ENTRIES = 500


# ---------------------------------------------------------------------------
# Pydantic result models — ADR-040 §3.1 typed envelopes.
# ---------------------------------------------------------------------------


class SearchDocsHit(BaseModel):
    """One result entry from ``search_docs``."""

    path: str = Field(description="Path relative to the docs/ tree root.")
    line: int = Field(description="Line number of first hit.")
    snippet: str = Field(description="Snippet around the first hit (no newlines).")
    score: float = Field(description="Count of hits within the file.")


class GetDocResult(BaseModel):
    """Result envelope for ``get_doc``."""

    path: str = Field(description="Absolute resolved path of the doc.")
    content: str = Field(description="Full text of the doc.")
    bytes: int = Field(description="Byte length of content (utf-8 encoded).")


class DataAssetEntry(BaseModel):
    """One entry in ``list_data``."""

    name: str
    path: str
    size_bytes: int = Field(default=0)
    modified_at: float = Field(description="POSIX mtime as float.")
    is_directory: bool


class ListDataResult(BaseModel):
    """Result envelope for ``list_data``."""

    zarr: list[DataAssetEntry] = Field(default_factory=list)
    parquet: list[DataAssetEntry] = Field(default_factory=list)
    artifacts: list[DataAssetEntry] = Field(default_factory=list)


class RecentRunEntry(BaseModel):
    """One entry in ``get_project_info.recent_runs``."""

    workflow_id: str
    started_at: str
    state: str


class GetProjectInfoResult(BaseModel):
    """Result envelope for ``get_project_info``."""

    project: dict[str, Any] = Field(default_factory=dict, description="Top-level project.yaml::project section.")
    path: str = Field(description="Absolute path of the project root.")
    workflows: list[str] = Field(default_factory=list, description="Names (file stems) of workflows in workflows/.")
    recent_runs: list[RecentRunEntry] = Field(
        default_factory=list,
        description="Best-effort recent run listing via MetadataStore.",
    )


# ---------------------------------------------------------------------------
# (d.1) search_docs
# ---------------------------------------------------------------------------


@mcp.tool(name="search_docs")
async def search_docs(
    query: str = Field(description="Free-text search query (case-insensitive substring match)."),
    scope: str | None = Field(
        default=None,
        description="Optional subdirectory under docs/ to restrict the search to (e.g. 'adr', 'specs').",
    ),
) -> list[SearchDocsHit]:
    """Search the on-disk docs/ tree for matches to a free-text query.

    Use when:
      - You need to find documentation for a feature/concept by keyword.
      - You're looking up an ADR by topic.

    Do NOT use to:
      - Search code — this only walks docs/.
      - Read a known doc — use ``get_doc`` directly.

    Returns up to 20 results sorted by descending hit count.
    """
    # TODO(#1012): port from ADR-033-era impl preserving:
    #   1. _docs_root() — project_dir/docs first, then walk up from
    #      __file__ to find repo-level docs/.
    #   2. PR #744 Codex P1 (discussion_r3231046696): validate scope
    #      resolves within docs/ — otherwise "../../" or absolute paths
    #      silently scan outside. Mirrors the guard in get_doc().
    #   3. Substring match, case-insensitive.
    #   4. Sort by score (count) descending; cap to _SEARCH_MAX_RESULTS=20.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (d.2) get_doc
# ---------------------------------------------------------------------------


@mcp.tool(name="get_doc")
async def get_doc(
    path: str = Field(description="Path to the doc — either 'docs/foo.md' or 'foo.md' (resolved under docs/)."),
) -> GetDocResult:
    """Return the full text of one documentation file.

    Use when:
      - You have a doc path from ``search_docs`` and want the full text.
      - You're reading a known ADR or spec by path.

    Do NOT use to:
      - Search docs — use ``search_docs``.

    Path validation: must resolve within the docs/ tree. Raises
    ``PermissionError`` for paths that escape (e.g. ``../../etc/passwd``).
    """
    # TODO(#1012): port from ADR-033-era impl preserving path-traversal
    #   guard. Reference:
    #   1. _docs_root() → root.
    #   2. Try p, root / p, root.parent / p; for each: resolve, verify
    #      relative_to(root.resolve()) succeeds.
    #   3. PermissionError when none resolve under root; FileNotFoundError
    #      when the resolved path doesn't exist.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (d.3) list_data
# ---------------------------------------------------------------------------


@mcp.tool(name="list_data")
async def list_data(
    project_dir: str = Field(description="Absolute path to the project root."),
) -> ListDataResult:
    """Enumerate data assets in the project workspace.

    Use when:
      - You need to know what data is available before referencing it.
      - You're producing a data-availability summary for the user.

    Do NOT use to:
      - Read data payloads — use ``inspect_data`` / ``preview_data``.

    Walks data/zarr/, data/parquet/, data/artifacts/ and returns one
    entry per top-level dataset. Does not open the datasets — payload
    reads stay in ``preview_data``.
    """
    # TODO(#1012): port from ADR-033-era impl preserving:
    #   1. _DATA_LIST_MAX_ENTRIES = 500 cap.
    #   2. Walks (zarr, "data/zarr"), (parquet, "data/parquet"),
    #      (artifacts, "data/artifacts").
    #   3. Skips entries whose stat() raises OSError.
    #   4. Returns ListDataResult with three lists.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")


# ---------------------------------------------------------------------------
# (d.4) get_project_info
# ---------------------------------------------------------------------------


@mcp.tool(name="get_project_info")
async def get_project_info() -> GetProjectInfoResult:
    """Return high-level information about the active project workspace.

    Use when:
      - You need an overview of the project (name, description,
        workflows, recent runs).
      - You're producing a project-status summary for the user.

    Do NOT use to:
      - Enumerate data — use ``list_data``.
      - List workflows in detail — use ``list_data`` or read individual
        workflows via ``get_workflow``.

    Raises ``FileNotFoundError`` if project.yaml is missing.
    """
    # TODO(#1012): port from ADR-033-era impl. Reference:
    #   1. _resolve_project_root(ctx) → root.
    #   2. yaml.safe_load(project.yaml) → project_meta = raw.get("project", {}).
    #   3. Enumerate workflows/*.yaml stems (sorted).
    #   4. Best-effort recent_runs via get_metadata_store() with the
    #      D38-2.3 deprecation-warning suppression dance.
    #   5. Return GetProjectInfoResult.
    #
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a.
    #   Followup: #1012.
    raise NotImplementedError("S40a skeleton — I40a impl in Phase 2a")
