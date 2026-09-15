"""MCP tools for documentation and project Q&A (6 tools)."""
# Maintainer context (kept outside generated API documentation):
# Category (d) MCP tools — documentation and project Q&A (6 tools).
#
# ADR-040 §3.1 FastMCP migration, I40a Phase 2a implementation.
#
# The 6 tools (all read-class) are:
#
# ``search_docs``, ``get_doc``, ``list_data``, ``get_project_info``,
# ``open_gui`` (the last added for #1947 so the agent can open the running
# GUI in a browser and self-debug plots / previewers / interactive blocks),
# and ``get_agent_context`` (ADR-055 Spec 2, #2279: the external-audience
# entry point to the project's already-provisioned agent assets).
# Development references: #1947, #2279, ADR-040, ADR-055, Spec 2.

from __future__ import annotations

import contextlib
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import yaml as yaml_module
from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import _resolve_project_root, _safe_under, get_context, get_optional_context
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

    path: str = Field(description="Path of the doc relative to the project directory (POSIX-style).")
    line: int = Field(description="Line number of first hit.")
    snippet: str = Field(description="Snippet around the first hit (no newlines).")
    score: float = Field(description="Count of hits within the file.")


class GetDocResult(BaseModel):
    """Result envelope for ``get_doc``."""

    path: str = Field(description="Path of the doc relative to the project directory (POSIX-style).")
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
    state: str = Field(description="One of running/succeeded/failed/cancelled, as get_run_status reports it.")
    run_id: str = Field(default="", description="The run id run_workflow returned for this run.")


class GetProjectInfoResult(BaseModel):
    """Result envelope for ``get_project_info``."""

    project: dict[str, Any] = Field(default_factory=dict, description="Top-level project.yaml::project section.")
    path: str = Field(description="Absolute path of the project root.")
    workflows: list[str] = Field(default_factory=list, description="Names (file stems) of workflows in workflows/.")
    recent_runs: list[RecentRunEntry] = Field(
        default_factory=list,
        description="The project's most recent runs from its run history, newest first.",
    )


