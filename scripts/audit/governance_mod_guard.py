#!/usr/bin/env python
"""Pre-commit hook shim for the LOCAL governance-modification guard.

Delegates to :func:`scieasy.qa.governance.mod_guard.main`. Kept as a
thin script so ``.pre-commit-config.yaml`` can invoke it without
relying on ``python -m`` path resolution (which has been a source of
hook lifecycle bugs across other QA pipelines).

See ADR-043 §3.3 Tool 1 for the authoritative spec.
"""

from __future__ import annotations

import sys

from scieasy.qa.governance.mod_guard import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
