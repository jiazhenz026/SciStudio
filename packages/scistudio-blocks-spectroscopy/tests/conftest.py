"""Spectroscopy plugin test configuration.

Adds the plugin's ``src`` directory to ``sys.path`` so the plugin tests can
import ``scistudio_blocks_spectroscopy`` without requiring an editable pip
install (matches the imaging plugin and the top-level skeleton shim).
"""

from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN_SRC = Path(__file__).resolve().parents[1] / "src"
if _PLUGIN_SRC.is_dir():
    _src_str = str(_PLUGIN_SRC)
    if _src_str not in sys.path:
        sys.path.insert(0, _src_str)
