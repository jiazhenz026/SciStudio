from __future__ import annotations

from scieasy.qa.governance.gate_record import CANONICAL_STAGE_ORDER, check_pr, validate_gate_record
from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": "1",
        "task_id": "1267-gate-record-core",
        "task_kind": "feature",
        "branch": "feat/issue-1267/gate-record-core",
        "owner_directive": "Implement ADR-042 Addendum 1 Track B.",
        "issues": [{"number": 1267, "url": "https://github.com/zjzcpj/SciEasy/issues/1267"}],
        "scope": {
            "include": [
                "src/scieasy/qa/governance/gate_record.py",
                "src/scieasy/qa/governance/__init__.py",
                ".workflow/**",
                "tests/qa/test_gate_record*.py",
            ],
            "exclude": ["docs/adr/ADR-042.md"],
        },
        "governance_touch": True,
        "stages": [{"stage": stage.value, "status": "done"} for stage in CANONICAL_STAGE_ORDER],
        "planned_files": ["src/scieasy/qa/governance/gate_record.py"],
        "changed_test_paths": ["tests/qa/test_gate_record_ci.py"],
        "sentrux": {
            "mode": "free-tier",
            "command_or_tool": "sentrux check .",
            "status": "pass",
            "rules_checked": 3,
            "total_rules_defined": 15,
            "pro_required": False,
        },
        "full_audit": {
            "command": "python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json",
            "status": "pass",
            "exit_code": 0,
            "output_path": "docs/audit/full-audit-latest.json",
            "blocks_merge": False,
        },
    }
    record.update(overrides)
    return record


def _changed_files(*extra: str) -> list[str]:
    return [
        "src/scieasy/qa/governance/gate_record.py",
        "tests/qa/test_gate_record_ci.py",
        ".workflow/gate-record.schema.json",
        *extra,
    ]


def test_pr_body_must_close_every_gate_issue() -> None:
    report = check_pr(_record(), changed_files=_changed_files(), pr_body="Refs #1267")

    assert report.blocks_merge
    assert {finding.rule_id for finding in report.findings} == {"gate-record.issue.not-closed"}

    closed = check_pr(_record(), changed_files=_changed_files(), pr_body="Closes #1267")
    assert not closed.blocks_merge


def test_pr_readiness_requires_all_gate_stages_done() -> None:
    stages = [{"stage": stage.value, "status": "done"} for stage in CANONICAL_STAGE_ORDER]
    stages[-1]["status"] = "pending"

    report = check_pr(_record(stages=stages), changed_files=_changed_files(), pr_body="Closes #1267")

    assert report.blocks_merge
    assert "gate-record.stage.not-done" in {finding.rule_id for finding in report.findings}


def test_multiple_issues_must_all_close() -> None:
    record = _record(
        issues=[
            {"number": 1267, "url": "https://github.com/zjzcpj/SciEasy/issues/1267"},
            {"number": 1266, "url": "https://github.com/zjzcpj/SciEasy/issues/1266"},
        ]
    )

    report = check_pr(record, changed_files=_changed_files(), pr_body="Closes #1267")

    assert report.blocks_merge
    assert [finding.message for finding in report.findings] == [
        "PR body must close issue #1266 with Closes, Fixes, or Resolves"
    ]


def test_scope_validation_rejects_files_outside_include_and_inside_exclude() -> None:
    report = validate_gate_record(
        _record(),
        changed_files=_changed_files("docs/adr/ADR-042.md", "src/scieasy/core/secret.py"),
    )

    rule_ids = {finding.rule_id for finding in report.findings}
    assert "gate-record.scope.inside-exclude" in rule_ids
    assert "gate-record.scope.outside-include" in rule_ids


def test_scope_amendment_can_expand_allowed_files() -> None:
    record = _record(amendments=[{"reason": "fixture expansion", "include": ["src/scieasy/core/allowed.py"]}])

    report = validate_gate_record(record, changed_files=_changed_files("src/scieasy/core/allowed.py"))

    assert not report.blocks_merge


def test_implementation_change_requires_changed_test_file() -> None:
    record = _record(changed_test_paths=[])

    report = validate_gate_record(record, changed_files=["src/scieasy/qa/governance/gate_record.py"])

    assert report.blocks_merge
    assert {finding.rule_id for finding in report.findings} == {"gate-record.tests.changed-test-required"}


def test_changed_test_paths_must_be_in_pr_diff() -> None:
    report = validate_gate_record(_record(), changed_files=["src/scieasy/qa/governance/gate_record.py"])

    assert report.blocks_merge
    assert {finding.rule_id for finding in report.findings} == {"gate-record.tests.changed-test-not-in-diff"}


def test_docs_task_without_implementation_files_does_not_require_tests() -> None:
    record = _record(
        task_kind="docs",
        changed_test_paths=[],
        scope={"include": ["docs/**"], "exclude": ["docs/adr/ADR-042.md"]},
        sentrux=None,
    )

    report = validate_gate_record(record, changed_files=["docs/contributing/workflows/human-bypass.md"])

    assert not report.blocks_merge


def test_sentrux_required_for_applicable_changes() -> None:
    record = _record(sentrux=None)

    report = validate_gate_record(record, changed_files=_changed_files())

    assert report.blocks_merge
    assert "gate-record.sentrux.missing" in {finding.rule_id for finding in report.findings}


def test_override_label_vocabulary_is_exact() -> None:
    valid = check_pr(
        _record(),
        changed_files=_changed_files(),
        pr_body="Fixes #1267",
        pr_labels=["human-authored", "admin-approved:core-change"],
    )
    assert not valid.blocks_merge

    invalid = check_pr(
        _record(),
        changed_files=_changed_files(),
        pr_body="Fixes #1267",
        pr_labels=["admin-approved:corechange"],
    )
    assert invalid.blocks_merge
    assert "gate-record.override-label.invalid" in {finding.rule_id for finding in invalid.findings}


def test_guard_reports_are_hard_fail_inputs() -> None:
    guard_report = AuditReport(
        tool="docs_landing",
        status=AuditStatus.FAIL,
        source_sha="fixture",
        findings=[
            Finding(
                rule_id="docs-landing.missing",
                severity=Severity.ERROR,
                file="docs/specs/example.md",
                message="missing docs landing",
            )
        ],
    )

    report = validate_gate_record(_record(), changed_files=_changed_files(), guard_reports=[guard_report])

    assert report.blocks_merge
    assert "gate-record.guard.failed" in {finding.rule_id for finding in report.findings}
