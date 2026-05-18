#!/usr/bin/env python
"""CI shim for the CI-authoritative governance-modification verifier.

Invoked from ``.github/workflows/governance-modification.yml`` (Phase 1E
Sub-PR 2 deliverable). Delegates to
:func:`scieasy.qa.governance.mod_pr_check.main`.

See ADR-043 §3.3 Tool 2 for the authoritative spec.
"""

from __future__ import annotations

import sys

from scieasy.qa.governance.mod_pr_check import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
