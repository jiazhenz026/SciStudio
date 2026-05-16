"""Test scaffold for ``agent_provisioning.claude_agents_md`` (ADR-040 §3.5).

All tests skipped pending I40c Phase 2a impl (#1013).
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_writes_both_files_identical(tmp_project_dir):
    """CLAUDE.md and AGENTS.md exist and have byte-identical content.

    Test plan (I40c):
      1. Call write_claude_agents_md(tmp_project_dir).
      2. Read <project>/CLAUDE.md and <project>/AGENTS.md.
      3. Assert both exist.
      4. Assert content is byte-identical (ADR §3.5 requirement).
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_idempotent_force_false_preserves_user_edits(tmp_project_dir):
    """Second call with force=False does not overwrite user edits.

    Test plan (I40c):
      1. Call write_claude_agents_md once.
      2. Append text to CLAUDE.md.
      3. Call again with force=False.
      4. Assert the appended text is preserved.
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_force_true_overwrites(tmp_project_dir):
    """force=True restores template content.

    Test plan (I40c):
      1. Call write_claude_agents_md once.
      2. Replace CLAUDE.md with garbage.
      3. Call again with force=True.
      4. Assert content matches template.
    """
