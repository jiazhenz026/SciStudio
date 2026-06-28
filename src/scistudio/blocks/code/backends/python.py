"""Backend that runs Python (``.py``) Code Block scripts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scistudio.blocks.code.code_block import (
    CodeBlockRuntimeContext,
    codeblock_exchange_env,
    register_codeblock_backend,
    run_codeblock_process,
)
from scistudio.blocks.code.config import CodeBlockConfig, CodeBlockConfigError
from scistudio.blocks.code.interpreters import ResolvedInterpreter, resolve_script_interpreter
from scistudio.stability import provisional


@provisional(since="0.3.1")
class PythonCodeBlockBackend:
    """Run a Code Block script written in Python (``.py``).

    This is the default Code Block backend. It picks a Python interpreter
    (either the one bundled with the app or an explicit path you configure via
    ``interpreter_mode`` / ``interpreter_path``), launches the script from the
    project root, and exposes the ``SCISTUDIO_*`` environment variables so the
    script can find its declared input and output folders. The script reads its
    inputs from files and writes its outputs to files; the Code Block converts
    those files back into typed data objects.

    Example:
        >>> backend = PythonCodeBlockBackend()
        >>> backend.name
        'python'
        >>> backend.supports(Path("analysis.py"), config)
        True
    """

    name = "python"
    """Backend identifier used in the registry and provenance records."""
    extensions = frozenset({".py"})
    """File extensions this backend handles."""

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        """Return whether *script_path* is a Python script this backend runs."""
        return script_path.suffix.lower() in self.extensions

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        """Resolve the Python interpreter and exchange environment for a run."""
        interpreter = resolve_script_interpreter(
            context.script_path,
            environment_config=context.environment_config,
            project_dir=context.project_dir,
            mode=context.config.interpreter_mode,
            interpreter_path=context.config.interpreter_path,
        )
        # FIND-F (#1740): inject the SCISTUDIO_*_DIR exchange env vars so a
        # Python script can locate its declared inputs/outputs, matching the
        # R/Quarto backends. resolve_script_interpreter has no access to the
        # exchange dir, so merge them here where the context is available.
        return interpreter.model_copy(
            update={"environment": {**interpreter.environment, **codeblock_exchange_env(context)}}
        )

    def run(
        self,
        context: CodeBlockRuntimeContext,
        interpreter: ResolvedInterpreter,
    ) -> subprocess.CompletedProcess[str]:
        """Launch the Python interpreter on the script and return the process."""
        # ADR-041 §4: launch the interpreter from the configured working
        # directory (default ``"."`` = project root). Previously the
        # subprocess inherited ``cwd=context.exchange_dir``, which broke
        # any script that read project-relative paths like ``Path("data/raw")``.
        # The exchange dir is still the materialisation target for declared
        # ports; only the *executing* process cwd changes here.
        script_cwd = _resolve_existing_working_directory(context)
        return run_codeblock_process(
            argv=[interpreter.executable, str(context.script_path)],
            cwd=script_cwd,
            env_delta=interpreter.environment,
            timeout_seconds=context.config.timeout_seconds,
        )


def _resolve_existing_working_directory(context: CodeBlockRuntimeContext) -> Path:
    """Resolve ``working_directory`` and require it to exist as a directory.

    :meth:`CodeBlockConfig.resolve_working_directory` intentionally allows
    paths that don't yet exist (e.g. a still-empty downstream cache dir),
    but :func:`subprocess.run` raises a low-level ``FileNotFoundError``
    when ``cwd`` doesn't exist. Surface a clear :class:`CodeBlockConfigError`
    instead so the failure points at the misconfigured field, not at a
    Python subprocess internal. Codex P2 review of PR #1392.
    """
    script_cwd = context.config.resolve_working_directory(context.project_dir)
    if not script_cwd.exists():
        raise CodeBlockConfigError(
            f"working_directory does not exist: {script_cwd} "
            f"(resolved from {context.config.working_directory!r} under project root "
            f"{context.project_dir!r})"
        )
    if not script_cwd.is_dir():
        raise CodeBlockConfigError(f"working_directory must be a directory, not a file: {script_cwd}")
    return script_cwd


def register() -> None:
    """Register the Python backend with the shared CodeBlock runtime."""

    register_codeblock_backend(PythonCodeBlockBackend(), replace=True)
