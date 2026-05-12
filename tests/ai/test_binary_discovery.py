"""Unit + integration tests for :mod:`scieasy.ai.agent.binary_discovery`.

The 8 fallback locations from ADR-033 §3 D1.2 are each exercised by an
isolated unit test that mocks the filesystem, ``subprocess.run``, and
``winreg`` so the test runs deterministically on every OS in CI.

A single integration test verifies real-binary resolution when ``claude``
is on the PATH; it is skipped otherwise.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scieasy.ai.agent import binary_discovery
from scieasy.ai.agent.binary_discovery import find_binary


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Pin HOME to a clean tmp directory and clear PATH-relevant env vars.

    This guarantees each test starts from "no real binary anywhere" and
    only the explicitly patched location resolves.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    monkeypatch.delenv("NVM_BIN", raising=False)
    monkeypatch.delenv("PNPM_HOME", raising=False)
    # Empty PATH so shutil.which never spuriously hits the host system.
    monkeypatch.setenv("PATH", "")


def _disable_all_but(monkeypatch: pytest.MonkeyPatch, *enabled: str) -> None:
    """Force every helper EXCEPT ``enabled`` ones to return ``None``.

    Keeps each unit test laser-focused on a single fallback.
    """
    helpers = [
        "_try_local_bin",
        "_try_env_dir",
        "_try_which",
        "_try_login_shell",
        "_try_windows_registry",
        "_try_nvm_versions",
        "_try_npm_global",
        "_try_standard_fallbacks",
    ]
    for helper in helpers:
        if helper in enabled:
            continue

        def _stub(*_args: Any, **_kwargs: Any) -> None:
            return None

        monkeypatch.setattr(binary_discovery, helper, _stub)


# ---------------------------------------------------------------------------
# Fallback 1: ~/.local/bin/<name>
# ---------------------------------------------------------------------------


def test_finds_in_local_bin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`~/.local/bin/claude` is the highest-priority fallback."""
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    binary = local_bin / "claude"
    binary.write_text("#!/bin/sh\n")
    _disable_all_but(monkeypatch, "_try_local_bin")

    result = find_binary("claude")
    assert result is not None
    assert result.name == "claude"
    assert ".local" in result.parts


# ---------------------------------------------------------------------------
# Fallback 2: $NVM_BIN/<name>
# ---------------------------------------------------------------------------


def test_finds_in_nvm_bin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`$NVM_BIN/claude` is consulted after `~/.local/bin`."""
    nvm_bin = tmp_path / "nvm" / "bin"
    nvm_bin.mkdir(parents=True)
    (nvm_bin / "claude").write_text("#!/bin/sh\n")
    monkeypatch.setenv("NVM_BIN", str(nvm_bin))
    _disable_all_but(monkeypatch, "_try_env_dir")

    result = find_binary("claude")
    assert result is not None
    assert result.parent == nvm_bin.resolve()


# ---------------------------------------------------------------------------
# Fallback 3: $PNPM_HOME/<name>
# ---------------------------------------------------------------------------


def test_finds_in_pnpm_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`$PNPM_HOME/claude` is consulted after `$NVM_BIN`."""
    pnpm = tmp_path / "pnpm"
    pnpm.mkdir()
    (pnpm / "claude").write_text("#!/bin/sh\n")
    monkeypatch.setenv("PNPM_HOME", str(pnpm))
    _disable_all_but(monkeypatch, "_try_env_dir")

    result = find_binary("claude")
    assert result is not None
    assert result.parent == pnpm.resolve()


# ---------------------------------------------------------------------------
# Fallback 4: shutil.which
# ---------------------------------------------------------------------------


