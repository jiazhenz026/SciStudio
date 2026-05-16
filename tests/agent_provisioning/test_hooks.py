"""Test scaffold for ``agent_provisioning.hooks`` (ADR-040 §3.6).

All tests skipped pending I40c Phase 2a impl (#1013).
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_write_hooks_creates_settings_json(tmp_project_dir):
    """``.claude/settings.json`` exists with PreToolUse + PostToolUse arrays.

    Test plan (I40c):
      1. Call write_hooks(tmp_project_dir).
      2. Read <project>/.claude/settings.json.
      3. Assert ``hooks.PreToolUse`` length == 3.
      4. Assert ``hooks.PostToolUse`` length == 3.
      5. Assert each entry references a python interpreter + hook script path.
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_write_hooks_copies_six_scripts(tmp_project_dir):
    """All 6 hook scripts copied from templates to .claude/hooks/.

    Test plan (I40c):
      1. Call write_hooks.
      2. For each of [deny_scieasy_cli, protect_workflow_yaml,
         enforce_list_blocks_before_block_write, remind_poll_status,
         mark_list_blocks_called, enforce_concrete_port_types],
         assert <project>/.claude/hooks/<name>.py exists.
      3. Assert content matches the template byte-for-byte (or up to
         template substitution, if I40c introduces any).
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_write_hooks_idempotent_preserves_user_edits(tmp_project_dir):
    """force=False does not overwrite user-customized settings.json.

    Test plan (I40c):
      1. Call write_hooks(force=False).
      2. Append a custom hook entry to <project>/.claude/settings.json.
      3. Call write_hooks(force=False) again.
      4. Assert the custom entry is still present (no clobber).
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_hook_template_smoke_exit_zero(tmp_path):
    """Each hook template, when invoked with empty JSON stdin, exits 0.

    Test plan (I40c — once real bodies land, expand to exit-2 cases too):
      1. For each template name, invoke ``python <template_path>`` with
         stdin '{}' via subprocess.run.
      2. Assert returncode == 0 for the skeleton (since all are exit-0
         stubs). I40c will replace this with full behavior tests.
    """
