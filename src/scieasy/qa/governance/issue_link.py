"""Validate ADR-042 issue linkage and PR closing keywords."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

ISSUE_URL_RE = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/issues/([1-9]\d*)$")
CLOSING_RE = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:https://github\.com/[^/\s]+/[^/\s]+/issues/)?#?([1-9]\d*)\b"
)


@dataclass(frozen=True)
class IssueRecord:
    """Repository issue evidence used by governance checks."""

    number: int
    url: str
    title: str = ""
    state: str = "open"


@dataclass(frozen=True)
class IssueQuery:
    """Fixture-friendly issue lookup or creation request."""

    title: str
    body: str = ""
    labels: tuple[str, ...] = ()
    existing_number: int | None = None
    existing_url: str | None = None


class IssueClient(Protocol):
    """Minimal issue client contract used by tests or GitHub wrappers."""

    def search_issues(self, query: IssueQuery) -> list[IssueRecord]: ...

    def create_issue(self, query: IssueQuery) -> IssueRecord: ...


def _source_sha(repo_root: Path | None) -> str:
    if repo_root is None:
        return "unknown"
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _coerce_issue(value: IssueRecord | Mapping[str, object]) -> IssueRecord:
    if isinstance(value, IssueRecord):
        return value
    number = value.get("number")
    url = value.get("url") or value.get("issue_url")
    if not isinstance(number, int):
        raise ValueError("issue number must be an integer")
    if not isinstance(url, str):
        raise ValueError("issue URL must be a string")
    return IssueRecord(
        number=number,
        url=url,
        title=str(value.get("title", "")),
        state=str(value.get("state", "open")),
    )


def _validate_issue(record: IssueRecord) -> list[Finding]:
    findings: list[Finding] = []
    if record.number <= 0:
        findings.append(
            Finding(
                rule_id="issue_link.invalid-number",
                severity=Severity.ERROR,
                message="issue number must be a positive integer",
                evidence={"issue_number": record.number},
            )
        )
    match = ISSUE_URL_RE.match(record.url)
    if match is None:
        findings.append(
            Finding(
                rule_id="issue_link.invalid-url",
                severity=Severity.ERROR,
                message="issue URL must be a GitHub issue URL",
                evidence={"issue_url": record.url},
            )
        )
    elif int(match.group(1)) != record.number:
        findings.append(
            Finding(
                rule_id="issue_link.url-number-mismatch",
                severity=Severity.ERROR,
                message="issue URL number does not match issue number",
                evidence={"issue_number": record.number, "issue_url": record.url},
            )
        )
    return findings


def resolve_or_create(
    query: IssueQuery,
    *,
    client: IssueClient | None = None,
    create_if_missing: bool = False,
) -> IssueRecord:
    """Resolve an existing issue, or create one through an explicit client."""

    if query.existing_number is not None and query.existing_url is not None:
        record = IssueRecord(number=query.existing_number, url=query.existing_url, title=query.title)
        findings = _validate_issue(record)
        if findings:
            raise ValueError("; ".join(finding.message for finding in findings))
        return record

    if client is None:
        raise ValueError("issue client is required when no existing issue is supplied")

    matches = client.search_issues(query)
    if matches:
        return matches[0]
    if create_if_missing:
        return client.create_issue(query)
    raise ValueError("no existing issue matched and create_if_missing is false")


def closing_issue_numbers(pr_body: str) -> set[int]:
    """Return issue numbers closed by GitHub closing keywords."""

    return {int(match.group(1)) for match in CLOSING_RE.finditer(pr_body or "")}


def check(
    *,
    issues: Sequence[IssueRecord | Mapping[str, object]],
    pr_body: str = "",
    require_closing: bool = False,
    followup_issues: Iterable[int] = (),
    repo_root: Path | None = None,
) -> AuditReport:
    """Validate issue evidence and optional PR closing keyword coverage."""

    records: list[IssueRecord] = []
    findings: list[Finding] = []
    for raw_issue in issues:
        try:
            record = _coerce_issue(raw_issue)
        except ValueError as exc:
            findings.append(
                Finding(
                    rule_id="issue_link.invalid-record",
                    severity=Severity.ERROR,
                    message=str(exc),
                )
            )
            continue
        records.append(record)
        findings.extend(_validate_issue(record))

    if not records:
        findings.append(
            Finding(
                rule_id="issue_link.missing",
                severity=Severity.ERROR,
                message="at least one linked issue is required",
            )
        )

    if require_closing:
        closed = closing_issue_numbers(pr_body)
        followups = set(followup_issues)
        for record in records:
            if record.number in closed or record.number in followups:
                continue
            findings.append(
                Finding(
                    rule_id="issue_link.missing-closing-keyword",
                    severity=Severity.ERROR,
                    message="PR body must close every delivered gate issue",
                    evidence={"issue_number": record.number, "closed": sorted(closed)},
                )
            )

    return AuditReport(
        tool="issue_link",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha=_source_sha(repo_root),
        findings=findings,
        summary={
            "issues": [record.number for record in records],
            "closed_issues": sorted(closing_issue_numbers(pr_body)),
            "require_closing": require_closing,
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", type=int, action="append", default=[])
    parser.add_argument("--issue-url", action="append", default=[])
    parser.add_argument("--pr-body", default="")
    parser.add_argument("--require-closing", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    issues = [{"number": number, "url": url} for number, url in zip(args.issue, args.issue_url, strict=False)]
    report = check(
        issues=issues,
        pr_body=args.pr_body,
        require_closing=args.require_closing,
        repo_root=args.repo_root,
    )
    if args.format == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print("issue_link: pass" if not report.findings else "issue_link: fail")
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
