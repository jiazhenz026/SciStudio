"""Shared fixtures/helpers for the dedicated ADR-052 contract suite (#1833).

Importing this conftest first inserts the suite directory onto ``sys.path`` so
the non-package helper module ``_spec_data`` is importable from the test modules
regardless of pytest's import mode. It also exposes small import helpers so the
tests never import a possibly-missing public name at module top level -- missing
symbols then surface as test *failures*, not collection errors, which keeps
``--collect-only`` clean in the pre-implementation tree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# The import helpers live in the uniquely named ``_spec_data`` module so the
# contract test modules can import them without going through the bare
# ``conftest`` module name (which, in a full-tree pytest run, collides with
# other suites' conftests in ``sys.modules`` — see _spec_data.import_root).
# Re-exported here so ``conftest.import_root`` keeps resolving too.
from _spec_data import import_root, module_all  # noqa: E402  (needs _HERE on sys.path first)

__all__ = ["import_root", "module_all"]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The worktree repository root (this file is tests/adr052_contract/conftest.py)."""
    return Path(_HERE).parents[1]


@pytest.fixture(scope="session")
def src_root(repo_root: Path) -> Path:
    return repo_root / "src" / "scistudio"


@pytest.fixture
def roots():
    from _spec_data import ROOTS

    return ROOTS
