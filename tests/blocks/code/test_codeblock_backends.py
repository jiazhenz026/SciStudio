"""Regression tests for CodeBlock v2 backend ``working_directory`` plumbing.

Issue #1309: the python and notebook backends used to hard-code
``cwd=context.exchange_dir`` for the launched subprocess, ignoring
:attr:`CodeBlockConfig.working_directory`. ADR-041 §4 promises that
scripts launch from ``working_directory`` (default ``"."`` = project
root) so they can read project-relative paths like ``Path("data/raw")``.
The exchange dir remains the materialisation target for declared ports;
only the *executing* process cwd changes.

These tests mock the subprocess and version-probe calls so they run in
CI without a Python interpreter or nbconvert installation on PATH.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scistudio.blocks.code.backends.notebook import (
    NotebookCodeBlockBackend,
    executed_notebook_path,
)
from scistudio.blocks.code.backends.python import PythonCodeBlockBackend
from scistudio.blocks.code.code_block import CodeBlockRuntimeContext
from scistudio.blocks.code.config import CodeBlockConfig
from scistudio.blocks.code.interpreters import ResolvedInterpreter


def _make_python_context(
    tmp_path: Path,
    *,
    script_relpath: str = "scripts/run.py",
    working_directory: str = ".",
) -> tuple[CodeBlockRuntimeContext, Path]:
    project_dir = tmp_path
    scripts = project_dir / "scripts"
    scripts.mkdir(exist_ok=True)
    script_abs = project_dir / script_relpath
    script_abs.parent.mkdir(parents=True, exist_ok=True)
    script_abs.write_text("import sys; sys.exit(0)\n", encoding="utf-8")

    config = CodeBlockConfig(script_path=script_relpath, working_directory=working_directory)
    exchange_dir = project_dir / "exchange" / "codeblock-block" / "run-1"
    exchange_dir.mkdir(parents=True, exist_ok=True)

    context = CodeBlockRuntimeContext(
        config=config,
        script_path=script_abs,
        project_dir=project_dir,
        exchange_dir=exchange_dir,
        environment_config={},
    )
    return context, project_dir


def _make_notebook_context(
    tmp_path: Path,
    *,
    notebook_relpath: str = "scripts/analysis.ipynb",
    working_directory: str = ".",
) -> tuple[CodeBlockRuntimeContext, Path]:
    project_dir = tmp_path
    notebook_abs = project_dir / notebook_relpath
    notebook_abs.parent.mkdir(parents=True, exist_ok=True)
    notebook_abs.write_text("{}", encoding="utf-8")

    config = CodeBlockConfig(
        script_path=notebook_relpath,
        working_directory=working_directory,
        timeout_seconds=30,
    )
    exchange_dir = project_dir / "exchange" / "codeblock-block" / "run-1"
    exchange_dir.mkdir(parents=True, exist_ok=True)

    context = CodeBlockRuntimeContext(
        config=config,
        script_path=notebook_abs,
        project_dir=project_dir,
        exchange_dir=exchange_dir,
        environment_config={},
    )
    return context, project_dir


# ---------------------------------------------------------------------------
# Python backend
# ---------------------------------------------------------------------------


class TestPythonBackendCwd:
    def test_run_launches_subprocess_from_resolved_working_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ADR-041 §4: default ``working_directory='.'`` means cwd = project root."""
        context, project_dir = _make_python_context(tmp_path)
        interpreter = ResolvedInterpreter(
            family="python",
            executable="python",
            argv=["python", str(context.script_path)],
            working_directory=project_dir.as_posix(),
            environment={},
            version="3.12.0",
            warnings=[],
        )

        captured: dict[str, Any] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured["cwd"] = kwargs.get("cwd")
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        PythonCodeBlockBackend().run(context, interpreter)

        assert captured["cwd"] == context.config.resolve_working_directory(project_dir)
        assert captured["cwd"] == project_dir.resolve()
        # Exchange dir must NOT be passed as the subprocess cwd anymore.
        assert captured["cwd"] != context.exchange_dir

    def test_run_honours_custom_working_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A non-default ``working_directory`` resolves under the project root."""
        # Create a project-relative subdir to use as the working directory.
        (tmp_path / "analysis").mkdir()
        context, project_dir = _make_python_context(tmp_path, working_directory="analysis")
        interpreter = ResolvedInterpreter(
            family="python",
            executable="python",
            argv=["python", str(context.script_path)],
            working_directory=(project_dir / "analysis").as_posix(),
            environment={},
            version="3.12.0",
            warnings=[],
        )

        captured: dict[str, Any] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured["cwd"] = kwargs.get("cwd")
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        PythonCodeBlockBackend().run(context, interpreter)

        assert captured["cwd"] == (project_dir / "analysis").resolve()


# ---------------------------------------------------------------------------
# Notebook backend
# ---------------------------------------------------------------------------


class TestNotebookBackendCwd:
    def test_resolve_sets_execute_preprocessor_cwd_to_working_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """nbconvert receives ``--ExecutePreprocessor.cwd=<resolved working dir>``."""
        # Avoid invoking jupyter --version on a CI box without it.
        monkeypatch.setattr(
            "scistudio.blocks.code.backends.notebook._probe_nbconvert_version",
            lambda _executable: ("nbconvert 7.0.0", []),
        )
        context, project_dir = _make_notebook_context(tmp_path)
        backend = NotebookCodeBlockBackend(
            executable_locator=lambda executable: (
                "/fake/path/to/jupyter-nbconvert" if executable == "jupyter-nbconvert" else None
            )
        )

        interpreter = backend.resolve(context)

        expected_cwd = context.config.resolve_working_directory(project_dir)
        assert expected_cwd == project_dir.resolve()
        # The interpreter's reported working_directory must match the
        # resolved working directory, not the exchange dir.
        assert interpreter.working_directory == expected_cwd.as_posix()
        # The nbconvert kernel cwd must match the resolved working directory.
        assert f"--ExecutePreprocessor.cwd={expected_cwd}" in interpreter.argv
        # Sanity: it must NOT silently keep the old exchange-dir behaviour.
        assert f"--ExecutePreprocessor.cwd={context.exchange_dir}" not in interpreter.argv

    def test_run_launches_nbconvert_subprocess_from_working_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The subprocess running nbconvert also launches from ``working_directory``."""
        monkeypatch.setattr(
            "scistudio.blocks.code.backends.notebook._probe_nbconvert_version",
            lambda _executable: ("nbconvert 7.0.0", []),
        )
        context, project_dir = _make_notebook_context(tmp_path)
        backend = NotebookCodeBlockBackend(
            executable_locator=lambda executable: (
                "/fake/path/to/jupyter-nbconvert" if executable == "jupyter-nbconvert" else None
            )
        )
        # ``resolve`` is called by the host CodeBlock; capture its output so we
        # can pass a valid ``ResolvedInterpreter`` into ``run``.
        interpreter = backend.resolve(context)

        # ``run`` copies the source notebook into the framework-managed
        # executed-notebook output dir. Ensure that path exists before the
        # copy so ``shutil.copy2`` doesn't fail before our captured run.
        executed_path = executed_notebook_path(context)
        executed_path.parent.mkdir(parents=True, exist_ok=True)

        captured: dict[str, Any] = {}

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured["cwd"] = kwargs.get("cwd")
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)

        backend.run(context, interpreter)

        expected_cwd = context.config.resolve_working_directory(project_dir)
        assert captured["cwd"] == expected_cwd
        assert captured["cwd"] == project_dir.resolve()
        assert captured["cwd"] != context.exchange_dir

    def test_resolve_honours_custom_working_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A non-default ``working_directory`` resolves under the project root
        and is forwarded to nbconvert."""
        monkeypatch.setattr(
            "scistudio.blocks.code.backends.notebook._probe_nbconvert_version",
            lambda _executable: ("nbconvert 7.0.0", []),
        )
        (tmp_path / "analysis").mkdir()
        context, project_dir = _make_notebook_context(tmp_path, working_directory="analysis")
        backend = NotebookCodeBlockBackend(
            executable_locator=lambda executable: (
                "/fake/path/to/jupyter-nbconvert" if executable == "jupyter-nbconvert" else None
            )
        )

        interpreter = backend.resolve(context)

        expected_cwd = (project_dir / "analysis").resolve()
        assert interpreter.working_directory == expected_cwd.as_posix()
        assert f"--ExecutePreprocessor.cwd={expected_cwd}" in interpreter.argv
