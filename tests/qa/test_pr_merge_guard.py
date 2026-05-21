from __future__ import annotations

from scistudio.qa.governance.pr_merge_guard import check
from scistudio.qa.schemas.report import AuditStatus


def _pr(label: str, permission: str = "admin") -> dict[str, object]:
    return {
        "labels": [label],
        "label_events": [{"label": label, "actor": "maintainer", "permission": permission}],
    }


def test_pr_merge_guard_blocks_ai_merge_without_label() -> None:
    report = check(pr={}, actor={"is_ai": True}, intent="merge")

    assert report.status == AuditStatus.FAIL
    assert "pr_merge_guard.missing-admin-merge-approval" in {finding.rule_id for finding in report.findings}


def test_pr_merge_guard_accepts_authorized_merge_label() -> None:
    report = check(pr=_pr("admin-approved:merge"), actor={"is_ai": True}, intent="squash")

    assert report.status == AuditStatus.PASS
    assert report.summary["approved"] is True


def test_pr_merge_guard_rejects_unauthorized_merge_label() -> None:
    report = check(pr=_pr("admin-approved:merge", permission="write"), actor={"is_ai": True}, intent="merge")

    assert report.status == AuditStatus.FAIL


def test_pr_merge_guard_ignores_non_merge_intent() -> None:
    report = check(pr={}, actor={"is_ai": True}, intent="comment")

    assert report.status == AuditStatus.PASS
    assert report.summary["needs_approval"] is False
