"""POSIX shell backend for CodeBlock v2."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scieasy.blocks.code.code_block import (
    CodeBlockRuntimeContext,
    register_codeblock_backend,
    run_codeblock_process,
)
from scieasy.blocks.code.config import CodeBlockConfig, InterpreterMode
from scieasy.blocks.code.interpreters import InterpreterResolutionError, ResolvedInterpreter

_SHELL_CANDIDATES = ("sh", "bash", "dash", "zsh")


class ShellCodeBlockBackend:
    """Shell `.sh` backend for the ADR-041 shared runtime."""

    name = "shell"
    extensions = frozenset({".sh"})

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        return script_path.suffix.lower() in self.extensions

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        executable = _resolve_shell_executable(
            mode=context.config.interpreter_mode,
            interpreter_path=context.config.interpreter_path,
            environment_config=context.environment_config,
        )
        version, warnings = _probe_shell_version(executable)

        return ResolvedInterpreter(
            family="shell",
            executable=executable,
            argv=[executable, str(context.script_path)],
            working_directory=context.exchange_dir.as_posix(),
            environment=_environment_delta(context),
            version=version,
            warnings=warnings,
        )

    def run(
        self,
        context: CodeBlockRuntimeContext,
        interpreter: ResolvedInterpreter,
    ) -> subprocess.CompletedProcess[str]:
        return run_codeblock_process(
            argv=interpreter.argv,
            cwd=context.exchange_dir,
            env_delta=interpreter.environment,
            timeout_seconds=context.config.timeout_seconds,
        )


def _resolve_shell_executable(
    *,
    mode: InterpreterMode,
    interpreter_path: str | None,
    environment_config: Mapping[str, Any],
) -> str:
    configured = interpreter_path or environment_config.get("interpreter_path") or environment_config.get("shell")
    if mode == "existing":
        if configured is None:
            raise InterpreterResolutionError("interpreter_mode='existing' requires a POSIX shell executable path")
        return _resolve_executable(str(configured), require_compatible=True)
    if mode != "auto":
        raise InterpreterResolutionError(f"Unsupported interpreter mode: {mode}")

    if configured is not None:
        return _resolve_executable(str(configured), require_compatible=True)

    for candidate in _SHELL_CANDIDATES:
        discovered = shutil.which(candidate)
        if discovered is None:
            continue
        resolved = str(Path(discovered).resolve())
        if _is_compatible_shell(resolved):
            return resolved
    raise InterpreterResolutionError(
        "POSIX shell executable not found on PATH; install sh/bash/dash/zsh or set interpreter_path."
    )


def _resolve_executable(raw_executable: str, *, require_compatible: bool) -> str:
    raw_executable = raw_executable.strip()
    if not raw_executable:
        raise InterpreterResolutionError("POSIX shell executable path must not be empty")

    candidate = Path(raw_executable)
    has_path_component = candidate.is_absolute() or any(part in raw_executable for part in ("/", "\\"))
    if has_path_component:
        resolved = candidate.expanduser().resolve()
        if not resolved.exists() or not resolved.is_file():
            raise InterpreterResolutionError(f"POSIX shell executable not found: {raw_executable}")
        executable = str(resolved)
        if require_compatible and not _is_compatible_shell(executable):
            raise InterpreterResolutionError(f"POSIX shell executable is not usable: {raw_executable}")
        return executable

    discovered = shutil.which(raw_executable)
    if discovered is None:
        raise InterpreterResolutionError(f"POSIX shell executable not found on PATH: {raw_executable}")
    executable = str(Path(discovered).resolve())
    if require_compatible and not _is_compatible_shell(executable):
        raise InterpreterResolutionError(f"POSIX shell executable is not usable: {raw_executable}")
    return executable


def _is_compatible_shell(executable: str) -> bool:
    if _is_windows_system_bash(executable):
        return False
    try:
        completed = subprocess.run(
            [executable, "-c", "exit 0"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _is_windows_system_bash(executable: str) -> bool:
    if os.name != "nt":
        return False
    path = Path(executable)
    return path.name.lower() == "bash.exe" and path.parent.name.lower() == "system32"


def _environment_delta(context: CodeBlockRuntimeContext) -> dict[str, str]:
    env_delta = _configured_environment(context.environment_config)
    exchange_dir = context.exchange_dir.resolve()
    env_delta.update(
        {
            "SCIEASY_CODEBLOCK_EXCHANGE_DIR": str(exchange_dir),
            "SCIEASY_CODEBLOCK_INPUTS_DIR": str((exchange_dir / "inputs").resolve()),
            "SCIEASY_CODEBLOCK_OUTPUTS_DIR": str((exchange_dir / "outputs").resolve()),
            "SCIEASY_CODEBLOCK_PROJECT_DIR": str(context.project_dir.resolve()),
            "SCIEASY_CODEBLOCK_SCRIPT_PATH": str(context.script_path.resolve()),
        }
    )
    return dict(sorted(env_delta.items()))


def _configured_environment(environment_config: Mapping[str, Any]) -> dict[str, str]:
    raw_delta = (
        environment_config.get("environment_variables")
        or environment_config.get("env")
        or environment_config.get("environment")
        or {}
    )
    if not isinstance(raw_delta, Mapping):
        raise InterpreterResolutionError("environment variables must be a mapping")
    return {str(key): str(value) for key, value in raw_delta.items()}


def _probe_shell_version(executable: str) -> tuple[str | None, list[str]]:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, [f"Could not capture shell version: {exc}"]

    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        return None, [f"Shell version command exited with {completed.returncode}"]
    return output or None, []


def register() -> None:
    """Register the shell backend with the shared CodeBlock runtime."""

    register_codeblock_backend(ShellCodeBlockBackend(), replace=True)
