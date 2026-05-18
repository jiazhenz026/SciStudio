"""Tests for ``scieasy.qa.schemas.tracker`` (ADR-043 §2.2).

NOTE: this test file is NOT listed in ADR-043 frontmatter ``tests:`` —
shipped under SUMMARY Q1A.6 manager-default (un-listed; flagged in PR
body as a §27.4 errata candidate).

Covers:

- Every ``SectionStatus`` enum value can be assigned and round-trips.
- ``RequiredArtifacts`` accepts empty + populated lists; rejects extras.
- ``TrackerEntry`` accepts the four optional fields; rejects extras.
- ``ImplementationTracker`` accepts ``schema_version=1`` default; rejects extras.
- Round-trip via ``model_dump_json`` / ``model_validate_json``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.tracker import (
    ImplementationTracker,
    RequiredArtifacts,
    SectionStatus,
    TrackerEntry,
    VerificationCheck,
)

# --------------------------------------------------------------------------- #
# SectionStatus                                                               #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    [
        SectionStatus.NOT_STARTED,
        SectionStatus.IN_PROGRESS,
        SectionStatus.IMPLEMENTED,
        SectionStatus.VERIFIED,
    ],
)
def test_section_status_round_trip(value: SectionStatus) -> None:
    """Every enum value should be accepted on a TrackerEntry."""
    entry = TrackerEntry(
        section="§1",
        requires_artifacts=RequiredArtifacts(),
        verification_checks=[],
        status=value,
        verifier_command="echo ok",
    )
    payload = entry.model_dump_json()
    restored = TrackerEntry.model_validate_json(payload)
    assert restored.status == value


def test_section_status_values_match_adr() -> None:
    """ADR-043 §2.2 declares exactly these four values, in this order."""
    assert [s.value for s in SectionStatus] == [
        "not_started",
        "in_progress",
        "implemented",
        "verified",
    ]


# --------------------------------------------------------------------------- #
# RequiredArtifacts                                                           #
# --------------------------------------------------------------------------- #


def test_required_artifacts_defaults_to_empty_lists() -> None:
    obj = RequiredArtifacts()
    assert obj.files == []
    assert obj.symbols == []
    assert obj.tests == []


def test_required_artifacts_accepts_populated_lists() -> None:
    obj = RequiredArtifacts(
        files=["src/scieasy/qa/schemas/tracker.py"],
        symbols=["scieasy.qa.schemas.tracker.ImplementationTracker"],
        tests=["tests/qa/test_schemas_tracker.py"],
    )
    assert obj.files == ["src/scieasy/qa/schemas/tracker.py"]
    assert obj.symbols == ["scieasy.qa.schemas.tracker.ImplementationTracker"]


def test_required_artifacts_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RequiredArtifacts.model_validate({"files": [], "extra_field": "boom"})


# --------------------------------------------------------------------------- #
# VerificationCheck                                                           #
# --------------------------------------------------------------------------- #


def test_verification_check_round_trip() -> None:
    obj = VerificationCheck(id="V1", description="phase_gate passes")
    payload = obj.model_dump_json()
    restored = VerificationCheck.model_validate_json(payload)
    assert restored == obj


def test_verification_check_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        VerificationCheck.model_validate({"id": "V1", "description": "x", "other": "y"})


# --------------------------------------------------------------------------- #
# TrackerEntry                                                                #
# --------------------------------------------------------------------------- #


def _minimal_entry(**overrides: object) -> TrackerEntry:
    base: dict[str, object] = {
        "section": "§5",
        "requires_artifacts": RequiredArtifacts(),
        "verification_checks": [],
        "status": SectionStatus.NOT_STARTED,
        "verifier_command": "echo ok",
    }
    base.update(overrides)
    return TrackerEntry(**base)  # type: ignore[arg-type]


def test_tracker_entry_optional_fields_default_to_none() -> None:
    entry = _minimal_entry()
    assert entry.implemented_in_pr is None
    assert entry.verified_at is None
    assert entry.verifier_skill is None


def test_tracker_entry_accepts_optional_fields() -> None:
    when = datetime(2026, 5, 18, tzinfo=UTC)
    entry = _minimal_entry(
        status=SectionStatus.VERIFIED,
        implemented_in_pr=1131,
        verified_at=when,
        verifier_skill="scieasy-skill-creator",
    )
    assert entry.implemented_in_pr == 1131
    assert entry.verified_at == when
    assert entry.verifier_skill == "scieasy-skill-creator"


def test_tracker_entry_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        TrackerEntry.model_validate(
            {
                "section": "§5",
                "requires_artifacts": {},
                "verification_checks": [],
                "status": "not_started",
                "verifier_command": "echo ok",
                "extra": "boom",
            }
        )


# --------------------------------------------------------------------------- #
# ImplementationTracker                                                       #
# --------------------------------------------------------------------------- #


def test_implementation_tracker_round_trip() -> None:
    tracker = ImplementationTracker(
        adr=42,
        sections=[
            _minimal_entry(section="§5"),
            _minimal_entry(section="§6", status=SectionStatus.IN_PROGRESS),
        ],
    )
    assert tracker.schema_version == 1
    payload = tracker.model_dump_json()
    restored = ImplementationTracker.model_validate_json(payload)
    assert restored == tracker


def test_implementation_tracker_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        ImplementationTracker.model_validate(
            {
                "adr": 42,
                "sections": [],
                "extra": "boom",
            }
        )


def test_implementation_tracker_accepts_explicit_schema_version() -> None:
    tracker = ImplementationTracker(adr=42, schema_version=1, sections=[])
    assert tracker.schema_version == 1


def test_adr_ref_range_enforced_via_tracker() -> None:
    """ADRRef is Annotated[int, ge=1, le=9999]; surface via tracker."""
    with pytest.raises(ValidationError):
        ImplementationTracker(adr=0, sections=[])  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ImplementationTracker(adr=10000, sections=[])  # type: ignore[arg-type]
