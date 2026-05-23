"""Tests for Issue #1498 gate-record field mutators.

Covers ``issue-add`` / ``issue-update`` / ``issue-remove``,
``admin-label-add`` / ``admin-label-remove``, ``plan-remove`` /
``docs-remove``, and the additive-merge semantics added to ``plan`` and
``docs``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.qa.governance.gate_record.io import _load_record
from scistudio.qa.governance.gate_record.stages import (
    admin_label_add_record,
    admin_label_remove_record,
    docs_record,
    docs_remove_record,
    issue_add_record,
    issue_remove_record,
    issue_update_record,
    plan_record,
    plan_remove_record,
    start_record,
)


@pytest.fixture
def fresh_record(tmp_path: Path) -> Path:
    record_path = start_record(
        repo_root=tmp_path,
        issue_number=42,
        slug="mutator-test",
        task_kind="feature",
        branch="feat/mutator-test",
        owner_directive="test directive",
        include=["src/**"],
        record_path=tmp_path / ".workflow" / "records" / "42-mutator-test.json",
        persona="implementer",
        issue_url="https://example.com/i/42",
    )
    return record_path


# ---------------------------------------------------------------------------
# issue management
# ---------------------------------------------------------------------------


def test_issue_add_appends_new_issue(fresh_record: Path) -> None:
    issue_add_record(fresh_record, number=99, url="https://example.com/i/99")

    record = _load_record(fresh_record)
    assert [issue.number for issue in record.issues] == [42, 99]
    assert record.issues[1].url == "https://example.com/i/99"
    assert record.issues[1].close_in_pr is True


def test_issue_add_rejects_duplicate_number(fresh_record: Path) -> None:
    with pytest.raises(ValueError, match="already linked"):
        issue_add_record(fresh_record, number=42)


def test_issue_add_supports_no_close_in_pr_with_rationale(fresh_record: Path) -> None:
    issue_add_record(
        fresh_record,
        number=100,
        close_in_pr=False,
        followup_rationale="tracked separately in #101",
    )

    record = _load_record(fresh_record)
    assert record.issues[1].close_in_pr is False
    assert record.issues[1].followup_rationale == "tracked separately in #101"


def test_issue_update_sets_url(fresh_record: Path) -> None:
    issue_update_record(fresh_record, number=42, url="https://example.com/i/42/updated")

    record = _load_record(fresh_record)
    assert record.issues[0].url == "https://example.com/i/42/updated"


def test_issue_update_requires_at_least_one_field(fresh_record: Path) -> None:
    with pytest.raises(ValueError, match="at least one of"):
        issue_update_record(fresh_record, number=42)


def test_issue_update_rejects_unknown_number(fresh_record: Path) -> None:
    with pytest.raises(ValueError, match="not linked"):
        issue_update_record(fresh_record, number=9999, url="https://example.com/i/9999")


def test_issue_remove_keeps_record_valid_when_other_issues_remain(fresh_record: Path) -> None:
    issue_add_record(fresh_record, number=99, url="https://example.com/i/99")
    issue_remove_record(fresh_record, number=42, reason="moved to #99")

    record = _load_record(fresh_record)
    assert [issue.number for issue in record.issues] == [99]


def test_issue_remove_rejects_removing_last_issue(fresh_record: Path) -> None:
    with pytest.raises(ValueError, match="last issue"):
        issue_remove_record(fresh_record, number=42, reason="testing")


# ---------------------------------------------------------------------------
# admin labels
# ---------------------------------------------------------------------------


def test_admin_label_add_appends_label(fresh_record: Path) -> None:
    admin_label_add_record(
        fresh_record,
        label="admin-approved:core-change",
        reason="owner authorized",
        approved_by="@owner",
    )

    record = _load_record(fresh_record)
    assert [label.name for label in record.admin_labels] == ["admin-approved:core-change"]
    assert record.admin_labels[0].applied_by == "@owner"
    assert record.admin_labels[0].applied_at is not None


def test_admin_label_add_rejects_invalid_label_name(fresh_record: Path) -> None:
    with pytest.raises(Exception, match="invalid ADR-042 override label"):
        admin_label_add_record(fresh_record, label="not-a-real-label", reason="testing")


def test_admin_label_add_rejects_duplicate(fresh_record: Path) -> None:
    admin_label_add_record(fresh_record, label="admin-approved:core-change", reason="r1")

    with pytest.raises(ValueError, match="already recorded"):
        admin_label_add_record(fresh_record, label="admin-approved:core-change", reason="r2")


def test_admin_label_remove_drops_label(fresh_record: Path) -> None:
    admin_label_add_record(fresh_record, label="admin-approved:core-change", reason="r1")
    admin_label_add_record(fresh_record, label="admin-approved:merge", reason="r2")

    admin_label_remove_record(fresh_record, label="admin-approved:core-change", reason="no longer needed")

    record = _load_record(fresh_record)
    assert [label.name for label in record.admin_labels] == ["admin-approved:merge"]


def test_admin_label_remove_rejects_unknown_label(fresh_record: Path) -> None:
    with pytest.raises(ValueError, match="not recorded"):
        admin_label_remove_record(fresh_record, label="admin-approved:ai-override", reason="testing")


# ---------------------------------------------------------------------------
# plan additive merge + plan-remove
# ---------------------------------------------------------------------------


def test_plan_is_additive_by_default(fresh_record: Path) -> None:
    plan_record(fresh_record, planned_files=["src/a.py"], required_checks=["ruff"])
    plan_record(fresh_record, planned_files=["src/b.py"], required_checks=["mypy"])

    record = _load_record(fresh_record)
    assert record.planned_files == ["src/a.py", "src/b.py"]
    assert record.required_checks == ["ruff", "mypy"]


def test_plan_dedupes_repeated_paths(fresh_record: Path) -> None:
    plan_record(fresh_record, planned_files=["src/a.py"], required_checks=["ruff"])
    plan_record(fresh_record, planned_files=["src/a.py"], required_checks=["ruff"])

    record = _load_record(fresh_record)
    assert record.planned_files == ["src/a.py"]
    assert record.required_checks == ["ruff"]


def test_plan_replace_flag_keeps_destructive_behavior(fresh_record: Path) -> None:
    plan_record(fresh_record, planned_files=["src/a.py"], required_checks=["ruff"])
    plan_record(
        fresh_record,
        planned_files=["src/b.py"],
        required_checks=["mypy"],
        replace=True,
    )

    record = _load_record(fresh_record)
    assert record.planned_files == ["src/b.py"]
    assert record.required_checks == ["mypy"]


def test_plan_remove_drops_specific_entries(fresh_record: Path) -> None:
    plan_record(fresh_record, planned_files=["src/a.py", "src/b.py", "src/c.py"], required_checks=["ruff", "mypy"])
    plan_remove_record(fresh_record, planned_files=["src/b.py"], required_checks=["mypy"])

    record = _load_record(fresh_record)
    assert record.planned_files == ["src/a.py", "src/c.py"]
    assert record.required_checks == ["ruff"]


# ---------------------------------------------------------------------------
# docs additive merge + docs-remove (regression: feedback_gate_record_docs_is_destructive)
# ---------------------------------------------------------------------------


def test_docs_is_additive_by_default(fresh_record: Path) -> None:
    docs_record(fresh_record, updated=["docs/spec/a.md"])
    docs_record(fresh_record, updated=["docs/spec/b.md", "CHANGELOG.md"])

    record = _load_record(fresh_record)
    assert record.docs_landing["docs"]["paths"] == ["docs/spec/a.md", "docs/spec/b.md"]
    assert record.docs_landing["changelog"]["paths"] == ["CHANGELOG.md"]


def test_docs_replace_flag_keeps_destructive_behavior(fresh_record: Path) -> None:
    docs_record(fresh_record, updated=["docs/spec/a.md"])
    docs_record(fresh_record, updated=["docs/spec/b.md"], replace=True)

    record = _load_record(fresh_record)
    assert record.docs_landing["docs"]["paths"] == ["docs/spec/b.md"]


def test_docs_remove_drops_specific_paths(fresh_record: Path) -> None:
    docs_record(fresh_record, updated=["docs/spec/a.md", "docs/spec/b.md", "docs/planning/x.md"])
    docs_remove_record(fresh_record, updated=["docs/spec/a.md"])

    record = _load_record(fresh_record)
    assert record.docs_landing["docs"]["paths"] == ["docs/spec/b.md"]
    assert record.docs_landing["checklist"]["paths"] == ["docs/planning/x.md"]


def test_docs_remove_drops_na_class(fresh_record: Path) -> None:
    docs_record(fresh_record, na=["tests=docs-only PR; no behavior change"])

    record = _load_record(fresh_record)
    assert "not_applicable" in record.docs_landing["tests"]

    docs_remove_record(fresh_record, na=["tests"])

    record = _load_record(fresh_record)
    assert "tests" not in record.docs_landing


# ---------------------------------------------------------------------------
# subcommand surface — the mutator returns the path it wrote so callers can
# print it / hand it off.
# ---------------------------------------------------------------------------


def test_mutators_return_record_path(fresh_record: Path) -> None:
    result = issue_add_record(fresh_record, number=200)
    assert result == fresh_record
