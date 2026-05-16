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
