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
package by everything loaded afterwards.
:func:`guard_dropin_type_roots` is the single definition of what counts as a
collision *and* of the mitigation — binding the module the drop-in would
shadow before the roots join ``sys.path``, so the installed package keeps
winning while the user renames the file.

The mitigation fails closed. A collided module that raises on import cannot be
bound, and a suppressed binding failure would leave the name free for the
drop-in file the guard just refused — FR-016 defeated in precisely the case it
exists for, by the import health of an unrelated package. Such a name is
refused outright instead, through :class:`_RefusedNameFinder`; see there for
why refusing is the same answer the un-shadowed process gives.

A refusal outlives the scan that discovered it but not the drop-in entry that
caused it. Each one is held on the warrant of the type roots where the
collision was found, and a subsequent pass over one of those roots withdraws
its warrant once the entry is gone, dropping the refusal when the last warrant
goes. Without that the product breaks an installed module it was never asked
to touch, for the life of the process, in answer to the user doing exactly
what the refusal asked — removing the file. The bound is the roots: a pass
never withdraws a warrant held by a root it was not asked about, because it
has no listing of that root and therefore no evidence the refusal is stale.

The collision question is asked of every name the directory makes importable,
including underscore-prefixed ones; :func:`_importable_entries` records why,
and why that is a different question from whether a registry registers the
file.

:func:`evict_cached_bytecode` is here for the FR-057 reason rather than the
FR-016 one: both drop-in scan passes must defeat CPython's bytecode-freshness
key before they load a file, and a rule restated at two scan sites is a rule
that drifts. See FR-062 and the function's own docstring.

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

Previewers are the third consumer (#2044 / #2017). ``<project>/previewers``
and ``~/.scistudio/previewers`` are the same user-writable claim on the
top-level module namespace as the types directories, so the tier definition
(:func:`previewer_scan_dirs`, :func:`previewer_import_roots`), the collision
guard (:func:`guard_dropin_roots`, one implementation shared with
the types guard), and :func:`evict_cached_bytecode` all live here rather than
as a fourth copy of the rule in ``scistudio.previewers.project``. The user
previewer tier exists at all because FR-060's rule — user-tier discovery is
unconditional, project-tier requires a project — applies to previewers
exactly as it does to types.

**The Learning Center adds a third kind and a second user-tier root**
(``docs/specs/adr-053-learning-center.md`` FR-016, FR-031, FR-070 to FR-073).
Tutorials are discovered from ``<project>/tutorials`` and
``~/.scistudio/tutorials`` through the same :func:`_tier_dirs` definition
(:func:`tutorial_scan_dirs`), so every event that already refreshes the block
and type registries reaches tutorial discovery too rather than needing a fourth
provisioning path. And a project under :func:`tutorial_parent_dir` scans
:func:`tutorial_library_dir` where a real project scans
:func:`user_library_dir` — one root swapped by
:func:`library_root_for_project`, not a new tier, which is why nothing above
this module has to learn what a tutorial project is. The tutorial tier's
absence from :func:`dropin_import_roots` is a decision rather than an omission;
that function records it.

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
    "PREVIEWERS_DIR_NAME",
    "PROJECT_DIR_ENV_VAR",
    "TUTORIALS_DIR_NAME",
    "TUTORIAL_LIBRARY_DIR_NAME",
    "TUTORIAL_PARENT_DIR_NAME",
    "TYPES_DIR_NAME",
    "USER_LIBRARY_DIR_NAME",
    "DropinTypeCollision",
    "SupportsScanDirs",
    "block_scan_dirs",
    "dropin_import_roots",
    "dropin_import_roots_for_block_dirs",
    "dropin_type_roots_for_block_dirs",
    "evict_cached_bytecode",
    "guard_dropin_roots",
    "guard_dropin_type_roots",
    "is_tutorial_location",
    "library_root_for_project",
    "previewer_import_roots",
    "previewer_scan_dirs",
    "project_blocks_dir",
    "project_dir_from_env",
    "project_previewers_dir",
    "project_tutorials_dir",
    "project_types_dir",
    "register_block_scan_dirs",
    "register_type_scan_dirs",
    "transient_dropin_modules",
    "tutorial_library_dir",
    "tutorial_parent_dir",
    "tutorial_scan_dirs",
    "type_scan_dirs",
    "user_blocks_dir",
    "user_library_dir",
    "user_previewers_dir",
    "user_tutorials_dir",
    "user_types_dir",
]

