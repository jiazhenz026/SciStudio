---
name: pr-maintainer
description: Maintain PR review readiness and repository traceability.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P1
  dependencies: [workflow-gate, provenance-tagger]
---

# pr-maintainer

Canonical target: `docs/adr/ADR-042.md` §17.1 (temporary).

Planned target: `docs/contributing/workflows/first-pr.md`.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use for PR labeling, readiness checks, duplicate triage, and review-context
handoff without weakening CI or branch protection.

When uncertain, prefer no edit with explanation.
