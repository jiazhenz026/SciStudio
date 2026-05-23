"""Tests for Issue #1498 provenance audit log + tamper detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.qa.governance.gate_record.io import (
    _load_record,
    _record_content_hash,
    _record_mutation,
    verify_provenance_hash,
)
from scistudio.qa.governance.gate_record.stages import (
    admin_label_add_record,
    amend_record,
    docs_record,
    issue_add_record,
    plan_record,
    provenance_rebuild_record,
    start_record,
)
from scistudio.qa.governance.gate_record.validation import validate_gate_record


@pytest.fixture
def fresh_record(tmp_path: Path) -> Path:
    return start_record(
        repo_root=tmp_path,
        issue_number=42,
        slug="provenance-test",
        task_kind="feature",
        branch="feat/provenance-test",
        owner_directive="test",
        include=["src/**"],
        record_path=tmp_path / ".workflow" / "records" / "42-provenance-test.json",
        persona="implementer",
        issue_url="https://example.com/i/42",
    )


# ---------------------------------------------------------------------------
# initial provenance after start
# ---------------------------------------------------------------------------


def test_start_initializes_provenance_with_start_mutation(fresh_record: Path) -> None:
    record = _load_record(fresh_record)

    assert record.provenance is not None
    assert len(record.provenance.mutations) == 1
    assert record.provenance.mutations[0].subcommand == "start"
    assert record.provenance.mutations[0].content_hash_before is None
    assert record.provenance.mutations[0].content_hash_after == record.provenance.head_content_hash
    assert "issue" in dict(record.provenance.mutations[0].summary)


def test_start_summary_records_essential_context(fresh_record: Path) -> None:
    record = _load_record(fresh_record)

    summary = dict(record.provenance.mutations[0].summary)
    assert summary["task_kind"] == "feature"
    assert summary["persona"] == "implementer"
    assert summary["branch"] == "feat/provenance-test"
    assert summary["governance_touch"] is False


# ---------------------------------------------------------------------------
# every mutator appends to provenance
# ---------------------------------------------------------------------------


def test_amend_appends_mutation(fresh_record: Path) -> None:
    amend_record(fresh_record, reason="add helper module", include=["src/helpers/**"])

    record = _load_record(fresh_record)
    assert len(record.provenance.mutations) == 2
    assert record.provenance.mutations[1].subcommand == "amend"


def test_plan_appends_mutation(fresh_record: Path) -> None:
    plan_record(fresh_record, planned_files=["src/a.py"], required_checks=["ruff"])

    record = _load_record(fresh_record)
    assert record.provenance.mutations[-1].subcommand == "plan"


def test_docs_appends_mutation(fresh_record: Path) -> None:
    docs_record(fresh_record, updated=["docs/spec/a.md"])

    record = _load_record(fresh_record)
    assert record.provenance.mutations[-1].subcommand == "docs"


def test_issue_add_appends_mutation(fresh_record: Path) -> None:
    issue_add_record(fresh_record, number=99)

    record = _load_record(fresh_record)
    assert record.provenance.mutations[-1].subcommand == "issue-add"


def test_admin_label_add_appends_mutation(fresh_record: Path) -> None:
    admin_label_add_record(fresh_record, label="admin-approved:core-change", reason="testing")

    record = _load_record(fresh_record)
    assert record.provenance.mutations[-1].subcommand == "admin-label-add"


def test_each_mutation_chains_to_previous_content_hash(fresh_record: Path) -> None:
    issue_add_record(fresh_record, number=99)
    plan_record(fresh_record, planned_files=["src/a.py"], required_checks=["ruff"])

    record = _load_record(fresh_record)
    mutations = record.provenance.mutations
    assert mutations[1].content_hash_before == mutations[0].content_hash_after
    assert mutations[2].content_hash_before == mutations[1].content_hash_after


# ---------------------------------------------------------------------------
# verify_provenance_hash: detect direct edits
# ---------------------------------------------------------------------------


def test_verify_passes_when_record_is_untouched(fresh_record: Path) -> None:
    record = _load_record(fresh_record)

    is_valid, _ = verify_provenance_hash(record)

    assert is_valid is True


def test_verify_detects_direct_json_edit(fresh_record: Path) -> None:
    payload = json.loads(fresh_record.read_text(encoding="utf-8"))
    payload["governance_touch"] = True  # mimic the smell PR #1497 hit
    fresh_record.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    record = _load_record(fresh_record)
    is_valid, computed = verify_provenance_hash(record)

    assert is_valid is False
    assert computed != record.provenance.head_content_hash


def test_verify_skips_records_without_provenance(tmp_path: Path) -> None:
    """Pre-Issue-#1498 records load without a provenance field; treat as
    not-yet-protected (verify returns True for backward compat)."""

    payload = {
        "schema_version": "1",
        "record_path": ".workflow/records/1-legacy.json",
        "task_id": "1-legacy",
        "task_kind": "feature",
        "persona": "implementer",
        "branch": "feat/legacy",
        "owner_directive": "legacy",
        "issues": [{"number": 1, "url": "https://example.com/i/1"}],
        "scope": {"include": ["src/**"], "exclude": []},
        "governance_touch": False,
        "stages": [
            {"stage": "scope_and_issue", "status": "done"},
            {"stage": "plan", "status": "pending"},
            {"stage": "implement", "status": "pending"},
            {"stage": "update_docs", "status": "pending"},
            {"stage": "test_and_checks", "status": "pending"},
            {"stage": "commit_and_submit_pr", "status": "pending"},
        ],
    }
    legacy_path = tmp_path / "legacy.json"
    legacy_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    record = _load_record(legacy_path)
    is_valid, _ = verify_provenance_hash(record)

    assert is_valid is True
    assert record.provenance is None


# ---------------------------------------------------------------------------
# provenance-rebuild
# ---------------------------------------------------------------------------


def test_provenance_rebuild_reanchors_hash(fresh_record: Path) -> None:
    payload = json.loads(fresh_record.read_text(encoding="utf-8"))
    payload["governance_touch"] = True
    fresh_record.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    provenance_rebuild_record(fresh_record, reason="legitimate migration", approved_by="@owner")

    record = _load_record(fresh_record)
    is_valid, _ = verify_provenance_hash(record)

    assert is_valid is True
    assert record.provenance.mutations[-1].subcommand == "provenance-rebuild"
    assert dict(record.provenance.mutations[-1].summary) == {
        "reason": "legitimate migration",
        "approved_by": "@owner",
    }


# ---------------------------------------------------------------------------
# validators report tampering via validate_gate_record
# ---------------------------------------------------------------------------


def test_validate_gate_record_reports_tampered_finding(fresh_record: Path) -> None:
    payload = json.loads(fresh_record.read_text(encoding="utf-8"))
    payload["governance_touch"] = True
    fresh_record.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = validate_gate_record(fresh_record, require_final_evidence=False)

    assert any(finding.rule_id == "gate-record.provenance.tampered" for finding in report.findings)


def test_validate_gate_record_passes_provenance_check_after_rebuild(fresh_record: Path) -> None:
    payload = json.loads(fresh_record.read_text(encoding="utf-8"))
    payload["governance_touch"] = True
    fresh_record.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    provenance_rebuild_record(fresh_record, reason="legitimate migration")

    report = validate_gate_record(fresh_record, require_final_evidence=False)

    assert not any(finding.rule_id == "gate-record.provenance.tampered" for finding in report.findings)


# ---------------------------------------------------------------------------
# content_hash excludes provenance to avoid self-reference
# ---------------------------------------------------------------------------


def test_content_hash_does_not_depend_on_provenance_itself(fresh_record: Path) -> None:
    record = _load_record(fresh_record)
    hash_before = _record_content_hash(record)

    # Simulate a fresh mutation: append a fake mutation entry to provenance.
    _record_mutation(record, subcommand="test-marker", summary={"intent": "verify hash isolation"})

    hash_after = _record_content_hash(record)

    # _record_content_hash excludes provenance, so adding a mutation should
    # NOT change the computed hash (the only field that changed is inside
    # provenance, which is excluded).
    assert hash_before == hash_after
