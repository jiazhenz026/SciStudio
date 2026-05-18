---
name: session-logs
description: Search local agent session logs for drift root-cause context.
allowed-tools: [Read, Bash]
kind: tool-wrapping
metadata:
  priority: P1
  dependencies: []
---

# session-logs

Canonical target: `docs/adr/ADR-042.md` §17.1 (temporary).

Planned target: `docs/contributing/reference/gate-cli.md` or audit reference.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use only for repository-relevant local session context; do not expose secrets or
private unrelated content.

When uncertain, prefer no edit with explanation.
