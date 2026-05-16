"""Top-level orchestration entry point (ADR-040 §3.8).

The orchestrator coordinates per-project provisioning:

  - CLAUDE.md + AGENTS.md (§3.5)         → ``claude_agents_md.py``
  - .claude/settings.json + hook scripts (§3.6) → ``hooks.py``
  - Skill cross-install to .claude/skills + .agents/skills (§3.4/§3.5/§3.8) → ``skills.py``
  - .codex/config.toml (§3.7)            → ``codex_config.py``

A version-marker file at ``<project>/.claude/.scieasy-provision-version``
governs upgrade behavior on later SciEasy releases (§9 OQ-1; design
deferred to Phase 3, see #1013).

Per ADR §7, failures are NOT fatal — they log at WARNING and return a
``ProvisionResult`` summarizing what succeeded. Callers continue with
project open / create flow regardless.

S40c skeleton: all bodies raise NotImplementedError. I40c (#1013)
implements the real flow in Phase 2a.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# TODO(#1011): bump SCIEASY_PROVISION_VERSION on the first real release.
#   Out of scope per ADR-040 §3.8 / §9 OQ-1 (version-marker upgrade design
#   deferred to Phase 3). Followup: open as part of ADR-040 Phase 3.
SCIEASY_PROVISION_VERSION = "0.1.0-skeleton"


@dataclass
class ProvisionResult:
    """Structured result of a provisioning run.

    Fields:
      written        — list of project-relative paths that were created.
      skipped        — list of project-relative paths that already existed
                       and were preserved (force=False).
      failed         — list of ``(path, reason)`` tuples for sub-steps that
                       errored. Surfacing failures here (instead of raising)
                       supports ADR §7 non-fatal degraded mode.
      version        — value written to the marker file
                       ``<project>/.claude/.scieasy-provision-version``.
    """

    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    version: str = SCIEASY_PROVISION_VERSION


def install_project_agent_assets(
    project_dir: Path,
    *,
    force: bool = False,
) -> ProvisionResult:
    """Install all prod-env agent assets into ``project_dir``.

    Inputs:
      project_dir : Path to the SciEasy project root (already exists).
      force       : When True, overwrite existing files. Default False
                    preserves user customizations on idempotent top-up
                    paths (e.g. ``open_project`` re-entry).

    Outputs (files written under ``project_dir``):
      - CLAUDE.md           (§3.5; ~50-line guide)
      - AGENTS.md           (§3.5; identical content; Codex mirror)
      - .claude/settings.json   (§3.6; PreToolUse + PostToolUse hook config)
      - .claude/hooks/*.py      (§3.6; 6 hook scripts — 3 PreToolUse, 3 PostToolUse)
      - .claude/skills/scieasy/<6 dirs>/SKILL.md   (§3.4 + §3.8)
      - .agents/skills/scieasy/<6 dirs>/SKILL.md   (§3.4 + §3.8; Codex mirror)
      - .codex/config.toml      (§3.7; project-scope MCP)
      - .claude/.scieasy-provision-version  (version marker; §3.8 + §9 OQ-1)

    Returns:
      ProvisionResult — summarizes written/skipped/failed paths plus the
      version stamp. Never raises (per ADR §7 degraded-mode contract);
      sub-step failures are recorded in ``ProvisionResult.failed`` and
      surfaced upstream as logger.warning calls.

    Idempotency:
      With force=False (default), every sub-writer checks file existence
      before writing. Already-present files are appended to
      ``ProvisionResult.skipped``. This is the contract for the
      open_project idempotent top-up path (ADR §3.8 third row).

    Error handling:
      The orchestrator catches per-step exceptions (claude_agents_md,
      hooks, skills, codex_config), records them in ProvisionResult.failed,
      and continues with the next sub-step. The caller in api/runtime.py /
      cli/main.py only needs to wrap the whole call in its own try/except
      defensive pattern.

    Version marker:
      The marker file ``.claude/.scieasy-provision-version`` is rewritten
      on every run (its value is the constant ``SCIEASY_PROVISION_VERSION``).
      Phase 3 design (deferred per #1011) decides whether to use the marker
      to detect stale provisioning and re-write specific files.
    """
    # TODO(#1013): I40c Phase 2a — implement the orchestration per ADR
    # §3.8. Out of scope per ADR-040 §3.8 (S40c skeleton).
    # Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
    raise NotImplementedError("S40c skeleton — I40c impl in Phase 2a (#1013)")
