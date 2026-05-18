"""Pydantic models for the ``MAINTAINERS`` ownership file.

ADR-042 §6 describes ``MAINTAINERS`` as the reverse-direction companion
to ADR ``governs.modules`` / ``governs.files``: a YAML file at repo root
that maps file globs to owning ADRs, human approvers, and AI runtimes
allowed to edit. ``Maintainers``/``MaintainersEntry`` here are the
pydantic shape; consumption (closure check, agent authorization) lives
in later Phase 1 tools.

References
----------
ADR-042 §6.1 — purpose (reverse-ownership / closure / agent auth).
ADR-042 §6.2 — schema (this file's authoritative source).
ADR-042 §6.4 — glob semantics.
ADR-042 §6.5 — multi-match resolution.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Audit fix C1: shared primitives moved to ._common to break the circular
# import that previously existed between frontmatter.py and maintainers.py.
from ._common import ADRRef, GitHandle, PathGlob


class AgentRuntime(StrEnum):
    """Enumeration of the AI coding runtimes the QA regime recognises.

    The set is deliberately closed; adding a runtime requires an ADR-042
    §27.4 errata amendment plus a corresponding entry in the cross-runtime
    installer (ADR-042 §17). See §5.4.1 for how ``agent_editable=allowlist``
    consumes this enum.
    """

    CLAUDE = "Claude"
    CODEX = "Codex"
    CURSOR = "Cursor"
    AIDER = "Aider"
    GEMINI = "Gemini"


class MaintainersEntry(BaseModel):
    """One row of ``MAINTAINERS``: a glob plus its owning ADRs/humans/agents.

    ``excludes`` carves negation out of ``path_glob``; the entry's
    effective coverage is ``glob_match(path_glob) - sum(glob_match(excludes))``
    per ADR-042 §6.4.
    """

    model_config = ConfigDict(extra="forbid")

    path_glob: PathGlob
    adrs: list[ADRRef] = Field(default_factory=list)
    humans: list[GitHandle] = Field(default_factory=list)
    agents_allowed: list[AgentRuntime] = Field(default_factory=list)
    excludes: list[PathGlob] = Field(default_factory=list)
    notes: str | None = None


class Maintainers(BaseModel):
    """Top-level shape of the ``MAINTAINERS`` YAML file.

    ``version`` is a literal ``1`` so future schema revisions can be
    discriminated by upcoming pydantic ``Discriminator`` tooling. ``entries``
    is required non-empty (audit fix I1).
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    entries: list[MaintainersEntry] = Field(min_length=1)
