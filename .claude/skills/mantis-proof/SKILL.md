---
name: mantis-proof
description: Capture reviewable browser proof for UI or behavior changes.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P1
  dependencies: []
---

# mantis-proof

Canonical target: `docs/adr/ADR-042.md` §17.1 (temporary).

Planned target: `docs/contributing/workflows/testing.md`.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use when a change needs human-reviewable proof such as a browser screenshot,
recorded smoke result, or visual regression note.

When uncertain, prefer no edit with explanation.
