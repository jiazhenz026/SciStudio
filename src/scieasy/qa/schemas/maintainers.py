"""MAINTAINERS schema primitives from ADR-042 section 6."""

from __future__ import annotations

from enum import StrEnum


class AgentRuntime(StrEnum):
    """AI runtimes that may be allowlisted for governance-owned files."""

    CLAUDE = "Claude"
    CODEX = "Codex"
    CURSOR = "Cursor"
    AIDER = "Aider"
    GEMINI = "Gemini"


__all__ = ["AgentRuntime"]
