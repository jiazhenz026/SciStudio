"""One answer to "which drop-in directories does this process see?"."""
# Maintainer context (kept outside generated API documentation):
# One answer to "which drop-in directories does this process see?".
#
# ADR-053 / ``docs/specs/adr-053-personal-tool-library.md`` §2.6 + §10.3
# (FR-057 to FR-060). The same semantic used to be written out four times and no
# two copies agreed:
#
# ============================================  =====================  ==================
# Registration point                            Blocks                 Types
# ============================================  =====================  ==================
# ``scistudio.api.runtime._projects``           project + user, both   project gated,
#                                               gated on a project     user unconditional
# ``scistudio.ai.agent.mcp.runtime``            project + user, user   no scan dir at all
#                                               unconditional
# ``scistudio.core.types.serialization``        --                     project + user
# ``scistudio.blocks.io._unified_dispatch``     ``always_home=False``  ``always_home=True``
# ============================================  =====================  ==================
#
# The synchronisation between them was maintained by a comment. This module
# replaces that comment with a single implementation that all four sites call.
#
# **FR-057.** Drop-in directory registration (:func:`register_block_scan_dirs`,
# :func:`register_type_scan_dirs`) is provided here and consumed by every
# registration point. A call site MAY pass its own project directory and MAY
# declare whether a project context exists (by passing ``None``), but it MUST NOT
# decide which directories the tier comprises.
#
# **FR-058.** Blocks and types resolve through the same tier definition:
# :func:`user_library_dir` is the single answer to "where does the user tier
# live", and both :func:`block_scan_dirs` and :func:`type_scan_dirs` are the same
# :func:`_tier_dirs` call with a different child directory name.
#
# **FR-060.** User-tier discovery is unconditional. The user library is defined
# by the user's home directory and has no relationship to which project happens
# to be open. Project-tier discovery still requires a project, since without one
# there is no project directory to scan.
#
# Ordering is load-bearing and identical for both kinds: the project tier comes
# first. The type registry's drop-in pass skips names already registered, so
# listing the project tier first is what makes a project type shadow a
# user-library type of the same name, and the user import path keeps the same
# order so module-name resolution agrees with registration.
#
# Directories are returned whether or not they exist. Both registries skip
# missing scan directories at scan time and the user import path drops missing
# directories, while returning declared paths is what makes the four
# registration points comparable in
# ``tests/api/test_registry_provisioning_parity.py``.
#
# Scan *order* and duplicate-resolution policy are deliberately **not** owned
# here: this module answers "which directories" and "which import roots", while
# each registry keeps its own discovery pass ordering. See
# :meth:`scistudio.core.types.registry.TypeRegistry.scan_all` for the FR-061
# record of why the two orders stay separate.
#
# **ADR-056 moved the import machinery out.** This module used to hold the
# FR-016 collision guard (a refusing ``sys.meta_path`` finder, bare-module
# deletion, a probing ``sys.path`` window), ``transient_dropin_modules``, the
# import-root sets handed to each consumer, and bytecode eviction. User code is
# now imported by module name through one user import path
# (:mod:`scistudio.core.user_code`): the name check is
# :func:`scistudio.core.user_code.check_user_import_path`, the path is built from
# the directory resolvers below, and bytecode eviction is part of the forget
# step. What stays here is the tier vocabulary those modules read.
#
# The previewer drop-in tier (``<project>/previewers``, #2044 / #2017) was a
# third consumer until the legacy previewers were removed (#2493); panels are
# folders discovered by :mod:`scistudio.panels.registry` and never imported, so
# they need no import roots or collision guard, only :func:`panel_scan_dirs`.
#
# **The Learning Center adds a third kind and a second user-tier root**
# (``docs/specs/adr-053-learning-center.md`` FR-016, FR-031, FR-070 to FR-073).
# Tutorials are discovered from ``<project>/tutorials`` and
# ``~/.scistudio/tutorials`` through the same :func:`_tier_dirs` definition
# (:func:`tutorial_scan_dirs`), so every event that already refreshes the block
# and type registries reaches tutorial discovery too rather than needing a fourth
# provisioning path. And a project under :func:`tutorial_parent_dir` scans
# :func:`tutorial_library_dir` where a real project scans
# :func:`user_library_dir` — one root swapped by
# :func:`library_root_for_project`, not a new tier, which is why nothing above
# this module has to learn what a tutorial project is. The tutorial tier is not
# on the user import path: a tutorial directory holds a manifest and assets,
# nothing the product imports by module name.
#
# Layering: this module lives in ``scistudio.core`` because
# :mod:`scistudio.core.types.serialization` is one of the four consumers and the
# ``Core must not depend on blocks, engine, api, ai, or workflow`` import-linter
# contract forbids the reverse direction. It sits directly under ``core`` rather
# than under ``core.types`` so that ``core.types.serialization`` importing it is
# not a ``core.types`` sibling edge (the ``core.types submodules are acyclic``
# contract). ``core -> desktop.paths`` is an established edge
# (:mod:`scistudio.core.types.registry` already uses it).
# Development references: #2017, #2044, ADR-053, FR-012, FR-013, FR-014, FR-016, FR-031, FR-057, FR-058,
# FR-060, FR-061, FR-062, FR-070, FR-073, OQ-1, docs/specs/adr-053-learning-center.md,
# docs/specs/adr-053-personal-tool-library.md.

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from typing import Protocol

