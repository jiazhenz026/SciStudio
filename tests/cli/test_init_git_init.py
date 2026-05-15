"""Skeleton test for ``scieasy init`` git-init parity (ADR-039 §6 Phase 1).

D39-2.2a stub; D39-2.2b flips to passing.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_cli_init_creates_git_repo(tmp_path: Path) -> None:
    """``scieasy init <name>`` creates a project with .git/ initialized.

    Steps:
    1. Invoke ``scieasy init my_project`` via the Typer test runner with
       ``cwd=tmp_path``.
    2. Assert exit code 0.
    3. Assert ``(tmp_path / "my_project" / ".git").is_dir()``.
    4. Assert ``(tmp_path / "my_project" / ".gitignore").is_file()``.
    5. Assert initial commit exists (``git log --oneline`` shows one
       line containing "Initial commit").

    The CLI must succeed AND emit "Initialized git repository." to
    stdout. If the bundled git is unavailable in the test environment,
    the CLI must succeed with a warning instead of failing — degraded
    mode is explicitly supported per ADR §3.9.
    """
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_cli_init_degraded_mode_when_git_unavailable(monkeypatch, tmp_path: Path) -> None:
    """When ``GitBinary.locate`` raises BundledGitMissing, init still succeeds.

    Verifies the "degraded mode" path:
    - project.yaml and subdirs created
    - .git/ absent
    - exit code 0
    - stderr contains a WARNING line about missing git
    """
    raise NotImplementedError("D39-2.2b — see docstring")
