"""Tests for ``scieasy.qa.schemas.classification`` (ADR-043 §6.1-§6.3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.classification import (
    AssessmentRubric,
    BoundaryLevel,
    DataClass,
    DataClassification,
    DataClassificationEntry,
    PathBoundary,
    PathBoundaryEntry,
    RubricCriterion,
)

# --------------------------------------------------------------------------- #
# §6.1 — DataClassification                                                   #
# --------------------------------------------------------------------------- #


def test_data_class_values_match_adr() -> None:
    """ADR-043 §6.1 declares exactly these seven categories."""
    expected = {
        "public",
        "internal",
        "user-data",
        "secrets",
        "model-artifacts",
        "generated-code",
        "test-fixtures",
    }
    assert {c.value for c in DataClass} == expected


def test_data_classification_entry_round_trip() -> None:
    entry = DataClassificationEntry(
        path_glob="src/**",
        data_class=DataClass.PUBLIC,
        description="Public code.",
    )
    restored = DataClassificationEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry
    assert restored.handling_constraint is None


def test_data_classification_entry_with_handling_constraint() -> None:
    entry = DataClassificationEntry(
        path_glob=".github/secrets/**",
        data_class=DataClass.SECRETS,
        description="Never read in code.",
        handling_constraint="Inject only via GH Actions",
    )
    assert entry.handling_constraint == "Inject only via GH Actions"


def test_data_classification_entry_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        DataClassificationEntry.model_validate(
            {
                "path_glob": "x",
                "data_class": "public",
                "description": "y",
                "extra": "boom",
            }
        )


def test_data_classification_aggregates_entries() -> None:
    section = DataClassification(
        entries=[
            DataClassificationEntry(
                path_glob="src/**",
                data_class=DataClass.PUBLIC,
                description="ok",
            ),
            DataClassificationEntry(
                path_glob="docs/identity/humans.yml",
                data_class=DataClass.USER_DATA,
                description="edit-blocked",
                handling_constraint="CODEOWNERS-gated",
            ),
        ]
    )
    assert len(section.entries) == 2
    payload = section.model_dump_json()
    restored = DataClassification.model_validate_json(payload)
    assert restored == section


def test_data_classification_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        DataClassification.model_validate({"entries": [], "extra": "boom"})


# --------------------------------------------------------------------------- #
# §6.2 — AssessmentRubric                                                     #
# --------------------------------------------------------------------------- #


def test_rubric_criterion_round_trip() -> None:
    obj = RubricCriterion(
        id="R1",
        description="All new code has docstrings",
        verification_command="interrogate src/",
        blocking=True,
    )
    restored = RubricCriterion.model_validate_json(obj.model_dump_json())
    assert restored == obj


def test_rubric_criterion_defaults() -> None:
    obj = RubricCriterion(id="R1", description="x")
    assert obj.verification_command is None
    assert obj.blocking is True


def test_rubric_criterion_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        RubricCriterion.model_validate({"id": "R1", "description": "x", "extra": "boom"})


def test_assessment_rubric_aggregates_criteria() -> None:
    rubric = AssessmentRubric(
        scope="root",
        criteria=[
            RubricCriterion(id="R1", description="x", verification_command="cmd"),
            RubricCriterion(id="R2", description="y"),
        ],
    )
    assert len(rubric.criteria) == 2
    restored = AssessmentRubric.model_validate_json(rubric.model_dump_json())
    assert restored == rubric


def test_assessment_rubric_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        AssessmentRubric.model_validate({"scope": "root", "criteria": [], "extra": "boom"})


# --------------------------------------------------------------------------- #
# §6.3 — PathBoundary                                                         #
# --------------------------------------------------------------------------- #


def test_boundary_level_values_match_adr() -> None:
    assert {b.value for b in BoundaryLevel} == {"always", "ask-first", "never"}


def test_path_boundary_entry_round_trip() -> None:
    entry = PathBoundaryEntry(
        path_glob="src/scieasy/**",
        level=BoundaryLevel.ALWAYS,
        reason="Free edit; tests required",
    )
    restored = PathBoundaryEntry.model_validate_json(entry.model_dump_json())
    assert restored == entry


def test_path_boundary_entry_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        PathBoundaryEntry.model_validate({"path_glob": "x", "level": "always", "reason": "r", "extra": "boom"})


def test_path_boundary_aggregates_entries() -> None:
    boundary = PathBoundary(
        entries=[
            PathBoundaryEntry(
                path_glob="src/scieasy/**",
                level=BoundaryLevel.ALWAYS,
                reason="ok",
            ),
            PathBoundaryEntry(
                path_glob="docs/adr/**",
                level=BoundaryLevel.ASK_FIRST,
                reason="ADR change requires approval",
            ),
            PathBoundaryEntry(
                path_glob="docs/identity/humans.yml",
                level=BoundaryLevel.NEVER,
                reason="user-data",
            ),
        ]
    )
    assert len(boundary.entries) == 3
    restored = PathBoundary.model_validate_json(boundary.model_dump_json())
    assert restored == boundary


def test_path_boundary_rejects_extras() -> None:
    with pytest.raises(ValidationError):
        PathBoundary.model_validate({"entries": [], "extra": "boom"})
