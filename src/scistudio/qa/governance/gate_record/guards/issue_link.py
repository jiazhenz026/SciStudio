"""issue_link calculator (ADR-042 Addendum 6 spec §4).

Produces: no linked issue; structurally invalid issue; PR body missing a closing
keyword for a deliverable issue.

Ported from the legacy ``issue_link`` (deleted on this branch). The closing
keyword regex now comes from the evaluator's single ``surfaces.CLOSING_KEYWORD_RE``
vocabulary instead of a private copy. Issues come from the ledger ``IssueRef``
records the evaluator supplies (no GitHub integration / ``resolve_or_create``
side concern lives here). Closing-keyword coverage is only enforced when a PR
body is supplied (pre-PR / CI modes).
"""

from __future__ import annotations

import re

import scistudio.qa.governance.gate_record.surfaces as surfaces
from scistudio.qa.governance.gate_record.guards._base import GuardInputs
from scistudio.qa.governance.gate_record.guards._stub import source_sha
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

_ISSUE_URL_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/([1-9]\d*)$")


def _closing_issue_numbers(pr_body: str) -> set[int]:
    return {int(match.group("number")) for match in surfaces.CLOSING_KEYWORD_RE.finditer(pr_body or "")}


def check(inputs: GuardInputs) -> AuditReport:
    """Validate issue evidence and PR closing-keyword coverage."""

    issues = list(inputs.issues)
    findings: list[Finding] = []

    if not issues:
        findings.append(
            Finding(
                rule_id="issue_link.missing",
                severity=Severity.ERROR,
                message="at least one linked issue is required",
            )
        )

    for issue in issues:
        # ``IssueRef.number`` is validated > 0 at the ledger layer; validate the
        # URL shape and number agreement here.
        if issue.url is not None:
            match = _ISSUE_URL_RE.match(issue.url)
            if match is None:
                findings.append(
                    Finding(
                        rule_id="issue_link.invalid-url",
                        severity=Severity.ERROR,
                        message="issue URL must be a GitHub issue URL",
                        evidence={"issue_url": issue.url},
                    )
                )
            elif int(match.group(1)) != issue.number:
                findings.append(
                    Finding(
                        rule_id="issue_link.url-number-mismatch",
                        severity=Severity.ERROR,
                        message="issue URL number does not match issue number",
                        evidence={"issue_number": issue.number, "issue_url": issue.url},
                    )
                )

    # Closing-keyword coverage only when a PR body exists (pre-PR / CI).
    if inputs.pr_body is not None:
        closed = _closing_issue_numbers(inputs.pr_body)
        for issue in issues:
            if not issue.close_in_pr:
                continue
            if issue.number not in closed:
                findings.append(
                    Finding(
                        rule_id="issue_link.missing-closing-keyword",
                        severity=Severity.ERROR,
                        message="PR body must close every delivered gate issue",
                        evidence={"issue_number": issue.number, "closed": sorted(closed)},
                    )
                )

    return AuditReport(
        tool="issue_link",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=source_sha(inputs.repo_root),
        findings=findings,
        summary={
            "issues": [issue.number for issue in issues],
            "closed_issues": sorted(_closing_issue_numbers(inputs.pr_body or "")),
            "pr_body_present": inputs.pr_body is not None,
        },
    )
