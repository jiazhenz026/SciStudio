"""Gate-record validation entry points used by hooks and CI.

Wraps the per-record schema validation, scope/governance checks, post-PR
stage requirements, and PR-body / label inspections into a single
``validate_gate_record`` plus the surface used by hooks
(``check_pre_commit``, ``check_pre_push``, ``check_pr_ready``,
``check_commit_msg``, ``check_pr``).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from scistudio.qa.governance.gate_record.io import (
    _discover_gate_record,
    _git_lines,
    _load_record,
)
from scistudio.qa.governance.gate_record.models import (
    POST_PR_STAGES,
    GateRecord,
)
from scistudio.qa.governance.gate_record.paths import (
    CLOSING_KEYWORD_RE,
    IMPLEMENTATION_TASK_KINDS,
    TRAILER_RE,
    VALID_OVERRIDE_LABELS,
    _is_governance_path,
    _is_implementation_path,
    _is_test_path,
    _match_path,
    _matches_any,
    _normalize_path,
    _sentrux_applies,
)
from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity


def _finding(rule_id: str, message: str, *, file: str = "", evidence: Mapping[str, Any] | None = None) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=Severity.ERROR,
        file=file,
        message=message,
        evidence=evidence or {},
    )


def _report(findings: list[Finding], *, summary: Mapping[str, Any] | None = None) -> AuditReport:
    return AuditReport(
        tool="gate_record",
        status=AuditStatus.FAIL if findings else AuditStatus.PASS,
        source_sha="unknown",
        findings=findings,
        summary=summary or {},
    )


def _effective_include(record: GateRecord) -> list[str]:
    includes = list(record.scope.include)
    for amendment in record.amendments:
        includes.extend(amendment.include)
    return includes


def _effective_exclude(record: GateRecord) -> list[str]:
    excludes = list(record.scope.exclude)
    for amendment in record.amendments:
        excludes.extend(amendment.exclude)
    return excludes


def _closed_issue_numbers(pr_body: str) -> set[int]:
    return {int(match.group("number")) for match in CLOSING_KEYWORD_RE.finditer(pr_body)}


def _invalid_override_labels(labels: Iterable[str]) -> list[str]:
    invalid: list[str] = []
    known_human_typos = {"human-authored:", "human_authored", "human authored", "human-authored-pr"}
    for label in labels:
        if label in VALID_OVERRIDE_LABELS:
            continue
        if label.startswith("admin-approved") or label.startswith("human") or label in known_human_typos:
            invalid.append(label)
    return invalid


def _split_labels(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\s,]+", value) if item.strip()]


def _env_bypass_labels() -> list[str]:
    return _split_labels(os.environ.get("SCISTUDIO_GATE_BYPASS_LABELS", ""))


def _local_bypass_report(labels: Sequence[str]) -> AuditReport | None:
    normalized = [label.strip() for label in labels if label.strip()]
    invalid = _invalid_override_labels(normalized)
    if invalid:
        return _report(
            [
                _finding(
                    "gate-record.override-label.invalid",
                    f"invalid ADR-042 override label: {label}",
                    evidence={"valid_labels": sorted(VALID_OVERRIDE_LABELS)},
                )
                for label in invalid
            ]
        )
    valid = sorted(set(normalized) & VALID_OVERRIDE_LABELS)
    if valid:
        return _report(
            [],
            summary={
                "skipped": "local ADR-042 hook bypassed by override label; CI/review remains authoritative",
                "bypass_labels": valid,
            },
        )
    return None


def _trailers(commit_message: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in TRAILER_RE.finditer(commit_message)}


def validate_gate_record(
    record: GateRecord | Mapping[str, Any] | str | Path,
    *,
    changed_files: Sequence[str] | None = None,
    pr_body: str | None = None,
    pr_labels: Sequence[str] = (),
    guard_reports: Sequence[AuditReport] = (),
    require_pr_body: bool = False,
    require_final_evidence: bool = True,
    require_post_pr_stages: bool = True,
) -> AuditReport:
    """Validate a gate record against optional PR or staged-file evidence.

    ``require_post_pr_stages`` controls whether stages that can only complete
    after the PR exists (currently ``commit_and_submit_pr``) are required.
    Pre-push and pr-ready validators set this to ``False`` because they run
    before ``gh pr create`` (#1340). CI validation leaves it ``True``.
    """

    findings: list[Finding] = []
    try:
        parsed = _load_record(record)
    except (OSError, ValidationError, ValueError) as exc:
        return _report([_finding("gate-record.schema.invalid", str(exc))])

    normalized_changed = [_normalize_path(path) for path in changed_files or []]
    includes = _effective_include(parsed)
    excludes = _effective_exclude(parsed)

    if normalized_changed:
        for path in normalized_changed:
            if includes and not _matches_any(path, includes):
                findings.append(
                    _finding(
                        "gate-record.scope.outside-include",
                        f"changed file is outside gate scope include patterns: {path}",
                        file=path,
                        evidence={"include": includes},
                    )
                )
            if _matches_any(path, excludes):
                findings.append(
                    _finding(
                        "gate-record.scope.inside-exclude",
                        f"changed file is inside gate scope exclude patterns: {path}",
                        file=path,
                        evidence={"exclude": excludes},
                    )
                )

        if not parsed.governance_touch:
            governance_paths = [path for path in normalized_changed if _is_governance_path(path)]
            for path in governance_paths:
                findings.append(
                    _finding(
                        "gate-record.governance-touch.missing",
                        "governance file changed but governance_touch is false",
                        file=path,
                    )
                )

        if require_final_evidence and parsed.task_kind in IMPLEMENTATION_TASK_KINDS:
            implementation_paths = [path for path in normalized_changed if _is_implementation_path(path)]
            changed_tests = [path for path in normalized_changed if _is_test_path(path)]
            if implementation_paths and not parsed.changed_test_paths and not changed_tests:
                findings.append(
                    _finding(
                        "gate-record.tests.changed-test-required",
                        "implementation-category tasks that change implementation files must add or modify tests",
                        evidence={"implementation_paths": implementation_paths},
                    )
                )
            missing_listed_tests = sorted(set(parsed.changed_test_paths) - set(normalized_changed))
            for path in missing_listed_tests:
                findings.append(
                    _finding(
                        "gate-record.tests.changed-test-not-in-diff",
                        f"changed_test_paths entry is not present in changed files: {path}",
                        file=path,
                    )
                )

        # ADR-042 Addendum 3: Sentrux is advisory at the gate. Missing,
        # skipped, or unknown evidence is allowed (sentrux binary may not
        # be available for this contributor / agent). Recorded
        # ``status="fail"`` still blocks locally — the developer ran
        # sentrux, observed a real failure, and is pushing anyway, which
        # is the only case the gate is now scoped to catch. Use
        # admin-approved:ai-override to bypass when justified.
        if (
            require_final_evidence
            and any(_sentrux_applies(path) for path in normalized_changed)
            and parsed.sentrux is not None
            and parsed.sentrux.status == "fail"
        ):
            findings.append(
                _finding(
                    "gate-record.sentrux.not-passing",
                    "Sentrux evidence records a failing status; fix the violation or override (ADR-042 Addendum 3)",
                    evidence={"status": parsed.sentrux.status},
                )
            )

    if require_final_evidence:
        for stage in parsed.stages:
            if stage.status == "done":
                continue
            if not require_post_pr_stages and stage.stage in POST_PR_STAGES:
                continue
            findings.append(
                _finding(
                    "gate-record.stage.not-done",
                    f"gate stage must be done before PR readiness: {stage.stage.value}",
                    evidence={"stage": stage.stage.value, "status": stage.status},
                )
            )

    if require_final_evidence and parsed.full_audit is None:
        findings.append(_finding("gate-record.full-audit.missing", "ADR-042 full audit evidence is required"))
    elif parsed.full_audit is not None:
        full_audit = parsed.full_audit
        if full_audit.unclassified_failures:
            findings.append(
                _finding(
                    "gate-record.full-audit.unclassified-failures",
                    "full-audit failures must be classified as known debt during the transition",
                    evidence={"unclassified_failures": full_audit.unclassified_failures},
                )
            )
        if full_audit.status == "fail" and not full_audit.known_debt:
            findings.append(
                _finding(
                    "gate-record.full-audit.unclassified-fail-status",
                    "failing full-audit evidence must list known_debt or unclassified_failures",
                )
            )

    if require_pr_body and pr_body is None:
        findings.append(_finding("gate-record.pr-body.missing", "PR body is required for CI validation"))
    if pr_body is not None:
        closed = _closed_issue_numbers(pr_body)
        for issue in parsed.issues:
            if issue.close_in_pr and issue.number not in closed:
                findings.append(
                    _finding(
                        "gate-record.issue.not-closed",
                        f"PR body must close issue #{issue.number} with Closes, Fixes, or Resolves",
                    )
                )
            elif not issue.close_in_pr and issue.followup_rationale:
                body_lower = pr_body.lower()
                if f"#{issue.number}" not in body_lower or "owner-approved" not in body_lower:
                    findings.append(
                        _finding(
                            "gate-record.issue.followup-rationale-missing",
                            f"non-closing issue #{issue.number} requires owner-approved follow-up rationale in PR body",
                        )
                    )

    for label in _invalid_override_labels(pr_labels):
        findings.append(
            _finding(
                "gate-record.override-label.invalid",
                f"invalid ADR-042 override label: {label}",
                evidence={"valid_labels": sorted(VALID_OVERRIDE_LABELS)},
            )
        )

    for guard_report in guard_reports:
        if guard_report.blocks_merge:
            findings.append(
                _finding(
                    "gate-record.guard.failed",
                    f"ADR-042 guard failed: {guard_report.tool}",
                    evidence=guard_report.model_dump(mode="json"),
                )
            )

    return _report(
        findings,
        summary={
            "task_id": parsed.task_id,
            "task_kind": parsed.task_kind,
            "issues": [issue.number for issue in parsed.issues],
            "changed_files_checked": normalized_changed,
            "valid_override_labels": sorted(VALID_OVERRIDE_LABELS),
        },
    )


def check_pre_commit(
    repo_root: Path | None = None,
    *,
    gate_record: Path | None = None,
    staged_files: Sequence[str] | None = None,
    bypass_labels: Sequence[str] = (),
) -> AuditReport:
    """Validate staged files against the committed gate record."""

    bypass = _local_bypass_report(bypass_labels)
    if bypass is not None:
        return bypass
    root = repo_root or Path.cwd()
    changed = list(staged_files) if staged_files is not None else _git_lines(root, ["diff", "--cached", "--name-only"])
    record_path = gate_record or _discover_gate_record(root, changed)
    if record_path is None:
        return _report([], summary={"skipped": "no gate record present yet; final push/PR/CI gate remains required"})
    return validate_gate_record(record_path, changed_files=changed, require_final_evidence=False)


def check_pre_push(
    repo_root: Path | None = None,
    *,
    gate_record: Path | None = None,
    base: str = "origin/main",
    head: str = "HEAD",
    bypass_labels: Sequence[str] = (),
) -> AuditReport:
    """Validate the current branch diff before push."""

    bypass = _local_bypass_report(bypass_labels)
    if bypass is not None:
        return bypass
    root = repo_root or Path.cwd()
    changed = _git_lines(root, ["diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...{head}"])
    record_path = gate_record or _discover_gate_record(root, changed)
    if record_path is None:
        return _report([_finding("gate-record.missing", "exactly one gate record is required before push")])
    return validate_gate_record(record_path, changed_files=changed, require_post_pr_stages=False)


def check_pr_ready(
    repo_root: Path | None = None,
    *,
    gate_record: Path | None = None,
    base: str = "origin/main",
    head: str = "HEAD",
    pr_body: str = "",
    pr_labels: Sequence[str] = (),
) -> AuditReport:
    """Validate local PR readiness before opening a PR."""

    bypass = _local_bypass_report(pr_labels)
    if bypass is not None:
        return bypass
    root = repo_root or Path.cwd()
    changed = _git_lines(root, ["diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...{head}"])
    record_path = gate_record or _discover_gate_record(root, changed)
    if record_path is None:
        return _report([_finding("gate-record.missing", "exactly one gate record is required before PR creation")])
    return validate_gate_record(
        record_path,
        changed_files=changed,
        pr_body=pr_body,
        pr_labels=pr_labels,
        require_pr_body=True,
        require_post_pr_stages=False,
    )


def check_commit_msg(commit_message: str | Path, *, bypass_labels: Sequence[str] = ()) -> AuditReport:
    """Validate ADR-042 commit trailers."""

    bypass = _local_bypass_report(bypass_labels)
    if bypass is not None:
        return bypass
    text = commit_message.read_text(encoding="utf-8") if isinstance(commit_message, Path) else commit_message
    trailers = _trailers(text)
    findings: list[Finding] = []
    required = ("Gate-Record", "Task-Kind", "Issue", "Assisted-by")
    for key in required:
        if key not in trailers:
            findings.append(_finding("gate-record.commit-trailer.missing", f"missing commit trailer: {key}"))
    task_kind = trailers.get("Task-Kind")
    if task_kind is not None and task_kind not in IMPLEMENTATION_TASK_KINDS | {"docs", "manager"}:
        findings.append(
            _finding(
                "gate-record.commit-trailer.invalid-task-kind",
                f"invalid Task-Kind trailer: {task_kind}",
            )
        )
    issue = trailers.get("Issue")
    if issue is not None and not re.fullmatch(r"#\d+(?:,\s*#\d+)*", issue):
        findings.append(_finding("gate-record.commit-trailer.invalid-issue", "Issue trailer must use #N format"))
    gate_record = trailers.get("Gate-Record")
    if gate_record is not None and not _match_path(gate_record, ".workflow/records/*.json"):
        findings.append(
            _finding(
                "gate-record.commit-trailer.invalid-path",
                "Gate-Record trailer must point to .workflow/records/<record>.json",
            )
        )
    assisted_by = trailers.get("Assisted-by")
    if assisted_by is not None and ":" not in assisted_by:
        findings.append(
            _finding("gate-record.commit-trailer.invalid-assisted-by", "Assisted-by must use runtime:model")
        )
    return _report(findings, summary={"trailers": trailers})


def check_pr(
    record: GateRecord | Mapping[str, Any] | str | Path,
    *,
    changed_files: Sequence[str],
    pr_body: str,
    pr_labels: Sequence[str] = (),
    guard_reports: Sequence[AuditReport] = (),
) -> AuditReport:
    """Validate a gate record in CI against PR metadata."""

    return validate_gate_record(
        record,
        changed_files=changed_files,
        pr_body=pr_body,
        pr_labels=pr_labels,
        guard_reports=guard_reports,
        require_pr_body=True,
    )
