---
name: workflow-gate
description: Follow SciEasy's gated implementation workflow.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P0
  dependencies: []
---

# workflow-gate

Canonical target: `CLAUDE.md` Appendix A (temporary legacy procedure).

Planned target: `docs/contributing/reference/gate-cli.md` and workflow docs.

TODO(#1113): Retarget this skill from `CLAUDE.md` to ADR-044 contributor docs
after those files exist. Out of scope per ADR-043 §5 / ADR-044 §11.
Followup: #1113.

Read root `AGENTS.md` first, then the canonical target. Preserve the active
dispatch scope, branch discipline, tests/docs obligations, and no-main-push
policy.

When uncertain, prefer no edit with explanation.
