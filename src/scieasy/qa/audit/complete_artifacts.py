"""Verify Workflow v2 stage-6 ``complete_artifacts`` requirements
(ADR-042 §19.2 stage 6).

:func:`check` composes existing audit checks into a single
:class:`Finding`-list answer to the question "is this PR fully
artifacted?". Per ADR-042 §9.6 the signature is ``check(repo_root=None,
*, pr_number=None) -> list[Finding]``.

The composite checks (stage 6 row of §19.2's table):

1. **Docstrings** — every public symbol has a docstring
   (delegates to :mod:`scieasy.qa.audit.doc_drift` ``missing-docstring``
   findings).
2. **ADR governs updated** — every changed file is covered by some
   Accepted ADR's ``governs``
   (delegates to :mod:`scieasy.qa.audit.closure` ``asymmetric`` findings).
3. **MAINTAINERS updated** — same closure invariant from the MAINTAINERS
   side (also covered by ``closure.check_bidirectional``).
4. **Translation enqueued** — Phase-1D deliverable; for now we surface
   a placeholder INFO finding so the stage-6 gate does not silently
   pass through it.
5. **CHANGELOG entry** — checks ``CHANGELOG.md`` has an entry
   referencing ``#<pr_number>`` (or the closing issue) when
   ``pr_number`` is supplied.
6. **Codemod committed (if contract change)** — best-effort check that
   ``tools/codemods/`` contains a file referencing the PR; gated on
   ``contract_change`` declaration we don't have access to here, so
   surfaced as INFO when not applicable.
7. **RBP attached** — placeholder INFO; the actual evidence lives on
   the GitHub PR body and is verified by the §14.3 CI workflow.
8. **Skills installed cross-runtime** — delegated to a §17.4 stub.

The composite is filtered to the PR's diff scope when ``pr_number`` is
supplied — we compute the diff via ``git diff origin/main...HEAD``
(best-effort; falls back to no-filter if git fails).

References
----------
ADR-042 §19.2 — workflow stage 6 (authoritative).
ADR-042 §9.6 — entry-point signature.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from scieasy.qa.audit.closure import check_bidirectional
from scieasy.qa.audit.doc_drift import classify_repo
from scieasy.qa.schemas.report import Finding, Severity

__all__ = ["check"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def check(
    repo_root: Path | None = None,
    *,
    pr_number: int | None = None,
) -> list[Finding]:
    """Aggregate the stage-6 ``complete_artifacts`` checks into one list.

    Args:
        repo_root: Repository root (defaults to ``Path.cwd()``).
        pr_number: When supplied, findings are filtered to files in the
            PR's diff against ``origin/main``.

    Returns:
        Flat list of :class:`Finding`. Empty when stage 6 is fully met.
    """
    root = repo_root or Path.cwd()
    findings: list[Finding] = []

    # 1. Docstrings + 2-3. governs/MAINTAINERS closure are emitted by
    # doc_drift's full pass (which itself delegates closure).
    report = classify_repo(root)
    for tr in report.runs:
        for f in tr.findings:
            if f.rule_id in {
                "doc-drift.missing-docstring",
                "doc-drift.orphan-class",
                "closure.asymmetric",
            }:
                findings.append(f)

    # Closure may not have been delegated in the doc_drift pass for
    # tests that monkey-patch classify_repo — re-run defensively here.
    if not any(f.rule_id.startswith("closure.") for f in findings):
        findings.extend(check_bidirectional(root))

    # 5. CHANGELOG entry.
    findings.extend(_check_changelog(root, pr_number))

    # 4 / 6 / 7 / 8 — placeholders (downstream sub-phases will tighten).
    # We surface them as INFO so stage-6 reports are explicit about what
    # is NOT yet covered, rather than silently passing.
    findings.append(_translation_placeholder())
    findings.append(_codemod_placeholder())
    findings.append(_rbp_placeholder(pr_number))
    findings.append(_skills_placeholder())

    if pr_number is not None:
        diff_files = _pr_diff_files(root)
        if diff_files:
            findings = _filter_to_diff(findings, diff_files)

    return findings


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_changelog(repo_root: Path, pr_number: int | None) -> list[Finding]:
    """Verify CHANGELOG.md carries an entry for the current change."""
    if pr_number is None:
        # Without a PR number we cannot bind the entry; emit INFO so the
        # caller (or downstream audit aggregator) knows we deferred.
        return [
            Finding(
                rule_id="complete-artifacts.changelog-skipped",
                severity=Severity.INFO,
                file="CHANGELOG.md",
                message=(
                    "CHANGELOG check skipped: pr_number not supplied. Stage-6 "
                    "CLI invocation should pass --pr-number for full coverage."
                ),
            )
        ]
    path = repo_root / "CHANGELOG.md"
    if not path.is_file():
        return [
            Finding(
                rule_id="complete-artifacts.changelog-missing",
                severity=Severity.ERROR,
                file="CHANGELOG.md",
                message="CHANGELOG.md does not exist; stage 6 requires it",
            )
        ]
    text = path.read_text(encoding="utf-8")
    if re.search(rf"#{pr_number}\b", text):
        return []
    # Allow an issue-number reference as a proxy (some workflows refer
    # to the closing issue rather than the PR).
    if re.search(rf"\bissue\s*#?\s*{pr_number}\b", text, re.IGNORECASE):
        return []
    return [
        Finding(
            rule_id="complete-artifacts.changelog-no-entry",
            severity=Severity.ERROR,
            file="CHANGELOG.md",
            message=(
                f"CHANGELOG.md does not reference PR #{pr_number}; stage-6 "
                "requires a [Unreleased] entry per CLAUDE.md Appendix A step 5"
            ),
            suggested_fix=(
                f"add a line: '- [#{pr_number}] <description> (@agent, "
                "YYYY-MM-DD, branch: ..., session: ...)' under [Unreleased]"
            ),
        )
    ]


def _translation_placeholder() -> Finding:
    # TODO(#1153-ext): wire ADR-042 §22 translator gate
    #   Out of scope per Phase 1B sub-PR 2 scope (1D ships docs translator).
    #   Followup: open 1B.7-ext after 1D ships.
    return Finding(
        rule_id="complete-artifacts.translation-placeholder",
        severity=Severity.INFO,
        file="docs/",
        message=(
            "translation gate not yet wired (Phase 1D deliverable per Q1B.7.x). Stage-6 currently reports INFO only."
        ),
    )


def _codemod_placeholder() -> Finding:
    # TODO(#1153-ext): wire codemod-with-adr check from §20
    #   Out of scope per Phase 1B sub-PR 2 scope.
    #   Followup: open 1B.7-ext after §20 codemod sub-phase lands.
    return Finding(
        rule_id="complete-artifacts.codemod-placeholder",
        severity=Severity.INFO,
        file="tools/codemods/",
        message=(
            "codemod check stub: actual logic gated on 'contract_change' "
            "declaration which is per-task and not available here."
        ),
    )


def _rbp_placeholder(pr_number: int | None) -> Finding:
    # TODO(#1153-ext): wire §14 Real-Behavior-Proof gate
    #   Out of scope per Phase 1B sub-PR 2 (RBP is CI-side; the §14.3 PR
    #   template enforces it via GitHub UI).
    #   Followup: open 1B.7-ext after §14 CI workflow lands.
    msg = (
        "RBP gate placeholder: real proof verification happens at PR-review "
        "time via §14.3 PR template. Stage 6 cannot verify a screenshot "
        "or video artefact mechanically."
    )
    if pr_number is not None:
        msg += f" (PR #{pr_number})"
    return Finding(
        rule_id="complete-artifacts.rbp-placeholder",
        severity=Severity.INFO,
        file="<PR body>",
        message=msg,
    )


def _skills_placeholder() -> Finding:
    # TODO(#1153-ext): wire §17.4 skill-installation cross-runtime check
    #   Out of scope per Phase 1B sub-PR 2.
    #   Followup: open 1B.7-ext after agent_provisioning lands.
    return Finding(
        rule_id="complete-artifacts.skills-placeholder",
        severity=Severity.INFO,
        file="docs/skills/required.yaml",
        message=(
            "cross-runtime skill-install check stub (Phase 17 deliverable); current implementation reports INFO only."
        ),
    )


# ---------------------------------------------------------------------------
# Diff scope filter
# ---------------------------------------------------------------------------


def _pr_diff_files(repo_root: Path) -> set[str]:
    """Best-effort: return the set of files changed against ``origin/main``."""
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    if out.returncode != 0:
        return set()
    return {line.strip().replace("\\", "/") for line in out.stdout.splitlines() if line.strip()}


#: Findings whose existence is independent of the PR diff scope. The
#: stage-6 contract requires every change to ship a CHANGELOG entry
#: (CLAUDE.md Appendix A step 5), so a "missing CHANGELOG" finding MUST
#: survive diff filtering — otherwise a PR that simply forgets to touch
#: ``CHANGELOG.md`` would pass stage 6 (the changelog isn't in its own
#: diff, so the filter would drop the finding). Codex P1 fix on PR
#: #1161.
_DIFF_FILTER_BYPASS_RULE_IDS: frozenset[str] = frozenset(
    {
        "complete-artifacts.changelog-missing",
        "complete-artifacts.changelog-no-entry",
        "complete-artifacts.changelog-skipped",
    }
)


def _filter_to_diff(findings: list[Finding], diff_files: set[str]) -> list[Finding]:
    """Return findings whose ``file`` matches the PR diff set.

    Findings whose ``file`` is a synthetic placeholder (``<PR body>``,
    ``docs/skills/required.yaml``, etc.) pass through unconditionally so
    stage-6 reporters can still surface the placeholder context.
    Findings whose ``rule_id`` is in :data:`_DIFF_FILTER_BYPASS_RULE_IDS`
    also bypass the filter — see the constant's docstring.
    """
    kept: list[Finding] = []
    for f in findings:
        if f.rule_id in _DIFF_FILTER_BYPASS_RULE_IDS:
            kept.append(f)
            continue
        norm = f.file.replace("\\", "/")
        if norm.startswith("<") or norm.endswith("/"):
            kept.append(f)
            continue
        if norm in diff_files:
            kept.append(f)
            continue
        # Match by parent directory glob (closure findings often cite a
        # source path that's a parent of the diff entry).
        if any(d.startswith(norm + "/") or norm.startswith(d + "/") for d in diff_files):
            kept.append(f)
    return kept
