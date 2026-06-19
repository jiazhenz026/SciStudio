"""Path helpers for developer and desktop-bundled SciStudio runs."""

from __future__ import annotations

import contextlib
import importlib
import os
import shlex
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path

APP_NAME = "SciStudio"
APP_AUTHOR = "SciStudio"
PACKAGE_SITE_DIR_NAME = "site-packages"
USER_PYTHON_DIR_NAME = "python"


def _platformdirs_dir(kind: str) -> Path | None:
    try:
        from platformdirs import PlatformDirs
    except Exception:
        return None

    dirs = PlatformDirs(APP_NAME, APP_AUTHOR)
    value = {
        "config": dirs.user_config_dir,
        "cache": dirs.user_cache_dir,
        "logs": dirs.user_log_dir,
        "data": dirs.user_data_dir,
    }[kind]
    return Path(value)


def _fallback_dir(kind: str) -> Path:
    home = Path.home()
    if sys.platform == "win32":
        if kind == "config":
            return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / APP_NAME
        base = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / APP_NAME
        if kind == "cache":
            return base / "Cache"
        if kind == "logs":
            return base / "Logs"
        return base
    if sys.platform == "darwin":
        if kind in {"config", "data"}:
            return home / "Library" / "Application Support" / APP_NAME
        if kind == "cache":
            return home / "Library" / "Caches" / APP_NAME
        return home / "Library" / "Logs" / APP_NAME
    if kind == "config":
        return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "scistudio"
    if kind == "cache":
        return Path(os.environ.get("XDG_CACHE_HOME", home / ".cache")) / "scistudio"
    if kind == "logs":
        return Path(os.environ.get("XDG_STATE_HOME", home / ".local" / "state")) / "scistudio"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "scistudio"


def _user_dir(kind: str) -> Path:
    return _platformdirs_dir(kind) or _fallback_dir(kind)


def config_dir() -> Path:
    return _user_dir("config")


def cache_dir() -> Path:
    return _user_dir("cache")


def logs_dir() -> Path:
    return _user_dir("logs")


def plugins_dir() -> Path:
    return _user_dir("data") / "plugins"


def installed_packages_dir() -> Path:
    return plugins_dir() / "packages"


def user_python_dir() -> Path:
    """Return the shared user dependency runtime directory."""
    return plugins_dir() / USER_PYTHON_DIR_NAME


def user_python_site_dir() -> Path:
    """Return the shared user dependency import directory."""
    return user_python_dir() / PACKAGE_SITE_DIR_NAME


def user_python_bin_dir() -> Path:
    """Return the directory containing SciStudio Python command wrappers."""
    return user_python_dir() / ("Scripts" if sys.platform == "win32" else "bin")


def user_python_import_roots() -> list[Path]:
    """Return shared user dependency import roots that already exist."""
    site_dir = user_python_site_dir()
    return [site_dir] if site_dir.is_dir() else []


def _resolve_existing_dirs(entries: Iterable[str | Path]) -> tuple[Path, ...]:
    resolved: list[Path] = []
    seen: set[str] = set()
    for entry in entries:
        path = Path(entry).expanduser()
        if not path.is_dir():
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        resolved.append(Path(key))
    return tuple(resolved)


def package_import_roots(package_root: str | Path) -> tuple[Path, ...]:
    """Return import roots for one user-installed desktop package."""
    root = Path(package_root).expanduser()
    roots: list[Path] = []
    src_dir = root / "src"
    site_dir = root / PACKAGE_SITE_DIR_NAME
    if src_dir.is_dir():
        roots.append(src_dir)
    if root.is_dir() and any(root.glob("scistudio_blocks_*/__init__.py")):
        roots.append(root)
    if site_dir.is_dir():
        roots.append(site_dir)
    return tuple(roots)


def looks_like_source_package_root(path: str | Path) -> bool:
    """Return whether *path* looks like a SciStudio source package root."""
    root = Path(path).expanduser()
    return (root / "src").is_dir() or any(root.glob("scistudio_blocks_*/__init__.py"))


def iter_package_roots(package_dir: str | Path) -> Iterator[Path]:
    """Yield package roots from a packages dir, package root, or source dir."""
    expanded = Path(package_dir).expanduser()
    candidates = [expanded]
    if expanded.name == "src" and expanded.is_dir():
        yield expanded
        return
    if expanded.is_dir():
        candidates.extend(child for child in sorted(expanded.iterdir()) if child.is_dir())

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.is_dir() or not looks_like_source_package_root(candidate):
            continue
        key = str(candidate.resolve())
        if key in seen:
            continue
        seen.add(key)
        yield candidate


def source_package_import_roots(package_root: str | Path) -> tuple[Path, ...]:
    root = Path(package_root).expanduser()
    roots = [root] if root.name == "src" and root.is_dir() else []
    return _resolve_existing_dirs([*roots, *package_import_roots(root.parent if root.name == "src" else root)])


