"""Lifecycle integration tests for ADR-040 §3.8 wiring.

All tests skipped pending I40c Phase 2a impl (#1013).
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_create_project_provisions_assets(tmp_path):
    """ApiRuntime.create_project triggers install_project_agent_assets.

    Test plan (I40c):
      1. Instantiate ApiRuntime with tmp_path as parent.
      2. Call create_project("test").
      3. Assert <project>/CLAUDE.md, AGENTS.md, .claude/settings.json,
         .codex/config.toml all exist.
      4. Assert wiring ran AFTER git init by checking .git/ also exists
         and .git/HEAD points to a commit that DOES include the
         provisioned files (verifies ADR-039 → ADR-040 ordering).
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_open_project_idempotent_top_up(tmp_path):
    """open_project on a pre-ADR-040 project provisions missing assets.

    Test plan (I40c):
      1. Create a project on disk WITHOUT provisioning (simulate
         pre-ADR-040 project — git init only).
      2. Call open_project on it.
      3. Assert provisioning files appeared.
      4. Mutate one file.
      5. Call open_project again.
      6. Assert mutation preserved (force=False contract).
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_cli_init_provisions_assets(tmp_path, capsys):
    """``scieasy init`` triggers provisioning after git init.

    Test plan (I40c):
      1. chdir to tmp_path.
      2. Invoke ``scieasy init testproj`` via typer.testing.CliRunner.
      3. Assert <tmp_path>/testproj/CLAUDE.md etc. exist.
      4. Assert ``Created project workspace: testproj/`` is in stdout
         (final echo not gated by provisioning success).
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_provisioning_failure_degraded_mode(tmp_path, monkeypatch, caplog):
    """Provisioning failure logs WARNING but project still opens.

    Test plan (I40c — covers ADR §7 non-fatal contract):
      1. Monkeypatch install_project_agent_assets to raise OSError.
      2. Call create_project.
      3. Assert project IS created (project.yaml exists, KnownProject returned).
      4. Assert caplog contains "ADR-040: agent provisioning failed".
      5. Assert open_project still succeeds.
    """