__all__ = [
    "BLOCKS_DIR_NAME",
    "PANELS_DIR_NAME",
    "PROJECT_DIR_ENV_VAR",
    "TUTORIALS_DIR_NAME",
    "TUTORIAL_LIBRARY_DIR_NAME",
    "TUTORIAL_PARENT_DIR_NAME",
    "TYPES_DIR_NAME",
    "USER_LIBRARY_DIR_NAME",
    "SupportsScanDirs",
    "block_scan_dirs",
    "is_tutorial_location",
    "library_root_for_project",
    "panel_scan_dirs",
    "project_blocks_dir",
    "project_dir_from_env",
    "project_tutorials_dir",
    "project_types_dir",
    "register_block_scan_dirs",
    "register_type_scan_dirs",
    "tutorial_library_dir",
    "tutorial_parent_dir",
    "tutorial_scan_dirs",
    "type_scan_dirs",
    "user_blocks_dir",
    "user_library_dir",
    "user_tutorials_dir",
    "user_types_dir",
]

#: Name of the per-user library directory under :func:`pathlib.Path.home`.
USER_LIBRARY_DIR_NAME = ".scistudio"

#: Child directory holding drop-in block files, in both tiers.
BLOCKS_DIR_NAME = "blocks"

#: Child directory holding drop-in ``DataObject`` files, in both tiers.
TYPES_DIR_NAME = "types"

#: Child directory holding panel folders, one ``panels/<panel-id>/`` per panel
#: or MiniApp, in both tiers (ADR-054). New projects are scaffolded with this
#: directory (#2411).
PANELS_DIR_NAME = "panels"

#: Child directory holding drop-in tutorial directories, in both tiers
#: (ADR-053 Learning Center FR-016).
TUTORIALS_DIR_NAME = "tutorials"

#: Directory under :func:`pathlib.Path.home` holding every tutorial project and
#: the tutorial-scoped library (ADR-053 Learning Center FR-062). The name the
#: single-tutorial implementation already used, kept so no user-visible location
#: changes (spec assumption A-002).
TUTORIAL_PARENT_DIR_NAME = "SciStudio Tutorials"

#: The tutorial-scoped library, a child of :func:`tutorial_parent_dir`
#: (ADR-053 Learning Center FR-070). Leading dot so it does not read as one more
#: tutorial project in a directory listing, and so clearing can tell the two
#: apart without consulting the known-projects registry.
TUTORIAL_LIBRARY_DIR_NAME = ".library"

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
    """Return the user library root, ``~/.scistudio``."""
    # Development references: FR-058.
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


def tutorial_parent_dir() -> Path:
    """Return the tutorial project parent, ``~/SciStudio Tutorials``."""
    # Development references: FR-062.
    return Path.home() / TUTORIAL_PARENT_DIR_NAME


def tutorial_library_dir() -> Path:
    """Return the tutorial-scoped library root.

    The user tier a tutorial project sees *in place of* :func:`user_library_dir`.
    One scenario has the user save a custom type to My Library so the next
    scenario can reuse it, and that must not deposit a teaching type into every
    real project the user opens afterwards.
    """
    # Development references: FR-070, FR-071.
    return tutorial_parent_dir() / TUTORIAL_LIBRARY_DIR_NAME


