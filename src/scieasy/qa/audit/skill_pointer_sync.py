"""Skill-as-pointer discipline lint (ADR-044 §11).

The anti-drift discipline from ADR-044 §11 says skills do not duplicate
workflow procedural text. Each ``SKILL.md`` is a short pointer
(~20 lines) naming the canonical doc and a small invocation tail; the
procedure body lives in the doc, not in the skill.

This module enforces that discipline:

* Skill kind detection from frontmatter ``kind`` field
  (``procedural`` / ``tool-wrapping`` / ``bootstrap-meta``).
* Pointer-target resolution per kind:

  - ``procedural`` → ``docs/contributing/workflows/<a-z0-9->+\\.md``
  - ``tool-wrapping`` → ``docs/contributing/reference/<a-z0-9->+\\.md`` OR
    a ``scieasy.qa.audit.*`` module path.
  - ``bootstrap-meta`` → ``docs/doc-guide/<a-z0-9->+\\.md``

* Body length cap: SKILL.md body (excluding frontmatter) ≤ 30 lines.
* Procedural-duplication heuristic: 3+ consecutive numbered list items
  in the body warns about copy-from-workflow drift.
* Reverse closure: every ``docs/contributing/workflows/*.md`` has at
  least one procedural skill pointing at it and lists that skill in
  its frontmatter ``related_skills``.

References
----------
ADR-044 §11.1 — principle.
ADR-044 §11.2 — skill template.
ADR-044 §11.3 — skill kinds + pointer targets.
ADR-044 §11.4 — algorithm (authoritative source).
ADR-044 §11.5 — entry-point signature contract.

Deferred work
-------------
Until ``docs/contributing/workflows/`` lands in sub-phase 1D, the
reverse-closure check is dormant: it returns a single INFO finding
(``skill-pointer-sync.workflows-dir-absent``) instead of erroring on
every skill with kind ``procedural`` that has no target.

# TODO(#1154-ext): activate reverse-closure once 1D ships docs/contributing/
#   Out of scope per Phase 1 investigation SUMMARY (workflow_sync overlap
#   is intentional; 1D dependency).
#   Followup: open as 1B.4-ext after 1D docs translator lands.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from scieasy.qa.schemas.report import Finding, Severity

__all__ = ["check", "detect_skill_kind"]

#: Maximum body lines for a SKILL.md (frontmatter excluded).
MAX_BODY_LINES = 30

#: Required form for a procedural skill's target path.
_PROCEDURAL_TARGET_RE = re.compile(r"^docs/contributing/workflows/[a-z0-9-]+\.md$")
_REFERENCE_TARGET_RE = re.compile(r"^docs/contributing/reference/[a-z0-9-]+\.md$")
_TOOL_WRAP_MODULE_RE = re.compile(r"^scieasy\.qa\.audit(?:\.[a-z_][a-z0-9_]*)+$")
_BOOTSTRAP_TARGET_RE = re.compile(r"^docs/doc-guide/[a-z0-9-]+\.md$")

#: Pointer-target detection: any backticked path/module reference.
#: The shape regex (per skill kind) then validates the captured target.
_POINTER_LINE_RE = re.compile(
    r"`(?P<target>(?:docs/|scieasy\.qa\.|[A-Za-z0-9_/.-]+/)[^`]+?\.md|scieasy\.qa\.audit\.[A-Za-z0-9_.]+)`"
)

#: Three consecutive numbered list items: heuristic for procedural duplication.
_NUMBERED_LIST_RE = re.compile(r"(?:^\s*\d+\.\s.+\n){3,}", re.MULTILINE)


def check(repo_root: Path | None = None) -> list[Finding]:
    """Validate every SKILL.md under ``.claude/skills/``.

    Per-skill checks:
      1. Frontmatter parseable; ``kind`` present (warning if missing).
      2. ``kind`` is one of {``procedural``, ``tool-wrapping``,
         ``bootstrap-meta``}.
      3. Body length ≤ 30 lines (frontmatter excluded). Exceeding emits a
         warning per §11.2's "~20 lines" guidance.
      4. Pointer target matches the regex for the declared kind.
      5. Pointer target exists on disk (file or importable module).
      6. No 3+ consecutive numbered list items (procedural duplication
         heuristic).

    Workflow-side checks (reverse closure):
      7. Every ``docs/contributing/workflows/*.md`` has ≥1 procedural
         skill referencing it.

    When ``docs/contributing/workflows/`` does not yet exist, step 7 is
    suppressed and replaced by a single INFO finding signalling the
    dormant state.
    """
    repo_root = repo_root or Path.cwd()
    skills_dir = repo_root / ".claude" / "skills"
    findings: list[Finding] = []
    if not skills_dir.is_dir():
        return findings

    procedural_targets: dict[str, str] = {}
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        rel_path = skill_md.relative_to(repo_root).as_posix()
        skill_findings, target = _lint_one_skill(skill_md, rel_path, repo_root)
        findings.extend(skill_findings)
        if target is not None:
            procedural_targets[skill_dir.name] = target

    findings.extend(_check_reverse_closure(repo_root, procedural_targets))
    return findings


def detect_skill_kind(frontmatter: dict[str, Any]) -> str | None:
    """Return the ``kind`` value if present and valid, else ``None``."""
    kind = frontmatter.get("kind")
    if not isinstance(kind, str):
        return None
    if kind not in {"procedural", "tool-wrapping", "bootstrap-meta"}:
        return None
    return kind


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _lint_one_skill(path: Path, rel_path: str, repo_root: Path) -> tuple[list[Finding], str | None]:
    """Lint one SKILL.md; return (findings, procedural target path or None)."""
    findings: list[Finding] = []
    text = path.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)

    if frontmatter is None:
        findings.append(
            Finding(
                rule_id="skill-pointer-sync.missing-frontmatter",
                severity=Severity.ERROR,
                file=rel_path,
                message="SKILL.md has no YAML frontmatter block",
            )
        )
        return findings, None

    kind = detect_skill_kind(frontmatter)
    if kind is None:
        findings.append(
            Finding(
                rule_id="skill-pointer-sync.missing-kind",
                severity=Severity.WARNING,
                file=rel_path,
                message=(
                    "SKILL.md frontmatter missing or invalid `kind` field; "
                    "must be one of {`procedural`, `tool-wrapping`, "
                    "`bootstrap-meta`} per ADR-044 §11.3."
                ),
            )
        )

    # Body length cap.
    body_lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(body_lines) > MAX_BODY_LINES:
        findings.append(
            Finding(
                rule_id="skill-pointer-sync.body-too-long",
                severity=Severity.WARNING,
                file=rel_path,
                message=(
                    f"SKILL.md body has {len(body_lines)} non-empty lines "
                    f"(cap {MAX_BODY_LINES} per ADR-044 §11.2 / §11.4). "
                    "Move procedural text into the pointed-at workflow doc."
                ),
            )
        )

    # Procedural-duplication heuristic.
    if _NUMBERED_LIST_RE.search(body):
        findings.append(
            Finding(
                rule_id="skill-pointer-sync.procedural-duplication",
                severity=Severity.WARNING,
                file=rel_path,
                message=(
                    "SKILL.md contains 3+ consecutive numbered list items; "
                    "this often indicates duplicated workflow procedure. "
                    "Move steps into the canonical workflow doc per "
                    "ADR-044 §11.1."
                ),
            )
        )

    # Pointer target resolution.
    target = _extract_pointer_target(body)
    procedural_target: str | None = None
    if kind is not None:
        target_findings, procedural_target = _check_target(kind, target, rel_path, repo_root)
        findings.extend(target_findings)

    return findings, procedural_target


def _split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Return ``(frontmatter_dict, body_text)``."""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None, parts[2]
    if not isinstance(data, dict):
        return None, parts[2]
    return data, parts[2]


def _extract_pointer_target(body: str) -> str | None:
    """Pull the first backticked path/module mention from the body."""
    match = _POINTER_LINE_RE.search(body)
    if match is None:
        return None
    return match.group("target")


def _check_target(kind: str, target: str | None, rel_path: str, repo_root: Path) -> tuple[list[Finding], str | None]:
    """Verify ``target`` is correctly shaped and exists for ``kind``."""
    findings: list[Finding] = []
    procedural_target: str | None = None

    if target is None:
        findings.append(
            Finding(
                rule_id="skill-pointer-sync.no-pointer",
                severity=Severity.WARNING,
                file=rel_path,
                message=(
                    f"SKILL.md ({kind}) names no pointer target. The body "
                    "should cite the canonical doc or module per ADR-044 §11.3."
                ),
            )
        )
        return findings, None

    if kind == "procedural":
        if not _PROCEDURAL_TARGET_RE.match(target):
            findings.append(
                Finding(
                    rule_id="skill-pointer-sync.pointer-shape-wrong",
                    severity=Severity.ERROR,
                    file=rel_path,
                    message=(
                        f"procedural skill pointer {target!r} must match "
                        "`docs/contributing/workflows/<slug>.md` per ADR-044 §11.3."
                    ),
                )
            )
            return findings, None
        procedural_target = target
        target_path = repo_root / target
        if not target_path.is_file():
            findings.append(
                Finding(
                    rule_id="skill-pointer-sync.target-missing",
                    severity=Severity.INFO,
                    file=rel_path,
                    message=(
                        f"procedural pointer target {target!r} not yet on "
                        "disk; will become ERROR once sub-phase 1D ships."
                    ),
                )
            )
            return findings, None
        return findings, procedural_target

    if kind == "tool-wrapping":
        if _REFERENCE_TARGET_RE.match(target):
            if not (repo_root / target).is_file():
                findings.append(
                    Finding(
                        rule_id="skill-pointer-sync.target-missing",
                        severity=Severity.INFO,
                        file=rel_path,
                        message=(
                            f"tool-wrapping reference target {target!r} not "
                            "yet on disk; will become ERROR once 1D ships."
                        ),
                    )
                )
        elif _TOOL_WRAP_MODULE_RE.match(target):
            # Module-path target — module-existence check is best-effort.
            if not _module_path_exists(target, repo_root):
                findings.append(
                    Finding(
                        rule_id="skill-pointer-sync.target-missing",
                        severity=Severity.WARNING,
                        file=rel_path,
                        message=(f"tool-wrapping module target {target!r} not found in src/ tree."),
                    )
                )
        else:
            findings.append(
                Finding(
                    rule_id="skill-pointer-sync.pointer-shape-wrong",
                    severity=Severity.ERROR,
                    file=rel_path,
                    message=(
                        f"tool-wrapping skill pointer {target!r} must match "
                        "`docs/contributing/reference/<slug>.md` OR "
                        "`scieasy.qa.audit.*` per ADR-044 §11.3."
                    ),
                )
            )
        return findings, None

    if kind == "bootstrap-meta":
        if not _BOOTSTRAP_TARGET_RE.match(target):
            findings.append(
                Finding(
                    rule_id="skill-pointer-sync.pointer-shape-wrong",
                    severity=Severity.ERROR,
                    file=rel_path,
                    message=(
                        f"bootstrap-meta pointer {target!r} must match `docs/doc-guide/<slug>.md` per ADR-044 §11.3."
                    ),
                )
            )
            return findings, None
        if not (repo_root / target).is_file():
            findings.append(
                Finding(
                    rule_id="skill-pointer-sync.target-missing",
                    severity=Severity.INFO,
                    file=rel_path,
                    message=(f"bootstrap-meta target {target!r} not yet on disk; will become ERROR once 1D ships."),
                )
            )
        return findings, None

    return findings, None


def _module_path_exists(module_path: str, repo_root: Path) -> bool:
    """Best-effort check: does ``scieasy.qa.audit.foo`` resolve to a file?"""
    parts = module_path.split(".")
    candidate = repo_root.joinpath("src", *parts).with_suffix(".py")
    return candidate.is_file()


def _check_reverse_closure(repo_root: Path, procedural_targets: dict[str, str]) -> list[Finding]:
    """Verify every workflow doc has ≥1 procedural skill pointing at it."""
    workflows_dir = repo_root / "docs" / "contributing" / "workflows"
    if not workflows_dir.is_dir():
        return [
            Finding(
                rule_id="skill-pointer-sync.workflows-dir-absent",
                severity=Severity.INFO,
                file="docs/contributing/workflows/",
                message=(
                    "docs/contributing/workflows/ does not yet exist; "
                    "reverse-closure check dormant until sub-phase 1D ships."
                ),
            )
        ]

    referenced = set(procedural_targets.values())
    findings: list[Finding] = []
    for workflow_path in sorted(workflows_dir.glob("*.md")):
        rel = workflow_path.relative_to(repo_root).as_posix()
        if rel not in referenced:
            findings.append(
                Finding(
                    rule_id="skill-pointer-sync.workflow-unreferenced",
                    severity=Severity.ERROR,
                    file=rel,
                    message=(
                        "workflow doc has no procedural skill pointing at "
                        "it. Add a SKILL.md under .claude/skills/ with "
                        f"`kind: procedural` and pointer {rel!r}."
                    ),
                )
            )
    return findings
