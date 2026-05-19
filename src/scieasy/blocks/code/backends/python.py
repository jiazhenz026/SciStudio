"""Python backend for CodeBlock v2."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scieasy.blocks.code.code_block import (
    CodeBlockRuntimeContext,
    register_codeblock_backend,
    run_codeblock_process,
)
from scieasy.blocks.code.config import CodeBlockConfig
from scieasy.blocks.code.interpreters import ResolvedInterpreter, resolve_script_interpreter


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
        return run_codeblock_process(
            argv=[interpreter.executable, str(context.script_path)],
            cwd=context.exchange_dir,
            env_delta=interpreter.environment,
            timeout_seconds=context.config.timeout_seconds,
        )


def register() -> None:
    """Register the Python backend with the shared CodeBlock runtime."""

    register_codeblock_backend(PythonCodeBlockBackend(), replace=True)
