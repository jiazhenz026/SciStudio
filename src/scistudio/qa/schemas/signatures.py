"""Expected signature schemas for ADR-042 signature drift checks."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


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

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    subject: str = Field(validation_alias=AliasChoices("subject", "symbol"))
    kind: Literal["function", "class", "method", "attribute", "pydantic-model", "cli-command"]
    parameters: list[ParameterSpec] = Field(default_factory=list)
    return_annotation: str | None = None
    source_path: str = Field(validation_alias=AliasChoices("source_path", "source_spec"))
    line: int = Field(validation_alias=AliasChoices("line", "source_line"))

    @field_validator("subject", "source_path")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("signature fields must be non-empty")
        return value.strip()

    @property
    def symbol(self) -> str:
        """ADR-042 compatibility alias for ``subject``."""

        return self.subject

    @property
    def source_spec(self) -> str:
        """ADR-042 compatibility alias for ``source_path``."""

        return self.source_path

    @property
    def source_line(self) -> int:
        """ADR-042 compatibility alias for ``line``."""

        return self.line


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
