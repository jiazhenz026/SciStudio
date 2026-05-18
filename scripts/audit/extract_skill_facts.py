"""Extract skill facts (ADR-042 §7.5.3).

Produces a :class:`scieasy.qa.schemas.facts.SkillFacts` instance with:

- ``required_skills``: ordered list of names from ``docs/skills/required.yaml``
  (the canonical list per ADR-042 §17.3).
- ``installed_per_runtime``: mapping of runtime ID → list of installed skill
  names, derived from ``.claude/skills/<name>/SKILL.md`` etc.

# TODO(#1155): cross-runtime probe currently scans the
#   ``.claude/skills/`` tree only. Codex (``.agents/skills/``,
#   ``.codex/skills/``), Cursor (``.cursor/rules/``), Aider, and Gemini
#   are deferred to a TC-1H.7 follow-up batch. Out of scope per ADR-042
#   §17.2 (canonical install-paths table). Followup: open as part of
#   Phase 1H sub-PR 2 (AGENTS.md hierarchy migration).

Reads
-----
``docs/skills/required.yaml`` — required skill list.
``.claude/skills/<name>/SKILL.md`` — per-runtime installed skills.

References
----------
ADR-042 §7.5.3 — generation table (skill namespace row).
ADR-042 §17.1 — required skill list.
ADR-042 §17.2 — installation paths per runtime (canonical).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from scieasy.qa.schemas.facts import SkillFacts

_RUNTIME_PROBE_PATHS: dict[str, str] = {
    "claude": ".claude/skills",
    # TODO(#1155): expand to .agents/skills/ + .codex/skills/ + .cursor/rules/
    #   + .aider.skills/ + .gemini/skills/ per ADR-042 §17.2. Out of scope
    #   for sub-PR 3. Followup: open as part of Phase 1H sub-PR 2.
}


def _find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise FileNotFoundError("could not locate repo root from extract_skill_facts.py")


def _read_required_yaml(path: Path) -> list[str]:
    if not path.is_file():
        return []
    parsed: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    skills_raw = parsed.get("skills") or []
    names: list[str] = []
    if isinstance(skills_raw, list):
        for entry in skills_raw:
            if isinstance(entry, dict):
                name = entry.get("name")
                if isinstance(name, str):
                    names.append(name)
            elif isinstance(entry, str):
                names.append(entry)
    return names


def _probe_runtime(skills_dir: Path) -> list[str]:
    if not skills_dir.is_dir():
        return []
    installed = []
    for entry in sorted(skills_dir.iterdir()):
        if entry.is_dir() and (entry / "SKILL.md").is_file():
            installed.append(entry.name)
    return installed


def extract(
    required_path: Path | None = None,
    repo_root: Path | None = None,
) -> SkillFacts:
    """Build a :class:`SkillFacts` instance from the manifest + runtime probes.

    Args:
        required_path: Optional explicit path to ``docs/skills/required.yaml``.
        repo_root: Optional repo-root override used for the per-runtime probe.
    """
    root = repo_root or _find_repo_root()
    required_path = required_path or (root / "docs" / "skills" / "required.yaml")
    required = _read_required_yaml(required_path)

    installed: dict[str, list[str]] = {}
    for runtime, rel in _RUNTIME_PROBE_PATHS.items():
        installed[runtime] = _probe_runtime(root / rel)

    return SkillFacts(
        required_skills=required,
        installed_per_runtime=installed,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Prints a JSON dump of the skill facts to stdout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--required", type=Path, default=None)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    facts = extract(args.required, args.repo_root)
    print(json.dumps(facts.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