#: Name of the per-user library directory under :func:`pathlib.Path.home`.
USER_LIBRARY_DIR_NAME = ".scistudio"

#: Child directory holding drop-in block files, in both tiers.
BLOCKS_DIR_NAME = "blocks"

#: Child directory holding drop-in ``DataObject`` files, in both tiers.
TYPES_DIR_NAME = "types"

#: Child directory holding drop-in previewer files, in both tiers.
#: Previewers are this module's third consumer (#2044/#2017): the same tier
#: definition, collision guard, and bytecode eviction that blocks and types
#: use, applied to ``<project>/previewers`` and ``~/.scistudio/previewers``.
PREVIEWERS_DIR_NAME = "previewers"

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
    """Return the user library root, ``~/.scistudio`` (FR-058)."""
    return Path.home() / USER_LIBRARY_DIR_NAME


def user_blocks_dir() -> Path:
    """Return the user-tier drop-in block dir, ``~/.scistudio/blocks``."""
    return user_library_dir() / BLOCKS_DIR_NAME


def user_types_dir() -> Path:
    """Return the user-tier drop-in type dir, ``~/.scistudio/types``."""
    return user_library_dir() / TYPES_DIR_NAME


def user_previewers_dir() -> Path:
    """Return the user-tier drop-in previewer dir, ``~/.scistudio/previewers``."""
    return user_library_dir() / PREVIEWERS_DIR_NAME


def project_blocks_dir(project_dir: str | Path) -> Path:
    """Return the project-tier drop-in block dir, ``<project>/blocks``."""
    return Path(project_dir) / BLOCKS_DIR_NAME


def project_types_dir(project_dir: str | Path) -> Path:
    """Return the project-tier drop-in type dir, ``<project>/types``."""
    return Path(project_dir) / TYPES_DIR_NAME


def project_previewers_dir(project_dir: str | Path) -> Path:
    """Return the project-tier drop-in previewer dir, ``<project>/previewers``."""
    return Path(project_dir) / PREVIEWERS_DIR_NAME


def project_dir_from_env() -> Path | None:
    """Return the project root from ``SCISTUDIO_PROJECT_DIR``, else ``None``."""
    raw = os.environ.get(PROJECT_DIR_ENV_VAR, "").strip()
    return Path(raw) if raw else None


def tutorial_parent_dir() -> Path:
    """Return the tutorial project parent, ``~/SciStudio Tutorials`` (FR-062)."""
    return Path.home() / TUTORIAL_PARENT_DIR_NAME


def tutorial_library_dir() -> Path:
    """Return the tutorial-scoped library root (FR-070).

    The user tier a tutorial project sees *in place of* :func:`user_library_dir`.
    One scenario has the user save a custom type to My Library so the next
    scenario can reuse it, and that must not deposit a teaching type into every
    real project the user opens afterwards (FR-071).
    """
    return tutorial_parent_dir() / TUTORIAL_LIBRARY_DIR_NAME


def is_tutorial_location(path: str | Path) -> bool:
    """Return whether *path* sits under :func:`tutorial_parent_dir` (FR-070).

    Location is the definition of a tutorial project, not a second opinion about
    it: FR-062 puts every tutorial project under one parent and FR-070 puts the
    scoped library there too, so the answer to "does this project scan the
    tutorial library" is decidable from the path alone. It has to be, because
    this module may not import :mod:`scistudio.api` and the known-projects
    marker (FR-064) lives there. The two markers answer different questions from
    the same rule: this one selects the library tier for a directory, and the
    known-projects one records *which* tutorial a project belongs to so the
    listing filter (FR-065) and the restart deletion (FR-066) can act on it.

    Non-resolvable paths answer ``False`` rather than raising: a caller asking
    about a path the filesystem will not resolve gets the real-project answer,
    which is the conservative one — it never routes a real project's writes into
    the tutorial library.
    """
    with suppress(OSError, ValueError):
        parent = tutorial_parent_dir().expanduser().resolve()
        return Path(path).expanduser().resolve().is_relative_to(parent)
    return False


