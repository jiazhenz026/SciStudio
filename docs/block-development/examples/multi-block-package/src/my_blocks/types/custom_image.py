"""Custom Array subclass example: AnalysisImage.

Demonstrates how to create a domain-specific Array subclass with:
- Tightened axis schema (required_axes, allowed_axes)
- Typed Meta Pydantic model (frozen, JSON-round-trippable)
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from scistudio.core.types.array import Array


class AnalysisImage(Array):
    """Image type for our analysis pipeline.

    Requires spatial axes (y, x) and optionally supports channels (c).
    Carries analysis-specific metadata in the Meta slot.
    """

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"c", "y", "x"})
    canonical_order: ClassVar[tuple[str, ...]] = ("c", "y", "x")

    class Meta(BaseModel):
        """Per-instance analysis metadata."""

        model_config = ConfigDict(frozen=True)

        source_file: str | None = None
        analysis_method: str | None = None
        quality_score: float | None = None
