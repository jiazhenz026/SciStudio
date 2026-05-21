"""Maintainer ownership schemas for ADR-042 governance checks."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MaintainerRule(BaseModel):
    """One path ownership and review-routing rule."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    pattern: str
    owners: list[str] = Field(min_length=1)
    required_reviewers: int = Field(default=1, ge=1)
    protected: bool = False

    @field_validator("pattern")
    @classmethod
    def _pattern_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("maintainer pattern must be non-empty")
        return value.strip()

    @field_validator("owners")
    @classmethod
    def _owners_non_empty(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = raw.strip()
            if not value:
                raise ValueError("maintainer owners must be non-empty strings")
            if value in seen:
                raise ValueError(f"duplicate maintainer owner: {value}")
            seen.add(value)
            cleaned.append(value)
        return cleaned


class Maintainers(BaseModel):
    """Repository maintainer ownership registry."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    rules: list[MaintainerRule] = Field(default_factory=list)
