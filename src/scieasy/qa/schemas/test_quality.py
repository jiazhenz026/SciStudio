"""Test-quality schemas (ADR-043 §4.2).

Backs the AST anti-pattern detector at
``src/scieasy/qa/test_quality/ast_lint.py`` and the mutation runner
integration (``mutmut`` / ``mutmut-result``).

Per SUMMARY TC-1A.8 manager default the schema is purely structural —
no ``model_validator`` enforces
``mutations_total == killed + survived + timeout``; semantic invariants
are tool-layer concerns.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AntiPattern(StrEnum):
    """Test-code anti-patterns flagged by the AST linter.

    Each enum value mirrors the §4.2.1 table verbatim.
    """

    NO_ASSERT = "no-assert"
    ASSERT_NOT_NONE_ONLY = "assert-not-none-only"
    MOCKS_THE_SUBJECT = "mocks-the-subject"
    ASSERTS_ON_MOCK_CALL_ONLY = "asserts-on-mock-call-count-only"
    HARDCODED_MAGIC_WITHOUT_COMMENT = "hardcoded-magic-without-comment"
    TEST_NAME_CLAIM_MISMATCH = "test-name-says-validates-but-no-related-assert"
    RAISES_WITHOUT_MATCH = "exception-test-without-exception-match"
    SNAPSHOT_WITHOUT_REASONING = "snapshot-without-reasoning"
    EXCESSIVE_MOCKS = "excessive-mocks"
    TEST_ALSO_PROVIDES_GROUND_TRUTH = "test-also-provides-ground-truth"


class AntiPatternFinding(BaseModel):
    """One AST-level anti-pattern occurrence."""

    model_config = ConfigDict(extra="forbid")

    pattern: AntiPattern
    test_file: str
    test_function: str
    line: int
    severity: Literal["error", "warning"]
    description: str
    suggested_fix: str | None = None


class MutationScoreResult(BaseModel):
    """Mutation-testing score result for one package."""

    model_config = ConfigDict(extra="forbid")

    package: str
    mutations_total: int
    mutations_killed: int
    mutations_survived: int
    mutations_timeout: int
    score: float = Field(ge=0.0, le=1.0)
    threshold: float
    passed: bool


class TestQualityReport(BaseModel):
    """Top-level report aggregating AST findings + mutation scores + property coverage."""

    # Suppress pytest's auto-collection of any class named ``Test*`` — this
    # is a pydantic model, not a test class.
    __test__ = False

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    generated_at: datetime
    anti_pattern_findings: list[AntiPatternFinding]
    mutation_scores: list[MutationScoreResult]
    dead_fixtures: list[str]
    property_test_coverage: dict[str, bool]  # function -> has @given test
    overall_passed: bool
