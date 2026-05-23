"""Shared local/CI ADR-042 workflow gate orchestration."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from scistudio.qa.governance import docs_landing, issue_link, mod_guard, weakened_ci_check
from scistudio.qa.governance.gate_record.io import _load_record
from scistudio.qa.governance.gate_record.validation import check_pr
from scistudio.qa.schemas.report import AuditReport, AuditStatus


def _git_lines(repo_root: Path, args: Sequence[str]) -> list[str]:
    out = subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL)
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _source_sha(repo_root: Path) -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _combined(reports: Sequence[AuditReport], *, repo_root: Path) -> AuditReport:
    findings = []
    for report in reports:
        findings.extend(report.findings)
    return AuditReport(
        tool="workflow_gate",
        status=AuditStatus.FAIL if any(report.blocks_merge for report in reports) else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        child_reports=list(reports),
        summary={"children": [report.tool for report in reports]},
    )


def run_ci(
    *,
    repo_root: Path,
    gate_record: Path,
    base: str = "origin/main",
    head: str = "HEAD",
    pr_body: str = "",
    pr_labels: Sequence[str] = (),
) -> AuditReport:
    """Run the local/CI-shared blocking guards over the exact branch diff."""

    repo_root = repo_root.resolve()
    changed_files = _git_lines(repo_root, ["diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...{head}"])
    record = _load_record(gate_record)
    record_json = record.model_dump(mode="json")
    issues = record_json.get("issues", [])
    followups = [issue["number"] for issue in issues if not issue.get("close_in_pr", True)]
    mod_report = mod_guard.check(
        repo_root,
        base_ref=base,
        head_ref=head,
        allow_governance_change=bool(record.governance_touch),
    )
    reports = [
        check_pr(gate_record, changed_files=changed_files, pr_body=pr_body, pr_labels=pr_labels),
        issue_link.check(
            issues=issues, pr_body=pr_body, require_closing=True, followup_issues=followups, repo_root=repo_root
        ),
        docs_landing.check(changed_files=changed_files, docs_landing=record.docs_landing, repo_root=repo_root),
        mod_report,
        weakened_ci_check.verify_no_weakening(repo_root, base_ref=base, head_ref=head),
    ]
    return _combined(reports, repo_root=repo_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ci",))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--pr-body", default="")
    parser.add_argument("--pr-label", action="append", default=[])
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    report = run_ci(
        repo_root=args.repo_root,
        gate_record=args.gate_record,
        base=args.base,
        head=args.head,
        pr_body=args.pr_body,
        pr_labels=args.pr_label,
    )
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        if report.blocks_merge:
            print("workflow_gate: fail")
            for finding in report.findings:
                print(f"- {finding.rule_id}: {finding.message}")
        else:
            print("workflow_gate: pass")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    raise SystemExit(main())
