"""Committed gate-record validation for ADR-042 Addendum 1."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

VALID_OVERRIDE_LABELS: frozenset[str] = frozenset(
    {
        "human-authored",
        "admin-approved:ai-override",
        "admin-approved:core-change",
        "admin-approved:merge",
    }
)

IMPLEMENTATION_TASK_KINDS: frozenset[str] = frozenset({"feature", "bugfix", "hotfix", "refactor", "maintenance"})

IMPLEMENTATION_PATTERNS: tuple[str, ...] = (
    "src/**",
    "packages/**",
    "frontend/**",
    "web/**",
    ".workflow/**",
    ".github/workflows/**",
    ".pre-commit-config.yaml",
    "scripts/hooks/**",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
)

NON_IMPLEMENTATION_PATTERNS: tuple[str, ...] = (
    "docs/**",
    "tests/**",
    "**/tests/**",
    "**/test_*.py",
    "**/*_test.py",
    ".workflow/records/**",
)

CLOSING_KEYWORD_RE = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#(?P<number>\d+)\b",
    re.IGNORECASE,
)

TRAILER_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z-]*):\s*(?P<value>.+?)\s*$", re.MULTILINE)
SLUG_RE = re.compile(r"[^a-z0-9]+")


class GateStage(StrEnum):
    """Canonical ADR-042 Addendum 1 gate stages."""

    SCOPE_AND_ISSUE = "scope_and_issue"
    PLAN = "plan"
    IMPLEMENT = "implement"
    UPDATE_DOCS = "update_docs"
    TEST_AND_CHECKS = "test_and_checks"
    COMMIT_AND_SUBMIT_PR = "commit_and_submit_pr"


CANONICAL_STAGE_ORDER: tuple[GateStage, ...] = (
    GateStage.SCOPE_AND_ISSUE,
    GateStage.PLAN,
    GateStage.IMPLEMENT,
    GateStage.UPDATE_DOCS,
    GateStage.TEST_AND_CHECKS,
    GateStage.COMMIT_AND_SUBMIT_PR,
)


class IssueRef(BaseModel):
    """A GitHub issue linked to the gate record."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(gt=0)
    url: str | None = None
    close_in_pr: bool = True
    followup_rationale: str | None = None

    @model_validator(mode="after")
    def _require_followup_rationale(self) -> IssueRef:
        if not self.close_in_pr and not self.followup_rationale:
            raise ValueError("non-closing issue references require followup_rationale")
        return self


class Scope(BaseModel):
    """Planned path scope for a gate record."""

    model_config = ConfigDict(extra="forbid")

    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    @field_validator("include", "exclude")
    @classmethod
    def _normalize_patterns(cls, value: list[str]) -> list[str]:
        return [_normalize_path(item) for item in value]


class ScopeAmendment(BaseModel):
    """Recorded scope amendment."""

    model_config = ConfigDict(extra="forbid")

    reason: str
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    approved_by: str | None = None

    @field_validator("include", "exclude")
    @classmethod
    def _normalize_patterns(cls, value: list[str]) -> list[str]:
        return [_normalize_path(item) for item in value]


class StageEvidence(BaseModel):
    """Completion evidence for one gate stage."""

    model_config = ConfigDict(extra="forbid")

    stage: GateStage
    status: Literal["pending", "done", "blocked", "skipped"] = "pending"
    completed_at: datetime | None = None
    summary: str | None = None


