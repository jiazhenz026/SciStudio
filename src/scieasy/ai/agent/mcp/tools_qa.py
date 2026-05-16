"""Category (d) MCP tools — documentation and project Q&A (4 tools).

ADR-040 §3.1 FastMCP migration, I40a Phase 2a implementation.

The 4 tools (all read-class) are:

``search_docs``, ``get_doc``, ``list_data``, ``get_project_info``.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any

import yaml as yaml_module
from pydantic import BaseModel, Field

from scieasy.ai.agent.mcp._context import _resolve_project_root, get_context
from scieasy.ai.agent.mcp.server import mcp

logger = logging.getLogger(__name__)


_SEARCH_MAX_RESULTS = 20
_SEARCH_SNIPPET_CHARS = 200
_DATA_LIST_MAX_ENTRIES = 500


# ---------------------------------------------------------------------------
# Pydantic result models.
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
# Helpers
# ---------------------------------------------------------------------------


def _docs_root() -> Path:
    """Locate the ``docs/`` tree."""
    ctx = get_context()
    if ctx.project_dir is not None:
        candidate = ctx.project_dir / "docs"
        if candidate.is_dir():
            return candidate
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docs").is_dir():
            return parent / "docs"
    raise FileNotFoundError("No docs/ directory found")


# ---------------------------------------------------------------------------
# (d.1) search_docs
# ---------------------------------------------------------------------------


@mcp.tool(name="search_docs", tags={"category:qa", "read"})
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
    if not query:
        return []
    root = _docs_root()
    root_resolved = root.resolve()
    if scope:
        # PR #744 Codex P1 (discussion_r3231046696): validate scope
        # resolves within docs/ so "../../" etc. cannot silently escape.
        try:
            scoped = (root / scope).resolve()
            scoped.relative_to(root_resolved)
        except (OSError, ValueError):
            return []
        if not scoped.exists():
            return []
        search_root = scoped
    else:
        search_root = root

    q = query.lower()
    results: list[SearchDocsHit] = []
    # Codex P2 (PR #1053): walk the full tree, score every matching doc,
    # then sort + cap. Pre-fix the loop broke at 20 raw traversal hits
    # before sorting, so higher-scoring docs encountered later were
    # discarded silently.
    for md_path in sorted(search_root.rglob("*.md")):
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lower = text.lower()
        idx = lower.find(q)
        if idx == -1:
            continue
        line_no = text[:idx].count("\n") + 1
        start = max(0, idx - 60)
        end = min(len(text), idx + _SEARCH_SNIPPET_CHARS - 60)
        snippet = text[start:end].replace("\n", " ")
        path_str = str(md_path.relative_to(root.parent)) if md_path.is_relative_to(root.parent) else str(md_path)
        results.append(
            SearchDocsHit(
                path=path_str,
                line=line_no,
                snippet=snippet,
                score=float(lower.count(q)),
            )
        )
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:_SEARCH_MAX_RESULTS]


# ---------------------------------------------------------------------------
# (d.2) get_doc
# ---------------------------------------------------------------------------


@mcp.tool(name="get_doc", tags={"category:qa", "read"})
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
    ``PermissionError`` for paths that escape.
    """
    root = _docs_root()
    p = Path(path)
    candidates = [p, root / p, root.parent / p]
    resolved: Path | None = None
    for cand in candidates:
        try:
            r = cand.resolve()
        except OSError:
            continue
        try:
            r.relative_to(root.resolve())
        except ValueError:
            continue
        if r.exists():
            resolved = r
            break
    if resolved is None:
        try:
            attempted = (root / p).resolve()
            attempted.relative_to(root.resolve())
        except ValueError as exc:
            raise PermissionError(f"Path '{path}' escapes the docs/ tree") from exc
        raise FileNotFoundError(f"Doc not found: {path}")

    content = resolved.read_text(encoding="utf-8", errors="replace")
    return GetDocResult(
        path=str(resolved),
        content=content,
        bytes=len(content.encode("utf-8")),
    )


# ---------------------------------------------------------------------------
# (d.3) list_data
# ---------------------------------------------------------------------------


@mcp.tool(name="list_data", tags={"category:qa", "read"})
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
    root = Path(project_dir)
    if not root.exists():
        raise FileNotFoundError(f"Project directory not found: {project_dir}")

    out: dict[str, list[DataAssetEntry]] = {"zarr": [], "parquet": [], "artifacts": []}
    total_count = 0
    for kind, subdir in (("zarr", "data/zarr"), ("parquet", "data/parquet"), ("artifacts", "data/artifacts")):
        dpath = root / subdir
        if not dpath.is_dir():
            continue
        for entry in sorted(dpath.iterdir()):
            try:
                stat = entry.stat()
            except OSError:
                continue
            out[kind].append(
                DataAssetEntry(
                    name=entry.name,
                    path=str(entry),
                    size_bytes=stat.st_size if entry.is_file() else 0,
                    modified_at=stat.st_mtime,
                    is_directory=entry.is_dir(),
                )
            )
            total_count += 1
            if total_count >= _DATA_LIST_MAX_ENTRIES:
                return ListDataResult(**out)
    return ListDataResult(**out)


# ---------------------------------------------------------------------------
# (d.4) get_project_info
# ---------------------------------------------------------------------------


@mcp.tool(name="get_project_info", tags={"category:qa", "read"})
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
    ctx = get_context()
    root = _resolve_project_root(ctx)
    project_file = root / "project.yaml"
    if not project_file.exists():
        raise FileNotFoundError(f"No project.yaml in {root}")
    raw = yaml_module.safe_load(project_file.read_text(encoding="utf-8")) or {}
    project_meta = raw.get("project", {}) if isinstance(raw, dict) else {}

    workflows_dir = root / "workflows"
    workflows: list[str] = []
    if workflows_dir.is_dir():
        workflows = sorted(p.stem for p in workflows_dir.glob("*.yaml"))

    recent_runs: list[RecentRunEntry] = []
    # Best-effort MetadataStore enumeration (D38-2.3 deprecation suppress).
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", module=r"scieasy\.core\.metadata_store")
        try:
            from scieasy.core.metadata_store import get_metadata_store

            store = get_metadata_store()
            if store is not None:
                # Best-effort: leave empty if the store doesn't expose
                # a recent_runs helper. Out of scope per ADR-040 §3.1.
                # TODO(#1012): once MetadataStore grows a proper
                # recent_runs() API, populate this list.
                pass
        except Exception:
            logger.debug("get_project_info: MetadataStore lookup failed", exc_info=True)

    return GetProjectInfoResult(
        project=project_meta,
        path=str(root),
        workflows=workflows,
        recent_runs=recent_runs,
    )
