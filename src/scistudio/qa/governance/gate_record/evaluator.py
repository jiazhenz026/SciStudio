"""The single shared evaluator for ADR-042 Addendum 6 (spec §3).

``reconcile()`` is the one reconciliation code path that every command, hook,
PR wrapper, and CI step calls. The ``mode`` only changes which facts are
required-now versus recorded as a pre-PR gap; it never forks the logic.

Pipeline (§3.3): observe git diff -> classify surfaces -> reconcile declared
scope -> reconcile declared docs/test claims -> infer obligations -> derive
strictness tier (escalate, never lower, §7.6) -> infer + run tier-selected
checks (with parity) -> run guard calculators -> write a reconcile event ->
sanitize committed events.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from scistudio.qa.governance.gate_record import checks, io, parity, surfaces
from scistudio.qa.governance.gate_record.guards import GUARD_REGISTRY, GuardInputs
from scistudio.qa.governance.gate_record.ledger import (
    CheckEvent,
    GateLedger,
    GuardEvent,
    ObservedDiff,
    ReconcileEvent,
    RequiredObligations,
    StrictnessTier,
    TaskKind,
)
from scistudio.qa.schemas.report import AuditFinding, AuditReport, AuditStatus, Severity

EvaluatorMode = Literal["local", "pre-commit", "commit-msg", "pre-push", "pre-pr", "ci"]

# Baseline tier from task kind (§7.6). Escalation only raises (never lowers).
_BASELINE_TIER: dict[str, StrictnessTier] = {
    "feature": 1,
    "refactor": 1,
    "bugfix": 2,
    "hotfix": 2,
    "maintenance": 2,
    "guided": 2,
    "docs": 3,
    "manager": 3,
}

# Surface classes the evaluator records on the observed diff.
_SURFACE_CLASSIFIERS = {
    "implementation": surfaces.is_implementation_path,
    "test": surfaces.is_test_path,
    "governance": surfaces.is_governance_path,
    "protected_core": surfaces.is_protected_core_path,
    "frontend": surfaces.is_frontend_path,
    "packaging": surfaces.is_packaging_path,
    "workflow_ci": surfaces.is_workflow_ci_path,
    "docs": surfaces.is_docs_path,
    "governed_docs": surfaces.is_governed_doc_path,
    "sentrux": surfaces.sentrux_applies,
}


@dataclass
class ReconcileResult:
    """The consolidated outcome of one ``reconcile()`` call (spec §3.1)."""

    report: AuditReport
    strictness_tier: StrictnessTier
    required_obligations: RequiredObligations
    unsatisfied: list[str] = field(default_factory=list)
    repair_hints: list[str] = field(default_factory=list)
    check_events: list[CheckEvent] = field(default_factory=list)
    guard_events: list[GuardEvent] = field(default_factory=list)
    reconcile_event: ReconcileEvent | None = None
    parity_gaps: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.unsatisfied and not self.report.blocks_merge


def classify_surfaces(changed_files: Sequence[str]) -> dict[str, list[str]]:
    """Group changed files by surface class (§3.3.2)."""

    grouped: dict[str, list[str]] = {name: [] for name in _SURFACE_CLASSIFIERS}
    for path in changed_files:
        for name, predicate in _SURFACE_CLASSIFIERS.items():
            if predicate(path):
                grouped[name].append(path)
    return grouped


def derive_tier(task_kind: TaskKind, grouped: dict[str, list[str]]) -> StrictnessTier:
    """Derive the strictness tier: baseline + escalation only (§7.6)."""

    tier: StrictnessTier = _BASELINE_TIER.get(task_kind, 2)
    escalate = bool(grouped["protected_core"] or grouped["governance"] or grouped["workflow_ci"])
    # Broad cross-module change: many distinct top-level surfaces touched.
    distinct_surfaces = sum(1 for name in ("implementation", "frontend", "packaging") if grouped[name])
    if distinct_surfaces >= 3:
        escalate = True
    if escalate:
        return 1
    return tier


def _scope_findings(ledger: GateLedger, changed_files: Sequence[str]) -> list[AuditFinding]:
    """Reconcile declared scope against the observed diff (§3.3.3)."""

    include = ledger.effective_include()
    exclude = ledger.effective_exclude()
    findings: list[AuditFinding] = []
    if not include:
        # No declared include: scope reconciliation defers to tier obligations.
        return findings
    for path in changed_files:
        if surfaces.is_gate_record_path(path):
            continue
        in_scope = surfaces.matches_any(path, include)
        excluded = surfaces.matches_any(path, exclude)
        if not in_scope or excluded:
            findings.append(
                AuditFinding(
                    rule_id="scope.out-of-scope",
                    severity=Severity.ERROR,
                    file=path,
                    message="changed file is outside the effective declared scope",
                    evidence={"include": include, "exclude": exclude},
                )
            )
    return findings


def _verify_claims(declared: Sequence[str], changed_files: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split declared paths into verified-in-diff and claimed-but-unverified."""

    changed = {surfaces.normalize_path(p) for p in changed_files}
    verified = [p for p in declared if surfaces.normalize_path(p) in changed]
    unverified = [p for p in declared if surfaces.normalize_path(p) not in changed]
    return verified, unverified


