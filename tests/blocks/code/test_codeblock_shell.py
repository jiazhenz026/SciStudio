from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from scistudio.blocks.code.backends import shell
from scistudio.blocks.code.backends.shell import ShellCodeBlockBackend
from scistudio.blocks.code.code_block import CodeBlock, CodeBlockExecutionError, CodeBlockRuntimeContext
from scistudio.blocks.code.config import CodeBlockConfig
from scistudio.blocks.code.interpreters import InterpreterResolutionError
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.text import Text


def _live_shell() -> str | None:
    for candidate in ("sh", "bash", "dash", "zsh"):
        discovered = shutil.which(candidate)
        if discovered is not None and shell._is_compatible_shell(discovered):
            return discovered
    return None


def _write_script(project_dir: Path, body: str, *, name: str = "script.sh") -> Path:
    scripts = project_dir / "scripts"
    scripts.mkdir()
    script = scripts / name
    script.write_text(body, encoding="utf-8", newline="\n")
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
        "interpreter_path": _live_shell(),
        "interpreter_mode": "existing",
        "exchange_root": "exchange",
        "block_id": "shell-block",
        "run_id": "run-1",
        "materialise_adapter": _text_materialise,
        "reconstruct_adapter": _text_reconstruct,
    }
    base.update(params)
    return {"params": base}


def _runtime_context(tmp_path: Path, config: CodeBlockConfig | None = None) -> CodeBlockRuntimeContext:
    script = tmp_path / "scripts" / "script.sh"
    script.parent.mkdir()
    script.write_text("echo ok\n", encoding="utf-8")
    exchange_dir = tmp_path / "exchange" / "codeblock-shell" / "run-1"
    (exchange_dir / "inputs").mkdir(parents=True)
    (exchange_dir / "outputs").mkdir()
    return CodeBlockRuntimeContext(
        config=config or CodeBlockConfig(script_path="scripts/script.sh"),
        script_path=script,
        project_dir=tmp_path,
        exchange_dir=exchange_dir,
        environment_config={"environment_variables": {"SHELL_BACKEND_TEST": "1"}},
    )


def test_shell_backend_supports_sh_scripts_only(tmp_path: Path) -> None:
    backend = ShellCodeBlockBackend()
    config = CodeBlockConfig(script_path="scripts/script.sh")

    assert backend.supports(tmp_path / "script.sh", config) is True
    assert backend.supports(tmp_path / "script.py", config) is False


def test_shell_backend_constructs_deterministic_command_and_exchange_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shell.shutil, "which", lambda name: f"/toolchain/{name}" if name == "sh" else None)
    monkeypatch.setattr(shell, "_is_compatible_shell", lambda executable: True)
    backend = ShellCodeBlockBackend()
    context = _runtime_context(tmp_path)

    resolved = backend.resolve(context)

    assert resolved.family == "shell"
    assert resolved.executable == str(Path("/toolchain/sh").resolve())
    assert resolved.argv == [resolved.executable, str(context.script_path)]
    assert resolved.working_directory == context.exchange_dir.as_posix()
    assert list(resolved.environment) == sorted(resolved.environment)
    assert resolved.environment["SHELL_BACKEND_TEST"] == "1"
    assert resolved.environment["SCISTUDIO_CODEBLOCK_EXCHANGE_DIR"] == str(context.exchange_dir.resolve())
    assert resolved.environment["SCISTUDIO_CODEBLOCK_INPUTS_DIR"] == str((context.exchange_dir / "inputs").resolve())
    assert resolved.environment["SCISTUDIO_CODEBLOCK_OUTPUTS_DIR"] == str((context.exchange_dir / "outputs").resolve())
    assert resolved.environment["SCISTUDIO_CODEBLOCK_PROJECT_DIR"] == str(tmp_path.resolve())
    assert resolved.environment["SCISTUDIO_CODEBLOCK_SCRIPT_PATH"] == str(context.script_path.resolve())


def test_missing_shell_diagnostic_is_clear(tmp_path: Path) -> None:
    missing_shell = tmp_path / "missing-sh"
    config = CodeBlockConfig(
        script_path="scripts/script.sh",
        interpreter_mode="existing",
        interpreter_path=str(missing_shell),
    )
    backend = ShellCodeBlockBackend()

    with pytest.raises(InterpreterResolutionError, match="POSIX shell executable not found"):
        backend.resolve(_runtime_context(tmp_path, config))


@pytest.mark.skipif(_live_shell() is None, reason="POSIX shell is not available for live shell execution")
def test_codeblock_runs_shell_script_through_exchange(tmp_path: Path) -> None:
    _write_script(
        tmp_path,
        """
set -eu
mkdir -p outputs/summary
input_file=$(ls inputs/prompt/*.txt | sort | sed -n '1p')
cat "$input_file" > outputs/summary/result.txt
""".strip()
        + "\n",
    )
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/script.sh",
            inputs=[{"name": "prompt", "direction": "input", "data_type": "Text", "extension": ".txt"}],
            outputs=[{"name": "summary", "direction": "output", "data_type": "Text", "extension": ".txt"}],
        )
    )

    outputs = block.run({"prompt": Collection([Text(content="hello from shell")])}, block.config)

    assert outputs["summary"][0].content == "hello from shell"
    assert block.last_process is not None
    assert block.last_process.returncode == 0
    assert block.last_provenance_payload is not None
    assert block.last_provenance_payload["interpreter"]["family"] == "shell"
    assert "SCISTUDIO_CODEBLOCK_EXCHANGE_DIR" in block.last_provenance_payload["environment"]["environment_delta"]


@pytest.mark.skipif(_live_shell() is None, reason="POSIX shell is not available for live shell execution")
def test_codeblock_shell_nonzero_exit_preserves_diagnostics(tmp_path: Path) -> None:
    _write_script(
        tmp_path,
        """
echo "before shell failure"
echo "shell boom" >&2
exit 7
""".strip()
        + "\n",
    )
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/script.sh",
            outputs=[{"name": "summary", "direction": "output", "data_type": "Text", "extension": ".txt"}],
        )
    )

    with pytest.raises(CodeBlockExecutionError) as exc_info:
        block.run({}, block.config)

    assert exc_info.value.returncode == 7
    assert "before shell failure" in exc_info.value.stdout
    assert "shell boom" in exc_info.value.stderr


@pytest.mark.skipif(
    os.name != "nt" or _live_shell() is not None,
    reason="Documents the Windows path where no POSIX shell is installed.",
)
def test_windows_without_posix_shell_uses_missing_shell_diagnostic(tmp_path: Path) -> None:
    config = CodeBlockConfig(script_path="scripts/script.sh")
    backend = ShellCodeBlockBackend()

    with pytest.raises(InterpreterResolutionError, match="POSIX shell executable not found on PATH"):
        backend.resolve(_runtime_context(tmp_path, config))
