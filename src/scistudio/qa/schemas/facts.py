"""Facts registry schema for ADR-042 generated repository facts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FactKind = Literal[
    "adr",
    "spec",
    "file",
    "symbol",
    "entry-point",
    "cli",
    "openapi",
    "schema",
    "workflow",
    "maintainer",
    "skill",
    "tool-output",
    "generated-doc",
    "expected-signature",
    "expected-model-field",
    "expected-cli-command",
]

FactConfidence = Literal["normative", "generated", "observed"]
FactStability = Literal["stable", "experimental", "deprecated", "unknown"]


class Fact(BaseModel):
    """One machine-verifiable repository statement."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: FactKind
    source: str
    subject: str
    value: Any
    owner: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_sha: str
    confidence: FactConfidence
    stability: FactStability = "unknown"


class FactsRegistry(BaseModel):
    """Generated facts snapshot consumed by drift and closure tools."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_sha: str
    facts: list[Fact] = Field(default_factory=list)

    def by_id(self) -> dict[str, Fact]:
        return {fact.id: fact for fact in self.facts}

    def find(self, *, kind: FactKind | None = None, subject: str | None = None) -> list[Fact]:
        facts = self.facts
        if kind is not None:
            facts = [fact for fact in facts if fact.kind == kind]
        if subject is not None:
            facts = [fact for fact in facts if fact.subject == subject]
        return facts
