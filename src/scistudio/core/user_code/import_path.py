"""The user import path: the user directories every process keeps on ``sys.path``."""
# Maintainer context (kept outside generated API documentation):
# ADR-056 Section 4.1, spec FR-001 and FR-012 (NEW-001).
#
# The user import path is one ordered list of directories:
#
#   1. the entry folder of the process, when there is one (a panel folder for a
#      panel process, a plot folder for a plot render);
#   2. project ``types/``;
#   3. project ``blocks/``;
#   4. library ``types/`` (the tutorial-scoped library for a tutorial project);
#   5. library ``blocks/``.
#
# A directory that does not exist contributes no entry. The list is *appended*
# to ``sys.path``, after the standard library and the installed packages, and it
# stays there: nothing opens a scoped window around a user import any more.
# Because user directories come last, a user file can never shadow a module the
# process could already import; the name check (``names.py``) refuses the files
# that would be shadowed instead.
#
# This module owns the list and nothing else. It does not decide what is
# importable by name (``names.py``), import anything (``loader.py``), or forget
# modules (``reset.py``). The roots of installed packages and the user
# dependency site stay with :mod:`scistudio.desktop.paths` and
# :mod:`scistudio.core.entry_points`.
#
# Child processes (the block worker, the panel process, the plot harness) receive
# the list through one environment variable, :data:`USER_IMPORT_PATH_ENV_VAR`,
# holding a JSON array of absolute directory paths. JSON rather than
# ``os.pathsep`` so the plot harness, which must not import SciStudio, can read it
# with the standard library alone, and so a directory name containing the
# separator survives. The variable replaces the panel process's
# ``SCISTUDIO_PANEL_IMPORT_ROOTS`` and the worker payload's
# ``runtime_import_roots`` (spec API-009, MIG-004).
# Development references: ADR-056, FR-001, FR-012, NEW-001, API-009.

from __future__ import annotations

import importlib
import json
import os
import sys
import threading
from collections.abc import Iterable, Mapping
from pathlib import Path

from scistudio.core.dropins import (
    BLOCKS_DIR_NAME,
    TYPES_DIR_NAME,
    library_root_for_project,
    project_blocks_dir,
    project_types_dir,
)

__all__ = [
    "USER_IMPORT_PATH_ENV_VAR",
    "build_user_import_path",
    "ensure_user_import_path",
    "install_user_import_path",
    "install_user_import_path_from_env",
    "installed_user_import_path",
    "parse_user_import_path",
    "serialise_user_import_path",
    "user_import_path_env",
    "user_import_path_from_env",
]

#: Environment variable carrying the user import path into a child process, as
#: a JSON array of absolute directory paths.
USER_IMPORT_PATH_ENV_VAR = "SCISTUDIO_USER_IMPORT_PATH"

_LOCK = threading.RLock()
#: The directories this process installed, in ``sys.path`` spelling and order.
_INSTALLED: list[str] = []
#: Directories removed from the installed list since the last forget step. The
#: forget step still owns the modules imported from them (spec FR-009: "the
#: current or previous user import path").
_PREVIOUS: dict[str, None] = {}


def _existing_unique(dirs: Iterable[str | Path]) -> tuple[Path, ...]:
    """Resolve *dirs*, drop the ones that are not directories, keep first occurrences."""
    result: list[Path] = []
    seen: set[str] = set()
    for entry in dirs:
        try:
            path = Path(entry).expanduser()
            if not path.is_dir():
                continue
            resolved = path.resolve()
        except (OSError, ValueError):
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        result.append(resolved)
    return tuple(result)


def build_user_import_path(
    project_dir: str | Path | None,
    *,
    entry_folder: str | Path | None = None,
) -> tuple[Path, ...]:
    """Return the ordered user import path for a project context.

    *entry_folder* comes first when given; then the project ``types/`` and
    ``blocks/`` when a project is open; then the library ``types/`` and
    ``blocks/`` of :func:`scistudio.core.dropins.library_root_for_project`, so a
    tutorial project uses the tutorial-scoped library. Directories that do not
    exist are left out, and every entry is a resolved absolute path.
    """
    # Development references: FR-001, FR-070, FR-071.
    candidates: list[Path] = []
    if entry_folder is not None:
        candidates.append(Path(entry_folder))
    if project_dir is not None:
        candidates.extend((project_types_dir(project_dir), project_blocks_dir(project_dir)))
    library = library_root_for_project(project_dir)
    candidates.extend((library / TYPES_DIR_NAME, library / BLOCKS_DIR_NAME))
    return _existing_unique(candidates)


