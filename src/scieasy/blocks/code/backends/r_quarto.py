"""R and Quarto backends for CodeBlock v2."""

from __future__ import annotations

import json
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
from scieasy.blocks.code.config import CodeBlockConfig
from scieasy.blocks.code.interpreters import InterpreterResolutionError, ResolvedInterpreter

_R_EXTENSIONS = frozenset({".r", ".rmd"})
_QUARTO_EXTENSIONS = frozenset({".qmd"})
_ALL_EXTENSIONS = _R_EXTENSIONS | _QUARTO_EXTENSIONS
_VERSION_TIMEOUT_SECONDS = 5
_R_PACKAGE_TIMEOUT_SECONDS = 10


class RQuartoCodeBlockBackend:
    """Rscript, R Markdown, and Quarto backend for ADR-041 CodeBlock runs."""

    name = "r-quarto"
    extensions = frozenset({".R", ".Rmd", ".qmd"})

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        return script_path.suffix.lower() in _ALL_EXTENSIONS

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        extension = context.script_path.suffix.lower()
        if extension == ".qmd":
            return _resolve_quarto(context)
        if extension in _R_EXTENSIONS:
            return _resolve_r(context, render_rmarkdown=extension == ".rmd")
        raise InterpreterResolutionError(
            f"R/Quarto backend supports .R, .Rmd, and .qmd scripts; got {context.script_path.suffix or '<none>'}."
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


def _resolve_r(context: CodeBlockRuntimeContext, *, render_rmarkdown: bool) -> ResolvedInterpreter:
    executable = _resolve_configured_executable(
        context,
        default_name="Rscript",
        environment_keys=("rscript", "Rscript"),
    )
    if render_rmarkdown:
        _ensure_rmarkdown_available(executable)
        argv = [executable, "-e", _rmarkdown_render_expression(context)]
    else:
        argv = [executable, str(context.script_path)]
    version, warnings = _probe_version([executable, "--version"])
    return ResolvedInterpreter(
        family="r",
        executable=executable,
        argv=argv,
        working_directory=context.exchange_dir.as_posix(),
        environment=_exchange_environment(context),
        version=version,
        warnings=warnings,
    )


def _resolve_quarto(context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
    executable = _resolve_configured_executable(
        context,
        default_name="quarto",
        environment_keys=("quarto", "quarto_path"),
    )
    version, warnings = _probe_version([executable, "--version"])
    return ResolvedInterpreter(
        family="quarto",
        executable=executable,
        argv=[executable, "render", str(context.script_path), "--output-dir", str(_render_output_dir(context))],
        working_directory=context.exchange_dir.as_posix(),
        environment=_exchange_environment(context),
        version=version,
        warnings=warnings,
    )


def _resolve_configured_executable(
    context: CodeBlockRuntimeContext,
    *,
    default_name: str,
    environment_keys: tuple[str, ...],
) -> str:
    configured = context.config.interpreter_path
    for key in environment_keys:
        configured = configured or context.environment_config.get(key)
    if context.config.interpreter_mode == "existing" and not configured:
        raise InterpreterResolutionError(
            f"interpreter_mode='existing' requires an interpreter_path for {default_name}."
        )
    if context.config.interpreter_mode not in {"auto", "existing"}:
        raise InterpreterResolutionError(f"Unsupported interpreter mode: {context.config.interpreter_mode}")
    return _resolve_executable(str(configured or default_name), label=default_name)


def _resolve_executable(raw_executable: str, *, label: str) -> str:
    raw_executable = raw_executable.strip()
    if not raw_executable:
        raise InterpreterResolutionError(f"{label} executable must not be empty.")

    candidate = Path(raw_executable)
    has_path_component = candidate.is_absolute() or any(part in raw_executable for part in ("/", "\\"))
    if has_path_component:
        resolved = candidate.expanduser().resolve()
        if not resolved.exists() or not resolved.is_file():
            raise InterpreterResolutionError(f"{label} executable not found: {raw_executable}")
        return str(resolved)

    discovered = shutil.which(raw_executable)
    if discovered is None:
        raise InterpreterResolutionError(f"{label} executable not found on PATH: {raw_executable}")
    return str(Path(discovered).resolve())


def _ensure_rmarkdown_available(rscript_executable: str) -> None:
    completed = subprocess.run(
        [
            rscript_executable,
            "-e",
            "if (!requireNamespace('rmarkdown', quietly = TRUE)) quit(status = 42)",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=_R_PACKAGE_TIMEOUT_SECONDS,
    )
    if completed.returncode == 0:
        return
    detail = (completed.stderr or completed.stdout or "").strip()
    suffix = f" Details: {detail}" if detail else ""
    raise InterpreterResolutionError(
        "R Markdown support requires the R package 'rmarkdown' to be installed and loadable."
        f"{suffix}"
    )


def _rmarkdown_render_expression(context: CodeBlockRuntimeContext) -> str:
    script = _r_string(context.script_path)
    output_dir = _r_string(_render_output_dir(context))
    return (
        "rmarkdown::render("
        f"input = {script}, "
        f"output_dir = {output_dir}, "
        "envir = new.env(parent = globalenv()), "
        "quiet = FALSE"
        ")"
    )


def _render_output_dir(context: CodeBlockRuntimeContext) -> Path:
    outputs = list(context.config.outputs)
    if len(outputs) == 1:
        folder = (outputs[0].exchange_folder or f"outputs/{outputs[0].name}/").replace("\\", "/").strip("/")
        return context.exchange_dir / folder
    return context.exchange_dir / "outputs"


def _exchange_environment(context: CodeBlockRuntimeContext) -> dict[str, str]:
    env_delta = _environment_delta(context.environment_config)
    env_delta.update(
        {
            "SCIEASY_EXCHANGE_DIR": str(context.exchange_dir),
            "SCIEASY_INPUTS_DIR": str(context.exchange_dir / "inputs"),
            "SCIEASY_OUTPUTS_DIR": str(context.exchange_dir / "outputs"),
            "SCIEASY_SCRIPT_PATH": str(context.script_path),
        }
    )
    return env_delta


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


def _probe_version(argv: list[str]) -> tuple[str | None, list[str]]:
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, [f"Could not capture interpreter version: {exc}"]

    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        return None, [f"Interpreter version command exited with {completed.returncode}"]
    return output or None, []


def _r_string(value: Path) -> str:
    return json.dumps(value.as_posix())


def register() -> None:
    """Register the R/Quarto backend with the shared CodeBlock runtime."""

    register_codeblock_backend(RQuartoCodeBlockBackend(), replace=True)
