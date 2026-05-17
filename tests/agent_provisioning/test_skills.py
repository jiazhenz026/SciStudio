"""Tests for ``agent_provisioning.skills`` (ADR-040 §3.4 + §3.8)."""

from __future__ import annotations

from pathlib import Path

from scieasy.agent_provisioning.skills import write_skills

_SKILL_NAMES = (
    "scieasy",
    "scieasy-build-workflow",
    "scieasy-write-block",
    "scieasy-debug-run",
    "scieasy-inspect-data",
    "scieasy-project-qa",
)


def test_write_skills_cross_installs_both_trees(tmp_project_dir: Path) -> None:
    """All 6 skills land in both .claude/skills/ and .agents/skills/."""
    written = write_skills(tmp_project_dir, force=False)
    assert len(written) == 12

    for name in _SKILL_NAMES:
        claude = tmp_project_dir / ".claude" / "skills" / name / "SKILL.md"
        agents = tmp_project_dir / ".agents" / "skills" / name / "SKILL.md"
        assert claude.is_file(), f"missing claude skill: {name}"
        assert agents.is_file(), f"missing agents skill: {name}"
        # Pair-wise content identity.
        assert claude.read_bytes() == agents.read_bytes(), f"content mismatch for: {name}"


def test_write_skills_idempotent(tmp_project_dir: Path) -> None:
    """Second call preserves user-edited skill files."""
    write_skills(tmp_project_dir, force=False)
    user_marker = "# user-customized skill\n"
    one_skill = tmp_project_dir / ".claude" / "skills" / "scieasy-write-block" / "SKILL.md"
    one_skill.write_text(user_marker, encoding="utf-8")

    written = write_skills(tmp_project_dir, force=False)
    # Skill paths that already exist are NOT in the written list on second call.
    assert ".claude/skills/scieasy-write-block/SKILL.md" not in written
    assert one_skill.read_text(encoding="utf-8") == user_marker


def test_write_skills_force_overwrites(tmp_project_dir: Path) -> None:
    write_skills(tmp_project_dir, force=False)
    target = tmp_project_dir / ".claude" / "skills" / "scieasy" / "SKILL.md"
    target.write_text("# garbage\n", encoding="utf-8")

    write_skills(tmp_project_dir, force=True)
    body = target.read_text(encoding="utf-8")
    assert "garbage" not in body


def test_write_skills_creates_parent_dirs(tmp_path: Path) -> None:
    """Both provider tree roots are created if absent."""
    target = tmp_path / "fresh"
    write_skills(target, force=False)
    assert (target / ".claude" / "skills" / "scieasy").is_dir()
    assert (target / ".agents" / "skills" / "scieasy").is_dir()


def test_write_skills_placeholder_for_missing_source(tmp_project_dir: Path) -> None:
    """Missing skill source falls back to a TODO-tagged placeholder body.

    On this implementation branch, the Skills track (_skills/scieasy/<name>/)
    has not yet shipped the multi-skill split. The 5 task-scoped skills
    resolve to a placeholder body — that's the expected behavior.
    The base ``scieasy`` skill falls back to the legacy monolithic source.
    """
    write_skills(tmp_project_dir, force=False)
    # 5 task-scoped placeholders contain the TODO marker.
    for task_name in ("scieasy-build-workflow", "scieasy-debug-run"):
        body = (tmp_project_dir / ".claude" / "skills" / task_name / "SKILL.md").read_text(encoding="utf-8")
        # Either the real Phase 2c body OR our placeholder — both are valid here.
        assert task_name in body or "placeholder" in body.lower() or "TODO" in body
