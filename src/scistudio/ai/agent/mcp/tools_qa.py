"""Category (d) MCP tools — documentation and project Q&A (6 tools).

ADR-040 §3.1 FastMCP migration, I40a Phase 2a implementation.

The 6 tools (all read-class) are:

``search_docs``, ``get_doc``, ``list_data``, ``get_project_info``,
``open_gui`` (the last added for #1947 so the agent can open the running
GUI in a browser and self-debug plots / previewers / interactive blocks),
and ``get_agent_context`` (ADR-055 Spec 2, #2279: the external-audience
entry point to the project's already-provisioned agent assets).
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
from scistudio.ai.agent.mcp.server import AUDIENCE_EXTERNAL_TAG, mcp
from scistudio.ai.agent.mcp.tools_workspace import ToolRefusal
from scistudio.core.lineage.store import artifact_size_bytes

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
            # #1983: zarr/parquet datasets are directories, and reporting the
            # directory inode size (64-128 bytes) made a 16 GB artifact tree
            # read as ~0 bytes here. Report the recursive total instead.
            out[kind].append(
                DataAssetEntry(
                    name=entry.name,
                    path=str(entry),
                    size_bytes=artifact_size_bytes(str(entry)) or 0,
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


# ---------------------------------------------------------------------------
# (d.6) get_agent_context  (ADR-055 Spec 2, #2279 — external audience)
#
# The one context tool ADR-055 §5.1 adds. It indexes what provisioning
# (``scistudio.agent_provisioning``) already put in the project — AGENTS.md /
# CLAUDE.md, ``.scistudio/agent-reference/``, the skills trees, the hook
# scripts — plus the project's own ``docs/``, and says for each entry which
# existing tool retrieves it: ``get_doc`` for ``docs/``, ``read_file`` for the
# rest (FR-002: never "everything through get_doc", never copies into docs/).
# Content stays in its files; the response is a bounded index.
# ---------------------------------------------------------------------------

_CONTEXT_INDEX_CAP_PER_CLASS = 100
_CONTEXT_SCAN_CEILING = 5000
_GUIDANCE_EXCERPT_CHARS = 4000
_TITLE_SNIFF_BYTES = 4096

#: (asset class, project-relative root, glob, retrieval tool)
_CONTEXT_ASSET_CLASSES: tuple[tuple[str, str, str, str], ...] = (
    ("project_docs", "docs", "**/*.md", "get_doc"),
    ("agent_reference", ".scistudio/agent-reference", "**/*.md", "read_file"),
    ("skills_claude", ".claude/skills", "*/SKILL.md", "read_file"),
    ("skills_agents", ".agents/skills", "*/SKILL.md", "read_file"),
    ("hooks", ".claude/hooks", "*.py", "read_file"),
)

_GUIDANCE_FILES = ("AGENTS.md", "CLAUDE.md")

_HOOK_EXECUTION_LOCATION = (
    "The provisioned hook scripts run only inside a local Claude Code or Codex CLI session that loads this "
    "project's .claude/settings.json or .codex/config.toml, on the machine where that CLI runs. A WebMCP "
    "host does not execute them, and SciStudio cannot observe whether any host did — reading a hook file "
    "is not evidence that it ran. Each entry's server_side_equivalent says exactly where SciStudio enforces "
    "the rule itself and where it does not: the workspace author tools apply their rules on every call from "
    "any transport; scaffold_block's list_blocks rule applies to WebMCP bridge calls only; and run_command "
    "does not check command text against the file-protection rules — a command runs with the user's "
    "ordinary permissions and can change any file the user can (ADR-055 section 5.3)."
)

#: (hook, host trigger, purpose, server-side equivalent) for the seven provisioned hooks.
_HOOK_GUIDANCE: tuple[tuple[str, str, str, str], ...] = (
    (
        "deny_scistudio_cli",
        "PreToolUse: Bash",
        "Blocks shell calls to the scistudio CLI.",
        "run_command refuses commands that invoke the scistudio CLI (the hook's pattern plus common launchers "
        "and shell wrappers) and names the MCP tools to use. This is parity with the hook, not containment.",
    ),
    (
        "protect_workflow_yaml",
        "PreToolUse: Edit|Write|MultiEdit",
        "Blocks direct edits to workflows/*.yaml.",
        "Author tools refuse any mutation whose source or target is workflows/*.yaml|*.yml; use "
        "write_workflow, update_block_config, or edit_workflow.",
    ),
    (
        "protect_data_dir",
        "PreToolUse: Edit|Write|MultiEdit|Bash",
        "Blocks direct edits and deletes under data/.",
        "Author tools refuse any mutation under data/; produce data with run_workflow. Backend runtime "
        "writes into data/ are unaffected. Not applied to run_command: unlike the local hook's Bash matcher, "
        "a command can change files under data/.",
    ),
    (
        "enforce_list_blocks_before_block_write",
        "PreToolUse: Edit|Write|MultiEdit|Bash|scaffold_block",
        "Requires list_blocks before authoring a blocks/*.py file.",
        "Author-tool writes to blocks/*.py (from any transport) and scaffold_block through the WebMCP bridge "
        "are refused until list_blocks has run once in this backend lifetime (a backend restart resets it). "
        "Not applied to run_command, or to scaffold_block over the local transport, where the host's own hook "
        "applies.",
    ),
    (
        "mark_list_blocks_called",
        "PostToolUse: list_blocks",
        "Records that list_blocks ran.",
        "list_blocks records the call server-side, from any transport, for the backend lifetime.",
    ),
    (
        "enforce_concrete_port_types",
        "PostToolUse: Edit|Write|MultiEdit|scaffold_block",
        "Warns about generic DataObject or empty accepted_types ports.",
        "Author-tool writes to blocks/*.py return the same warnings in the result's warnings list (non-blocking).",
    ),
    (
        "remind_poll_status",
        "PostToolUse: run_workflow",
        "Reminds the agent to poll get_run_status.",
        "run_workflow results carry a poll_hint field.",
    ),
)


class RetrievalInstruction(BaseModel):
    """How to fetch one indexed asset."""

    tool: str = Field(description="Existing tool that retrieves the asset.")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Arguments to pass to that tool.")


class ContextIndexEntry(BaseModel):
    """One indexed asset with its real path."""

    asset_class: str
    path: str = Field(description="Project-relative POSIX path; exists on disk.")
    title: str | None = Field(default=None, description="First heading, or a skill's name and description.")
    retrieval: RetrievalInstruction


class AssetClassStatus(BaseModel):
    """Whether one class of provisioned asset is present."""

    asset_class: str
    root: str = Field(description="Project-relative directory (or '.' for root guidance files).")
    available: bool
    entry_count: int = 0
    truncated: bool = Field(default=False, description="True when more entries exist than the index lists.")
    retrieval_tool: str
    diagnostic: str | None = Field(default=None, description="Why the class is unavailable, when it is.")


class HookGuidanceEntry(BaseModel):
    """One provisioned hook and what the server enforces in its place."""

    hook: str
    host_trigger: str
    purpose: str
    script_path: str
    script_present: bool
    server_side_equivalent: str


class HookGuidance(BaseModel):
    """Hook guidance with the execution location made explicit."""

    execution_location: str
    host_execution_observed: bool = Field(
        default=False,
        description="Always false: SciStudio never observes whether a host executed a hook.",
    )
    entries: list[HookGuidanceEntry] = Field(default_factory=list)


class AgentContextResult(BaseModel):
    """Result envelope for ``get_agent_context``."""

    status: str = Field(
        description="'ok', or 'refused' with refusal.code 'no_active_project' (no project index without a project)."
    )
    refusal: ToolRefusal | None = Field(default=None, description="Why no project context is available.")
    message: str | None = None
    project: dict[str, Any] | None = Field(default=None, description="Project identity and active context.")
    guidance_summary: str | None = Field(default=None, description="Bounded excerpt of the effective guidance file.")
    guidance_source: str | None = None
    guidance_truncated: bool = False
    asset_classes: list[AssetClassStatus] = Field(default_factory=list)
    index: list[ContextIndexEntry] = Field(default_factory=list)
    hooks: HookGuidance | None = None
    execution_environment: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)


def _sniff_text(path: Path, max_bytes: int = _TITLE_SNIFF_BYTES) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(max_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _asset_title(path: Path) -> str | None:
    text = _sniff_text(path)
    if path.name == "SKILL.md" and text.startswith("---"):
        fields: dict[str, str] = {}
        for line in text.splitlines()[1:]:
            if line.strip() == "---":
                break
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip().strip("\"'")
        name = fields.get("name")
        if name:
            description = fields.get("description", "")
            return (f"{name}: {description}" if description else name)[:200]
    if path.suffix == ".py":
        return None
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()[:200]
    return None


def _index_asset_class(
    root: Path, asset_class: str, rel_root: str, pattern: str, tool: str
) -> tuple[AssetClassStatus, list[ContextIndexEntry]]:
    base = root / rel_root
    if not base.is_dir():
        return (
            AssetClassStatus(
                asset_class=asset_class,
                root=rel_root,
                available=False,
                retrieval_tool=tool,
                diagnostic=(
                    f"{rel_root}/ is not present in this project, so nothing is indexed for this class. "
                    "SciStudio provisions agent assets when a project is created or opened; they may "
                    "also have been removed."
                    if asset_class != "project_docs"
                    else "The project has no docs/ directory; get_doc and search_docs have nothing to read."
                ),
            ),
            [],
        )
    found: list[Path] = []
    for path in base.glob(pattern):
        if path.is_file():
            found.append(path)
            if len(found) >= _CONTEXT_SCAN_CEILING:
                break
    found.sort(key=lambda path: path.as_posix().casefold())
    if not found:
        return (
            AssetClassStatus(
                asset_class=asset_class,
                root=rel_root,
                available=False,
                retrieval_tool=tool,
                diagnostic=f"{rel_root}/ exists but holds no files matching {pattern}.",
            ),
            [],
        )
    entries = []
    for path in found[:_CONTEXT_INDEX_CAP_PER_CLASS]:
        rel = path.relative_to(root).as_posix()
        entries.append(
            ContextIndexEntry(
                asset_class=asset_class,
                path=rel,
                title=_asset_title(path),
                retrieval=RetrievalInstruction(tool=tool, arguments={"path": rel}),
            )
        )
    return (
        AssetClassStatus(
            asset_class=asset_class,
            root=rel_root,
            available=True,
            entry_count=len(found),
            truncated=len(found) > _CONTEXT_INDEX_CAP_PER_CLASS,
            retrieval_tool=tool,
        ),
        entries,
    )


def _guidance(root: Path) -> tuple[AssetClassStatus, list[ContextIndexEntry], str | None, str | None, bool]:
    present = [name for name in _GUIDANCE_FILES if (root / name).is_file()]
    entries = [
        ContextIndexEntry(
            asset_class="guidance",
            path=name,
            title=_asset_title(root / name),
            retrieval=RetrievalInstruction(tool="read_file", arguments={"path": name}),
        )
        for name in present
    ]
    status = AssetClassStatus(
        asset_class="guidance",
        root=".",
        available=bool(present),
        entry_count=len(present),
        retrieval_tool="read_file",
        diagnostic=None
        if present
        else "Neither AGENTS.md nor CLAUDE.md is present at the project root, so no project guidance is summarized.",
    )
    if not present:
        return status, entries, None, None, False
    # AGENTS.md is the canonical instruction file; CLAUDE.md routes to it (#2137).
    source = present[0]
    text = _sniff_text(root / source, _GUIDANCE_EXCERPT_CHARS * 4)
    return (
        status,
        entries,
        text[:_GUIDANCE_EXCERPT_CHARS],
        source,
        len(text) > _GUIDANCE_EXCERPT_CHARS or ((root / source).stat().st_size > _GUIDANCE_EXCERPT_CHARS * 4),
    )


def _project_identity(ctx: Any, root: Path) -> dict[str, Any]:
    identity: dict[str, Any] = {"path": str(root), "active_workflow_id": getattr(ctx, "active_workflow_id", None)}
    project_file = root / "project.yaml"
    if project_file.is_file():
        try:
            raw = yaml_module.safe_load(_sniff_text(project_file, 64 * 1024)) or {}
        except yaml_module.YAMLError:
            raw = {}
        meta = raw.get("project", {}) if isinstance(raw, dict) else {}
        if isinstance(meta, dict):
            for key in ("id", "name", "description"):
                if meta.get(key) is not None:
                    identity[key] = meta[key]
    workflows_dir = root / "workflows"
    identity["workflows"] = sorted(path.stem for path in workflows_dir.glob("*.yaml")) if workflows_dir.is_dir() else []
    return identity


def _capabilities() -> dict[str, Any]:
    return {
        "read_scope": (
            "Inspect tools (list_directory, get_file_info, search_files, read_file) accept absolute paths and read "
            "anything the backend's OS user can read; relative paths resolve against the active project. Reads "
            "are bounded; server-resident datasets are used in place by absolute path."
        ),
        "author_scope": (
            "Author tools (write_file, create_directory, patch_file, move_path, delete_path) change files only "
            "inside the active project, through the editor's write path (the open UI updates; drop-in blocks "
            "reload). They refuse data/ (use run_workflow) and workflows/*.yaml (use write_workflow / "
            "update_block_config)."
        ),
        "execution": (
            "run_command runs shell commands in the active project with SciStudio's bundled Python first on PATH, "
            "as managed jobs (list_commands, get_command_status, cancel_command). Commands that invoke the "
            "scistudio CLI are refused."
        ),
        "transfer": "No upload or download tools are registered on this instance.",
        "tools": {
            "context": ["get_agent_context", "get_project_info", "search_docs", "get_doc"],
            "inspect": ["list_directory", "get_file_info", "search_files", "read_file"],
            "author": ["write_file", "create_directory", "patch_file", "move_path", "delete_path"],
            "execution": ["run_command", "list_commands", "get_command_status", "cancel_command"],
            "workflow": ["list_blocks", "get_block_schema", "write_workflow", "run_workflow", "get_run_status"],
        },
    }


def _agent_context_sync(ctx: Any, root: Path) -> AgentContextResult:
    from scistudio.ai.agent.mcp.tools_execution import describe_command_environment

    guidance_status, index, excerpt, source, truncated = _guidance(root)
    classes = [guidance_status]
    for asset_class, rel_root, pattern, tool in _CONTEXT_ASSET_CLASSES:
        status, entries = _index_asset_class(root, asset_class, rel_root, pattern, tool)
        classes.append(status)
        index.extend(entries)
    hooks = HookGuidance(
        execution_location=_HOOK_EXECUTION_LOCATION,
        entries=[
            HookGuidanceEntry(
                hook=hook,
                host_trigger=trigger,
                purpose=purpose,
                script_path=f".claude/hooks/{hook}.py",
                script_present=(root / ".claude" / "hooks" / f"{hook}.py").is_file(),
                server_side_equivalent=equivalent,
            )
            for hook, trigger, purpose, equivalent in _HOOK_GUIDANCE
        ],
    )
    return AgentContextResult(
        status="ok",
        project=_project_identity(ctx, root),
        guidance_summary=excerpt,
        guidance_source=source,
        guidance_truncated=truncated,
        asset_classes=classes,
        index=index,
        hooks=hooks,
        execution_environment=describe_command_environment(root),
        capabilities=_capabilities(),
    )


@mcp.tool(name="get_agent_context", tags={"category:qa", "read", AUDIENCE_EXTERNAL_TAG})
async def get_agent_context() -> AgentContextResult:
    """Start here: the project's instructions, a docs/skills index, the execution environment, and hook guidance.

    Returns project identity, a bounded excerpt of the project guidance
    (AGENTS.md), and an index of the provisioned assets that actually exist —
    project docs/, .scistudio/agent-reference/, the skills trees, the hook
    scripts — each entry naming the tool that retrieves it (get_doc for docs/,
    read_file for the rest). Missing asset classes are reported with a
    diagnostic instead of being invented. Hook guidance states where hooks run
    and what the server enforces in their place. With no project open it says
    so and returns no project index.
    """
    import asyncio

    ctx = get_context()
    project_dir = ctx.project_dir
    if project_dir is None:
        from scistudio.ai.agent.mcp.tools_execution import describe_command_environment

        message = (
            "No project is open in this SciStudio instance, so there is no project guidance or asset index. "
            "Ask the user to open or create a project, then call get_agent_context again."
        )
        return AgentContextResult(
            status="refused",
            refusal=ToolRefusal(code="no_active_project", message=message),
            message=message,
            execution_environment=describe_command_environment(None),
            capabilities=_capabilities(),
        )
    return await asyncio.to_thread(_agent_context_sync, ctx, Path(os.path.realpath(project_dir)))
