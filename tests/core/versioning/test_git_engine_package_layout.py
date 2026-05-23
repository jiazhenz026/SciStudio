"""§C9 + ADR-046 Addendum 1 AST guard for ``GitEngine`` sibling modules.

Per ADR-028 Addendum 1 §C9 and ADR-046 Addendum 1, the private
``_*_ops.py`` siblings of ``git_engine.py`` must contain **only**
private module-level functions taking the ``GitEngine`` instance as
the first positional argument. They must contain **zero** ``class``
definitions — helper classes are explicitly forbidden by §C9.

This test parses each sibling module via :mod:`ast` and fails on any
``ClassDef`` node. It is a structural invariant guard: if a future
edit reintroduces a helper class in any ``_*_ops.py`` sibling, this
test must catch it.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_VERSIONING_DIR = Path("src/scistudio/core/versioning")
_SIBLING_FILES = sorted(_VERSIONING_DIR.glob("_*_ops.py"))


@pytest.mark.parametrize("path", _SIBLING_FILES, ids=lambda p: p.name)
def test_sibling_modules_define_no_classes(path: Path) -> None:
    """Each ``_*_ops.py`` sibling must contain zero ``class`` definitions
    (ADR-028 Addendum 1 §C9 + ADR-046 Addendum 1).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    assert classes == [], (
        f"§C9 violation in {path.as_posix()}: defines classes {classes}. "
        f"Per ADR-046 Addendum 1, only private module-level functions are "
        f"allowed in ``_*_ops.py`` siblings of GitEngine."
    )


def test_sibling_files_are_discovered() -> None:
    """Sanity check: at least 3 sibling modules exist.

    Guards against silent test deletion: if someone accidentally
    removes every ``_*_ops.py`` sibling, the parametrized test above
    would pass with zero rows. This explicit count keeps the layout
    contract visible.
    """
    assert len(_SIBLING_FILES) >= 3, (
        f"Expected at least 3 _*_ops.py siblings under {_VERSIONING_DIR}; "
        f"found {len(_SIBLING_FILES)}: {[p.name for p in _SIBLING_FILES]}"
    )
