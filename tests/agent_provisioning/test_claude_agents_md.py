"""Tests for ``agent_provisioning.claude_agents_md`` (ADR-040 §3.5, refined by #2137).

#2137: AGENTS.md is the single canonical agent-instruction entry point;
CLAUDE.md is reduced to a one-line router pointing at AGENTS.md so the
guide text lives in exactly one place no matter how many provider CLIs
are supported.
"""

from __future__ import annotations

from pathlib import Path

from scistudio.agent_provisioning.claude_agents_md import write_claude_agents_md


def test_writes_agents_md_full_guide_and_claude_md_router(tmp_project_dir: Path) -> None:
    """AGENTS.md carries the full guide; CLAUDE.md only routes to AGENTS.md."""
    written = write_claude_agents_md(tmp_project_dir, force=False)
    assert set(written) == {"CLAUDE.md", "AGENTS.md"}

    agents = (tmp_project_dir / "AGENTS.md").read_text(encoding="utf-8")
    claude = (tmp_project_dir / "CLAUDE.md").read_text(encoding="utf-8")

    assert "SciStudio project" in agents  # template marker
    assert "mcp__scistudio__" in agents  # full guide content

    # The router names AGENTS.md and carries none of the guide body.
    assert "AGENTS.md" in claude
    assert "mcp__scistudio__" not in claude
    assert claude != agents


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

    (tmp_project_dir / "AGENTS.md").write_text("# garbage\n", encoding="utf-8")

    written = write_claude_agents_md(tmp_project_dir, force=True)
    assert set(written) == {"CLAUDE.md", "AGENTS.md"}

    body = (tmp_project_dir / "AGENTS.md").read_text(encoding="utf-8")
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
# Content assertions read AGENTS.md, the canonical entry point (#2137).


def test_template_indexes_all_five_task_skills(tmp_project_dir: Path) -> None:
    """The AGENTS.md template must reference all 5 task skills.

    Cross-discoverability rule: the project-level AGENTS.md is the
    agent's entry point on each turn; if a task skill is not indexed
    here, the agent will not know to load it.
    """
    write_claude_agents_md(tmp_project_dir, force=False)
    body = (tmp_project_dir / "AGENTS.md").read_text(encoding="utf-8")
    for task_skill in (
        "scistudio-build-workflow",
        "scistudio-write-block",
        "scistudio-debug-run",
        "scistudio-inspect-data",
        "scistudio-project-qa",
    ):
        assert task_skill in body, f"AGENTS.md template must reference {task_skill}."


def test_template_carries_non_negotiable_rules(tmp_project_dir: Path) -> None:
    """The AGENTS.md template must spell out non-negotiable rules.

    These rules are the agent's first defense (Layer 1 of ADR-040's
    defense in depth): the MCP tools are the only interface (no CLI),
    list_blocks before authoring, list_types before port selection,
    write_workflow over direct edits.
    """
    write_claude_agents_md(tmp_project_dir, force=False)
    body = (tmp_project_dir / "AGENTS.md").read_text(encoding="utf-8")
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


def test_template_hook_safety_is_provider_neutral(tmp_project_dir: Path) -> None:
    """#2137: the hook-safety section must not name individual provider CLIs.

    SciStudio supports five assistant CLIs (Claude Code, Codex, Kimi Code,
    Qoder, Qoder CN). The provisioned guide addresses the assistant — Mio —
    the same way on every provider, so it must not contain "if you are
    Codex / Claude Code"-style branching or per-provider capability claims.
    """
    write_claude_agents_md(tmp_project_dir, force=False)
    body = (tmp_project_dir / "AGENTS.md").read_text(encoding="utf-8")
    body_lower = body.lower()
    # A hook-safety section is present.
    assert "hook safety net" in body_lower
    # No provider is named anywhere in the guide body.
    for provider in ("claude code", "codex", "kimi", "qoder"):
        assert provider not in body_lower, f"provider name {provider!r} in AGENTS.md template"
    # The obsolete "no backstop on Codex" framing is gone.
    assert "no hook fires" not in body_lower
    assert "self-police" not in body_lower
    # The user's data/ is protected and the no-internal-citation rule is present.
    assert "data/" in body
    assert "per scistudio's requirements" in body_lower or "rule-citation" in body_lower
