"""One answer to "which drop-in directories does this process see?".

ADR-053 / ``docs/specs/adr-053-personal-tool-library.md`` §2.6 + §10.3
(FR-057 to FR-060). The same semantic used to be written out four times and no
two copies agreed:

============================================  =====================  ==================
Registration point                            Blocks                 Types
============================================  =====================  ==================
``scistudio.api.runtime._projects``           project + user, both   project gated,
                                              gated on a project     user unconditional
``scistudio.ai.agent.mcp.runtime``            project + user, user   no scan dir at all
                                              unconditional
``scistudio.core.types.serialization``        --                     project + user
``scistudio.blocks.io._unified_dispatch``     ``always_home=False``  ``always_home=True``
============================================  =====================  ==================

The synchronisation between them was maintained by a comment. This module
replaces that comment with a single implementation that all four sites call.

**FR-057.** Drop-in directory registration (:func:`register_block_scan_dirs`,
:func:`register_type_scan_dirs`) and import-root injection
(:func:`dropin_import_roots`) are provided here and consumed by every
registration point. A call site MAY pass its own project directory and MAY
declare whether a project context exists (by passing ``None``), but it MUST NOT
decide which directories the tier comprises or which roots go on ``sys.path``.

**FR-058.** Blocks and types resolve through the same tier definition:
:func:`user_library_dir` is the single answer to "where does the user tier
live", and both :func:`block_scan_dirs` and :func:`type_scan_dirs` are the same
:func:`_tier_dirs` call with a different child directory name.

**FR-060.** User-tier discovery is unconditional. The user library is defined
by the user's home directory and has no relationship to which project happens
to be open. Project-tier discovery still requires a project, since without one
there is no project directory to scan.

Ordering is load-bearing and identical for both kinds: the project tier comes
first. The type registry's drop-in pass skips names already registered, so
listing the project tier first is what makes a project type shadow a
user-library type of the same name, and :func:`dropin_import_roots` keeps the
same order so module-name resolution agrees with registration.

Directories are returned whether or not they exist. Both registries skip
missing scan directories at scan time and
:func:`scistudio.desktop.paths.prepended_sys_paths` filters missing import
roots, while returning declared paths is what makes the four registration
points comparable in ``tests/api/test_registry_provisioning_parity.py``.

Scan *order* and duplicate-resolution policy are deliberately **not** owned
here: this module answers "which directories" and "which import roots", while
each registry keeps its own discovery pass ordering. See
:meth:`scistudio.core.types.registry.TypeRegistry.scan_all` for the FR-061
record of why the two orders stay separate.

Layering: this module lives in ``scistudio.core`` because
:mod:`scistudio.core.types.serialization` is one of the four consumers and the
``Core must not depend on blocks, engine, api, ai, or workflow`` import-linter
contract forbids the reverse direction. It sits directly under ``core`` rather
than under ``core.types`` so that ``core.types.serialization`` importing it is
not a ``core.types`` sibling edge (the ``core.types submodules are acyclic``
contract). ``core -> desktop.paths`` is an established edge
(:mod:`scistudio.core.types.registry` already uses it).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from scistudio.desktop.paths import user_python_import_roots

__all__ = [
    "BLOCKS_DIR_NAME",
    "PROJECT_DIR_ENV_VAR",
    "TYPES_DIR_NAME",
    "USER_LIBRARY_DIR_NAME",
    "SupportsScanDirs",
    "block_scan_dirs",
    "dropin_import_roots",
    "project_blocks_dir",
    "project_dir_from_env",
    "project_types_dir",
    "register_block_scan_dirs",
    "register_type_scan_dirs",
    "type_scan_dirs",
    "user_blocks_dir",
    "user_library_dir",
    "user_types_dir",
]

#: Name of the per-user library directory under :func:`pathlib.Path.home`.
USER_LIBRARY_DIR_NAME = ".scistudio"

#: Child directory holding drop-in block files, in both tiers.
BLOCKS_DIR_NAME = "blocks"

#: Child directory holding drop-in ``DataObject`` files, in both tiers.
TYPES_DIR_NAME = "types"

#: Environment variable carrying the active project root into processes that
#: do not own an ``ApiRuntime`` (worker subprocesses, the standalone MCP
#: bridge, IO dispatch). Set by
#: :class:`scistudio.engine.runners.local.LocalRunner` and by
#: ``scistudio install``.
PROJECT_DIR_ENV_VAR = "SCISTUDIO_PROJECT_DIR"


class SupportsScanDirs(Protocol):
    """Structural type for a registry that accepts drop-in scan directories.

    Both :class:`scistudio.blocks.registry.BlockRegistry` and
    :class:`scistudio.core.types.registry.TypeRegistry` satisfy it. Declaring
    it structurally keeps this module free of any import of the block layer,
    which ``core`` may not depend on.
    """

    def add_scan_dir(self, directory: str | Path) -> None:  # pragma: no cover - protocol
        ...


def user_library_dir() -> Path:
    """Return the user library root, ``~/.scistudio`` (FR-058)."""
    return Path.home() / USER_LIBRARY_DIR_NAME


def user_blocks_dir() -> Path:
    """Return the user-tier drop-in block dir, ``~/.scistudio/blocks``."""
    return user_library_dir() / BLOCKS_DIR_NAME


def user_types_dir() -> Path:
    """Return the user-tier drop-in type dir, ``~/.scistudio/types``."""
    return user_library_dir() / TYPES_DIR_NAME


def project_blocks_dir(project_dir: str | Path) -> Path:
    """Return the project-tier drop-in block dir, ``<project>/blocks``."""
    return Path(project_dir) / BLOCKS_DIR_NAME


def project_types_dir(project_dir: str | Path) -> Path:
    """Return the project-tier drop-in type dir, ``<project>/types``."""
    return Path(project_dir) / TYPES_DIR_NAME


def project_dir_from_env() -> Path | None:
    """Return the project root from ``SCISTUDIO_PROJECT_DIR``, else ``None``."""
    raw = os.environ.get(PROJECT_DIR_ENV_VAR, "").strip()
    return Path(raw) if raw else None


def _tier_dirs(child: str, project_dir: str | Path | None) -> tuple[Path, ...]:
    """Return the drop-in directories named *child* for a project context.

    The one place the tier definition lives (FR-058): the project tier when a
    project context exists, then the user tier unconditionally (FR-060).
    """
    dirs: list[Path] = []
    if project_dir is not None:
        dirs.append(Path(project_dir) / child)
    dirs.append(user_library_dir() / child)
    return tuple(dirs)


def block_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in block scan dirs for *project_dir*'s context."""
    return _tier_dirs(BLOCKS_DIR_NAME, project_dir)


