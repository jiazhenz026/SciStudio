from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from scistudio.ai.agent import terminal
from scistudio.api.routes import ai as ai_route


def _npm_shim_which(name: str) -> str | None:
    shims = {
        "codex": "C:/Users/dev/AppData/Roaming/npm/codex",
        "codex.cmd": "C:/Users/dev/AppData/Roaming/npm/codex.cmd",
        "claude": "C:/Users/dev/AppData/Roaming/npm/claude",
        "claude.cmd": "C:/Users/dev/AppData/Roaming/npm/claude.cmd",
    }
    return shims.get(name.lower())


def test_resolve_windows_executable_prefers_cmd_over_bare_npm_wrapper(monkeypatch: Any) -> None:
    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", _npm_shim_which)

    assert terminal.resolve_windows_executable("codex") == "C:/Users/dev/AppData/Roaming/npm/codex.cmd"


def test_resolve_windows_executable_preserves_non_windows_which(monkeypatch: Any) -> None:
    monkeypatch.setattr(terminal.sys, "platform", "linux")
    monkeypatch.setattr(terminal.shutil, "which", lambda name: f"/usr/bin/{name}")

    assert terminal.resolve_windows_executable("codex") == "/usr/bin/codex"


def test_binary_status_uses_cmd_when_windows_which_finds_bare_wrapper(monkeypatch: Any) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="codex 0.1.0\n", stderr="")

    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", _npm_shim_which)
    monkeypatch.setattr(ai_route.subprocess, "run", fake_run)

    assert ai_route._binary_status("codex") == (True, "codex 0.1.0")
    assert calls == [["C:/Users/dev/AppData/Roaming/npm/codex.cmd", "--version"]]


def test_spawn_codex_uses_cmd_when_windows_which_finds_bare_wrapper(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    spawned: dict[str, Any] = {}

    class FakePtyProcess:
        def __init__(self, argv: list[str], *args: Any, **kwargs: Any) -> None:
            spawned["argv"] = argv
            spawned["args"] = args
            spawned["kwargs"] = kwargs

    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", _npm_shim_which)
    monkeypatch.setattr(terminal, "PtyProcess", FakePtyProcess)

    terminal.spawn_codex(project_dir=tmp_path, dangerous=True)

    assert spawned["argv"] == [
        "C:/Users/dev/AppData/Roaming/npm/codex.cmd",
        "--dangerously-bypass-approvals-and-sandbox",
    ]


def test_spawn_claude_uses_cmd_when_windows_which_finds_bare_wrapper(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    spawned: dict[str, Any] = {}
    prompt_path = tmp_path / "prompt.md"
    mcp_config = tmp_path / ".scistudio" / "mcp.json"

    class FakePtyProcess:
        def __init__(self, argv: list[str], *args: Any, **kwargs: Any) -> None:
            spawned["argv"] = argv
            spawned["args"] = args
            spawned["kwargs"] = kwargs

    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", _npm_shim_which)
    monkeypatch.setattr(terminal, "PtyProcess", FakePtyProcess)
    monkeypatch.setattr(terminal, "_write_system_prompt_tempfile", lambda project_dir: prompt_path)
    monkeypatch.setattr(terminal, "_ensure_mcp_config", lambda project_dir: mcp_config)

    terminal.spawn_claude(project_dir=tmp_path, dangerous=False)

    assert spawned["argv"] == [
        "C:/Users/dev/AppData/Roaming/npm/claude.cmd",
        "--append-system-prompt",
        f"@{prompt_path}",
        "--mcp-config",
        str(mcp_config),
    ]


def test_spawn_argv_seam_bypasses_windows_resolution(monkeypatch: Any, tmp_path: Path) -> None:
    spawned: dict[str, Any] = {}

    class FakePtyProcess:
        def __init__(self, argv: list[str], *args: Any, **kwargs: Any) -> None:
            spawned["argv"] = argv
            spawned["args"] = args
            spawned["kwargs"] = kwargs

    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", _npm_shim_which)
    monkeypatch.setattr(terminal, "PtyProcess", FakePtyProcess)

    terminal.spawn_codex(project_dir=tmp_path, dangerous=True, _spawn_argv=[sys.executable, "-c", "pass"])

    assert spawned["argv"] == [sys.executable, "-c", "pass"]
