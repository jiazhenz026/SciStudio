"""Workflow doc ↔ skill bidirectional sync (ADR-044 §11.5 + §12.3).

This module is the audit-tool surface of ADR-044's bidirectional
closure between procedural skills and contributor workflow docs:

* Forward: every ``docs/contributing/workflows/*.md`` has at least one
  ``.claude/skills/*/SKILL.md`` with ``kind: procedural`` pointing at it.
* Reverse: every procedural skill has a workflow target on disk and is
  listed in that workflow's ``related_skills`` frontmatter.

The deliberate overlap with :mod:`scieasy.qa.audit.skill_pointer_sync`
is intentional (Phase 1 investigation SUMMARY non-blocking note on TC
1B.10): ``skill_pointer_sync`` checks the *skill-side* discipline
(pointer shape, body length, duplication), while this module checks
the bidirectional closure invariants. Same closure, different lens.

References
----------
ADR-044 §11.4 — algorithm (skill-side, partially reused here).
ADR-044 §11.5 — entry-point signature contract.
ADR-044 §12.3 — bidirectional closure extension scope.

Deferred work
-------------
Until ``docs/contributing/workflows/`` lands in sub-phase 1D, this
module returns a single INFO finding signalling the dormant state.

# TODO(#1154-ext): activate full bidirectional check once 1D ships
#   Out of scope per Phase 1 investigation SUMMARY (1D-dependent).
#   Followup: open as 1B.4-ext after 1D docs translator lands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from scieasy.qa.schemas.report import Finding, Severity

__all__ = ["run"]


def run(repo_root: Path | None = None) -> list[Finding]:
    """Verify skill ↔ workflow-doc pointer integrity.

    Algorithm:
      1. If ``docs/contributing/workflows/`` does not exist, return a
         single INFO finding (dormant — sub-phase 1D not yet shipped).
      2. Build the procedural-skill index: ``skill_name -> pointer_target``.
      3. For each workflow doc:
         - Forward closure: ≥1 procedural skill targets it → otherwise
           ``workflow-sync.workflow-unreferenced`` (ERROR).
         - Frontmatter ``related_skills`` lists each referencing skill →
           otherwise ``workflow-sync.related-skills-mismatch`` (WARNING).
      4. For each procedural skill whose target does not exist on disk →
         ``workflow-sync.target-missing`` (ERROR).
    """
    repo_root = repo_root or Path.cwd()
    workflows_dir = repo_root / "docs" / "contributing" / "workflows"
    if not workflows_dir.is_dir():
        return [
            Finding(
                rule_id="workflow-sync.dormant",
                severity=Severity.INFO,
                file="docs/contributing/workflows/",
                message=(
                    "workflow-sync skipped — `docs/contributing/workflows/` "
                    "is absent. Becomes active once sub-phase 1D ships the "
                    "docs translator."
                ),
            )
        ]

    findings: list[Finding] = []

    # 2. Procedural skill index.
    skills_index = _build_skill_index(repo_root)

    # 4. (Done first because we need the per-skill target validity for 3.)
    for skill_name, target in skills_index.items():
        if target is None:
            findings.append(
                Finding(
                    rule_id="workflow-sync.no-target",
                    severity=Severity.WARNING,
                    file=f".claude/skills/{skill_name}/SKILL.md",
                    message=(
                        "procedural skill names no workflow target. Add a backticked pointer to the canonical doc."
                    ),
                )
            )
            continue
        if not (repo_root / target).is_file():
            findings.append(
                Finding(
                    rule_id="workflow-sync.target-missing",
                    severity=Severity.ERROR,
                    file=f".claude/skills/{skill_name}/SKILL.md",
                    message=(f"procedural skill pointer {target!r} does not resolve to a workflow doc on disk."),
                )
            )

    # 3. Workflow-side closure.
    target_to_skill_names: dict[str, list[str]] = {}
    for skill_name, target in skills_index.items():
        if target is not None:
            target_to_skill_names.setdefault(target, []).append(skill_name)

    for workflow_path in sorted(workflows_dir.glob("*.md")):
        rel = workflow_path.relative_to(repo_root).as_posix()
        referencing = sorted(target_to_skill_names.get(rel, []))

        if not referencing:
            findings.append(
                Finding(
                    rule_id="workflow-sync.workflow-unreferenced",
                    severity=Severity.ERROR,
                    file=rel,
                    message=(
                        "workflow doc has no procedural skill pointing at it. "
                        "Forward closure broken — add a SKILL.md under "
                        ".claude/skills/."
                    ),
                )
            )
            continue

        frontmatter = _read_frontmatter(workflow_path)
        declared = frontmatter.get("related_skills") if frontmatter else None
        declared_set = set(declared) if isinstance(declared, list) else set()
        missing = set(referencing) - declared_set
        for skill_name in sorted(missing):
            findings.append(
                Finding(
                    rule_id="workflow-sync.related-skills-mismatch",
                    severity=Severity.WARNING,
                    file=rel,
                    message=(
                        f"skill {skill_name!r} points at this workflow but "
                        "is not listed in frontmatter `related_skills`."
                    ),
                )
            )

    return findings


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _build_skill_index(repo_root: Path) -> dict[str, str | None]:
    """Map ``skill_name -> workflow-doc pointer`` for ``kind: procedural`` skills."""
    skills_dir = repo_root / ".claude" / "skills"
    index: dict[str, str | None] = {}
    if not skills_dir.is_dir():
        return index

    # Lazy import to avoid a circular at module-load time.
    from scieasy.qa.audit.skill_pointer_sync import detect_skill_kind

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        frontmatter = _read_frontmatter(skill_md)
        if frontmatter is None:
            continue
        kind = detect_skill_kind(frontmatter)
        if kind != "procedural":
            continue
        target = _extract_pointer_target(skill_md.read_text(encoding="utf-8"))
        index[skill_dir.name] = target
    return index


def _extract_pointer_target(text: str) -> str | None:
    """Pull the first ``docs/contributing/workflows/<slug>.md`` mention."""
    import re

    match = re.search(
        r"`(docs/contributing/workflows/[a-z0-9-]+\.md)`",
        text,
    )
    return match.group(1) if match else None


def _read_frontmatter(path: Path) -> dict[str, Any] | None:
    """Return parsed YAML frontmatter or ``None``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data