class CheckEvidence(BaseModel):
    """Command or MCP evidence captured by the gate."""

    model_config = ConfigDict(extra="forbid")

    name: str
    command_or_tool: str
    status: Literal["pass", "fail", "skipped", "unknown"]
    exit_code: int | None = None
    timestamp: datetime | None = None
    output_path: str | None = None
    summary: Mapping[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_exit_code(self) -> CheckEvidence:
        if self.status == "pass" and self.exit_code not in (None, 0):
            raise ValueError("passing checks cannot record a non-zero exit_code")
        return self


class SentruxEvidence(BaseModel):
    """Free-tier Sentrux evidence shape validated by Track B."""

    model_config = ConfigDict(extra="forbid")

    name: str = "sentrux.free_tier"
    mode: Literal["free-tier"]
    command_or_tool: str
    status: Literal["pass", "fail", "skipped", "unknown"]
    rules_checked: int | None = Field(default=None, ge=0)
    total_rules_defined: int | None = Field(default=None, ge=0)
    quality_signal: int | float | None = None
    thresholds: Mapping[str, Any] = Field(default_factory=dict)
    pro_required: Literal[False] = False
    output_path: str | None = None
    summary: Mapping[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_rule_counts(self) -> SentruxEvidence:
        if (
            self.rules_checked is not None
            and self.total_rules_defined is not None
            and self.rules_checked > self.total_rules_defined
        ):
            raise ValueError("rules_checked cannot exceed total_rules_defined")
        return self


class FullAuditEvidence(BaseModel):
    """ADR-042 full audit evidence."""

    model_config = ConfigDict(extra="forbid")

    command: str
    status: Literal["pass", "fail", "skipped", "unknown"]
    exit_code: int | None = None
    output_path: str
    blocks_merge: bool | None = None
    known_debt: list[str] = Field(default_factory=list)
    unclassified_failures: list[str] = Field(default_factory=list)
    summary: Mapping[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_known_debt_semantics(self) -> FullAuditEvidence:
        if self.status == "pass" and self.exit_code not in (None, 0):
            raise ValueError("passing full audit cannot record a non-zero exit_code")
        return self


class AdminLabelEvidence(BaseModel):
    """Administrator label and provenance evidence."""

    model_config = ConfigDict(extra="forbid")

    name: str
    applied_by: str | None = None
    applied_at: datetime | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if value not in VALID_OVERRIDE_LABELS:
            raise ValueError(f"invalid ADR-042 override label: {value}")
        return value


class CommitEvidence(BaseModel):
    """Commit provenance."""

    model_config = ConfigDict(extra="forbid")

    shas: list[str] = Field(default_factory=list)
    gate_record_path: str | None = None
    trailers: Mapping[str, str] = Field(default_factory=dict)


class PullRequestEvidence(BaseModel):
    """Pull-request provenance."""

    model_config = ConfigDict(extra="forbid")

    number: int | None = Field(default=None, gt=0)
    url: str | None = None
    body_closes_issues: list[int] = Field(default_factory=list)


class GateRecord(BaseModel):
    """Pydantic schema for committed ADR-042 gate records."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    record_path: str | None = None
    task_id: str
    task_kind: Literal["hotfix", "bugfix", "feature", "docs", "maintenance", "manager", "refactor"]
    branch: str
    owner_directive: str
    issues: list[IssueRef]
    scope: Scope
    governance_touch: bool = False
    stages: list[StageEvidence]
    planned_files: list[str] = Field(default_factory=list)
    changed_test_paths: list[str] = Field(default_factory=list)
    admin_labels: list[AdminLabelEvidence] = Field(default_factory=list)
    amendments: list[ScopeAmendment] = Field(default_factory=list)
    docs_landing: Mapping[str, Any] = Field(default_factory=dict)
    required_checks: list[str] = Field(default_factory=list)
    check_results: list[CheckEvidence] = Field(default_factory=list)
    sentrux: SentruxEvidence | None = None
    full_audit: FullAuditEvidence | None = None
    commit: CommitEvidence | None = None
    pull_request: PullRequestEvidence | None = None

    @field_validator("planned_files", "changed_test_paths")
    @classmethod
    def _normalize_paths(cls, value: list[str]) -> list[str]:
        return [_normalize_path(item) for item in value]

    @model_validator(mode="after")
    def _validate_record(self) -> GateRecord:
        if not self.issues:
            raise ValueError("gate records require at least one issue")
        stages = [stage.stage for stage in self.stages]
        if stages != list(CANONICAL_STAGE_ORDER):
            raise ValueError("stages must match the six ADR-042 Addendum 1 stages in canonical order")
        invalid_tests = [path for path in self.changed_test_paths if not _is_test_path(path)]
        if invalid_tests:
            raise ValueError(f"changed_test_paths contains non-test paths: {invalid_tests}")
        return self


def _normalize_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _match_path(path: str, pattern: str) -> bool:
    normalized_path = _normalize_path(path)
    normalized_pattern = _normalize_path(pattern)
    if normalized_pattern.endswith("/**"):
        return normalized_path == normalized_pattern[:-3] or normalized_path.startswith(normalized_pattern[:-2])
    if normalized_pattern.endswith("/"):
        return normalized_path.startswith(normalized_pattern)
    return fnmatch.fnmatchcase(normalized_path, normalized_pattern) or normalized_path == normalized_pattern


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(_match_path(path, pattern) for pattern in patterns)


def _is_test_path(path: str) -> bool:
    normalized = _normalize_path(path)
    name = Path(normalized).name
    return (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _is_implementation_path(path: str) -> bool:
    normalized = _normalize_path(path)
    if _matches_any(normalized, NON_IMPLEMENTATION_PATTERNS):
        return False
    return _matches_any(normalized, IMPLEMENTATION_PATTERNS)


def _sentrux_applies(path: str) -> bool:
    normalized = _normalize_path(path)
    if normalized.startswith("docs/") and not normalized.startswith(("docs/adr/", "docs/specs/")):
        return False
    return _matches_any(
        normalized,
        (
            "src/**",
            "packages/**",
            ".workflow/**",
            ".github/workflows/**",
            ".pre-commit-config.yaml",
            "scripts/hooks/**",
            ".sentrux/**",
            "docs/adr/**",
            "docs/specs/**",
        ),
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


def _load_record(record: GateRecord | Mapping[str, Any] | str | Path) -> GateRecord:
    if isinstance(record, GateRecord):
        return record
    if isinstance(record, Mapping):
        return GateRecord.model_validate(record)
    path = Path(record)
    return GateRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _slugify(value: str) -> str:
    slug = SLUG_RE.sub("-", value.lower()).strip("-")
    return slug or "task"


def _record_path(repo_root: Path, issue_number: int, slug: str, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit if explicit.is_absolute() else repo_root / explicit
    return repo_root / ".workflow" / "records" / f"{issue_number}-{_slugify(slug)}.json"


def _write_record(path: Path, record: GateRecord) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = record.model_dump(mode="json", exclude_none=False)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _mark_stage(record: GateRecord, stage: GateStage) -> None:
    for stage_evidence in record.stages:
        if stage_evidence.stage == stage:
            stage_evidence.status = "done"
            return


def _upsert_check(record: GateRecord, evidence: CheckEvidence) -> None:
    record.check_results = [check for check in record.check_results if check.name != evidence.name]
    record.check_results.append(evidence)


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


def validate_gate_record(
    record: GateRecord | Mapping[str, Any] | str | Path,
    *,
    changed_files: Sequence[str] | None = None,
    pr_body: str | None = None,
    pr_labels: Sequence[str] = (),
    guard_reports: Sequence[AuditReport] = (),
    require_pr_body: bool = False,
    require_final_evidence: bool = True,
) -> AuditReport:
    """Validate a gate record against optional PR or staged-file evidence."""

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
            governance_paths = [
                path
                for path in normalized_changed
                if _matches_any(
                    path,
                    (
                        ".workflow/**",
                        ".github/workflows/**",
                        ".pre-commit-config.yaml",
                        "docs/adr/ADR-042.md",
                        "docs/adr/ADR-042-addendum*.md",
                        "src/scistudio/qa/governance/**",
                    ),
                )
            ]
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

        if require_final_evidence and any(_sentrux_applies(path) for path in normalized_changed):
            if parsed.sentrux is None:
                findings.append(_finding("gate-record.sentrux.missing", "applicable changes require Sentrux evidence"))
            elif parsed.sentrux.status != "pass":
                findings.append(
                    _finding(
                        "gate-record.sentrux.not-passing",
                        "Sentrux evidence must pass for applicable changes",
                        evidence={"status": parsed.sentrux.status},
                    )
                )

    if require_final_evidence:
        for stage in parsed.stages:
            if stage.status != "done":
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


def _git_lines(repo_root: Path, args: list[str]) -> list[str]:
    output = subprocess.check_output(["git", *args], cwd=repo_root, text=True, stderr=subprocess.DEVNULL)
    return [_normalize_path(line) for line in output.splitlines() if line.strip()]


def _discover_gate_record(repo_root: Path, changed_files: Sequence[str]) -> Path | None:
    record_paths = [path for path in changed_files if _match_path(path, ".workflow/records/*.json")]
    if len(record_paths) == 1:
        return repo_root / record_paths[0]
    records_dir = repo_root / ".workflow" / "records"
    records = sorted(records_dir.glob("*.json")) if records_dir.exists() else []
    return records[0] if len(records) == 1 else None


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
    return validate_gate_record(record_path, changed_files=changed)


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
    return check_pr(record_path, changed_files=changed, pr_body=pr_body, pr_labels=pr_labels)


def _trailers(commit_message: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in TRAILER_RE.finditer(commit_message)}


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
) -> Path:
    """Append a scope amendment."""

    record = _load_record(record_path)
    record.amendments.append(
        ScopeAmendment(reason=reason, include=list(include), exclude=list(exclude), approved_by=approved_by)
    )
    _mark_stage(record, GateStage.IMPLEMENT)
    return _write_record(record_path, record)


def docs_record(
    record_path: Path,
    *,
    updated: Sequence[str] = (),
    na: Sequence[str] = (),
) -> Path:
    """Record documentation landing evidence."""

    record = _load_record(record_path)
    na_rationales = dict(_parse_key_values(na))
    docs_paths = [_normalize_path(path) for path in updated if not _normalize_path(path).startswith("docs/planning/")]
    checklist_paths = [_normalize_path(path) for path in updated if _normalize_path(path).startswith("docs/planning/")]
    landing: dict[str, Any] = {
        "docs": {"paths": docs_paths} if docs_paths else {},
        "checklist": {"paths": checklist_paths} if checklist_paths else {},
        "changelog": {},
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


def _parse_key_values(values: Sequence[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in values:
        if "=" in item:
            key, value = item.split("=", 1)
        elif ":" in item:
            key, value = item.split(":", 1)
        else:
            raise ValueError(f"expected KEY=VALUE item: {item}")
        pairs.append((key.strip(), value.strip()))
    return pairs


def _parse_issue_numbers(values: Sequence[str]) -> list[int]:
    numbers: list[int] = []
    for value in values:
        match = re.fullmatch(r"#?(\d+)", value.strip())
        if match is None:
            raise ValueError(f"expected issue number or #N item: {value}")
        numbers.append(int(match.group(1)))
    return numbers


def _render_text(report: AuditReport) -> str:
    if not report.findings:
        return "gate_record: pass"
    lines = ["gate_record: fail"]
    lines.extend(f"- {finding.rule_id}: {finding.message}" for finding in report.findings)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="create or replace a committed gate record")
    start.add_argument("--repo-root", type=Path, default=Path.cwd())
    start.add_argument("--issue", type=int, required=True)
    start.add_argument("--issue-url")
    start.add_argument("--slug", required=True)
    start.add_argument("--task-kind", required=True)
    start.add_argument("--branch", required=True)
    start.add_argument("--owner-directive", required=True)
    start.add_argument("--include", action="append", default=[])
    start.add_argument("--exclude", action="append", default=[])
    start.add_argument("--governance-touch", action="store_true")
    start.add_argument("--record-path", "--record", dest="record_path", type=Path)

    plan = subparsers.add_parser("plan", help="record planned files, checks, and expected tests")
    plan.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    plan.add_argument("--planned-file", "--files", dest="planned_file", action="append", default=[])
    plan.add_argument("--required-check", "--checks", dest="required_check", action="append", default=[])
    plan.add_argument("--changed-test-path", "--tests", dest="changed_test_path", action="append", default=[])
    plan.add_argument("--docs", action="append", default=[], help="planned documentation path or N/A rationale")

    amend = subparsers.add_parser("amend", help="append a scope amendment")
    amend.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    amend.add_argument("--reason", required=True)
    amend.add_argument("--include", action="append", default=[])
    amend.add_argument("--exclude", action="append", default=[])
    amend.add_argument("--approved-by")

    docs = subparsers.add_parser("docs", help="record documentation landing")
    docs.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    docs.add_argument("--updated", action="append", default=[])
    docs.add_argument("--na", action="append", default=[], help="N/A rationale as KEY=VALUE or KEY:VALUE")

    check = subparsers.add_parser("check", help="record a check result or full-audit evidence")
    check.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    check.add_argument("--name", default="full_audit")
    check.add_argument("--command-or-tool", "--command", dest="command_or_tool", required=True)
    check.add_argument("--status", choices=("pass", "fail", "skipped", "unknown"), required=True)
    check.add_argument("--exit-code", type=int)
    check.add_argument("--output-path", "--output", dest="output_path")
    check.add_argument("--full-audit", action="store_true")
    check.add_argument("--blocks-merge", action="store_true")
    check.add_argument("--known-debt", action="append", default=[])
    check.add_argument("--unclassified-failure", action="append", default=[])

    sentrux = subparsers.add_parser("sentrux", help="record Sentrux free-tier evidence")
    sentrux.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    sentrux.add_argument("--command-or-tool", "--command", dest="command_or_tool", default="sentrux check")
    sentrux.add_argument("--mode", choices=("free-tier",), default="free-tier")
    sentrux.add_argument("--status", choices=("pass", "fail", "skipped", "unknown"), required=True)
    sentrux.add_argument("--evidence", dest="output_path")
    sentrux.add_argument("--rules-checked", type=int)
    sentrux.add_argument("--total-rules-defined", type=int)
    sentrux.add_argument("--quality-signal", type=float)
    sentrux.add_argument("--threshold", action="append", default=[], help="threshold as KEY=VALUE")
    sentrux.add_argument("--output-path")

    finalize = subparsers.add_parser("finalize", help="record final commit and PR provenance")
    finalize.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    finalize.add_argument("--commit-sha", "--commit", dest="commit_sha", action="append", default=[])
    finalize.add_argument("--pr-number", type=int)
    finalize.add_argument("--pr-url", "--pr", dest="pr_url")
    finalize.add_argument("--body-closes-issue", "--closes", dest="body_closes_issue", action="append", default=[])

    pre_commit = subparsers.add_parser("pre-commit", help="validate staged files against a gate record")
    pre_commit.add_argument("--repo-root", type=Path, default=Path.cwd())
    pre_commit.add_argument("--gate-record", "--record", dest="gate_record", type=Path)
    pre_commit.add_argument("--staged", action="store_true", help="kept for hook compatibility")
    pre_commit.add_argument("--bypass-label", action="append", default=[])

    commit_msg = subparsers.add_parser("commit-msg", help="validate commit-message trailers")
    commit_msg.add_argument("message_file", type=Path)
    commit_msg.add_argument("--bypass-label", action="append", default=[])

    ci = subparsers.add_parser("ci", help="validate a committed gate record against PR metadata")
    ci.add_argument("--repo-root", type=Path, default=Path.cwd())
    ci.add_argument("--gate-record", "--record", dest="gate_record", type=Path, required=True)
    ci.add_argument("--base", default="origin/main")
    ci.add_argument("--head", default="HEAD")
    ci.add_argument("--pr-body", default="")
    ci.add_argument("--pr-label", action="append", default=[])
    ci.add_argument("--format", choices=("text", "json"), default="text")

    pre_push = subparsers.add_parser("pre-push", help="validate local branch diff before push")
    pre_push.add_argument("--repo-root", type=Path, default=Path.cwd())
    pre_push.add_argument("--gate-record", "--record", dest="gate_record", type=Path)
    pre_push.add_argument("--base", default="origin/main")
    pre_push.add_argument("--head", default="HEAD")
    pre_push.add_argument("--format", choices=("text", "json"), default="text")
    pre_push.add_argument("--bypass-label", action="append", default=[])

    pr_ready = subparsers.add_parser("pr-ready", help="validate local PR readiness before gh pr create")
    pr_ready.add_argument("--repo-root", type=Path, default=Path.cwd())
    pr_ready.add_argument("--gate-record", "--record", dest="gate_record", type=Path)
    pr_ready.add_argument("--base", default="origin/main")
    pr_ready.add_argument("--head", default="HEAD")
    pr_ready.add_argument("--pr-body", default="")
    pr_ready.add_argument("--pr-label", action="append", default=[])
    pr_ready.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            output_path = start_record(
                repo_root=args.repo_root,
                issue_number=args.issue,
                issue_url=args.issue_url,
                slug=args.slug,
                task_kind=args.task_kind,
                branch=args.branch,
                owner_directive=args.owner_directive,
                include=args.include,
                exclude=args.exclude,
                governance_touch=args.governance_touch,
                record_path=args.record_path,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "plan":
            output_path = plan_record(
                args.gate_record,
                planned_files=args.planned_file,
                required_checks=args.required_check,
                changed_test_paths=args.changed_test_path,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "amend":
            output_path = amend_record(
                args.gate_record,
                reason=args.reason,
                include=args.include,
                exclude=args.exclude,
                approved_by=args.approved_by,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "docs":
            output_path = docs_record(args.gate_record, updated=args.updated, na=args.na)
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "check":
            output_path = check_record(
                args.gate_record,
                name=args.name,
                command_or_tool=args.command_or_tool,
                status=args.status,
                exit_code=args.exit_code,
                output_path=args.output_path,
                full_audit=args.full_audit,
                blocks_merge=args.blocks_merge if args.full_audit else None,
                known_debt=args.known_debt,
                unclassified_failure=args.unclassified_failure,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "sentrux":
            output_path = sentrux_record(
                args.gate_record,
                command_or_tool=args.command_or_tool,
                status=args.status,
                rules_checked=args.rules_checked,
                total_rules_defined=args.total_rules_defined,
                quality_signal=args.quality_signal,
                threshold=args.threshold,
                output_path=args.output_path,
            )
            print(_normalize_path(str(output_path)))
            return 0
        if args.command == "finalize":
            output_path = finalize_record(
                args.gate_record,
                commit_sha=args.commit_sha,
                pr_number=args.pr_number,
                pr_url=args.pr_url,
                body_closes_issue=_parse_issue_numbers(args.body_closes_issue),
            )
            print(_normalize_path(str(output_path)))
            return 0
    except (OSError, ValidationError, ValueError) as exc:
        print(f"gate_record {args.command} failed: {exc}", file=sys.stderr)
        return 1

    if args.command == "pre-commit":
        report = check_pre_commit(
            args.repo_root,
            gate_record=args.gate_record,
            bypass_labels=[*args.bypass_label, *_env_bypass_labels()],
        )
    elif args.command == "commit-msg":
        report = check_commit_msg(args.message_file, bypass_labels=[*args.bypass_label, *_env_bypass_labels()])
    elif args.command == "pre-push":
        report = check_pre_push(
            args.repo_root,
            gate_record=args.gate_record,
            base=args.base,
            head=args.head,
            bypass_labels=[*args.bypass_label, *_env_bypass_labels()],
        )
    elif args.command == "pr-ready":
        report = check_pr_ready(
            args.repo_root,
            gate_record=args.gate_record,
            base=args.base,
            head=args.head,
            pr_body=args.pr_body,
            pr_labels=[*args.pr_label, *_env_bypass_labels()],
        )
    else:
        changed_files = _git_lines(
            args.repo_root, ["diff", "--name-only", "--diff-filter=ACMRTUXB", f"{args.base}...{args.head}"]
        )
        report = check_pr(
            args.gate_record,
            changed_files=changed_files,
            pr_body=args.pr_body,
            pr_labels=args.pr_label,
        )

    if getattr(args, "format", "text") == "json":
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 1 if report.blocks_merge else 0


if __name__ == "__main__":
    sys.exit(main())
