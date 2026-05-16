"""Tests for ``scieasy install`` (#787).

Covers:

* Idempotent install/remove against synthetic Claude (JSON) and Codex
  (TOML) configs.
* Merge preserves other entries.
* Skill copy lands at the right location and removal is clean.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scieasy.cli.install import (
    MCP_SERVER_NAME,
    _strip_codex_block,
    perform_install,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() so install never touches the real user dir."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


@pytest.fixture
def fake_cwd(tmp_path: Path) -> Path:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    return cwd


# ---------------------------------------------------------------------------
# Claude target
# ---------------------------------------------------------------------------


def test_install_claude_user_idempotent(fake_home: Path, fake_cwd: Path) -> None:
    first = perform_install(target="claude", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    second = perform_install(target="claude", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)

    assert len(first) == 1 and first[0].action == "installed"
    assert len(second) == 1 and second[0].action == "noop"

    cfg = json.loads((fake_home / ".claude.json").read_text(encoding="utf-8"))
    assert MCP_SERVER_NAME in cfg["mcpServers"]
    entry = cfg["mcpServers"][MCP_SERVER_NAME]
    # Hotfix #880: args now prepend ["-m", "scieasy"] so the bridge always
    # invokes the same scieasy install as the engine (avoids stale-PATH bug).
    assert entry["args"][-1] == "mcp-bridge"
    assert "scieasy" in entry["args"]
    assert "command" in entry


def test_install_claude_preserves_other_entries(fake_home: Path, fake_cwd: Path) -> None:
    pre_existing = {
        "numStartups": 1,
        "mcpServers": {
            "other-server": {"command": "other", "args": []},
        },
    }
    config_path = fake_home / ".claude.json"
    config_path.write_text(json.dumps(pre_existing), encoding="utf-8")

    perform_install(target="claude", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    assert cfg["numStartups"] == 1
    assert "other-server" in cfg["mcpServers"]
    assert MCP_SERVER_NAME in cfg["mcpServers"]


def test_remove_claude_user(fake_home: Path, fake_cwd: Path) -> None:
    perform_install(target="claude", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    removed = perform_install(target="claude", scope="user", skill=False, do_all=False, remove=True, cwd=fake_cwd)
    assert removed[0].action == "removed"

    cfg = json.loads((fake_home / ".claude.json").read_text(encoding="utf-8"))
    assert MCP_SERVER_NAME not in cfg.get("mcpServers", {})


def test_install_claude_project_scope_uses_mcp_json(fake_home: Path, fake_cwd: Path) -> None:
    perform_install(target="claude", scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    project_cfg = fake_cwd / ".mcp.json"
    assert project_cfg.is_file()
    cfg = json.loads(project_cfg.read_text(encoding="utf-8"))
    assert MCP_SERVER_NAME in cfg["mcpServers"]
    # Project scope pins SCIEASY_PROJECT_DIR.
    assert cfg["mcpServers"][MCP_SERVER_NAME]["env"]["SCIEASY_PROJECT_DIR"] == str(fake_cwd)


# ---------------------------------------------------------------------------
# Codex target
# ---------------------------------------------------------------------------


def test_install_codex_idempotent(fake_home: Path, fake_cwd: Path) -> None:
    first = perform_install(target="codex", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    second = perform_install(target="codex", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    assert first[0].action == "installed"
    assert second[0].action == "noop"

    toml_text = (fake_home / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert f"[mcp_servers.{MCP_SERVER_NAME}]" in toml_text
    # Hotfix #880: args now prepend ["-m", "scieasy"] so the bridge always
    # runs from the same interpreter as the engine instead of relying on PATH.
    assert '"mcp-bridge"' in toml_text
    assert '"-m"' in toml_text
    assert '"scieasy"' in toml_text


def test_install_codex_preserves_other_keys(fake_home: Path, fake_cwd: Path) -> None:
    codex_dir = fake_home / ".codex"
    codex_dir.mkdir()
    cfg_path = codex_dir / "config.toml"
    cfg_path.write_text(
        'model = "gpt-5.4"\nmodel_reasoning_effort = "xhigh"\n\n[mcp_servers.other]\ncommand = "x"\nargs = []\n',
        encoding="utf-8",
    )

    perform_install(target="codex", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    text = cfg_path.read_text(encoding="utf-8")
    assert 'model = "gpt-5.4"' in text
    assert "[mcp_servers.other]" in text
    assert f"[mcp_servers.{MCP_SERVER_NAME}]" in text


def test_remove_codex_round_trip(fake_home: Path, fake_cwd: Path) -> None:
    perform_install(target="codex", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    perform_install(target="codex", scope="user", skill=False, do_all=False, remove=True, cwd=fake_cwd)

    text = (fake_home / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert f"[mcp_servers.{MCP_SERVER_NAME}]" not in text


def test_strip_codex_block_handles_nested_env() -> None:
    src = (
        "[mcp_servers.scieasy]\n"
        'command = "scieasy"\n'
        'args = ["mcp-bridge"]\n'
        "\n"
        "[mcp_servers.scieasy.env]\n"
        'SCIEASY_PROJECT_DIR = "/tmp/proj"\n'
        "\n"
        "[other_section]\n"
        'foo = "bar"\n'
    )
    stripped, removed = _strip_codex_block(src)
    assert removed is True
    assert "scieasy" not in stripped
    assert "[other_section]" in stripped
    assert 'foo = "bar"' in stripped


# ---------------------------------------------------------------------------
# Skill target
# ---------------------------------------------------------------------------


def test_install_skill_user_copies_dir(fake_home: Path, fake_cwd: Path) -> None:
    results = perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    # ADR-040 §3.9: two cross-installed destinations.
    assert all(r.target == "skill" for r in results)
    skill_dir = fake_home / ".claude" / "skills" / MCP_SERVER_NAME
    assert (skill_dir / "SKILL.md").is_file()


def test_install_skill_idempotent_replaces_dir(fake_home: Path, fake_cwd: Path) -> None:
    perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    second = perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    # Both destinations get rewritten on the second run.
    assert all(r.action == "updated" for r in second)


def test_remove_skill(fake_home: Path, fake_cwd: Path) -> None:
    perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    removed = perform_install(target=None, scope="user", skill=True, do_all=False, remove=True, cwd=fake_cwd)
    assert all(r.action == "removed" for r in removed)
    skill_dir = fake_home / ".claude" / "skills" / MCP_SERVER_NAME
    assert not skill_dir.exists()


def test_install_all_runs_claude_and_codex_and_skill(fake_home: Path, fake_cwd: Path) -> None:
    results = perform_install(target=None, scope="user", skill=False, do_all=True, remove=False, cwd=fake_cwd)
    targets = {r.target for r in results}
    assert {"claude", "codex", "skill"} <= targets
    # All three artefacts exist on disk.
    assert (fake_home / ".claude.json").is_file()
    assert (fake_home / ".codex" / "config.toml").is_file()
    assert (fake_home / ".claude" / "skills" / MCP_SERVER_NAME / "SKILL.md").is_file()


def test_missing_target_and_skill_raises(fake_home: Path, fake_cwd: Path) -> None:
    with pytest.raises(ValueError):
        perform_install(target=None, scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)


def test_invalid_scope_raises(fake_home: Path, fake_cwd: Path) -> None:
    with pytest.raises(ValueError):
        perform_install(target="claude", scope="bogus", skill=False, do_all=False, remove=False, cwd=fake_cwd)


def test_install_skill_with_missing_source_raises_clearly(fake_home: Path, fake_cwd: Path) -> None:
    """If the bundled skill is missing, surface a FileNotFoundError."""
    with (
        patch("scieasy.cli.install._find_skill_source", side_effect=FileNotFoundError("missing skill")),
        pytest.raises(FileNotFoundError),
    ):
        perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)


# ---------------------------------------------------------------------------
# ADR-040 §3.7 / §3.9 — I40d Phase 2a (#1014) implementation tests.
# ---------------------------------------------------------------------------


def test_install_skill_cross_install_user_scope(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.9: user-scope skill install writes both `.claude/skills/` AND `.agents/skills/`."""
    results = perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    # Two destinations, both skill-target, both installed (fresh).
    assert len(results) == 2
    assert {r.target for r in results} == {"skill"}
    assert {r.action for r in results} == {"installed"}

    claude_skill = fake_home / ".claude" / "skills" / MCP_SERVER_NAME
    codex_skill = fake_home / ".agents" / "skills" / MCP_SERVER_NAME
    assert (claude_skill / "SKILL.md").is_file()
    assert (codex_skill / "SKILL.md").is_file()
    # InstallResult paths cover both destinations.
    paths = {r.path for r in results}
    assert claude_skill in paths
    assert codex_skill in paths


