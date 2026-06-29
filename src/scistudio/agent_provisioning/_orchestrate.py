"""Top-level orchestration entry point (ADR-040 §3.8).

The orchestrator coordinates per-project provisioning:

  - CLAUDE.md + AGENTS.md (§3.5)         → ``claude_agents_md.py``
  - .claude/settings.json + hook scripts (§3.6) → ``hooks.py``
  - Skill cross-install to .claude/skills + .agents/skills (§3.4/§3.5/§3.8) → ``skills.py``
  - .codex/config.toml (§3.7)            → ``codex_config.py``

A version-marker file at ``<project>/.claude/.scistudio-provision-version``
governs upgrade behavior on later SciStudio releases (§9 OQ-1; design
deferred to Phase 3, see #1011).

Per ADR §7, failures are NOT fatal — they log at WARNING and return a
``ProvisionResult`` summarizing what succeeded. Callers continue with
project open / create flow regardless.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scistudio.agent_provisioning.claude_agents_md import write_claude_agents_md
from scistudio.agent_provisioning.codex_config import write_codex_config
from scistudio.agent_provisioning.docs import write_docs
from scistudio.agent_provisioning.hooks import write_hooks
from scistudio.agent_provisioning.skills import write_skills

logger = logging.getLogger(__name__)

# I40c Phase 2a sets this to "0.1.0" — the first real cut.
# TODO(#1011): version-marker UPGRADE flow (detect stale version + re-write
#   only changed canonical files) is Phase 3 design.
#   Out of scope per ADR-040 §3.8 / §9 OQ-1.
#   Followup: https://github.com/zjzcpj/SciStudio/issues/1011.
SCISTUDIO_PROVISION_VERSION = "0.2.0"

_MARKER_REL_PATH = ".claude/.scistudio-provision-version"


@dataclass
class ProvisionResult:
    """Structured result of a provisioning run.

    Fields:
      written        — list of project-relative paths that were created.
      skipped        — list of project-relative paths that already existed
                       and were preserved (force=False).
      failed         — list of ``(label, reason)`` tuples for sub-steps that
                       errored. Surfacing failures here (instead of raising)
                       supports ADR §7 non-fatal degraded mode.
      version        — value written to the marker file
                       ``<project>/.claude/.scistudio-provision-version``.
    """

    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    version: str = SCISTUDIO_PROVISION_VERSION


def install_project_agent_assets(
    project_dir: Path,
    *,
    force: bool = False,
) -> ProvisionResult:
    """Install all prod-env agent assets into ``project_dir``.

    See module docstring for the full contract. Sub-steps are isolated:
    a failing sub-step is recorded in ``ProvisionResult.failed`` and
    remaining sub-steps still run.
    """
    project_dir = Path(project_dir)
    result = ProvisionResult()

    # Each sub-step: (label, callable, list-of-expected-paths-it-would-write).
    # ``expected`` is used to compute the skipped delta when force=False.
    steps: list[tuple[str, Callable[[], list[str]], list[str]]] = [
        (
            "claude_agents_md",
            lambda: write_claude_agents_md(project_dir, force=force),
            ["CLAUDE.md", "AGENTS.md"],
        ),
        (
            "hooks",
            lambda: write_hooks(project_dir, force=force),
            [
                ".claude/settings.json",
                ".claude/hooks/deny_scistudio_cli.py",
                ".claude/hooks/protect_workflow_yaml.py",
                ".claude/hooks/enforce_list_blocks_before_block_write.py",
                ".claude/hooks/remind_poll_status.py",
                ".claude/hooks/mark_list_blocks_called.py",
                ".claude/hooks/enforce_concrete_port_types.py",
            ],
        ),
        (
            "skills",
            lambda: write_skills(project_dir, force=force),
            _expected_skill_paths(),
        ),
        (
            "codex_config",
            lambda: write_codex_config(project_dir, force=force),
            [".codex/config.toml"],
        ),
        (
            "docs",
            lambda: write_docs(project_dir, force=force),
            _expected_doc_paths(),
        ),
    ]

    for label, fn, expected in steps:
        try:
            written = fn()
        except Exception as exc:
            logger.warning(
                "ADR-040: sub-step %s failed at %s (non-fatal): %s",
                label,
                project_dir,
                exc,
            )
            result.failed.append((label, f"{type(exc).__name__}: {exc}"))
            continue

        written_set = set(written)
        result.written.extend(written)
        for path in expected:
            if path not in written_set:
                result.skipped.append(path)

    # Version marker write — best-effort; if .claude/ does not exist (e.g.
    # hooks sub-step failed entirely), we still try to create the marker
    # so a later run can detect progress.
    try:
        marker = project_dir / _MARKER_REL_PATH
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(SCISTUDIO_PROVISION_VERSION, encoding="utf-8")
        if _MARKER_REL_PATH not in result.written:
            result.written.append(_MARKER_REL_PATH)
    except Exception as exc:
        logger.warning(
            "ADR-040: version marker write failed at %s (non-fatal): %s",
            project_dir,
            exc,
        )
        result.failed.append((_MARKER_REL_PATH, f"{type(exc).__name__}: {exc}"))

    return result


def _expected_doc_paths() -> list[str]:
    """Representative landing files the docs sub-step is expected to write (#1850).

    Used only to compute the skipped delta; the full set (every user-guide page,
    example, and API-reference page, plus the agent reference docs) is discovered
    from the packaged trees at write time.
    """
    return [
        "user-guide/README.md",
        "user-guide/getting-started.md",
        "user-guide/api-reference/index.md",
        ".scistudio/agent-reference/README.md",
        ".scistudio/agent-reference/public-api.md",
    ]


def _expected_skill_paths() -> list[str]:
    """Return the 14 skill-file paths the skills sub-step is expected to write.

    1 base + 6 task skills (including ADR-048 ``scistudio-write-plot``) across
    2 provider trees = 14.
    """
    names = [
        "scistudio",
        "scistudio-build-workflow",
        "scistudio-write-block",
        "scistudio-debug-run",
        "scistudio-inspect-data",
        "scistudio-project-qa",
        "scistudio-write-plot",
    ]
    paths: list[str] = []
    for tree in (".claude/skills", ".agents/skills"):
        for name in names:
            paths.append(f"{tree}/{name}/SKILL.md")
    return paths
