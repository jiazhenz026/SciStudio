"""Shared fixtures/helpers for the dedicated ADR-052 contract suite (#1833).

Importing this conftest first inserts the suite directory onto ``sys.path`` so
the non-package helper module ``_spec_data`` is importable from the test modules
regardless of pytest's import mode. It also exposes small import helpers so the
tests never import a possibly-missing public name at module top level -- missing
symbols then surface as test *failures*, not collection errors, which keeps
``--collect-only`` clean in the pre-implementation tree.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def import_root(name: str):
    """Import and return a public root module, or ``None`` if it cannot import.

    Returning ``None`` (rather than raising) lets a test assert a clear failure
    message instead of erroring during collection.
    """
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001 - a broken root is a contract failure, reported by the test
        return None


def module_all(module) -> set[str]:
    """The declared public surface of a module: ``set(module.__all__)``."""
    return set(getattr(module, "__all__", ()) or ())


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
