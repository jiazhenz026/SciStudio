---
name: test-author
description: Write meaningful tests that assert observable behavior.
allowed-tools: [Read, Write, Edit, Bash]
kind: procedural
metadata:
  priority: P0
  dependencies: []
---

# test-author

Canonical target: `docs/adr/ADR-043.md` §4.4.

Planned target: `docs/contributing/workflows/testing.md`.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Before writing tests, identify the observable contract, write the assertion
first, confirm the test fails for the expected reason, then implement the
minimum passing behavior.

When uncertain, prefer no edit with explanation.
