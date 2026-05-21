"""LC-MS plugin test configuration."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
_PACKAGE_SRC_STR = str(_PACKAGE_SRC)
if _PACKAGE_SRC_STR not in sys.path:
    sys.path.insert(0, _PACKAGE_SRC_STR)


def pytest_configure(config: pytest.Config) -> None:
    """Register LC-MS plugin marker names."""
    config.addinivalue_line(
        "markers",
        "requires_r: skip unless an R runtime is available (T-LCMS-007/017).",
    )
    config.addinivalue_line(
        "markers",
        "requires_elmaven: skip unless ElMAVEN is installed (T-LCMS-007).",
    )
