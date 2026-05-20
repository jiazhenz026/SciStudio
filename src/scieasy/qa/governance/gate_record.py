"""Committed gate-record validation for ADR-042 Addendum 1."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from scieasy.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

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
    return path.replace("\\", "/").strip().lstrip("./")


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


def _closed_issue_numbers(pr_body: str) -> set[int]:
    return {int(match.group("number")) for match in CLOSING_KEYWORD_RE.finditer(pr_body)}


def _invalid_override_labels(labels: Iterable[str]) -> list[str]:
    invalid: list[str] = []
    known_human_typos = {"human-authored:", "human_authored", "human authored", "human-authored-pr"}
    for label in labels:
        if label in VALID_OVERRIDE_LABELS:
            continue
        if label.startswith("admin-approved:") or label in known_human_typos:
            invalid.append(label)
    return invalid


def validate_gate_record(
    record: GateRecord | Mapping[str, Any] | str | Path,
    *,
    changed_files: Sequence[str] | None = None,
    pr_body: str | None = None,
    pr_labels: Sequence[str] = (),
    guard_reports: Sequence[AuditReport] = (),
    require_pr_body: bool = False,
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
                        "src/scieasy/qa/governance/**",
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

        if parsed.task_kind in IMPLEMENTATION_TASK_KINDS:
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

        if any(_sentrux_applies(path) for path in normalized_changed):
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

    if parsed.full_audit is None:
        findings.append(_finding("gate-record.full-audit.missing", "ADR-042 full audit evidence is required"))
    else:
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
) -> AuditReport:
    """Validate staged files against the committed gate record."""

    root = repo_root or Path.cwd()
    changed = list(staged_files) if staged_files is not None else _git_lines(root, ["diff", "--cached", "--name-only"])
    record_path = gate_record or _discover_gate_record(root, changed)
    if record_path is None:
        return _report([_finding("gate-record.missing", "exactly one gate record is required for pre-commit checks")])
    return validate_gate_record(record_path, changed_files=changed)


def _trailers(commit_message: str) -> dict[str, str]:
    return {match.group("key"): match.group("value") for match in TRAILER_RE.finditer(commit_message)}


def check_commit_msg(commit_message: str | Path) -> AuditReport:
    """Validate ADR-042 commit trailers."""

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


def _render_text(report: AuditReport) -> str:
    if not report.findings:
        return "gate_record: pass"
    lines = ["gate_record: fail"]
    lines.extend(f"- {finding.rule_id}: {finding.message}" for finding in report.findings)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    pre_commit = subparsers.add_parser("pre-commit", help="validate staged files against a gate record")
    pre_commit.add_argument("--repo-root", type=Path, default=Path.cwd())
    pre_commit.add_argument("--gate-record", type=Path)
    pre_commit.add_argument("--staged", action="store_true", help="kept for hook compatibility")

    commit_msg = subparsers.add_parser("commit-msg", help="validate commit-message trailers")
    commit_msg.add_argument("message_file", type=Path)

    ci = subparsers.add_parser("ci", help="validate a committed gate record against PR metadata")
    ci.add_argument("--repo-root", type=Path, default=Path.cwd())
    ci.add_argument("--gate-record", type=Path, required=True)
    ci.add_argument("--base", default="origin/main")
    ci.add_argument("--head", default="HEAD")
    ci.add_argument("--pr-body", default="")
    ci.add_argument("--pr-label", action="append", default=[])
    ci.add_argument("--format", choices=("text", "json"), default="text")

    args = parser.parse_args(argv)
    if args.command == "pre-commit":
        report = check_pre_commit(args.repo_root, gate_record=args.gate_record)
    elif args.command == "commit-msg":
        report = check_commit_msg(args.message_file)
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
