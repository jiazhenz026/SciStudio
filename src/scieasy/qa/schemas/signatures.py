"""Expected signature schemas for ADR-042 signature drift checks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExpectedParameter(BaseModel):
    """One expected callable parameter."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str
    annotation: str | None = None
    default: str | None = None
    required: bool = True

    @field_validator("name", "kind")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("parameter fields must be non-empty")
        return value.strip()


class ExpectedSignature(BaseModel):
    """Expected function, method, or class signature extracted from a spec."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    kind: Literal["function", "class"]
    parameters: list[ExpectedParameter] = Field(default_factory=list)
    return_annotation: str | None = None
    source_path: str
    line: int

    @field_validator("subject", "source_path")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("signature fields must be non-empty")
        return value.strip()
