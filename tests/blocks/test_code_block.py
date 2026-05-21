"""Tests for CodeBlock — inline Python, script Python, Collection unpack/repack."""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.blocks.base.state import BlockState
from scistudio.blocks.code.code_block import CodeBlock, CodeBlockMigrationError
from scistudio.blocks.code.introspect import introspect_script
from scistudio.blocks.code.runners.python_runner import PythonRunner


class TestPythonRunnerInline:
    """PythonRunner inline mode — exec() in namespace."""

    def test_simple_script(self) -> None:
        runner = PythonRunner()
        result = runner.execute_inline("x = 2\ny = x * 3", {})
        assert result["x"] == 2
        assert result["y"] == 6

    def test_script_with_inputs(self) -> None:
        runner = PythonRunner()
        result = runner.execute_inline("out = data + 10", {"data": 5})
        assert result["out"] == 15

    def test_private_keys_stripped(self) -> None:
        runner = PythonRunner()
        result = runner.execute_inline("_private = 1\npublic = 2", {})
        assert "public" in result
        assert "_private" not in result

    def test_inputs_not_in_output(self) -> None:
        runner = PythonRunner()
        result = runner.execute_inline("x = data + 1", {"data": 5})
        assert "x" in result
        assert result["x"] == 6
        assert "data" not in result  # input should be filtered

    def test_imports_not_in_output(self) -> None:
        runner = PythonRunner()
        result = runner.execute_inline("import math\nresult = math.sqrt(4)", {})
        assert "result" in result
        assert result["result"] == 2.0
        assert "math" not in result  # imports should be filtered


class TestPythonRunnerScript:
    """PythonRunner script mode — importlib-based execution."""

    def test_script_file(self, tmp_path: Path) -> None:
        script = tmp_path / "my_block.py"
        script.write_text("def run(inputs, config):\n    return {'result': inputs['value'] * 2}\n")
        runner = PythonRunner()
        result = runner.execute_script(script, "run", {"value": 21}, {})
        assert result["result"] == 42

    def test_missing_script(self) -> None:
        runner = PythonRunner()
        with pytest.raises(FileNotFoundError):
            runner.execute_script("/nonexistent.py", "run", {}, {})

    def test_missing_function(self, tmp_path: Path) -> None:
        script = tmp_path / "empty.py"
        script.write_text("# no run function\n")
        runner = PythonRunner()
        with pytest.raises(AttributeError, match="run"):
            runner.execute_script(script, "run", {}, {})


class TestCodeBlockInline:
    """Legacy CodeBlock inline mode now reports ADR-041 migration diagnostics."""

    def test_inline_execution_reports_migration(self) -> None:
        block = CodeBlock(config={"params": {"script": "result = 42"}})
        block.transition(BlockState.READY)
        with pytest.raises(CodeBlockMigrationError, match="Inline CodeBlock configs are not valid"):
            block.run({}, block.config)

    def test_inline_with_input_reports_migration(self) -> None:
        block = CodeBlock(config={"params": {"script": "output = data * 2"}})
        block.transition(BlockState.READY)
        with pytest.raises(CodeBlockMigrationError, match="Inline CodeBlock configs are not valid"):
            block.run({"data": 10}, block.config)


class TestCodeBlockScript:
    """Legacy CodeBlock entry-function script mode now reports migration diagnostics."""

    def test_entry_function_script_reports_migration(self, tmp_path: Path) -> None:
        script = tmp_path / "block_script.py"
        script.write_text("def run(inputs, config):\n    return {'result': sum(inputs.get('values', []))}\n")
        block = CodeBlock(config={"params": {"project_dir": str(tmp_path), "script_path": "block_script.py"}})
        block.transition(BlockState.READY)
        with pytest.raises(CodeBlockMigrationError, match="does not call entry functions"):
            block.run({}, block.config)


# ADR-020: TestCodeBlockProxyMode and TestCodeBlockChunkedMode removed.
# InputDelivery enum deleted — CodeBlock uses Collection auto-unpack only.
# PROXY and CHUNKED delivery are superseded by ProcessBlock.


class TestIntrospectScript:
    """introspect_script — AST-based script analysis."""

    def test_simple_run_function(self, tmp_path: Path) -> None:
        script = tmp_path / "block.py"
        script.write_text('"""My block."""\ndef run(inputs, config, threshold=0.5):\n    pass\n')
        info = introspect_script(script)
        assert info["has_run"] is True
        assert len(info["run_params"]) == 3
        assert info["run_params"][0]["name"] == "inputs"
        assert info["docstring"] == "My block."

    def test_configure_function(self, tmp_path: Path) -> None:
        script = tmp_path / "block.py"
        script.write_text(
            "def configure():\n    return {'window': 11, 'method': 'savgol'}\n\ndef run(inputs, config):\n    pass\n"
        )
        info = introspect_script(script)
        assert info["has_configure"] is True
        assert info["configure_schema"] == {"window": 11, "method": "savgol"}

    def test_no_run_function(self, tmp_path: Path) -> None:
        script = tmp_path / "utils.py"
        script.write_text("x = 1\n")
        info = introspect_script(script)
        assert info["has_run"] is False

    def test_missing_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            introspect_script("/nonexistent.py")
