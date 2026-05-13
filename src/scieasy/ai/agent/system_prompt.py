"""Three-tier system prompt composition for the embedded agent.

T-ECA-204. The final ``--append-system-prompt`` passed to the provider
CLI is the ordered concatenation of (spec / ADR-033 §3 D3):

1. The builtin prompt body. As of #787 this is sourced from the bundled
   ``skills/scieasy/SKILL.md`` so the embedded GUI agent and any external
   ``claude``/``codex`` consuming the same skill see identical content.
   When the skill file is unavailable (e.g. wheel install without skill
   data — see ``docs/cli-integration.md`` for the install path), we fall
   back to the legacy inline sections so the GUI never goes dark.
2. ``{project}/.scieasy/system_prompt.md`` if present.
3. ``{project}/.scieasy/system_prompt.local.md`` if present
   (gitignored, for per-machine tweaks).

Regardless of source, Section C (the tool catalog) is always
re-synthesised from :mod:`scieasy.ai.agent.mcp._registry` so the prompt
cannot drift from the dispatcher: if the skill file's static catalog
disagrees with the live registry, the live registry wins.

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
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legacy inline sections — fallback only.
#
# Kept verbatim so the contract pinned by tests/ai/test_system_prompt.py
# (e.g. SECTION_A_IDENTITY.strip() non-empty) keeps working. When the
# bundled SKILL.md is present, its body supersedes these; when it's
# absent, these are concatenated together verbatim.
# ---------------------------------------------------------------------------

SECTION_A_IDENTITY: str = """\
You are an AI assistant embedded inside SciEasy, an AI-native workflow runtime \
for multimodal scientific data. You help researchers design and run workflows, \
write custom blocks, inspect run results, tune parameters, and answer questions \
about their projects.
"""
"""Section A — Identity & scope (ADR-033 §3 D3.2). Fallback only."""


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
"""Section B — SciEasy core concepts (ADR-033 §3 D3.2). Fallback only."""


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
"""Section D — Working principles (ADR-033 §3 D3.2, full text from §4). Fallback only."""


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


# ---------------------------------------------------------------------------
# Skill-based body — primary source (#787).
# ---------------------------------------------------------------------------

# Frontmatter delimiter in SKILL.md (YAML-style).
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Markers around the static tool catalog inside SKILL.md. The body
# between these markers is replaced at runtime with the registry-driven
# Section C so the embedded prompt cannot drift from the live tool list.
_TOOL_CATALOG_BEGIN = "<!-- tool_catalog:begin -->"
_TOOL_CATALOG_END = "<!-- tool_catalog:end -->"


def _find_skill_file() -> Path | None:
    """Locate the bundled ``skills/scieasy/SKILL.md`` file.

    Walks up from this module looking for a ``skills/scieasy/SKILL.md``
    relative to a directory containing ``pyproject.toml`` (the repo
    root in editable installs). Returns ``None`` when the file is not
    present (wheel installs without packaged skill data).
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / "scieasy" / "SKILL.md"
        if candidate.is_file():
            return candidate
        if (parent / "pyproject.toml").is_file():
            # Reached repo root without finding the skill file.
            break
    return None


def _strip_frontmatter(text: str) -> str:
    """Drop the YAML frontmatter block from a SKILL.md body."""
    m = _FRONTMATTER_RE.match(text)
    if m is None:
        return text
    return text[m.end() :]


def _splice_live_tool_catalog(body: str) -> str:
    """Replace the static tool catalog with the live registry rendering.

    If markers are not found, leave the body untouched and append the
    live catalog at the end so we never produce a prompt without
    Section C content.
    """
    live = _build_section_c()
    begin = body.find(_TOOL_CATALOG_BEGIN)
    end = body.find(_TOOL_CATALOG_END)
    if begin == -1 or end == -1 or end < begin:
        return body.rstrip() + "\n\n" + live
    # Preserve the marker comments so subsequent rebuilds stay
    # idempotent (the embedded GUI prompt is rebuilt per session).
    head = body[: begin + len(_TOOL_CATALOG_BEGIN)]
    tail = body[end:]
    return head + "\n" + live.rstrip() + "\n" + tail


def _compose_from_skill(skill_path: Path) -> str | None:
    """Build the builtin prompt body from a SKILL.md file, or ``None`` on error."""
    try:
        raw = skill_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("system_prompt: failed to read skill file %s: %s", skill_path, exc)
        return None
    body = _strip_frontmatter(raw)
    return _splice_live_tool_catalog(body).rstrip() + "\n"


def _compose_fallback() -> str:
    """Build the legacy inline prompt body (used when SKILL.md is missing)."""
    parts: list[str] = [
        SECTION_A_IDENTITY.strip(),
        "",
        SECTION_B_CORE_CONCEPTS.strip(),
        "",
        _build_section_c().strip(),
        "",
        SECTION_D_WORKING_PRINCIPLES.strip(),
    ]
    return "\n".join(parts) + "\n"


def _compose_builtin_body() -> str:
    """Build the builtin prompt body — skill file preferred, fallback otherwise."""
    skill_path = _find_skill_file()
    if skill_path is not None:
        body = _compose_from_skill(skill_path)
        if body is not None:
            return body
    logger.warning(
        "system_prompt: skills/scieasy/SKILL.md not found; using inline fallback. "
        "Run 'pip install -e .' from the SciEasy repo, or `scieasy install --skill`, "
        "to make the bundled skill discoverable."
    )
    return _compose_fallback()


def compose_system_prompt(project_dir: Path) -> str:
    """Build the final ``--append-system-prompt`` payload for a session.

    The composition is:

    1. The builtin body (skills/scieasy/SKILL.md, or the legacy
       Sections A + B + C + D when the skill file is absent).
    2. ``{project}/.scieasy/system_prompt.md`` if present.
    3. ``{project}/.scieasy/system_prompt.local.md`` if present.

    Returns
    -------
    str
        The composed prompt. Stable across calls with identical inputs
        — :func:`prompt_hash` produces the same digest.
    """
    builtin = _compose_builtin_body().rstrip()
    project_overlay = _read_overlay(project_dir / ".scieasy" / "system_prompt.md")
    local_overlay = _read_overlay(project_dir / ".scieasy" / "system_prompt.local.md")

    parts: list[str] = [builtin]
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
