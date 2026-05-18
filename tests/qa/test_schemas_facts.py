"""Tests for ``scieasy.qa.schemas.facts`` (ADR-042 §7.5).

Covers:

- Every ``Field(...)`` constraint (positive + negative boundaries).
- ``schema_version: Literal[1]`` rejecting non-1 values.
- ``extra="forbid"`` on every sub-model.
- Round-trip via ``model_dump_json`` / ``model_validate_json``.
- JSON Schema export (Draft 2020-12).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scieasy.qa.schemas.facts import (
    ADRFacts,
    FactsRegistry,
    MaintainersFacts,
    SkillFacts,
    ToolFacts,
    WorkflowFacts,
)

# --------------------------------------------------------------------------- #
# WorkflowFacts                                                               #
# --------------------------------------------------------------------------- #


def _valid_workflow() -> WorkflowFacts:
    return WorkflowFacts(
        stage_count=7,
        stages=[
            "intent",
            "issue",
            "change_plan",
            "branch",
            "implement_validate",
            "docs_changelog",
            "submit_pr",
        ],
        blocking_validations={"intent": ["intent_clear"], "submit_pr": ["pr_open"]},
    )


def test_workflow_facts_minimum_stage_count() -> None:
    WorkflowFacts(stage_count=1, stages=["one"], blocking_validations={})


def test_workflow_facts_rejects_zero_stage_count() -> None:
    with pytest.raises(ValidationError):
        WorkflowFacts(stage_count=0, stages=[], blocking_validations={})


def test_workflow_facts_rejects_negative_stage_count() -> None:
    with pytest.raises(ValidationError):
        WorkflowFacts(stage_count=-1, stages=[], blocking_validations={})


def test_workflow_facts_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        WorkflowFacts(
            stage_count=1,
            stages=["x"],
            blocking_validations={},
            extra_field="nope",
        )


# --------------------------------------------------------------------------- #
# ToolFacts                                                                   #
# --------------------------------------------------------------------------- #


def _valid_tool() -> ToolFacts:
    return ToolFacts(
        python_version="3.12",
        min_coverage_percent=70,
        lint_rules=["E", "F"],
        type_checkers=["mypy", "pyright"],
        docs_engine="sphinx",
    )


@pytest.mark.parametrize("value", [0, 1, 50, 99, 100])
def test_tool_facts_coverage_bounds_inclusive(value: int) -> None:
    ToolFacts(
        python_version="3.12",
        min_coverage_percent=value,
        lint_rules=[],
        type_checkers=[],
        docs_engine="sphinx",
    )


@pytest.mark.parametrize("value", [-1, 101, 200])
def test_tool_facts_coverage_out_of_range(value: int) -> None:
    with pytest.raises(ValidationError):
        ToolFacts(
            python_version="3.12",
            min_coverage_percent=value,
            lint_rules=[],
            type_checkers=[],
            docs_engine="sphinx",
        )


def test_tool_facts_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ToolFacts(
            python_version="3.12",
            min_coverage_percent=50,
            lint_rules=[],
            type_checkers=[],
            docs_engine="sphinx",
            stray="x",
        )


# --------------------------------------------------------------------------- #
# ADRFacts                                                                    #
# --------------------------------------------------------------------------- #


def _valid_adr() -> ADRFacts:
    return ADRFacts(
        total_count=44,
        by_status={"Accepted": 30, "Draft": 14},
        latest_adr_number=44,
    )


def test_adr_facts_round_trip() -> None:
    src = _valid_adr()
    rebuilt = ADRFacts.model_validate_json(src.model_dump_json())
    assert rebuilt == src


def test_adr_facts_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        ADRFacts(total_count=1, by_status={}, latest_adr_number=1, extra=True)


# --------------------------------------------------------------------------- #
# MaintainersFacts                                                            #
# --------------------------------------------------------------------------- #


def test_maintainers_facts_basic() -> None:
    m = MaintainersFacts(entry_count=10, human_count=4, paths_covered_count=20)
    assert m.entry_count == 10


def test_maintainers_facts_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        MaintainersFacts(
            entry_count=1,
            human_count=1,
            paths_covered_count=1,
            other=1,
        )


# --------------------------------------------------------------------------- #
# SkillFacts                                                                  #
# --------------------------------------------------------------------------- #


def test_skill_facts_basic() -> None:
    s = SkillFacts(
        required_skills=["adr-router", "doc-drift-guard"],
        installed_per_runtime={"claude": ["adr-router"], "cursor": ["adr-router"]},
    )
    assert s.required_skills[0] == "adr-router"


def test_skill_facts_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        SkillFacts(
            required_skills=[],
            installed_per_runtime={},
            unexpected="x",
        )


# --------------------------------------------------------------------------- #
# FactsRegistry                                                               #
# --------------------------------------------------------------------------- #


def _valid_registry() -> FactsRegistry:
    return FactsRegistry(
        generated_at=datetime(2026, 5, 18, 12, 0, 0, tzinfo=UTC),
        source_shas={"workflow": "abc123", "adr": "def456"},
        workflow=_valid_workflow(),
        tool=_valid_tool(),
        adr=_valid_adr(),
        maintainers=MaintainersFacts(entry_count=1, human_count=1, paths_covered_count=1),
        skill=SkillFacts(required_skills=[], installed_per_runtime={}),
    )


def test_facts_registry_schema_version_default_is_one() -> None:
    assert _valid_registry().schema_version == 1


def test_facts_registry_schema_version_accepts_one_explicitly() -> None:
    reg = FactsRegistry(
        schema_version=1,
        generated_at=datetime(2026, 5, 18, tzinfo=UTC),
        source_shas={},
        workflow=_valid_workflow(),
        tool=_valid_tool(),
        adr=_valid_adr(),
        maintainers=MaintainersFacts(entry_count=0, human_count=0, paths_covered_count=0),
        skill=SkillFacts(required_skills=[], installed_per_runtime={}),
    )
    assert reg.schema_version == 1


@pytest.mark.parametrize("bad", [0, 2, 99])
def test_facts_registry_rejects_other_schema_versions(bad: int) -> None:
    with pytest.raises(ValidationError):
        FactsRegistry(
            schema_version=bad,
            generated_at=datetime(2026, 5, 18, tzinfo=UTC),
            source_shas={},
            workflow=_valid_workflow(),
            tool=_valid_tool(),
            adr=_valid_adr(),
            maintainers=MaintainersFacts(entry_count=0, human_count=0, paths_covered_count=0),
            skill=SkillFacts(required_skills=[], installed_per_runtime={}),
        )


def test_facts_registry_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        FactsRegistry(
            generated_at=datetime(2026, 5, 18, tzinfo=UTC),
            source_shas={},
            workflow=_valid_workflow(),
            tool=_valid_tool(),
            adr=_valid_adr(),
            maintainers=MaintainersFacts(entry_count=0, human_count=0, paths_covered_count=0),
            skill=SkillFacts(required_skills=[], installed_per_runtime={}),
            rogue="field",
        )


def test_facts_registry_round_trip() -> None:
    src = _valid_registry()
    rebuilt = FactsRegistry.model_validate_json(src.model_dump_json())
    assert rebuilt == src


def test_facts_registry_json_schema_exports() -> None:
    schema = FactsRegistry.model_json_schema()
    assert schema["title"] == "FactsRegistry"
    # Each nested sub-model surfaces in $defs.
    assert "WorkflowFacts" in schema["$defs"]
    assert "ToolFacts" in schema["$defs"]
    assert "ADRFacts" in schema["$defs"]
    assert "MaintainersFacts" in schema["$defs"]
    assert "SkillFacts" in schema["$defs"]
