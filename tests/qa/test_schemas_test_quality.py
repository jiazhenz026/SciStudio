"""Tests for ``scieasy.qa.schemas.test_quality`` (ADR-043 §4.2)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.test_quality import (
    AntiPattern,
    AntiPatternFinding,
    MutationScoreResult,
    TestQualityReport,
)

# --------------------------------------------------------------------------- #
# AntiPattern                                                                 #
# --------------------------------------------------------------------------- #


def test_anti_pattern_values_match_adr() -> None:
    """ADR-043 §4.2.1 declares exactly these 10 categories."""
    expected = {
        "no-assert",
        "assert-not-none-only",
        "mocks-the-subject",
        "asserts-on-mock-call-count-only",
        "hardcoded-magic-without-comment",
        "test-name-says-validates-but-no-related-assert",
        "exception-test-without-exception-match",
        "snapshot-without-reasoning",
        "excessive-mocks",
        "test-also-provides-ground-truth",
    }
    assert {p.value for p in AntiPattern} == expected


# --------------------------------------------------------------------------- #
# AntiPatternFinding                                                          #
# --------------------------------------------------------------------------- #


def test_anti_pattern_finding_round_trip() -> None:
    finding = AntiPatternFinding(
        pattern=AntiPattern.NO_ASSERT,
        test_file="tests/test_foo.py",
        test_function="test_thing",
        line=12,
        severity="error",
        description="Function has no assert.",
        suggested_fix="Add an assert covering the post-condition.",
    )
    restored = AntiPatternFinding.model_validate_json(finding.model_dump_json())
    assert restored == finding


@pytest.mark.parametrize("sev", ["error", "warning"])
def test_anti_pattern_finding_accepts_severity_literal(sev: str) -> None:
    obj = AntiPatternFinding(
        pattern=AntiPattern.NO_ASSERT,
        test_file="t.py",
        test_function="t",
        line=1,
        severity=sev,  # type: ignore[arg-type]
        description="x",
    )
    assert obj.severity == sev


def test_anti_pattern_finding_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        AntiPatternFinding(
            pattern=AntiPattern.NO_ASSERT,
            test_file="t.py",
            test_function="t",
            line=1,
            severity="info",  # type: ignore[arg-type]
            description="x",
        )


def test_anti_pattern_finding_suggested_fix_optional() -> None:
    obj = AntiPatternFinding(
        pattern=AntiPattern.NO_ASSERT,
        test_file="t.py",
        test_function="t",
        line=1,
        severity="warning",
        description="x",
    )
    assert obj.suggested_fix is None


def test_anti_pattern_finding_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        AntiPatternFinding.model_validate(
            {
                "pattern": "no-assert",
                "test_file": "t.py",
                "test_function": "t",
                "line": 1,
                "severity": "error",
                "description": "x",
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# MutationScoreResult                                                         #
# --------------------------------------------------------------------------- #


def test_mutation_score_result_round_trip() -> None:
    obj = MutationScoreResult(
        package="scieasy.qa",
        mutations_total=100,
        mutations_killed=80,
        mutations_survived=15,
        mutations_timeout=5,
        score=0.80,
        threshold=0.75,
        passed=True,
    )
    restored = MutationScoreResult.model_validate_json(obj.model_dump_json())
    assert restored == obj


def test_mutation_score_result_score_must_be_in_unit_interval() -> None:
    with pytest.raises(ValidationError):
        MutationScoreResult(
            package="p",
            mutations_total=1,
            mutations_killed=0,
            mutations_survived=0,
            mutations_timeout=0,
            score=1.5,
            threshold=0.5,
            passed=False,
        )
    with pytest.raises(ValidationError):
        MutationScoreResult(
            package="p",
            mutations_total=1,
            mutations_killed=0,
            mutations_survived=0,
            mutations_timeout=0,
            score=-0.1,
            threshold=0.5,
            passed=False,
        )


def test_mutation_score_result_accepts_boundary_scores() -> None:
    for score in (0.0, 1.0):
        obj = MutationScoreResult(
            package="p",
            mutations_total=0,
            mutations_killed=0,
            mutations_survived=0,
            mutations_timeout=0,
            score=score,
            threshold=0.5,
            passed=False,
        )
        assert obj.score == score


def test_mutation_score_result_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        MutationScoreResult.model_validate(
            {
                "package": "p",
                "mutations_total": 0,
                "mutations_killed": 0,
                "mutations_survived": 0,
                "mutations_timeout": 0,
                "score": 0.0,
                "threshold": 0.5,
                "passed": False,
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# TestQualityReport                                                           #
# --------------------------------------------------------------------------- #


def test_test_quality_report_round_trip() -> None:
    report = TestQualityReport(
        generated_at=datetime(2026, 5, 18, tzinfo=UTC),
        anti_pattern_findings=[
            AntiPatternFinding(
                pattern=AntiPattern.NO_ASSERT,
                test_file="t.py",
                test_function="t",
                line=1,
                severity="error",
                description="x",
            )
        ],
        mutation_scores=[
            MutationScoreResult(
                package="p",
                mutations_total=0,
                mutations_killed=0,
                mutations_survived=0,
                mutations_timeout=0,
                score=0.0,
                threshold=0.5,
                passed=False,
            )
        ],
        dead_fixtures=["unused_fixture"],
        property_test_coverage={"scieasy.qa.foo.bar": True},
        overall_passed=False,
    )
    restored = TestQualityReport.model_validate_json(report.model_dump_json())
    assert restored == report
    assert restored.schema_version == 1


def test_test_quality_report_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        TestQualityReport.model_validate(
            {
                "generated_at": "2026-05-18T00:00:00Z",
                "anti_pattern_findings": [],
                "mutation_scores": [],
                "dead_fixtures": [],
                "property_test_coverage": {},
                "overall_passed": True,
                "extra": "boom",
            }
        )


def test_test_quality_report_purely_structural_no_cross_field_validator() -> None:
    """SUMMARY TC-1A.8 manager-default: no model_validator enforces
    mutations_total == killed + survived + timeout. Verify by accepting an
    intentionally inconsistent record."""
    report = TestQualityReport(
        generated_at=datetime(2026, 5, 18, tzinfo=UTC),
        anti_pattern_findings=[],
        mutation_scores=[
            MutationScoreResult(
                package="p",
                mutations_total=999,  # inconsistent — but accepted at schema layer
                mutations_killed=1,
                mutations_survived=1,
                mutations_timeout=1,
                score=0.33,
                threshold=0.5,
                passed=False,
            )
        ],
        dead_fixtures=[],
        property_test_coverage={},
        overall_passed=True,  # overall_passed is independent here
    )
    # No exception → confirms schema is structural-only.
    assert report.overall_passed is True
