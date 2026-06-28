"""Tests for CodeBlock — inline Python, script Python, Collection unpack/repack."""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.blocks.code.code_block import CodeBlock, CodeBlockMigrationError
from scistudio.blocks.code.introspect import introspect_script

# ADR-052 §7A: the legacy runner layer (runner_registry.py + runners/*) is dead
# code (0 production importers; code_block.py uses backends/) and is deleted in
# #1817. The old TestPythonRunnerInline / TestPythonRunnerScript classes that
# exercised scistudio.blocks.code.runners.python_runner were removed with the
# runner import. CodeBlock + introspect coverage stays below.


class TestCodeBlockInline:
    """Legacy CodeBlock inline mode now reports ADR-041 migration diagnostics."""

    def test_inline_execution_reports_migration(self) -> None:
        block = CodeBlock(config={"params": {"script": "result = 42"}})
        with pytest.raises(CodeBlockMigrationError, match="Inline CodeBlock configs are not valid"):
            block.run({}, block.config)

    def test_inline_with_input_reports_migration(self) -> None:
        block = CodeBlock(config={"params": {"script": "output = data * 2"}})
        with pytest.raises(CodeBlockMigrationError, match="Inline CodeBlock configs are not valid"):
            block.run({"data": 10}, block.config)


class TestCodeBlockScript:
    """Legacy CodeBlock entry-function script mode now reports migration diagnostics."""

    def test_entry_function_script_reports_migration(self, tmp_path: Path) -> None:
        script = tmp_path / "block_script.py"
        script.write_text("def run(inputs, config):\n    return {'result': sum(inputs.get('values', []))}\n")
        block = CodeBlock(config={"params": {"project_dir": str(tmp_path), "script_path": "block_script.py"}})
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
