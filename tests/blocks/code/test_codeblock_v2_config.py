from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scieasy.blocks.code.config import (
    CodeBlockConfig,
    CodeBlockConfigError,
    PortFileConfig,
    legacy_migration_diagnostics,
)


def test_valid_codeblock_v2_config_resolves_project_local_paths(tmp_path: Path) -> None:
    script = tmp_path / "scripts" / "segment.py"
    script.parent.mkdir()
    script.write_text("print('ok')\n", encoding="utf-8")

    config = CodeBlockConfig(
        script_path="scripts/segment.py",
        working_directory=".",
        exchange_root="exchange",
        inputs=[PortFileConfig(name="image", direction="input", data_type="Image", extension="tif")],
        outputs=[PortFileConfig(name="table", direction="output", data_type="DataFrame", extension=".CSV")],
        timeout_seconds=10,
    )

    assert config.resolve_script_path(tmp_path) == script.resolve()
    assert config.resolve_working_directory(tmp_path) == tmp_path.resolve()
    assert config.resolve_exchange_root(tmp_path) == (tmp_path / "exchange").resolve()
    assert config.inputs[0].extension == ".tif"
    assert config.inputs[0].exchange_folder == "inputs/image/"
    assert config.outputs[0].extension == ".csv"
    assert config.outputs[0].exchange_folder == "outputs/table/"


def test_mixed_inline_and_script_config_is_rejected() -> None:
    with pytest.raises(ValidationError, match="does not support inline code"):
        CodeBlockConfig(script_path="scripts/segment.py", inline_code="print('legacy')")


def test_entry_function_script_config_is_rejected() -> None:
    with pytest.raises(ValidationError, match="does not call SciEasy entry functions"):
        CodeBlockConfig(script_path="scripts/segment.py", entry_function="run")


def test_missing_script_path_fails_project_validation(tmp_path: Path) -> None:
    config = CodeBlockConfig(script_path="scripts/missing.py")

    with pytest.raises(FileNotFoundError):
        config.resolve_script_path(tmp_path)


def test_outside_project_script_path_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_codeblock_v2.py"
    outside.write_text("print('outside')\n", encoding="utf-8")
    config = CodeBlockConfig(script_path=str(outside))

    try:
        with pytest.raises(CodeBlockConfigError, match="inside the project"):
            config.resolve_script_path(tmp_path)
    finally:
        outside.unlink(missing_ok=True)


def test_legacy_migration_diagnostics_are_explicit() -> None:
    diagnostics = legacy_migration_diagnostics({"mode": "inline", "script": "result = data", "entry_function": "run"})

    assert [diagnostic.legacy_mode for diagnostic in diagnostics] == ["inline", "inline"]
    assert all(diagnostic.severity == "error" for diagnostic in diagnostics)
    assert all("ADR-041" in diagnostic.reference for diagnostic in diagnostics)
