"""Expected implementation signature schemas for ADR-042."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SignatureKind = Literal["function", "class", "method", "pydantic-model", "cli-command"]


class ParameterSpec(BaseModel):
    name: str
    kind: Literal[
        "positional-only",
        "positional-or-keyword",
        "var-positional",
        "keyword-only",
        "var-keyword",
    ]
    annotation: str | None = None
    default: str | None = None
    required: bool = True


class ExpectedSignature(BaseModel):
    symbol: str
    kind: SignatureKind
    parameters: list[ParameterSpec] = Field(default_factory=list)
    return_annotation: str | None = None
    source_spec: str
    source_line: int


class ExpectedModelField(BaseModel):
    model_symbol: str
    field_name: str
    annotation: str
    default: str | None = None
    required: bool = True
    source_spec: str
    source_line: int


class ExpectedCliCommand(BaseModel):
    command: list[str]
    module: str | None = None
    expected_exit_codes: dict[int, str] = Field(default_factory=dict)
    source_spec: str
    source_line: int
