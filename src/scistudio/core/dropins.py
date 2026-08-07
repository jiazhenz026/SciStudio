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

**FR-016 lives here too, for the same reason FR-057 does.** A types directory
on ``sys.path`` is a user-writable claim on the top-level module namespace: a
``json.py`` or ``numpy.py`` there would be imported in preference to the real
package by everything loaded afterwards. :func:`guard_dropin_type_roots` is the
single definition of what counts as a collision *and* of the mitigation —
binding the module the drop-in would shadow before the roots join ``sys.path``,
so the installed package keeps winning while the user renames the file.

It is here rather than in either registry because the roots reach ``sys.path``
from four processes and the answer must be the same in all of them. It
previously lived in ``blocks.registry._scan`` and ran only during the palette
scan, so a block resolved the installed module in the API process and the
drop-in file in the worker — the scan-time-versus-run-time divergence FR-013
exists to eliminate, reintroduced by the fix for it. The call sites are
:func:`scistudio.blocks.registry._scan._scan_tier1` (palette scan),
:meth:`scistudio.blocks.registry.BlockRegistry.instantiate` (in-process
execution), :func:`scistudio.engine.runners.worker._prepend_runtime_import_roots`
(worker subprocess), and :meth:`scistudio.core.types.registry.TypeRegistry._scan_filesystem_dirs`,
which asks the same question with ``bind=False`` and refuses registration on
the answer (§13 OQ-1: the refusal is a refusal, not a warning). That one call
site needs no binding because it loads drop-in types by file path rather than
through ``sys.path``, so binding would import a third-party package for no
reason; every site that *does* touch ``sys.path`` takes the default.

The guard takes *import* roots rather than type roots and picks the type tiers
out of them itself, by the ``<tier-root>/`` :data:`TYPES_DIR_NAME` shape
:func:`_tier_dirs` builds — exact rather than heuristic, because the same
module writes the paths and reads them back. ``runtime_import_roots``
interleaves the type tiers with the shared user dependency site, and a caller
that had to separate them first would be deciding FR-016's scope on its own —
the class of decision FR-057 removed.

One consumer holds block scan directories rather than a project directory.
:class:`scistudio.blocks.registry.BlockRegistry` is handed its directories
through :func:`register_block_scan_dirs` and never learns the project root, but
FR-012 requires the drop-in blocks it executes to import drop-in types by file
name. Every tier is ``<root>/<child>`` (:func:`_tier_dirs`), so a block
directory's tier root is its parent, and
:func:`dropin_type_roots_for_block_dirs` / :func:`dropin_import_roots_for_block_dirs`
turn a set of block directories back into the type directories and import roots
of the same tiers, first occurrence winning so the project tier stays ahead of
the user tier (FR-014). Deriving the roots from the directories the registry was
given — rather than from an environment variable — is what makes the answer
identical in the API, agent, worker, and IO dispatch processes (FR-057): none of
them sets ``SCISTUDIO_PROJECT_DIR`` for the API server, but all four register
their scan directories through this module.

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

import importlib
import importlib.util
import os
import sys
from collections.abc import Iterable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from scistudio.desktop.paths import user_python_import_roots

