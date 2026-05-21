"""Lifecycle integration tests for ADR-040 §3.8 wiring."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from scistudio.agent_provisioning import SCISTUDIO_PROVISION_VERSION


def _make_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Construct an ApiRuntime with an isolated home directory."""
    from scistudio.api import runtime as runtime_module

    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runtime_module.Path, "home", classmethod(lambda cls: fake_home))
    return runtime_module.ApiRuntime()


def test_create_project_provisions_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ApiRuntime.create_project triggers install_project_agent_assets."""
    runtime = _make_runtime(tmp_path, monkeypatch)
    parent = tmp_path / "projects"
    parent.mkdir()

    project = runtime.create_project(name="testproj", description="x", parent_path=str(parent))
    project_path = Path(project.path)

    assert (project_path / "CLAUDE.md").is_file()
    assert (project_path / "AGENTS.md").is_file()
    assert (project_path / ".claude" / "settings.json").is_file()
    assert (project_path / ".codex" / "config.toml").is_file()
    assert (project_path / ".claude" / "hooks" / "deny_scistudio_cli.py").is_file()

    marker = project_path / ".claude" / ".scistudio-provision-version"
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8").strip() == SCISTUDIO_PROVISION_VERSION


def test_open_project_idempotent_top_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """open_project on a pre-ADR-040 project provisions missing assets."""
    runtime = _make_runtime(tmp_path, monkeypatch)
    parent = tmp_path / "projects"
    parent.mkdir()

    # Build a minimal project-shaped directory WITHOUT going through
    # create_project (simulates pre-ADR-040 project).
    legacy = parent / "legacy"
    legacy.mkdir()
    (legacy / "workflows").mkdir()
    (legacy / "project.yaml").write_text(
        yaml.safe_dump({"project": {"id": "legacy-1", "name": "legacy"}}),
        encoding="utf-8",
    )

    runtime.open_project(str(legacy))
    assert (legacy / "CLAUDE.md").is_file()
    assert (legacy / ".claude" / "settings.json").is_file()

    # Mutate one provisioned file → confirm preserved on next open.
    (legacy / "CLAUDE.md").write_text("# user-edited\n", encoding="utf-8")
    runtime.open_project(str(legacy))
    assert (legacy / "CLAUDE.md").read_text(encoding="utf-8") == "# user-edited\n"


def test_cli_init_provisions_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``scistudio init`` triggers provisioning after git init."""
    from scistudio.cli.main import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["init", "testproj"])
    assert result.exit_code == 0, result.output
    assert "Created project workspace: testproj/" in result.output

    project_path = tmp_path / "testproj"
    assert (project_path / "CLAUDE.md").is_file()
    assert (project_path / "AGENTS.md").is_file()
    assert (project_path / ".claude" / "settings.json").is_file()
    assert (project_path / ".codex" / "config.toml").is_file()


def test_provisioning_failure_degraded_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Provisioning failure logs WARNING but project still opens (ADR §7)."""
    runtime = _make_runtime(tmp_path, monkeypatch)
    parent = tmp_path / "projects"
    parent.mkdir()

    # Make the orchestrator raise.
    def _raise(*args: object, **kwargs: object):
        raise OSError("disk on fire")

    # The runtime imports lazily: ``from scistudio.agent_provisioning import
    # install_project_agent_assets`` inside the try/except, so patching the
    # source module attribute is what intercepts the call.
    monkeypatch.setattr(
        "scistudio.agent_provisioning.install_project_agent_assets",
        _raise,
    )

    caplog.set_level(logging.WARNING, logger="scistudio.api.runtime")
    project = runtime.create_project(name="degraded", description="x", parent_path=str(parent))

    # Project IS created.
    assert Path(project.path).is_dir()
    assert (Path(project.path) / "project.yaml").is_file()
    # WARNING surfaced.
    assert any("ADR-040" in record.getMessage() for record in caplog.records), (
        f"expected ADR-040 warning in caplog: {[r.getMessage() for r in caplog.records]}"
    )
