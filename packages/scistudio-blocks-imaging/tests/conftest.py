"""Imaging plugin test configuration — Phase 11 skeleton placeholder.

Adds the plugin's ``src`` directory to ``sys.path`` so the plugin tests can
import ``scistudio_blocks_imaging`` without requiring an editable pip install
(matches the top-level ``tests/plugins/test_phase11_skeleton.py`` shim).
Once T-IMG-038 packaging lands and the plugin is installed editable in CI,
this shim becomes redundant and the test keeps passing via the normal
import path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_SRC = Path(__file__).resolve().parents[1] / "src"
if _PLUGIN_SRC.is_dir():
    _src_str = str(_PLUGIN_SRC)
    if _src_str not in sys.path:
        sys.path.insert(0, _src_str)
