"""Tests for ``agent_provisioning._refresh`` (#1860, PR #2144 review P1).

The content-aware refresh migrates existing projects to newly shipped
canonical content (agent guide, skills) while preserving genuine user
edits: a per-project hash manifest tracks what SciStudio last wrote, and a
frozen legacy-hash table adopts projects provisioned before the manifest
existed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.agent_provisioning import _refresh, install_project_agent_assets
from scistudio.agent_provisioning._refresh import (
    MANIFEST_REL_PATH,
    _digest,
    load_manifest,
    save_manifest,
    write_managed_file,
)
from scistudio.agent_provisioning.claude_agents_md import _CLAUDE_MD_ROUTER, _load_template


def test_manifest_round_trip(tmp_path: Path) -> None:
    """save → load returns the same mapping; missing/corrupt loads as {}."""
    assert load_manifest(tmp_path) == {}
    save_manifest(tmp_path, {"AGENTS.md": "abc"})
    assert load_manifest(tmp_path) == {"AGENTS.md": "abc"}
    (tmp_path / MANIFEST_REL_PATH).write_text("not json", encoding="utf-8")
    assert load_manifest(tmp_path) == {}


def test_digest_is_line_ending_insensitive() -> None:
    """CRLF and LF spellings hash identically (Windows checkouts)."""
    assert _digest("a\nb\n") == _digest("a\r\nb\r\n")


def test_write_managed_file_writes_missing_and_records_hash(tmp_path: Path) -> None:
    manifest: dict[str, str] = {}
    assert write_managed_file(tmp_path, "AGENTS.md", "v1\n", manifest) is True
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "v1\n"
    assert manifest["AGENTS.md"] == _digest("v1\n")


def test_write_managed_file_refreshes_unchanged_and_preserves_user_edits(tmp_path: Path) -> None:
    manifest: dict[str, str] = {}
    write_managed_file(tmp_path, "AGENTS.md", "v1\n", manifest)
    # Unchanged since we wrote it: a new canonical version replaces it.
    assert write_managed_file(tmp_path, "AGENTS.md", "v2\n", manifest) is True
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "v2\n"
    # A user edit diverges from the manifest entry: preserved verbatim.
    (tmp_path / "AGENTS.md").write_text("# my own edits\n", encoding="utf-8")
    assert write_managed_file(tmp_path, "AGENTS.md", "v3\n", manifest) is False
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "# my own edits\n"


def test_write_managed_file_force_overwrites_user_edits(tmp_path: Path) -> None:
    manifest: dict[str, str] = {}
    (tmp_path / "AGENTS.md").write_text("# my own edits\n", encoding="utf-8")
    assert write_managed_file(tmp_path, "AGENTS.md", "v1\n", manifest, force=True) is True
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "v1\n"


def test_legacy_hash_adoption_without_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A pre-manifest project whose file matches a historical canonical version is refreshed."""
    legacy_content = "old canonical content\n"
    monkeypatch.setattr(
        _refresh,
        "_legacy_hashes",
        lambda: {"AGENTS.md": frozenset({_digest(legacy_content)})},
    )
    (tmp_path / "AGENTS.md").write_text(legacy_content, encoding="utf-8")
    manifest: dict[str, str] = {}
    assert write_managed_file(tmp_path, "AGENTS.md", "new canonical\n", manifest) is True
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "new canonical\n"


def test_unknown_pre_manifest_content_is_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No manifest entry and no legacy match → treated as user-edited."""
    monkeypatch.setattr(_refresh, "_legacy_hashes", lambda: {})
    (tmp_path / "AGENTS.md").write_text("anything at all\n", encoding="utf-8")
    assert write_managed_file(tmp_path, "AGENTS.md", "new canonical\n", {}) is False
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "anything at all\n"


def test_existing_project_migrates_to_mio_guide(tmp_project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PR #2144 review P1: a pre-#2137 project picks up the Mio guide on reopen.

    Simulates a project provisioned before this change: both CLAUDE.md and
    AGENTS.md hold the pre-Mio guide body (registered as legacy canonical
    content, as the shipped legacy hash table does for every historical
    version). A force=False top-up — the production path — must refresh
    AGENTS.md to the current Mio guide and reduce CLAUDE.md to the router.
    """
    old_body = _load_template().replace("You are Mio", "You are an embedded agent inside")
    assert old_body != _load_template()
    legacy = _digest(old_body)
    monkeypatch.setattr(
        _refresh,
        "_legacy_hashes",
        lambda: {
            "CLAUDE.md": frozenset({legacy}),
            "AGENTS.md": frozenset({legacy}),
        },
    )
    (tmp_project_dir / "CLAUDE.md").write_text(old_body, encoding="utf-8")
    (tmp_project_dir / "AGENTS.md").write_text(old_body, encoding="utf-8")

    result = install_project_agent_assets(tmp_project_dir, force=False)

    assert result.failed == []
    agents = (tmp_project_dir / "AGENTS.md").read_text(encoding="utf-8")
    claude = (tmp_project_dir / "CLAUDE.md").read_text(encoding="utf-8")
    assert "You are Mio" in agents
    assert claude == _CLAUDE_MD_ROUTER


def test_user_edited_guide_survives_migration(tmp_project_dir: Path) -> None:
    """A genuinely user-edited guide is never clobbered by the migration."""
    user_text = "# my own project notes\n"
    (tmp_project_dir / "AGENTS.md").write_text(user_text, encoding="utf-8")

    install_project_agent_assets(tmp_project_dir, force=False)

    assert (tmp_project_dir / "AGENTS.md").read_text(encoding="utf-8") == user_text


def test_install_writes_manifest(tmp_project_dir: Path) -> None:
    """Provisioning records hashes for the guide and every skill file."""
    result = install_project_agent_assets(tmp_project_dir, force=False)
    assert MANIFEST_REL_PATH in result.written
    manifest = load_manifest(tmp_project_dir)
    assert "AGENTS.md" in manifest
    assert "CLAUDE.md" in manifest
    assert ".claude/skills/scistudio/SKILL.md" in manifest
    assert ".agents/skills/scistudio-write-plot/SKILL.md" in manifest


def test_skill_files_refresh_on_second_run(tmp_project_dir: Path) -> None:
    """Unchanged skills are refreshed (not skipped) on a later top-up.

    With the manifest, an unchanged managed file is rewritable — so a skill
    body shipped in a later release reaches existing projects.
    """
    install_project_agent_assets(tmp_project_dir, force=False)
    result2 = install_project_agent_assets(tmp_project_dir, force=False)
    assert ".claude/skills/scistudio/SKILL.md" in result2.written
    assert ".agents/skills/scistudio/SKILL.md" in result2.written
