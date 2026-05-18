---
name: agent-manager
description: Coordinate multi-agent SciEasy work with scoped dispatches.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P1
  dependencies: [workflow-gate]
---

# agent-manager

Canonical target: `AGENTS.md` routing plus ADR-044 §6.1 agent-dispatch plan.

Planned target: `docs/contributing/workflows/agent-dispatch.md`.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use only for explicitly multi-agent work. Dispatch prompts must restate scope,
forbidden paths, and required `TODO(#1113)` handling for deferred behavior.

When uncertain, prefer no edit with explanation.
