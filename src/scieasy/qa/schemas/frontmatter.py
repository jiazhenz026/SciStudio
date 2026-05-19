"""ADR-042 frontmatter schemas."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Translation(BaseModel):
    locale: str
    path: str
    auto_generated: bool
    source_sha: str | None


class GovernedSurfaces(BaseModel):
    modules: list[str]
    contracts: list[str]
    entry_points: list[str] = Field(default_factory=list)
    files: list[str]
    excludes: list[str] = Field(default_factory=list)


class ADRFrontmatter(BaseModel):
    adr: int
    title: str
    status: Literal["Proposed", "Accepted", "Deprecated", "Superseded"]
    date_created: date
    date_accepted: date | None
    date_superseded: date | None
    supersedes: list[int]
    superseded_by: int | None
    related: list[int]
    closes_issues: list[int]
    tracking_issue: int | None
    is_code_implementation: bool
    governs: GovernedSurfaces
    tests: list[str]
    agent_editable: bool | Literal["owner-only"]
    assisted_by: list[str]
    phase: Literal["planning", "implementation", "complete", "maintenance"]
    tags: list[str]
    owner: str
    co_authors: list[str]
    language_source: str = "en"
    translations: list[Translation | Mapping[str, Any]]

    @field_validator("adr")
    @classmethod
    def _positive_adr(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("adr must be positive")
        return value

    @field_validator("title")
    @classmethod
    def _title_length(cls, value: str) -> str:
        if not 4 <= len(value) <= 160:
            raise ValueError("title must be 4-160 characters")
        return value

    @field_validator("tags")
    @classmethod
    def _tags_are_slugs(cls, value: list[str]) -> list[str]:
        for tag in value:
            if tag.lower() != tag or " " in tag:
                raise ValueError("tags must be lowercase slugs")
        return value

    @model_validator(mode="after")
    def _status_dates(self) -> ADRFrontmatter:
        if self.status == "Accepted" and self.date_accepted is None:
            raise ValueError("Accepted ADRs must set date_accepted")
        if self.status == "Proposed" and self.date_accepted is not None:
            raise ValueError("Proposed ADRs must not set date_accepted")
        if self.status == "Superseded":
            if self.date_superseded is None or self.superseded_by is None:
                raise ValueError("Superseded ADRs must set date_superseded and superseded_by")
        elif self.date_superseded is not None:
            raise ValueError("Only Superseded ADRs may set date_superseded")
        if self.is_code_implementation and not self.tests:
            raise ValueError("implementation ADRs must list tests")
        return self


class SpecScope(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    in_: list[str] = Field(alias="in")
    out: list[str]


class SpecFrontmatter(BaseModel):
    spec_id: str
    title: str
    status: Literal["Draft", "Clarifying", "Planned", "Implemented", "Deprecated"]
    feature_branch: str
    created: date
    input: str
    owners: list[str]
    related_adrs: list[int]
    related_specs: list[str]
    scope: SpecScope
    governs: GovernedSurfaces
    tests: list[str]
    acceptance_source: Literal["speckit", "issue", "adr", "manual"]
    language_source: str = "en"


def _load_yaml_frontmatter(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path} has no YAML frontmatter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            loaded = yaml.safe_load("\n".join(lines[1:index])) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"{path} frontmatter is not a mapping")
            return loaded
    raise ValueError(f"{path} has unclosed YAML frontmatter")


def load_adr_frontmatter(path: Path) -> ADRFrontmatter:
    return ADRFrontmatter.model_validate(_load_yaml_frontmatter(path))


def load_spec_frontmatter(path: Path) -> SpecFrontmatter:
    return SpecFrontmatter.model_validate(_load_yaml_frontmatter(path))
