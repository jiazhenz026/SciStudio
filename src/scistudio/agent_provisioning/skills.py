"""Write multi-skill split to both provider trees (ADR-040 §3.4 + §3.5 + §3.8).

Per ADR §3.4, the monolithic ``SKILL.md`` is split into 1 base index +
task-scoped skills. ADR-048 SPEC 2 adds ``scistudio-write-plot``, taking
the bundle to 1 base + 6 task-scoped skills (7 total). Per ADR §3.8, all
are auto-installed under both:

  - ``<project>/.claude/skills/<name>/SKILL.md`` (Claude Code)
  - ``<project>/.agents/skills/<name>/SKILL.md`` (Codex)

Skills land FLAT under ``skills/`` rather than nested under
``skills/scistudio/`` because Claude Code's skill discovery
(https://code.claude.com/docs/en/skills) and Codex Skills
(https://developers.openai.com/codex/skills) both walk one level only.
The skill named ``scistudio`` keeps its own ``scistudio/`` directory at this
top level; task skills sit beside it as siblings. Discovered during
ADR-040 Phase 4 e2e — the original ADR §3.5/§3.8 nested layout caused
``Skill(scistudio-write-block) -> Unknown skill`` because the agent's
skill registry never recursed into ``skills/scistudio/``.

Skill names (per ADR §3.4):

  1. scistudio                  — base index
  2. scistudio-build-workflow   — design a new workflow
  3. scistudio-write-block      — author a custom block (#875 + §3.4 port rules)
  4. scistudio-debug-run        — diagnose a failed run
  5. scistudio-inspect-data     — explore data references / lineage
  6. scistudio-project-qa       — project structure / docs Q&A
  7. scistudio-write-plot       — author a preview-only plot job (ADR-048 SPEC 2)

Source resolution (I40c):

  Skill source content lives at ``src/scistudio/_skills/scistudio/<name>/SKILL.md``
  per ADR §3.4. That tree is owned by the Skills track (Phase 2b — S40b
  scaffolds; I40b authors body in Phase 2c). On this implementation
  branch, the Skills track has NOT yet merged, so the source tree is
  partially absent. Resolution strategy:

    1. importlib.resources lookup in ``scistudio._skills.scistudio.<name>``
       (primary, wheel-safe per #824).
    2. Walk-up filesystem lookup for ``<repo>/_skills/scistudio/<name>/SKILL.md``.
    3. Walk-up filesystem lookup for ``<repo>/src/scistudio/_skills/scistudio/<name>/SKILL.md``.
    4. Legacy monolithic ``<repo>/skills/scistudio/SKILL.md`` is used for the
       base ``scistudio`` skill IF the multi-skill source is not yet present
       (Phase 2c relocates content into ``_skills/``).
    5. Placeholder body (marked with ``TODO(#1013)``) for any name that
       none of the above resolves to. Each placeholder embeds a
       reference to the Phase 2c followup.

# TODO(#1013): post-cascade cleanup once Skills track merges to main:
#   collapse fallback chain to importlib.resources-only. The dual-path
#   logic is a sequencing accommodation for parallel-track development.
#   Followup: https://github.com/zjzcpj/SciStudio/issues/1013.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

_SKILL_NAMES = (
    "scistudio",
    "scistudio-build-workflow",
    "scistudio-write-block",
    "scistudio-debug-run",
    "scistudio-inspect-data",
    "scistudio-project-qa",
    "scistudio-write-plot",
)

_DEST_TREES = (
    ".claude/skills",
    ".agents/skills",
)


def _placeholder_skill_body(name: str) -> str:
    """Generate a placeholder body (with ``TODO(#1013)`` marker) for a skill not yet sourced.

    Phase 2c (I40b) authors the real bodies and removes the need for this
    fallback (the importlib.resources path will resolve instead).
    """
    return (
        f"---\nname: {name}\ndescription: |\n"
        f"  SciStudio task-scoped skill ({name}). Content authored in\n"
        f"  ADR-040 Phase 2c (#1013 followup).\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"<!-- TODO(#1013): Phase 2c (I40b) — author real body per\n"
        f"     ADR-040 §3.4 skill-design investigation.\n"
        f"     Followup: https://github.com/zjzcpj/SciStudio/issues/1013. -->\n\n"
        f"This is a placeholder. The real body lands when the Skills track\n"
        f"(`track/adr-040/skills`) merges into main. Until then, refer to\n"
        f"the legacy monolithic skill at `skills/scistudio/SKILL.md` in the\n"
        f"SciStudio source tree, or to `CLAUDE.md` / `AGENTS.md` at the project\n"
        f"root for the core rules.\n"
    )


def _read_skill_source(name: str) -> str:
    """Resolve and read the SKILL.md content for ``name``.

    See module docstring for the resolution order. Returns a placeholder
    body if no source is found; never raises FileNotFoundError for the
    common case (lets idempotent top-up proceed even before Skills track
    merges).
    """
    # The base "scistudio" skill lives at the top of the _skills/scistudio/
    # package (no extra subdir); task-scoped skills live one level deeper.
    package_path = "scistudio._skills.scistudio" if name == "scistudio" else f"scistudio._skills.scistudio.{name}"
    try:
        return importlib.resources.files(package_path).joinpath("SKILL.md").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, NotADirectoryError):
        pass

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates = [
            parent / "_skills" / "scistudio" / name / "SKILL.md",
            parent / "src" / "scistudio" / "_skills" / "scistudio" / name / "SKILL.md",
        ]
        # Skills track layout: the base "scistudio" skill lives directly at
        # _skills/scistudio/SKILL.md (no extra "scistudio/" subdir).
        if name == "scistudio":
            candidates.extend(
                [
                    parent / "_skills" / "scistudio" / "SKILL.md",
                    parent / "src" / "scistudio" / "_skills" / "scistudio" / "SKILL.md",
                ]
            )
        for candidate in candidates:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        if (parent / "pyproject.toml").is_file():
            break

    if name == "scistudio":
        for parent in here.parents:
            candidate = parent / "skills" / "scistudio" / "SKILL.md"
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
            if (parent / "pyproject.toml").is_file():
                break

    return _placeholder_skill_body(name)


def write_skills(
    project_dir: Path,
    *,
    force: bool = False,
) -> list[str]:
    """Cross-install the SciStudio skill bundle to both provider trees.

    With 7 skill names (1 base + 6 task skills, including the ADR-048
    ``scistudio-write-plot`` plot skill) cross-installed to both
    ``.claude/skills`` and ``.agents/skills``, a fresh install writes 14
    files.

    Returns:
      List of project-relative paths actually written (max 14 entries).
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    sources = {name: _read_skill_source(name) for name in _SKILL_NAMES}

    for tree in _DEST_TREES:
        for name in _SKILL_NAMES:
            rel_path = f"{tree}/{name}/SKILL.md"
            dest = project_dir / rel_path
            if dest.exists() and not force:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(sources[name], encoding="utf-8")
            written.append(rel_path)

    return written