def library_root_for_project(project_dir: str | Path | None) -> Path:
    """Return the user-tier library root *project_dir* scans (FR-070, FR-071).

    :func:`tutorial_library_dir` for a project under the tutorial parent and
    :func:`user_library_dir` for every other project, including the no-project
    case. The tier *shape* is unchanged — ``<root>/blocks`` and ``<root>/types``
    either way — so the swap is one root rather than a fourth tier, which is
    what keeps :func:`block_scan_dirs`, :func:`type_scan_dirs`,
    :func:`dropin_import_roots`, and :func:`dropin_type_roots_for_block_dirs`
    correct for tutorial projects without any of them learning what a tutorial
    is.
    """
    if project_dir is not None and is_tutorial_location(project_dir):
        return tutorial_library_dir()
    return user_library_dir()


def user_tutorials_dir() -> Path:
    """Return the user tutorial tier, ``~/.scistudio/tutorials`` (FR-016)."""
    return user_library_dir() / TUTORIALS_DIR_NAME


def project_tutorials_dir(project_dir: str | Path) -> Path:
    """Return the project tutorial tier, ``<project>/tutorials`` (FR-016)."""
    return Path(project_dir) / TUTORIALS_DIR_NAME


def _tier_dirs(child: str, project_dir: str | Path | None, user_root: Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in directories named *child* for a project context.

    The one place the tier definition lives (FR-058): the project tier when a
    project context exists, then the user tier unconditionally (FR-060).

    *user_root* names the root the user tier lives under, defaulting to
    :func:`user_library_dir`. Only the two library kinds pass anything else —
    see :func:`library_root_for_project`.
    """
    dirs: list[Path] = []
    if project_dir is not None:
        dirs.append(Path(project_dir) / child)
    dirs.append((user_root or user_library_dir()) / child)
    return tuple(dirs)


def block_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in block scan dirs for *project_dir*'s context.

    A tutorial project's user tier is the tutorial-scoped library
    (:func:`library_root_for_project`, FR-070/FR-071).
    """
    return _tier_dirs(BLOCKS_DIR_NAME, project_dir, library_root_for_project(project_dir))


def type_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in type scan dirs for *project_dir*'s context.

    A tutorial project's user tier is the tutorial-scoped library
    (:func:`library_root_for_project`, FR-070/FR-071).
    """
    return _tier_dirs(TYPES_DIR_NAME, project_dir, library_root_for_project(project_dir))


def tutorial_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in tutorial scan dirs for *project_dir*'s context.

    FR-016's user and project tutorial sources, resolved through the same tier
    definition as blocks and types so package install, package uninstall, branch
    switch, and the working-tree rewrites that refresh the registries reach
    tutorial discovery by the path they already travel (FR-031) rather than a
    fourth one.

    The user tier is ``~/.scistudio/tutorials`` for **every** project, tutorial
    projects included: :func:`library_root_for_project` swaps the root the user
    saves *into* during a tutorial (FR-070), and applying that swap here as well
    would make the user's own tutorials disappear from the catalogue for as long
    as a tutorial was running.
    """
    return _tier_dirs(TUTORIALS_DIR_NAME, project_dir)


def previewer_scan_dirs(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the drop-in previewer scan dirs for *project_dir*'s context.

    Same tier definition as :func:`type_scan_dirs` (FR-058): the project tier
    when a project context exists, then the user tier unconditionally (FR-060).
    """
    return _tier_dirs(PREVIEWERS_DIR_NAME, project_dir)


def dropin_import_roots(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the import roots to put on ``sys.path`` when running a drop-in.

    FR-057: no call site decides which roots go on ``sys.path``. They are the
    project types dir (when a project context exists), the user types dir, and
    the shared user dependency site from
    :func:`scistudio.desktop.paths.user_python_import_roots` - third-party
    packages the user installed through the in-app Python terminal. The type
    tiers come first and in :func:`type_scan_dirs` order, so a project type
    shadows a user-library type of the same module name.

    For a tutorial project the type tiers come from the tutorial-scoped library
    rather than ``~/.scistudio`` (:func:`library_root_for_project`), so FR-071
    holds for module resolution and not only for registration: a teaching type
    is importable inside the tutorial and nowhere else.

    **The tutorial drop-in tier is deliberately not here** (ADR-053 Learning
    Center FR-016 with FR-020a). A tutorial directory holds a ``tutorial.yaml``
    and an ``assets/`` tree, nothing the product imports by module name, so it
    has no claim to make on ``sys.path`` — and putting ``<project>/tutorials``
    there would hand a project-level tutorial exactly the exposure FR-020a
    exists to close, since any ``.py`` beside a manifest would become an
    importable top-level module. Discovery reads those directories as files
    (:func:`tutorial_scan_dirs`); it never imports out of them.
    """
    return (*type_scan_dirs(project_dir), *user_python_import_roots())


def previewer_import_roots(project_dir: str | Path | None = None) -> tuple[Path, ...]:
    """Return the import roots to put on ``sys.path`` when running a drop-in previewer.

    Mirrors :func:`dropin_import_roots` for the previewer tier: the previewer
    scan dirs in :func:`previewer_scan_dirs` order, then the shared user
    dependency site, so a drop-in previewer's sibling imports and
    user-installed dependencies resolve the same way a drop-in type's do.
    """
    return (*previewer_scan_dirs(project_dir), *user_python_import_roots())


def dropin_type_roots_for_block_dirs(block_dirs: Iterable[str | Path]) -> tuple[Path, ...]:
    """Return the type dirs of the tiers *block_dirs* belong to (FR-012/FR-014).

    An empty input yields no type roots, so a registry that was given no scan
    directory stays inert rather than reaching into the user's home.

    A tutorial project's block dirs carry the swap with them: each tier root is
    the block dir's parent, and :func:`type_scan_dirs` re-applies
    :func:`library_root_for_project` to it, so a registry handed a tutorial
    project's directories resolves the tutorial library's types and never the
    user's (FR-071).
    """
    roots = [root for block_dir in block_dirs for root in type_scan_dirs(Path(block_dir).parent)]
    return tuple(dict.fromkeys(roots))


def dropin_import_roots_for_block_dirs(block_dirs: Iterable[str | Path]) -> tuple[Path, ...]:
    """Return :func:`dropin_import_roots` for a caller that holds block dirs."""
    return (*dropin_type_roots_for_block_dirs(block_dirs), *user_python_import_roots())


class _RefusedNameFinder:
    """``sys.meta_path`` entry that fails the import of an unguardable name.

    FR-016's mitigation is to *bind* the module a drop-in would shadow, so the
    installed package keeps winning while the user renames the file. That
    mitigation has one hole: a collided module can have a perfectly good spec
    and still **raise** on import — a missing native dependency is the ordinary
    case — and then there is nothing to bind. Leaving the name unbound while
    the caller goes on to prepend the drop-in types directory hands the name to
    the very file the guard just refused, so FR-016 fails in exactly the
    situation it exists for and the product's safety becomes a function of an
    unrelated package's import health.

    Refusing the name outright is what makes §13 OQ-1's "registration is
    refused, not merely warned" true in that case. It is also what the
    *unshadowed* process does: without the drop-in on ``sys.path`` that import
    raises, so raising is a restoration of the un-shadowed behaviour rather
    than a new failure. The refusal is scoped to the one colliding name, so the
    rest of the drop-in tier keeps working — dropping the whole root would
    punish every other type in it for one bad neighbour.

    Registered at ``sys.meta_path[0]``, and only while something is actually
    refused: the finder answers ``None`` for every other name, so a process with
    no unguardable collision never pays for it, and one whose last refusal is
    released stops paying again.

    **A refusal is held on a warrant, and ends with it.** It has to outlive the
    scan that discovered it — that is what failing closed means — but not the
    drop-in entry that caused it. Each refusal records the type roots whose
    contents warrant it, and :meth:`reconcile` lets the next pass withdraw the
    warrants of the roots it has just listed; a refusal left with no warrant is
    dropped. That is what makes the guard self-healing: the user
    removes the file the report named, rescans, and the name works again.

    The warrant is per root because a pass is given specific roots and knows the
    collision set for those alone. :meth:`reconcile` therefore only ever adds or
    withdraws the warrants of the roots it is handed, and a warrant held by a
    root outside the pass survives untouched. Releasing more than that would
    reopen FR-016 on the strength of not having looked.
    """

    def __init__(self) -> None:
        #: Colliding stem to the sentence explaining the refusal.
        self.reasons: dict[str, str] = {}
        #: Colliding stem to the type roots warranting it, by :func:`_root_warrant`.
        self.warrants: dict[str, set[str]] = {}
        self._silent = False

    @contextmanager
    def silenced(self) -> Iterator[None]:
        """Answer ``None`` for every name for the duration of the body.

        :func:`_sys_path_without` needs this module's own previous answers out
        of the way while it asks what a name would resolve to. A flag rather
        than a trip out of ``sys.meta_path``, because a refusal recorded
        *inside* that window puts the finder back mid-pass: the same stem
        colliding in a second root would then have this finder's ``ImportError``
        handed to :func:`_installed_origin` as the verdict on its own question
        and read as "no installed module owns this name". That root would be
        reported to nobody and would record no warrant, so removing the first
        root's file would release a refusal the second root's file still
        warrants — the FR-016 hole reopened by the release rule itself.
        """
        previous = self._silent
        self._silent = True
        try:
            yield
        finally:
            self._silent = previous

    def refuse(self, stem: str, reason: str) -> None:
        """Refuse *stem* from now on, installing the finder if needed.

        The warrant is not recorded here but by :meth:`reconcile`, at the end of
        the same pass, so that every warrant is derived from one listing rather
        than some here and some there.
        """
        self.reasons[stem] = reason
        self.warrants.setdefault(stem, set())
        self._sync_meta_path()

    def allow(self, stem: str) -> None:
        """Drop any refusal on *stem* — the binding succeeded after all.

        Unconditional and bounded by no root: the installed module is now in
        ``sys.modules``, where no drop-in file can displace it, so no root can
        still warrant refusing the name.
        """
        self.reasons.pop(stem, None)
        self.warrants.pop(stem, None)
        self._sync_meta_path()

    def reconcile(self, colliding_by_root: dict[str, frozenset[str]]) -> None:
        """Re-derive the warrants held by the roots in *colliding_by_root*.

        The argument is one guard pass's complete answer for the roots it
        listed: warrant key to the stems that still collide there. Every refused
        stem gains that root's warrant when it is in the set and loses it when
        it is not, and a refusal left with no warrant at all is dropped. Roots
        absent from the mapping are not consulted — the ones the pass was not
        given, and the ones it could not list — so their warrants stand.
        """
        for stem in list(self.reasons):
            held = self.warrants.setdefault(stem, set())
            for warrant, stems in colliding_by_root.items():
                if stem in stems:
                    held.add(warrant)
                else:
                    held.discard(warrant)
            if not held:
                del self.warrants[stem]
                del self.reasons[stem]
        self._sync_meta_path()

    def _sync_meta_path(self) -> None:
        """Hold a place on ``sys.meta_path`` exactly while something is refused."""
        installed = self in sys.meta_path
        if self.reasons and not installed:
            sys.meta_path.insert(0, self)
        elif not self.reasons and installed:
            sys.meta_path.remove(self)

    def find_spec(self, fullname: str, path: object = None, target: object = None) -> None:
        if self._silent:
            return None
        reason = self.reasons.get(fullname)
        if reason is None:
            return None
        raise ImportError(reason, name=fullname)


#: Process-wide, because the roots reach ``sys.path`` from several call sites
#: and the refusal has to outlive the scan that discovered it — though not the
#: drop-in entry that warrants it (:meth:`_RefusedNameFinder.reconcile`).
_REFUSED_NAMES = _RefusedNameFinder()


def _root_warrant(root: Path) -> str:
    """Return the key a refusal's warrant on *root* is recorded under.

    The resolved path, because the call sites do not agree on the spelling they
    pass: :func:`scistudio.engine.runners.worker._prepend_runtime_import_roots`
    resolves its roots before the guard ever sees them and the palette scan does
    not, and a warrant recorded under one spelling has to be found again under
    the other. A path that will not resolve keeps its literal spelling, which
    can only withhold a release, never grant one.
    """
    with suppress(OSError, ValueError):
        return str(root.resolve())
    return str(root)


@dataclass(frozen=True)
class DropinTypeCollision:
    """A drop-in type entry whose name would shadow an installed module.

    ``path`` is what the user renames — the ``.py`` file, or the package
    directory when the entry is a package. ``stem`` is the top-level module
    name the entry would claim, and ``origin`` is where the module it collides
    with actually lives. ``dir_label`` names the drop-in directory kind in the
    user-facing message (``"types"`` or ``"previewers"``).
    """

    path: Path
    stem: str
    origin: str
    dir_label: str = "types"

    @property
    def message(self) -> str:
        """The FR-015 text shown to the user for this refusal."""
        return (
            f"{self.path.name} is rejected: the name {self.stem!r} already belongs to an "
            f"importable module ({self.origin}), which this drop-in would shadow once the "
            f"{self.dir_label} directory joins sys.path. Rename it to a name no installed module uses."
        )


@contextmanager
def _sys_path_without(type_roots: tuple[Path, ...]) -> Iterator[None]:
    """Run the body as if the drop-in tier had never been installed.

    Every FR-016 question is "what would this name resolve to if the drop-in
    were not there", so every one of them is asked from inside this block. Two
    things have to go for that to be the question actually asked: *type_roots*
    leave ``sys.path``, and :data:`_REFUSED_NAMES` stops answering. The finder
    is this module's own answer to a previous scan, so leaving it live would
    make :func:`_installed_origin` see its ``ImportError`` and conclude the name
    is free — the guard would stop reporting the very collision it is enforcing,
    and would never retry a binding that fails only because a native dependency
    was missing when the scan ran. It is silenced rather than lifted out of
    ``sys.meta_path`` so that a refusal recorded *inside* the window cannot put
    it back mid-pass; :meth:`_RefusedNameFinder.silenced` records what that
    costs when it happens.

    Removes and re-inserts only the entries it took out, rather than swapping
    ``sys.path`` for a snapshot. The snapshot form clobbers a concurrent
    :func:`scistudio.desktop.paths.prepended_sys_paths` window — which is how a
    scan could end up asking this question against the wrong ``sys.path`` and
    reporting a false verdict in either direction
    (``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P3-1).
    """
    excluded = {str(root) for root in type_roots} | {str(root.resolve()) for root in type_roots}
    removed = [(index, entry) for index, entry in enumerate(sys.path) if entry in excluded]
    for index, _entry in reversed(removed):
        del sys.path[index]
    try:
        with _REFUSED_NAMES.silenced():
            yield
    finally:
        for index, entry in removed:
            sys.path.insert(min(index, len(sys.path)), entry)


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
    if found.origin:
        return found.origin
    # ``origin`` is ``None`` for a namespace package as well as for a genuinely
    # built-in module, and reporting a directory on disk as ``built-in`` sends
    # the user looking in the wrong place. Reporting the collision is still
    # right — a regular module does displace a namespace portion — so name the
    # directories instead (P3-10).
    locations = list(getattr(found, "submodule_search_locations", None) or [])
    if locations:
        return f"namespace package at {os.pathsep.join(locations)}"
    return "built-in"


#: Entries a directory on ``sys.path`` never makes importable *by name*.
#: ``__init__.py`` names the directory itself rather than a top-level module,
#: and ``__pycache__`` holds compiled artefacts. Everything else that matches
#: the two importable shapes below is in scope, underscore-prefixed or not.
_NEVER_IMPORTABLE_BY_NAME = frozenset({"__init__.py", "__pycache__"})


def _importable_entries(root: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(module name, path the user would rename)`` under *root*.

    Both shapes a directory on ``sys.path`` makes importable are covered: a
    ``<name>.py`` file and a ``<name>/__init__.py`` package. A plain
    subdirectory is not, and cannot be: without ``__init__.py`` it only
    contributes a namespace portion, and Python resolves a regular module or
    package found anywhere on ``sys.path`` ahead of every namespace portion,
    so it can never displace an installed module.

    **Underscore-prefixed names are in scope** (AUDIT-SEC P1-1,
    ``docs/audit/2026-08-07-adr-053-spec1-write-path.md``). This function
    answers the *collision* question — "which names does this directory claim
    on the top-level module namespace" — and a leading underscore does not
    stop ``import`` from finding a file. It is a convention meaning "private",
    and the two registries honour it for the separate *registration* question
    by skipping such files. Skipping them here as well exempted exactly the
    names that matter most: several of the standard library's private modules
    are imported lazily by ordinary calls, long after any scan has run, so a
    guard that only looks at public names never sees them. A user writing
    ``types/_helpers.py`` collides with nothing and is unaffected; only a name
    an installed module already owns is refused.

    The only exclusions are the entries that are structurally not importable
    by name (:data:`_NEVER_IMPORTABLE_BY_NAME`) and stems that are not Python
    identifiers, which no ``import`` statement can name and no installed
    module can be called.

    Raises ``OSError`` when *root* cannot be listed rather than yielding a short
    listing, because :func:`guard_dropin_type_roots` reads a listing as evidence
    that the names *not* in it are gone. A partial listing is not that evidence,
    and a truncated one would look like it.
    """
    for entry in sorted(root.iterdir()):
        if entry.name in _NEVER_IMPORTABLE_BY_NAME:
            continue
        if entry.is_file() and entry.suffix == ".py" and entry.stem.isidentifier():
            yield entry.stem, entry
        elif entry.is_dir() and entry.name.isidentifier() and (entry / "__init__.py").is_file():
            yield entry.name, entry


# Back-compat door for the types tier; the contract lives on :func:`guard_dropin_roots`.
def guard_dropin_type_roots(
    import_roots: Iterable[str | Path], *, bind: bool = True
) -> tuple[DropinTypeCollision, ...]:
    return guard_dropin_roots(import_roots, dir_name=TYPES_DIR_NAME, bind=bind)


def guard_dropin_roots(
    import_roots: Iterable[str | Path], *, dir_name: str, bind: bool = True
) -> tuple[DropinTypeCollision, ...]:
    """Return the FR-016 collisions in *import_roots*, binding what they shadow.

    The single definition of both the rule and its mitigation, shared by every
    drop-in kind; *dir_name* picks which drop-in roots are examined
    (:data:`TYPES_DIR_NAME` or :data:`PREVIEWERS_DIR_NAME`). Call it from every
    site that puts drop-in roots of that kind on ``sys.path``, before it does
    so. Binding is once per process per name, so a ``tensorflow.py`` collision
    does not re-import TensorFlow on every palette refresh. Pass ``bind=False``
    when the caller only needs the verdict and never touches ``sys.path``.

    The ``path.name == TYPES_DIR_NAME`` filter needs no widening for the
    tutorial tiers and must not get one. The tutorial-scoped library keeps the
    tier shape — its types dir is ``<tutorial parent>/.library/types`` — so it
    is already selected here and a teaching type shadowing ``numpy`` is refused
    exactly as a user-library one is. The tutorial *drop-in* tier
    (:func:`tutorial_scan_dirs`) is never on ``sys.path``
    (:func:`dropin_import_roots`), so it claims no module name and there is
    nothing for this guard to protect; selecting it here would only report
    collisions nobody can suffer.

    A pass also ends the refusals its own roots no longer warrant
    (:meth:`_RefusedNameFinder.reconcile`), which is what lets the user act on
    the report: rename the file it named, rescan, and the name is importable
    again. That half runs whatever *bind* says, because its evidence is the
    directory listing rather than the binding — a stem no entry in the root
    claims any more cannot be shadowed from that root by anybody. A root this
    pass was not given, or was given and could not list, produces no evidence
    and so keeps whatever it warrants.
    """
    type_roots = tuple(path for path in map(Path, import_roots) if path.name == dir_name)
    collisions: list[DropinTypeCollision] = []
    colliding_by_root: dict[str, set[str]] = {}
    bound_in_this_pass: set[str] = set()
    with _sys_path_without(type_roots):
        for root in type_roots:
            entries: tuple[tuple[str, Path], ...] = ()
            if root.is_dir():
                try:
                    entries = tuple(_importable_entries(root))
                except OSError:
                    # No listing, so no evidence in either direction. Leaving
                    # this root out of ``colliding_by_root`` withholds the
                    # release rather than granting it on a directory nobody
                    # could read.
                    continue
            stems = colliding_by_root.setdefault(_root_warrant(root), set())
            for stem, path in entries:
                origin = _installed_origin(stem, type_roots)
                if origin is None:
                    continue
                stems.add(stem)
                collision = DropinTypeCollision(path=path, stem=stem, origin=origin, dir_label=dir_name)
                collisions.append(collision)
                # One import attempt per name per pass: the same broken package
                # colliding in both tiers is one failure, not two. Which tiers
                # those were is recorded by the warrants above, not here.
                # A stem already refused outright is not retried either: its
                # binding failed once this process, and re-attempting it on
                # every later pass re-runs the broken module's top-level side
                # effects on hot paths such as per-render guard passes. The
                # reconcile above is what releases the refusal once the user
                # renames the colliding file, so the retry door stays open.
                if (
                    bind
                    and stem not in sys.modules
                    and stem not in bound_in_this_pass
                    and stem not in _REFUSED_NAMES.reasons
                ):
                    bound_in_this_pass.add(stem)
                    _bind_or_refuse(collision)
    _REFUSED_NAMES.reconcile({warrant: frozenset(stems) for warrant, stems in colliding_by_root.items()})
    return tuple(collisions)


def _bind_or_refuse(collision: DropinTypeCollision) -> None:
    """Bind the module *collision* shadows, or refuse the name if it raises.

    The mitigation half of FR-016, and the reason it cannot be written as
    ``with suppress(Exception)``: a suppressed binding failure leaves the name
    free for the drop-in the guard just refused. See :class:`_RefusedNameFinder`
    for why refusing is the fail-closed answer rather than a second failure, and
    for how long the resulting refusal is allowed to stand.
    """
    try:
        importlib.import_module(collision.stem)
    except Exception as exc:
        _REFUSED_NAMES.refuse(
            collision.stem,
            f"{collision.message} The installed module could not be imported "
            f"({exc!r}), so the name is refused outright rather than left for "
            f"the drop-in to claim.",
        )
    else:
        _REFUSED_NAMES.allow(collision.stem)


@contextmanager
def transient_dropin_modules(import_roots: Iterable[str | Path]) -> Iterator[None]:
    """Evict the ``sys.modules`` entries a scoped drop-in import window leaks.

    :func:`scistudio.desktop.paths.prepended_sys_paths` reverts ``sys.path``
    when its window closes but not what the window imported: a sibling
    ``import helpers`` stays cached under its bare stem, where the *next*
    tier's scan or render resolves that stale binding instead of its own
    file. The result is cross-tier wrong-code execution and false FR-016
    refusals that survive even closing the project (PR #2072 audit, #2017).
    On exit, every entry *added* inside the window whose ``__file__`` lives
    under one of *import_roots* is removed. Entries that predate the window
    are left alone: their verdicts belong to :func:`guard_dropin_roots`, not
    to this window.
    """
    roots = tuple(Path(root) for root in import_roots)
    before = set(sys.modules)
    try:
        yield
    finally:
        for name in set(sys.modules).difference(before):
            module = sys.modules.get(name)
            if module is not None and _is_within(getattr(module, "__file__", None), roots):
                del sys.modules[name]


def evict_cached_bytecode(py_file: Path) -> None:
    """Drop the ``__pycache__`` entry CPython would validate for *py_file*.

    A cached ``.pyc`` is accepted when its recorded source mtime — in whole
    **seconds** — and source size both match. A drop-in edited within one second
    of its last load, to the same length, therefore re-executes the previous
    bytecode: a reload clears the registry and then registers the very
    definition it was rebuilding to replace, with no error anywhere. FR-062
    exists to make an edit visible without a restart, so silently running the
    previous definition is the one outcome it cannot produce.

    Deleting the cache entry rather than tightening the key, because the key is
    CPython's and not ours. The cost is a recompile per drop-in file per scan,
    for a handful of small user-authored files off any hot path — the *edited*
    case is the whole point of this tier, so the cache has almost nothing to
    offer it. The recompile also writes back a ``.pyc`` that does match the
    current source, so each subsequent by-path load (in-process instantiation,
    the worker subprocess) inherits a correct cache instead of needing this call.

    Here rather than in either registry for the reason FR-057 gives: both scan
    passes need it, and a rule restated at two sites is a rule that drifts. Every
    failure is swallowed — a missing or unwritable cache entry means the loader
    compiles from source, which is exactly what this wants.
    """
    with suppress(OSError, NotImplementedError, ValueError):
        Path(importlib.util.cache_from_source(str(py_file))).unlink(missing_ok=True)


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