__all__ = [
    "BLOCKS_DIR_NAME",
    "PROJECT_DIR_ENV_VAR",
    "TYPES_DIR_NAME",
    "USER_LIBRARY_DIR_NAME",
    "DropinTypeCollision",
    "SupportsScanDirs",
    "block_scan_dirs",
    "dropin_import_roots",
    "dropin_import_roots_for_block_dirs",
    "dropin_type_roots_for_block_dirs",
    "guard_dropin_type_roots",
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


def dropin_type_roots_for_block_dirs(block_dirs: Iterable[str | Path]) -> tuple[Path, ...]:
    """Return the type dirs of the tiers *block_dirs* belong to (FR-012/FR-014).

    An empty input yields no type roots, so a registry that was given no scan
    directory stays inert rather than reaching into the user's home.
    """
    roots = [root for block_dir in block_dirs for root in type_scan_dirs(Path(block_dir).parent)]
    return tuple(dict.fromkeys(roots))


def dropin_import_roots_for_block_dirs(block_dirs: Iterable[str | Path]) -> tuple[Path, ...]:
    """Return :func:`dropin_import_roots` for a caller that holds block dirs."""
    return (*dropin_type_roots_for_block_dirs(block_dirs), *user_python_import_roots())


@dataclass(frozen=True)
class DropinTypeCollision:
    """A drop-in type entry whose name would shadow an installed module.

    ``path`` is what the user renames — the ``.py`` file, or the package
    directory when the entry is a package. ``stem`` is the top-level module
    name the entry would claim, and ``origin`` is where the module it collides
    with actually lives.
    """

    path: Path
    stem: str
    origin: str

    @property
    def message(self) -> str:
        """The FR-015 text shown to the user for this refusal."""
        return (
            f"{self.path.name} is rejected: the name {self.stem!r} already belongs to an "
            f"importable module ({self.origin}), which this drop-in would shadow once the "
            f"types directory joins sys.path. Rename it to a name no installed module uses."
        )


@contextmanager
def _sys_path_without(type_roots: tuple[Path, ...]) -> Iterator[None]:
    """Run the body with *type_roots* absent from ``sys.path``.

    Every FR-016 question is "what would this name resolve to if the drop-in
    were not there", so every one of them is asked from inside this block.
    """
    excluded = {str(root) for root in type_roots} | {str(root.resolve()) for root in type_roots}
    original = list(sys.path)
    sys.path[:] = [entry for entry in original if entry not in excluded]
    try:
        yield
    finally:
        sys.path[:] = original


def _is_within(origin: str | None, type_roots: tuple[Path, ...]) -> bool:
    """Return whether *origin* names a file inside one of *type_roots*."""
    if not origin or origin in {"built-in", "frozen"}:
        return False
    with suppress(OSError, ValueError):
        resolved = Path(origin).resolve()
        return any(resolved.is_relative_to(root.resolve()) for root in type_roots)
    return False


def _installed_origin(stem: str, type_roots: tuple[Path, ...]) -> str | None:
    """Return where an installed top-level *stem* lives, else ``None``.

    ``find_spec`` short-circuits on ``sys.modules``, so an earlier drop-in
    import of this very stem would otherwise answer for the installed module
    and turn a real collision into a clean bill of health. Dropping that
    binding first is safe: drop-in types register under synthetic
    ``_scistudio_type_dropin_*`` names, so nothing resolves through the stem,
    and a drop-in block that imports it gets it back on the next scan.
    """
    bound = sys.modules.get(stem)
    if bound is not None and _is_within(getattr(bound, "__file__", None), type_roots):
        del sys.modules[stem]
    try:
        found = importlib.util.find_spec(stem)
    except Exception:
        return None
    if found is None or _is_within(found.origin, type_roots):
        return None
    return found.origin or "built-in"


def _importable_entries(root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(module name, path the user would rename)`` under *root*.

    Both shapes a directory on ``sys.path`` makes importable are covered: a
    ``<name>.py`` file and a ``<name>/__init__.py`` package. A plain
    subdirectory is not, and cannot be: without ``__init__.py`` it only
    contributes a namespace portion, and Python resolves a regular module or
    package found anywhere on ``sys.path`` ahead of every namespace portion,
    so it can never displace an installed module.
    """
    with suppress(OSError):
        for entry in sorted(root.iterdir()):
            if entry.name.startswith("_"):
                continue
            if entry.is_file() and entry.suffix == ".py":
                yield entry.stem, entry
            elif entry.is_dir() and (entry / "__init__.py").is_file():
                yield entry.name, entry


def guard_dropin_type_roots(
    import_roots: Iterable[str | Path], *, bind: bool = True
) -> tuple[DropinTypeCollision, ...]:
    """Return the FR-016 collisions in *import_roots*, binding what they shadow.

    The single definition of both the rule and its mitigation. Call it from
    every site that puts drop-in type roots on ``sys.path``, before it does so.
    Binding is once per process per name, so a ``tensorflow.py`` collision does
    not re-import TensorFlow on every palette refresh. Pass ``bind=False`` when
    the caller only needs the verdict and never touches ``sys.path``.
    """
    type_roots = tuple(path for path in map(Path, import_roots) if path.name == TYPES_DIR_NAME)
    collisions: list[DropinTypeCollision] = []
    with _sys_path_without(type_roots):
        for root in type_roots:
            if not root.is_dir():
                continue
            for stem, path in _importable_entries(root):
                origin = _installed_origin(stem, type_roots)
                if origin is None:
                    continue
                collisions.append(DropinTypeCollision(path=path, stem=stem, origin=origin))
                if bind and stem not in sys.modules:
                    with suppress(Exception):
                        importlib.import_module(stem)
    return tuple(collisions)


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
