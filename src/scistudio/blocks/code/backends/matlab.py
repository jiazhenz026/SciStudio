"""MATLAB and Octave backend for CodeBlock v2."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from scistudio.blocks.code.code_block import (
    CodeBlockRuntimeContext,
    register_codeblock_backend,
    run_codeblock_process,
)
from scistudio.blocks.code.config import CodeBlockConfig
from scistudio.blocks.code.interpreters import InterpreterResolutionError, ResolvedInterpreter
from scistudio.stability import provisional

MatlabFamily = Literal["matlab", "octave"]


@provisional(since="0.3.1")
class MatlabRuntimeResolutionError(InterpreterResolutionError):
    """Raised when MATLAB-family interpreter selection fails."""


@provisional(since="0.3.1")
class MatlabCodeBlockBackend:
    """MATLAB `.m` and `.mlx` backend for the ADR-041 shared runtime."""

    name = "matlab"
    extensions = frozenset({".m", ".mlx"})

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        return script_path.suffix.lower() in self.extensions

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        suffix = context.script_path.suffix.lower()
        executable, family = resolve_matlab_executable(
            suffix=suffix,
            mode=context.config.interpreter_mode,
            interpreter_path=context.config.interpreter_path,
            environment_config=context.environment_config,
        )
        argv = build_matlab_command(executable=executable, family=family, script_path=context.script_path)
        version, warnings = probe_matlab_version(executable=executable, family=family)

        return ResolvedInterpreter(
            family=family,
            executable=executable,
            argv=argv,
            working_directory=context.exchange_dir.as_posix(),
            environment=environment_delta(context.environment_config),
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


def resolve_matlab_executable(
    *,
    suffix: str,
    mode: str,
    interpreter_path: str | Path | None,
    environment_config: Mapping[str, Any] | None = None,
) -> tuple[str, MatlabFamily]:
    """Resolve MATLAB or Octave for a MATLAB-family CodeBlock script."""

    suffix = suffix.lower()
    if suffix not in {".m", ".mlx"}:
        raise MatlabRuntimeResolutionError(f"MATLAB backend does not support {suffix or '<none>'} scripts.")

    environment_config = environment_config or {}
    configured = interpreter_path or environment_config.get("interpreter_path")
    if configured is None:
        configured = environment_config.get("matlab") or environment_config.get("octave")

    if mode == "existing":
        if configured is None:
            raise MatlabRuntimeResolutionError("interpreter_mode='existing' requires a MATLAB or Octave executable")
        executable = resolve_executable(str(configured))
        family = infer_matlab_family(executable, environment_config=environment_config)
        validate_matlab_family_for_suffix(family=family, suffix=suffix)
        return executable, family

    if mode != "auto":
        raise MatlabRuntimeResolutionError(f"Unsupported interpreter mode: {mode}")

    if configured is not None:
        executable = resolve_executable(str(configured))
        family = infer_matlab_family(executable, environment_config=environment_config)
        validate_matlab_family_for_suffix(family=family, suffix=suffix)
        return executable, family

    matlab = which_executable("matlab")
    if matlab is not None:
        return matlab, "matlab"

    if suffix == ".mlx":
        raise MatlabRuntimeResolutionError(
            ".mlx CodeBlock scripts require MATLAB; no MATLAB executable was found on PATH."
        )

    octave = which_executable("octave")
    if octave is not None:
        return octave, "octave"

    raise MatlabRuntimeResolutionError("No MATLAB or Octave executable was found on PATH for .m CodeBlock scripts.")


def build_matlab_command(*, executable: str, family: MatlabFamily, script_path: Path) -> list[str]:
    """Build the process command for MATLAB-family execution."""

    script = script_path.resolve().as_posix()
    if family == "matlab":
        return [executable, "-batch", f"run('{escape_matlab_string(script)}')"]
    return [executable, "--quiet", "--no-gui", script]


def validate_matlab_family_for_suffix(*, family: MatlabFamily, suffix: str) -> None:
    """Reject MATLAB live scripts when the selected executable is Octave."""

    if suffix == ".mlx" and family != "matlab":
        raise MatlabRuntimeResolutionError(".mlx CodeBlock scripts require MATLAB; Octave cannot execute live scripts.")


def infer_matlab_family(
    executable: str,
    *,
    environment_config: Mapping[str, Any] | None = None,
) -> MatlabFamily:
    """Infer MATLAB vs Octave from an explicit executable and optional hint."""

    environment_config = environment_config or {}
    raw_hint = environment_config.get("interpreter_family") or environment_config.get("runtime_family")
    if raw_hint is not None:
        hint = str(raw_hint).strip().lower()
        if hint in {"matlab", "octave"}:
            return hint  # type: ignore[return-value]
        raise MatlabRuntimeResolutionError("MATLAB backend interpreter_family must be 'matlab' or 'octave'")

    executable_name = Path(executable).name.lower()
    if "octave" in executable_name:
        return "octave"
    return "matlab"


def resolve_executable(raw_executable: str) -> str:
    """Resolve an executable name or path."""

    raw_executable = raw_executable.strip()
    if not raw_executable:
        raise MatlabRuntimeResolutionError("MATLAB-family executable must not be empty")

    candidate = Path(raw_executable)
    has_path_component = candidate.is_absolute() or any(part in raw_executable for part in ("/", "\\"))
    if has_path_component:
        resolved = candidate.expanduser().resolve()
        if not resolved.exists() or not resolved.is_file():
            raise MatlabRuntimeResolutionError(f"MATLAB-family executable not found: {raw_executable}")
        return str(resolved)

    discovered = which_executable(raw_executable)
    if discovered is None:
        raise MatlabRuntimeResolutionError(f"MATLAB-family executable not found on PATH: {raw_executable}")
    return discovered


def which_executable(name: str) -> str | None:
    """Return a normalized executable path from PATH lookup."""

    discovered = shutil.which(name)
    if discovered is None:
        return None
    return str(Path(discovered).resolve())


def environment_delta(environment_config: Mapping[str, Any]) -> dict[str, str]:
    """Return environment variables that differ from the current process."""

    raw_delta = (
        environment_config.get("environment_variables")
        or environment_config.get("env")
        or environment_config.get("environment")
        or {}
    )
    if not isinstance(raw_delta, Mapping):
        raise MatlabRuntimeResolutionError("environment variables must be a mapping")
    return {str(key): str(value) for key, value in raw_delta.items() if os.environ.get(str(key)) != str(value)}


def probe_matlab_version(*, executable: str, family: MatlabFamily) -> tuple[str | None, list[str]]:
    """Capture best-effort interpreter version metadata."""

    command = [executable, "--version"] if family == "octave" else [executable, "-batch", "disp(version)"]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, [f"Could not capture MATLAB-family interpreter version: {exc}"]

    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        return None, [f"MATLAB-family version command exited with {completed.returncode}"]
    return output or None, []


def escape_matlab_string(value: str) -> str:
    """Escape a value for a single-quoted MATLAB string literal."""

    return value.replace("'", "''")


def register() -> None:
    """Register the MATLAB-family backend with the shared CodeBlock runtime."""

    register_codeblock_backend(MatlabCodeBlockBackend(), replace=True)
