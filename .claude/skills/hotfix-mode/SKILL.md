---
name: hotfix-mode
description: Enter SciEasy hotfix mode only after an explicit human request.
allowed-tools: [Read, Bash]
kind: procedural
disable-model-invocation: true
metadata:
  priority: P0
  dependencies: [workflow-gate]
---

# hotfix-mode

Canonical target: `CLAUDE.md` §11.5 (temporary legacy procedure).

Planned target: `docs/contributing/workflows/hotfix.md`.

TODO(#1113): Retarget this skill from `CLAUDE.md` to ADR-044 contributor docs
after those files exist. Out of scope per ADR-043 §5 / ADR-044 §11.
Followup: #1113.

Use only when the user explicitly invokes hotfix mode. Root `AGENTS.md` feature
freeze, architecture boundaries, and no-main-push rules still apply.

When uncertain, prefer no edit with explanation.
