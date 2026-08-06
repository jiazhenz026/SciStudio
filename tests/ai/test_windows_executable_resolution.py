"""ADR-034 provider binary discovery tests (issue #1994, spec T-002).

Two families:

* **PATH resolution** — the original ``.cmd``-over-bare-npm-wrapper behaviour
  that pywinpty's CreateProcess spawn path depends on.
* **Off-PATH discovery** — Kimi Code and both Qoder channels are absent from
  PATH on every platform, so they are found only in registry-declared
  well-known directories (FR-004, FR-005). Every one of those tests drives a
  **fake home**, so results never depend on which CLIs happen to be installed
  on the machine running the suite.

The off-PATH tests run under both simulated platforms. The well-known-directory
scan is deliberately not Windows-only: Kimi and Qoder are off PATH everywhere,
and FR-005 requires the chat path and the AI Block path to agree on every OS.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

from scistudio.ai.agent import providers_registry as registry
from scistudio.ai.agent import terminal
from scistudio.ai.agent.providers_registry import resolve_binary
from scistudio.api.routes import ai as ai_route
from scistudio.desktop import paths as desktop_paths


def _npm_shim_which(name: str) -> str | None:
    shims = {
        "codex": "C:/Users/dev/AppData/Roaming/npm/codex",
        "codex.cmd": "C:/Users/dev/AppData/Roaming/npm/codex.cmd",
        "claude": "C:/Users/dev/AppData/Roaming/npm/claude",
        "claude.cmd": "C:/Users/dev/AppData/Roaming/npm/claude.cmd",
    }
    return shims.get(name.lower())


def _nothing_on_path(_name: str) -> str | None:
    """``which`` stub for a machine where the CLI is not on PATH at all."""
    return None


@pytest.fixture(params=["win32", "linux"])
def platform(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test body once per simulated platform."""
    monkeypatch.setattr(sys, "platform", request.param)
    return str(request.param)


def _install_binary(directory: Path, name: str, platform: str) -> Path:
    """Create a fake installed CLI at ``directory/<name>[.exe]``."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (f"{name}.exe" if platform == "win32" else name)
    path.write_text("", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# PATH resolution
# ---------------------------------------------------------------------------


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

    assert ai_route._binary_status("codex") == (
        "C:/Users/dev/AppData/Roaming/npm/codex.cmd",
        True,
        "codex 0.1.0",
    )
    assert calls == [["C:/Users/dev/AppData/Roaming/npm/codex.cmd", "--version"]]


def test_path_hit_wins_over_a_well_known_directory_copy(tmp_path: Path, platform: str) -> None:
    """A CLI genuinely on PATH is what the user's shell would run."""
    fake_home = tmp_path / "home"
    _install_binary(fake_home / ".local" / "bin", "claude", platform)
    on_path = "C:/tools/claude.cmd" if platform == "win32" else "/usr/bin/claude"

    resolved = resolve_binary(
        registry.get("claude-code"),
        which=lambda name: on_path if name in {"claude", "claude.cmd"} else None,
        home=fake_home,
        env={},
    )
    assert resolved == Path(on_path)


# ---------------------------------------------------------------------------
# FR-004 / FR-005: off-PATH discovery in a fake home
# ---------------------------------------------------------------------------


def test_off_path_discovery_finds_kimi_and_both_qoder_channels(tmp_path: Path, platform: str) -> None:
    """None of the three new CLIs is on PATH; all must still be discovered."""
    fake_home = tmp_path / "home"
    kimi = _install_binary(fake_home / ".kimi-code" / "bin", "kimi", platform)
    qoder = _install_binary(fake_home / ".qoder" / "bin" / "qodercli", "qodercli", platform)
    qoder_cn = _install_binary(fake_home / ".qoder-cn" / "bin" / "qoderclicn", "qoderclicn", platform)

    def resolve(key: str) -> Path | None:
        return resolve_binary(registry.get(key), which=_nothing_on_path, home=fake_home, env={})

    assert resolve("kimi-code") == kimi
    assert resolve("qoder") == qoder
    assert resolve("qoder-cn") == qoder_cn


def test_absent_provider_resolves_to_none(tmp_path: Path, platform: str) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    for key in registry.agent_keys():
        assert resolve_binary(registry.get(key), which=_nothing_on_path, home=fake_home, env={}) is None