def test_finds_via_shutil_which(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`shutil.which` is the fourth fallback."""
    fake = tmp_path / "from-path" / "claude"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))
    _disable_all_but(monkeypatch, "_try_which")

    result = find_binary("claude")
    assert result is not None
    assert result == fake.resolve()


# ---------------------------------------------------------------------------
# Fallback 5: bash -lc command -v
# ---------------------------------------------------------------------------


def test_finds_via_login_shell(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Login-shell `command -v` reveals shell-config-only PATH entries."""
    fake = tmp_path / "shell-bin" / "claude"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\n")

    def _fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=f"{fake}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    _disable_all_but(monkeypatch, "_try_login_shell")

    result = find_binary("claude")
    assert result is not None
    assert result == fake.resolve()


def test_login_shell_handles_no_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing `bash` does not raise; the fallback is just skipped."""

    def _no_bash(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("bash not installed")

    monkeypatch.setattr(subprocess, "run", _no_bash)
    _disable_all_but(monkeypatch, "_try_login_shell")
    assert find_binary("claude") is None


def test_login_shell_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bash login-shell timeout is non-fatal."""

    def _timeout(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="bash", timeout=2.0)

    monkeypatch.setattr(subprocess, "run", _timeout)
    _disable_all_but(monkeypatch, "_try_login_shell")
    assert find_binary("claude") is None


def test_login_shell_handles_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generic OSError (PermissionError, etc.) is non-fatal."""

    def _oserr(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise PermissionError("denied")

    monkeypatch.setattr(subprocess, "run", _oserr)
    _disable_all_but(monkeypatch, "_try_login_shell")
    assert find_binary("claude") is None


def test_login_shell_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero exit from `command -v` is a clean non-match."""

    def _failed(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="not found")

    monkeypatch.setattr(subprocess, "run", _failed)
    _disable_all_but(monkeypatch, "_try_login_shell")
    assert find_binary("claude") is None


def test_login_shell_empty_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    """`command -v` succeeding with empty stdout is a non-match."""

    def _empty(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _empty)
    _disable_all_but(monkeypatch, "_try_login_shell")
    assert find_binary("claude") is None


# ---------------------------------------------------------------------------
# Fallback 6: Windows registry (mocked so test runs everywhere)
# ---------------------------------------------------------------------------


def test_finds_via_windows_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Windows registry walk: mocked so the path is exercised on Linux + macOS CI."""
    fake_dir = tmp_path / "winpath"
    fake_dir.mkdir()
    fake = fake_dir / ("claude.exe" if os.name == "nt" else "claude")
    fake.write_text("#!/bin/sh\n")

    # Pretend we're on Windows for this test only.
    monkeypatch.setattr("sys.platform", "win32")

    # Build a fake winreg shim.
    class _FakeKey:
        def __enter__(self) -> _FakeKey:
            return self

        def __exit__(self, *_exc: Any) -> None:
            return None

    class _FakeWinreg:
        HKEY_CURRENT_USER = 0
        HKEY_LOCAL_MACHINE = 1

        @staticmethod
        def OpenKey(_root: int, _subkey: str) -> _FakeKey:  # noqa: N802 - matches winreg API
            return _FakeKey()

        @staticmethod
        def QueryValueEx(_key: _FakeKey, _name: str) -> tuple[str, int]:  # noqa: N802 - matches winreg API
            return (str(fake_dir), 1)

    monkeypatch.setitem(__import__("sys").modules, "winreg", _FakeWinreg)
    _disable_all_but(monkeypatch, "_try_windows_registry")

    result = find_binary("claude")
    assert result is not None
    assert result.parent.resolve() == fake_dir.resolve()


def test_windows_registry_skipped_on_unix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-Windows always returns None from the registry probe."""
    monkeypatch.setattr("sys.platform", "linux")
    assert binary_discovery._try_windows_registry("claude") is None


# ---------------------------------------------------------------------------
# Fallback 7: ~/.nvm/versions/node/*/bin/<name>
# ---------------------------------------------------------------------------


def test_finds_in_nvm_versions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Among multiple NVM versions, the lexicographically latest wins."""
    base = tmp_path / ".nvm" / "versions" / "node"
    for ver in ("v18.0.0", "v20.0.0", "v22.0.0"):
        bin_dir = base / ver / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "claude").write_text("#!/bin/sh\n")
    _disable_all_but(monkeypatch, "_try_nvm_versions")

    result = find_binary("claude")
    assert result is not None
    assert "v22.0.0" in str(result)


# ---------------------------------------------------------------------------
# Fallback 8: npm global
# ---------------------------------------------------------------------------


def test_finds_via_npm_global(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`npm root -g` parent's bin/<name> is the eighth fallback."""
    npm_root = tmp_path / "lib" / "node_modules"
    bin_dir = tmp_path / "lib" / "bin"
    bin_dir.mkdir(parents=True)
    npm_root.mkdir(parents=True)
    (bin_dir / "claude").write_text("#!/bin/sh\n")

    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/npm" if n == "npm" else None)

    def _fake_run(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=f"{npm_root}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    _disable_all_but(monkeypatch, "_try_npm_global")

    result = find_binary("claude")
    assert result is not None
    assert result.parent.resolve() == bin_dir.resolve()


def test_npm_global_skipped_when_npm_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without npm on PATH, the probe is a clean no-op."""
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    assert binary_discovery._try_npm_global("claude") is None


def test_npm_global_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """`npm root -g` timeout is non-fatal."""
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/npm" if n == "npm" else None)

    def _timeout(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="npm", timeout=5.0)

    monkeypatch.setattr(subprocess, "run", _timeout)
    assert binary_discovery._try_npm_global("claude") is None


def test_npm_global_handles_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    """`npm root -g` non-zero exit is non-fatal."""
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/npm" if n == "npm" else None)

    def _failed(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="oops")

    monkeypatch.setattr(subprocess, "run", _failed)
    assert binary_discovery._try_npm_global("claude") is None


# ---------------------------------------------------------------------------
# Fallback 9 (terminal): /usr/local/bin, /usr/bin
# ---------------------------------------------------------------------------


def test_finds_in_standard_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Standard fallback directories are the last resort."""
    # We can't write into /usr/local/bin in CI, so monkeypatch Path.is_file
    # to recognise a synthetic path.
    target = Path("/usr/local/bin/claude")

    real_is_file = Path.is_file

    def _is_file(self: Path) -> bool:
        if self == target:
            return True
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", _is_file)
    _disable_all_but(monkeypatch, "_try_standard_fallbacks")

    result = find_binary("claude")
    assert result is not None
    assert "/usr/local/bin" in str(result).replace("\\", "/")


# ---------------------------------------------------------------------------
# Misc edge cases
# ---------------------------------------------------------------------------


def test_empty_path_environment_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing on PATH and no fallbacks resolving, `find_binary` returns None cleanly."""
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    def _no_bash(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("no bash")

    monkeypatch.setattr(subprocess, "run", _no_bash)
    assert find_binary("definitely-not-installed-xyz") is None


def test_first_hit_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """When `~/.local/bin` resolves, later fallbacks must not be consulted."""
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "claude").write_text("#!/bin/sh\n")

    sentinel = {"called": False}

    def _should_not_be_called(*_a: Any, **_k: Any) -> Path | None:
        sentinel["called"] = True
        return None

    monkeypatch.setattr(binary_discovery, "_try_nvm_versions", _should_not_be_called)
    monkeypatch.setattr(binary_discovery, "_try_npm_global", _should_not_be_called)

    result = find_binary("claude")
    assert result is not None
    assert sentinel["called"] is False


def test_env_var_unset_short_circuits() -> None:
    """`_try_env_dir` with an unset env var returns None without touching the filesystem."""
    # Verifies the NVM_BIN / PNPM_HOME defensive path.
    assert binary_discovery._try_env_dir("DEFINITELY_UNSET_VAR_XYZ", "claude") is None


# ---------------------------------------------------------------------------
# Integration test — real binary, opt-in
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    shutil.which("claude") is None,
    reason="real `claude` CLI not on PATH; integration test skipped",
)
def test_integration_real_claude() -> None:
    """When a real `claude` binary is on PATH, `find_binary` resolves it."""
    result = find_binary("claude")
    assert result is not None
    assert result.is_file()
