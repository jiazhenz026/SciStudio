"""Shared local/CI ADR-042 workflow gate orchestration."""

from __future__ import annotations

import importlib
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scistudio.qa.governance.gate_record.io import _load_record
from scistudio.qa.governance.gate_record.validation import check_pr
from scistudio.qa.schemas.report import AuditReport, AuditStatus


def _git_lines(repo_root: Path, args: Sequence[str]) -> list[str]:
    out = subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL)
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _governance_module(name: str) -> Any:
    return importlib.import_module(f"scistudio.qa.governance.{name}")


def _combined(reports: Sequence[AuditReport], *, repo_root: Path) -> AuditReport:
    findings = []
    for report in reports:
        findings.extend(report.findings)
    mod_guard = _governance_module("mod_guard")
    return AuditReport(
        tool="workflow_gate",
        status=AuditStatus.FAIL if any(report.blocks_merge for report in reports) else AuditStatus.PASS,
        source_sha=str(mod_guard._source_sha(repo_root)),
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
    mod_guard = _governance_module("mod_guard")
    mod_report = mod_guard.check(
        repo_root,
        base_ref=base,
        head_ref=head,
        allow_governance_change=bool(record.governance_touch),
    )
    issue_link = _governance_module("issue_link")
    docs_landing = _governance_module("docs_landing")
    weakened_ci_check = _governance_module("weakened_ci_check")
    reports = [
        check_pr(gate_record, changed_files=changed_files, pr_body=pr_body, pr_labels=pr_labels),
        issue_link.check(
            issues=issues,
            pr_body=pr_body,
            require_closing=True,
            followup_issues=followups,
            repo_root=repo_root,
        ),
        docs_landing.check(changed_files=changed_files, docs_landing=record.docs_landing, repo_root=repo_root),
        mod_report,
        weakened_ci_check.verify_no_weakening(repo_root, base_ref=base, head_ref=head),
    ]
    return _combined(reports, repo_root=repo_root)
