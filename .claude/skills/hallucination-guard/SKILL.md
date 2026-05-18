---
name: hallucination-guard
description: Verify referenced symbols, imports, files, and URLs exist.
allowed-tools: [Read, Bash]
kind: tool-wrapping
metadata:
  priority: P2
  dependencies: []
---

# hallucination-guard

Canonical target: `docs/adr/ADR-042.md` §17.1 (temporary).

Planned target: `docs/contributing/workflows/testing.md` or audit reference.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use before citing symbols, imports, files, URLs, tools, or generated facts that
may not exist in the current repository.

When uncertain, prefer no edit with explanation.
