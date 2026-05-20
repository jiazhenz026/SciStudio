from __future__ import annotations

from scieasy.qa.governance.human_bypass_guard import VALID_OVERRIDE_LABELS, check
from scieasy.qa.schemas.report import AuditStatus


def _pr(*, labels: list[str], permission: str = "admin", has_ai_evidence: bool = False) -> dict[str, object]:
    return {
        "labels": labels,
        "label_events": [{"label": label, "actor": "maintainer", "permission": permission} for label in labels],
        "has_ai_evidence": has_ai_evidence,
    }


def test_valid_override_label_vocabulary_is_exact() -> None:
    assert {
        "human-authored",
        "admin-approved:ai-override",
        "admin-approved:core-change",
        "admin-approved:merge",
    } == VALID_OVERRIDE_LABELS


def test_human_authored_label_skips_ai_only_gates_for_human_pr() -> None:
    report = check(pr=_pr(labels=["human-authored"]))

    assert report.status == AuditStatus.PASS
    assert report.summary["bypass_status"] == "skipped-human"


def test_human_authored_label_requires_authorized_provenance() -> None:
    report = check(pr=_pr(labels=["human-authored"], permission="write"))

    assert report.status == AuditStatus.FAIL
    assert "human_bypass_guard.unauthorized-label" in {finding.rule_id for finding in report.findings}


def test_human_authored_does_not_hide_ai_evidence_without_admin_override() -> None:
    report = check(pr=_pr(labels=["human-authored"], has_ai_evidence=True))

    assert report.status == AuditStatus.FAIL
    assert "human_bypass_guard.ai-evidence-needs-admin-override" in {finding.rule_id for finding in report.findings}


def test_ai_override_allows_ai_evidence_when_authorized() -> None:
    report = check(pr=_pr(labels=["human-authored", "admin-approved:ai-override"], has_ai_evidence=True))

    assert report.status == AuditStatus.PASS
    assert report.summary["bypass_status"] == "admin-ai-override"


def test_invalid_override_label_is_rejected() -> None:
    report = check(pr=_pr(labels=["admin-approved:corechange"]))

    assert report.status == AuditStatus.FAIL
    assert "human_bypass_guard.invalid-override-label" in {finding.rule_id for finding in report.findings}
