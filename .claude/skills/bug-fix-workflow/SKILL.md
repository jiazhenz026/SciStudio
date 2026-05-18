---
name: bug-fix-workflow
description: Triage and resolve a SciEasy bug or audit finding.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P0
  dependencies: [workflow-gate, test-author]
---

# bug-fix-workflow

Canonical target: `CLAUDE.md` Appendix C (temporary legacy procedure).

Planned target: `docs/contributing/workflows/bug-fix.md`.

TODO(#1113): Retarget this skill from `CLAUDE.md` to ADR-044 contributor docs
after those files exist. Out of scope per ADR-043 §5 / ADR-044 §11.
Followup: #1113.

Read root `AGENTS.md`, then classify the issue as bug, design-choice bug,
contract behavior change, or new feature before editing.

When uncertain, prefer no edit with explanation.
