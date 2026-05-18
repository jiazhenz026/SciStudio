---
name: doc-drift-guard
description: Run §9 doc-drift classifier; brief agent on current debt before editing.
allowed-tools: [Read, Bash]
kind: tool-wrapping
priority: P0
pointer: scieasy.qa.audit.doc_drift
adr: 42
---

# doc-drift-guard skill

For canonical behaviour, read the module docstring of `scieasy.qa.audit.doc_drift`.

After reading, execute in order:
1. `python -m scieasy.qa.audit.doc_drift --format summary` to view current findings.
2. If editing a doc cited by a `b/c1/c2/c3` finding, read the finding's `evidence_paths` first.
3. Apply the §8 status-driven arbitration rule based on the cited ADR's `status` frontmatter.

When uncertain, prefer no edit with explanation.
