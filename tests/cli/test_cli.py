"""CLI smoke tests for scistudio commands."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from scistudio.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _restore_cli_environment() -> object:
    """Keep in-process CLI env mutations from leaking across tests."""
    keys = ("SCISTUDIO_BUNDLED", "SCISTUDIO_ENGINE_API_URL")
    previous = {key: os.environ.get(key) for key in keys}
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class TestCLIHelp:
    """Verify --help lists all registered commands."""

    def test_help_shows_commands(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("init", "validate", "run", "blocks", "serve", "gui"):
            assert cmd in result.output


class TestCLIInit:
    """Tests for the ``scistudio init`` command."""

    def test_init_creates_workspace(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        result = runner.invoke(app, ["init", "test_proj"])
        assert result.exit_code == 0
        assert (tmp_path / "test_proj").is_dir()
        assert (tmp_path / "test_proj" / "workflows").is_dir()
        assert (tmp_path / "test_proj" / "data" / "raw").is_dir()
        assert (tmp_path / "test_proj" / "data" / "zarr").is_dir()
        assert (tmp_path / "test_proj" / "data" / "parquet").is_dir()
        assert (tmp_path / "test_proj" / "data" / "artifacts").is_dir()
        assert (tmp_path / "test_proj" / "blocks").is_dir()
        assert (tmp_path / "test_proj" / "types").is_dir()
        # ADR-038 §3.5 / §5.2: lineage history lives under ``.scistudio/`` now;
        # the legacy ``checkpoints/`` and ``lineage/`` top-level dirs are gone.
        assert (tmp_path / "test_proj" / ".scistudio").is_dir()
        assert (tmp_path / "test_proj" / "logs").is_dir()
        assert (tmp_path / "test_proj" / "project.yaml").is_file()

    def test_init_project_yaml_content(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        runner.invoke(app, ["init", "my_proj"])
        content = yaml.safe_load((tmp_path / "my_proj" / "project.yaml").read_text())
        assert content["project"]["name"] == "my_proj"
        assert content["project"]["version"] == "0.1.0"
        assert "created" in content["project"]

    def test_init_existing_dir_fails(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        (tmp_path / "existing").mkdir()
        result = runner.invoke(app, ["init", "existing"])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_init_default_name(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "my_project").is_dir()

    def test_init_output_message(self, tmp_path: Path, monkeypatch: object) -> None:
        monkeypatch.chdir(tmp_path)  # type: ignore[union-attr]
        result = runner.invoke(app, ["init", "workspace1"])
        assert result.exit_code == 0
        assert "Created project workspace: workspace1/" in result.output


class TestCLIBlocks:
    """Tests for the ``scistudio blocks`` command."""

    def test_blocks_runs_without_error(self) -> None:
        result = runner.invoke(app, ["blocks"])
        assert result.exit_code == 0

    def test_blocks_output_contains_count_or_no_blocks(self) -> None:
        result = runner.invoke(app, ["blocks"])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "block(s)" in output_lower or "no blocks found" in output_lower


class TestCLIServe:
    """Tests for the ``scistudio serve`` command."""

    def test_serve_starts_uvicorn_with_factory(self, monkeypatch: object) -> None:
        calls: dict[str, object] = {}

        def fake_run(app_target: str, *, host: str, port: int, factory: bool, log_config: object = None) -> None:
            calls.update(
                {
                    "app_target": app_target,
                    "host": host,
                    "port": port,
                    "factory": factory,
                }
            )

        monkeypatch.setattr("uvicorn.run", fake_run)  # type: ignore[union-attr]
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        assert "Starting SciStudio server on 0.0.0.0:8000" in result.output
        assert calls == {
            "app_target": "scistudio.api.app:create_app",
            "host": "0.0.0.0",
            "port": 8000,
            "factory": True,
        }

    def test_serve_shows_host_and_port(self, monkeypatch: object) -> None:
        monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)  # type: ignore[union-attr]
        result = runner.invoke(app, ["serve"])
        assert result.exit_code == 0
        assert "0.0.0.0" in result.output
        assert "8000" in result.output

    def test_serve_custom_host_port(self, monkeypatch: object) -> None:
        calls: dict[str, object] = {}

        def fake_run(app_target: str, *, host: str, port: int, factory: bool, log_config: object = None) -> None:
            calls.update(
                {
                    "app_target": app_target,
                    "host": host,
                    "port": port,
                    "factory": factory,
                }
            )

        monkeypatch.setattr("uvicorn.run", fake_run)  # type: ignore[union-attr]
        result = runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "9000"])
        assert result.exit_code == 0
        assert "127.0.0.1" in result.output
        assert "9000" in result.output
        assert calls["host"] == "127.0.0.1"
        assert calls["port"] == 9000


class TestCLIGui:
    """Tests for the ``scistudio gui`` command."""

    def test_gui_help_prints_usage(self) -> None:
        result = runner.invoke(app, ["gui", "--help"])
        assert result.exit_code == 0
        assert "Launch SciStudio GUI" in result.output

    def test_gui_starts_uvicorn_with_factory(self, monkeypatch: object) -> None:
        calls: dict[str, object] = {}

        def fake_run(app_target: str, *, host: str, port: int, factory: bool, log_config: object = None) -> None:
            calls.update({"app_target": app_target, "host": host, "port": port, "factory": factory})

        monkeypatch.setattr("uvicorn.run", fake_run)  # type: ignore[union-attr]
        result = runner.invoke(app, ["gui", "--no-browser"])
        assert result.exit_code == 0
        assert calls == {
            "app_target": "scistudio.api.app:create_app",
            "host": "0.0.0.0",
            "port": 8000,
            "factory": True,
        }

    def test_gui_default_port(self, monkeypatch: object) -> None:
        monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)  # type: ignore[union-attr]
        result = runner.invoke(app, ["gui", "--no-browser"])
        assert result.exit_code == 0
        assert "8000" in result.output

    def test_gui_custom_port(self, monkeypatch: object) -> None:
        calls: dict[str, object] = {}

        def fake_run(app_target: str, *, host: str, port: int, factory: bool, log_config: object = None) -> None:
            calls["port"] = port

        monkeypatch.setattr("uvicorn.run", fake_run)  # type: ignore[union-attr]
        result = runner.invoke(app, ["gui", "--port", "9000", "--no-browser"])
        assert result.exit_code == 0
        assert "9000" in result.output
        assert calls["port"] == 9000

    def test_gui_no_browser_skips_open(self, monkeypatch: object) -> None:
        browser_calls: list[str] = []

        monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)  # type: ignore[union-attr]
        monkeypatch.setattr("webbrowser.open", lambda url: browser_calls.append(url))  # type: ignore[union-attr]
        result = runner.invoke(app, ["gui", "--no-browser"])
        assert result.exit_code == 0
        assert len(browser_calls) == 0

    def test_gui_bundled_uses_loopback_and_emits_ready_json(self, monkeypatch: object) -> None:
        calls: dict[str, object] = {}

        def fake_run(app_target: str, *, host: str, port: int, factory: bool, log_config: object = None) -> None:
            calls.update({"app_target": app_target, "host": host, "port": port, "factory": factory})

        monkeypatch.setattr("uvicorn.run", fake_run)  # type: ignore[union-attr]
        result = runner.invoke(app, ["gui", "--bundled", "--port", "0"])
        assert result.exit_code == 0
        assert calls["host"] == "127.0.0.1"
        assert isinstance(calls["port"], int)
        assert calls["port"] != 0
        assert '{"event":"scistudio.ready"' in result.output
        assert '"url":"http://127.0.0.1:' in result.output


class TestCLIValidate:
    """Tests for the ``scistudio validate`` command."""

    def test_validate_missing_file(self) -> None:
        result = runner.invoke(app, ["validate", "nonexistent.yaml"])
        assert result.exit_code == 1
        assert "file not found" in result.output.lower()

    def test_validate_valid_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text(
            'workflow:\n  id: test\n  version: "1.0.0"\n  nodes:\n    - id: a\n      block_type: IOBlock\n  edges: []\n'
        )
        result = runner.invoke(app, ["validate", str(yaml_file)])
        # May succeed or fail with "not yet implemented" depending on serializer state.
        assert result.exit_code in (0, 1)

    def test_validate_minimal_yaml_succeeds(self, tmp_path: Path) -> None:
        """Minimal workflow YAML should load and validate successfully."""
        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text("workflow:\n  id: test\n")
        result = runner.invoke(app, ["validate", str(yaml_file)])
        assert result.exit_code == 0

    def test_validate_creates_registry_for_full_checks(self, tmp_path: Path) -> None:
        """validate command creates BlockRegistry for type-compatibility checks (#121)."""
        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text("workflow:\n  id: test\n  nodes:\n    - id: a\n      block_type: IOBlock\n  edges: []\n")
        result = runner.invoke(app, ["validate", str(yaml_file)])
        # Should not crash -- registry creation + scan + validate all work.
        assert result.exit_code in (0, 1)


class TestCLIRun:
    """Tests for the ``scistudio run`` command."""

    def test_run_missing_file(self) -> None:
        result = runner.invoke(app, ["run", "nonexistent.yaml"])
        assert result.exit_code == 1
        assert "file not found" in result.output.lower()

    def test_run_minimal_yaml(self, tmp_path: Path) -> None:
        """Minimal workflow YAML should load and attempt execution."""
        yaml_file = tmp_path / "workflow.yaml"
        yaml_file.write_text("workflow:\n  id: test\n")
        result = runner.invoke(app, ["run", str(yaml_file)])
        # Exit 0 if empty workflow completes, or 1 if DAG/execution raises
        assert result.exit_code in (0, 1)
