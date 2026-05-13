"""Cross-platform discovery of the agent provider's CLI binary.

The discovery routine searches the eight fallback paths from ADR-033 §3 D1.2,
in order:

1. ``$HOME/.local/bin/<name>`` (Anthropic installer default).
2. ``$NVM_BIN/<name>``.
3. ``$PNPM_HOME/<name>``.
4. ``shutil.which("<name>")``.
5. Login-shell resolution: ``bash -lc "command -v <name>"`` (Unix).
6. Windows registry: ``HKCU\\Environment\\Path`` +
   ``HKLM\\System\\CurrentControlSet\\Control\\Session Manager\\Environment\\Path``.
7. NVM directories: ``$HOME/.nvm/versions/node/*/bin/<name>``.
8. npm global: ``$(npm root -g)/../bin/<name>`` (only if ``npm`` is on PATH).
9. Standard fallbacks: ``/usr/local/bin``, ``/usr/bin``.

First hit wins. ``None`` if no fallback resolves. The function never raises;
all subprocess / registry / filesystem failures are logged at DEBUG and
treated as a non-match.
"""

from __future__ import annotations

import glob
import logging
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_BASH_TIMEOUT_SEC = 2.0
_NPM_TIMEOUT_SEC = 5.0


def _resolve(path: Path) -> Path:
    """Return the path resolved to absolute form, falling back to absolute() on error."""
    try:
        return path.resolve()
    except OSError:  # symlink loop, missing parent, etc.
        return path.absolute()


def _check(path: Path, label: str) -> Path | None:
    """Return ``path`` resolved if it exists as a file, else ``None``."""
    logger.debug("find_binary: checking %s -> %s", label, path)
    try:
        if path.is_file():
            resolved = _resolve(path)
            logger.debug("find_binary: HIT %s at %s", label, resolved)
            return resolved
    except OSError as exc:
        logger.debug("find_binary: stat error for %s: %s", path, exc)
    return None


def _candidate_filenames(name: str) -> list[str]:
    """Return the list of basenames to look for on this platform.

    On Windows, both ``<name>`` (in case the user dropped a no-extension
    shim) and ``<name>.exe`` / ``<name>.cmd`` are valid.
    """
    if sys.platform == "win32":
        return [f"{name}.exe", f"{name}.cmd", name]
    return [name]


def _check_dir(directory: Path, name: str, label: str) -> Path | None:
    """Check every candidate filename under ``directory`` for ``name``."""
    for candidate in _candidate_filenames(name):
        hit = _check(directory / candidate, label)
        if hit is not None:
            return hit
    return None


def _try_local_bin(name: str) -> Path | None:
    home = Path(os.path.expanduser("~"))
    return _check_dir(home / ".local" / "bin", name, "~/.local/bin")


def _try_env_dir(env_var: str, name: str) -> Path | None:
    value = os.environ.get(env_var)
    if not value:
        logger.debug("find_binary: env var %s not set", env_var)
        return None
    return _check_dir(Path(value), name, f"${env_var}")


def _try_which(name: str) -> Path | None:
    result = shutil.which(name)
    if result is None:
        logger.debug("find_binary: shutil.which(%s) returned None", name)
        return None
    logger.debug("find_binary: shutil.which(%s) -> %s", name, result)
    return _resolve(Path(result))


def _try_login_shell(name: str) -> Path | None:
    """Use ``bash -lc 'command -v <name>'`` to catch shell-config-only PATH entries."""
    try:
        proc = subprocess.run(
            ["bash", "-lc", f"command -v {shlex.quote(name)}"],
            capture_output=True,
            text=True,
            timeout=_BASH_TIMEOUT_SEC,
        )
    except FileNotFoundError:
        logger.debug("find_binary: bash not available for login-shell probe")
        return None
    except subprocess.TimeoutExpired:
        logger.debug("find_binary: bash login-shell probe timed out")
        return None
    except OSError as exc:  # PermissionError, etc.
        logger.debug("find_binary: bash login-shell probe failed: %s", exc)
        return None
    if proc.returncode != 0:
        logger.debug("find_binary: bash login-shell probe returned %d", proc.returncode)
        return None
    output = proc.stdout.strip()
    if not output:
        return None
    path = Path(output.splitlines()[0].strip())
    return _check(path, "bash -lc command -v")