def test_kimi_discovery_honours_kimi_code_home(tmp_path: Path, platform: str) -> None:
    """Kimi's own docs instruct callers never to assume ``~/.kimi-code``."""
    fake_home = tmp_path / "home"
    override_root = tmp_path / "opt" / "kimi-code"
    installed = _install_binary(override_root / "bin", "kimi", platform)
    # A decoy at the default location proves the override is actually read.
    decoy = _install_binary(fake_home / ".kimi-code" / "bin", "kimi", platform)

    resolved = resolve_binary(
        registry.get("kimi-code"),
        which=_nothing_on_path,
        home=fake_home,
        env={"KIMI_CODE_HOME": str(override_root)},
    )
    assert resolved == installed
    assert resolved != decoy


# ---------------------------------------------------------------------------
# FR-027: sidecar rejection
# ---------------------------------------------------------------------------


def test_qoder_security_scan_sidecar_is_never_offered_as_a_provider(tmp_path: Path, platform: str) -> None:
    """``~/.qodersec/bin/qodercli.exe`` is the scanner's pinned internal copy.

    It is stale relative to the real install and unauthenticated. Discovery
    matches exact names inside *registered* directories and never globs under
    the home directory, so it must never surface.
    """
    fake_home = tmp_path / "home"
    sidecar = _install_binary(fake_home / ".qodersec" / "bin", "qodercli", platform)
    _install_binary(fake_home / ".qodersec" / "bin", "qodersec", platform)
    assert sidecar.is_file()

    for key in ("qoder", "qoder-cn"):
        resolved = resolve_binary(registry.get(key), which=_nothing_on_path, home=fake_home, env={})
        assert resolved is None, f"{key} resolved to the security-scan sidecar: {resolved}"


def test_sidecar_directory_is_not_a_registered_well_known_dir() -> None:
    """Guards the data, not just the behaviour: no descriptor may register it."""
    for descriptor in registry.REGISTRY:
        for segments in descriptor.well_known_dirs:
            assert ".qodersec" not in segments


# ---------------------------------------------------------------------------
# FR-026: channel isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("installed", "missing", "binary", "install_dir"),
    [
        ("qoder", "qoder-cn", "qodercli", (".qoder", "bin", "qodercli")),
        ("qoder-cn", "qoder", "qoderclicn", (".qoder-cn", "bin", "qoderclicn")),
    ],
)
def test_a_missing_qoder_channel_never_resolves_to_its_sibling(
    tmp_path: Path,
    platform: str,
    installed: str,
    missing: str,
    binary: str,
    install_dir: tuple[str, ...],
) -> None:
    fake_home = tmp_path / "home"
    installed_path = _install_binary(fake_home.joinpath(*install_dir), binary, platform)

    assert resolve_binary(registry.get(installed), which=_nothing_on_path, home=fake_home, env={}) == installed_path
    assert resolve_binary(registry.get(missing), which=_nothing_on_path, home=fake_home, env={}) is None


def test_channels_resolve_independently_when_both_are_installed(tmp_path: Path, platform: str) -> None:
    fake_home = tmp_path / "home"
    intl = _install_binary(fake_home / ".qoder" / "bin" / "qodercli", "qodercli", platform)
    china = _install_binary(fake_home / ".qoder-cn" / "bin" / "qoderclicn", "qoderclicn", platform)

    assert resolve_binary(registry.get("qoder"), which=_nothing_on_path, home=fake_home, env={}) == intl
    assert resolve_binary(registry.get("qoder-cn"), which=_nothing_on_path, home=fake_home, env={}) == china
    assert intl != china


# ---------------------------------------------------------------------------
# Spawn-side binary resolution
# ---------------------------------------------------------------------------


class _FakePtyProcess:
    def __init__(self, argv: list[str], *args: Any, **kwargs: Any) -> None:
        _FakePtyProcess.spawned = {"argv": argv, "args": args, "kwargs": kwargs}

    spawned: ClassVar[dict[str, Any]] = {}


