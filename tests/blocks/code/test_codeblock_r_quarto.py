from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scistudio.blocks.code.backends import r_quarto
from scistudio.blocks.code.code_block import CodeBlock, CodeBlockRuntimeContext, list_codeblock_backends
from scistudio.blocks.code.config import CodeBlockConfig
from scistudio.blocks.code.interpreters import InterpreterResolutionError
from scistudio.core.types.base import DataObject
from scistudio.core.types.text import Text


def _write_script(project_dir: Path, name: str, body: str = "# script\n") -> Path:
    scripts = project_dir / "scripts"
    scripts.mkdir(exist_ok=True)
    script = scripts / name
    script.write_text(body, encoding="utf-8")
    return script


def _context(
    tmp_path: Path,
    script_name: str,
    *,
    outputs: list[dict[str, object]] | None = None,
    environment: dict[str, object] | None = None,
    interpreter_path: str | None = None,
) -> CodeBlockRuntimeContext:
    script = _write_script(tmp_path, script_name)
    exchange_dir = tmp_path / "exchange" / "codeblock-block-1" / "run-1"
    exchange_dir.mkdir(parents=True)
    config = CodeBlockConfig(
        script_path=f"scripts/{script_name}",
        interpreter_path=interpreter_path,
        interpreter_mode="existing" if interpreter_path else "auto",
        environment=environment or {},
        outputs=outputs or [],
    )
    return CodeBlockRuntimeContext(
        config=config,
        script_path=script,
        project_dir=tmp_path,
        exchange_dir=exchange_dir,
        environment_config=dict(config.environment),
    )


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
        "exchange_root": "exchange",
        "block_id": "block-1",
        "run_id": "run-1",
        "reconstruct_adapter": _text_reconstruct,
    }
    base.update(params)
    return {"params": base}


def test_backend_loader_registers_r_quarto_backend() -> None:
    backends = list_codeblock_backends()

    backend = next(backend for backend in backends if backend.name == "r-quarto")
    assert backend.supports(Path("analysis.R"), CodeBlockConfig(script_path="analysis.R"))
    assert backend.supports(Path("report.Rmd"), CodeBlockConfig(script_path="report.Rmd"))
    assert backend.supports(Path("report.qmd"), CodeBlockConfig(script_path="report.qmd"))


def test_rscript_command_uses_exchange_directory_and_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(r_quarto, "_resolve_executable", lambda raw, *, label: f"/tools/{label}")
    monkeypatch.setattr(r_quarto, "_probe_version", lambda argv: ("Rscript 4.4.0", []))
    context = _context(tmp_path, "analysis.R", environment={"environment_variables": {"SCI": "easy"}})

    interpreter = r_quarto.RQuartoCodeBlockBackend().resolve(context)

    assert interpreter.family == "r"
    assert interpreter.argv == ["/tools/Rscript", str(context.script_path)]
    assert interpreter.working_directory == context.exchange_dir.as_posix()
    assert interpreter.environment["SCI"] == "easy"
    assert interpreter.environment["SCISTUDIO_EXCHANGE_DIR"] == str(context.exchange_dir)
    assert interpreter.environment["SCISTUDIO_INPUTS_DIR"] == str(context.exchange_dir / "inputs")
    assert interpreter.environment["SCISTUDIO_OUTPUTS_DIR"] == str(context.exchange_dir / "outputs")
    assert interpreter.environment["SCISTUDIO_SCRIPT_PATH"] == str(context.script_path)


def test_rmarkdown_command_targets_single_declared_output_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(r_quarto, "_resolve_executable", lambda raw, *, label: f"/tools/{label}")
    monkeypatch.setattr(r_quarto, "_probe_version", lambda argv: ("Rscript 4.4.0", []))
    monkeypatch.setattr(r_quarto, "_ensure_rmarkdown_available", lambda executable: None)
    context = _context(
        tmp_path,
        "report.Rmd",
        outputs=[{"name": "report", "direction": "output", "data_type": "Text", "extension": ".html"}],
    )

    interpreter = r_quarto.RQuartoCodeBlockBackend().resolve(context)

    assert interpreter.family == "r"
    assert interpreter.argv[:2] == ["/tools/Rscript", "-e"]
    expression = interpreter.argv[2]
    assert "rmarkdown::render" in expression
    assert context.script_path.as_posix() in expression
    assert (context.exchange_dir / "outputs" / "report").as_posix() in expression


def test_rmarkdown_missing_package_reports_clear_dependency_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(r_quarto, "_resolve_executable", lambda raw, *, label: f"/tools/{label}")

    def fail_rmarkdown(executable: str) -> None:
        raise InterpreterResolutionError("R Markdown support requires the R package 'rmarkdown'")

    monkeypatch.setattr(r_quarto, "_ensure_rmarkdown_available", fail_rmarkdown)
    context = _context(tmp_path, "report.Rmd")

    with pytest.raises(InterpreterResolutionError, match="rmarkdown"):
        r_quarto.RQuartoCodeBlockBackend().resolve(context)


def test_quarto_missing_executable_reports_clear_diagnostic(tmp_path: Path) -> None:
    missing = str(tmp_path / "missing-quarto")
    context = _context(tmp_path, "report.qmd", interpreter_path=missing)

    with pytest.raises(InterpreterResolutionError, match="quarto executable not found"):
        r_quarto.RQuartoCodeBlockBackend().resolve(context)


def test_quarto_backend_output_is_collected_from_declared_port_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_script(tmp_path, "report.qmd", "---\ntitle: report\n---\n")
    monkeypatch.setattr(r_quarto, "_resolve_executable", lambda raw, *, label: sys.executable)
    monkeypatch.setattr(r_quarto, "_probe_version", lambda argv: ("quarto 1.5.0", []))

    captured: dict[str, object] = {}

    def fake_process(
        *,
        argv: list[str],
        cwd: Path,
        env_delta: dict[str, str],
        timeout_seconds: float | None,
    ) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["cwd"] = cwd
        captured["env_delta"] = env_delta
        output_dir = Path(argv[argv.index("--output-dir") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "result.txt").write_text("rendered", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="rendered", stderr="")

    monkeypatch.setattr(r_quarto, "run_codeblock_process", fake_process)
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/report.qmd",
            outputs=[{"name": "report", "direction": "output", "data_type": "Text", "extension": ".txt"}],
        )
    )

    outputs = block.run({}, block.config)

    assert outputs["report"][0].content == "rendered"
    assert block.last_exchange_manifest is not None
    assert captured["cwd"] == block.last_exchange_manifest.layout.exchange_dir
    assert captured["env_delta"]["SCISTUDIO_OUTPUTS_DIR"] == str(block.last_exchange_manifest.layout.outputs_dir)
    assert captured["argv"][1:3] == ["render", str(tmp_path / "scripts" / "report.qmd")]
    assert Path(captured["argv"][4]) == block.last_exchange_manifest.output_folders["report"]


def test_optional_live_rscript_execution_skips_when_rscript_is_unavailable(tmp_path: Path) -> None:
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript is not available in this environment")
    _write_script(
        tmp_path,
        "live.R",
        """
dir.create("outputs/result", recursive = TRUE, showWarnings = FALSE)
writeLines("live-r", "outputs/result/result.txt")
""".strip()
        + "\n",
    )
    block = CodeBlock(
        config=_block_config(
            tmp_path,
            "scripts/live.R",
            outputs=[{"name": "result", "direction": "output", "data_type": "Text", "extension": ".txt"}],
        )
    )

    outputs = block.run({}, block.config)

    assert outputs["result"][0].content == "live-r\n"
