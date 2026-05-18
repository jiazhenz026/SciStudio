#!/usr/bin/env python
"""CLI shim for the §3.5 workflow shadow-list defense (ADR-043).

Delegates to :func:`scieasy.qa.governance.workflow_sync_check.main`.
"""

from __future__ import annotations

import sys

from scieasy.qa.governance.workflow_sync_check import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
