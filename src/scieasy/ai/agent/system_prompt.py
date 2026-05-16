"""Compose the system prompt for the embedded agent.

ADR-040 §3.3 / §3.4. This module owns three responsibilities:

1. **Load the base SKILL.md** via ``importlib.resources`` so the prompt
   composer works for both editable installs and wheel installs
   (closes #824). The skill source lives at
   ``src/scieasy/_skills/scieasy/SKILL.md`` after the §3.4 relocation.
2. **Render the tool catalogue** by enumerating FastMCP's
   ``mcp.list_tools()`` surface and splicing it between the
   ``<!-- tool_catalog:begin/end -->`` markers in SKILL.md.
3. **Render a per-project context block** (project name, workflow
   count, plugins, git branch/sha, recent workflows) and splice it
   between the ``<!-- project_context:begin/end -->`` markers
   (closes #825).

Perf budget for ``_render_project_context`` is <100ms even at 1000
workflows; we use :func:`os.scandir` for the directory walk.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from importlib.resources import files
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# Markers in SKILL.md that delimit rendered insertion blocks.
_TOOL_CATALOG_BEGIN = "<!-- tool_catalog:begin -->"
_TOOL_CATALOG_END = "<!-- tool_catalog:end -->"
_PROJECT_CONTEXT_BEGIN = "<!-- project_context:begin -->"
_PROJECT_CONTEXT_END = "<!-- project_context:end -->"

# Category labels for the tool catalogue. Module name → label.
_CATEGORY_LABELS: dict[str, str] = {
    "tools_workflow": "### (a) Workflow design & execution",
    "tools_authoring": "### (b) Block authoring",
    "tools_inspection": "### (c) Run & data inspection",
    "tools_qa": "### (d) Project Q&A",
}

# Tool name → mutation classifier. Write-class tools mutate workflow
# YAMLs, the runtime, or the AI Block signal file.
_WRITE_CLASS_TOOLS: frozenset[str] = frozenset(
    {
        "write_workflow",
        "run_workflow",
        "cancel_run",
        "finish_ai_block",
        "scaffold_block",
        "reload_blocks",
        "run_block_tests",
        "update_block_config",
    }
)

__all__ = ["compose_system_prompt"]


def compose_system_prompt(project_dir: Path) -> str:
    """Return the system prompt string for ``project_dir``.

    Per ADR-040 §3.3, the ``project_dir`` argument is load-bearing: a
    rendered project-context section is spliced into SKILL.md between
    the ``<!-- project_context:begin -->`` markers.

    Parameters
    ----------
    project_dir
        Active project root. Used to render the project_context section
        (project name, workflow count, plugins, recent workflows, git
        branch/sha when applicable). Closes #825.

    Returns
    -------
    str
        The full system prompt — SKILL.md content with both the
        tool_catalog and the project_context blocks re-rendered.

    Raises
    ------
    FileNotFoundError
        When SKILL.md cannot be located (broken install / worktree).
    """
    skill_md = _load_skill_md()
    catalog = _render_tool_catalog()
    project_context = _render_project_context(project_dir)
    with_catalog = _splice(skill_md, _TOOL_CATALOG_BEGIN, _TOOL_CATALOG_END, catalog)
    return _splice(
        with_catalog,
        _PROJECT_CONTEXT_BEGIN,
        _PROJECT_CONTEXT_END,
        project_context,
    )


def _load_skill_md() -> str:
    """Load the base SKILL.md via ``importlib.resources`` (ADR-040 §3.4).

    The legacy walk-up resolver broke for wheel installs (#824) because
    ``skills/`` lived at repo-root, not inside ``src/scieasy/``. ADR-040
    §3.4 relocates the skill tree to ``src/scieasy/_skills/scieasy/``
    and switches consumers to ``importlib.resources``.

    Returns
    -------
    str
        Full text of the base SKILL.md.

    Raises
    ------
    FileNotFoundError
        If SKILL.md is missing (broken install).
    """
    try:
        resource = files("scieasy") / "_skills" / "scieasy" / "SKILL.md"
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise FileNotFoundError(
            "scieasy/_skills/scieasy/SKILL.md was not found via importlib.resources. "
            "Reinstall SciEasy (a wheel-install regression like #824)."
        ) from exc


def _render_tool_catalog() -> str:
    """Build the ``<!-- tool_catalog -->`` block contents from FastMCP.

    Enumerates :data:`scieasy.ai.agent.mcp.server.mcp.list_tools()` and
    groups by the owning module (per the four ``tools_*`` files).
    """
    from scieasy.ai.agent.mcp.server import mcp

    # FastMCP exposes list_tools as an async coroutine — run it in a
    # synchronous bridge here since compose_system_prompt is called
    # from synchronous Python (AIBlock bootstrap, terminal spawn).
    tools = _await(mcp.list_tools())

    grouped: dict[str, list[tuple[str, str, str]]] = {key: [] for key in _CATEGORY_LABELS}
    uncategorised: list[tuple[str, str, str]] = []
    for tool in tools:
        name = getattr(tool, "name", "") or ""
        description = getattr(tool, "description", "") or ""
        # First-line of the description keeps the catalogue tight.
        first_line = description.strip().split("\n", 1)[0]
        mutation = "write" if name in _WRITE_CLASS_TOOLS else "read"
        # Determine owning module from the underlying function.
        fn = getattr(tool, "fn", None)
        module_name = getattr(fn, "__module__", "") or ""
        category_key = next(
            (key for key in _CATEGORY_LABELS if module_name.endswith(key)),
            None,
        )
        entry = (name, mutation, first_line)
        if category_key is None:
            uncategorised.append(entry)
        else:
            grouped[category_key].append(entry)

    lines: list[str] = []
    for category_key, label in _CATEGORY_LABELS.items():
        entries = sorted(grouped[category_key], key=lambda e: e[0])
        if not entries:
            continue
        lines.append(label)
        for name, mutation, desc in entries:
            lines.append(f"- `{name}` [{mutation}] — {desc}")
        lines.append("")
    for name, mutation, desc in sorted(uncategorised, key=lambda e: e[0]):
        lines.append(f"- `{name}` [{mutation}] — {desc}")
    return "\n".join(lines).rstrip() + "\n"


def _render_project_context(project_dir: Path) -> str:
    """Render the per-project dynamic context block (ADR-040 §3.3).

    Spliced between ``<!-- project_context:begin -->`` and
    ``<!-- project_context:end -->`` markers in the base SKILL.md.

    Returns an empty string when ``project_dir`` is falsy. Otherwise
    renders project_name, workflow_count, installed_plugins, optional
    git branch/sha, and top-3 recently-modified workflows.

    Perf budget: <100ms even at 1000 workflows.
    """
    if not project_dir:
        return ""

    project_root = Path(project_dir)
    project_name = _read_project_name(project_root)

    # Workflow count + recently-modified workflows (os.scandir for perf).
    workflow_count, recent_workflows = _scan_workflows(project_root / "workflows")

    # Installed plugins via live BlockRegistry, or empty if not available.
    installed_plugins = _list_installed_plugins()

    # Git info (best-effort; non-git projects → empty).
    git_branch, git_sha = _git_info(project_root)

    lines: list[str] = []
    lines.append(f"**Project:** {project_name}")
    lines.append(f"**Path:** `{project_root}`")
    if workflow_count == 1:
        lines.append("**Workflows:** 1 workflow on disk")
    else:
        lines.append(f"**Workflows:** {workflow_count} workflows on disk")
    if installed_plugins:
        plugins_str = ", ".join(installed_plugins[:10])
        if len(installed_plugins) > 10:
            plugins_str += f" (and {len(installed_plugins) - 10} more)"
        lines.append(f"**Installed plugins:** {plugins_str}")
    if git_branch is not None:
        sha_short = git_sha[:7] if git_sha else "unknown"
        lines.append(f"**Git:** branch=`{git_branch}` sha=`{sha_short}`")
    if recent_workflows:
        lines.append("")
        lines.append("**Recently-modified workflows:**")
        for name, age in recent_workflows:
            lines.append(f"- `{name}` ({age})")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


def _splice(text: str, begin_marker: str, end_marker: str, body: str) -> str:
    """Replace the body between ``begin_marker`` and ``end_marker`` in ``text``."""
    begin = text.find(begin_marker)
    end = text.find(end_marker)
    if begin == -1 or end == -1 or end < begin:
        logger.warning(
            "SKILL.md is missing the %s / %s markers; appending the rendered block at end.",
            begin_marker,
            end_marker,
        )
        return f"{text}\n\n{begin_marker}\n{body}\n{end_marker}\n"
    end_marker_end = end + len(end_marker)
    return text[: begin + len(begin_marker)] + "\n" + body + "\n" + text[end:end_marker_end] + text[end_marker_end:]


def _await(coro: Any) -> Any:
    """Run an async coroutine from synchronous code.

    Used so the synchronous ``compose_system_prompt`` API surface
    doesn't bleed asyncio into its callers (AIBlock bootstrap, terminal
    spawn). We expect to be called from a thread that does NOT have an
    event loop running.
    """
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # An event loop is already running (rare — only test harnesses).
        # Fall back to creating a new loop in a worker thread.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(asyncio.run, coro)
            return future.result(timeout=10.0)


def _read_project_name(project_root: Path) -> str:
    """Read project.name from project.yaml, falling back to dir name."""
    project_file = project_root / "project.yaml"
    if not project_file.is_file():
        return project_root.name or "<unnamed>"
    try:
        import yaml

        raw = yaml.safe_load(project_file.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            project_meta = raw.get("project", {})
            if isinstance(project_meta, dict):
                name = project_meta.get("name")
                if isinstance(name, str) and name.strip():
                    return name
    except Exception:
        logger.debug("compose_system_prompt: could not parse project.yaml", exc_info=True)
    return project_root.name or "<unnamed>"


def _scan_workflows(workflows_dir: Path) -> tuple[int, list[tuple[str, str]]]:
    """Return (count, top-3-by-mtime) for ``workflows/*.yaml``.

    Uses ``os.scandir`` for the perf budget (<100ms at 1000 workflows).
    """
    if not workflows_dir.is_dir():
        return 0, []
    count = 0
    entries: list[tuple[float, str]] = []
    try:
        with os.scandir(workflows_dir) as it:
            for de in it:
                if not de.is_file():
                    continue
                if not de.name.endswith(".yaml"):
                    continue
                count += 1
                try:
                    mtime = de.stat().st_mtime
                except OSError:
                    continue
                entries.append((mtime, de.name))
    except OSError:
        return 0, []
    entries.sort(reverse=True)
    now = time.time()
    top: list[tuple[str, str]] = []
    for mtime, name in entries[:3]:
        top.append((name, _format_age(now - mtime)))
    return count, top


def _format_age(seconds_ago: float) -> str:
    """Format an age in seconds as 'Nh ago' / 'Nd ago' / 'Nw ago'."""
    if seconds_ago < 60:
        return "just now"
    minutes = seconds_ago / 60
    if minutes < 60:
        return f"{int(minutes)}m ago"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}h ago"
    days = hours / 24
    if days < 7:
        return f"{int(days)}d ago"
    weeks = days / 7
    if weeks < 52:
        return f"{int(weeks)}w ago"
    years = days / 365
    return f"{int(years)}y ago"


def _list_installed_plugins() -> list[str]:
    """Return registered plugin names from the live BlockRegistry."""
    try:
        from scieasy.ai.agent.mcp._context import get_optional_context

        ctx = get_optional_context()
        if ctx is None:
            return []
        registry = getattr(ctx, "block_registry", None)
        if registry is None:
            return []
        all_specs = registry.all_specs()
        return sorted(all_specs.keys())
    except Exception:
        logger.debug("compose_system_prompt: BlockRegistry enumeration failed", exc_info=True)
        return []


def _git_info(project_root: Path) -> tuple[str | None, str | None]:
    """Return (branch, sha) via best-effort ``git -C <root> rev-parse``."""
    git_dir = project_root / ".git"
    if not git_dir.exists():
        return None, None
    try:
        branch_proc = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        sha_proc = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else None
    sha = sha_proc.stdout.strip() if sha_proc.returncode == 0 else None
    return branch, sha
