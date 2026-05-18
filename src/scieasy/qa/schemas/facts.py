"""Pydantic models for the QA facts registry (ADR-042 §7.5).

The facts registry is the structured manifest produced by per-namespace
extractors (``scripts/audit/extract_workflow_facts.py``,
``extract_tool_facts.py``, ``extract_adr_facts.py``,
``extract_maintainers_facts.py``, ``extract_skill_facts.py``) and
aggregated into ``docs/facts/generated.yaml`` by
``scripts/audit/generate_facts.py`` (ADR-042 §7.5.3).

Downstream consumers:

- ``fact_drift.check_substitutions`` (Phase 1B.3) reads
  ``FactsRegistry`` to enforce numeric/string substitutions in prose.
- ``trailer_lint.run`` (Phase 1B.5) consults
  ``facts.workflow.phase3_cutoff_sha`` once the workflow extractor
  populates it (Phase 1H.8 follow-up; not modelled in this v1 schema).

References
----------
ADR-042 §7.5.1 — design rationale for the facts registry.
ADR-042 §7.5.2 (lines 1142-1196) — authoritative pydantic models for
this file (verbatim).
ADR-042 §7.5.3 — generation pipeline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowFacts(BaseModel):
    """Extracted facts about the ``.workflow/`` gate machinery."""

    model_config = ConfigDict(extra="forbid")

    stage_count: int = Field(ge=1)
    stages: list[str]
    blocking_validations: dict[str, list[str]]


class ToolFacts(BaseModel):
    """Extracted facts about the project's tool stack (lint, types, docs)."""

    model_config = ConfigDict(extra="forbid")

    python_version: str
    min_coverage_percent: int = Field(ge=0, le=100)
    lint_rules: list[str]
    type_checkers: list[str]
    docs_engine: str


class ADRFacts(BaseModel):
    """Extracted facts about the ADR corpus (counts, status histogram, latest)."""

    model_config = ConfigDict(extra="forbid")

    total_count: int
    by_status: dict[str, int]
    latest_adr_number: int


class MaintainersFacts(BaseModel):
    """Extracted facts about the ``MAINTAINERS`` ownership file."""

    model_config = ConfigDict(extra="forbid")

    entry_count: int
    human_count: int
    paths_covered_count: int


class SkillFacts(BaseModel):
    """Extracted facts about installed skills across runtimes."""

    model_config = ConfigDict(extra="forbid")

    required_skills: list[str]
    installed_per_runtime: dict[str, list[str]]


class FactsRegistry(BaseModel):
    """Top-level envelope persisted to ``docs/facts/generated.yaml``.

    ``schema_version`` is a ``Literal[1]`` — bumping the version is a
    breaking change that flows through an explicit ADR amendment.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    generated_at: datetime
    source_shas: dict[str, str]
    workflow: WorkflowFacts
    tool: ToolFacts
    adr: ADRFacts
    maintainers: MaintainersFacts
    skill: SkillFacts
