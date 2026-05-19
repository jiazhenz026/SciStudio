"""Maintainer ownership schemas for ADR-042 closure checks."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class MaintainerRule(BaseModel):
    pattern: str
    owners: list[str]
    required_reviewers: int = 1
    protected: bool = False


class Maintainers(BaseModel):
    schema_version: str = "1"
    rules: list[MaintainerRule] = Field(default_factory=list)


def load_maintainers(path: Path) -> Maintainers:
    if not path.exists():
        return Maintainers()
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return Maintainers()
    loaded = yaml.safe_load(text) or {}
    if isinstance(loaded, list):
        loaded = {"rules": loaded}
    if not isinstance(loaded, dict):
        raise ValueError("MAINTAINERS must be a mapping or list of rules")
    return Maintainers.model_validate(loaded)
