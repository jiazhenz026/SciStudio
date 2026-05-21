"""SRS plugin test configuration with cross-plugin ``imaging_types`` fixture per §Q5.

Adds the plugin's ``src`` directory to ``sys.path`` so the plugin tests can
import ``scistudio_blocks_srs`` without requiring an editable pip install,
mirroring the imaging and lcms plugin conftests. Fixes issue #382.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
if _PACKAGE_SRC.is_dir():
    _src_str = str(_PACKAGE_SRC)
    if _src_str not in sys.path:
        sys.path.insert(0, _src_str)


@pytest.fixture(scope="session")
def imaging_types():
    """Session-scoped fixture that imports the imaging plugin or skips.

    Per ``docs/specs/phase11-implementation-standards.md`` §Q5, this is the
    only sanctioned way to import imaging-plugin types from SRS tests.
    Callers access ``imaging_types.Image``, ``imaging_types.Mask``, etc.
    """
    imaging = pytest.importorskip("scistudio_blocks_imaging")
    return imaging
