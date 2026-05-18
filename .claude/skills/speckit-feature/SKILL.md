---
name: speckit-feature
description: Route significant feature work through SpecKit before execution.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P1
  dependencies: [workflow-gate]
---

# speckit-feature

Canonical target: `CLAUDE.md` Appendix B and existing `speckit-*` skills.

Planned target: `docs/contributing/workflows/new-feature.md`.

TODO(#1113): Retarget this skill from `CLAUDE.md` to ADR-044 contributor docs
after those files exist. Out of scope per ADR-043 §5 / ADR-044 §11.
Followup: #1113.

Use when a task needs requirements, design decisions, or task decomposition
before gated implementation.

When uncertain, prefer no edit with explanation.
