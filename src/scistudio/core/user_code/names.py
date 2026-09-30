"""The name check every user file passes before it is imported."""
# Maintainer context (kept outside generated API documentation):
# ADR-056 Section 4.5, spec FR-008 (NEW-002).
#
# User directories sit at the end of ``sys.path``, so a user file never shadows
# a module the process can already import. The reverse is the hazard: a user
# file whose stem an installed module owns would be silently replaced by that
# module, and a stem appearing twice in one tier would depend on directory order
# the user never chose. Before a directory is used, every stem in it is checked:
#
# - a stem in ``sys.stdlib_module_names`` is refused;
# - a stem ``importlib.util.find_spec`` resolves outside the user import path is
#   refused;
# - a stem present in more than one directory of the same tier is a conflict,
#   and every file with that stem is refused.
#
# Across tiers no refusal applies: the order of the user import path decides,
# so a project file shadows a library file of the same stem.
#
# The check refuses by *returning* a refusal. It installs nothing on
# ``sys.meta_path``, deletes nothing from ``sys.modules`` and imports nothing;
# the refusing finder, the bare-module deletion and the probing window of the
# ``core.dropins`` guard it replaces are gone (spec MIG-009).
#
# A tier is identified by the parent of a directory: ``<root>/types`` and
# ``<root>/blocks`` share ``<root>``. That is exact rather than heuristic,
# because :func:`scistudio.core.dropins._tier_dirs` builds every tier directory
# as ``<root>/<child>``. A panel or plot entry folder has a parent of its own,
# so it forms a tier by itself.
# Development references: ADR-056, FR-008, NEW-002, MIG-009.

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from importlib.machinery import ModuleSpec, PathFinder
from pathlib import Path

__all__ = [
    "CONFLICT",
    "INSTALLED",
    "STDLIB",
    "NameRefusal",
    "check_user_import_path",
    "importable_entries",
]

#: Refusal reason: the stem is a standard-library module name.
STDLIB = "stdlib"
#: Refusal reason: the stem resolves to a module outside the user import path.
INSTALLED = "installed"
#: Refusal reason: the stem appears in more than one directory of one tier.
CONFLICT = "conflict"

#: Entries a directory on ``sys.path`` never makes importable by name.
_NEVER_IMPORTABLE_BY_NAME = frozenset({"__init__.py", "__pycache__"})


@dataclass(frozen=True)
class NameRefusal:
    """One user file or package the name check refused.

    ``path`` is what the user renames: the ``.py`` file, or the package
    directory. ``stem`` is the module name it would claim, ``reason`` one of
    :data:`STDLIB`, :data:`INSTALLED` or :data:`CONFLICT`, and ``detail`` where
    the competing module or file lives.
    """

    path: Path
    stem: str
    reason: str
    detail: str

    @property
    def error_type(self) -> str:
        """The failure class name a failure list records for this refusal."""
        return "UserModuleNameConflict" if self.reason == CONFLICT else "UserModuleNameCollision"

    @property
    def message(self) -> str:
        """The one-line explanation shown to the user, ending in a rename request."""
        if self.reason == STDLIB:
            why = f"the name {self.stem!r} belongs to the Python standard library"
        elif self.reason == INSTALLED:
            why = f"the name {self.stem!r} already belongs to an importable module ({self.detail})"
        else:
            why = f"the name {self.stem!r} is also used by {self.detail} in the same library tier"
        return f"{self.path.name} is refused: {why}. Rename it to a module name nothing else uses."