def iter_source_package_modules(import_root: str | Path) -> Iterator[str]:
    """Yield ``scistudio_blocks_*`` modules visible in one import root."""
    root = Path(import_root).expanduser()
    if not root.is_dir():
        return
    for package_init in sorted(root.glob("scistudio_blocks_*/__init__.py")):
        yield package_init.parent.name


def iter_source_package_module_candidates(
    package_dirs: Iterable[str | Path],
    *,
    module_suffixes: Iterable[str] = (),
) -> Iterator[tuple[str, str, tuple[Path, ...]]]:
    """Yield importable source-package module candidates for package dirs.

    Returns ``(root_module, candidate_module, import_roots)``. For example,
    with ``module_suffixes=("previewers",)`` an imaging package yields
    ``("scistudio_blocks_imaging", "scistudio_blocks_imaging", roots)`` and
    then ``("scistudio_blocks_imaging", "scistudio_blocks_imaging.previewers",
    roots)``.
    """
    suffixes = tuple(s.strip(".") for s in module_suffixes if s)
    seen_roots: set[str] = set()
    seen_candidates: set[str] = set()
    for package_dir in package_dirs:
        for package_root in iter_package_roots(package_dir):
            root_key = str(package_root.resolve())
            if root_key in seen_roots:
                continue
            seen_roots.add(root_key)
            import_roots = source_package_import_roots(package_root)
            root_modules = sorted(
                {
                    module_name
                    for import_root in import_roots
                    for module_name in iter_source_package_modules(import_root)
                }
            )
            for root_module in root_modules:
                for candidate in (root_module, *(f"{root_module}.{suffix}" for suffix in suffixes)):
                    if candidate in seen_candidates:
                        continue
                    seen_candidates.add(candidate)
                    yield root_module, candidate, import_roots


@contextlib.contextmanager
def prepended_sys_paths(paths: Iterable[str | Path]) -> Iterator[None]:
    """Prepend existing import roots to ``sys.path`` inside this context."""
    original = list(sys.path)
    for path in reversed(_resolve_existing_dirs(paths)):
        path_str = str(path)
        if path_str in sys.path:
            sys.path.remove(path_str)
        sys.path.insert(0, path_str)
    try:
        importlib.invalidate_caches()
        yield
    finally:
        sys.path[:] = original
        importlib.invalidate_caches()


def installed_package_import_roots() -> list[Path]:
    """Return import roots for all user-installed desktop packages."""
    roots: list[Path] = user_python_import_roots()
    packages_root = installed_packages_dir()
    if not packages_root.is_dir():
        return roots
    for child in sorted(packages_root.iterdir()):
        if child.is_dir():
            roots.extend(package_import_roots(child))
    return roots


def desktop_plugin_import_roots() -> tuple[Path, ...]:
    """Return all desktop/plugin import roots that should not leak into core."""
    roots: list[Path] = []
    for package_dir in candidate_package_dirs():
        expanded = package_dir.expanduser()
        roots.extend(package_import_roots(expanded))
        if expanded.is_dir():
            for child in sorted(expanded.iterdir()):
                if child.is_dir():
                    roots.extend(package_import_roots(child))
    return _resolve_existing_dirs(roots)


def activate_pythonpath_entries(
    entries: Iterable[str | Path],
    *,
    update_sys_path: bool = False,
) -> tuple[Path, ...]:
    """Add plugin import roots to inherited worker env.

    ``update_sys_path`` is opt-in so registry scans can keep their historical
    no-leak behavior and use scoped import contexts for in-process imports.
    """
    resolved = list(_resolve_existing_dirs(entries))
    if not resolved:
        return ()

    if update_sys_path:
        existing_sys_path = list(sys.path)
        for path in reversed(resolved):
            path_str = str(path)
            if path_str in sys.path:
                sys.path.remove(path_str)
            sys.path.insert(0, path_str)
        sys.path[:] = list(dict.fromkeys(sys.path + existing_sys_path))

    env_parts = [str(path) for path in resolved]
    for part in os.environ.get("PYTHONPATH", "").split(os.pathsep):
        if part and part not in env_parts:
            env_parts.append(part)
    os.environ["PYTHONPATH"] = os.pathsep.join(env_parts)
    return tuple(resolved)