def test_spawn_agent_uses_cmd_when_windows_which_finds_bare_wrapper(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    """The pywinpty CreateProcess path cannot execute the bare npm wrapper."""
    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", _npm_shim_which)
    monkeypatch.setattr(terminal, "PtyProcess", _FakePtyProcess)
    monkeypatch.setattr(
        terminal,
        "_codex_mcp_config_overrides",
        lambda project_dir: [
            "-c",
            f"mcp_servers.scistudio.command={json.dumps(sys.executable)}",
        ],
    )

    terminal.spawn_agent(registry.get("codex"), project_dir=tmp_path, dangerous=True)

    argv = _FakePtyProcess.spawned["argv"]
    # ``resolve_binary`` returns a ``Path`` (frozen registry contract), so the
    # spawned argv carries the platform-native separator spelling.
    assert argv[0] == str(Path("C:/Users/dev/AppData/Roaming/npm/codex.cmd"))
    assert "--dangerously-bypass-approvals-and-sandbox" in argv


def test_spawn_agent_falls_back_to_the_bare_binary_name(monkeypatch: Any, tmp_path: Path) -> None:
    """An unresolved binary must fail inside the PTY the user opened.

    Raising out of the spawn call instead would replace the OS's own
    "not found" message with a stack trace in the server log.
    """
    monkeypatch.setattr(terminal, "PtyProcess", _FakePtyProcess)
    monkeypatch.setattr(terminal, "resolve_binary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(terminal, "_merge_provider_mcp_config", lambda descriptor, project_dir: None)

    terminal.spawn_agent(registry.get("kimi-code"), project_dir=tmp_path, dangerous=False)

    assert _FakePtyProcess.spawned["argv"][0] == "kimi"


def test_spawn_argv_seam_bypasses_binary_resolution(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(terminal.sys, "platform", "win32")
    monkeypatch.setattr(terminal.shutil, "which", _npm_shim_which)
    monkeypatch.setattr(terminal, "PtyProcess", _FakePtyProcess)

    terminal.spawn_agent(
        registry.get("codex"),
        project_dir=tmp_path,
        dangerous=True,
        _spawn_argv=[sys.executable, "-c", "pass"],
    )

    assert _FakePtyProcess.spawned["argv"] == [sys.executable, "-c", "pass"]


def test_spawn_provider_dispatches_on_kind_not_on_key(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(terminal, "PtyProcess", _FakePtyProcess)
    monkeypatch.setattr(terminal, "_user_shell_argv", lambda: ["shell"])
    monkeypatch.setattr(terminal, "resolve_binary", lambda desc, **_k: Path(desc.binary_candidates[0]))

    terminal.spawn_provider("user-terminal", project_dir=tmp_path, dangerous=False)
    assert _FakePtyProcess.spawned["argv"][0] == "shell"

    terminal.spawn_provider("qoder-cn", project_dir=tmp_path, dangerous=False)
    assert _FakePtyProcess.spawned["argv"][0] == "qoderclicn"


def test_spawn_provider_rejects_an_unknown_key(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="unknown provider"):
        terminal.spawn_provider("gemini-cli", project_dir=tmp_path, dangerous=False)


def test_spawn_user_terminal_uses_user_dependency_env(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(terminal, "PtyProcess", _FakePtyProcess)
    monkeypatch.setattr(terminal, "_user_shell_argv", lambda: ["shell"])
    monkeypatch.setattr(
        desktop_paths,
        "user_python_terminal_env",
        lambda python_executable: {
            "SCISTUDIO_PYTHON": str(python_executable),
            "SCISTUDIO_USER_PYTHON_SITE": str(tmp_path / "deps"),
        },
    )

    terminal.spawn_user_terminal(project_dir=tmp_path, dangerous=False, extra_env={"EXTRA": "1"})

    spawned = _FakePtyProcess.spawned
    assert spawned["argv"] == ["shell"]
    assert spawned["kwargs"]["extra_env"]["SCISTUDIO_PYTHON"] == sys.executable
    assert spawned["kwargs"]["extra_env"]["SCISTUDIO_USER_PYTHON_SITE"] == str(tmp_path / "deps")
    assert spawned["kwargs"]["extra_env"]["EXTRA"] == "1"


# ---------------------------------------------------------------------------
# Legacy aliases (TODO(#1994): removed once _state.py derives its spawner map)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("alias", "expected_binary"),
    [(terminal.spawn_claude, "claude"), (terminal.spawn_codex, "codex")],
)
def test_legacy_spawn_aliases_are_registry_lookups(
    monkeypatch: Any,
    tmp_path: Path,
    alias: Any,
    expected_binary: str,
) -> None:
    """The aliases must add nothing — no branching, no divergent argv."""
    monkeypatch.setattr(terminal, "PtyProcess", _FakePtyProcess)
    monkeypatch.setattr(terminal, "resolve_binary", lambda desc, **_k: Path(desc.binary_candidates[0]))
    monkeypatch.setattr(terminal, "_write_system_prompt_tempfile", lambda pd: pd / "prompt.md")

    alias(project_dir=tmp_path, dangerous=True)
    via_alias = _FakePtyProcess.spawned["argv"]

    key = "claude-code" if expected_binary == "claude" else "codex"
    terminal.spawn_agent(registry.get(key), project_dir=tmp_path, dangerous=True)
    via_spawn_agent = _FakePtyProcess.spawned["argv"]

    assert via_alias[0] == expected_binary
    assert via_alias == via_spawn_agent
