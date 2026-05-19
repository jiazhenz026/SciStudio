"""Shared models for documentation generators."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GeneratorResult(BaseModel):
    generator_id: str
    target_path: str
    content: str
    source_paths: list[str]
    warnings: list[str] = Field(default_factory=list)
    manifest_entry: dict[str, Any] | None = None

    @property
    def generated_marker(self) -> str:
        if self.manifest_entry:
            marker = self.manifest_entry.get("marker")
            if isinstance(marker, str):
                return marker
        return f"<!-- generated-by: {self.generator_id} -->"
