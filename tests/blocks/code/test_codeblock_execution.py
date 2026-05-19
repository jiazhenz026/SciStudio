from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scieasy.blocks.code.code_block import (
    CodeBlock,
    CodeBlockExecutionError,
    CodeBlockMigrationError,
    CodeBlockRuntimeContext,
    CodeBlockTimeoutError,
    list_codeblock_backends,
    register_codeblock_backend,
    unregister_codeblock_backend,
)
from scieasy.blocks.code.exchange import CodeBlockExchangeError
from scieasy.blocks.code.interpreters import ResolvedInterpreter
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.core.types.text import Text


def _write_script(project_dir: Path, body: str, *, name: str = "script.py") -> Path:
    scripts = project_dir / "scripts"
    scripts.mkdir()
    script = scripts / name
    script.write_text(body, encoding="utf-8")
    return script


def _text_materialise(
    obj: DataObject,
    dest_dir: Path,
    extension: str,
    *,
    filename_stem: str,
    capability_id: str | None = None,
) -> Path:
    assert isinstance(obj, Text)
    path = dest_dir / f"{filename_stem}{extension}"
    path.write_text(obj.content or "", encoding=obj.encoding)
    return path


def _text_reconstruct(
    path: Path,
    target_type: type[DataObject],
    extension: str,
    *,
    capability_id: str | None = None,
) -> DataObject:
    assert target_type is Text
    assert extension == ".txt"
    return Text(content=path.read_text(encoding="utf-8"))


def _block_config(project_dir: Path, script_path: str, **params: object) -> dict[str, object]:
    base: dict[str, object] = {
        "project_dir": str(project_dir),
        "script_path": script_path,
        "interpreter_path": sys.executable,
        "interpreter_mode": "existing",
        "exchange_root": "exchange",
        "block_id": "block-1",
        "run_id": "run-1",
        "materialise_adapter": _text_materialise,
        "reconstruct_adapter": _text_reconstruct,
    }
    base.update(params)
    return {"params": base}


def test_codeblock_runs_python_script_through_exchange(tmp_path: Path) -> None:
    _write_script(
        tmp_path,
        """
from pathlib import Path

source = sorted(Path("inputs/prompt").glob("*.txt"))[0]
target = Path("outputs/summary/result.txt")
target.write_text(source.read_text(encoding="utf-8").upper(), encoding="utf-8")
""".strip()
        + "\n",
    )
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/script.py",
            inputs=[{"name": "prompt", "direction": "input", "data_type": "Text", "extension": ".txt"}],
            outputs=[{"name": "summary", "direction": "output", "data_type": "Text", "extension": ".txt"}],
        )
    )

    outputs = block.run({"prompt": Collection([Text(content="hello")])}, block.config)

    assert outputs["summary"][0].content == "HELLO"
    assert block.last_process is not None
    assert block.last_process.returncode == 0
    assert block.last_exchange_manifest is not None
    assert (block.last_exchange_manifest.layout.manifest_path).is_file()
    assert block.last_provenance_payload is not None
    assert block.last_provenance_payload["script"]["relative_path"] == "scripts/script.py"
    assert block.last_provenance_payload["exchange_manifest"]["ports"]["summary"]["status"] == "collected"


def test_codeblock_missing_required_output_fails_after_successful_process(tmp_path: Path) -> None:
    _write_script(tmp_path, "print('no declared output')\n")
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/script.py",
            outputs=[{"name": "summary", "direction": "output", "data_type": "Text", "extension": ".txt"}],
        )
    )

    with pytest.raises(CodeBlockExchangeError) as exc_info:
        block.run({}, block.config)

    assert [diagnostic.code for diagnostic in exc_info.value.diagnostics] == ["missing_required_output"]
    assert block.last_process is not None
    assert block.last_process.returncode == 0


def test_codeblock_nonzero_exit_preserves_process_diagnostics(tmp_path: Path) -> None:
    _write_script(
        tmp_path,
        """
import sys

print("before failure")
print("boom", file=sys.stderr)
raise SystemExit(3)
""".strip()
        + "\n",
    )
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/script.py",
            outputs=[{"name": "summary", "direction": "output", "data_type": "Text", "extension": ".txt"}],
        )
    )

    with pytest.raises(CodeBlockExecutionError) as exc_info:
        block.run({}, block.config)

    assert exc_info.value.returncode == 3
    assert "before failure" in exc_info.value.stdout
    assert "boom" in exc_info.value.stderr


def test_codeblock_timeout_raises_structured_error(tmp_path: Path) -> None:
    _write_script(tmp_path, "import time\ntime.sleep(5)\n")
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/script.py",
            timeout_seconds=0.1,
            outputs=[{"name": "summary", "direction": "output", "data_type": "Text", "extension": ".txt"}],
        )
    )

    with pytest.raises(CodeBlockTimeoutError, match="timed out"):
        block.run({}, block.config)


def test_legacy_inline_config_reports_migration_error() -> None:
    block = CodeBlock(config={"params": {"script": "result = 42"}})

    with pytest.raises(CodeBlockMigrationError) as exc_info:
        block.run({}, block.config)

    assert "Inline CodeBlock configs are not valid" in str(exc_info.value)


def test_legacy_entry_function_script_reports_migration_error(tmp_path: Path) -> None:
    _write_script(tmp_path, "def run(inputs, config):\n    return {'result': 42}\n")
    block = CodeBlock(config=_block_config(tmp_path, "scripts/script.py"))

    with pytest.raises(CodeBlockMigrationError) as exc_info:
        block.run({}, block.config)

    assert "does not call entry functions" in str(exc_info.value)


def test_codeblock_dispatches_through_registered_backend(tmp_path: Path) -> None:
    script = _write_script(tmp_path, "backend-owned script\n", name="script.dummy")

    class DummyBackend:
        name = "dummy"
        extensions = frozenset({".dummy"})

        def __init__(self) -> None:
            self.context: CodeBlockRuntimeContext | None = None
            self.ran = False

        def supports(self, script_path: Path, config: object) -> bool:
            return script_path.suffix == ".dummy"

        def resolve(self, context: CodeBlockRuntimeContext) -> ResolvedInterpreter:
            self.context = context
            return ResolvedInterpreter(
                family="python",
                executable=sys.executable,
                argv=[sys.executable, str(script)],
                working_directory=context.exchange_dir.as_posix(),
            )

        def run(
            self,
            context: CodeBlockRuntimeContext,
            interpreter: ResolvedInterpreter,
        ) -> subprocess.CompletedProcess[str]:
            self.ran = True
            return subprocess.CompletedProcess(interpreter.argv, 0, stdout="ok", stderr="")

    backend = DummyBackend()
    register_codeblock_backend(backend)
    try:
        assert any(registered.name == "dummy" for registered in list_codeblock_backends())
        block = CodeBlock(config=_block_config(tmp_path, "scripts/script.dummy"))

        assert block.run({}, block.config) == {}
        assert backend.ran is True
        assert backend.context is not None
        assert backend.context.exchange_dir.is_dir()
    finally:
        unregister_codeblock_backend("dummy")


def test_codeblock_backend_loader_registers_python_backend() -> None:
    backends = list_codeblock_backends()

    python_backend = next(backend for backend in backends if backend.name == "python")
    assert ".py" in python_backend.extensions
