"""Python backend for CodeBlock v2."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scistudio.blocks.code.code_block import (
    CodeBlockRuntimeContext,
    register_codeblock_backend,
    run_codeblock_process,
)
from scistudio.blocks.code.config import CodeBlockConfig
from scistudio.blocks.code.interpreters import ResolvedInterpreter, resolve_script_interpreter


class PythonCodeBlockBackend:
    """Python `.py` backend for the ADR-041 shared runtime."""

    name = "python"
    extensions = frozenset({".py"})

    def supports(self, script_path: Path, config: CodeBlockConfig) -> bool:
        return script_path.suffix.lower() in self.extensions

    def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
        return resolve_script_interpreter(
            context.script_path,
            environment_config=context.environment_config,
            project_dir=context.project_dir,
            mode=context.config.interpreter_mode,
            interpreter_path=context.config.interpreter_path,
        )

    def run(
        self,
        context: CodeBlockRuntimeContext,
        interpreter: ResolvedInterpreter,
    ) -> subprocess.CompletedProcess[str]:
        # ADR-041 §4: launch the interpreter from the configured working
        # directory (default ``"."`` = project root). Previously the
        # subprocess inherited ``cwd=context.exchange_dir``, which broke
        # any script that read project-relative paths like ``Path("data/raw")``.
        # The exchange dir is still the materialisation target for declared
        # ports; only the *executing* process cwd changes here.
        script_cwd = context.config.resolve_working_directory(context.project_dir)
        return run_codeblock_process(
            argv=[interpreter.executable, str(context.script_path)],
            cwd=script_cwd,
            env_delta=interpreter.environment,
            timeout_seconds=context.config.timeout_seconds,
        )


def register() -> None:
    """Register the Python backend with the shared CodeBlock runtime."""

    register_codeblock_backend(PythonCodeBlockBackend(), replace=True)
