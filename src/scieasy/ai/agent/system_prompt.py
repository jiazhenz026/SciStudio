"""Compose the system prompt for the embedded agent.

ADR-040 §3.3 evolves this module in three ways (S40a skeleton phase):

1. ``_load_skill_md`` switches from a walk-up-the-tree resolver to
   ``importlib.resources``, fixing the #824 wheel-install bug. (See
   ADR-040 §3.4 — the skill source relocates from repo-root
   ``skills/scieasy/SKILL.md`` to ``src/scieasy/_skills/scieasy/SKILL.md``
   in the Skills track, owned by S40b.)
2. ``_render_tool_catalog`` switches from iterating the deleted
   :data:`_registry.TOOL_REGISTRY` to enumerating FastMCP's
   ``mcp.list_tools()`` surface.
3. New :func:`_render_project_context` renders a per-project dynamic
   section spliced into the base SKILL.md between
   ``<!-- project_context:begin/end -->`` markers. Source fields
   include: project_name, workflow_count, installed_plugins, git
   branch/sha (best-effort), and recently-modified workflows. Closes
   #825.

All three bodies raise :class:`NotImplementedError` in this skeleton —
I40a Phase 2a fills them in. The composer's high-level structure
(splice catalog + splice project_context) is laid down here so the
file's shape is the contract Phase 2a fills.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Markers in SKILL.md that delimit rendered insertion blocks.
_TOOL_CATALOG_BEGIN = "<!-- tool_catalog:begin -->"
_TOOL_CATALOG_END = "<!-- tool_catalog:end -->"
_PROJECT_CONTEXT_BEGIN = "<!-- project_context:begin -->"
_PROJECT_CONTEXT_END = "<!-- project_context:end -->"

__all__ = ["compose_system_prompt"]


def compose_system_prompt(project_dir: Path) -> str:
    """Return the system prompt string for ``project_dir``.

    Per ADR-040 §3.3, the ``project_dir`` argument is now load-bearing:
    a rendered project-context section is spliced into the SKILL.md
    between ``<!-- project_context:begin -->`` and
    ``<!-- project_context:end -->`` markers.

    Parameters
    ----------
    project_dir
        Active project root. Used to render the project_context section
        (project name, workflow count, installed plugins, recent
        workflows, git branch/sha when applicable). Closes #825.

    Returns
    -------
    str
        The full system prompt — SKILL.md content with both the
        tool_catalog and the project_context blocks re-rendered.

    Raises
    ------
    FileNotFoundError
        When SKILL.md cannot be located (broken install / worktree).

    # TODO(#1012): wire real bodies once S40b lands the new base
    #   SKILL.md at ``src/scieasy/_skills/scieasy/SKILL.md`` with both
    #   the tool_catalog and project_context marker blocks.
    #   Out of scope per ADR-040 §3.3 / phase: 2a I40a. Followup: #1012.
    """
    skill_md = _load_skill_md()
    catalog = _render_tool_catalog()
    project_context = _render_project_context(project_dir)
    with_catalog = _splice(skill_md, _TOOL_CATALOG_BEGIN, _TOOL_CATALOG_END, catalog)
    return _splice(with_catalog, _PROJECT_CONTEXT_BEGIN, _PROJECT_CONTEXT_END, project_context)


def _load_skill_md() -> str:
    """Load the base SKILL.md via ``importlib.resources`` (ADR-040 §3.4).

    The legacy walk-up resolver broke for wheel installs (#824) because
    ``skills/`` lived at repo-root, not inside ``src/scieasy/``. ADR-040
    §3.4 relocates the skill tree to ``src/scieasy/_skills/scieasy/``
    and switches both consumers (this module and
    :func:`scieasy.cli.install._find_skill_source`) to use
    ``importlib.resources.files``.

    Reference impl plan for I40a:

    ```python
    from importlib.resources import files
    def _load_skill_md() -> str:
        return (files("scieasy") / "_skills" / "scieasy" / "SKILL.md").read_text("utf-8")
    ```

    Returns
    -------
    str
        Full text of the base SKILL.md.

    # TODO(#1012): switch to importlib.resources once S40b lands the
    #   relocated SKILL.md at src/scieasy/_skills/scieasy/SKILL.md and
    #   adds the [tool.setuptools.package-data] scieasy =
    #   ["_skills/scieasy/**/*.md"] entry in pyproject.toml (S40b owns
    #   that pyproject section — S40a only touches [project] deps).
    #   Out of scope per ADR-040 §3.4 / phase: 2a I40a. Followup: #1012.
    #
    # Skeleton-phase rule (agent-manager templates/skeleton-agent.md §5):
    # "Skeleton must build — pytest --collect-only runs without errors."
    # Several AIBlock runtime tests exercise compose_system_prompt →
    # _load_skill_md transitively (see tests/blocks/ai/*). A bare
    # NotImplementedError here leaks into those test runs (CI failure
    # tracebacks at ai_block.py:467). Skeleton therefore preserves the
    # legacy walk-up implementation verbatim until I40a switches it to
    # importlib.resources. The body change is the implementation; the
    # docstring above documents the planned switch.
    """
    here = Path(__file__).resolve()
    # Walk up looking for the repo root (contains ``skills/scieasy``).
    for parent in here.parents:
        candidate = parent / "skills" / "scieasy" / "SKILL.md"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
        # Stop at repo root if pyproject.toml is found there.
        if (parent / "pyproject.toml").is_file():
            # Final probe inside the repo root before giving up.
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
            break
    raise FileNotFoundError(
        "skills/scieasy/SKILL.md was not found relative to "
        f"{here}.  Reinstall SciEasy or run from a checkout that "
        "includes the skills/ tree."
    )


def _render_tool_catalog() -> str:
    """Build the ``<!-- tool_catalog -->`` block contents from FastMCP.

    Replaces the ADR-033-era TOOL_REGISTRY iteration. The deleted
    ``_registry.TOOL_REGISTRY`` is now ``mcp.list_tools()`` enumeration.

    Reference impl plan for I40a (per ADR-040 §3.1 + §3.2):

    ```python
    from scieasy.ai.agent.mcp.server import mcp

    category_titles = {
        "workflow": "### (a) Workflow design & execution",
        "authoring": "### (b) Block authoring",
        "inspection": "### (c) Run & data inspection",
        "qa": "### (d) Project Q&A",
    }
    grouped: dict[str, list[str]] = {key: [] for key in category_titles}
    for tool in mcp.list_tools():
        # tool object exposes: .name, .description, .annotations (incl.
        # mutation), .inputSchema (FastMCP-generated from type hints).
        # Category source TBD — likely a custom annotation set when the
        # tool is decorated. For S40a, we can derive from the tool's
        # owning module via a small mapping.
        ...
    ```

    Returns
    -------
    str
        Multi-line markdown block listing every registered tool grouped
        by category. Each line is
        ``- `<name>` [<mutation>] — <description>``.

    # TODO(#1012): wire FastMCP list_tools() iteration once the real
    #   FastMCP instance lands in server.py. The deleted
    #   _registry.TOOL_REGISTRY had a clean (name, category, mutation,
    #   description) shape; we need to recover equivalent metadata from
    #   FastMCP either by tool annotations or a parallel category map.
    #   Decision deferred to I40a.
    #   Out of scope per ADR-040 §3.1 / phase: 2a I40a. Followup: #1012.
    #
    # Skeleton-phase hygiene (agent-manager templates/skeleton-agent.md §5):
    # runtime callers (compose_system_prompt → AIBlock bootstrap) must not
    # crash. Return placeholder text; I40a rewrites with real FastMCP
    # enumeration. Placeholder is intentionally short so spawned agents
    # see the missing-catalog state explicitly.
    """
    return (
        "<!-- tool_catalog: skeleton placeholder — I40a (#1012) "
        "wires FastMCP list_tools() enumeration. -->\n"
    )


def _render_project_context(project_dir: Path) -> str:
    """Render the per-project dynamic context block (ADR-040 §3.3, closes #825).

    Spliced between ``<!-- project_context:begin -->`` and
    ``<!-- project_context:end -->`` markers in the base SKILL.md.
    Renders project_name, workflow_count, installed_plugins, optional
    git branch/sha, and top-3 recently-modified workflows.

    Field sources per ADR-040 §3.3:

    | Field | Source |
    |---|---|
    | ``project_name`` | ``project.yaml::project.name`` or ``project_dir.name`` fallback |
    | ``workflow_count`` | ``len(list((project_dir / 'workflows').glob('*.yaml')))`` |
    | ``installed_plugins`` | live BlockRegistry enumeration |
    | ``branch``, ``sha`` | best-effort ``git -C <project_dir> rev-parse``; omit if not a git repo |
    | ``recent_workflows`` | top 3 by ``Path.stat().st_mtime``, formatted as "N{h,d,w} ago" |

    Performance budget: <100ms even at 1000 workflows (use os.scandir).
    Composer is called once per PTY spawn; no caching needed.

    Parameters
    ----------
    project_dir
        Active project root.

    Returns
    -------
    str
        Markdown block with the rendered project context. When
        ``project_dir`` is empty / missing / not a SciEasy project,
        returns a minimal fallback noting the project state.

    # TODO(#1012): implement per ADR-040 §3.3 field-source table.
    #   Notes for I40a:
    #   - Use os.scandir for performance; <100ms perf assertion test
    #     should be added to test_system_prompt.py.
    #   - Best-effort git rev-parse: catch subprocess errors silently.
    #   - BlockRegistry enumeration: import live registry via the same
    #     pathway tools use (scieasy.ai.agent.mcp._context.get_context)
    #     OR fall back to project-local blocks/ scan when context is None.
    #   - Empty-workflows handling: omit the "Recently-modified" section
    #     entirely rather than rendering an empty list.
    #   - Non-git-repo handling: omit the "Git:" line.
    #   Out of scope per ADR-040 §3.3 / phase: 2a I40a. Followup: #1012.
    #
    # Skeleton-phase hygiene (agent-manager templates/skeleton-agent.md §5):
    # runtime callers must not crash. Return placeholder text; I40a rewrites
    # with the real per-project metadata renderer per ADR-040 §3.3 + #825.
    """
    return (
        "<!-- project_context: skeleton placeholder — I40a (#1012, closes #825) "
        "implements per-project metadata injection. -->\n"
    )


def _splice(text: str, begin_marker: str, end_marker: str, body: str) -> str:
    """Replace the body between ``begin_marker`` and ``end_marker`` in ``text``.

    Falls back to appending the marker block at the end of ``text``
    when the marker pair is missing — surfacing a warning so a stale
    SKILL.md is easy to diagnose without breaking the agent.

    Used for both the tool_catalog and the project_context splices.
    The function itself is intentionally NOT a NotImplementedError
    stub — it's pure string manipulation with no skeleton/impl split,
    and the test scaffolding in test_system_prompt.py exercises it
    through ``compose_system_prompt``. I40a will use this verbatim
    once the body-rendering helpers stop raising.
    """
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
