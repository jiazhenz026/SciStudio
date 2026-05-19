"""Facts registry schemas for ADR-042 consistency tooling."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

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
DriftClass = Literal[
    "match",
    "behavior-drift",
    "phantom-reference",
    "missing-documentation",
    "signature-drift",
]


class Fact(BaseModel):
    id: str
    kind: FactKind
    source: str
    subject: str
    value: Any
    owner: str | None = None
    generated_at: datetime
    source_sha: str
    confidence: FactConfidence
    stability: FactStability = "unknown"


class FactsRegistry(BaseModel):
    schema_version: str = "1"
    generated_at: datetime
    source_sha: str
    facts: list[Fact] = Field(default_factory=list)

    def by_id(self) -> dict[str, Fact]:
        return {fact.id: fact for fact in self.facts}

    def find(self, *, kind: FactKind | None = None, subject: str | None = None) -> list[Fact]:
        return [
            fact
            for fact in self.facts
            if (kind is None or fact.kind == kind) and (subject is None or fact.subject == subject)
        ]


def load_facts(path: Path) -> FactsRegistry:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return FactsRegistry.model_validate(raw)


def write_facts(registry: FactsRegistry, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = registry.model_dump(mode="json")
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
