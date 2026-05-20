from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scieasy.blocks.code.backends.matlab import (
    MatlabCodeBlockBackend,
    MatlabRuntimeResolutionError,
    build_matlab_command,
    register,
    resolve_matlab_executable,
)
from scieasy.blocks.code.code_block import CodeBlockRuntimeContext, list_codeblock_backends
from scieasy.blocks.code.config import CodeBlockConfig
from scieasy.blocks.code.interpreters import ResolvedInterpreter


def _write_script(project_dir: Path, name: str = "scripts/run.m") -> Path:
    script = project_dir / name
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("disp('ok')\n", encoding="utf-8")
    return script


def _config(script_path: str, **kwargs: object) -> CodeBlockConfig:
    return CodeBlockConfig(script_path=script_path, **kwargs)


def _context(project_dir: Path, script_path: str, **kwargs: object) -> CodeBlockRuntimeContext:
    script = _write_script(project_dir, script_path)
    exchange_dir = project_dir / "exchange" / "block-run"
    exchange_dir.mkdir(parents=True)
    config = _config(script_path, **kwargs)
    return CodeBlockRuntimeContext(
        config=config,
        script_path=script,
        project_dir=project_dir,
        exchange_dir=exchange_dir,
        environment_config={"environment_variables": {"SCIEASY_CODEBLOCK_TEST": "1"}},
    )


def test_matlab_backend_supports_plain_and_live_scripts(tmp_path: Path) -> None:
    backend = MatlabCodeBlockBackend()
    config = _config("scripts/run.m")

    assert backend.supports(tmp_path / "scripts" / "run.m", config) is True
    assert backend.supports(tmp_path / "scripts" / "run.mlx", config) is True
    assert backend.supports(tmp_path / "scripts" / "run.py", config) is False


def test_register_adds_matlab_backend_extensions() -> None:
    register()

    backend = next(registered for registered in list_codeblock_backends() if registered.name == "matlab")
    assert backend.extensions == frozenset({".m", ".mlx"})


def test_auto_selection_prefers_matlab_for_plain_m(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(name: str) -> str | None:
        return f"/toolchain/{name}" if name in {"matlab", "octave"} else None

    monkeypatch.setattr("scieasy.blocks.code.backends.matlab.which_executable", fake_which)

    executable, family = resolve_matlab_executable(suffix=".m", mode="auto", interpreter_path=None)

    assert executable == "/toolchain/matlab"
    assert family == "matlab"


def test_auto_selection_uses_octave_for_plain_m_when_matlab_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(name: str) -> str | None:
        return "/toolchain/octave" if name == "octave" else None

    monkeypatch.setattr("scieasy.blocks.code.backends.matlab.which_executable", fake_which)

    executable, family = resolve_matlab_executable(suffix=".m", mode="auto", interpreter_path=None)

    assert executable == "/toolchain/octave"
    assert family == "octave"


def test_mlx_requires_matlab_in_auto_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_which(name: str) -> str | None:
        return "/toolchain/octave" if name == "octave" else None

    monkeypatch.setattr("scieasy.blocks.code.backends.matlab.which_executable", fake_which)

    with pytest.raises(MatlabRuntimeResolutionError, match=r"\.mlx CodeBlock scripts require MATLAB"):
        resolve_matlab_executable(suffix=".mlx", mode="auto", interpreter_path=None)


def test_existing_octave_rejected_for_mlx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scieasy.blocks.code.backends.matlab.which_executable", lambda name: f"/toolchain/{name}")

    with pytest.raises(MatlabRuntimeResolutionError, match="Octave cannot execute live scripts"):
        resolve_matlab_executable(suffix=".mlx", mode="existing", interpreter_path="octave")


def test_missing_executable_reports_matlab_family_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scieasy.blocks.code.backends.matlab.which_executable", lambda name: None)

    with pytest.raises(MatlabRuntimeResolutionError, match="No MATLAB or Octave executable"):
        resolve_matlab_executable(suffix=".m", mode="auto", interpreter_path=None)


def test_command_construction_is_deterministic_for_matlab_and_octave(tmp_path: Path) -> None:
    script = _write_script(tmp_path)

    matlab = build_matlab_command(executable="/bin/matlab", family="matlab", script_path=script)
    octave = build_matlab_command(executable="/bin/octave", family="octave", script_path=script)

    assert matlab == ["/bin/matlab", "-batch", f"run('{script.resolve().as_posix()}')"]
    assert octave == ["/bin/octave", "--quiet", "--no-gui", script.resolve().as_posix()]


def test_resolve_builds_runtime_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("scieasy.blocks.code.backends.matlab.which_executable", lambda name: f"/toolchain/{name}")
    monkeypatch.setattr(
        "scieasy.blocks.code.backends.matlab.probe_matlab_version",
        lambda *, executable, family: ("MATLAB test-version", []),
    )
    context = _context(tmp_path, "scripts/run.m")
    backend = MatlabCodeBlockBackend()

    resolved = backend.resolve(context)

    assert resolved.family == "matlab"
    assert resolved.executable == "/toolchain/matlab"
    assert resolved.argv[0] == "/toolchain/matlab"
    assert resolved.argv[1] == "-batch"
    assert resolved.working_directory == context.exchange_dir.as_posix()
    assert resolved.environment == {"SCIEASY_CODEBLOCK_TEST": "1"}
    assert resolved.version == "MATLAB test-version"


def test_run_reuses_shared_codeblock_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context = _context(tmp_path, "scripts/run.m", timeout_seconds=5)
    interpreter = ResolvedInterpreter(
        family="matlab",
        executable="/toolchain/matlab",
        argv=["/toolchain/matlab", "-batch", "run('script.m')"],
        working_directory=context.exchange_dir.as_posix(),
        environment={"SCIEASY_CODEBLOCK_TEST": "1"},
    )
    calls: dict[str, object] = {}

    def fake_run_codeblock_process(**kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.update(kwargs)
        return subprocess.CompletedProcess(interpreter.argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("scieasy.blocks.code.backends.matlab.run_codeblock_process", fake_run_codeblock_process)

    completed = MatlabCodeBlockBackend().run(context, interpreter)

    assert completed.returncode == 0
    assert calls == {
        "argv": interpreter.argv,
        "cwd": context.exchange_dir,
        "env_delta": interpreter.environment,
        "timeout_seconds": 5.0,
    }


@pytest.mark.skipif(shutil.which("octave") is None, reason="Octave is optional for base CodeBlock CI")
def test_optional_live_octave_execution(tmp_path: Path) -> None:
    script = _write_script(tmp_path)
    backend = MatlabCodeBlockBackend()
    exchange_dir = tmp_path / "exchange"
    exchange_dir.mkdir()
    context = CodeBlockRuntimeContext(
        config=_config("scripts/run.m", timeout_seconds=10),
        script_path=script,
        project_dir=tmp_path,
        exchange_dir=exchange_dir,
        environment_config={},
    )
    interpreter = ResolvedInterpreter(
        family="octave",
        executable=shutil.which("octave") or "octave",
        argv=build_matlab_command(executable=shutil.which("octave") or "octave", family="octave", script_path=script),
        working_directory=exchange_dir.as_posix(),
    )

    completed = backend.run(context, interpreter)

    assert completed.returncode == 0
