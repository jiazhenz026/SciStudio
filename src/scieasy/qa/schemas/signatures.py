"""Expected signature schemas for ADR-042 signature drift checks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ParameterSpec(BaseModel):
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


ExpectedParameter = ParameterSpec


class ExpectedSignature(BaseModel):
    """Expected function, method, or class signature extracted from a spec."""

    model_config = ConfigDict(extra="forbid")

    subject: str
    kind: Literal["function", "class", "attribute"]
    parameters: list[ParameterSpec] = Field(default_factory=list)
    return_annotation: str | None = None
    source_path: str
    line: int

    @field_validator("subject", "source_path")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("signature fields must be non-empty")
        return value.strip()


class ExpectedModelField(BaseModel):
    """Expected Pydantic model field extracted from a spec."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model_symbol: str
    field_name: str
    annotation: str
    default: str | None = None
    required: bool = True
    source_spec: str
    source_line: int


class ExpectedCliCommand(BaseModel):
    """Expected CLI command and exit-code contract extracted from a spec."""

    model_config = ConfigDict(extra="forbid")

    command: list[str] = Field(min_length=1)
    module: str | None = None
    expected_exit_codes: dict[int, str] = Field(default_factory=dict)
    source_spec: str
    source_line: int