def _infer_obligations(
    *,
    task_kind: TaskKind,
    tier: StrictnessTier,
    grouped: dict[str, list[str]],
    required_checks: Sequence[str],
) -> RequiredObligations:
    """Infer required obligations from task kind, tier, and surfaces (§3.3.5)."""

    docs: list[str] = []
    tests: list[str] = []
    guards = sorted(GUARD_REGISTRY.keys())
    admin_labels: list[str] = []

    # Docs obligation when governed/contract surfaces change.
    if grouped["implementation"] or grouped["governance"] or grouped["governed_docs"]:
        docs.append("docs_required_or_na")
    # Test obligation when implementation/runtime/tooling surfaces change.
    if grouped["implementation"] and task_kind not in ("docs", "manager"):
        tests.append("changed_test_required")
    # Protected-core authorization.
    if grouped["protected_core"]:
        admin_labels.append("admin-approved:core-change")

    return RequiredObligations(
        checks=list(required_checks),
        docs=docs,
        tests=tests,
        guards=guards,
        admin_labels=admin_labels,
    )


def reconcile(
    *,
    ledger: GateLedger,
    repo_root: Path,
    base: str,
    head: str,
    mode: EvaluatorMode,
    pr_body: str | None = None,
    pr_context: dict[str, Any] | None = None,
    run_checks: bool = True,
    only: Sequence[str] | None = None,
) -> ReconcileResult:
    """The single shared reconciliation entry point (spec §3.1)."""

    staged = mode == "pre-commit"

    # 1. Observe the git diff (objective evidence, never agent claims).
    observed_files = io.changed_files(repo_root, base, head, staged=staged)
    fingerprint = io.diff_fingerprint(repo_root, base, head, staged=staged)

    # 2. Classify surfaces.
    grouped = classify_surfaces(observed_files)

    # Record observed diff on the ledger (append: latest wins).
    ledger.observed_diff = ObservedDiff(
        base=base,
        head=head,
        base_sha=io.resolve_sha(repo_root, base),
        head_sha=io.resolve_sha(repo_root, head),
        diff_fingerprint=fingerprint,
        changed_files=list(observed_files),
        surfaces={name: len(paths) for name, paths in grouped.items()},
    )

    # 6. Derive tier (escalate, never lower). Done before check inference.
    tier = derive_tier(ledger.task_kind, grouped)
    ledger.strictness_tier = tier

    findings: list[AuditFinding] = []
    unsatisfied: list[str] = []
    repair_hints: list[str] = []
    parity_gaps: list[str] = []

    # 3. Reconcile declared scope against the observed diff.
    findings.extend(_scope_findings(ledger, observed_files))

    # 4. Reconcile declared docs/test claims (claimed-but-unverified, §3.3.4).
    verified_docs, unverified_docs = _verify_claims(ledger.declared_docs_paths(), observed_files)
    verified_tests, unverified_tests = _verify_claims(ledger.declared_test_paths(), observed_files)
    for path in unverified_docs:
        findings.append(
            AuditFinding(
                rule_id="docs.claimed-but-unverified",
                severity=Severity.WARNING,
                file=path,
                message="declared docs path is not in the observed diff; does not satisfy a docs obligation",
            )
        )
    for path in unverified_tests:
        findings.append(
            AuditFinding(
                rule_id="tests.claimed-but-unverified",
                severity=Severity.WARNING,
                file=path,
                message="declared test path is not in the observed diff; does not satisfy a test obligation",
            )
        )

    # 7. Infer tier-selected required check set from the CI graph.
    selection = checks.select_checks(tier=tier, changed_files=observed_files)
    parity_gaps.extend(selection.parity_gaps)

    # 5. Infer obligations.
    obligations = _infer_obligations(
        task_kind=ledger.task_kind,
        tier=tier,
        grouped=grouped,
        required_checks=selection.required,
    )
    ledger.required_obligations = obligations

    # 8. Execute / validate checks with parity (§7.10), unless skipping.
    check_events: list[CheckEvent] = []
    na_names = {na.name for na in ledger.check_na}
    if run_checks and mode not in ("commit-msg",):
        parity_report = parity.assess_parity(repo_root)
        if mode in ("pre-pr", "ci") and not parity_report.importable:
            # Fail closed for PR readiness (exit 4 surfaced by the CLI).
            parity_gaps.extend(parity_report.gaps)
        to_run = [name for name in selection.required if name not in na_names]
        if only is not None:
            to_run = [name for name in to_run if name in set(only)]
        for name in to_run:
            event = checks.run_check(repo_root, name, changed_files=observed_files, diff_fingerprint=fingerprint)
            check_events.append(event)
            ledger.check_events.append(event)
            if event.status == "fail":
                unsatisfied.append(f"checks.{name}")
                repair_hints.append(f"- checks.{name}\n  Re-run the check after fixing:\n  {event.command}")

    # Docs/test obligations unsatisfied when no verified evidence and no N/A.
    docs_na = any(event.kind == "na" for event in ledger.docs_events)
    tests_na = any(event.kind == "na" for event in ledger.test_events)
    if obligations.docs and not verified_docs and not docs_na:
        unsatisfied.append("docs.docs_required_or_na")
        repair_hints.append(
            "- docs.docs_required_or_na\n  Record a docs path or N/A:\n"
            "  gate_record amend --reason '<why>' --docs-na 'implementation:<rationale>'"
        )
    if obligations.tests and not verified_tests and not tests_na:
        unsatisfied.append("tests.changed_test_required")
        repair_hints.append(
            "- tests.changed_test_required\n  Add a changed test path:\n"
            "  gate_record amend --reason '<why>' --test-path tests/<area>/test_<x>.py"
        )

    # Issue obligation (always required before PR readiness, §7.7.3).
    if mode in ("pre-pr", "ci") and not ledger.issues:
        unsatisfied.append("issue.required")
        repair_hints.append("- issue.required\n  Link an issue:\n  gate_record amend --reason '<why>' --issue <n>")

    # 9. Run guard calculators (each exactly once, §3.3.9).
    guard_inputs = GuardInputs(
        repo_root=repo_root,
        mode=mode,
        task_kind=ledger.task_kind,
        persona=ledger.persona,
        runtime=ledger.runtime,
        tier=tier,
        governance_touch=ledger.governance_touch,
        changed_files=list(observed_files),
        diff_fingerprint=fingerprint,
        surfaces={name: list(paths) for name, paths in grouped.items()},
        effective_include=ledger.effective_include(),
        effective_exclude=ledger.effective_exclude(),
        declared_docs_paths=ledger.declared_docs_paths(),
        declared_test_paths=ledger.declared_test_paths(),
        verified_docs_paths=verified_docs,
        verified_test_paths=verified_tests,
        issues=list(ledger.issues),
        pr_body=pr_body,
        pr_context=pr_context,
        requested_admin_labels=list(ledger.requested_admin_labels),
        observed_admin_labels=list(ledger.observed_admin_labels),
    )
    guard_reports: list[AuditReport] = []
    guard_events: list[GuardEvent] = []
    for name in sorted(GUARD_REGISTRY):
        guard = GUARD_REGISTRY[name]
        report = guard(guard_inputs)
        guard_reports.append(report)
        guard_status: Literal["pass", "fail"] = "fail" if report.blocks_merge else "pass"
        guard_event = GuardEvent(
            guard=name,
            status=guard_status,
            findings=[f.model_dump(mode="json") for f in report.findings],
        )
        guard_events.append(guard_event)
        ledger.guard_events.append(guard_event)
        if report.blocks_merge:
            unsatisfied.append(f"guard.{name}")
            findings.extend(report.error_findings())

    # Parity gaps fail closed for PR readiness.
    if mode in ("pre-pr", "ci") and parity_gaps:
        for gap in parity_gaps:
            unsatisfied.append(f"parity.{gap}")

    result_status = AuditStatus.FAIL if (findings or unsatisfied) else AuditStatus.PASS
    report = AuditReport(
        tool="gate_record.evaluator",
        status=result_status,
        source_sha=ledger.observed_diff.head_sha or "unknown",
        findings=findings,
        summary={
            "mode": mode,
            "tier": tier,
            "task_kind": ledger.task_kind,
            "required_checks": selection.required,
            "pr_only_checks": selection.pr_only,
        },
        child_reports=guard_reports,
    )

    # 10. Write a reconcile event.
    reconcile_event = ReconcileEvent(
        mode=mode,
        tier=tier,
        diff_fingerprint=fingerprint,
        result="pass" if not unsatisfied and not report.blocks_merge else "fail",
        unsatisfied=sorted(set(unsatisfied)),
    )
    ledger.reconcile_events.append(reconcile_event)

    return ReconcileResult(
        report=report,
        strictness_tier=tier,
        required_obligations=obligations,
        unsatisfied=sorted(set(unsatisfied)),
        repair_hints=repair_hints,
        check_events=check_events,
        guard_events=guard_events,
        reconcile_event=reconcile_event,
        parity_gaps=parity_gaps,
    )
