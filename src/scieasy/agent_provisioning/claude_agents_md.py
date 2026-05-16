"""Write CLAUDE.md + AGENTS.md sub-step (ADR-040 §3.5).

Both files are written verbatim from a single template at
``src/scieasy/agent_provisioning/templates/claude_agents_md.md``. Claude
Code reads ``<project>/CLAUDE.md``; Codex reads ``<project>/AGENTS.md``;
content is identical on both sides to ensure symmetric agent behavior.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

_TARGETS = ("CLAUDE.md", "AGENTS.md")
_TEMPLATE_RESOURCE = "claude_agents_md.md"


def _load_template() -> str:
    """Read the bundled CLAUDE.md/AGENTS.md template via importlib.resources.

    Wheel-safe per #824; falls back to source-tree lookup if the resource
    is missing (e.g. during certain editable-install + package-data race
    conditions).
    """
    try:
        return (
            importlib.resources.files("scieasy.agent_provisioning.templates")
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
) -> list[str]:
    """Write ``<project>/CLAUDE.md`` and ``<project>/AGENTS.md``.

    Inputs:
      project_dir : Path to project root.
      force       : True to overwrite existing files; False to preserve.

    Returns:
      List of project-relative paths actually written.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    body = _load_template()
    written: list[str] = []
    for name in _TARGETS:
        dest = project_dir / name
        if dest.exists() and not force:
            continue
        dest.write_text(body, encoding="utf-8")
        written.append(name)
    return written