def type_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in type scan dirs for *project_dir*'s context."""
    return _tier_dirs(TYPES_DIR_NAME, project_dir)


def dropin_import_roots(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the import roots to put on ``sys.path`` when running a drop-in.

    FR-057: no call site decides which roots go on ``sys.path``. They are the
    project types dir (when a project context exists), the user types dir, and
    the shared user dependency site from
    :func:`scistudio.desktop.paths.user_python_import_roots` - third-party
    packages the user installed through the in-app Python terminal. The type
    tiers come first and in :func:`type_scan_dirs` order, so a project type
    shadows a user-library type of the same module name.
    """
    return (*type_scan_dirs(project_dir), *user_python_import_roots())


def _register(registry: SupportsScanDirs, dirs: tuple[Path, ...]) -> tuple[Path, ...]:
    """Add every directory in *dirs* to *registry* and return them.

    Deliberately does not scan: the caller still owns *when* discovery runs.
    """
    for directory in dirs:
        registry.add_scan_dir(directory)
    return dirs


def register_block_scan_dirs(registry: SupportsScanDirs, project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Register :func:`block_scan_dirs` on *registry* and return them."""
    return _register(registry, block_scan_dirs(project_dir))


def register_type_scan_dirs(registry: SupportsScanDirs, project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Register :func:`type_scan_dirs` on *registry* and return them."""
    return _register(registry, type_scan_dirs(project_dir))
