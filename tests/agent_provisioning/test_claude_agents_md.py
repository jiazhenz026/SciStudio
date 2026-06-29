"""Tests for ``agent_provisioning.claude_agents_md`` (ADR-040 §3.5)."""

from __future__ import annotations

from pathlib import Path

from scistudio.agent_provisioning.claude_agents_md import write_claude_agents_md


def test_writes_both_files_identical(tmp_project_dir: Path) -> None:
    """CLAUDE.md and AGENTS.md exist and have byte-identical content."""
    written = write_claude_agents_md(tmp_project_dir, force=False)
    assert set(written) == {"CLAUDE.md", "AGENTS.md"}

    claude = (tmp_project_dir / "CLAUDE.md").read_bytes()
    agents = (tmp_project_dir / "AGENTS.md").read_bytes()
    assert claude == agents
    assert b"SciStudio project" in claude  # template marker


def test_idempotent_force_false_preserves_user_edits(tmp_project_dir: Path) -> None:
    """Second call with force=False does not overwrite user edits."""
    write_claude_agents_md(tmp_project_dir, force=False)

    user_text = "# user-edited content\n"
    (tmp_project_dir / "CLAUDE.md").write_text(user_text, encoding="utf-8")
    (tmp_project_dir / "AGENTS.md").write_text(user_text, encoding="utf-8")

    written = write_claude_agents_md(tmp_project_dir, force=False)
    assert written == []

    assert (tmp_project_dir / "CLAUDE.md").read_text(encoding="utf-8") == user_text
    assert (tmp_project_dir / "AGENTS.md").read_text(encoding="utf-8") == user_text


def test_force_true_overwrites(tmp_project_dir: Path) -> None:
    """force=True restores template content over user edits."""
    write_claude_agents_md(tmp_project_dir, force=False)

    (tmp_project_dir / "CLAUDE.md").write_text("# garbage\n", encoding="utf-8")

    written = write_claude_agents_md(tmp_project_dir, force=True)
    assert set(written) == {"CLAUDE.md", "AGENTS.md"}

    body = (tmp_project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "garbage" not in body
    assert "SciStudio project" in body


def test_creates_parent_dir_if_missing(tmp_path: Path) -> None:
    """Function creates project_dir if absent."""
    target = tmp_path / "new-project"
    assert not target.exists()
    written = write_claude_agents_md(target, force=False)
    assert (target / "CLAUDE.md").is_file()
    assert (target / "AGENTS.md").is_file()
    assert set(written) == {"CLAUDE.md", "AGENTS.md"}


# --- I40b content-refinement tests (ADR-040 §3.5, Phase 2c) -----------


def test_template_indexes_all_five_task_skills(tmp_project_dir: Path) -> None:
    """The CLAUDE.md/AGENTS.md template must reference all 5 task skills.

    Cross-discoverability rule: the project-level CLAUDE.md is the
    agent's entry point on each turn; if a task skill is not indexed
    here, the agent will not know to load it.
    """
    write_claude_agents_md(tmp_project_dir, force=False)
    body = (tmp_project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    for task_skill in (
        "scistudio-build-workflow",
        "scistudio-write-block",
        "scistudio-debug-run",
        "scistudio-inspect-data",
        "scistudio-project-qa",
    ):
        assert task_skill in body, f"CLAUDE.md/AGENTS.md template must reference {task_skill}."


def test_template_carries_non_negotiable_rules(tmp_project_dir: Path) -> None:
    """The CLAUDE.md/AGENTS.md template must spell out non-negotiable rules.

    These rules are the agent's first defense (Layer 1 of ADR-040's
    defense in depth): the MCP tools are the only interface (no CLI),
    list_blocks before authoring, list_types before port selection,
    write_workflow over direct edits.
    """
    write_claude_agents_md(tmp_project_dir, force=False)
    body = (tmp_project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    # MCP is the only interface; the doc states there is no command-line tool
    # (positive framing, #1850) rather than denying CLI use.
    assert "mcp__scistudio__" in body
    assert "command-line tool" in body.lower()
    # Block-reuse rule (#875)
    assert "list_blocks" in body
    assert "#875" in body or "reuse" in body.lower()
    # Port-type rule (ADR-040 §3.2a)
    assert "list_types" in body
    assert "DataObject" in body
    # Workflow YAML protection
    assert "workflows/" in body
    assert "write_workflow" in body


def test_template_hook_safety_covers_both_providers(tmp_project_dir: Path) -> None:
    """#1850: hook coverage now applies to BOTH Claude Code and Codex.

    The earlier template carried a "Hook safety net — Claude Code only"
    section and "on Codex, no hook fires — self-police" caveats because Codex
    hook coverage was deferred. Codex now has full hook coverage, so the
    template must say the hooks back both providers and must NOT tell the
    agent it has no backstop on Codex.
    """
    write_claude_agents_md(tmp_project_dir, force=False)
    body = (tmp_project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    body_lower = body.lower()
    # A hook-safety section is present and names both providers.
    assert "hook safety net" in body_lower
    assert "both" in body_lower
    assert "claude code" in body_lower and "codex" in body_lower
    # The obsolete "no backstop on Codex" framing is gone.
    assert "claude code only" not in body_lower
    assert "no hook fires" not in body_lower
    assert "self-police" not in body_lower
    # The user's data/ is protected and the no-internal-citation rule is present.
    assert "data/" in body
    assert "per scistudio's requirements" in body_lower or "rule-citation" in body_lower
