---
name: codemod-with-adr
description: Run codemods only when paired with an ADR-backed scope.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P2
  dependencies: [adr-router]
---

# codemod-with-adr

Canonical target: `docs/adr/ADR-042.md` §17.1 (temporary).

Planned target: `docs/contributing/workflows/file-adr-or-spec.md`.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use only for scoped codemods with an accepted ADR/spec and a focused review
plan.

When uncertain, prefer no edit with explanation.
