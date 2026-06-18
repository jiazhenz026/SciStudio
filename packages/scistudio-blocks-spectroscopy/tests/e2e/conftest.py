"""Shared helpers for the spectroscopy end-to-end workflow tests (#1661).

Scoped to ``tests/e2e/`` only. Provides thin run/extract helpers reused across
the per-group e2e test modules and re-exports the pseudo-spectra generators in
:mod:`fixtures` so test files can ``import e2e_helpers`` style without juggling
import roots. The package ``src`` directory is already on ``sys.path`` via the
parent ``tests/conftest.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.collection import Collection

# Make ``import fixtures`` work regardless of pytest import mode by putting this
# directory on sys.path (it holds the pseudo-spectra generators).
_E2E_DIR = str(Path(__file__).resolve().parent)
if _E2E_DIR not in sys.path:
    sys.path.insert(0, _E2E_DIR)

from scistudio_blocks_spectroscopy import _support  # noqa: E402


def config(**params: Any) -> BlockConfig:
    """Build a ``BlockConfig`` whose params ``config.get`` reads."""
    return BlockConfig(params=dict(params))


def frame(collection: Any) -> Any:
    """Return the single ``DataFrame`` in an output port collection as pandas."""
    return _support.dataframe_pandas(next(iter(collection)))


def spectra_list(collection: Any) -> list[Any]:
    """Materialise an output port ``Collection[Spectrum]`` to a list."""
    return list(collection)


def require_scipy() -> None:
    """Skip the current test when scipy is unavailable (function scope)."""
    pytest.importorskip("scipy")


def require_openpyxl() -> None:
    """Skip the current test when openpyxl is unavailable (function scope)."""
    pytest.importorskip("openpyxl")


__all__ = [
    "BlockConfig",
    "Collection",
    "config",
    "frame",
    "require_openpyxl",
    "require_scipy",
    "spectra_list",
]
