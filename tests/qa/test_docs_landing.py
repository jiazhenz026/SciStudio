from __future__ import annotations

from scistudio.qa.governance.docs_landing import check
from scistudio.qa.schemas.report import AuditStatus


def test_docs_landing_blocks_governed_change_without_evidence() -> None:
    report = check(changed_files=["src/scistudio/qa/governance/issue_link.py"], docs_landing={})

    assert report.status == AuditStatus.FAIL
    assert {
        "docs_landing.missing-docs",
        "docs_landing.missing-changelog",
        "docs_landing.missing-checklist",
    } <= {finding.rule_id for finding in report.findings}


def test_docs_landing_accepts_paths_and_na_rationales() -> None:
    report = check(
        changed_files=["src/scistudio/qa/governance/issue_link.py"],
        docs_landing={
            "docs": {"paths": ["docs/specs/adr-042-gate-record-sentrux-workflow.md"]},
            "changelog": {"not_applicable": True, "rationale": "N/A: internal guard rollout"},
            "checklist": {"paths": ["docs/planning/adr-042-addendum1-implementation-checklist.md"]},
        },
    )

    assert report.status == AuditStatus.PASS


def test_docs_landing_does_not_require_evidence_for_unrelated_docs_only_change() -> None:
    report = check(changed_files=["docs/user/guide.md"], docs_landing={})

    assert report.status == AuditStatus.PASS
    assert report.summary["required"] == []
