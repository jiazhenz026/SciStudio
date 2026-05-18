"""Cross-runtime installer for QA-required skills (ADR-042 §17.3).

This module is the sibling of :mod:`scieasy.agent_provisioning.skills`
(which handles the ADR-040 multi-skill split for the user-facing
``scieasy*`` skills). ``qa_skills`` handles the ADR-042 §17 *required*
skill manifest — the 11 P0/P1/P2 skills every agent runtime must have
installed before it may commit to the repository.

Source of truth
---------------

- ``docs/skills/required.yaml`` — manifest of names + priority + pointer
  targets.
- ``src/scieasy/_skills/qa/<name>/SKILL.md`` — the canonical pointer body
  for each required skill. Authored once; installer copies verbatim to
  every supported runtime path.

Runtime target paths (per ADR-042 §17.2 canonical table)
--------------------------------------------------------

================  ===================================  ==================
Runtime           Project-local path                   v1 status
================  ===================================  ==================
Claude Code       ``.claude/skills/<name>/SKILL.md``   IMPLEMENTED
Codex             ``.agents/skills/<name>/SKILL.md``   TODO(#1155)
Codex (alt)       ``.codex/skills/<name>/SKILL.md``    TODO(#1155)
Cursor            ``.cursor/rules/<name>.md``          TODO(#1155)
Aider             ``.aider.skills/<name>/SKILL.md``    TODO(#1155)
Gemini            ``.gemini/skills/<name>/SKILL.md``   TODO(#1155)
================  ===================================  ==================

# TODO(#1155): expand to all non-Claude runtimes per ADR-042 §17.2.
#   Sub-PR 3 ships Claude only because (a) the user runs Claude, (b) the
#   other runtime paths require AGENTS.md hierarchy migration (sub-PR 2)
#   to be useful (an installed skill with no AGENTS.md pointer is dead
#   weight). Out of scope per Phase 1H sub-PR 3 dispatch prompt.
#   Followup: open as part of Phase 1H sub-PR 2.

References
----------
ADR-042 §17.1 — required-skill list.
ADR-042 §17.2 — installation-paths table.
ADR-042 §17.3 — cross-runtime installer (this module).
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any

import yaml

# Per-runtime project-local install paths. v1 ships Claude only; others
# are present-but-disabled so the manifest reader sees the structure
# (the test suite asserts these stay in lockstep with the canonical table).
_RUNTIME_PATHS: dict[str, str] = {
    "claude": ".claude/skills",
    # TODO(#1155): enable below paths in Phase 1H sub-PR 2.
    # "codex": ".agents/skills",
    # "codex-alt": ".codex/skills",
    # "cursor": ".cursor/rules",
    # "aider": ".aider.skills",
    # "gemini": ".gemini/skills",
}


def _read_required_manifest(manifest_path: Path) -> list[str]:
    """Parse ``docs/skills/required.yaml`` and return the ordered skill name list.

    Schema is shared with :mod:`scripts.audit.extract_skill_facts` — see
    that module for the parser. Kept duplicated to avoid a runtime
    dependency from ``agent_provisioning`` on ``scripts/`` (the latter
    is not in ``sys.path`` at agent-init time).
    """
    if not manifest_path.is_file():
        return []
    parsed: dict[str, Any] = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    skills_raw = parsed.get("skills") or []
    names: list[str] = []
    if not isinstance(skills_raw, list):
        return names
    for entry in skills_raw:
        if isinstance(entry, dict):
            name = entry.get("name")
            if isinstance(name, str):
                names.append(name)
        elif isinstance(entry, str):
            names.append(entry)
    return names


def _read_skill_body(name: str) -> str:
    """Resolve and read the SKILL.md body for the named QA skill.

    Resolution order (matches the pattern in :mod:`scieasy.agent_provisioning.skills`
    for symmetry):

    1. ``importlib.resources`` lookup in ``scieasy._skills.qa.<name>``.
    2. Walk-up filesystem lookup for ``<repo>/src/scieasy/_skills/qa/<name>/SKILL.md``.

    Returns a minimal placeholder body if both lookups miss (no exception
    so the installer can run idempotently against partial source trees).
    """
    package_path = f"scieasy._skills.qa.{name}"
    try:
        return importlib.resources.files(package_path).joinpath("SKILL.md").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, NotADirectoryError):
        pass

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "src" / "scieasy" / "_skills" / "qa" / name / "SKILL.md"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
        candidate = parent / "_skills" / "qa" / name / "SKILL.md"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
        if (parent / "pyproject.toml").is_file():
            break

    return f"---\nname: {name}\ndescription: (source body missing — see ADR-042 §17.3)\n---\n\n# {name}\n\nSource body not found. See `docs/skills/required.yaml`.\n"


def install_qa_skills(
    project_dir: Path,
    *,
    manifest_path: Path | None = None,
    force: bool = False,
    runtimes: list[str] | None = None,
) -> list[str]:
    """Install every required QA skill into the given project's runtime trees.

    Args:
        project_dir: The project root (i.e. the directory containing
            ``.claude/`` and ``pyproject.toml``).
        manifest_path: Optional override for ``docs/skills/required.yaml``.
            Defaults to the manifest under ``project_dir``.
        force: If True, overwrite existing SKILL.md files. Default False
            (idempotent top-up; never silently clobbers a customised skill).
        runtimes: Optional subset of runtimes to install into. Defaults
            to all enabled runtimes (currently ``["claude"]``).

    Returns:
        List of project-relative paths actually written (may be empty if
        every skill already exists and ``force`` is False).
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_path or (project_dir / "docs" / "skills" / "required.yaml")
    skill_names = _read_required_manifest(manifest_path)
    target_runtimes = runtimes if runtimes is not None else list(_RUNTIME_PATHS.keys())

    written: list[str] = []
    bodies = {name: _read_skill_body(name) for name in skill_names}
    for runtime in target_runtimes:
        rel_root = _RUNTIME_PATHS.get(runtime)
        if rel_root is None:
            continue  # silently skip disabled runtimes for forward-compat
        for name in skill_names:
            rel_path = f"{rel_root}/{name}/SKILL.md"
            dest = project_dir / rel_path
            if dest.exists() and not force:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(bodies[name], encoding="utf-8")
            written.append(rel_path)
    return written


def list_required_skills(manifest_path: Path) -> list[str]:
    """Return the ordered list of required skill names (manifest read helper)."""
    return _read_required_manifest(manifest_path)


__all__ = [
    "install_qa_skills",
    "list_required_skills",
]
