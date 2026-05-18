#!/usr/bin/env python
"""CLI shim for the dynamic governance-path filter.

Delegates to :func:`scieasy.qa.governance.path_filter.main`.
See ADR-043 §3.5 for the authoritative spec.
"""

from __future__ import annotations

import sys

from scieasy.qa.governance.path_filter import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
