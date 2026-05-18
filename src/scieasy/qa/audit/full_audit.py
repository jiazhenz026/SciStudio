"""Orchestrate the full audit pipeline (ADR-042 §9.6).

:func:`run` is the top-level entry point invoked by CI and by the
Workflow v2 stage-5 ``implement_validate`` gate. It chains every audit
tool in this sub-package and aggregates their :class:`ToolRun` outputs
into a single :class:`AuditReport`.

The pipeline composition is fixed at the API level (one ToolRun per
tool), but each tool's individual config / scoping decisions stay
internal to that tool. ``pre_push=True`` runs only the fast subset:

* trailer_lint
* committer_enforce
* frontmatter_lint
* closure (via doc_drift's delegation)

This subset is the Q1B.7.1 manager default — slow tools
(:mod:`~scieasy.qa.audit.doc_drift` full pass, ``fact_drift`` scan)
are skipped during the local pre-push hook.

``self_check=True`` is the §28.2 continuous self-validation gate: when
set, ``targets`` defaults to ``[docs/adr/ADR-042.md]`` and the
``contradiction_audit`` tool is added.

References
----------
ADR-042 §9.6 — entry-point signature (authoritative).
ADR-042 §21.4 — CI aggregator surface.
ADR-042 §28.2 — self-check semantics.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from scieasy.qa.audit.closure import check_bidirectional
from scieasy.qa.audit.committer_enforce import check as committer_check
from scieasy.qa.audit.contradiction_audit import run as contradiction_run
from scieasy.qa.audit.doc_drift import classify_repo
from scieasy.qa.audit.fact_drift import check_substitutions
from scieasy.qa.audit.frontmatter_lint import lint_file
from scieasy.qa.audit.trailer_lint import run as trailer_run
from scieasy.qa.schemas.report import (
    AuditReport,
    DriftClass,
    Finding,
    Severity,
    ToolRun,
)

__all__ = ["run"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    repo_root: Path | None = None,
    *,
    targets: list[Path] | None = None,
    pre_push: bool = False,
    self_check: bool = False,
    commit_range: str | None = None,
) -> AuditReport:
    """Aggregate every audit tool into a single :class:`AuditReport`.

    Args:
        repo_root: Repository root (defaults to ``Path.cwd()``).
        targets: Narrow the per-file tools (frontmatter_lint,
            contradiction_audit) to specific files. ``None`` means
            "all ADRs + specs".
        pre_push: When ``True`` run only the fast subset (Q1B.7.1).
        self_check: When ``True`` target ADR-042 itself for §28.2.
        commit_range: Git revision range passed to ``trailer_lint``.
            ``None`` defaults to ``"origin/main..HEAD"`` so every commit
            on the PR/branch is audited (Codex P1 fix — single-commit
            ``HEAD~1..HEAD`` silently skips earlier commits on
            multi-commit branches). Falls back to ``"HEAD~1..HEAD"`` when
            ``origin/main`` cannot be resolved (fresh checkout / shallow
            clone).

    Returns:
        Single :class:`AuditReport` carrying one :class:`ToolRun` per
        invoked tool.
    """
    root = repo_root or Path.cwd()
    started_at = datetime.now(UTC)

    runs: list[ToolRun] = []

    if self_check and targets is None:
        targets = [root / "docs" / "adr" / "ADR-042.md"]

    file_targets = _resolve_file_targets(root, targets)

    resolved_range = commit_range or _default_commit_range(root)

    # ── Always-run tools (pre_push subset) ─────────────────────────────
    runs.append(_run_trailer_lint(root, resolved_range))
    runs.append(_run_committer_enforce(root))
    runs.append(_run_frontmatter_lint(root, file_targets))
    runs.append(_run_closure(root))

    if not pre_push:
        runs.append(_run_doc_drift(root))
        runs.append(_run_fact_drift(root))

    if self_check:
        runs.append(_run_contradiction(root, file_targets))

    completed_at = datetime.now(UTC)
    config_hash = hashlib.sha1(
        f"full_audit:pre_push={pre_push}:self_check={self_check}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:16]
    _ = config_hash  # config_hash currently scoped per-ToolRun; kept for API parity

    all_findings: list[Finding] = [f for tr in runs for f in tr.findings]

    return AuditReport(
        schema_version=1,
        run_id=f"full_audit-{started_at.strftime('%Y%m%dT%H%M%SZ')}",
        repo_sha=_resolve_repo_sha(root),
        repo_branch=_resolve_repo_branch(root),
        generated_at=completed_at,
        runs=runs,
        total_findings=len(all_findings),
        by_severity=dict(Counter(f.severity for f in all_findings)),
        by_drift_class=dict(Counter(f.drift_class for f in all_findings if f.drift_class is not None)),
        bidirectional_closure_ok=_closure_ok(runs),
        translation_ok=True,
    )


# ---------------------------------------------------------------------------
# Per-tool wrappers (uniform ToolRun packaging)
# ---------------------------------------------------------------------------


def _run_trailer_lint(root: Path, commit_range: str) -> ToolRun:
    started = datetime.now(UTC)
    findings = trailer_run(root, commit_range=commit_range)
    completed = datetime.now(UTC)
    return ToolRun(
        tool="trailer_lint",
        version="1",
        config_hash=_hash(f"trailer_lint:{root}:{commit_range}"),
        started_at=started,
        completed_at=completed,
        exit_status=_exit_status(findings),
        findings=findings,
    )


def _default_commit_range(root: Path) -> str:
    """Return the broadest sensible default commit range for trailer lint.

    Prefers ``origin/main..HEAD`` (every commit ahead of main, including
    pre-rebase intermediates). Falls back to ``HEAD~1..HEAD`` when the
    ``origin/main`` ref is not available (fresh clone, shallow CI checkout
    that hasn't fetched main, or a brand-new repo). Codex P1 fix on PR
    #1161 — the prior default silently skipped earlier commits on any
    multi-commit branch.
    """
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--verify", "origin/main"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "HEAD~1..HEAD"
    if out.returncode == 0 and out.stdout.strip():
        return "origin/main..HEAD"
    return "HEAD~1..HEAD"


def _run_committer_enforce(root: Path) -> ToolRun:
    started = datetime.now(UTC)
    findings = committer_check(root)
    completed = datetime.now(UTC)
    return ToolRun(
        tool="committer_enforce",
        version="1",
        config_hash=_hash(f"committer_enforce:{root}"),
        started_at=started,
        completed_at=completed,
        exit_status=_exit_status(findings),
        findings=findings,
    )


def _run_frontmatter_lint(root: Path, targets: list[Path]) -> ToolRun:
    started = datetime.now(UTC)
    findings: list[Finding] = []
    for t in targets:
        findings.extend(lint_file(t, repo_root=root))
    completed = datetime.now(UTC)
    return ToolRun(
        tool="frontmatter_lint",
        version="1",
        config_hash=_hash(f"frontmatter_lint:{root}:n={len(targets)}"),
        started_at=started,
        completed_at=completed,
        exit_status=_exit_status(findings),
        findings=findings,
    )


def _run_closure(root: Path) -> ToolRun:
    started = datetime.now(UTC)
    findings = check_bidirectional(root)
    completed = datetime.now(UTC)
    return ToolRun(
        tool="closure",
        version="1",
        config_hash=_hash(f"closure:{root}"),
        started_at=started,
        completed_at=completed,
        exit_status=_exit_status(findings),
        findings=findings,
    )


def _run_doc_drift(root: Path) -> ToolRun:
    started = datetime.now(UTC)
    report = classify_repo(root)
    completed = datetime.now(UTC)
    # classify_repo packages itself; we re-package the single ToolRun it
    # produces so the orchestrator surfaces uniform timestamps. The
    # findings list is preserved verbatim.
    inner = report.runs[0] if report.runs else None
    findings = list(inner.findings) if inner else []
    return ToolRun(
        tool="doc_drift",
        version=inner.version if inner else "1",
        config_hash=inner.config_hash if inner else _hash(f"doc_drift:{root}"),
        started_at=started,
        completed_at=completed,
        exit_status=_exit_status(findings),
        findings=findings,
    )


def _run_fact_drift(root: Path) -> ToolRun:
    started = datetime.now(UTC)
    findings = check_substitutions(root)
    completed = datetime.now(UTC)
    return ToolRun(
        tool="fact_drift",
        version="1",
        config_hash=_hash(f"fact_drift:{root}"),
        started_at=started,
        completed_at=completed,
        exit_status=_exit_status(findings),
        findings=findings,
    )


def _run_contradiction(root: Path, targets: list[Path]) -> ToolRun:
    started = datetime.now(UTC)
    report = contradiction_run(root, targets=targets)
    completed = datetime.now(UTC)
    inner = report.runs[0] if report.runs else None
    findings = list(inner.findings) if inner else []
    return ToolRun(
        tool="contradiction_audit",
        version=inner.version if inner else "1",
        config_hash=inner.config_hash if inner else _hash(f"contradiction:{root}"),
        started_at=started,
        completed_at=completed,
        exit_status=_exit_status(findings),
        findings=findings,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_file_targets(root: Path, targets: list[Path] | None) -> list[Path]:
    """Default to every ADR + every spec when ``targets`` is ``None``.

    Spec discovery checks BOTH ``docs/spec/`` (the singular form used by
    ADR-042 §5.2 prose) and ``docs/specs/`` (the actual repo layout —
    Codex P2 fix on PR #1161). All ``*.md`` files under either directory
    are passed to frontmatter_lint; the linter's own ``select_schema``
    decides which schema applies and emits a permissive fall-through
    when none does.
    """
    if targets is not None:
        return [t for t in targets if t.is_file()]
    out: list[Path] = []
    adr_dir = root / "docs" / "adr"
    if adr_dir.is_dir():
        out.extend(sorted(adr_dir.glob("ADR-*.md")))
    for spec_dirname in ("spec", "specs"):
        spec_dir = root / "docs" / spec_dirname
        if not spec_dir.is_dir():
            continue
        # SPEC-prefixed files first (ADR-042 §5.7 spec frontmatter
        # subset), then any other markdown under the dir.
        spec_files = sorted(spec_dir.glob("SPEC-*.md"))
        for f in spec_files:
            if f not in out:
                out.append(f)
        for f in sorted(spec_dir.glob("*.md")):
            if f not in out:
                out.append(f)
    return out


def _closure_ok(runs: list[ToolRun]) -> bool:
    for tr in runs:
        if tr.tool != "closure":
            continue
        return not any(f.rule_id.startswith("closure.") for f in tr.findings)
    return True


def _exit_status(findings: list[Finding]) -> Literal["ok", "warnings", "errors", "crash"]:
    if not findings:
        return "ok"
    if any(f.severity == Severity.ERROR for f in findings):
        return "errors"
    if any(f.severity == Severity.WARNING for f in findings):
        return "warnings"
    return "ok"


def _hash(s: str) -> str:
    return hashlib.sha1(s.encode(), usedforsecurity=False).hexdigest()[:16]


def _resolve_repo_sha(repo_root: Path) -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    return out.stdout.strip() or "unknown"


def _resolve_repo_branch(repo_root: Path) -> str:
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "unknown"
    return out.stdout.strip() or "unknown"


# DriftClass import is intentional even if unused: keeps the public API
# surface accessible at the orchestrator level so callers can reference
# `full_audit.DriftClass` without a separate import.
_ = DriftClass
