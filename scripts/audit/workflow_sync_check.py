#!/usr/bin/env python
"""CLI shim for the governance-modification workflow-sync check.

Delegates to :func:`scieasy.qa.governance.workflow_sync_check.main`.
See ADR-043 §3.5 for the authoritative spec.
"""

from __future__ import annotations

import sys

from scieasy.qa.governance.workflow_sync_check import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
