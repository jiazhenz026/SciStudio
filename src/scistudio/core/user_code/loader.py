"""The one place SciStudio imports a user module."""
# Maintainer context (kept outside generated API documentation):
# ADR-056 Section 4.2, spec FR-002 and FR-003 (NEW-003).
#
# A user file is imported with ``importlib.import_module(<stem>)``, a package
# directory by its directory name. Python finds it through the user import path,
# runs it once and keeps it in ``sys.modules``, so every later import of the same
# stem in the process — from a block, a type, the type registry, a pickle —
# returns the same module and therefore the same classes. That is what makes a
# user data type one class per process.
#
# No function here takes a file path to execute and none invents a module name.
# A module already in ``sys.modules`` is returned as it is; making it current is
# what the forget step (``reset.py``) does.
#
# :func:`load_user_module` returns the classes a module *defines*
# (``cls.__module__ == module.__name__``), so a registry registers a class only
# from the module that defines it: a block file that imports a class from
# another block file does not register that class a second time.
#
# Every exception from the import becomes failure information on the result.
# ``BaseException`` is caught, not only ``Exception``: a script turned into a
# block often keeps its ``sys.exit(main())`` idiom, and a ``SystemExit`` must not
# take a registry scan down with it. ``KeyboardInterrupt`` is the exception: it
# is the operator's own signal, and swallowing it would make a scan
# uninterruptible.
# Development references: ADR-056, FR-002, FR-003, NEW-003.

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

__all__ = [
    "UserModuleLoad",
    "defined_classes",
    "load_user_module",
    "module_owner_dir",
    "module_source_file",
]


@dataclass(frozen=True)
class UserModuleLoad:
    """The outcome of importing one user module by name.

    On success ``module`` is set, ``classes`` holds the classes the module
    defines, and ``file`` / ``mtime_ns`` record the source file and its
    modification time at import. On failure ``module`` is ``None`` and
    ``error_type`` / ``message`` describe the exception.
    """

    name: str
    module: ModuleType | None = None
    classes: tuple[type, ...] = field(default_factory=tuple)
    file: Path | None = None
    mtime_ns: int | None = None
    error_type: str | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        """Whether the import succeeded."""
        return self.module is not None


def defined_classes(module: ModuleType) -> tuple[type, ...]:
    """Return the classes *module* defines itself, in ``dir()`` order.

    A class the module only imported carries another ``__module__`` and is left
    out, so a caller registers it from the module that defines it.
    """
    classes: list[type] = []
    for attr_name in dir(module):
        obj = getattr(module, attr_name, None)
        if isinstance(obj, type) and getattr(obj, "__module__", None) == module.__name__:
            classes.append(obj)
    return tuple(classes)


def module_source_file(name: str) -> Path | None:
    """Return the source file of the top-level module *name* without importing it.

    Reads ``sys.modules`` when the module is loaded and otherwise asks
    ``importlib.util.find_spec``, which for a top-level name locates the file
    without executing it. A package resolves to its ``__init__.py``.
    """
    if not name or "." in name:
        module = sys.modules.get(name) if name else None
        location = getattr(module, "__file__", None) if module is not None else None
        return Path(location) if location else None
    module = sys.modules.get(name)
    if module is not None:
        location = getattr(module, "__file__", None)
        return Path(location) if location else None
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin or spec.origin in {"built-in", "frozen"}:
        return None
    return Path(spec.origin)


def module_owner_dir(name: str) -> Path | None:
    """Return the ``sys.path`` directory the top-level module *name* resolves from.

    The directory holding ``<name>.py``, or holding the ``<name>/`` package.
    A registry scanning a directory registers a stem only when this is that
    directory; otherwise another user directory earlier on the path shadows the
    file (a project file shadowing a library file of the same stem).
    """
    source = module_source_file(name)
    if source is None:
        return None
    owner = source.parent.parent if source.name == "__init__.py" else source.parent
    try:
        return owner.resolve()
    except (OSError, ValueError):
        return owner


def load_user_module(name: str) -> UserModuleLoad:
    """Import the user module *name* by name and describe the result.

    Never raises except for ``KeyboardInterrupt``: an exception during the
    import is returned as ``error_type`` / ``message``.
    """
    # Development references: FR-002, FR-003.
    try:
        module = importlib.import_module(name)
        classes = defined_classes(module)
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        return UserModuleLoad(
            name=name,
            error_type=type(exc).__name__,
            message=str(exc) or type(exc).__name__,
        )
    location = getattr(module, "__file__", None)
    file = Path(location) if location else None
    mtime_ns: int | None = None
    if file is not None:
        try:
            mtime_ns = file.stat().st_mtime_ns
        except OSError:
            mtime_ns = None
    return UserModuleLoad(
        name=name,
        module=module,
        classes=classes,
        file=file,
        mtime_ns=mtime_ns,
    )
