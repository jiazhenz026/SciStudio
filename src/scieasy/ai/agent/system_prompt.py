"""Three-tier system prompt composition for the embedded agent.

T-ECA-204. The final ``--append-system-prompt`` passed to the provider
CLI is the ordered concatenation of (spec / ADR-033 §3 D3):

1. The builtin prompt (this module — Sections A / B / C / D from
   ADR-033 §3 D3.2 verbatim, with Section C synthesised from the
   actual registered MCP tool registry so the prompt cannot drift from
   the dispatcher).
2. ``{project}/.scieasy/system_prompt.md`` if present.
3. ``{project}/.scieasy/system_prompt.local.md`` if present
   (gitignored, for per-machine tweaks).

Same inputs (same project_dir, same overlay files, same tool registry)
produce the same string — and therefore the same
``system_prompt_hash`` recorded in session metadata. The
overlay-file mtime is **not** part of the hash; content equality
suffices.

The deliberate omissions from the builtin prompt — anything from
``CLAUDE.md``, SpecKit, conventional commit / branch / changelog
discipline — are documented in ADR-033 §3 D3.3.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

SECTION_A_IDENTITY: str = """\
You are an AI assistant embedded inside SciEasy, an AI-native workflow runtime \
for multimodal scientific data. You help researchers design and run workflows, \
write custom blocks, inspect run results, tune parameters, and answer questions \
about their projects.
"""
"""Section A — Identity & scope (ADR-033 §3 D3.2)."""


SECTION_B_CORE_CONCEPTS: str = """\
SciEasy core concepts:

- Workflows are DAGs of blocks. Each block has typed input_ports and \
output_ports and a JSON Schema config_schema. Six base block categories: io, \
process, code, app, ai, subworkflow.
- Six base data types: Array, Series, DataFrame, Text, Artifact, CompositeData. \
Plugins extend them (e.g. Image is an Array subtype, Spectrum is a Series subtype).
- Data flows as references (StorageReference), not in-memory payloads. Use \
inspect_data / preview_data; never load full arrays into memory.
- Workflow definitions live in {project}/workflows/*.yaml. The runtime is the \
source of truth; the GUI canvas is an editor and a viewer.
- Lineage links artifacts via derived_from. Use get_lineage to trace inputs \
back to their producing blocks.
"""
"""Section B — SciEasy core concepts (ADR-033 §3 D3.2)."""


SECTION_D_WORKING_PRINCIPLES: str = """\
Working principles (production-mode discipline; not developer/maintainer \
discipline — there is nothing in this prompt about commit messages, branches, \
issues, or CI):

1. Plan before acting. For any non-trivial change (new workflow, new block, \
parameter sweep), describe the plan in plain language and wait for user \
confirmation before invoking write tools.
2. Verify before claiming success. After running a workflow, call \
get_run_status and check each block's final state. Don't say "done" on a \
workflow you haven't confirmed completed.
3. Cite real data. When discussing results, fetch them via inspect_data or \
preview_data. Never fabricate numbers, shapes, or column names. If a value is \
unknown, say "I don't know — let me check" and use a tool.
4. Prefer minimal change. Edit the specific block parameter; don't rewrite \
working blocks. Don't introduce abstractions the user didn't ask for.
5. Use SciEasy semantics, not raw file ops. list_blocks beats grep. \
validate_workflow beats reasoning about port types in your head. inspect_data \
beats reading a 50 GB Zarr.
6. Be honest about limits. If a tool call is denied, accept it and ask the \
user how to proceed. If you can't do something, say so. If a tool returned an \
error, report the error verbatim.
7. Respect data scale. Don't load large arrays into memory. preview_data \
returns a thumbnail or first-N rows; that's enough for most reasoning.
8. Never silently overwrite. Before write_workflow / Write / \
update_block_config on an existing artifact, briefly describe the diff or \
confirm it's the intended target.
"""
"""Section D — Working principles (ADR-033 §3 D3.2, full text from §4)."""


# Section C is synthesised at composition time from the actual MCP tool
# registry so the prompt never drifts from the dispatcher. We keep
# ``SECTION_C_AVAILABLE_TOOLS`` as a sentinel constant so the
# ``test_phase1_skeleton.py`` symbol-existence checks keep passing.
SECTION_C_AVAILABLE_TOOLS: str = (
    "(synthesised at runtime from scieasy.ai.agent.mcp._registry; see compose_system_prompt)"
)


_CATEGORY_TITLES = {
    "workflow": "(a) Workflow design & execution",
    "authoring": "(b) Block authoring",
    "inspection": "(c) Run & data inspection",
    "qa": "(d) Project Q&A",
}


def _build_section_c() -> str:
    """Synthesise Section C from the MCP tool registry.

    Imports lazily so this module remains importable when the MCP
    package has not been fully constructed (e.g. during test collection
    on an isolated module).
    """
    from scieasy.ai.agent.mcp._registry import by_category

    lines: list[str] = ["Available tools:", ""]
    grouped = by_category()
    for cat_key in ("workflow", "authoring", "inspection", "qa"):
        if cat_key not in grouped:
            continue
        lines.append(_CATEGORY_TITLES[cat_key])
        for entry in grouped[cat_key]:
            tag = "[write]" if entry.mutation == "write" else "[read]"
            lines.append(f"  - {entry.name} {tag} — {entry.description}")
        lines.append("")
    lines.append(
        "Claude Code native tools (Read, Write, Edit, Glob, Grep, Bash, "
        "WebFetch, WebSearch, Task) are also available. Prefer the MCP "
        "tools above when they apply — they understand SciEasy semantics."
    )
    return "\n".join(lines) + "\n"


def _read_overlay(path: Path) -> str:
    """Read an optional overlay file, returning empty string on absence."""
    try:
        if path.is_file():
            return path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return ""


def compose_system_prompt(project_dir: Path) -> str:
    """Build the final ``--append-system-prompt`` payload for a session.

    The composition is:

    1. Section A + Section B + Section C + Section D (the builtin).
    2. ``{project}/.scieasy/system_prompt.md`` if present.
    3. ``{project}/.scieasy/system_prompt.local.md`` if present.

    Returns
    -------
    str
        The composed prompt. Stable across calls with identical inputs
        — :func:`prompt_hash` produces the same digest.
    """
    project_overlay = _read_overlay(project_dir / ".scieasy" / "system_prompt.md")
    local_overlay = _read_overlay(project_dir / ".scieasy" / "system_prompt.local.md")

    parts: list[str] = [
        SECTION_A_IDENTITY.strip(),
        "",
        SECTION_B_CORE_CONCEPTS.strip(),
        "",
        _build_section_c().strip(),
        "",
        SECTION_D_WORKING_PRINCIPLES.strip(),
    ]
    if project_overlay.strip():
        parts.extend(["", "--- Project overlay (.scieasy/system_prompt.md) ---", project_overlay.strip()])
    if local_overlay.strip():
        parts.extend(["", "--- Per-machine overlay (.scieasy/system_prompt.local.md) ---", local_overlay.strip()])
    return "\n".join(parts) + "\n"


def prompt_hash(prompt: str) -> str:
    """Return a stable SHA-256 hex digest of *prompt*.

    Used by :class:`SessionMetadata` so a session whose system prompt
    changes between turns can be detected (and the conversation
    optionally restarted).
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()
