"""Forget user modules so the next import runs the code on disk."""
# Maintainer context (kept outside generated API documentation):
# ADR-056 Section 4.6, spec FR-009 (NEW-009), first step.
#
# User modules now keep stable names, so a module imported once stays in
# ``sys.modules`` and a later ``import_module`` returns the cached copy. An edit
# therefore takes effect only after the module is forgotten. This module holds
# that forget step:
#
# 1. collect every module in ``sys.modules`` whose file lies under a directory
#    of the current or the previous user import path, submodules included;
# 2. remove them, delete their cached bytecode, and call
#    ``importlib.invalidate_caches()``.
#
# Every user module is forgotten, not only the changed ones. A block module that
# imported a type holds a reference to that type's class, so forgetting only the
# changed type would bring back two classes of one type. The caller rebuilds
# every registry that holds user classes right after (the existing refresh
# drivers do).
#
# Bytecode is deleted because CPython validates a ``.pyc`` against the source's
# modification time in whole seconds and its size: a file edited within one
# second of its last import, to the same length, would otherwise re-run the
# previous bytecode. This replaces ``core.dropins.evict_cached_bytecode``.
#
# TODO(ADR-056): grow this into the single reset entry point (mtime change
#   detection, rediscovery, the refresh event, resident panel restarts).
#   Out of scope per the owner-agreed ADR-056 three-PR split (spec FR-009 to
#   FR-013 and FR-015 land in the fourth pull request of that split).
#   Followup: ADR-056 implementation spec NEW-009, docs/specs/adr-056-user-code-import.md.
# Development references: ADR-056, FR-009, NEW-009.

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from types import ModuleType

from scistudio.core.user_code.import_path import clear_previous, forget_candidates

__all__ = ["evict_bytecode", "forget_user_modules"]


def evict_bytecode(source: str | Path) -> None:
    """Delete the ``__pycache__`` entry CPython would validate for *source*.

    Every failure is ignored: a missing or unwritable cache entry means the next
    import compiles from source, which is the point.
    """
    with suppress(OSError, NotImplementedError, ValueError):
        Path(importlib.util.cache_from_source(str(source))).unlink(missing_ok=True)


def _root_prefixes(roots: Iterable[str | Path]) -> tuple[str, ...]:
    prefixes: list[str] = []
    for root in roots:
        for spelling in (str(Path(root)), os.path.realpath(str(root))):
            prefix = spelling.rstrip(os.sep) + os.sep
            if prefix not in prefixes:
                prefixes.append(prefix)
    return tuple(prefixes)


def _module_location(module: ModuleType) -> str | None:
    location = getattr(module, "__file__", None)
    if location:
        return str(location)
    search = getattr(module, "__path__", None)
    if search is not None:
        with suppress(TypeError):
            for entry in search:
                return str(entry)
    return None


def _under(location: str, prefixes: tuple[str, ...]) -> bool:
    # A string comparison, not a resolved one: modules imported through the
    # installed entries carry those entries' (resolved) spelling in
    # ``__file__``, and resolving every module in the process would cost a
    # filesystem walk per module on every forget.
    return location.startswith(prefixes)


def forget_user_modules(extra_dirs: Iterable[str | Path] = ()) -> tuple[str, ...]:
    """Forget every user module and return the names forgotten, sorted.

    A module is a user module when its file lies under a directory of the
    current or the previous user import path (see
    :mod:`scistudio.core.user_code.import_path`), or under one of *extra_dirs*.
    Its ``sys.modules`` entry is removed, its cached bytecode deleted, and the
    import system's finder caches invalidated, so the next import of the name
    runs the file as it is on disk. The record of previous entries is cleared.
    """
    # Development references: FR-009.
    prefixes = _root_prefixes([*forget_candidates(), *extra_dirs])
    forgotten: list[str] = []
    if prefixes:
        for name, module in list(sys.modules.items()):
            if module is None:
                continue
            location = _module_location(module)
            if location is None or not _under(location, prefixes):
                continue
            sys.modules.pop(name, None)
            forgotten.append(name)
            if location.endswith(".py"):
                evict_bytecode(location)
    importlib.invalidate_caches()
    clear_previous()
    return tuple(sorted(forgotten))
