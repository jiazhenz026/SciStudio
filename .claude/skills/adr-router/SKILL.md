---
name: adr-router
description: Decide whether a SciEasy change needs an ADR or spec before code.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P0
  dependencies: []
---

# adr-router

Canonical target: root `AGENTS.md` Policy and `docs/adr/ADR-042.md` §17.1.

Planned target: `docs/contributing/workflows/file-adr-or-spec.md`.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use before code changes that may alter contracts, architecture, storage, APIs,
plugins, runtime semantics, major UI semantics, or AI orchestration.

When uncertain, prefer no edit with explanation.
