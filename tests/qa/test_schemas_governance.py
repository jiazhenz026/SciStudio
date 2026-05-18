"""Tests for ``scieasy.qa.schemas.governance`` (ADR-043 §3 + §6.4).

NOTE: this test file is NOT listed in ADR-043 frontmatter ``tests:`` —
shipped under SUMMARY Q7.2 manager-default (un-listed; flagged in PR
body as a §27.4 errata candidate).

Covers every schema in the consolidated module:

- §3.2 ``GovernancePaths`` (incl. ``min_length=1`` on ``governance_paths``)
  and ``HoneypotRuleEntry`` (which is also un-listed in ``governs.contracts``).
- §3.4.3 ``LoosenedAxis`` + ``MonotonicCheckResult``.
- §3.6.1 ``GovernanceChangeLogEntry`` (incl. the ``author_tier`` Literal
  union and ``monotonic_check_result`` Literal union).
- §3.6.3 ``HoneypotRule`` + ``HoneypotViolation``.
- §6.4.1 ``WeakeningKind`` (all 14 enum values per ADR) + ``WeakeningFinding``.

Every model verifies round-trip and ``extra="forbid"`` rejection.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.governance import (
    GovernanceChangeLogEntry,
    GovernancePaths,
    HoneypotRule,
    HoneypotRuleEntry,
    HoneypotViolation,
    LoosenedAxis,
    MonotonicCheckResult,
    WeakeningFinding,
    WeakeningKind,
)

# --------------------------------------------------------------------------- #
# §3.2 — GovernancePaths + HoneypotRuleEntry                                  #
# --------------------------------------------------------------------------- #


def test_honeypot_rule_entry_round_trip() -> None:
    entry = HoneypotRuleEntry(
        path=".governance-paths.yaml",
        marker_pattern="# CANARY-DO-NOT-MODIFY: TRIPWIRE-RULE",
    )
    restored = HoneypotRuleEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


def test_honeypot_rule_entry_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        HoneypotRuleEntry.model_validate({"path": "x", "marker_pattern": "y", "extra": "boom"})


def test_governance_paths_requires_at_least_one_path() -> None:
    with pytest.raises(ValidationError):
        GovernancePaths(governance_paths=[])


def test_governance_paths_defaults_honeypots_to_empty() -> None:
    obj = GovernancePaths(governance_paths=["docs/adr/**"])
    assert obj.version == 1
    assert obj.honeypot_canaries == []


def test_governance_paths_rejects_non_1_version() -> None:
    with pytest.raises(ValidationError):
        GovernancePaths(version=2, governance_paths=["docs/adr/**"])  # type: ignore[arg-type]


def test_governance_paths_with_honeypots() -> None:
    obj = GovernancePaths(
        governance_paths=["docs/adr/**", "AGENTS.md"],
        honeypot_canaries=[
            HoneypotRuleEntry(
                path=".governance-paths.yaml",
                marker_pattern="# CANARY-DO-NOT-MODIFY: TRIPWIRE-RULE",
            )
        ],
    )
    assert len(obj.honeypot_canaries) == 1


def test_governance_paths_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        GovernancePaths.model_validate({"governance_paths": ["docs/adr/**"], "extra": "boom"})


# --------------------------------------------------------------------------- #
# §3.4.3 — LoosenedAxis + MonotonicCheckResult                                #
# --------------------------------------------------------------------------- #


def test_loosened_axis_accepts_unconstrained_string() -> None:
    """SUMMARY X1 manager-default: axis is unconstrained str.

    Semantic enforcement of the 14 canonical axes from §3.4.1 lives at
    the tool layer (TC-1E.3), not in the schema.
    """
    axis = LoosenedAxis(
        axis="any-arbitrary-axis-string",
        before_value="0.90",
        after_value="0.80",
        file="pyproject.toml",
    )
    assert axis.axis == "any-arbitrary-axis-string"
    assert axis.line is None


def test_loosened_axis_round_trip_with_line() -> None:
    axis = LoosenedAxis(
        axis="coverage_threshold",
        before_value="0.90",
        after_value="0.80",
        file="pyproject.toml",
        line=42,
    )
    restored = LoosenedAxis.model_validate_json(axis.model_dump_json())
    assert restored == axis


def test_loosened_axis_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        LoosenedAxis.model_validate(
            {
                "axis": "x",
                "before_value": "a",
                "after_value": "b",
                "file": "f",
                "extra": "boom",
            }
        )


def test_monotonic_check_result_defaults() -> None:
    obj = MonotonicCheckResult(
        has_loosening_approved_trailer=False,
        overall_blocking=False,
    )
    assert obj.loosened == []
    assert obj.approver_handle is None
    assert obj.approver_is_tier2_verified is False
    assert obj.companion_addendum_pr is None
    assert obj.contradiction_audit_clean is False


def test_monotonic_check_result_round_trip() -> None:
    obj = MonotonicCheckResult(
        loosened=[
            LoosenedAxis(
                axis="coverage_threshold",
                before_value="0.90",
                after_value="0.80",
                file="pyproject.toml",
            )
        ],
        has_loosening_approved_trailer=True,
        approver_handle="@jiazhenz026",
        approver_is_tier2_verified=True,
        companion_addendum_pr=12345,
        contradiction_audit_clean=True,
        overall_blocking=False,
    )
    restored = MonotonicCheckResult.model_validate_json(obj.model_dump_json())
    assert restored == obj


def test_monotonic_check_result_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        MonotonicCheckResult.model_validate(
            {
                "has_loosening_approved_trailer": False,
                "overall_blocking": False,
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# §3.6.1 — GovernanceChangeLogEntry                                           #
# --------------------------------------------------------------------------- #


def _valid_change_log() -> GovernanceChangeLogEntry:
    return GovernanceChangeLogEntry(
        sha="abc1234",
        timestamp=datetime(2026, 5, 18, tzinfo=UTC),
        author_handle="@jiazhenz026",
        author_tier="human-tier-2",
        runtime="claude-code",
        files_changed=["CLAUDE.md"],
        diff_summary="+2/-1",
        governance_paths_touched=["CLAUDE.md"],
        has_approval_trailer=True,
        approver_handle="@jiazhenz026",
        approval_pr=999,
        monotonic_check_result="ok",
        contradiction_audit_clean=True,
        honeypot_intact=True,
    )


def test_governance_change_log_round_trip() -> None:
    entry = _valid_change_log()
    restored = GovernanceChangeLogEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


def test_governance_change_log_runtime_optional() -> None:
    payload = _valid_change_log().model_dump()
    payload["runtime"] = None
    obj = GovernanceChangeLogEntry.model_validate(payload)
    assert obj.runtime is None


@pytest.mark.parametrize("tier", ["agent", "human-tier-1", "human-tier-2"])
def test_governance_change_log_author_tier_literal_accepts(tier: str) -> None:
    payload = _valid_change_log().model_dump()
    payload["author_tier"] = tier
    obj = GovernanceChangeLogEntry.model_validate(payload)
    assert obj.author_tier == tier


def test_governance_change_log_author_tier_rejects_other() -> None:
    payload = _valid_change_log().model_dump()
    payload["author_tier"] = "super-user"
    with pytest.raises(ValidationError):
        GovernanceChangeLogEntry.model_validate(payload)


@pytest.mark.parametrize("result", ["ok", "loosening-approved", "loosening-rejected"])
def test_governance_change_log_monotonic_result_literal(result: str) -> None:
    payload = _valid_change_log().model_dump()
    payload["monotonic_check_result"] = result
    obj = GovernanceChangeLogEntry.model_validate(payload)
    assert obj.monotonic_check_result == result


def test_governance_change_log_monotonic_result_rejects_other() -> None:
    payload = _valid_change_log().model_dump()
    payload["monotonic_check_result"] = "unknown"
    with pytest.raises(ValidationError):
        GovernanceChangeLogEntry.model_validate(payload)


def test_governance_change_log_rejects_extras() -> None:
    payload = _valid_change_log().model_dump(mode="json")
    payload["extra_field"] = "boom"
    with pytest.raises(ValidationError):
        GovernanceChangeLogEntry.model_validate(payload)


# --------------------------------------------------------------------------- #
# §3.6.3 — HoneypotRule + HoneypotViolation                                   #
# --------------------------------------------------------------------------- #


def test_honeypot_rule_round_trip() -> None:
    rule = HoneypotRule(
        path=".governance-paths.yaml",
        marker_pattern="# CANARY-DO-NOT-MODIFY: TRIPWIRE-RULE",
        expected_sha256="deadbeef" * 8,
        last_verified=datetime(2026, 5, 18, tzinfo=UTC),
    )
    restored = HoneypotRule.model_validate_json(rule.model_dump_json())
    assert restored == rule


def test_honeypot_rule_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        HoneypotRule.model_validate(
            {
                "path": "p",
                "marker_pattern": "m",
                "expected_sha256": "s",
                "last_verified": "2026-05-18T00:00:00Z",
                "extra": "boom",
            }
        )


@pytest.mark.parametrize("action", ["auto-revert", "block-pr", "notify-only"])
def test_honeypot_violation_action_literal(action: str) -> None:
    obj = HoneypotViolation(
        rule_path=".governance-paths.yaml",
        violating_commit_sha="abc1234",
        violating_author="some-bot",
        action_taken=action,  # type: ignore[arg-type]
    )
    assert obj.action_taken == action


def test_honeypot_violation_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        HoneypotViolation(
            rule_path=".governance-paths.yaml",
            violating_commit_sha="abc1234",
            violating_author="some-bot",
            action_taken="explode",  # type: ignore[arg-type]
        )


def test_honeypot_violation_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        HoneypotViolation.model_validate(
            {
                "rule_path": "p",
                "violating_commit_sha": "s",
                "violating_author": "a",
                "action_taken": "auto-revert",
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# §6.4.1 — WeakeningKind + WeakeningFinding                                   #
# --------------------------------------------------------------------------- #


def test_weakening_kind_values_match_adr() -> None:
    """ADR-043 §6.4.1 declares exactly these 14 categories."""
    expected = {
        "deleted-test-file",
        "removed-test-function",
        "lowered-coverage-threshold",
        "lowered-mutation-threshold",
        "unjustified-skip-or-xfail",
        "disabled-lint-rule",
        "disabled-typecheck-flag",
        "disabled-precommit-hook",
        "removed-ci-job",
        "increased-pytest-timeout",
        "expanded-exemption-paths",
        "expanded-noqa-usage",
        "reduced-skill-list",
        "reduced-honeypot-count",
    }
    assert {w.value for w in WeakeningKind} == expected


def test_weakening_finding_round_trip() -> None:
    finding = WeakeningFinding(
        kind=WeakeningKind.LOWERED_COVERAGE_THRESHOLD,
        file="pyproject.toml",
        line=27,
        before_value="0.90",
        after_value="0.80",
        has_loosening_approval=False,
        blocking=True,
    )
    restored = WeakeningFinding.model_validate_json(finding.model_dump_json())
    assert restored == finding


def test_weakening_finding_line_optional() -> None:
    finding = WeakeningFinding(
        kind=WeakeningKind.REMOVED_CI_JOB,
        file=".github/workflows/test.yml",
        before_value="present",
        after_value="absent",
        has_loosening_approval=True,
        blocking=False,
    )
    assert finding.line is None


def test_weakening_finding_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        WeakeningFinding.model_validate(
            {
                "kind": "deleted-test-file",
                "file": "f",
                "before_value": "a",
                "after_value": "b",
                "has_loosening_approval": False,
                "blocking": True,
                "extra": "boom",
            }
        )
