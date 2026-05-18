#!/usr/bin/env python
"""CLI shim for the §3.5 dynamic governance-path filter (ADR-043).

Delegates to :func:`scieasy.qa.governance.path_filter.main`.
"""

from __future__ import annotations

import sys

from scieasy.qa.governance.path_filter import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
