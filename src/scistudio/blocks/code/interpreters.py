"""Interpreter resolution helpers for CodeBlock v2.

Track A supports deterministic Python interpreter resolution only.  Later
tracks can add more families behind this same narrow surface.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from scistudio.blocks.code.config import InterpreterMode, resolve_project_path
from scistudio.stability import provisional

# Stability: provisional type-alias (ADR-052 §7A). ``Literal`` special forms
# cannot carry a stability marker; tier is recorded in the ADR-052 contract.
InterpreterFamily = Literal["python", "notebook", "r", "quarto", "shell", "matlab", "octave"]


@provisional(since="0.3.1")
class InterpreterResolutionError(RuntimeError):
    """Raised when CodeBlock v2 cannot produce a safe interpreter command."""


@provisional(since="0.3.1")
class UnsupportedScriptExtensionError(InterpreterResolutionError):
    """Raised when Track A does not support a script extension."""


@provisional(since="0.3.1")
class ResolvedInterpreter(BaseModel):
    """Resolved command metadata for launching a CodeBlock v2 script."""

    model_config = ConfigDict(extra="forbid")

    family: InterpreterFamily
    executable: str
    argv: list[str]
    working_directory: str
    environment: dict[str, str] = Field(default_factory=dict)
    version: str | None = None
    warnings: list[str] = Field(default_factory=list)


@provisional(since="0.3.1")
def resolve_script_interpreter(
    script_path: Path,
    *,
    environment_config: Mapping[str, Any] | None = None,
    project_dir: Path,
    mode: InterpreterMode = "auto",
    interpreter_path: Path | str | None = None,
) -> ResolvedInterpreter:
    """Resolve an interpreter for *script_path* under ADR-041 constraints."""

    environment_config = environment_config or {}
    resolved_script = resolve_project_path(script_path, project_dir=project_dir, field_name="script_path")
    if resolved_script.suffix.lower() != ".py":
        raise UnsupportedScriptExtensionError(
            f"CodeBlock v2 Track A supports .py scripts only; got {resolved_script.suffix or '<none>'}"
        )

    executable = _resolve_python_executable(
        mode=mode,
        interpreter_path=interpreter_path,
        environment_config=environment_config,
    )
    working_directory = _resolve_working_directory(environment_config, project_dir=project_dir)
    relative_script = resolved_script.relative_to(project_dir.resolve()).as_posix()
    env_delta = _environment_delta(environment_config)
    version, warnings = _probe_version(executable)

    return ResolvedInterpreter(
        family="python",
        executable=executable,
        argv=[executable, relative_script],
        working_directory=working_directory.as_posix(),
        environment=env_delta,
        version=version,
        warnings=warnings,
    )


def _resolve_python_executable(
    *,
    mode: InterpreterMode,
    interpreter_path: Path | str | None,
    environment_config: Mapping[str, Any],
) -> str:
    configured = interpreter_path or environment_config.get("interpreter_path") or environment_config.get("python")
    if mode == "existing":
        if configured is None:
            raise InterpreterResolutionError("interpreter_mode='existing' requires an interpreter path")
        return _resolve_executable(str(configured))
    if mode != "auto":
        raise InterpreterResolutionError(f"Unsupported interpreter mode: {mode}")

    if configured is not None:
        return _resolve_executable(str(configured))
    return _resolve_executable(sys.executable)


def _resolve_executable(raw_executable: str) -> str:
    raw_executable = raw_executable.strip()
    if not raw_executable:
        raise InterpreterResolutionError("interpreter executable must not be empty")

    candidate = Path(raw_executable)
    has_path_component = candidate.is_absolute() or any(part in raw_executable for part in ("/", "\\"))
    if has_path_component:
        resolved = candidate.expanduser().resolve()
        if not resolved.exists() or not resolved.is_file():
            raise InterpreterResolutionError(f"interpreter executable not found: {raw_executable}")
        return str(resolved)

    discovered = shutil.which(raw_executable)
    if discovered is None:
        raise InterpreterResolutionError(f"interpreter executable not found on PATH: {raw_executable}")
    return str(Path(discovered).resolve())


def _resolve_working_directory(environment_config: Mapping[str, Any], *, project_dir: Path) -> Path:
    raw_working_dir = environment_config.get("working_directory", ".")
    return resolve_project_path(
        str(raw_working_dir),
        project_dir=project_dir,
        field_name="working_directory",
        must_exist=False,
        allow_file=False,
    )


def _environment_delta(environment_config: Mapping[str, Any]) -> dict[str, str]:
    raw_delta = (
        environment_config.get("environment_variables")
        or environment_config.get("env")
        or environment_config.get("environment")
        or {}
    )
    if not isinstance(raw_delta, Mapping):
        raise InterpreterResolutionError("environment variables must be a mapping")
    return {str(key): str(value) for key, value in raw_delta.items() if os.environ.get(str(key)) != str(value)}


def _probe_version(executable: str) -> tuple[str | None, list[str]]:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, [f"Could not capture interpreter version: {exc}"]

    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        return None, [f"Interpreter version command exited with {completed.returncode}"]
    return output or None, []
