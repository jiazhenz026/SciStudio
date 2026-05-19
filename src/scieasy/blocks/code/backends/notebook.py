"""Notebook backend for CodeBlock v2."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from scieasy.blocks.code.code_block import (
    CodeBlockRuntimeContext,
    register_codeblock_backend,
    run_codeblock_process,
)
from scieasy.blocks.code.config import CodeBlockConfig
from scieasy.blocks.code.exchange import safe_exchange_name
from scieasy.blocks.code.interpreters import InterpreterResolutionError, ResolvedInterpreter

_EXECUTED_NOTEBOOK_PORT = "_executed_notebook"
_NOTEBOOK_MIME_TYPE = "application/x-ipynb+json"


class NotebookCodeBlockBackend:
    """Jupyter notebook backend for ADR-041 CodeBlock v2."""

    name = "notebook"
    extensions = frozenset({".ipynb"})

    def __init__(self, executable_locator: Callable[[str], str | None] | None = None) -> None:
        self._executable_locator = executable_locator or shutil.which

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        return script_path.suffix.lower() in self.extensions

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        executable = self._resolve_executable(context.config)
        target = executed_notebook_path(context)
        argv = _nbconvert_argv(
            executable,
            source_notebook=target,
            execution_cwd=context.exchange_dir,
            timeout_seconds=context.config.timeout_seconds,
        )
        version, warnings = _probe_nbconvert_version(executable)
        return ResolvedInterpreter(
            family="notebook",
            executable=executable,
            argv=argv,
            working_directory=context.exchange_dir.as_posix(),
            environment=_environment_delta(context.environment_config),
            version=version,
            warnings=warnings,
        )

    def run(
        self,
        context: CodeBlockRuntimeContext,
        interpreter: ResolvedInterpreter,
    ) -> subprocess.CompletedProcess[str]:
        target = executed_notebook_path(context)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(context.script_path, target)
        return run_codeblock_process(
            argv=interpreter.argv,
            cwd=context.exchange_dir,
            env_delta=interpreter.environment,
            timeout_seconds=context.config.timeout_seconds,
        )

    def _resolve_executable(self, config: CodeBlockConfig) -> str:
        if config.interpreter_mode == "existing":
            if not config.interpreter_path:
                raise InterpreterResolutionError(
                    "Notebook CodeBlock interpreter_mode='existing' requires interpreter_path."
                )
            return _resolve_configured_executable(config.interpreter_path)

        if config.interpreter_mode != "auto":
            raise InterpreterResolutionError(f"Unsupported notebook interpreter mode: {config.interpreter_mode}")

        discovered_nbconvert = self._executable_locator("jupyter-nbconvert")
        if discovered_nbconvert:
            return str(Path(discovered_nbconvert).resolve())

        discovered_jupyter = self._executable_locator("jupyter")
        if discovered_jupyter and _jupyter_has_nbconvert(discovered_jupyter):
            return str(Path(discovered_jupyter).resolve())
        raise InterpreterResolutionError(
            "Notebook CodeBlock backend requires Jupyter nbconvert. Install the optional Jupyter tooling "
            "or set interpreter_mode='existing' with an executable path."
        )


def executed_notebook_path(context: CodeBlockRuntimeContext) -> Path:
    """Return the framework-managed executed notebook artifact path."""

    folder = _executed_notebook_output_dir(context)
    return folder / f"{context.script_path.stem}.executed.ipynb"


def _executed_notebook_output_dir(context: CodeBlockRuntimeContext) -> Path:
    # TODO(#1245): Let backends inject framework-managed CodeBlock outputs before
    #   port planning so `_executed_notebook` does not need a declared port to be
    #   returned from CodeBlock.run().
    #   Out of scope per ADR-041 section 7 and docs/specs/adr-041-codeblock-v2.md AC-011.
    #   Followup: https://github.com/zjzcpj/SciEasy/issues/1245.
    for output in context.config.outputs:
        if output.name == _EXECUTED_NOTEBOOK_PORT and output.exchange_folder:
            folder = output.exchange_folder.replace("\\", "/").strip("/")
            if folder.startswith("outputs/"):
                folder = folder[len("outputs/") :]
            if folder:
                return context.exchange_dir / "outputs" / safe_exchange_name(folder)
    return context.exchange_dir / "outputs" / safe_exchange_name(_EXECUTED_NOTEBOOK_PORT)


def _resolve_configured_executable(raw_executable: str) -> str:
    raw_executable = raw_executable.strip()
    if not raw_executable:
        raise InterpreterResolutionError("Notebook interpreter executable must not be empty.")

    candidate = Path(raw_executable)
    has_path_component = candidate.is_absolute() or any(part in raw_executable for part in ("/", "\\"))
    if has_path_component:
        resolved = candidate.expanduser().resolve()
        if not resolved.exists() or not resolved.is_file():
            raise InterpreterResolutionError(f"Notebook interpreter executable not found: {raw_executable}")
        return str(resolved)

    discovered = shutil.which(raw_executable)
    if discovered is None:
        raise InterpreterResolutionError(f"Notebook interpreter executable not found on PATH: {raw_executable}")
    return str(Path(discovered).resolve())


def _nbconvert_argv(
    executable: str,
    *,
    source_notebook: Path,
    execution_cwd: Path,
    timeout_seconds: float | None,
) -> list[str]:
    executable_name = Path(executable).name.lower()
    argv = [executable]
    if "nbconvert" not in executable_name:
        argv.append("nbconvert")
    argv.extend(
        [
            "--to",
            "notebook",
            "--execute",
            "--inplace",
            str(source_notebook),
            f"--ExecutePreprocessor.cwd={execution_cwd}",
        ]
    )
    if timeout_seconds is not None:
        argv.append(f"--ExecutePreprocessor.timeout={max(1, int(timeout_seconds))}")
    return argv


def _probe_nbconvert_version(executable: str) -> tuple[str | None, list[str]]:
    argv = [executable, "--version"] if "nbconvert" in Path(executable).name.lower() else [executable, "nbconvert", "--version"]
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, [f"Could not capture notebook interpreter version: {exc}"]

    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        return None, [f"Notebook interpreter version command exited with {completed.returncode}"]
    return output or None, []


def _jupyter_has_nbconvert(executable: str) -> bool:
    version, _warnings = _probe_nbconvert_version(executable)
    return version is not None


def _environment_delta(environment_config: Mapping[str, object]) -> dict[str, str]:
    raw_delta = (
        environment_config.get("environment_variables")
        or environment_config.get("env")
        or environment_config.get("environment")
        or {}
    )
    if not isinstance(raw_delta, Mapping):
        raise InterpreterResolutionError("Notebook environment variables must be a mapping.")
    return {str(key): str(value) for key, value in raw_delta.items() if os.environ.get(str(key)) != str(value)}


def register() -> None:
    """Register the notebook backend with the shared CodeBlock runtime."""

    register_codeblock_backend(NotebookCodeBlockBackend(), replace=True)
