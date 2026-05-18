#!/usr/bin/env python
"""CLI shim for the monotonic-strengthening check.

Delegates to :func:`scieasy.qa.governance.monotonic_check.main`.
See ADR-043 §3.4 for the authoritative spec.
"""

from __future__ import annotations

import sys

from scieasy.qa.governance.monotonic_check import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
