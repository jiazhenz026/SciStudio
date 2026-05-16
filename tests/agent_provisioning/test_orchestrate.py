"""Tests for ``agent_provisioning._orchestrate`` (ADR-040 §3.8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scieasy.agent_provisioning import (
    SCIEASY_PROVISION_VERSION,
    install_project_agent_assets,
)


def test_install_project_agent_assets_fresh_project(tmp_project_dir: Path) -> None:
    """Fresh project → ProvisionResult.written contains all expected paths."""
    result = install_project_agent_assets(tmp_project_dir, force=False)

    assert result.version == SCIEASY_PROVISION_VERSION
    assert result.failed == []

    expected_essential = {
        "CLAUDE.md",
        "AGENTS.md",
        ".claude/settings.json",
        ".claude/hooks/deny_scieasy_cli.py",
        ".claude/hooks/protect_workflow_yaml.py",
        ".claude/hooks/enforce_list_blocks_before_block_write.py",
        ".claude/hooks/remind_poll_status.py",
        ".claude/hooks/mark_list_blocks_called.py",
        ".claude/hooks/enforce_concrete_port_types.py",
        ".codex/config.toml",
        ".claude/.scieasy-provision-version",
    }
    written = set(result.written)
    missing = expected_essential - written
    assert not missing, f"expected paths not written: {missing}"

    # Each written path must exist on disk.
    for path in result.written:
        assert (tmp_project_dir / path).exists(), f"declared written but missing: {path}"

    # 12 skill files (6 names, 2 trees).
    skill_files = [p for p in result.written if "skills/scieasy/" in p and p.endswith("SKILL.md")]
    assert len(skill_files) == 12, f"expected 12 skill files, got {len(skill_files)}: {skill_files}"


def test_install_project_agent_assets_idempotent(tmp_project_dir: Path) -> None:
    """Second call with force=False preserves user edits."""
    install_project_agent_assets(tmp_project_dir, force=False)

    # Simulate user customization.
    claude_md = tmp_project_dir / "CLAUDE.md"
    user_marker = "# CUSTOM USER EDIT — preserve me\n"
    claude_md.write_text(user_marker, encoding="utf-8")

    result2 = install_project_agent_assets(tmp_project_dir, force=False)

    assert claude_md.read_text(encoding="utf-8") == user_marker
    assert "CLAUDE.md" in result2.skipped
    assert "CLAUDE.md" not in result2.written


def test_install_project_agent_assets_force(tmp_project_dir: Path) -> None:
    """force=True overwrites existing files."""
    install_project_agent_assets(tmp_project_dir, force=False)

    claude_md = tmp_project_dir / "CLAUDE.md"
    claude_md.write_text("# tainted\n", encoding="utf-8")

    install_project_agent_assets(tmp_project_dir, force=True)
    body = claude_md.read_text(encoding="utf-8")
    # Should contain ADR-040 §3.5 canonical phrase, not the taint.
    assert "tainted" not in body
    assert "SciEasy project" in body


def test_install_project_agent_assets_partial_failure(tmp_project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sub-step failure recorded in ProvisionResult.failed; others succeed."""

    def _boom(*args: object, **kwargs: object) -> list[str]:
        raise OSError("simulated codex_config failure")

    monkeypatch.setattr("scieasy.agent_provisioning._orchestrate.write_codex_config", _boom)

    result = install_project_agent_assets(tmp_project_dir, force=False)

    # codex_config failed; the rest succeeded.
    assert any(label == "codex_config" for label, _reason in result.failed)
    assert "CLAUDE.md" in result.written
    assert ".claude/settings.json" in result.written
    # No exception propagated to the caller (we got a ProvisionResult).
    assert isinstance(result.failed, list)


def test_version_marker_written(tmp_project_dir: Path) -> None:
    """``.claude/.scieasy-provision-version`` contains SCIEASY_PROVISION_VERSION."""
    install_project_agent_assets(tmp_project_dir, force=False)
    marker = tmp_project_dir / ".claude" / ".scieasy-provision-version"
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8").strip() == SCIEASY_PROVISION_VERSION


def test_install_project_agent_assets_creates_missing_parent(tmp_path: Path) -> None:
    """Orchestrator creates ``project_dir`` if it does not exist."""
    target = tmp_path / "newproject"
    assert not target.exists()
    result = install_project_agent_assets(target, force=False)
    assert target.is_dir()
    assert (target / "CLAUDE.md").is_file()
    assert result.failed == []
