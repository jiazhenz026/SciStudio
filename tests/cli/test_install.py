"""Tests for ``scistudio install`` (#787).

Covers:

* Idempotent install/remove against synthetic Claude (JSON) and Codex
  (TOML) configs.
* Merge preserves other entries.
* Skill copy lands at the right location and removal is clean.
"""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from scistudio.ai.agent.providers_registry import agent_keys
from scistudio.cli.install import (
    MCP_SERVER_NAME,
    _mcp_bridge_pythonpath,
    _mcp_entry_payload,
    _render_codex_block,
    _strip_codex_block,
    install_targets,
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
    # Hotfix #880: args now prepend ["-m", "scistudio"] so the bridge always
    # invokes the same scistudio install as the engine (avoids stale-PATH bug).
    assert entry["args"][-1] == "mcp-bridge"
    assert "scistudio" in entry["args"]
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
    # Project scope pins SCISTUDIO_PROJECT_DIR.
    assert cfg["mcpServers"][MCP_SERVER_NAME]["env"]["SCISTUDIO_PROJECT_DIR"] == str(fake_cwd)


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
    # Hotfix #880: args now prepend ["-m", "scistudio"] so the bridge always
    # runs from the same interpreter as the engine instead of relying on PATH.
    assert '"mcp-bridge"' in toml_text
    assert '"-m"' in toml_text
    assert '"scistudio"' in toml_text


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


# ---------------------------------------------------------------------------
# #1889 — bridge env carries PYTHONPATH so Codex (stripped launch env) can
# import scistudio, matching Claude Code (which inherits the parent env).
# ---------------------------------------------------------------------------


def _scistudio_src_root() -> str:
    import scistudio

    return str(Path(scistudio.__file__).resolve().parents[1])


def test_pythonpath_helper_includes_scistudio_root_and_ambient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", f"/custom/a{os.pathsep}/custom/b")
    result = _mcp_bridge_pythonpath()
    assert result is not None
    parts = result.split(os.pathsep)
    # scistudio's own source root must be present so `-m scistudio` resolves.
    assert _scistudio_src_root() in parts
    # The ambient PYTHONPATH segments are preserved (and de-duplicated).
    assert "/custom/a" in parts
    assert "/custom/b" in parts
    assert len(parts) == len(set(parts)), "PYTHONPATH segments must be de-duplicated"


def test_mcp_entry_payload_injects_pythonpath_project_scope(tmp_path: Path) -> None:
    entry = _mcp_entry_payload(tmp_path)
    env = entry["env"]
    assert isinstance(env, dict)
    assert env["SCISTUDIO_PROJECT_DIR"] == str(tmp_path)
    # #1889: without this, Codex's stripped launch env hits No module named scistudio.
    assert _scistudio_src_root() in env["PYTHONPATH"].split(os.pathsep)


def test_mcp_entry_payload_injects_pythonpath_user_scope() -> None:
    # User scope (project_dir=None) still needs PYTHONPATH so the bridge imports.
    entry = _mcp_entry_payload(None)
    env = entry["env"]
    assert isinstance(env, dict)
    assert "SCISTUDIO_PROJECT_DIR" not in env
    assert _scistudio_src_root() in env["PYTHONPATH"].split(os.pathsep)


def test_claude_and_codex_share_identical_mcp_env(tmp_path: Path) -> None:
    """#1889: both providers go through one env builder, so their launch env matches."""
    claude_entry = _mcp_entry_payload(tmp_path)
    codex_block = _render_codex_block(tmp_path)
    claude_env = claude_entry["env"]
    assert isinstance(claude_env, dict)

    # #2030: decode the TOML rather than substring-matching its source text. A
    # TOML basic string escapes backslashes, so on Windows the rendered block
    # spells the path `C:\\Users\\...` while the claude JSON carries the raw
    # `C:\Users\...` — the old `pythonpath in codex_block` check could only ever
    # hold on POSIX. Comparing decoded values tests what this test is actually
    # about (one env builder feeds both providers) on every platform.
    codex_env = tomllib.loads(codex_block)["mcp_servers"][MCP_SERVER_NAME]["env"]

    assert codex_env["PYTHONPATH"] == claude_env["PYTHONPATH"]
    assert codex_env["SCISTUDIO_PROJECT_DIR"] == claude_env["SCISTUDIO_PROJECT_DIR"]


def test_render_codex_block_includes_pythonpath_env(tmp_path: Path) -> None:
    text = _render_codex_block(tmp_path)
    assert f"[mcp_servers.{MCP_SERVER_NAME}.env]" in text
    assert "PYTHONPATH = " in text
    # SCISTUDIO_PROJECT_DIR must still be emitted before PYTHONPATH.
    assert text.index("SCISTUDIO_PROJECT_DIR") < text.index("PYTHONPATH")


def test_strip_codex_block_handles_nested_env() -> None:
    src = (
        "[mcp_servers.scistudio]\n"
        'command = "scistudio"\n'
        'args = ["mcp-bridge"]\n'
        "\n"
        "[mcp_servers.scistudio.env]\n"
        'SCISTUDIO_PROJECT_DIR = "/tmp/proj"\n'
        "\n"
        "[other_section]\n"
        'foo = "bar"\n'
    )
    stripped, removed = _strip_codex_block(src)
    assert removed is True
    assert "scistudio" not in stripped
    assert "[other_section]" in stripped
    assert 'foo = "bar"' in stripped


# ---------------------------------------------------------------------------
# Skill target
# ---------------------------------------------------------------------------


def test_install_skill_user_copies_dir(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.9: --skill cross-installs to both Claude and Codex skill trees."""
    results = perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    # Cross-install yields one InstallResult per destination (Claude + Codex).
    skill_results = [r for r in results if r.target == "skill"]
    assert len(skill_results) == 2
    claude_dir = fake_home / ".claude" / "skills" / MCP_SERVER_NAME
    agents_dir = fake_home / ".agents" / "skills" / MCP_SERVER_NAME
    assert (claude_dir / "SKILL.md").is_file()
    assert (agents_dir / "SKILL.md").is_file()


def test_install_skill_idempotent_replaces_dir(fake_home: Path, fake_cwd: Path) -> None:
    perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    second = perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    # Both skill destinations report "updated" on the second pass.
    skill_results = [r for r in second if r.target == "skill"]
    assert len(skill_results) == 2
    assert all(r.action == "updated" for r in skill_results)


def test_remove_skill(fake_home: Path, fake_cwd: Path) -> None:
    perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    removed = perform_install(target=None, scope="user", skill=True, do_all=False, remove=True, cwd=fake_cwd)
    skill_results = [r for r in removed if r.target == "skill"]
    assert len(skill_results) == 2
    assert all(r.action == "removed" for r in skill_results)
    assert not (fake_home / ".claude" / "skills" / MCP_SERVER_NAME).exists()
    assert not (fake_home / ".agents" / "skills" / MCP_SERVER_NAME).exists()


def test_install_all_runs_claude_and_codex_and_skill(fake_home: Path, fake_cwd: Path) -> None:
    results = perform_install(target=None, scope="user", skill=False, do_all=True, remove=False, cwd=fake_cwd)
    targets = {r.target for r in results}
    assert {"claude", "codex", "skill"} <= targets
    # All four artefacts exist on disk (skill is cross-installed).
    assert (fake_home / ".claude.json").is_file()
    assert (fake_home / ".codex" / "config.toml").is_file()
    assert (fake_home / ".claude" / "skills" / MCP_SERVER_NAME / "SKILL.md").is_file()
    assert (fake_home / ".agents" / "skills" / MCP_SERVER_NAME / "SKILL.md").is_file()


def test_missing_target_and_skill_raises(fake_home: Path, fake_cwd: Path) -> None:
    with pytest.raises(ValueError):
        perform_install(target=None, scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)


def test_invalid_scope_raises(fake_home: Path, fake_cwd: Path) -> None:
    with pytest.raises(ValueError):
        perform_install(target="claude", scope="bogus", skill=False, do_all=False, remove=False, cwd=fake_cwd)


def test_codex_project_scope_writes_local_config(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.7: Codex 2026 project-scope config — writes <cwd>/.codex/config.toml.

    Supersedes the legacy ``test_codex_project_scope_falls_back_with_caveat``
    test, which asserted the now-removed "force user-scope" fallback.
    """
    results = perform_install(target="codex", scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    assert len(results) == 1
    assert results[0].action == "installed"
    project_cfg = fake_cwd / ".codex" / "config.toml"
    assert project_cfg.is_file()
    text = project_cfg.read_text(encoding="utf-8")
    assert f"[mcp_servers.{MCP_SERVER_NAME}]" in text
    # Project scope pins SCISTUDIO_PROJECT_DIR via [mcp_servers.scistudio.env].
    assert f"[mcp_servers.{MCP_SERVER_NAME}.env]" in text
    assert str(fake_cwd) in text or repr(str(fake_cwd))[1:-1] in text
    # The user-scope codex config must NOT be touched.
    assert not (fake_home / ".codex" / "config.toml").is_file()
    # And the legacy "wrote to user scope" caveat is gone.
    assert "codex has no project-scope" not in results[0].detail
    assert "wrote to user scope" not in results[0].detail


def test_install_skill_with_missing_source_raises_clearly(fake_home: Path, fake_cwd: Path) -> None:
    """If the bundled skill is missing, surface a FileNotFoundError."""
    with (
        patch("scistudio.cli.install._find_skill_source", side_effect=FileNotFoundError("missing skill")),
        pytest.raises(FileNotFoundError),
    ):
        perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)


# ---------------------------------------------------------------------------
# ADR-040 §3.7 / §3.9 — I40d cross-install + project-scope codex impl (#1035)
# ---------------------------------------------------------------------------


def test_install_skill_cross_install_user_scope(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.9: user-scope skill install writes both `.claude/skills/` AND `.agents/skills/`."""
    results = perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    skill_results = [r for r in results if r.target == "skill"]
    assert len(skill_results) == 2
    paths = {r.path for r in skill_results}
    claude_path = fake_home / ".claude" / "skills" / MCP_SERVER_NAME
    agents_path = fake_home / ".agents" / "skills" / MCP_SERVER_NAME
    assert claude_path in paths
    assert agents_path in paths
    # Both destinations contain the canonical base SKILL.md.
    assert (claude_path / "SKILL.md").is_file()
    assert (agents_path / "SKILL.md").is_file()


def test_install_skill_cross_install_project_scope(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.9: project-scope writes both <cwd>/.claude/skills/ AND <cwd>/.agents/skills/."""
    results = perform_install(target=None, scope="project", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    skill_results = [r for r in results if r.target == "skill"]
    assert len(skill_results) == 2
    paths = {r.path for r in skill_results}
    claude_path = fake_cwd / ".claude" / "skills" / MCP_SERVER_NAME
    agents_path = fake_cwd / ".agents" / "skills" / MCP_SERVER_NAME
    assert claude_path in paths
    assert agents_path in paths
    assert (claude_path / "SKILL.md").is_file()
    assert (agents_path / "SKILL.md").is_file()
    # User-scope locations are NOT touched.
    assert not (fake_home / ".claude" / "skills" / MCP_SERVER_NAME).exists()
    assert not (fake_home / ".agents" / "skills" / MCP_SERVER_NAME).exists()


def test_remove_skill_cross_removal(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.9: `_remove_skill` cleans both paths symmetrically."""
    perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    removed = perform_install(target=None, scope="user", skill=True, do_all=False, remove=True, cwd=fake_cwd)
    skill_results = [r for r in removed if r.target == "skill"]
    assert len(skill_results) == 2
    assert all(r.action == "removed" for r in skill_results)
    assert not (fake_home / ".claude" / "skills" / MCP_SERVER_NAME).exists()
    assert not (fake_home / ".agents" / "skills" / MCP_SERVER_NAME).exists()


def test_install_codex_project_scope_writes_local_config(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.7: `scistudio install --target codex --scope project` writes <cwd>/.codex/config.toml."""
    results = perform_install(target="codex", scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    assert len(results) == 1
    project_cfg = fake_cwd / ".codex" / "config.toml"
    assert project_cfg.is_file()
    text = project_cfg.read_text(encoding="utf-8")
    assert f"[mcp_servers.{MCP_SERVER_NAME}]" in text
    assert f"[mcp_servers.{MCP_SERVER_NAME}.env]" in text
    assert "SCISTUDIO_PROJECT_DIR" in text
    # User-scope codex config not touched.
    assert not (fake_home / ".codex" / "config.toml").is_file()


# ---------------------------------------------------------------------------
# #1521 — FLAT skill layout (discoverable by Claude Code / Codex)
# ---------------------------------------------------------------------------


_EXPECTED_SUB_SKILLS = (
    "scistudio-build-workflow",
    "scistudio-write-block",
    "scistudio-debug-run",
    "scistudio-inspect-data",
    "scistudio-project-qa",
    "scistudio-write-plot",
)


def test_install_skill_layout_is_flat_and_discoverable(fake_home: Path, fake_cwd: Path) -> None:
    """#1521: sub-skills install as flat siblings, not nested under scistudio/.

    Claude Code / Codex discovery walk exactly one level under ``skills/``;
    the base skill keeps its own ``scistudio/`` dir and every task-scoped
    sub-skill must sit beside it (depth 1), never at ``skills/scistudio/<name>/``.
    """
    perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)

    for tree in (".claude", ".agents"):
        skills_root = fake_home / tree / "skills"
        # Base skill discoverable at depth 1.
        assert (skills_root / MCP_SERVER_NAME / "SKILL.md").is_file()
        # Each sub-skill is a flat sibling, discoverable at depth 1.
        for sub in _EXPECTED_SUB_SKILLS:
            assert (skills_root / sub / "SKILL.md").is_file(), f"{tree}: {sub} not flat-installed"
            # And it must NOT be buried under the nested (undiscoverable) path.
            assert not (skills_root / MCP_SERVER_NAME / sub).exists(), f"{tree}: {sub} nested under scistudio/"


def test_install_skill_layout_matches_provisioning(fake_home: Path, fake_cwd: Path) -> None:
    """#1521: install.py FLAT layout mirrors agent_provisioning.skills.write_skills."""
    perform_install(target=None, scope="project", skill=True, do_all=False, remove=False, cwd=fake_cwd)

    from scistudio.agent_provisioning.skills import _SKILL_NAMES

    for tree in (".claude", ".agents"):
        skills_root = fake_cwd / tree / "skills"
        for name in _SKILL_NAMES:
            assert (skills_root / name / "SKILL.md").is_file(), f"{tree}: {name} missing in flat layout"
        # No skill SKILL.md should exist deeper than one level under skills/.
        for skill_md in skills_root.rglob("SKILL.md"):
            depth = len(skill_md.relative_to(skills_root).parts)
            assert depth == 2, f"{tree}: {skill_md} at unexpected depth {depth} (expected <name>/SKILL.md)"


def test_remove_skill_removes_flat_siblings(fake_home: Path, fake_cwd: Path) -> None:
    """#1521: removal cleans the base skill AND every flat sub-skill sibling."""
    perform_install(target=None, scope="user", skill=True, do_all=False, remove=False, cwd=fake_cwd)
    removed = perform_install(target=None, scope="user", skill=True, do_all=False, remove=True, cwd=fake_cwd)
    skill_results = [r for r in removed if r.target == "skill"]
    assert len(skill_results) == 2
    assert all(r.action == "removed" for r in skill_results)
    for tree in (".claude", ".agents"):
        skills_root = fake_home / tree / "skills"
        assert not (skills_root / MCP_SERVER_NAME).exists()
        for sub in _EXPECTED_SUB_SKILLS:
            assert not (skills_root / sub).exists(), f"{tree}: {sub} not removed"


def test_perform_install_codex_no_longer_forces_user_scope(fake_home: Path, fake_cwd: Path) -> None:
    """ADR-040 §3.9: removed fallback — 'wrote to user scope' detail no longer surfaces when scope=project."""
    results = perform_install(target="codex", scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    assert len(results) == 1
    detail = results[0].detail
    assert "codex has no project-scope config file" not in detail
    assert "wrote to user scope" not in detail
    # And the InstallResult's scope is "project" (not silently rewritten to "user").
    assert results[0].scope == "project"


# ---------------------------------------------------------------------------
# ADR-034 T-013 — registry-derived install targets
# ---------------------------------------------------------------------------


def test_install_targets_are_registry_derived(fake_home: Path) -> None:
    """Every agent provider key is an install target, plus the legacy aliases.

    Asserted against ``agent_keys()`` rather than a literal so a sixth provider
    becomes an install target with no edit here — the whole point of the
    registry (User Story 7). ``user-terminal`` is excluded: it is a shell, not an
    agent CLI with an MCP config to wire.
    """
    targets = install_targets()

    assert set(agent_keys()) <= set(targets)
    assert "user-terminal" not in targets
    # Legacy spellings survive so existing invocations and scripts keep working.
    assert {"claude", "codex"} <= set(targets)
    # Order is stable and legacy-first, since it is rendered into ``--help``.
    assert targets[:2] == ("claude", "codex")
    assert len(targets) == len(set(targets))


@pytest.mark.parametrize("target", ["claude", "codex", "claude-code", "kimi-code", "qoder", "qoder-cn"])
def test_perform_install_accepts_every_registry_target(target: str, fake_home: Path, fake_cwd: Path) -> None:
    """Both legacy and registry-key targets install at project scope."""
    results = perform_install(target=target, scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)

    assert len(results) == 1
    assert results[0].target == target  # the requested spelling is echoed back
    assert results[0].action == "installed"
    assert results[0].path.is_file()


def test_install_claude_code_alias_writes_the_same_file_as_claude(fake_home: Path, fake_cwd: Path) -> None:
    """``--target claude-code`` is the registry key for ``--target claude``.

    Different spelling, same file: the alias must not create a second config
    location the user then has to keep in sync.
    """
    legacy = perform_install(target="claude", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    modern = perform_install(target="claude-code", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)

    assert legacy[0].path == modern[0].path == fake_home / ".claude.json"
    # Second call is a no-op because the entry is already exactly right.
    assert modern[0].action == "noop"


def test_install_kimi_project_scope_writes_provider_owned_config(fake_home: Path, fake_cwd: Path) -> None:
    """Kimi's project-scope location comes from its descriptor, not a literal."""
    results = perform_install(
        target="kimi-code", scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd
    )

    expected = fake_cwd / ".kimi-code" / "mcp.json"
    assert results[0].path == expected
    data = json.loads(expected.read_text(encoding="utf-8"))
    assert data["mcpServers"][MCP_SERVER_NAME]["env"]["SCISTUDIO_PROJECT_DIR"] == str(fake_cwd)


@pytest.mark.parametrize("target", ["qoder", "qoder-cn"])
def test_install_qoder_channels_use_project_scope_mcp_json(target: str, fake_home: Path, fake_cwd: Path) -> None:
    """Both Qoder channels discover ``<project>/.mcp.json`` (spec section 1 table)."""
    results = perform_install(target=target, scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)

    assert results[0].path == fake_cwd / ".mcp.json"
    data = json.loads((fake_cwd / ".mcp.json").read_text(encoding="utf-8"))
    assert MCP_SERVER_NAME in data["mcpServers"]


def test_install_preserves_other_servers_in_a_provider_owned_file(fake_home: Path, fake_cwd: Path) -> None:
    """A provider-owned config may already hold the user's own MCP servers.

    ``.kimi-code/mcp.json`` belongs to Kimi, not SciStudio, so a clobbering write
    would destroy configuration the user cannot recover.
    """
    target_file = fake_cwd / ".kimi-code" / "mcp.json"
    target_file.parent.mkdir(parents=True)
    target_file.write_text(
        json.dumps({"mcpServers": {"user-owned": {"command": "keep-me"}}, "theme": "dark"}),
        encoding="utf-8",
    )

    perform_install(target="kimi-code", scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)

    data = json.loads(target_file.read_text(encoding="utf-8"))
    assert data["mcpServers"]["user-owned"] == {"command": "keep-me"}
    assert data["theme"] == "dark"
    assert MCP_SERVER_NAME in data["mcpServers"]


@pytest.mark.parametrize("target", ["claude-code", "kimi-code", "qoder"])
def test_remove_round_trips_every_registry_target(target: str, fake_home: Path, fake_cwd: Path) -> None:
    """``--remove`` reverses a registry-derived install and is idempotent."""
    perform_install(target=target, scope="project", skill=False, do_all=False, remove=False, cwd=fake_cwd)
    removed = perform_install(target=target, scope="project", skill=False, do_all=False, remove=True, cwd=fake_cwd)
    again = perform_install(target=target, scope="project", skill=False, do_all=False, remove=True, cwd=fake_cwd)

    assert removed[0].action == "removed"
    assert again[0].action == "noop"
    data = json.loads(removed[0].path.read_text(encoding="utf-8"))
    assert MCP_SERVER_NAME not in data["mcpServers"]


@pytest.mark.parametrize("target", ["kimi-code", "qoder", "qoder-cn"])
def test_user_scope_is_refused_where_no_location_is_verified(target: str, fake_home: Path, fake_cwd: Path) -> None:
    """No user-scope MCP path is recorded for these providers, so we refuse.

    Kimi's ``<KIMI_CODE_HOME>/mcp.json`` is shared user state the spec forbids
    SciStudio from mutating, and no user-scope location was observed for either
    Qoder channel. Guessing at a path would write into a file the user owns, so
    the error names the provider and points at ``--scope project`` instead.
    """
    with pytest.raises(ValueError) as excinfo:
        perform_install(target=target, scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)

    message = str(excinfo.value)
    assert target in message
    assert "--scope project" in message


def test_unknown_target_still_errors_and_names_the_accepted_set(fake_home: Path, fake_cwd: Path) -> None:
    """An unknown target is rejected, with every accepted target enumerated."""
    with pytest.raises(ValueError) as excinfo:
        perform_install(target="bogus", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)

    message = str(excinfo.value)
    assert "bogus" in message
    for target in install_targets():
        assert target in message
    # Nothing was written before the rejection.
    assert not (fake_home / ".claude.json").exists()


def test_user_terminal_is_not_an_install_target(fake_home: Path, fake_cwd: Path) -> None:
    """``user-terminal`` is a registry key but not an agent CLI (FR-003)."""
    with pytest.raises(ValueError):
        perform_install(target="user-terminal", scope="user", skill=False, do_all=False, remove=False, cwd=fake_cwd)


def test_install_all_stays_scoped_to_claude_and_codex(fake_home: Path, fake_cwd: Path) -> None:
    """``--all`` is unchanged by T-013 and does not fan out to every provider.

    Widening it would make one flag write into five providers' config files,
    which is not what "the usual setup" means — and three of them have no
    user-scope location at all.
    """
    results = perform_install(target=None, scope="user", skill=False, do_all=True, remove=False, cwd=fake_cwd)

    assert {r.target for r in results} == {"claude", "codex", "skill"}
    assert not (fake_home / ".kimi-code").exists()
