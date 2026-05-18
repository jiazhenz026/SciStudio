"""AGENTS.md required-section schemas (ADR-043 §6).

Three required AGENTS.md sections, with one pydantic group each:

- §6.1 — ``## Data classification`` (``DataClass`` + ``DataClassificationEntry``
  + ``DataClassification``).
- §6.2 — ``## Assessment rubric`` (``RubricCriterion`` + ``AssessmentRubric``).
- §6.3 — ``## Paths`` three-tier boundary marker (``BoundaryLevel``
  + ``PathBoundaryEntry`` + ``PathBoundary``).

Per SUMMARY ``X3`` / Q1A.9 manager defaults the vestigial ``Literal``
import in §6.2 and ``Field`` imports unused in §6.1 / §6.2 / §6.3 are
dropped here (recorded as deviation in PR body for cycle audit).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# §6.1 — Data classification
# ---------------------------------------------------------------------------


class DataClass(StrEnum):
    """Sensitivity / handling class for a path glob in an AGENTS.md."""

    PUBLIC = "public"
    INTERNAL = "internal"
    USER_DATA = "user-data"
    SECRETS = "secrets"
    MODEL_ARTIFACTS = "model-artifacts"
    GENERATED_CODE = "generated-code"
    TEST_FIXTURES = "test-fixtures"


class DataClassificationEntry(BaseModel):
    """One row in the ``## Data classification`` table."""

    model_config = ConfigDict(extra="forbid")

    path_glob: str
    data_class: DataClass
    description: str
    handling_constraint: str | None = None


class DataClassification(BaseModel):
    """The ``## Data classification`` section as a whole."""

    model_config = ConfigDict(extra="forbid")

    entries: list[DataClassificationEntry]


# ---------------------------------------------------------------------------
# §6.2 — Assessment rubric
# ---------------------------------------------------------------------------


class RubricCriterion(BaseModel):
    """One concrete done-criterion an agent must self-check before claiming task complete."""

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    verification_command: str | None = None
    blocking: bool = True


class AssessmentRubric(BaseModel):
    """The ``## Assessment rubric`` section as a whole."""

    model_config = ConfigDict(extra="forbid")

    scope: str
    criteria: list[RubricCriterion]


# ---------------------------------------------------------------------------
# §6.3 — Three-tier Path Boundary
# ---------------------------------------------------------------------------


class BoundaryLevel(StrEnum):
    """Path-edit permission tier.

    Per the §6.3 table:

    - ``ALWAYS`` (✅) — agent may freely edit.
    - ``ASK_FIRST`` (⚠️) — agent must obtain explicit approval first.
    - ``NEVER`` (🚫) — agent must refuse, even with approval.
    """

    ALWAYS = "always"
    ASK_FIRST = "ask-first"
    NEVER = "never"


class PathBoundaryEntry(BaseModel):
    """One row in the ``## Paths`` boundary table."""

    model_config = ConfigDict(extra="forbid")

    path_glob: str
    level: BoundaryLevel
    reason: str


class PathBoundary(BaseModel):
    """The ``## Paths`` section as a whole."""

    model_config = ConfigDict(extra="forbid")

    entries: list[PathBoundaryEntry]