def test_install_skill_cross_install_project_scope(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.9: project-scope writes both <cwd>/.claude/skills/ AND <cwd>/.agents/skills/."""
    results = perform_install(target=None, scope="project", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    assert len(results) == 2

    claude_skill = fake_cwd / ".claude" / "skills" / MCP_SERVER_NAME
    codex_skill = fake_cwd / ".agents" / "skills" / MCP_SERVER_NAME
    assert (claude_skill / "SKILL.md").is_file()
    assert (codex_skill / "SKILL.md").is_file()
    paths = {r.path for r in results}
    assert claude_skill in paths
    assert codex_skill in paths
    # User-scope paths NOT touched.
    assert not (fake_home / ".claude" / "skills" / MCP_SERVER_NAME).exists()
    assert not (fake_home / ".agents" / "skills" / MCP_SERVER_NAME).exists()


def test_remove_skill_cross_removal(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.9: `_remove_skill` cleans both paths symmetrically."""
    perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    removed = perform_install(target=None, scope="user", skill=True, do_all=False, remove=True, cwd=fake_cwd)
    assert len(removed) == 2
    assert {r.action for r in removed} == {"removed"}
    assert not (fake_home / ".claude" / "skills" / MCP_SERVER_NAME).exists()
    assert not (fake_home / ".agents" / "skills" / MCP_SERVER_NAME).exists()


def test_install_codex_project_scope_writes_local_config(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.7: `scieasy install --target codex --scope project` writes <cwd>/.codex/config.toml."""
    results = perform_install(target="codex", scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    assert len(results) == 1
    assert results[0].target == "codex"
    assert results[0].scope == "project"

    project_cfg = fake_cwd / ".codex" / "config.toml"
    assert project_cfg.is_file()
    text = project_cfg.read_text(encoding="utf-8")
    assert f"[mcp_servers.{MCP_SERVER_NAME}]" in text
    # Project scope pins SCIEASY_PROJECT_DIR in the env table.
    assert f"[mcp_servers.{MCP_SERVER_NAME}.env]" in text
    assert "SCIEASY_PROJECT_DIR" in text
    # _format_toml_string escapes backslashes; check the escaped form on
    # Windows so the test is platform-agnostic.
    assert str(fake_cwd).replace("\\", "\\\\") in text

    # User-scope ~/.codex/config.toml MUST NOT be touched.
    user_cfg = fake_home / ".codex" / "config.toml"
    assert not user_cfg.exists()


def test_perform_install_codex_no_longer_forces_user_scope(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.9: legacy 'wrote to user scope' detail-suffix is gone."""
    results = perform_install(target="codex", scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    assert len(results) == 1
    # The pre-I40d fallback added a parenthetical suffix to the detail.
    assert "wrote to user scope" not in results[0].detail
    assert "codex has no project-scope config file" not in results[0].detail


def test_remove_codex_project_scope_round_trip(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.7: install then --remove against project scope leaves the file clean."""
    perform_install(target="codex", scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    perform_install(target="codex", scope="project", skill=False, do_all=False, remove=True, cwd=fake_cwd)

    project_cfg = fake_cwd / ".codex" / "config.toml"
    assert project_cfg.is_file()
    text = project_cfg.read_text(encoding="utf-8")
    assert f"[mcp_servers.{MCP_SERVER_NAME}]" not in text
