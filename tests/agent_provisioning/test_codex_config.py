"""Tests for ``agent_provisioning.codex_config`` (ADR-040 §3.7)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scistudio.agent_provisioning.codex_config import write_codex_config


def test_writes_codex_config_toml(tmp_project_dir: Path) -> None:
    """``.codex/config.toml`` exists with expected mcp_servers.scistudio block."""
    written = write_codex_config(tmp_project_dir, force=False)
    assert written == [".codex/config.toml"]

    raw = (tmp_project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    data = tomllib.loads(raw)
    assert "mcp_servers" in data
    block = data["mcp_servers"]["scistudio"]
    assert block["args"] == ["-m", "scistudio", "mcp-bridge"]
    assert block["env"]["SCISTUDIO_PROJECT_DIR"] == str(tmp_project_dir.resolve())


def test_codex_config_mcp_block_matches_install_render(tmp_project_dir: Path) -> None:
    """The ``[mcp_servers.scistudio]`` block matches ``_render_codex_block`` exactly.

    Per ADR §3.7 / §3.9 unification contract the MCP server block must
    be byte-identical to what ``scistudio install --target codex`` emits.
    Per ADR Addendum 4 the auto-provisioned file additionally appends a
    hooks block — so the contract is now "MCP block is the prefix" rather
    than "whole file is equal".
    """
    from scistudio.cli.install import _render_codex_block

    write_codex_config(tmp_project_dir, force=False)
    actual = (tmp_project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    expected_mcp = _render_codex_block(tmp_project_dir.resolve())
    assert actual.startswith(expected_mcp), (
        "MCP-server block must be the unmodified prefix; "
        "scistudio install --target codex must keep producing the same bytes."
    )


def test_codex_config_emits_hooks(tmp_project_dir: Path) -> None:
    """ADR-040/042: Codex gets the same hook surface as Claude.

    Asserts ``features.hooks = true``, 3 PreToolUse + 3 PostToolUse
    matcher groups, and each hook command line references a script
    under ``.claude/hooks/`` (the cross-provider canonical home).
    """
    write_codex_config(tmp_project_dir, force=False)
    raw = (tmp_project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    data = tomllib.loads(raw)

    assert data.get("features", {}).get("hooks") is True, (
        "features.hooks must be true to enable Codex 0.130+'s hook surface"
    )

    pre = data.get("hooks", {}).get("PreToolUse", [])
    post = data.get("hooks", {}).get("PostToolUse", [])
    assert len(pre) == 4, f"expected 4 PreToolUse hooks, got {len(pre)}"
    assert len(post) == 3, f"expected 3 PostToolUse hooks, got {len(post)}"

    expected_pre_scripts = {
        "worktree_write_guard.py",
        "deny_scistudio_cli.py",
        "protect_workflow_yaml.py",
        "enforce_list_blocks_before_block_write.py",
    }
    expected_post_scripts = {
        "remind_poll_status.py",
        "mark_list_blocks_called.py",
        "enforce_concrete_port_types.py",
    }

    def _script_names(groups: list[dict]) -> set[str]:
        names: set[str] = set()
        for group in groups:
            for handler in group.get("hooks", []):
                cmd = handler.get("command", "")
                # Extract trailing script name from the command.
                for known in expected_pre_scripts | expected_post_scripts:
                    if known in cmd:
                        names.add(known)
                # Every hook command must invoke a .claude/hooks/ script
                # (cross-provider DRY — no Codex-specific script tree).
                assert ".claude/hooks/" in cmd, f"hook command should target .claude/hooks/, got: {cmd!r}"
        return names

    assert _script_names(pre) == expected_pre_scripts
    assert _script_names(post) == expected_post_scripts


def test_idempotent_preserves_user_managed_toml(tmp_project_dir: Path) -> None:
    """Pre-existing config.toml preserved on force=False."""
    codex_dir = tmp_project_dir / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    user_body = "# user-managed config\n[some_other_section]\nkey = 'value'\n"
    (codex_dir / "config.toml").write_text(user_body, encoding="utf-8")

    written = write_codex_config(tmp_project_dir, force=False)
    assert written == []
    assert (codex_dir / "config.toml").read_text(encoding="utf-8") == user_body


def test_force_overwrites(tmp_project_dir: Path) -> None:
    codex_dir = tmp_project_dir / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    (codex_dir / "config.toml").write_text("# old\n", encoding="utf-8")

    written = write_codex_config(tmp_project_dir, force=True)
    assert written == [".codex/config.toml"]
    body = (codex_dir / "config.toml").read_text(encoding="utf-8")
    assert "mcp_servers.scistudio" in body
