"""Tests for ``agent_provisioning.claude_agents_md`` (ADR-040 §3.5)."""

from __future__ import annotations

from pathlib import Path

from scieasy.agent_provisioning.claude_agents_md import write_claude_agents_md


def test_writes_both_files_identical(tmp_project_dir: Path) -> None:
    """CLAUDE.md and AGENTS.md exist and have byte-identical content."""
    written = write_claude_agents_md(tmp_project_dir, force=False)
    assert set(written) == {"CLAUDE.md", "AGENTS.md"}

    claude = (tmp_project_dir / "CLAUDE.md").read_bytes()
    agents = (tmp_project_dir / "AGENTS.md").read_bytes()
    assert claude == agents
    assert b"SciEasy project" in claude  # template marker


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
    assert "SciEasy project" in body


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
        "scieasy-build-workflow",
        "scieasy-write-block",
        "scieasy-debug-run",
        "scieasy-inspect-data",
        "scieasy-project-qa",
    ):
        assert task_skill in body, f"CLAUDE.md/AGENTS.md template must reference {task_skill}."


def test_template_carries_non_negotiable_rules(tmp_project_dir: Path) -> None:
    """The CLAUDE.md/AGENTS.md template must spell out non-negotiable rules.

    These rules are the agent's first defense (Layer 1 of ADR-040's
    defense in depth): MCP tools over CLI, list_blocks before authoring,
    list_types before port selection, write_workflow over direct edits.
    """
    write_claude_agents_md(tmp_project_dir, force=False)
    body = (tmp_project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    # MCP tools over CLI
    assert "mcp__scieasy__" in body
    assert "scieasy" in body.lower() and "CLI" in body
    # Block-reuse rule (#875)
    assert "list_blocks" in body
    assert "#875" in body or "reuse" in body.lower()
    # Port-type rule (ADR-040 §3.2a)
    assert "list_types" in body
    assert "DataObject" in body
    # Workflow YAML protection
    assert "workflows/" in body
    assert "write_workflow" in body


def test_template_distinguishes_claude_vs_codex_hook_safety_net(tmp_project_dir: Path) -> None:
    """F40-integration F4: template must distinguish hook-backed (Claude)
    vs no-safety-net (Codex) per ADR-040 §3.10.

    Pre-F4 the template wrote "A PreToolUse hook blocks such calls" /
    "A PostToolUse hook stderr-warns" unconditionally, which is FALSE
    on Codex — Codex hook coverage is deferred per ADR §3.10. A Codex
    agent reading the unfixed template believes hooks will catch
    violations; they will not.

    Post-F4 the template carries a top-level "Hook safety net — Claude
    Code only" section and parenthetical (on Claude Code, …; on Codex,
    no hook fires) clauses on each rule.
    """
    write_claude_agents_md(tmp_project_dir, force=False)
    body = (tmp_project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    body_lower = body.lower()
    # Top-level distinction section present.
    assert "claude code only" in body_lower, (
        "Template must carry a top-level 'Hook safety net — Claude Code only' "
        "section so Codex agents see they have no backstop (F40-integration F4)."
    )
    # Codex explicitly named and self-police phrasing present.
    assert "codex" in body_lower
    assert "self-police" in body_lower or "no hook" in body_lower
    # ADR §3.10 reference grounds the gap.
    assert "3.10" in body or "ADR-040" in body
