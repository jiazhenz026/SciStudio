"""Per-stage mutators for ADR-042 gate records.

One mutator per gate-record subcommand. Two groups:

* Phase mutators (``start``, ``plan``, ``amend``, ``docs``, ``check``,
  ``sentrux``, ``finalize``) — record per-stage evidence and mark the
  matching ``GateStage`` as ``done``.
* Field mutators (Issue #1498: ``issue_add`` / ``issue_update`` /
  ``issue_remove``, ``admin_label_add`` / ``admin_label_remove``,
  ``plan_remove`` / ``docs_remove``, ``provenance_rebuild``) — modify
  individual record fields without advancing a stage.

Each mutator loads the record, applies the change, calls
:func:`_record_mutation` to append a provenance entry (Issue #1498), and
writes the record back to disk via :func:`_write_record`.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from scistudio.qa.governance.gate_record.io import (
    _load_record,
    _mark_stage,
    _parse_key_values,
    _record_mutation,
    _record_path,
    _slugify,
    _upsert_check,
    _write_record,
)
from scistudio.qa.governance.gate_record.models import (
    CANONICAL_STAGE_ORDER,
    AdminLabelEvidence,
    CheckEvidence,
    CommitEvidence,
    FullAuditEvidence,
    GateRecord,
    GateStage,
    IssueRef,
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
    _record_mutation(
        record,
        subcommand="start",
        summary={
            "issue": issue_number,
            "task_kind": task_kind,
            "persona": persona or "implementer",
            "branch": branch,
            "governance_touch": governance_touch,
        },
    )
    return _write_record(path, record)


def plan_record(
    record_path: Path,
    *,
    planned_files: Sequence[str] = (),
    required_checks: Sequence[str] = (),
    changed_test_paths: Sequence[str] = (),
    replace: bool = False,
) -> Path:
    """Update the Plan stage of a gate record.

    Issue #1498: ``replace`` defaults to ``False`` (additive merge) so calling
    ``plan`` twice no longer silently drops the first call's entries. Pass
    ``replace=True`` to keep the pre-Issue-#1498 destructive behavior when
    the agent explicitly wants to rewrite the plan from scratch.
    """

    record = _load_record(record_path)
    new_planned = [_normalize_path(path) for path in planned_files]
    new_checks = list(required_checks)
    new_tests = [_normalize_path(path) for path in changed_test_paths]
    if replace:
        record.planned_files = new_planned
        record.required_checks = new_checks
        record.changed_test_paths = new_tests
    else:
        for path in new_planned:
            if path not in record.planned_files:
                record.planned_files.append(path)
        for check in new_checks:
            if check not in record.required_checks:
                record.required_checks.append(check)
        for path in new_tests:
            if path not in record.changed_test_paths:
                record.changed_test_paths.append(path)
    _mark_stage(record, GateStage.PLAN)
    _record_mutation(
        record,
        subcommand="plan",
        summary={
            "replace": replace,
            "added_files": len(new_planned),
            "added_checks": len(new_checks),
            "added_tests": len(new_tests),
        },
    )
    return _write_record(record_path, record)


def plan_remove_record(
    record_path: Path,
    *,
    planned_files: Sequence[str] = (),
    required_checks: Sequence[str] = (),
    changed_test_paths: Sequence[str] = (),
) -> Path:
    """Remove specific plan entries (Issue #1498).

    Unlike :func:`plan_record`, this does not advance the Plan stage. Use it
    to correct a plan that included files no longer in scope after an
    ``amend``.
    """

    record = _load_record(record_path)
    paths_to_remove = {_normalize_path(p) for p in planned_files}
    checks_to_remove = set(required_checks)
    tests_to_remove = {_normalize_path(p) for p in changed_test_paths}
    record.planned_files = [p for p in record.planned_files if p not in paths_to_remove]
    record.required_checks = [c for c in record.required_checks if c not in checks_to_remove]
    record.changed_test_paths = [p for p in record.changed_test_paths if p not in tests_to_remove]
    _record_mutation(
        record,
        subcommand="plan-remove",
        summary={
            "removed_files": len(paths_to_remove),
            "removed_checks": len(checks_to_remove),
            "removed_tests": len(tests_to_remove),
        },
    )
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
    _record_mutation(
        record,
        subcommand="amend",
        summary={
            "include_added": len(include),
            "exclude_added": len(exclude),
            "governance_touch_flipped_true": governance_touch is True,
            "approved_by": approved_by,
        },
    )
    return _write_record(record_path, record)


_CHANGELOG_PATHS: frozenset[str] = frozenset({"CHANGELOG.md"})
"""Repo-relative paths that credit the gate record's ``changelog`` landing
class. Previously the routing logic only knew about ``docs/`` and
``docs/planning/`` prefixes, so passing ``--updated CHANGELOG.md`` silently
routed it into the ``docs`` class and left ``changelog`` empty — every PR
that genuinely updated the changelog still failed ``docs_landing.missing-
changelog`` and had to either N/A the changelog (untruthful) or use
``admin-approved:ai-override`` to bypass the whole workflow gate (#1362)."""


def _bucket_paths(updated: Sequence[str]) -> tuple[list[str], list[str], list[str]]:
    """Sort updated paths into (docs_paths, checklist_paths, changelog_paths)."""

    normalised = [_normalize_path(path) for path in updated]
    changelog_paths = [path for path in normalised if path in _CHANGELOG_PATHS]
    checklist_paths = [path for path in normalised if path.startswith("docs/planning/")]
    docs_paths = [path for path in normalised if path not in _CHANGELOG_PATHS and not path.startswith("docs/planning/")]
    return docs_paths, checklist_paths, changelog_paths


def docs_record(
    record_path: Path,
    *,
    updated: Sequence[str] = (),
    na: Sequence[str] = (),
    replace: bool = False,
) -> Path:
    """Record documentation landing evidence.

    Issue #1498: ``replace`` defaults to ``False`` (additive merge over the
    existing ``docs_landing`` dict). Previously two ``docs`` calls would
    silently drop the first call's entries; this is now fixed unless the
    caller explicitly passes ``replace=True``.
    """

    record = _load_record(record_path)
    na_rationales = dict(_parse_key_values(na))
    docs_paths, checklist_paths, changelog_paths = _bucket_paths(updated)
    if replace:
        landing: dict[str, Any] = {
            "docs": {"paths": docs_paths} if docs_paths else {},
            "checklist": {"paths": checklist_paths} if checklist_paths else {},
            "changelog": {"paths": changelog_paths} if changelog_paths else {},
        }
    else:
        landing = dict(record.docs_landing)
        for class_name, new_paths in (
            ("docs", docs_paths),
            ("checklist", checklist_paths),
            ("changelog", changelog_paths),
        ):
            bucket = landing.get(class_name)
            existing_paths: list[str] = list(bucket["paths"]) if isinstance(bucket, dict) and "paths" in bucket else []
            merged = list(existing_paths)
            for path in new_paths:
                if path not in merged:
                    merged.append(path)
            if merged:
                landing[class_name] = {"paths": merged}
            elif class_name not in landing:
                landing[class_name] = {}
    for class_name, rationale in na_rationales.items():
        landing[class_name] = {"not_applicable": True, "rationale": rationale}
    record.docs_landing = landing
    _mark_stage(record, GateStage.UPDATE_DOCS)
    _record_mutation(
        record,
        subcommand="docs",
        summary={
            "replace": replace,
            "added_docs": len(docs_paths),
            "added_checklist": len(checklist_paths),
            "added_changelog": len(changelog_paths),
            "na_classes": list(na_rationales),
        },
    )
    return _write_record(record_path, record)


def docs_remove_record(
    record_path: Path,
    *,
    updated: Sequence[str] = (),
    na: Sequence[str] = (),
) -> Path:
    """Remove specific docs-landing entries (Issue #1498).

    Removes named paths from the ``docs``/``checklist``/``changelog``
    buckets and removes named N/A class keys. Does not advance the
    Update-Docs stage.
    """

    record = _load_record(record_path)
    paths_to_remove = {_normalize_path(p) for p in updated}
    landing = dict(record.docs_landing)
    removed_paths = 0
    for class_name in ("docs", "checklist", "changelog"):
        bucket = landing.get(class_name)
        if isinstance(bucket, dict) and "paths" in bucket:
            kept = [p for p in bucket["paths"] if p not in paths_to_remove]
            removed_paths += len(bucket["paths"]) - len(kept)
            landing[class_name] = {"paths": kept} if kept else {}
    removed_na: list[str] = []
    for na_key in na:
        if na_key in landing:
            del landing[na_key]
            removed_na.append(na_key)
    record.docs_landing = landing
    _record_mutation(
        record,
        subcommand="docs-remove",
        summary={"removed_paths": removed_paths, "removed_na": removed_na},
    )
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
    _record_mutation(
        record,
        subcommand="check",
        summary={"name": name, "status": status, "exit_code": exit_code, "full_audit": full_audit},
    )
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
    _record_mutation(
        record,
        subcommand="sentrux",
        summary={"status": status, "rules_checked": rules_checked, "total_rules_defined": total_rules_defined},
    )
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
    _record_mutation(
        record,
        subcommand="finalize",
        summary={
            "commit_count": len(commit_sha),
            "pr_number": pr_number,
            "closes_count": len(body_closes_issue),
        },
    )
    return _write_record(record_path, record)


# ---------------------------------------------------------------------------
# Issue #1498 — field mutators (issue, admin-labels, provenance)
# ---------------------------------------------------------------------------


def issue_add_record(
    record_path: Path,
    *,
    number: int,
    url: str | None = None,
    close_in_pr: bool = True,
    followup_rationale: str | None = None,
) -> Path:
    """Add a new issue reference to a gate record (Issue #1498).

    Multi-issue PRs (e.g., hotfix batches) need to add issues after ``start``.
    Previously the only way was to delete the record and restart, which lost
    all accumulated stages/plans/checks.
    """

    record = _load_record(record_path)
    if any(existing.number == number for existing in record.issues):
        raise ValueError(f"issue #{number} is already linked to this gate record")
    record.issues.append(
        IssueRef(
            number=number,
            url=url,
            close_in_pr=close_in_pr,
            followup_rationale=followup_rationale,
        )
    )
    _record_mutation(
        record,
        subcommand="issue-add",
        summary={"number": number, "close_in_pr": close_in_pr},
    )
    return _write_record(record_path, record)


def issue_update_record(
    record_path: Path,
    *,
    number: int,
    url: str | None = None,
    close_in_pr: bool | None = None,
    followup_rationale: str | None = None,
) -> Path:
    """Update fields on an existing issue reference (Issue #1498).

    Closes the gap where ``gate_record start --issue-url`` was the only way
    to set an issue URL — agents who forgot ``--issue-url`` previously had
    to direct-edit JSON to add it.
    """

    record = _load_record(record_path)
    target: IssueRef | None = None
    for existing in record.issues:
        if existing.number == number:
            target = existing
            break
    if target is None:
        raise ValueError(f"issue #{number} is not linked to this gate record")
    fields_updated: list[str] = []
    if url is not None:
        target.url = url
        fields_updated.append("url")
    if close_in_pr is not None:
        target.close_in_pr = close_in_pr
        fields_updated.append("close_in_pr")
    if followup_rationale is not None:
        target.followup_rationale = followup_rationale
        fields_updated.append("followup_rationale")
    if not fields_updated:
        raise ValueError("issue update requires at least one of --url / --close-in-pr / --followup-rationale")
    _record_mutation(
        record,
        subcommand="issue-update",
        summary={"number": number, "fields_updated": fields_updated},
    )
    return _write_record(record_path, record)


def issue_remove_record(
    record_path: Path,
    *,
    number: int,
    reason: str,
) -> Path:
    """Remove an issue reference (Issue #1498).

    Rejects removal of the last remaining issue because the GateRecord
    model invariant requires at least one issue.
    """

    record = _load_record(record_path)
    remaining = [issue for issue in record.issues if issue.number != number]
    if len(remaining) == len(record.issues):
        raise ValueError(f"issue #{number} is not linked to this gate record")
    if not remaining:
        raise ValueError("cannot remove the last issue from a gate record")
    record.issues = remaining
    _record_mutation(
        record,
        subcommand="issue-remove",
        summary={"number": number, "reason": reason},
    )
    return _write_record(record_path, record)


def admin_label_add_record(
    record_path: Path,
    *,
    label: str,
    reason: str,
    approved_by: str | None = None,
) -> Path:
    """Record that an admin label is expected on this PR (Issue #1498).

    Previously there was no CLI mutator at all for ``admin_labels``; PR
    #1497 had to direct-edit JSON. AdminLabelEvidence model_validator
    rejects label names outside ``VALID_OVERRIDE_LABELS``.
    """

    record = _load_record(record_path)
    if any(existing.name == label for existing in record.admin_labels):
        raise ValueError(f"admin label {label!r} is already recorded")
    record.admin_labels.append(AdminLabelEvidence(name=label, applied_by=approved_by, applied_at=datetime.now(UTC)))
    _record_mutation(
        record,
        subcommand="admin-label-add",
        summary={"label": label, "reason": reason, "approved_by": approved_by},
    )
    return _write_record(record_path, record)


def admin_label_remove_record(
    record_path: Path,
    *,
    label: str,
    reason: str,
) -> Path:
    """Remove an admin label entry from the gate record (Issue #1498)."""

    record = _load_record(record_path)
    remaining = [existing for existing in record.admin_labels if existing.name != label]
    if len(remaining) == len(record.admin_labels):
        raise ValueError(f"admin label {label!r} is not recorded")
    record.admin_labels = remaining
    _record_mutation(
        record,
        subcommand="admin-label-remove",
        summary={"label": label, "reason": reason},
    )
    return _write_record(record_path, record)


def provenance_rebuild_record(
    record_path: Path,
    *,
    reason: str,
    approved_by: str | None = None,
) -> Path:
    """Rebuild ``head_content_hash`` after a legitimate out-of-band edit (Issue #1498).

    Use sparingly. Appends a ``provenance-rebuild`` mutation whose
    ``content_hash_after`` is the new content hash. The audit trail records
    the rebuild so reviewers can see exactly when (and why) provenance was
    re-anchored.
    """

    record = _load_record(record_path)
    summary: dict[str, Any] = {"reason": reason}
    if approved_by:
        summary["approved_by"] = approved_by
    _record_mutation(record, subcommand="provenance-rebuild", summary=summary)
    return _write_record(record_path, record)