def installed_user_import_path() -> tuple[Path, ...]:
    """Return the user import path this process has installed, in order."""
    with _LOCK:
        return tuple(Path(entry) for entry in _INSTALLED)


def install_user_import_path(dirs: Iterable[str | Path]) -> tuple[Path, ...]:
    """Make *dirs* this process's user import path and return what was installed.

    The previously installed entries leave ``sys.path``; the new ones are
    appended at its end in the given order and stay there. An entry already on
    ``sys.path`` is moved to the end so the order of the list holds. Directories
    that do not exist are skipped. The replaced entries are remembered for the
    forget step until it next runs.
    """
    # Development references: FR-001, FR-009.
    new = _existing_unique(dirs)
    new_entries = [str(path) for path in new]
    with _LOCK:
        for entry in _INSTALLED:
            while entry in sys.path:
                sys.path.remove(entry)
        for entry in new_entries:
            while entry in sys.path:
                sys.path.remove(entry)
            sys.path.append(entry)
        for entry in _INSTALLED:
            if entry not in new_entries:
                _PREVIOUS[entry] = None
        _INSTALLED[:] = new_entries
    importlib.invalidate_caches()
    return new


def ensure_user_import_path(dirs: Iterable[str | Path]) -> tuple[Path, ...]:
    """Add to the installed user import path any of *dirs* it lacks.

    For a caller that was handed directories rather than a project, such as a
    registry built with explicit scan directories. A ``types/`` or ``blocks/``
    directory brings its tier sibling with it, in the path order (``types``
    before ``blocks``), so two registries built separately for one project
    produce the same path. Directories already installed keep their position.
    Returns the installed path.
    """
    # Development references: FR-001.
    wanted: list[Path] = []
    for entry in dirs:
        path = Path(entry)
        if path.name in (TYPES_DIR_NAME, BLOCKS_DIR_NAME):
            wanted.extend((path.parent / TYPES_DIR_NAME, path.parent / BLOCKS_DIR_NAME))
        else:
            wanted.append(path)
    with _LOCK:
        missing = [path for path in _existing_unique(wanted) if str(path) not in _INSTALLED]
        if missing:
            install_user_import_path([*_INSTALLED, *missing])
        return installed_user_import_path()


def forget_candidates() -> tuple[Path, ...]:
    """Return the current and the previous user import path, for the forget step."""
    with _LOCK:
        return tuple(Path(entry) for entry in dict.fromkeys([*_INSTALLED, *_PREVIOUS]))


def clear_previous() -> None:
    """Drop the record of previously installed entries; the forget step calls this."""
    with _LOCK:
        _PREVIOUS.clear()


def serialise_user_import_path(dirs: Iterable[str | Path]) -> str:
    """Return *dirs* as the value of :data:`USER_IMPORT_PATH_ENV_VAR`."""
    return json.dumps([str(Path(entry)) for entry in dirs])


def parse_user_import_path(raw: str | None) -> tuple[Path, ...]:
    """Return the directories in an environment value, ignoring malformed input."""
    if not raw:
        return ()
    try:
        value = json.loads(raw)
    except ValueError:
        return ()
    if not isinstance(value, list):
        return ()
    return tuple(Path(entry) for entry in value if isinstance(entry, str) and entry)


def user_import_path_env(dirs: Iterable[str | Path]) -> dict[str, str]:
    """Return the environment entry that carries *dirs* to a child process."""
    return {USER_IMPORT_PATH_ENV_VAR: serialise_user_import_path(dirs)}


def user_import_path_from_env(environ: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    """Return the user import path a parent process passed in the environment."""
    source = os.environ if environ is None else environ
    return parse_user_import_path(source.get(USER_IMPORT_PATH_ENV_VAR))


def install_user_import_path_from_env(environ: Mapping[str, str] | None = None) -> tuple[Path, ...]:
    """Install the user import path passed in the environment, if any.

    A child process calls this before it imports any user module.
    """
    # Development references: FR-012.
    dirs = user_import_path_from_env(environ)
    if not dirs:
        return installed_user_import_path()
    return install_user_import_path(dirs)