class OpenGuiResult(BaseModel):
    """Result envelope for ``open_gui``."""

    # Development references: #1947, #2385.

    url: str = Field(
        description=(
            "URL to open in a browser tab. When a project is open it deep-links to that "
            "project's view (and the active workflow); otherwise it is the base URL. No tab is opened."
        ),
    )
    base_url: str = Field(
        description="Plain base URL of the running SciStudio GUI, without the project deep link.",
    )
    hint: str = Field(
        description="GUI skill and available browser/computer-use guidance for operating this instance.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


#: File suffixes (lower-case) that ``search_docs`` and ``get_doc`` treat as docs.
_DOC_SUFFIXES = frozenset({".md", ".rst", ".txt"})

#: Directory names ``search_docs`` never descends into, at any depth.
_SEARCH_PRUNED_DIR_NAMES = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv"})

#: Project-root children ``search_docs`` never descends into (the data store).
_SEARCH_PRUNED_ROOT_DIR_NAMES = frozenset({"data"})

#: Doc files larger than this are skipped by ``search_docs`` (large ``.txt`` exports).
_SEARCH_MAX_FILE_BYTES = 10 * 1024 * 1024


def _docs_root() -> Path | None:
    """Return the resolved root of the active project, or ``None`` when no project is open.

    The MCP docs tools read the whole project directory: provisioning writes
    documentation to ``user-guide/``, ``.scistudio/agent-reference/``, and the
    skills trees, and projects have no ``docs/`` directory. Searches stay within
    the active project and never fall back to the installed package's source tree.
    """
    # Development references: #1097, #2375, ADR-040.
    project_dir = get_context().project_dir
    if project_dir is None:
        return None
    return project_dir.resolve()


def _is_doc_file(path: Path) -> bool:
    return path.suffix.lower() in _DOC_SUFFIXES


def _iter_project_docs(project_root: Path, search_root: Path) -> list[Path]:
    """Walk *search_root* for doc files, pruning data, VCS, and environment trees.

    ``os.walk`` with in-place pruning keeps pruned trees untraversed, and
    ``followlinks=False`` keeps directory symlinks from leading out of the
    project. Symlinked files that resolve outside *project_root* are skipped.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(search_root, followlinks=False):
        current = Path(dirpath)
        at_project_root = current == project_root
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in _SEARCH_PRUNED_DIR_NAMES
            and not (at_project_root and name in _SEARCH_PRUNED_ROOT_DIR_NAMES)
            and not (current / name / "pyvenv.cfg").is_file()
        )
        for name in sorted(filenames):
            candidate = current / name
            if not _is_doc_file(candidate):
                continue
            try:
                resolved = candidate.resolve()
                resolved.relative_to(project_root)
                if resolved.stat().st_size > _SEARCH_MAX_FILE_BYTES:
                    continue
            except (OSError, ValueError):
                continue
            found.append(candidate)
    return found


# ---------------------------------------------------------------------------
# (d.1) search_docs
# ---------------------------------------------------------------------------


@mcp.tool(name="search_docs", tags={"category:qa", "read"})
async def search_docs(
    query: str = Field(description="Free-text search query (case-insensitive substring match)."),
    scope: str | None = Field(
        default=None,
        description=(
            "Optional subdirectory of the project directory to restrict the search to "
            "(e.g. 'user-guide', '.scistudio/agent-reference')."
        ),
    ),
) -> list[SearchDocsHit]:
    """Search the project directory's .md, .rst, and .txt files for a free-text query.

    Use when:
      - You need to find documentation for a feature/concept by keyword.
      - You're looking for a user-guide page, agent reference page, or skill by topic.

    Do NOT use to:
      - Search code — only .md/.rst/.txt files are read.
      - Read a known doc — use ``get_doc`` directly.

    The walk covers hidden directories (``.scistudio/``, ``.claude/``,
    ``.agents/``) and skips ``data/``, ``.git/``, ``node_modules/``,
    ``__pycache__/``, and virtualenv directories. Returns up to 20 results
    sorted by descending hit count; each ``path`` is project-relative.
    """
    if not query:
        return []
    root = _docs_root()
    if root is None:
        # Issue #1097: no active project — return an empty list rather than
        # reaching into the developer source tree.
        return []
    if scope:
        # PR #744 Codex P1 (discussion_r3231046696): validate scope
        # resolves within the project so "../../" etc. cannot silently escape.
        try:
            scoped = (root / scope).resolve()
            scoped.relative_to(root)
        except (OSError, ValueError):
            return []
        if not scoped.is_dir():
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
    for doc_path in _iter_project_docs(root, search_root):
        try:
            text = doc_path.read_text(encoding="utf-8", errors="replace")
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
        results.append(
            SearchDocsHit(
                path=doc_path.relative_to(root).as_posix(),
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
    path: str = Field(
        description=(
            "Project-relative path of a .md, .rst, or .txt file (e.g. 'user-guide/README.md'), "
            "as returned by search_docs. An absolute path inside the project is also accepted."
        )
    ),
) -> GetDocResult:
    """Return the full text of one documentation file in the project directory.

    Use when:
      - You have a doc path from ``search_docs`` and want the full text.
      - You're reading a known user-guide, agent-reference, or skill page by path.

    Do NOT use to:
      - Search docs — use ``search_docs``.
      - Read code or data files — only .md/.rst/.txt files are served.

    Path validation: must resolve within the project directory. Raises
    ``PermissionError`` for paths that escape, ``ValueError`` for a non-doc
    suffix, ``FileNotFoundError`` when the file does not exist, and
    ``RuntimeError`` when no project is open.
    """
    root = _docs_root()
    if root is None:
        raise RuntimeError("No project is currently open. Open a project before invoking get_doc.")
    try:
        resolved = _safe_under(root, Path(path))
    except PermissionError as exc:
        raise PermissionError(f"Path '{path}' escapes the project directory") from exc
    if not _is_doc_file(resolved):
        raise ValueError(f"get_doc reads only .md, .rst, and .txt files; '{path}' is not one of these.")
    if not resolved.is_file():
        raise FileNotFoundError(f"Doc not found: {path}")

    content = resolved.read_text(encoding="utf-8", errors="replace")
    # Issue #1097: return a project-relative path so MCP responses do not leak
    # absolute developer-machine filesystem paths.
    return GetDocResult(
        path=resolved.relative_to(root).as_posix(),
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

#: How many runs ``get_project_info.recent_runs`` lists.
_RECENT_RUNS_LIMIT = 20
#: The run history's status spelled the way ``get_run_status`` reports a state.
_RUN_STATE_BY_STATUS = {"completed": "succeeded"}


def _recent_runs(ctx: Any, root: Path) -> list[RecentRunEntry]:
    """The project's most recent runs, read from its lineage run history.

    Uses the runtime's open lineage store when the context exposes one, and
    otherwise reads ``.scistudio/lineage.db`` directly. A project with no run
    history, or one that cannot be read, lists none.
    """
    # Development references: #2401.
    store = getattr(ctx, "lineage_store", None)
    owned = None
    try:
        if store is None:
            db_path = root / ".scistudio" / "lineage.db"
            if not db_path.is_file():
                return []
            from scistudio.core.lineage.store import LineageStore

            store = owned = LineageStore(str(db_path))
        rows = store.list_runs(limit=_RECENT_RUNS_LIMIT)
    except Exception:
        logger.debug("get_project_info: run history lookup failed", exc_info=True)
        return []
    finally:
        if owned is not None:
            with contextlib.suppress(Exception):
                owned.close()
    entries: list[RecentRunEntry] = []
    for row in rows:
        status = str(row.get("status") or "")
        entries.append(
            RecentRunEntry(
                run_id=str(row.get("run_id") or ""),
                workflow_id=str(row.get("workflow_id") or ""),
                started_at=str(row.get("started_at") or ""),
                state=_RUN_STATE_BY_STATUS.get(status, status),
            )
        )
    return entries


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

    recent_runs = _recent_runs(ctx, root)

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
    """Get a URL for the user's current SciStudio project view for browser or computer use.

    Use when you need to operate the interface or inspect its live rendered
    state. This tool only returns an address and guidance; it does not open a
    tab, capture the screen, or operate controls.

    Read the project's ``scistudio-use-gui`` skill for connecting, navigating,
    interacting, and checking the result. Use whichever browser automation,
    Chrome, or computer-use tools your AI client actually provides, following
    their own instructions. Open the complete returned ``url``, preserving its
    project/workflow query parameters and any deployment prefix. Reuse a tab
    on the intended instance/project when possible. Computer use can also
    operate the existing SciStudio desktop window.

    When a project is open, ``url`` deep-links to it
    (``?project=<path>&workflow=<id>``): the page attaches to the project the
    backend already has open, read-only, and shows the active workflow, so
    it skips the welcome page and leaves the user's session untouched. When
    no project is open, ``url`` is the base URL and the hint says so.
    ``base_url`` is always the plain base, without project context. The URL
    is loopback-only: use a browser on the same machine as SciStudio. Confirm
    the intended project and content before acting; other selected items may
    differ between the browser tab and the desktop window.

    If suitable tools are unavailable or cannot reach the instance, report
    that specific limitation. Receiving a URL does not establish GUI access.
    Use ``inspect_data`` / ``preview_data`` for data payloads and
    ``run_plot_job`` for headless plot rendering.

    Reads the backend-published ``SCISTUDIO_ENGINE_API_URL``. Raises
    ``RuntimeError`` when the session has no published GUI address, such as a
    standalone MCP bridge without a running backend.
    """
    # Development references: ADR-035, #2385.
    base_url = os.environ.get("SCISTUDIO_ENGINE_API_URL", "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError(
            "No running SciStudio GUI is available for this session. The GUI "
            "URL is published only while the backend/API server is running "
            "(via `scistudio gui` / `scistudio serve`). If you are connected "
            "through the MCP bridge in standalone mode, start the GUI first."
        )
    loopback_note = (
        "The URL is loopback-only: open it in a browser on the same machine as "
        "SciStudio (a browser elsewhere resolves 127.0.0.1 to itself). Read the "
        "project's scistudio-use-gui skill. Open the complete returned url, "
        "preserving its project/workflow query parameters and any path prefix, "
        "using available browser, Chrome, or computer-use tools. Follow those "
        "tools' instructions. Reuse a tab on the intended instance/project when "
        "possible, or use computer use on the existing SciStudio desktop window. "
        "Confirm the project and content before acting. If no suitable tool can "
        "reach the GUI, state that limitation. open_gui only returns an address; "
        "it does not open a tab, take a screenshot, or operate controls."
    )
    ctx = get_optional_context()
    project_dir = ctx.project_dir if ctx is not None else None
    if project_dir is None:
        return OpenGuiResult(
            url=base_url,
            base_url=base_url,
            hint=(
                "No project is open in SciStudio, so this URL opens the welcome page. "
                "Ask the user to open a project first if you need its view. " + loopback_note
            ),
        )
    params = {"project": str(project_dir)}
    workflow_id = getattr(ctx, "active_workflow_id", None)
    if isinstance(workflow_id, str) and workflow_id:
        params["workflow"] = workflow_id
    return OpenGuiResult(
        url=f"{base_url}/?{urlencode(params, quote_via=quote)}",
        base_url=base_url,
        hint=(
            "This URL opens the project the user has open"
            + (f" on workflow '{workflow_id}'" if "workflow" in params else "")
            + ", attaching read-only to the running session instead of showing "
            "the welcome page. " + loopback_note
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
                    else (
                        "The project has no docs/ directory, so nothing is indexed for this class; "
                        "search_docs and get_doc still read .md/.rst/.txt files across the whole project."
                    )
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
