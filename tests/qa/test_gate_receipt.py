from __future__ import annotations

import json
from pathlib import Path

import pytest

import scistudio.qa.governance.gate_receipt as gate_receipt
from scistudio.qa.governance.gate_receipt import (
    EMPTY_SHA256,
    CandidateFingerprint,
    infer_required_checks,
    receipt_paths,
    validate_receipt,
)


def _record(path: Path, *, required_checks: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "task_id": "1492-local-receipts",
                "task_kind": "maintenance",
                "persona": "implementer",
                "branch": "feat/local-receipts",
                "owner_directive": "test",
                "issues": [{"number": 1492, "url": "https://github.com/zjzcpj/SciStudio/issues/1492"}],
                "scope": {"include": ["src/**"], "exclude": []},
                "governance_touch": True,
                "stages": [
                    {"stage": "scope_and_issue", "status": "done"},
                    {"stage": "plan", "status": "done"},
                    {"stage": "implement", "status": "done"},
                    {"stage": "update_docs", "status": "done"},
                    {"stage": "test_and_checks", "status": "done"},
                    {"stage": "commit_and_submit_pr", "status": "pending"},
                ],
                "required_checks": required_checks,
            }
        ),
        encoding="utf-8",
    )


def _candidate() -> CandidateFingerprint:
    return CandidateFingerprint(
        base="origin/main",
        head="HEAD",
        head_sha="abc123",
        branch="feat/local-receipts",
        changed_files=("src/scistudio/qa/governance/gate_receipt.py",),
        diff_sha256="diff",
        gate_record_sha256="record",
        pr_body_sha256=EMPTY_SHA256,
    )


def test_infer_required_checks_combines_gate_record_and_diff() -> None:
    checks = infer_required_checks(
        ["src/scistudio/qa/governance/gate_receipt.py", "docs/specs/adr-042-local-gate-receipts.md"],
        gate_required=["pytest-governance"],
    )

    assert {
        "ruff",
        "format",
        "mypy",
        "full_audit",
        "gate_record_pre_push",
        "frontmatter_lint",
        "pytest-governance",
    } <= checks


def test_validate_receipt_rejects_missing_required_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = tmp_path / "record.json"
    _record(record, required_checks=["ruff"])
    candidate = _candidate()
    receipt_dir = tmp_path / ".workflow" / "local" / "gate-receipts"
    receipt_dir.mkdir(parents=True)
    receipt, _ = receipt_paths(
        tmp_path, head_sha=candidate.head_sha, pr_body_sha256=candidate.pr_body_sha256, receipt_dir=receipt_dir
    )
    receipt.write_text(
        json.dumps({"schema_version": "1", "candidate": candidate.to_json(), "checks": []}),
        encoding="utf-8",
    )

    def fake_build_candidate(*args: object, **kwargs: object) -> CandidateFingerprint:
        return candidate

    monkeypatch.setattr(gate_receipt, "build_candidate", fake_build_candidate)

    ok, errors = validate_receipt(tmp_path, gate_record=record, receipt_dir=receipt_dir)

    assert not ok
    assert any("missing gate receipt check: ruff" in error for error in errors)


def test_validate_receipt_rejects_stale_fingerprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = tmp_path / "record.json"
    _record(record, required_checks=[])
    candidate = _candidate()
    receipt_dir = tmp_path / ".workflow" / "local" / "gate-receipts"
    receipt_dir.mkdir(parents=True)
    stale = candidate.to_json()
    stale["diff_sha256"] = "old"
    receipt, _ = receipt_paths(
        tmp_path, head_sha=candidate.head_sha, pr_body_sha256=candidate.pr_body_sha256, receipt_dir=receipt_dir
    )
    receipt.write_text(
        json.dumps({"schema_version": "1", "candidate": stale, "checks": []}),
        encoding="utf-8",
    )

    def fake_build_candidate(*args: object, **kwargs: object) -> CandidateFingerprint:
        return candidate

    monkeypatch.setattr(gate_receipt, "build_candidate", fake_build_candidate)

    ok, errors = validate_receipt(tmp_path, gate_record=record, receipt_dir=receipt_dir)

    assert not ok
    assert "fingerprint does not match" in "\n".join(errors)
