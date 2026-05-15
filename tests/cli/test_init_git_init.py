"""Tests for ``scieasy init`` git-init parity (ADR-039 §6 Phase 1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from scieasy.cli.main import app

runner = CliRunner()


def test_cli_init_creates_git_repo(tmp_path: Path, monkeypatch) -> None:
    """``scieasy init <name>`` creates a project with .git/ initialized."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "my_project"])
    assert result.exit_code == 0, result.output
    project = tmp_path / "my_project"
    assert (project / ".git").is_dir()
    assert (project / ".gitignore").is_file()
    assert "Initialized git repository" in result.output


def test_cli_init_degraded_mode_when_git_unavailable(tmp_path: Path, monkeypatch) -> None:
    """When ``GitBinary.locate`` raises BundledGitMissing, init still succeeds."""
    monkeypatch.chdir(tmp_path)
    from scieasy.core.versioning.git_binary import BundledGitMissing

    with patch(
        "scieasy.core.versioning.git_binary.GitBinary.locate",
        side_effect=BundledGitMissing("no git for test"),
    ):
        result = runner.invoke(app, ["init", "degraded_project"])

    assert result.exit_code == 0
    project = tmp_path / "degraded_project"
    assert project.is_dir()
    assert not (project / ".git").exists()
    # Warning should appear in output (typer.echo with err=True goes to stderr,
    # which CliRunner captures via mix_stderr in default).
    combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
    assert "WARNING" in combined or "git binary unavailable" in combined
