---
name: maintainers-reverse
description: Reverse-lookup owners before editing maintained paths.
allowed-tools: [Read, Bash]
kind: tool-wrapping
metadata:
  priority: P2
  dependencies: []
---

# maintainers-reverse

Canonical target: `docs/adr/ADR-042.md` §17.1 (temporary).

Planned target: `docs/contributing/reference/trailer-conventions.md` or owner
reference docs.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use before editing ownership-sensitive paths so the agent can identify required
reviewers or refuse unscoped edits.

When uncertain, prefer no edit with explanation.
