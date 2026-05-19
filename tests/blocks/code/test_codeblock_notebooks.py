from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scieasy.blocks.code.backends.notebook import NotebookCodeBlockBackend, executed_notebook_path
from scieasy.blocks.code.code_block import (
    CodeBlock,
    CodeBlockExecutionError,
    CodeBlockRuntimeContext,
    list_codeblock_backends,
)
from scieasy.blocks.code.config import CodeBlockConfig
from scieasy.blocks.code.interpreters import InterpreterResolutionError
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.base import DataObject
from scieasy.core.types.text import Text


def _write_notebook(project_dir: Path, source: str, *, name: str = "analysis.ipynb") -> Path:
    scripts = project_dir / "scripts"
    scripts.mkdir(exist_ok=True)
    notebook = scripts / name
    notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {
                        "cell_type": "code",
                        "execution_count": None,
                        "metadata": {},
                        "outputs": [],
                        "source": source.splitlines(keepends=True),
                    }
                ],
                "metadata": {
                    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                    "language_info": {"name": "python", "pygments_lexer": "ipython3"},
                },
                "nbformat": 4,
                "nbformat_minor": 5,
            }
        ),
        encoding="utf-8",
    )
    return notebook


def _reconstruct_adapter(
    path: Path,
    target_type: type[DataObject],
    extension: str,
    *,
    capability_id: str | None = None,
) -> DataObject:
    if target_type is Text:
        assert extension == ".txt"
        return Text(content=path.read_text(encoding="utf-8"))
    if target_type is Artifact:
        assert extension == ".ipynb"
        return Artifact(
            file_path=path,
            mime_type="application/x-ipynb+json",
            description=path.name,
        )
    raise AssertionError(f"Unexpected target_type: {target_type!r}")


def _block_config(project_dir: Path, script_path: str, **params: object) -> dict[str, object]:
    base: dict[str, object] = {
        "project_dir": str(project_dir),
        "script_path": script_path,
        "interpreter_mode": "auto",
        "exchange_root": "exchange",
        "block_id": "notebook-block",
        "run_id": "run-1",
        "reconstruct_adapter": _reconstruct_adapter,
    }
    base.update(params)
    return {"params": base}


def _notebook_tool() -> str | None:
    nbconvert = shutil.which("jupyter-nbconvert")
    if nbconvert is not None:
        return nbconvert
    jupyter = shutil.which("jupyter")
    if jupyter is None:
        return None
    completed = subprocess.run(
        [jupyter, "nbconvert", "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return jupyter if completed.returncode == 0 else None


def _require_notebook_tool() -> None:
    if _notebook_tool() is None:
        pytest.skip("Jupyter nbconvert is not installed in this environment.")


def test_notebook_backend_loader_registers_ipynb_backend() -> None:
    backends = list_codeblock_backends()

    notebook_backend = next(backend for backend in backends if backend.name == "notebook")
    assert ".ipynb" in notebook_backend.extensions


def test_notebook_backend_reports_clear_missing_dependency(tmp_path: Path) -> None:
    script = _write_notebook(tmp_path, "print('hello')\n")
    config = CodeBlockConfig(script_path="scripts/analysis.ipynb")
    context = CodeBlockRuntimeContext(
        config=config,
        script_path=script,
        project_dir=tmp_path,
        exchange_dir=tmp_path / "exchange",
        environment_config={},
    )
    backend = NotebookCodeBlockBackend(executable_locator=lambda executable: None)

    with pytest.raises(InterpreterResolutionError, match="requires Jupyter nbconvert"):
        backend.resolve(context)


def test_notebook_backend_builds_inplace_nbconvert_command(tmp_path: Path) -> None:
    script = _write_notebook(tmp_path, "print('hello')\n")
    exchange_dir = tmp_path / "exchange"
    config = CodeBlockConfig(script_path="scripts/analysis.ipynb", timeout_seconds=30)
    context = CodeBlockRuntimeContext(
        config=config,
        script_path=script,
        project_dir=tmp_path,
        exchange_dir=exchange_dir,
        environment_config={},
    )
    backend = NotebookCodeBlockBackend(
        executable_locator=lambda executable: "C:/tools/jupyter-nbconvert.exe" if executable == "jupyter-nbconvert" else None
    )

    interpreter = backend.resolve(context)

    assert interpreter.family == "notebook"
    assert interpreter.executable == str(Path("C:/tools/jupyter-nbconvert.exe").resolve())
    assert interpreter.argv[0] == interpreter.executable
    assert "--inplace" in interpreter.argv
    assert str(executed_notebook_path(context)) in interpreter.argv
    assert f"--ExecutePreprocessor.cwd={exchange_dir}" in interpreter.argv
    assert "--ExecutePreprocessor.timeout=30" in interpreter.argv


def test_codeblock_runs_notebook_and_collects_typed_output_plus_executed_artifact(tmp_path: Path) -> None:
    _require_notebook_tool()
    _write_notebook(
        tmp_path,
        """
from pathlib import Path

Path("outputs/summary/result.txt").write_text("notebook ok", encoding="utf-8")
""".lstrip(),
    )
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/analysis.ipynb",
            outputs=[
                {"name": "summary", "direction": "output", "data_type": "Text", "extension": ".txt"},
                {
                    "name": "_executed_notebook",
                    "direction": "output",
                    "data_type": "Artifact",
                    "extension": ".ipynb",
                },
            ],
        )
    )

    outputs = block.run({}, block.config)

    assert outputs["summary"][0].content == "notebook ok"
    executed_artifact = outputs["_executed_notebook"][0]
    assert isinstance(executed_artifact, Artifact)
    assert executed_artifact.file_path is not None
    assert executed_artifact.file_path.name == "analysis.executed.ipynb"
    assert executed_artifact.file_path.is_file()
    assert block.last_process is not None
    assert block.last_process.returncode == 0


def test_failed_notebook_retains_executed_artifact_file_when_nbconvert_created_it(tmp_path: Path) -> None:
    _require_notebook_tool()
    _write_notebook(
        tmp_path,
        """
from pathlib import Path

Path("outputs/summary/result.txt").write_text("before failure", encoding="utf-8")
raise RuntimeError("notebook boom")
""".lstrip(),
    )
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/analysis.ipynb",
            outputs=[
                {"name": "summary", "direction": "output", "data_type": "Text", "extension": ".txt"},
                {
                    "name": "_executed_notebook",
                    "direction": "output",
                    "data_type": "Artifact",
                    "extension": ".ipynb",
                },
            ],
        )
    )

    with pytest.raises(CodeBlockExecutionError):
        block.run({}, block.config)

    assert block.last_exchange_manifest is not None
    artifact_folder = block.last_exchange_manifest.output_folders["_executed_notebook"]
    retained = artifact_folder / "analysis.executed.ipynb"
    assert retained.is_file()
    assert block.last_process is not None
    assert block.last_process.returncode != 0


def test_notebook_execution_live_test_skips_when_optional_dependency_missing() -> None:
    if _notebook_tool() is None:
        pytest.skip("Jupyter nbconvert is not installed in this environment.")
    assert _notebook_tool() is not None
