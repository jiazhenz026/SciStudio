---
name: doc-drift-guard
description: Check documentation drift before doc or public-surface edits.
allowed-tools: [Read, Bash]
kind: tool-wrapping
metadata:
  priority: P0
  dependencies: []
---

# doc-drift-guard

Canonical target: `docs/adr/ADR-042.md` §17.1 (temporary).

Planned target: `docs/contributing/reference/gate-cli.md` or audit module docs.

TODO(#1113): Retarget this tool-wrapping skill after ADR-044 contributor docs
and the audit module documentation exist. Out of scope per ADR-043 §5 /
ADR-044 §11. Followup: #1113.

Use to brief the agent on doc/code drift risk before editing docs or public
surface areas.

When uncertain, prefer no edit with explanation.
