"""Governance-layer schemas (ADR-043 §3 + §6.4).

This module consolidates the pydantic shapes ADR-043 introduces across
five separate fenced code blocks for governance rule modification, the
monotonic loosening check, the append-only audit log, the honeypot
canaries, and the CI-weakening detector.

The ADR text restates ``from … import …`` inside each fenced block —
``audit fix F6`` notes pytest-examples treats every fenced block as
independent. In the real module we collapse those into one module-top
import block, which is the manager-default consolidation pattern flagged
in the Phase 1 investigation SUMMARY.

Layout:

- §3.2 — ``GovernancePaths`` + ``HoneypotRuleEntry`` validate
  ``.governance-paths.yaml``.
- §3.4.3 — ``LoosenedAxis`` + ``MonotonicCheckResult`` back the loosening
  detector at ``scripts/audit/monotonic_check.py``.
- §3.6.1 — ``GovernanceChangeLogEntry`` is the row shape for the
  append-only ``docs/audit/governance-changes.log`` JSONL log.
- §3.6.3 — ``HoneypotRule`` + ``HoneypotViolation`` back the tripwire
  canary check.
- §6.4.1 — ``WeakeningKind`` + ``WeakeningFinding`` back the CI-weakening
  detector at ``scripts/audit/weakened_ci_check.py``.

All semantic enforcement (e.g. the 14 canonical ``LoosenedAxis.axis``
values from §3.4.1) lives at the tool layer per SUMMARY ``X1`` /
TC-1A.7 manager defaults — schemas here are purely structural.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._common import PathGlob

# ---------------------------------------------------------------------------
# §3.2 — Governance path registry + honeypot entries
# ---------------------------------------------------------------------------


class HoneypotRuleEntry(BaseModel):
    """One ``honeypot_canaries`` row inside ``.governance-paths.yaml``.

    Note: this schema is NOT listed in ADR-043 ``governs.contracts`` —
    flagged in the Phase 1 investigation SUMMARY (Q1A.7) as a §27.4
    errata candidate; ship the schema unblocked for IMPL-1A-c.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    marker_pattern: str


class GovernancePaths(BaseModel):
    """Validates ``.governance-paths.yaml``."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    governance_paths: list[PathGlob] = Field(min_length=1)
    honeypot_canaries: list[HoneypotRuleEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# §3.4.3 — Monotonic-loosening check result
# ---------------------------------------------------------------------------


class LoosenedAxis(BaseModel):
    """One observed loosening on a governance axis.

    ``axis`` is unconstrained ``str`` per SUMMARY ``X1`` manager default;
    the 14 canonical axes documented in ADR-043 §3.4.1 are enforced at
    the tool layer (TC-1E.3 ``monotonic_check``), not by the schema.
    """

    model_config = ConfigDict(extra="forbid")

    axis: str
    before_value: str
    after_value: str
    file: str
    line: int | None = None


class MonotonicCheckResult(BaseModel):
    """Result of running the monotonic-loosening check on a PR."""

    model_config = ConfigDict(extra="forbid")

    loosened: list[LoosenedAxis] = Field(default_factory=list)
    has_loosening_approved_trailer: bool
    approver_handle: str | None = None
    approver_is_tier2_verified: bool = False
    companion_addendum_pr: int | None = None
    contradiction_audit_clean: bool = False
    overall_blocking: bool


# ---------------------------------------------------------------------------
# §3.6.1 — Append-only governance-change log
# ---------------------------------------------------------------------------


class GovernanceChangeLogEntry(BaseModel):
    """One JSONL row of ``docs/audit/governance-changes.log``.

    ``runtime`` has no default per ADR text and SUMMARY Q1A.7 manager
    default (``required field``).
    """

    model_config = ConfigDict(extra="forbid")

    sha: str
    timestamp: datetime
    author_handle: str
    author_tier: Literal["agent", "human-tier-1", "human-tier-2"]
    runtime: str | None = None
    files_changed: list[str]
    diff_summary: str
    governance_paths_touched: list[str]
    has_approval_trailer: bool
    approver_handle: str | None = None
    approval_pr: int | None = None
    monotonic_check_result: Literal["ok", "loosening-approved", "loosening-rejected"]
    contradiction_audit_clean: bool
    honeypot_intact: bool


# ---------------------------------------------------------------------------
# §3.6.3 — Honeypot tripwires
# ---------------------------------------------------------------------------


class HoneypotRule(BaseModel):
    """Stored honeypot canary descriptor (line marker + sha)."""

    model_config = ConfigDict(extra="forbid")

    path: str
    marker_pattern: str
    expected_sha256: str
    last_verified: datetime


class HoneypotViolation(BaseModel):
    """One observed honeypot tripwire trip."""

    model_config = ConfigDict(extra="forbid")

    rule_path: str
    violating_commit_sha: str
    violating_author: str
    action_taken: Literal["auto-revert", "block-pr", "notify-only"]


# ---------------------------------------------------------------------------
# §6.4.1 — CI weakening detection
# ---------------------------------------------------------------------------


class WeakeningKind(StrEnum):
    """Categories of CI / test / lint weakening that block PR merge.

    Sourced from ADR-043 §6.4 — GitHub's 2026 agent-PR analysis flagged
    these as the highest-frequency failure modes.
    """

    DELETED_TEST_FILE = "deleted-test-file"
    REMOVED_TEST_FUNCTION = "removed-test-function"
    LOWERED_COVERAGE_THRESHOLD = "lowered-coverage-threshold"
    LOWERED_MUTATION_THRESHOLD = "lowered-mutation-threshold"
    UNJUSTIFIED_SKIP_OR_XFAIL = "unjustified-skip-or-xfail"
    DISABLED_LINT_RULE = "disabled-lint-rule"
    DISABLED_TYPECHECK_FLAG = "disabled-typecheck-flag"
    DISABLED_PRECOMMIT_HOOK = "disabled-precommit-hook"
    REMOVED_CI_JOB = "removed-ci-job"
    INCREASED_PYTEST_TIMEOUT = "increased-pytest-timeout"
    EXPANDED_EXEMPTION_PATHS = "expanded-exemption-paths"
    EXPANDED_NOQA_USAGE = "expanded-noqa-usage"
    REDUCED_SKILL_LIST = "reduced-skill-list"
    REDUCED_HONEYPOT_COUNT = "reduced-honeypot-count"


class WeakeningFinding(BaseModel):
    """One observed weakening event, with approval state and PR-blocking flag."""

    model_config = ConfigDict(extra="forbid")

    kind: WeakeningKind
    file: str
    line: int | None = None
    before_value: str
    after_value: str
    has_loosening_approval: bool
    blocking: bool
