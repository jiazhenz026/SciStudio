"""Write multi-skill split to both provider trees (ADR-040 §3.4 + §3.5 + §3.8).

Per ADR §3.4, the monolithic ``SKILL.md`` is split into 1 base index +
5 task-scoped skills (6 total). Per ADR §3.8, all 6 are auto-installed
under both:

  - ``<project>/.claude/skills/scieasy/<name>/SKILL.md`` (Claude Code)
  - ``<project>/.agents/skills/scieasy/<name>/SKILL.md`` (Codex)

Skill names (per ADR §3.4):

  1. scieasy                  — base index (~50 LOC; tool catalog markers)
  2. scieasy-build-workflow   — design a new workflow
  3. scieasy-write-block      — author a custom block (#875 + §3.4 port rules)
  4. scieasy-debug-run        — diagnose a failed run
  5. scieasy-inspect-data     — explore data references / lineage
  6. scieasy-project-qa       — project structure / docs Q&A

The skill *content* is owned by the Skills track (Phase 2b — S40b
scaffolds the dirs in ``src/scieasy/_skills/``; I40b authors body in
Phase 2c). This module is responsible only for **copying** the
already-prepared files from package resources into the project tree.

S40c skeleton: NotImplementedError stub. I40c (#1013) implements copy.
"""

from __future__ import annotations

from pathlib import Path


def write_skills(
    project_dir: Path,
    *,
    force: bool = False,
) -> list[str]:
    """Cross-install 6 skill files to both provider trees.

    Inputs:
      project_dir : Path to project root.
      force       : True to overwrite; False to preserve.

    Outputs (12 paths total, returned as relative strings):
      - ".claude/skills/scieasy/scieasy/SKILL.md"
      - ".claude/skills/scieasy/scieasy-build-workflow/SKILL.md"
      - ".claude/skills/scieasy/scieasy-write-block/SKILL.md"
      - ".claude/skills/scieasy/scieasy-debug-run/SKILL.md"
      - ".claude/skills/scieasy/scieasy-inspect-data/SKILL.md"
      - ".claude/skills/scieasy/scieasy-project-qa/SKILL.md"
      - ".agents/skills/scieasy/scieasy/SKILL.md"  (Codex mirror)
      - ".agents/skills/scieasy/scieasy-build-workflow/SKILL.md"
      - ".agents/skills/scieasy/scieasy-write-block/SKILL.md"
      - ".agents/skills/scieasy/scieasy-debug-run/SKILL.md"
      - ".agents/skills/scieasy/scieasy-inspect-data/SKILL.md"
      - ".agents/skills/scieasy/scieasy-project-qa/SKILL.md"

    Idempotency (force=False):
      Each destination is checked individually; preserved on existence.

    Source:
      Skill source lives at ``src/scieasy/_skills/scieasy/<name>/SKILL.md``
      after the relocation in ADR §3.4 (owned by Skills track, S40b
      scaffold + I40b content). I40c loads each via
      ``importlib.resources.files("scieasy") / "_skills" / "scieasy"
      / <name> / "SKILL.md"`` to support wheel installs (#824).

    Error handling:
      Missing source files (e.g. if Skills track has not yet shipped the
      relocation) should raise FileNotFoundError. The orchestrator records
      in ``ProvisionResult.failed``; the project still opens. This is a
      known sequencing concern flagged for the integration auditor.
    """
    # TODO(#1013): I40c Phase 2a — implement per ADR §3.4 / §3.8.
    #   Out of scope per ADR-040 §3.8 (S40c skeleton).
    #   Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
    raise NotImplementedError("S40c skeleton — I40c impl in Phase 2a (#1013)")
