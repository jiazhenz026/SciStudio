"""Category (d) MCP tools — documentation and project Q&A (5 tools).

ADR-040 §3.1 FastMCP migration, I40a Phase 2a implementation.

The 5 tools (all read-class) are:

``search_docs``, ``get_doc``, ``list_data``, ``get_project_info``,
``open_gui`` (the last added for #1947 so the agent can open the running
GUI in a browser and self-debug plots / previewers / interactive blocks).
"""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path
from typing import Any

import yaml as yaml_module
from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import _resolve_project_root, get_context
from scistudio.ai.agent.mcp.server import mcp

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

    path: str = Field(description="Path of the doc relative to the docs/ tree root (POSIX-style).")
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


class OpenGuiResult(BaseModel):
    """Result envelope for ``open_gui`` (#1947)."""

    url: str = Field(
        description="Base URL of the running SciStudio GUI. Open this in a browser tab.",
    )
    hint: str = Field(
        description="How to use the URL to inspect the live GUI.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _docs_root() -> Path:
    """Locate the ``docs/`` tree visible to the active MCP session.

    The **only** docs root MCP tools ever resolve is
    ``ctx.project_dir/docs``. If the active project has no ``docs/``
    subdirectory this raises :class:`FileNotFoundError`.

    Issue #1097 (P0 information-disclosure): prior to this change
    ``_docs_root()`` fell back to walking ``__file__.parents`` looking
    for any ``docs/`` directory. With SciStudio installed editable from a
    developer checkout (as it commonly is during e2e testing), that walk
    landed on the developer's source-tree docs/ — letting a production
    embedded agent search and read SciStudio ADRs / specs / planning
    documents and disclosing absolute developer-machine paths via MCP
    responses. This violated the ADR-040 §2.1 dev/prod boundary.

    **No env-var backdoor.** An earlier draft of this fix gated the
    parents-walk behind ``SCISTUDIO_DEV=1``, mirroring the monorepo-scan
    convention. That was rejected: any env-var-controlled escape into
    "dev mode" is a soft attack surface — a compromised shell init, a
    malicious launcher script, or a supply-chain dependency that sets
    env vars could silently re-open the leak. The MCP docs surface is
    therefore identical in production and development. Contributors
    iterating on SciStudio itself should read source-tree docs through
    their editor / filesystem tools, not through the production MCP
    server.
    """
    ctx = get_context()
    if ctx.project_dir is not None:
        candidate = ctx.project_dir / "docs"
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError(
        "No docs/ directory is visible to MCP docs tools. The MCP docs "
        "surface is restricted to the active project's own docs/ tree "
        "(see ADR-040 §2.1 / issue #1097). Source-repository docs are "
        "not exposed in any mode."
    )


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
    try:
        root = _docs_root()
    except FileNotFoundError:
        # Issue #1097: no docs/ available in production mode — return an
        # empty list rather than reaching into the developer source tree.
        return []
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
    # Issue #1097: return a path relative to the docs/ tree root so MCP
    # responses do not leak absolute developer-machine filesystem paths
    # (e.g. ``C:\Users\<dev>\workspace\SciStudio\docs\adr\ADR-038.md``).
    try:
        rel_path = resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        rel_path = resolved.name
    return GetDocResult(
        path=rel_path,
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
        warnings.filterwarnings("ignore", module=r"scistudio\.core\.metadata_store")
        try:
            from scistudio.core.metadata_store import get_metadata_store

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


# ---------------------------------------------------------------------------
# (d.5) open_gui  (#1947)
# ---------------------------------------------------------------------------


@mcp.tool(name="open_gui", tags={"category:qa", "read"})
async def open_gui() -> OpenGuiResult:
    """Return the URL of the running SciStudio GUI so you can open it in a browser.

    Use when:
      - You need to SEE the live rendered frontend — a plot, a previewer,
        or an interactive block panel — to debug how it renders or behaves.
      - You want to drive the GUI yourself with your own browser tooling.

    Do NOT use to:
      - Read a data payload — use ``inspect_data`` / ``preview_data``.
      - Render a plot artifact headlessly — use ``run_plot_job``.

    Open the returned URL in a browser tab (the frontend renders the same
    in a plain browser as in the desktop app) and use your own browser
    tools from there. SciStudio does not drive the browser for you.

    The URL is read from the ``SCISTUDIO_ENGINE_API_URL`` the backend
    publishes on startup (ADR-035 §3.10); the SciStudio SPA is served at
    that server's root. Raises ``RuntimeError`` when no GUI server is
    running for this session — for example when the MCP bridge is in
    standalone mode with no backend behind it.
    """
    url = os.environ.get("SCISTUDIO_ENGINE_API_URL", "").strip()
    if not url:
        raise RuntimeError(
            "No running SciStudio GUI is available for this session. The GUI "
            "URL is published only while the backend/API server is running "
            "(via `scistudio gui` / `scistudio serve`). If you are connected "
            "through the MCP bridge in standalone mode, start the GUI first."
        )
    return OpenGuiResult(
        url=url.rstrip("/"),
        hint=(
            "Open this URL in a browser tab and use your own browser tools to "
            "inspect plots, previewers, and interactive block panels. "
            "SciStudio does not control the browser for you."
        ),
    )
