from __future__ import annotations

from scieasy.qa.governance.issue_link import (
    IssueQuery,
    IssueRecord,
    check,
    closing_issue_numbers,
    resolve_or_create,
)
from scieasy.qa.schemas.report import AuditStatus


class FixtureIssueClient:
    def __init__(self, matches: list[IssueRecord] | None = None) -> None:
        self.matches = matches or []
        self.created: list[IssueQuery] = []

    def search_issues(self, query: IssueQuery) -> list[IssueRecord]:
        return self.matches

    def create_issue(self, query: IssueQuery) -> IssueRecord:
        self.created.append(query)
        return IssueRecord(number=77, url="https://github.com/zjzcpj/SciEasy/issues/77")


def test_resolve_or_create_prefers_existing_issue() -> None:
    client = FixtureIssueClient([IssueRecord(number=42, url="https://github.com/zjzcpj/SciEasy/issues/42")])

    record = resolve_or_create(IssueQuery(title="gate work"), client=client, create_if_missing=True)

    assert record.number == 42
    assert client.created == []


def test_resolve_or_create_can_use_fixture_create_client() -> None:
    client = FixtureIssueClient()

    record = resolve_or_create(IssueQuery(title="gate work"), client=client, create_if_missing=True)

    assert record.number == 77
    assert [query.title for query in client.created] == ["gate work"]


def test_check_requires_pr_body_closing_keywords() -> None:
    report = check(
        issues=[{"number": 1271, "url": "https://github.com/zjzcpj/SciEasy/issues/1271"}],
        pr_body="Refs #1271",
        require_closing=True,
    )

    assert report.status == AuditStatus.FAIL
    assert "issue_link.missing-closing-keyword" in {finding.rule_id for finding in report.findings}


def test_check_accepts_closing_keywords_for_multiple_issues() -> None:
    report = check(
        issues=[
            {"number": 1271, "url": "https://github.com/zjzcpj/SciEasy/issues/1271"},
            {"number": 1266, "url": "https://github.com/zjzcpj/SciEasy/issues/1266"},
        ],
        pr_body="Closes #1271\nFixes https://github.com/zjzcpj/SciEasy/issues/1266",
        require_closing=True,
    )

    assert report.status == AuditStatus.PASS
    assert closing_issue_numbers("Resolves #10 and closes #11") == {10, 11}


def test_check_rejects_mismatched_issue_url() -> None:
    report = check(
        issues=[{"number": 1271, "url": "https://github.com/zjzcpj/SciEasy/issues/1266"}],
        require_closing=False,
    )

    assert report.status == AuditStatus.FAIL
    assert "issue_link.url-number-mismatch" in {finding.rule_id for finding in report.findings}