def is_tutorial_location(path: str | Path) -> bool:
    """Return whether *path* sits under :func:`tutorial_parent_dir`.

    Location is the definition of a tutorial project, not a second opinion about
    it: every tutorial project lives under one parent, with the
    scoped library there too, so the answer to "does this project scan the
    tutorial library" is decidable from the path alone. It has to be, because
    this module may not import :mod:`scistudio.api` and the known-projects
    marker lives there. The two markers answer different questions from
    the same rule: this one selects the library tier for a directory, and the
    known-projects one records *which* tutorial a project belongs to so the
    listing filter and the restart deletion can act on it.

    Non-resolvable paths answer ``False`` rather than raising: a caller asking
    about a path the filesystem will not resolve gets the real-project answer,
    which is the conservative one — it never routes a real project's writes into
    the tutorial library.
    """
    # Development references: FR-062, FR-064, FR-065, FR-066, FR-070.
    with suppress(OSError, ValueError):
        parent = tutorial_parent_dir().expanduser().resolve()
        return Path(path).expanduser().resolve().is_relative_to(parent)
    return False


def library_root_for_project(project_dir: str | Path | None) -> Path:
    """Return the user-tier library root *project_dir* scans.

    :func:`tutorial_library_dir` for a project under the tutorial parent and
    :func:`user_library_dir` for every other project, including the no-project
    case. The tier *shape* is unchanged — ``<root>/blocks``, ``<root>/types``,
    and ``<root>/panels`` either way — so the swap is one root rather than
    a fourth tier, which is what keeps :func:`block_scan_dirs`,
    :func:`type_scan_dirs`, :func:`panel_scan_dirs`, and the user import path
    (:func:`scistudio.core.user_code.build_user_import_path`) correct for
    tutorial projects without any of them learning what a tutorial is.
    """
    # Development references: FR-070, FR-071.
    if project_dir is not None and is_tutorial_location(project_dir):
        return tutorial_library_dir()
    return user_library_dir()


def user_tutorials_dir() -> Path:
    """Return the user tutorial tier, ``~/.scistudio/tutorials``."""
    # Development references: FR-016.
    return user_library_dir() / TUTORIALS_DIR_NAME


def project_tutorials_dir(project_dir: str | Path) -> Path:
    """Return the project tutorial tier, ``<project>/tutorials``."""
    # Development references: FR-016.
    return Path(project_dir) / TUTORIALS_DIR_NAME


def _tier_dirs(child: str, project_dir: str | Path | None, user_root: Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in directories named *child* for a project context.

    The one place the tier definition lives: the project tier when a
    project context exists, then the user tier unconditionally.

    *user_root* names the root the user tier lives under, defaulting to
    :func:`user_library_dir`. Only the three library kinds pass anything else —
    see :func:`library_root_for_project`.
    """
    # Development references: FR-058, FR-060.
    dirs: list[Path] = []
    if project_dir is not None:
        dirs.append(Path(project_dir) / child)
    dirs.append((user_root or user_library_dir()) / child)
    return tuple(dirs)


def block_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in block scan dirs for *project_dir*'s context.

    A tutorial project's user tier is the tutorial-scoped library
    (:func:`library_root_for_project`).
    """
    # Development references: FR-070, FR-071.
    return _tier_dirs(BLOCKS_DIR_NAME, project_dir, library_root_for_project(project_dir))


def type_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in type scan dirs for *project_dir*'s context.

    A tutorial project's user tier is the tutorial-scoped library
    (:func:`library_root_for_project`).
    """
    # Development references: FR-070, FR-071.
    return _tier_dirs(TYPES_DIR_NAME, project_dir, library_root_for_project(project_dir))


def tutorial_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in tutorial scan dirs for *project_dir*'s context.

    The API's user and project tutorial sources, resolved through the same tier
    definition as blocks and types so package install, package uninstall, branch
    switch, and the working-tree rewrites that refresh the registries reach
    tutorial discovery by the path they already travel rather than a
    fourth one.

    The user tier is ``~/.scistudio/tutorials`` for **every** project, tutorial
    projects included: :func:`library_root_for_project` swaps the root the user
    saves *into* during a tutorial, and applying that swap here as well
    would make the user's own tutorials disappear from the catalogue for as long
    as a tutorial was running.
    """
    # Development references: FR-016, FR-031, FR-070.
    return _tier_dirs(TUTORIALS_DIR_NAME, project_dir)


def panel_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the panel folder tiers for *project_dir*'s context.

    The project tier when a project context exists, then the user tier. A
    tutorial project's user tier is the tutorial-scoped library
    (:func:`library_root_for_project`), so a panel saved during one tutorial
    travels to the next tutorial project and never into ``~/.scistudio/panels``.
    """
    # Development references: #2086, FR-058, FR-060, FR-070, FR-071.
    return _tier_dirs(PANELS_DIR_NAME, project_dir, library_root_for_project(project_dir))


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
