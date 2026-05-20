from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scieasy.qa.governance.gate_record import (
    CANONICAL_STAGE_ORDER,
    CheckEvidence,
    GateRecord,
    GateStage,
    SentruxEvidence,
    check_commit_msg,
    main,
    validate_gate_record,
)


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": "1",
        "record_path": ".workflow/records/1267-gate-record-core.json",
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
        "changed_test_paths": ["tests/qa/test_gate_record.py"],
        "admin_labels": [{"name": "admin-approved:core-change", "applied_by": "@owner"}],
        "required_checks": ["ruff", "pytest", "full_audit", "sentrux"],
        "check_results": [
            {
                "name": "pytest",
                "command_or_tool": "pytest tests/qa/test_gate_record.py",
                "status": "pass",
                "exit_code": 0,
            }
        ],
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


def test_gate_record_accepts_canonical_six_stage_model() -> None:
    record = GateRecord.model_validate(_record())

    assert record.stages[0].stage is GateStage.SCOPE_AND_ISSUE
    assert record.stages[-1].stage is GateStage.COMMIT_AND_SUBMIT_PR
    assert record.admin_labels[0].name == "admin-approved:core-change"


def test_gate_record_rejects_missing_or_reordered_stage() -> None:
    data = _record(stages=[{"stage": GateStage.PLAN.value, "status": "done"}])

    try:
        GateRecord.model_validate(data)
    except ValidationError as exc:
        assert "six ADR-042 Addendum 1 stages" in str(exc)
    else:  # pragma: no cover - explicit assertion path
        raise AssertionError("GateRecord accepted an invalid stage sequence")


def test_sentrux_evidence_rejects_pro_required_claims() -> None:
    with pytest.raises(ValidationError, match="pro_required"):
        SentruxEvidence.model_validate(
            {
                "mode": "free-tier",
                "command_or_tool": "sentrux check .",
                "status": "pass",
                "pro_required": True,
            }
        )


def test_sentrux_evidence_rejects_impossible_rule_counts() -> None:
    with pytest.raises(ValidationError, match="rules_checked cannot exceed total_rules_defined"):
        SentruxEvidence.model_validate(
            {
                "mode": "free-tier",
                "command_or_tool": "sentrux check .",
                "status": "pass",
                "rules_checked": 4,
                "total_rules_defined": 3,
                "pro_required": False,
            }
        )


def test_full_audit_known_debt_is_allowed_but_unclassified_failures_block() -> None:
    known_debt = _record(
        full_audit={
            "command": "python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json",
            "status": "fail",
            "exit_code": 1,
            "output_path": "docs/audit/full-audit-latest.json",
            "blocks_merge": True,
            "known_debt": ["frontmatter legacy backlog"],
        }
    )
    assert not validate_gate_record(known_debt).blocks_merge

    unclassified = _record(
        full_audit={
            "command": "python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json",
            "status": "fail",
            "exit_code": 1,
            "output_path": "docs/audit/full-audit-latest.json",
            "blocks_merge": True,
            "unclassified_failures": ["new doc drift"],
        }
    )
    report = validate_gate_record(unclassified)
    assert report.blocks_merge
    assert {finding.rule_id for finding in report.findings} == {
        "gate-record.full-audit.unclassified-failures",
        "gate-record.full-audit.unclassified-fail-status",
    }


def test_check_evidence_rejects_passing_nonzero_exit_code() -> None:
    with pytest.raises(ValidationError, match="passing checks cannot record a non-zero exit_code"):
        CheckEvidence.model_validate(
            {
                "name": "ruff",
                "command_or_tool": "ruff check .",
                "status": "pass",
                "exit_code": 1,
            }
        )


def test_check_commit_msg_requires_adr042_trailers() -> None:
    report = check_commit_msg(
        """feat(#1267): add gate record core

Gate-Record: .workflow/records/1267-gate-record-core.json
Task-Kind: feature
Issue: #1267
Assisted-by: Codex:gpt-5
"""
    )
    assert not report.blocks_merge

    missing = check_commit_msg("feat: no trailers\n")
    assert missing.blocks_merge
    assert "Gate-Record" in {finding.message.rsplit(" ", 1)[-1] for finding in missing.findings}


def test_ai_facing_cli_records_canonical_workflow(tmp_path: Path) -> None:
    record_path = tmp_path / ".workflow" / "records" / "1267-gate-record-core.json"

    assert (
        main(
            [
                "start",
                "--repo-root",
                str(tmp_path),
                "--issue",
                "1267",
                "--issue-url",
                "https://github.com/zjzcpj/SciEasy/issues/1267",
                "--slug",
                "Gate Record Core",
                "--task-kind",
                "feature",
                "--branch",
                "feat/issue-1267/gate-record-core",
                "--owner-directive",
                "Implement ADR-042 Addendum 1 Track B.",
                "--include",
                "src/scieasy/qa/governance/**",
                "--include",
                "tests/qa/test_gate_record*.py",
                "--governance-touch",
                "--record",
                str(record_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "plan",
                "--record",
                str(record_path),
                "--planned-file",
                "src/scieasy/qa/governance/gate_record.py",
                "--required-check",
                "ruff check .",
                "--changed-test-path",
                "tests/qa/test_gate_record.py",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "docs",
                "--record",
                str(record_path),
                "--updated",
                "docs/specs/adr-042-addendum1-gate-record-implementation.md",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "amend",
                "--record",
                str(record_path),
                "--reason",
                "Implementation confirmed within planned scope.",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "check",
                "--record",
                str(record_path),
                "--name",
                "pytest",
                "--command-or-tool",
                "pytest tests/qa/test_gate_record.py --timeout=60",
                "--status",
                "pass",
                "--exit-code",
                "0",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "check",
                "--record",
                str(record_path),
                "--full-audit",
                "--command-or-tool",
                "python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json",
                "--status",
                "pass",
                "--exit-code",
                "0",
                "--output-path",
                "docs/audit/full-audit-latest.json",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "sentrux",
                "--record",
                str(record_path),
                "--command-or-tool",
                "sentrux mcp check-rules",
                "--status",
                "pass",
                "--rules-checked",
                "3",
                "--total-rules-defined",
                "15",
                "--threshold",
                "max_cycles=0",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "finalize",
                "--record",
                str(record_path),
                "--commit-sha",
                "abc1234",
                "--pr-number",
                "1276",
                "--pr-url",
                "https://github.com/zjzcpj/SciEasy/pull/1276",
                "--body-closes-issue",
                "1267",
            ]
        )
        == 0
    )

    payload = json.loads(record_path.read_text(encoding="utf-8"))
    record = GateRecord.model_validate(payload)
    assert [stage.status for stage in record.stages] == ["done", "done", "done", "done", "done", "done"]
    assert record.record_path == ".workflow/records/1267-gate-record-core.json"
    assert record.full_audit is not None
    assert record.sentrux is not None
    assert record.commit is not None
