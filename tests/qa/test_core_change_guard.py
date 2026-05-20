from __future__ import annotations

from scieasy.qa.governance.core_change_guard import check
from scieasy.qa.schemas.report import AuditStatus


def _pr(label: str, permission: str = "admin") -> dict[str, object]:
    return {
        "labels": [label],
        "label_events": [{"label": label, "actor": "maintainer", "permission": permission}],
    }


def test_core_change_guard_passes_unprotected_files() -> None:
    report = check(changed_files=["docs/user/guide.md"], pr={})

    assert report.status == AuditStatus.PASS
    assert report.summary["protected_files"] == []


def test_core_change_guard_blocks_protected_core_without_approval() -> None:
    report = check(changed_files=["src/scieasy/core/runtime.py"], pr={})

    assert report.status == AuditStatus.FAIL
    assert "core_change_guard.missing-admin-approval" in {finding.rule_id for finding in report.findings}


def test_core_change_guard_accepts_authorized_core_change_label() -> None:
    report = check(
        changed_files=["src/scieasy/qa/governance/human_bypass_guard.py"],
        pr=_pr("admin-approved:core-change"),
    )

    assert report.status == AuditStatus.PASS
    assert report.summary["approved"] is True


def test_core_change_guard_rejects_misspelled_or_unauthorized_label() -> None:
    report = check(
        changed_files=["src/scieasy/qa/governance/human_bypass_guard.py"],
        pr=_pr("admin-approved:corechange"),
    )

    assert report.status == AuditStatus.FAIL


def test_core_change_guard_accepts_admin_approval_review() -> None:
    report = check(
        changed_files=["src/scieasy/workflow/graph.py"],
        pr={"reviews": [{"state": "APPROVED", "actor": "owner", "permission": "maintain"}]},
    )

    assert report.status == AuditStatus.PASS
