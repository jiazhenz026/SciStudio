"""Per-stage mutators for ADR-042 gate records.

One mutator per gate-record subcommand: ``start``, ``plan``, ``amend``,
``docs``, ``check``, ``sentrux``, ``finalize``. Each mutator loads the
record, applies the stage-specific update, marks the corresponding
``GateStage`` as ``done``, and writes the record back to disk.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, cast

from scistudio.qa.governance.gate_record.io import (
    _load_record,
    _mark_stage,
    _parse_key_values,
    _record_path,
    _slugify,
    _upsert_check,
    _write_record,
)
from scistudio.qa.governance.gate_record.models import (
    CANONICAL_STAGE_ORDER,
    CheckEvidence,
    CommitEvidence,
    FullAuditEvidence,
    GateRecord,
    GateStage,
    PullRequestEvidence,
    ScopeAmendment,
    SentruxEvidence,
)
from scistudio.qa.governance.gate_record.paths import _normalize_path


def start_record(
    *,
    repo_root: Path,
    issue_number: int,
    slug: str,
    task_kind: str,
    branch: str,
    owner_directive: str,
    include: Sequence[str],
    exclude: Sequence[str] = (),
    issue_url: str | None = None,
    governance_touch: bool = False,
    record_path: Path | None = None,
    persona: str | None = None,
) -> Path:
    """Create or deterministically replace a committed gate record."""

    path = _record_path(repo_root, issue_number, slug, record_path)
    rel_path = _normalize_path(str(path.relative_to(repo_root))) if path.is_relative_to(repo_root) else str(path)
    record = GateRecord.model_validate(
        {
            "schema_version": "1",
            "record_path": rel_path,
            "task_id": f"{issue_number}-{_slugify(slug)}",
            "task_kind": task_kind,
            "persona": persona or "implementer",
            "branch": branch,
            "owner_directive": owner_directive,
            "issues": [{"number": issue_number, "url": issue_url}],
            "scope": {"include": list(include), "exclude": list(exclude)},
            "governance_touch": governance_touch,
            "stages": [
                {
                    "stage": stage.value,
                    "status": "done" if stage == GateStage.SCOPE_AND_ISSUE else "pending",
                }
                for stage in CANONICAL_STAGE_ORDER
            ],
        }
    )
    return _write_record(path, record)


def plan_record(
    record_path: Path,
    *,
    planned_files: Sequence[str] = (),
    required_checks: Sequence[str] = (),
    changed_test_paths: Sequence[str] = (),
) -> Path:
    """Update the Plan stage of a gate record."""

    record = _load_record(record_path)
    record.planned_files = [_normalize_path(path) for path in planned_files]
    record.required_checks = list(required_checks)
    record.changed_test_paths = [_normalize_path(path) for path in changed_test_paths]
    _mark_stage(record, GateStage.PLAN)
    return _write_record(record_path, record)


def amend_record(
    record_path: Path,
    *,
    reason: str,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    approved_by: str | None = None,
    governance_touch: bool | None = None,
) -> Path:
    """Append a scope amendment.

    When ``governance_touch`` is ``True``, flip the record's
    ``governance_touch`` flag to ``True``. Passing ``None`` leaves the existing
    value untouched. This exists because real governance touches can become
    known only after ``start`` (the original CLI gap that #1340 surfaced —
    editing governance code under an in-flight gate record left no clean way
    to certify ``governance_touch=true`` other than recreating the record).
    """

    record = _load_record(record_path)
    record.amendments.append(
        ScopeAmendment(reason=reason, include=list(include), exclude=list(exclude), approved_by=approved_by)
    )
    if governance_touch is True:
        record.governance_touch = True
    _mark_stage(record, GateStage.IMPLEMENT)
    return _write_record(record_path, record)


_CHANGELOG_PATHS: frozenset[str] = frozenset({"CHANGELOG.md"})
"""Repo-relative paths that credit the gate record's ``changelog`` landing
class. Previously the routing logic only knew about ``docs/`` and
``docs/planning/`` prefixes, so passing ``--updated CHANGELOG.md`` silently
routed it into the ``docs`` class and left ``changelog`` empty — every PR
that genuinely updated the changelog still failed ``docs_landing.missing-
changelog`` and had to either N/A the changelog (untruthful) or use
``admin-approved:ai-override`` to bypass the whole workflow gate (#1362)."""


def docs_record(
    record_path: Path,
    *,
    updated: Sequence[str] = (),
    na: Sequence[str] = (),
) -> Path:
    """Record documentation landing evidence."""

    record = _load_record(record_path)
    na_rationales = dict(_parse_key_values(na))
    normalised = [_normalize_path(path) for path in updated]
    changelog_paths = [path for path in normalised if path in _CHANGELOG_PATHS]
    checklist_paths = [path for path in normalised if path.startswith("docs/planning/")]
    docs_paths = [path for path in normalised if path not in _CHANGELOG_PATHS and not path.startswith("docs/planning/")]
    landing: dict[str, Any] = {
        "docs": {"paths": docs_paths} if docs_paths else {},
        "checklist": {"paths": checklist_paths} if checklist_paths else {},
        "changelog": {"paths": changelog_paths} if changelog_paths else {},
    }
    for class_name, rationale in na_rationales.items():
        landing[class_name] = {"not_applicable": True, "rationale": rationale}
    record.docs_landing = landing
    _mark_stage(record, GateStage.UPDATE_DOCS)
    return _write_record(record_path, record)


def check_record(
    record_path: Path,
    *,
    name: str,
    command_or_tool: str,
    status: str,
    exit_code: int | None = None,
    output_path: str | None = None,
    full_audit: bool = False,
    blocks_merge: bool | None = None,
    known_debt: Sequence[str] = (),
    unclassified_failure: Sequence[str] = (),
) -> Path:
    """Record a command result or ADR-042 full-audit evidence."""

    record = _load_record(record_path)
    if full_audit:
        if output_path is None:
            raise ValueError("--output-path is required for --full-audit")
        record.full_audit = FullAuditEvidence(
            command=command_or_tool,
            status=cast(Literal["pass", "fail", "skipped", "unknown"], status),
            exit_code=exit_code,
            output_path=output_path,
            blocks_merge=blocks_merge,
            known_debt=list(known_debt),
            unclassified_failures=list(unclassified_failure),
        )
    else:
        _upsert_check(
            record,
            CheckEvidence(
                name=name,
                command_or_tool=command_or_tool,
                status=cast(Literal["pass", "fail", "skipped", "unknown"], status),
                exit_code=exit_code,
                output_path=output_path,
            ),
        )
    _mark_stage(record, GateStage.TEST_AND_CHECKS)
    return _write_record(record_path, record)


def sentrux_record(
    record_path: Path,
    *,
    command_or_tool: str,
    status: str,
    rules_checked: int | None = None,
    total_rules_defined: int | None = None,
    quality_signal: float | None = None,
    threshold: Sequence[str] = (),
    output_path: str | None = None,
) -> Path:
    """Record Sentrux free-tier evidence."""

    record = _load_record(record_path)
    record.sentrux = SentruxEvidence(
        mode="free-tier",
        command_or_tool=command_or_tool,
        status=cast(Literal["pass", "fail", "skipped", "unknown"], status),
        rules_checked=rules_checked,
        total_rules_defined=total_rules_defined,
        quality_signal=quality_signal,
        thresholds=dict(_parse_key_values(threshold)),
        pro_required=False,
        output_path=output_path,
    )
    _mark_stage(record, GateStage.TEST_AND_CHECKS)
    return _write_record(record_path, record)


def finalize_record(
    record_path: Path,
    *,
    commit_sha: Sequence[str] = (),
    pr_number: int | None = None,
    pr_url: str | None = None,
    body_closes_issue: Sequence[int] = (),
) -> Path:
    """Record final commit and PR provenance."""

    record = _load_record(record_path)
    rel_path = record.record_path or _normalize_path(str(record_path))
    record.commit = CommitEvidence(shas=list(commit_sha), gate_record_path=rel_path)
    record.pull_request = PullRequestEvidence(
        number=pr_number,
        url=pr_url,
        body_closes_issues=list(body_closes_issue),
    )
    _mark_stage(record, GateStage.COMMIT_AND_SUBMIT_PR)
    return _write_record(record_path, record)
