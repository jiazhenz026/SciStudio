"""Compose the system prompt for the embedded agent.

ADR-034 Phase 1.2.  PR #808 rolled back the previous
``compose_system_prompt`` implementation (along with the rest of the
Phase 5 e2e harness).  This module restores the helper in its
PTY-architecture-appropriate shape:

* The prompt's narrative content lives in ``skills/scieasy/SKILL.md``
  (single source of truth — the same file is also copied into
  ``~/.claude/skills/scieasy/`` by ``scieasy install --skill`` so the
  ambient claude shell sees it too).
* The MCP tool catalogue is **not** stored statically inside SKILL.md.
  Instead, SKILL.md ships a placeholder block delimited by
  ``<!-- tool_catalog:begin -->`` / ``<!-- tool_catalog:end -->`` and
  this module re-renders that block from the live
  :data:`scieasy.ai.agent.mcp._registry.TOOL_REGISTRY` so the prompt
  and the dispatcher can never drift.

The function is **pure** — same inputs produce the same string,
byte-for-byte.  Hashing for SessionMetadata is no longer needed (the
PTY architecture does not persist that field), so we just return a
plain ``str``.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Markers in SKILL.md that delimit the rendered tool catalogue.
_TOOL_CATALOG_BEGIN = "<!-- tool_catalog:begin -->"
_TOOL_CATALOG_END = "<!-- tool_catalog:end -->"

__all__ = ["compose_system_prompt"]


def compose_system_prompt(project_dir: Path) -> str:
    """Return the system prompt string for ``project_dir``.

    The ``project_dir`` argument is kept in the signature for forward
    compatibility (future iterations may want to splice in project
    metadata) but is currently used only as a deterministic input —
    callers should *not* assume the returned string varies with it
    today.

    Parameters
    ----------
    project_dir
        Active project root.  Not currently woven into the prompt;
        reserved for future use.

    Returns
    -------
    str
        The full system prompt — SKILL.md content with the tool
        catalogue block re-rendered from :data:`TOOL_REGISTRY`.

    Raises
    ------
    FileNotFoundError
        When SKILL.md cannot be located.  This indicates a broken
        install / worktree and should surface to the route layer as a
        WebSocket error frame.
    """
    skill_md = _load_skill_md()
    catalog = _render_tool_catalog()
    return _splice_catalog(skill_md, catalog)


def _load_skill_md() -> str:
    """Locate and read ``skills/scieasy/SKILL.md``.

    Resolution order:

    1. Walk up from this file (``src/scieasy/ai/agent/system_prompt.py``)
       until we find a ``skills/scieasy/SKILL.md`` sibling.  This covers
       editable installs and the worktree-PYTHONPATH dev loop.
    2. Fall back to the wheel-packaged copy (planned for a later phase
       that bundles SKILL.md into the wheel).  When that lands the path
       here will be ``Path(__file__).parent.parent.parent / 'skills' /
       'scieasy' / 'SKILL.md'``.
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
    """Build the ``<!-- tool_catalog -->`` block contents.

    Walks :data:`TOOL_REGISTRY` in declaration order, grouping by
    category so the prompt remains readable.  Format mirrors what
    SKILL.md ships as a static fallback so behavior is unchanged for
    out-of-process readers.
    """
    # Local import keeps the ai.agent package import-light at module load.
    from scieasy.ai.agent.mcp._registry import TOOL_REGISTRY

    # Group by category in declaration order.
    category_titles = {
        "workflow": "### (a) Workflow design & execution",
        "authoring": "### (b) Block authoring",
        "inspection": "### (c) Run & data inspection",
        "qa": "### (d) Project Q&A",
    }
    grouped: dict[str, list[str]] = {key: [] for key in category_titles}
    for entry in TOOL_REGISTRY:
        line = f"- `{entry.name}` [{entry.mutation}] — {entry.description}"
        grouped.setdefault(entry.category, []).append(line)

    lines: list[str] = []
    for cat, title in category_titles.items():
        if not grouped.get(cat):
            continue
        if lines:
            lines.append("")  # blank between categories
        lines.append(title)
        lines.append("")
        lines.extend(grouped[cat])
    return "\n".join(lines)


def _splice_catalog(skill_md: str, catalog: str) -> str:
    """Replace the marker block in SKILL.md with the rendered catalog.

    Falls back to appending the catalogue at the end of the file when
    the marker pair is missing — surfacing a warning so a stale SKILL.md
    is easy to diagnose without breaking the agent.
    """
    begin = skill_md.find(_TOOL_CATALOG_BEGIN)
    end = skill_md.find(_TOOL_CATALOG_END)
    if begin == -1 or end == -1 or end < begin:
        logger.warning(
            "SKILL.md is missing the tool_catalog begin/end markers; appending the rendered catalogue at end of prompt."
        )
        return f"{skill_md}\n\n{_TOOL_CATALOG_BEGIN}\n{catalog}\n{_TOOL_CATALOG_END}\n"

    end_marker_end = end + len(_TOOL_CATALOG_END)
    return (
        skill_md[: begin + len(_TOOL_CATALOG_BEGIN)]
        + "\n"
        + catalog
        + "\n"
        + skill_md[end:end_marker_end]
        + skill_md[end_marker_end:]
    )