def ensure_user_python_environment(python_executable: str | Path | None = None) -> dict[str, Path]:
    """Create user dependency directories and command wrappers.

    The wrappers make the desktop terminal feel like a normal shell while
    routing ``python``/``pip`` through the bundled runtime and user data dir.
    """
    python_path = Path(python_executable or sys.executable).resolve()
    site_dir = user_python_site_dir()
    bin_dir = user_python_bin_dir()
    site_dir.mkdir(parents=True, exist_ok=True)
    bin_dir.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        _write_command_wrapper(bin_dir / "python.cmd", python_path, site_dir, pip=False)
        _write_command_wrapper(bin_dir / "python3.cmd", python_path, site_dir, pip=False)
        _write_command_wrapper(bin_dir / "pip.cmd", python_path, site_dir, pip=True)
        _write_command_wrapper(bin_dir / "pip3.cmd", python_path, site_dir, pip=True)
    else:
        _write_command_wrapper(bin_dir / "python", python_path, site_dir, pip=False)
        _write_command_wrapper(bin_dir / "python3", python_path, site_dir, pip=False)
        _write_command_wrapper(bin_dir / "pip", python_path, site_dir, pip=True)
        _write_command_wrapper(bin_dir / "pip3", python_path, site_dir, pip=True)

    return {"bin": bin_dir, "site": site_dir, "python": python_path}


def user_python_terminal_env(python_executable: str | Path | None = None) -> dict[str, str]:
    """Return environment overrides for a desktop user dependency terminal."""
    paths = ensure_user_python_environment(python_executable)
    python_bin = paths["python"].parent
    activate_pythonpath_entries(
        [paths["site"], *installed_package_import_roots()],
        update_sys_path=False,
    )

    path_parts = [str(paths["bin"]), str(python_bin)]
    for part in os.environ.get("PATH", "").split(os.pathsep):
        if part and part not in path_parts:
            path_parts.append(part)

    return {
        "PATH": os.pathsep.join(path_parts),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "PIP_TARGET": str(paths["site"]),
        "PIP_REQUIRE_VIRTUALENV": "false",
        "SCISTUDIO_USER_PYTHON_SITE": str(paths["site"]),
        "SCISTUDIO_PYTHON": str(paths["python"]),
    }


def _write_command_wrapper(path: Path, python_path: Path, site_dir: Path, *, pip: bool) -> None:
    if sys.platform == "win32":
        command = '"%SCISTUDIO_PYTHON%" -m pip %*' if pip else '"%SCISTUDIO_PYTHON%" %*'
        lines = [
            "@echo off",
            f'set "SCISTUDIO_PYTHON={python_path}"',
            f'set "SCISTUDIO_USER_PYTHON_SITE={site_dir}"',
            *(['set "PIP_TARGET=%SCISTUDIO_USER_PYTHON_SITE%"', 'set "PIP_REQUIRE_VIRTUALENV=false"'] if pip else []),
            'set "PYTHONPATH=%SCISTUDIO_USER_PYTHON_SITE%;%PYTHONPATH%"',
            command,
            "exit /b %ERRORLEVEL%",
        ]
    else:
        command = 'exec "${SCISTUDIO_PYTHON}" -m pip "$@"' if pip else 'exec "${SCISTUDIO_PYTHON}" "$@"'
        lines = [
            "#!/bin/sh",
            f"SCISTUDIO_PYTHON={shlex.quote(str(python_path))}",
            f"SCISTUDIO_USER_PYTHON_SITE={shlex.quote(str(site_dir))}",
            "export SCISTUDIO_USER_PYTHON_SITE",
            *(
                ['export PIP_TARGET="${SCISTUDIO_USER_PYTHON_SITE}"', "export PIP_REQUIRE_VIRTUALENV=false"]
                if pip
                else []
            ),
            'export PYTHONPATH="${SCISTUDIO_USER_PYTHON_SITE}${PYTHONPATH:+:${PYTHONPATH}}"',
            command,
        ]
    body = "\n".join([*lines, ""])
    path.write_text(body, encoding="utf-8")
    if sys.platform != "win32":
        path.chmod(path.stat().st_mode | 0o755)


def shared_model_cache() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / APP_NAME / "models"
    if sys.platform == "darwin":
        return Path("/Library/Application Support") / APP_NAME / "models"
    return Path("/var/cache/scistudio/models")


def repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "scistudio").is_dir():
            return parent
    return None


def desktop_resources_dir() -> Path:
    env = os.environ.get("SCISTUDIO_DESKTOP_RESOURCES")
    if env:
        return Path(env).resolve()
    root = repo_root()
    if root is not None:
        return root / "desktop" / "resources"
    return Path(sys.executable).resolve().parent / "resources"


def bundled_resource(relative: str | Path) -> Path:
    return desktop_resources_dir() / Path(relative)


def bundled_packages_dir() -> Path:
    return bundled_resource("packages")


def candidate_package_dirs() -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("SCISTUDIO_PLUGIN_PACKAGE_DIRS", "")
    for item in env.split(os.pathsep):
        if item:
            dirs.append(Path(item).resolve())
    dirs.append(user_python_dir())
    dirs.append(installed_packages_dir())
    dirs.append(bundled_packages_dir())
    root = repo_root()
    if root is not None:
        dirs.append(root / "desktop" / "packages")

    unique: list[Path] = []
    seen: set[str] = set()
    for directory in dirs:
        key = str(directory)
        if key not in seen:
            seen.add(key)
            unique.append(directory)
    return unique
