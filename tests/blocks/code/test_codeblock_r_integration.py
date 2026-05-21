"""Legacy R CodeBlock integration expectations.

ADR-041 Track C wires the common runtime and Python backend.  R support is outside this track, and
legacy ``language='r'`` inline runner configs must fail with explicit migration
diagnostics instead of executing through the old CodeBlock runner path.
"""

from __future__ import annotations

import pytest

from scistudio.blocks.code.code_block import CodeBlock, CodeBlockMigrationError


def test_legacy_r_inline_config_reports_migration() -> None:
    block = CodeBlock(config={"params": {"language": "r", "mode": "inline", "script": "filtered <- data"}})

    with pytest.raises(CodeBlockMigrationError) as exc_info:
        block.run({}, block.config)

    assert "Legacy CodeBlock field 'language'" in str(exc_info.value)
    assert any(diagnostic.legacy_mode == "inline" for diagnostic in exc_info.value.diagnostics)


def test_legacy_r_error_script_reports_migration_before_execution() -> None:
    block = CodeBlock(config={"params": {"language": "r", "mode": "inline", "script": 'stop("boom")'}})

    with pytest.raises(CodeBlockMigrationError):
        block.run({}, block.config)
