"""Tests for ``agent_provisioning.codex_config`` (ADR-040 §3.7)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from scieasy.agent_provisioning.codex_config import write_codex_config


def test_writes_codex_config_toml(tmp_project_dir: Path) -> None:
    """``.codex/config.toml`` exists with expected mcp_servers.scieasy block."""
    written = write_codex_config(tmp_project_dir, force=False)
    assert written == [".codex/config.toml"]

    raw = (tmp_project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    data = tomllib.loads(raw)
    assert "mcp_servers" in data
    block = data["mcp_servers"]["scieasy"]
    assert block["args"] == ["-m", "scieasy", "mcp-bridge"]
    assert block["env"]["SCIEASY_PROJECT_DIR"] == str(tmp_project_dir.resolve())


def test_codex_config_matches_install_render(tmp_project_dir: Path) -> None:
    """Auto-provisioned TOML is byte-identical to scieasy install --target codex output.

    ADR §3.7 / §3.9 unification contract.
    """
    from scieasy.cli.install import _render_codex_block

    write_codex_config(tmp_project_dir, force=False)
    actual = (tmp_project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    expected = _render_codex_block(tmp_project_dir.resolve())
    assert actual == expected


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
    assert "mcp_servers.scieasy" in body
