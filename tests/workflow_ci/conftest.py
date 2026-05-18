"""Test helpers for the `.workflow/ci/` package.

Because `.workflow` starts with a dot, Python's normal import machinery
cannot treat `.workflow` as a package name.  We insert the `.workflow`
directory onto ``sys.path`` so the inner ``ci`` subdirectory is importable
as the top-level ``ci`` package.

This shim is test-only.  In CI, the ratchet wrapper and SARIF converters
are invoked as scripts (``python .workflow/ci/ratchet.py``), so they
don't depend on the package being importable from the project root.
"""

from __future__ import annotations

import sys
from pathlib import Path

_WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".workflow"
if str(_WORKFLOW_DIR) not in sys.path:
    sys.path.insert(0, str(_WORKFLOW_DIR))
