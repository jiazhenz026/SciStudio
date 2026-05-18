#!/usr/bin/env python
"""CLI shim for the honeypot canary integrity check.

Delegates to :func:`scieasy.qa.governance.honeypot.main`.
See ADR-043 §3.6.3 for the authoritative spec.
"""

from __future__ import annotations

import sys

from scieasy.qa.governance.honeypot import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
