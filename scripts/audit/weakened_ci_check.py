#!/usr/bin/env python
"""CLI shim for the weakened-CI automatic block.

Delegates to :func:`scieasy.qa.governance.weakened_ci_check.main`.
See ADR-043 §6.4 for the authoritative spec.
"""

from __future__ import annotations

import sys

from scieasy.qa.governance.weakened_ci_check import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
