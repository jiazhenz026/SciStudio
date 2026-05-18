---
description: QA infrastructure edit boundaries
paths:
  - src/scieasy/qa/**
  - tests/qa/**
---

# QA Edits

- Root and `src/scieasy/qa/AGENTS.md` apply first.
- Only touch QA paths assigned to the current ADR-042/043/044 cascade slice.
- Coordinate with parallel agents before touching schemas, trackers, or audit
  tools.
- Every placeholder or deferred QA behavior must carry `TODO(#1113)`.

TODO(#1113): Wire the future classification lint and QA ownership checks after
the ADR-043 §6 schema/audit tools land. Out of scope per ADR-043 §5 /
ADR-044 §11. Followup: #1113.
