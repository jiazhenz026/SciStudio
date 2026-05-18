---
name: provenance-tagger
description: Ensure agent-authored commits carry required provenance trailers.
allowed-tools: [Read, Bash]
kind: tool-wrapping
metadata:
  priority: P0
  dependencies: []
---

# provenance-tagger

Canonical target: `docs/adr/ADR-042.md` §13 and §17.1 (temporary).

Planned target: `docs/contributing/reference/trailer-conventions.md`.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use before committing agent-authored work so attribution, ADR, and bug-fix
trailers are not silently omitted.

When uncertain, prefer no edit with explanation.
