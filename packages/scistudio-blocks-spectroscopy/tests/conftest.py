from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PACKAGE_SRC = ROOT / "packages" / "scistudio-blocks-spectroscopy" / "src"
CORE_SRC = ROOT / "src"

for path in (PACKAGE_SRC, CORE_SRC):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)
