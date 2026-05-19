"""Strict ADR and spec frontmatter schemas from ADR-042."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Translation(BaseModel):
    """Translation record embedded in ADR/spec frontmatter."""

    model_config = ConfigDict(extra="forbid")

    locale: str
    path: str
    auto_generated: bool
    source_sha: str | None

    @field_validator("locale")
    @classmethod
    def _locale_shape(cls, value: str) -> str:
        if not value or " " in value:
            raise ValueError("locale must be a non-empty BCP-47-like string")
        return value

    @field_validator("path")
    @classmethod
    def _translation_path_under_docs_locale(cls, value: str) -> str:
        normalised = value.replace("\\", "/")
        if not normalised.startswith("docs/"):
            raise ValueError("translation path must live under docs/<locale>/")
        return normalised


class GovernedSurfaces(BaseModel):
    """Governed modules, symbols, entry points, files, and exclusions."""

    model_config = ConfigDict(extra="forbid")

    modules: list[str] = Field(default_factory=list)
    contracts: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)

    @field_validator("modules", "contracts", mode="before")
    @classmethod
    def _default_missing_symbol_lists(cls, value: object) -> object:
        return [] if value is None else value

    @field_validator("modules", "contracts", "entry_points", "files", "excludes")
    @classmethod
    def _strip_and_reject_empty(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = raw.strip()
            if not value:
                raise ValueError("governed surface entries must be non-empty strings")
            if value in seen:
                raise ValueError(f"duplicate governed surface entry: {value}")
            seen.add(value)
            cleaned.append(value)
        return cleaned


class ADRFrontmatter(BaseModel):
    """ADR frontmatter contract from ADR-042 Section 3.3."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    adr: int = Field(gt=0)
    title: str = Field(min_length=4, max_length=160)
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
    language_source: Literal["en"] = "en"
    translations: list[Translation]

    @model_validator(mode="after")
    def _status_dates_match(self) -> ADRFrontmatter:
        if self.status == "Accepted" and self.date_accepted is None:
            raise ValueError("status=Accepted requires date_accepted")
        if self.status != "Accepted" and self.date_accepted is not None:
            raise ValueError("date_accepted must be null unless status=Accepted")
        if self.status == "Superseded":
            if self.date_superseded is None:
                raise ValueError("status=Superseded requires date_superseded")
            if self.superseded_by is None:
                raise ValueError("status=Superseded requires superseded_by")
        if self.status != "Superseded":
            if self.date_superseded is not None:
                raise ValueError("date_superseded must be null unless status=Superseded")
            if self.superseded_by is not None:
                raise ValueError("superseded_by must be null unless status=Superseded")
        return self

    @model_validator(mode="after")
    def _implementation_expectations(self) -> ADRFrontmatter:
        if self.is_code_implementation:
            if self.tracking_issue is None:
                raise ValueError("is_code_implementation=true requires tracking_issue")
            if not self.tests:
                raise ValueError("is_code_implementation=true requires tests")
        return self


class SpecScope(BaseModel):
    """SpecKit-compatible scope record."""

    model_config = ConfigDict(extra="forbid")

    in_: list[str] = Field(alias="in")
    out: list[str]


class SpecFrontmatter(BaseModel):
    """Spec frontmatter contract from ADR-042 Section 3.4."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    spec_id: str = Field(min_length=3)
    title: str = Field(min_length=4, max_length=160)
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
    language_source: Literal["en"] = "en"