def importable_entries(directory: Path) -> Iterator[tuple[str, Path]]:
    """Yield ``(stem, path)`` for every module *directory* makes importable by name.

    Both shapes count: a ``<name>.py`` file and a ``<name>/__init__.py``
    package. Underscore-prefixed names count too: a leading underscore does not
    stop ``import`` from finding a file, even though the registries skip such
    files when they register. Stems that are not identifiers are skipped, since
    no ``import`` statement can name them. An unreadable directory yields
    nothing.
    """
    try:
        entries = sorted(directory.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.name in _NEVER_IMPORTABLE_BY_NAME:
            continue
        try:
            if entry.is_file() and entry.suffix == ".py" and entry.stem.isidentifier():
                yield entry.stem, entry
            elif entry.is_dir() and entry.name.isidentifier() and (entry / "__init__.py").is_file():
                yield entry.name, entry
        except OSError:
            continue


def _resolved(path: str | Path) -> Path | None:
    try:
        return Path(path).resolve()
    except (OSError, ValueError):
        return None


def _within(location: str | None, roots: Sequence[Path]) -> bool:
    if not location or location in {"built-in", "frozen"}:
        return False
    resolved = _resolved(location)
    if resolved is None:
        return False
    return any(resolved.is_relative_to(root) for root in roots)


def _spec_outside(stem: str, user_roots: Sequence[Path]) -> ModuleSpec | None:
    """Return the spec *stem* has when the user directories are left out, else ``None``.

    Asks every ``sys.meta_path`` finder, giving the path-based finder only the
    ``sys.path`` entries that are not user directories. A pure query: nothing
    on ``sys.path`` or ``sys.meta_path`` changes and nothing is imported. The
    user directories are left out because Python resolves a regular module
    anywhere on the path ahead of every namespace portion, so a query that saw
    the user file would hide a namespace package (``google``) the file displaces.
    """
    non_user = [entry for entry in sys.path if not _within(entry or os.getcwd(), user_roots)]
    for finder in sys.meta_path:
        try:
            if finder is PathFinder or (isinstance(finder, type) and issubclass(finder, PathFinder)):
                spec = PathFinder.find_spec(stem, non_user)
            else:
                find_spec = getattr(finder, "find_spec", None)
                if find_spec is None:
                    continue
                spec = find_spec(stem, None)
        except Exception:
            continue
        if spec is not None:
            return spec
    return None


def _outside_owner(stem: str, user_roots: Sequence[Path]) -> str | None:
    """Return where *stem* resolves outside the user import path, else ``None``."""
    module = sys.modules.get(stem)
    if module is not None:
        location = getattr(module, "__file__", None)
        if _within(location, user_roots):
            return None
        return location or "an already imported module"
    spec = _spec_outside(stem, user_roots)
    if spec is None:
        return None
    if spec.origin and spec.origin not in {"built-in", "frozen", "namespace"}:
        return None if _within(spec.origin, user_roots) else spec.origin
    locations = list(spec.submodule_search_locations or [])
    if locations:
        if all(_within(location, user_roots) for location in locations):
            return None
        return "namespace package at " + ", ".join(locations)
    return spec.origin or "built-in"


def check_user_import_path(
    dirs: Iterable[str | Path],
    *,
    user_import_path: Iterable[str | Path] | None = None,
) -> tuple[NameRefusal, ...]:
    """Return the refusals for every stem in *dirs*.

    *user_import_path* is the path a stem may legitimately resolve into; it
    defaults to *dirs*. Each refused file appears once, with the first reason
    that applies in the order standard library, installed module, same-tier
    conflict. The function imports nothing and changes no process state.
    """
    # Development references: FR-008.
    directories = [path for path in (_resolved(entry) for entry in dirs) if path is not None]
    roots_source = directories if user_import_path is None else [_resolved(entry) for entry in user_import_path]
    user_roots = [root for root in roots_source if root is not None]

    listing: list[tuple[Path, str, Path]] = []
    for directory in dict.fromkeys(directories):
        for stem, path in importable_entries(directory):
            listing.append((directory, stem, path))

    refusals: dict[Path, NameRefusal] = {}
    stdlib: frozenset[str] = getattr(sys, "stdlib_module_names", frozenset())
    for _directory, stem, path in listing:
        if stem in stdlib:
            refusals[path] = NameRefusal(path=path, stem=stem, reason=STDLIB, detail="standard library")
            continue
        owner = _outside_owner(stem, user_roots)
        if owner is not None:
            refusals[path] = NameRefusal(path=path, stem=stem, reason=INSTALLED, detail=owner)

    by_tier: dict[tuple[Path, str], list[tuple[Path, Path]]] = {}
    for directory, stem, path in listing:
        by_tier.setdefault((directory.parent, stem), []).append((directory, path))
    for (_tier, stem), members in by_tier.items():
        if len({directory for directory, _path in members}) < 2:
            continue
        for directory, path in members:
            if path in refusals:
                continue
            others = ", ".join(
                f"{other_dir.name}/{other_path.name}" for other_dir, other_path in members if other_dir != directory
            )
            refusals[path] = NameRefusal(path=path, stem=stem, reason=CONFLICT, detail=others)

    return tuple(refusals[path] for _directory, _stem, path in listing if path in refusals)
