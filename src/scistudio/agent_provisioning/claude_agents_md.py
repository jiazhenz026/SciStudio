"""Write AGENTS.md + CLAUDE.md sub-step (ADR-040 §3.5, refined by #2137).

``<project>/AGENTS.md`` is the single canonical agent-instruction entry
point: every supported assistant CLI either reads AGENTS.md natively or
discovers the provisioned skills trees beside it. ``<project>/CLAUDE.md``
is reduced to a one-line router pointing at AGENTS.md, so the guide text
is maintained in exactly one place regardless of how many provider CLIs
are supported.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from scistudio.agent_provisioning._refresh import write_managed_file

_TARGETS = ("AGENTS.md", "CLAUDE.md")
_TEMPLATE_RESOURCE = "claude_agents_md.md"

#: CLAUDE.md carries no content of its own — it routes to AGENTS.md (#2137).
_CLAUDE_MD_ROUTER = """\
# SciStudio project — agent guide

This project keeps its agent instructions in `AGENTS.md`. Read and follow
`AGENTS.md` in this directory — it holds the identity, non-negotiable rules,
skills index, and project layout. Do not duplicate its content here.
"""


def _load_template() -> str:
    """Read the bundled AGENTS.md template via importlib.resources.

    Wheel-safe per #824; falls back to source-tree lookup if the resource
    is missing (e.g. during certain editable-install + package-data race
    conditions).
    """
    try:
        return (
            importlib.resources.files("scistudio.agent_provisioning.templates")
            .joinpath(_TEMPLATE_RESOURCE)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError):
        here = Path(__file__).resolve()
        candidate = here.parent / "templates" / _TEMPLATE_RESOURCE
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
        raise


def write_claude_agents_md(
    project_dir: Path,
    *,
    force: bool = False,
    manifest: dict[str, str] | None = None,
) -> list[str]:
    """Write ``<project>/AGENTS.md`` and the ``<project>/CLAUDE.md`` router.

    AGENTS.md receives the full guide template; CLAUDE.md receives only a
    pointer to AGENTS.md (#2137). Existing files are refreshed when they are
    unchanged since SciStudio last wrote them and preserved when the user
    edited them (#1860, content-aware refresh).

    Inputs:
      project_dir : Path to project root.
      force       : True to overwrite existing files; False to preserve.
      manifest    : managed-content hash manifest (see ``_refresh``);
                    a fresh dict is used when omitted.

    Returns:
      List of project-relative paths actually written.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    bodies = {"AGENTS.md": _load_template(), "CLAUDE.md": _CLAUDE_MD_ROUTER}
    if manifest is None:
        manifest = {}
    written: list[str] = []
    for name in _TARGETS:
        if write_managed_file(project_dir, name, bodies[name], manifest, force=force):
            written.append(name)
    return written
