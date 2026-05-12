"""Three-tier system prompt composition for the embedded agent.

The final ``--append-system-prompt`` passed to the provider CLI is the
ordered concatenation of (spec / ADR-033 §3 D3):

1. The builtin prompt (this module).
2. ``{project}/.scieasy/system_prompt.md`` if present.
3. ``{project}/.scieasy/system_prompt.local.md`` if present.

The builtin prompt itself is split into four sections (A / B / C / D
per ADR-033 §3 D3.2). Phase 1 ships the section constants as empty
strings; T-ECA-204 (Phase 2) populates them with the canonical
end-user-facing text and implements the section-C tool enumeration
sourced from the runtime MCP tool registry.

The deliberate omissions from the builtin prompt — anything from
``CLAUDE.md``, SpecKit, conventional commit / branch / changelog
discipline — are documented in ADR-033 §3 D3.3.
"""

from __future__ import annotations

from pathlib import Path

SECTION_A_IDENTITY: str = ""
"""Section A — Identity & scope. Populated in T-ECA-204."""

SECTION_B_CORE_CONCEPTS: str = ""
"""Section B — SciEasy core concepts (block model, type system, references). Populated in T-ECA-204."""

SECTION_C_AVAILABLE_TOOLS: str = ""
"""Section C — Available tools. Generated from the MCP tool registry at runtime. Populated in T-ECA-204."""

SECTION_D_WORKING_PRINCIPLES: str = ""
"""Section D — Working principles (production-mode agent discipline). Populated in T-ECA-204."""


def compose_system_prompt(project_dir: Path) -> str:
    """Build the final ``--append-system-prompt`` payload for a session.

    Parameters
    ----------
    project_dir
        Absolute path to the SciEasy project workspace; used to read
        the optional ``system_prompt.md`` and ``system_prompt.local.md``
        overlay files under ``.scieasy/``.

    Returns
    -------
    str
        The composed prompt (builtin + project overlay + project-local
        overlay).

    Raises
    ------
    NotImplementedError
        Always, in Phase 1. Implementation lands in T-ECA-204.
    """
    raise NotImplementedError("compose_system_prompt is implemented in T-ECA-204")