def _try_windows_registry(name: str) -> Path | None:
    """Walk HKCU + HKLM Path values for the binary (Windows only)."""
    if sys.platform != "win32":
        logger.debug("find_binary: skipping winreg on non-Windows")
        return None
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - non-Windows safety net
        logger.debug("find_binary: winreg unavailable")
        return None

    hives: list[tuple[int, str]] = [
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"System\CurrentControlSet\Control\Session Manager\Environment",
        ),
    ]
    for root, subkey in hives:
        try:
            with winreg.OpenKey(root, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
        except OSError as exc:
            logger.debug("find_binary: winreg %s failed: %s", subkey, exc)
            continue
        for entry in str(value).split(os.pathsep):
            entry = entry.strip()
            if not entry:
                continue
            hit = _check_dir(Path(entry), name, f"winreg:{subkey}")
            if hit is not None:
                return hit
    return None


def _try_nvm_versions(name: str) -> Path | None:
    """Search ``~/.nvm/versions/node/*/bin/<name>``; pick lexicographically latest."""
    home = Path(os.path.expanduser("~"))
    matches: list[str] = []
    for candidate in _candidate_filenames(name):
        pattern = str(home / ".nvm" / "versions" / "node" / "*" / "bin" / candidate)
        matches.extend(glob.glob(pattern))
    if not matches:
        logger.debug("find_binary: no nvm versions matched %s", name)
        return None
    chosen = sorted(matches)[-1]
    logger.debug("find_binary: HIT nvm-versions at %s (from %d candidates)", chosen, len(matches))
    return _resolve(Path(chosen))


def _try_npm_global(name: str) -> Path | None:
    """Resolve ``npm root -g`` and check its parent's ``bin/<name>``."""
    npm_path = shutil.which("npm")
    if npm_path is None:
        logger.debug("find_binary: npm not on PATH; skipping npm-global probe")
        return None
    try:
        proc = subprocess.run(
            [npm_path, "root", "-g"],
            capture_output=True,
            text=True,
            timeout=_NPM_TIMEOUT_SEC,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("find_binary: npm root -g failed: %s", exc)
        return None
    if proc.returncode != 0:
        logger.debug("find_binary: npm root -g returned %d", proc.returncode)
        return None
    root = proc.stdout.strip()
    if not root:
        return None
    parent = Path(root).parent
    return _check_dir(parent / "bin", name, "npm root -g/../bin")


def _try_standard_fallbacks(name: str) -> Path | None:
    for directory in ("/usr/local/bin", "/usr/bin"):
        hit = _check_dir(Path(directory), name, directory)
        if hit is not None:
            return hit
    return None


def find_binary(name: str) -> Path | None:
    """Locate the named binary using the ADR-033 §3 D1.2 fallback order.

    Parameters
    ----------
    name
        Bare binary name (e.g. ``"claude"``, ``"codex"``).

    Returns
    -------
    pathlib.Path or None
        Absolute path to the first matching binary, or ``None`` if no
        fallback resolves to an executable. Never raises — all subprocess,
        registry, and filesystem errors are swallowed at DEBUG.
    """
    logger.debug("find_binary: starting discovery for %s", name)
    finders = (
        _try_local_bin,
        lambda n: _try_env_dir("NVM_BIN", n),
        lambda n: _try_env_dir("PNPM_HOME", n),
        _try_which,
        _try_login_shell,
        _try_windows_registry,
        _try_nvm_versions,
        _try_npm_global,
        _try_standard_fallbacks,
    )
    for finder in finders:
        hit = finder(name)
        if hit is not None:
            logger.info("find_binary: resolved %s to %s", name, hit)
            return hit
    logger.info("find_binary: no fallback resolved for %s", name)
    return None
