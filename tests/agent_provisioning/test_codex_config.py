"""Test scaffold for ``agent_provisioning.codex_config`` (ADR-040 §3.7).

All tests skipped pending I40c Phase 2a impl (#1013).
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_writes_codex_config_toml(tmp_project_dir):
    """``.codex/config.toml`` exists with expected mcp_servers.scieasy block.

    Test plan (I40c):
      1. Call write_codex_config(tmp_project_dir).
      2. Read <project>/.codex/config.toml.
      3. Parse with tomllib.
      4. Assert ``mcp_servers.scieasy.command`` references sys.executable.
      5. Assert ``mcp_servers.scieasy.args == ["-m", "scieasy", "mcp-bridge"]``.
      6. Assert ``mcp_servers.scieasy.env.SCIEASY_PROJECT_DIR`` == absolute tmp_project_dir.
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_codex_config_matches_install_render(tmp_project_dir):
    """Auto-provisioned TOML is byte-identical to scieasy install --target codex output.

    Test plan (I40c):
      1. Call write_codex_config.
      2. Read <project>/.codex/config.toml.
      3. Call _render_codex_block(tmp_project_dir) from scieasy.cli.install.
      4. Assert string equality (ADR §3.7 / §3.9 unification contract).
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_idempotent_preserves_user_managed_toml(tmp_project_dir):
    """Pre-existing config.toml preserved on force=False.

    Test plan (I40c):
      1. Write a manual <project>/.codex/config.toml.
      2. Call write_codex_config with force=False.
      3. Assert file unchanged.
    """
