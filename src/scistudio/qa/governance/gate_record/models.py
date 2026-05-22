"""Pydantic models and enums for ADR-042 gate records.

Defines the on-disk schema (``GateRecord`` and its evidence sub-models) plus
the canonical stage enum. Kept free of CLI / I/O imports so that the schema
can be loaded by tests, plugins, and audit tools without pulling in argparse
or subprocess.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scistudio.qa.governance.gate_record.paths import (
    VALID_OVERRIDE_LABELS,
    _is_test_path,
    _normalize_path,
)


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


# Stages that can only be done after the PR exists. Pre-push and pr-ready
# validators run BEFORE the PR is created, so they must not require these
# stages to be done — otherwise every initial push hits a chicken-and-egg
# (#1340): commit_and_submit_pr is set by ``finalize`` which needs a commit
# SHA and PR URL, but the PR cannot be opened without first passing pr-ready,
# and pre-push cannot accept without commit_and_submit_pr. CI runs after the
# PR exists, so it does require all stages.
POST_PR_STAGES: frozenset[GateStage] = frozenset({GateStage.COMMIT_AND_SUBMIT_PR})


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
