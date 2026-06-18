"""Path helpers for developer and desktop-bundled SciStudio runs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "SciStudio"
APP_AUTHOR = "SciStudio"


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
