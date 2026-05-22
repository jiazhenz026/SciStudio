"""Entry point for ``python -m scistudio.qa.governance.gate_record``.

Kept minimal — CI hooks, ``scripts/scistudio_pr_create.py``, and the
ADR-042 pre-commit hook all shell out to this module form, so the
behavior must stay identical to the pre-refactor single-file module.
"""

from __future__ import annotations

import sys

from scistudio.qa.governance.gate_record.cli import main

if __name__ == "__main__":
    sys.exit(main())
