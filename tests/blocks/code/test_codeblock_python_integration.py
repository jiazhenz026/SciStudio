"""Legacy Python CodeBlock integration expectations.

ADR-041 removes inline/function-mode CodeBlock execution.  The Python backend coverage lives in ``test_codeblock_execution.py`` and uses file exchange instead.
These tests keep the former integration surface explicit by asserting migration
diagnostics for legacy inline runner configs.
"""

from __future__ import annotations

import pytest

from scieasy.blocks.code.code_block import CodeBlock, CodeBlockMigrationError


def test_legacy_python_inline_pipeline_reports_migration() -> None:
    block = CodeBlock(config={"params": {"language": "python", "mode": "inline", "script": "processed = []"}})

    with pytest.raises(CodeBlockMigrationError) as exc_info:
        block.run({}, block.config)

    assert "Inline CodeBlock configs are not valid" in str(exc_info.value)
    assert any(diagnostic.legacy_mode == "inline" for diagnostic in exc_info.value.diagnostics)


def test_legacy_python_language_field_reports_migration() -> None:
    block = CodeBlock(config={"params": {"language": "python", "script_path": "scripts/legacy.py"}})

    with pytest.raises(CodeBlockMigrationError) as exc_info:
        block.run({}, block.config)

    assert "Legacy CodeBlock field 'language'" in str(exc_info.value)
