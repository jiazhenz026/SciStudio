from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scieasy.blocks.code.interpreters import (
    InterpreterResolutionError,
    ResolvedInterpreter,
    UnsupportedScriptExtensionError,
    resolve_script_interpreter,
)


def _write_script(project_dir: Path, name: str = "scripts/run.py") -> Path:
    script = project_dir / name
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("print('ok')\n", encoding="utf-8")
    return script


def test_auto_interpreter_resolution_uses_active_python(tmp_path: Path) -> None:
    script = _write_script(tmp_path)

    resolved = resolve_script_interpreter(script, project_dir=tmp_path)

    assert resolved.family == "python"
    assert Path(resolved.executable).resolve() == Path(sys.executable).resolve()
    assert resolved.argv == [resolved.executable, "scripts/run.py"]
    assert resolved.working_directory == tmp_path.resolve().as_posix()
    assert resolved.version is None or "Python" in resolved.version


def test_existing_interpreter_resolution_accepts_explicit_executable(tmp_path: Path) -> None:
    script = _write_script(tmp_path)

    resolved = resolve_script_interpreter(
        script,
        project_dir=tmp_path,
        mode="existing",
        interpreter_path=sys.executable,
        environment_config={"environment_variables": {"SCIEASY_CODEBLOCK_TEST": "1"}},
    )

    assert Path(resolved.executable).resolve() == Path(sys.executable).resolve()
    assert resolved.environment == {"SCIEASY_CODEBLOCK_TEST": "1"}


def test_existing_interpreter_resolution_requires_executable(tmp_path: Path) -> None:
    script = _write_script(tmp_path)

    with pytest.raises(InterpreterResolutionError, match="requires an interpreter path"):
        resolve_script_interpreter(script, project_dir=tmp_path, mode="existing")


def test_missing_interpreter_path_fails(tmp_path: Path) -> None:
    script = _write_script(tmp_path)
    missing = tmp_path / "missing-python.exe"

    with pytest.raises(InterpreterResolutionError, match="not found"):
        resolve_script_interpreter(script, project_dir=tmp_path, mode="existing", interpreter_path=missing)


def test_unsupported_script_extension_fails_before_interpreter_lookup(tmp_path: Path) -> None:
    script = _write_script(tmp_path, "scripts/run.R")

    with pytest.raises(UnsupportedScriptExtensionError, match=r"supports \.py scripts only"):
        resolve_script_interpreter(script, project_dir=tmp_path)


@pytest.mark.parametrize("family", ["python", "notebook", "r", "quarto", "shell", "matlab", "octave"])
def test_resolved_interpreter_accepts_all_adr041_runtime_families(family: str) -> None:
    resolved = ResolvedInterpreter(
        family=family,
        executable="runtime",
        argv=["runtime", "script"],
        working_directory=".",
    )

    assert resolved.family == family
