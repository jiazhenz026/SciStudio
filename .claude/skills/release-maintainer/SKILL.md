---
name: release-maintainer
description: Prepare a SciEasy release slice with changelog and tag discipline.
allowed-tools: [Read, Bash]
kind: procedural
metadata:
  priority: P1
  dependencies: [provenance-tagger]
---

# release-maintainer

Canonical target: `docs/adr/ADR-042.md` §17.1 (temporary).

Planned target: `docs/contributing/workflows/new-feature.md` or release docs.

TODO(#1113): Retarget this skill to ADR-044 contributor docs after those files
exist. Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.

Use for version bump, changelog slice, tag discipline, and release handoff when
the release task is explicitly scoped.

When uncertain, prefer no edit with explanation.
