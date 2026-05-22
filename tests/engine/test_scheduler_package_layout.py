"""ADR-046 §6 guard: scheduler sub-package siblings must have zero ``class`` defs.

The Path D structural-decomposition pattern (ADR-028 Addendum 1 §C9 /
ADR-046 §4) forbids helper classes in the sibling modules. Method
bodies live as private ``_underscore`` module-level functions whose
first parameter is ``self``, and they are bound onto :class:`DAGScheduler`
via class-body static assignment inside ``scheduler/__init__.py``.

This test walks the AST of each Path D sibling and asserts no
``ClassDef`` nodes exist. It also verifies that ``DAGScheduler`` and
``RunHandle`` are the only top-level classes in ``__init__.py`` so a
future contributor cannot quietly relocate them and lose the canonical
griffe fact path.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import scistudio.engine.scheduler as scheduler_pkg

# Resolve the package directory once via the imported module so tests
# do not rely on the current working directory.
_PACKAGE_DIR = Path(scheduler_pkg.__file__).resolve().parent

# Path D siblings governed by ADR-046 §6: each one MUST contain zero
# ``ClassDef`` nodes. ``_helpers.py`` is also a sibling created by the
# decomposition but it holds only three module-level helper functions
# and likewise has zero classes — kept in this set so a future drift
# (e.g. someone introducing a helper dataclass) fails fast.
_PATH_D_SIBLINGS = (
    "_dispatch.py",
    "_events.py",
    "_lineage.py",
    "_state.py",
    "_rerun.py",
    "_helpers.py",
)


def _classes_in(path: Path) -> list[str]:
    """Return the names of all top-level ``ClassDef`` nodes in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.name for node in tree.body if isinstance(node, ast.ClassDef)]


@pytest.mark.parametrize("sibling", _PATH_D_SIBLINGS)
def test_path_d_sibling_has_zero_classes(sibling: str) -> None:
    """ADR-046 §6: each Path D sibling must contain zero ``ClassDef`` nodes."""
    path = _PACKAGE_DIR / sibling
    assert path.is_file(), f"Path D sibling {sibling} missing from scheduler package"
    found = _classes_in(path)
    assert not found, (
        f"ADR-046 §6 violation: {sibling} declares class(es) {found}; Path D forbids helper classes in sibling modules."
    )


def test_init_classes_are_only_dagscheduler_and_runhandle() -> None:
    """ADR-046 §3: ``__init__.py`` is the only home of ``DAGScheduler`` and ``RunHandle``."""
    found = _classes_in(_PACKAGE_DIR / "__init__.py")
    assert sorted(found) == ["DAGScheduler", "RunHandle"], (
        f"ADR-046 §3: scheduler/__init__.py must declare exactly DAGScheduler and RunHandle, found {found}."
    )


def test_public_import_surface_preserved() -> None:
    """Pre-split callers must keep importing the same names."""
    from scistudio.engine.scheduler import (
        DAGScheduler,
        RunHandle,
        _collect_object_ids,
        _extract_error_summary,
        _object_ids_for_value,
    )

    # The three module-level helpers stay reachable at the
    # ``scistudio.engine.scheduler.<name>`` import path (ADR-046 §3).
    assert callable(_collect_object_ids)
    assert callable(_extract_error_summary)
    assert callable(_object_ids_for_value)

    # The two classes remain bound on the package, not the siblings.
    assert DAGScheduler.__module__ == "scistudio.engine.scheduler"
    assert RunHandle.__module__ == "scistudio.engine.scheduler"
