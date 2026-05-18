---
name: dispatch-agents
description: Wrap agent-manager with SciEasy cascade dispatch defaults.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P1
  dependencies: [agent-manager]
---

# dispatch-agents

Canonical target: `AGENTS.md` routing plus ADR-044 §6.1 agent-dispatch plan.

Planned target: `docs/contributing/workflows/agent-dispatch.md`.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use SciEasy defaults: one branch per task, no main push, explicit forbidden
paths, and tracked TODOs for deferred behavior.

When uncertain, prefer no edit with explanation.
