"""Test scaffold for ``agent_provisioning.skills`` (ADR-040 §3.4 + §3.8).

All tests skipped pending I40c Phase 2a impl (#1013).
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_write_skills_cross_installs_both_trees(tmp_project_dir):
    """All 6 skills land in both .claude/skills/ and .agents/skills/.

    Test plan (I40c):
      1. Call write_skills(tmp_project_dir).
      2. For each of [scieasy, scieasy-build-workflow, scieasy-write-block,
         scieasy-debug-run, scieasy-inspect-data, scieasy-project-qa]:
         a. Assert <project>/.claude/skills/scieasy/<name>/SKILL.md exists.
         b. Assert <project>/.agents/skills/scieasy/<name>/SKILL.md exists.
      3. Assert the two files at each name pair have identical content.
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_write_skills_idempotent(tmp_project_dir):
    """Second call preserves user-edited skill files.

    Test plan (I40c):
      1. Call write_skills.
      2. Append text to one of the SKILL.md files.
      3. Call write_skills again (force=False).
      4. Assert appended text is still present.
    """


@pytest.mark.skip(reason="S40c skeleton — I40c impl in Phase 2a. TODO(#1013)")
def test_write_skills_missing_source_handled(tmp_project_dir, monkeypatch):
    """Missing skill source raises FileNotFoundError handled upstream.

    Test plan (I40c):
      1. Monkeypatch importlib.resources to make one source missing.
      2. Call write_skills.
      3. Assert it raises FileNotFoundError (orchestrator catches).
    """
