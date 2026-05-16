"""Test scaffold for ``agent_provisioning._orchestrate`` (ADR-040 §3.8).

All tests skipped pending I40c Phase 2a impl (#1013).
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_install_project_agent_assets_fresh_project(tmp_project_dir):
    """Fresh project → ProvisionResult.written contains all expected paths.

    Test plan (I40c):
      1. Call install_project_agent_assets(tmp_project_dir, force=False).
      2. Assert ProvisionResult.version == SCIEASY_PROVISION_VERSION.
      3. Assert written includes CLAUDE.md, AGENTS.md,
         .claude/settings.json, all 6 hook scripts, .codex/config.toml,
         and 12 skill files (6 per provider tree).
      4. Assert each file actually exists on disk.
      5. Assert ProvisionResult.failed is empty.
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_install_project_agent_assets_idempotent(tmp_project_dir):
    """Second call with force=False preserves user edits.

    Test plan (I40c):
      1. Call install once.
      2. Mutate <project>/CLAUDE.md (simulate user customization).
      3. Call install again with force=False.
      4. Assert CLAUDE.md content is unchanged.
      5. Assert ProvisionResult.skipped contains "CLAUDE.md".
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_install_project_agent_assets_force(tmp_project_dir):
    """force=True overwrites existing files.

    Test plan (I40c):
      1. Call install once.
      2. Mutate <project>/CLAUDE.md.
      3. Call install with force=True.
      4. Assert CLAUDE.md content matches the template (not the mutation).
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_install_project_agent_assets_partial_failure(tmp_project_dir, monkeypatch):
    """Sub-step failure recorded in ProvisionResult.failed, others succeed.

    Test plan (I40c):
      1. Monkeypatch ``write_codex_config`` to raise OSError.
      2. Call install.
      3. Assert ProvisionResult.failed has one entry referencing codex_config.
      4. Assert ProvisionResult.written still contains CLAUDE.md etc.
      5. Assert no exception propagates to the caller.
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_version_marker_written(tmp_project_dir):
    """``.claude/.scieasy-provision-version`` contains SCIEASY_PROVISION_VERSION.

    Test plan (I40c):
      1. Call install.
      2. Read <project>/.claude/.scieasy-provision-version.
      3. Assert equality with SCIEASY_PROVISION_VERSION constant.
    """
