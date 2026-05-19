"""Aggregate ADR-042 consistency checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scieasy.qa._report_helpers import build_finding
from scieasy.qa._shared import AuditFinding, AuditReport, git_sha, now_utc
from scieasy.qa.audit._cli import exit_code, print_report
from scieasy.qa.audit.closure import check_bidirectional
from scieasy.qa.audit.doc_drift import classify_repo
from scieasy.qa.audit.fact_drift import check_substitutions
from scieasy.qa.audit.facts import generate_facts
from scieasy.qa.audit.signature_drift import check_expected_signatures
from scieasy.qa.schemas.facts import load_facts


def _child_error(tool: str, exc: Exception, repo_root: Path) -> AuditReport:
    finding = build_finding(
        finding_id=f"full-audit-child-error-{tool}",
        tool="full_audit",
        finding_class="child-error",
        severity="error",
        message=f"Child audit {tool} failed unexpectedly: {exc}",
        subject=tool,
    )
    return AuditReport(
        tool=tool,
        status="error",
        generated_at=now_utc(),
        source_sha=git_sha(repo_root),
        findings=[finding],
    )


def run(
    repo_root: Path,
    *,
    facts_path: Path = Path("docs/facts/generated.yaml"),
    include_doc_drift: bool = True,
    include_fact_drift: bool = True,
    include_closure: bool = True,
    include_signature_drift: bool = True,
) -> AuditReport:
    repo_root = repo_root.resolve()
    target = facts_path if facts_path.is_absolute() else repo_root / facts_path
    facts = load_facts(target) if target.exists() else generate_facts(repo_root)

    child_reports: list[AuditReport] = []
    for name, enabled, callback in [
        ("doc_drift", include_doc_drift, lambda: classify_repo(repo_root, facts)),
        ("fact_drift", include_fact_drift, lambda: check_substitutions(repo_root, facts)),
        ("closure", include_closure, lambda: check_bidirectional(repo_root, facts)),
        ("signature_drift", include_signature_drift, lambda: check_expected_signatures(repo_root, facts)),
    ]:
        if not enabled:
            child_reports.append(
                AuditReport(
                    tool=name,
                    status="skipped",
                    generated_at=now_utc(),
                    source_sha=git_sha(repo_root),
                    findings=[],
                    summary={"disabled": True},
                )
            )
            continue
        try:
            child_reports.append(callback())
        except Exception as exc:
            child_reports.append(_child_error(name, exc, repo_root))

    findings: list[AuditFinding] = []
    for report in child_reports:
        for finding in report.findings:
            if finding.severity == "error":
                findings.append(
                    build_finding(
                        finding_id=f"full-audit-child-failure-{report.tool}-{finding.id}",
                        tool="full_audit",
                        finding_class=finding.finding_class,
                        severity="error",
                        message=f"{report.tool}: {finding.message}",
                        path=finding.path,
                        line=finding.line,
                        subject=finding.subject,
                        expected=finding.expected,
                        actual=finding.actual,
                        remediation=finding.remediation,
                        evidence={"child_tool": report.tool, "child_finding_id": finding.id},
                    )
                )

    status = "failed" if findings else "passed"
    return AuditReport(
        tool="full_audit",
        status=status,
        generated_at=now_utc(),
        source_sha=git_sha(repo_root),
        findings=findings,
        summary={"children": {report.tool: report.status for report in child_reports}},
        child_reports=child_reports,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run aggregate ADR-042 consistency audit.")
    parser.add_argument("--facts", default="docs/facts/generated.yaml")
    parser.add_argument("--skip-doc-drift", action="store_true")
    parser.add_argument("--skip-fact-drift", action="store_true")
    parser.add_argument("--skip-closure", action="store_true")
    parser.add_argument("--skip-signature-drift", action="store_true")
    parser.add_argument("--format", default="text", choices=["text", "json"])
    args = parser.parse_args(argv)
    try:
        report = run(
            Path.cwd(),
            facts_path=Path(args.facts),
            include_doc_drift=not args.skip_doc_drift,
            include_fact_drift=not args.skip_fact_drift,
            include_closure=not args.skip_closure,
            include_signature_drift=not args.skip_signature_drift,
        )
    except Exception as exc:
        print(f"full_audit: {exc}", file=sys.stderr)
        return 2
    print_report(report, as_json=args.format == "json")
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
