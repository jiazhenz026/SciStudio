"""Tests for RRunner and JuliaRunner — mock subprocess to test JSON serialization logic."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scistudio.blocks.code.runners.julia_runner import JuliaRunner
from scistudio.blocks.code.runners.r_runner import RRunner

# ---------------------------------------------------------------------------
# RRunner
# ---------------------------------------------------------------------------


class TestRRunnerInline:
    """RRunner.execute_inline — mock Rscript subprocess."""

    @patch("scistudio.blocks.code.runners.r_runner.subprocess.run")
    def test_inline_creates_temp_files_and_calls_rscript(self, mock_run: MagicMock) -> None:
        """Inline execution should write inputs JSON, script, and call Rscript."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        runner = RRunner()
        # We mock subprocess.run, so the output file won't exist; expect empty dict
        result = runner.execute_inline("x <- 42", {"data": 5})
        assert result == {}

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0][0] == "Rscript"
        assert call_args[1]["capture_output"] is True
        assert call_args[1]["timeout"] == 300

    @patch("scistudio.blocks.code.runners.r_runner.subprocess.run")
    def test_inline_rscript_failure_raises(self, mock_run: MagicMock) -> None:
        """Rscript failure should raise RuntimeError."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Error in source")
        runner = RRunner()
        with pytest.raises(RuntimeError, match="Rscript failed"):
            runner.execute_inline("stop('fail')", {})

    @patch("scistudio.blocks.code.runners.r_runner.subprocess.run")
    def test_inline_reads_output_json(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """When output file exists, should parse and return JSON."""

        def side_effect(*args: object, **kwargs: object) -> MagicMock:
            # Find the script path from the call args and derive output path
            script_path = Path(args[0][1])  # type: ignore[index]
            output_path = script_path.parent / "outputs.json"
            output_path.write_text(json.dumps({"x": 42}), encoding="utf-8")
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = side_effect
        runner = RRunner()
        result = runner.execute_inline("x <- 42", {})
        assert result == {"x": 42}


class TestRRunnerScript:
    """RRunner.execute_script — mock Rscript subprocess."""

    @patch("scistudio.blocks.code.runners.r_runner.subprocess.run")
    def test_script_missing_file_raises(self, mock_run: MagicMock) -> None:
        runner = RRunner()
        with pytest.raises(FileNotFoundError, match="R script not found"):
            runner.execute_script("/nonexistent.R", "run", {}, {})

    @patch("scistudio.blocks.code.runners.r_runner.subprocess.run")
    def test_script_calls_rscript_with_wrapper(self, mock_run: MagicMock, tmp_path: Path) -> None:
        script = tmp_path / "my_block.R"
        script.write_text("run <- function(inputs, config) { list(result=42) }")

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        runner = RRunner()
        result = runner.execute_script(script, "run", {"x": 1}, {"param": 2})
        assert result == {}  # No output file created by mock
        mock_run.assert_called_once()

    @patch("scistudio.blocks.code.runners.r_runner.subprocess.run")
    def test_script_failure_raises(self, mock_run: MagicMock, tmp_path: Path) -> None:
        script = tmp_path / "bad.R"
        script.write_text("run <- function(inputs, config) stop('fail')")

        mock_run.return_value = MagicMock(returncode=1, stderr="Error")
        runner = RRunner()
        with pytest.raises(RuntimeError, match="Rscript failed"):
            runner.execute_script(script, "run", {}, {})


# ---------------------------------------------------------------------------
# JuliaRunner
# ---------------------------------------------------------------------------


class TestJuliaRunnerInline:
    """JuliaRunner.execute_inline — mock julia subprocess."""

    @patch("scistudio.blocks.code.runners.julia_runner.subprocess.run")
    def test_inline_creates_temp_files_and_calls_julia(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        runner = JuliaRunner()
        result = runner.execute_inline("x = 42", {"data": 5})
        assert result == {}

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0][0] == "julia"
        assert call_args[1]["timeout"] == 600

    @patch("scistudio.blocks.code.runners.julia_runner.subprocess.run")
    def test_inline_julia_failure_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="ERROR: LoadError")
        runner = JuliaRunner()
        with pytest.raises(RuntimeError, match="Julia failed"):
            runner.execute_inline("error()", {})

    @patch("scistudio.blocks.code.runners.julia_runner.subprocess.run")
    def test_inline_reads_output_json(self, mock_run: MagicMock) -> None:
        def side_effect(*args: object, **kwargs: object) -> MagicMock:
            script_path = Path(args[0][1])  # type: ignore[index]
            output_path = script_path.parent / "outputs.json"
            output_path.write_text(json.dumps({"x": 42}), encoding="utf-8")
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = side_effect
        runner = JuliaRunner()
        result = runner.execute_inline("x = 42", {})
        assert result == {"x": 42}


class TestJuliaRunnerScript:
    """JuliaRunner.execute_script — mock julia subprocess."""

    @patch("scistudio.blocks.code.runners.julia_runner.subprocess.run")
    def test_script_missing_file_raises(self, mock_run: MagicMock) -> None:
        runner = JuliaRunner()
        with pytest.raises(FileNotFoundError, match="Julia script not found"):
            runner.execute_script("/nonexistent.jl", "run", {}, {})

    @patch("scistudio.blocks.code.runners.julia_runner.subprocess.run")
    def test_script_calls_julia(self, mock_run: MagicMock, tmp_path: Path) -> None:
        script = tmp_path / "block.jl"
        script.write_text('function run(inputs, config) return Dict("result" => 42) end')

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        runner = JuliaRunner()
        result = runner.execute_script(script, "run", {"x": 1}, {})
        assert result == {}
        mock_run.assert_called_once()

    @patch("scistudio.blocks.code.runners.julia_runner.subprocess.run")
    def test_script_failure_raises(self, mock_run: MagicMock, tmp_path: Path) -> None:
        script = tmp_path / "bad.jl"
        script.write_text("function run(i, c) error() end")

        mock_run.return_value = MagicMock(returncode=1, stderr="ERROR")
        runner = JuliaRunner()
        with pytest.raises(RuntimeError, match="Julia failed"):
            runner.execute_script(script, "run", {}, {})
