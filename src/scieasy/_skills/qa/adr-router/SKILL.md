---
name: adr-router
description: Refuse code change without an Accepted ADR reference.
allowed-tools: [Read, Bash]
kind: procedural
priority: P0
pointer: docs/contributing/workflows/adr-router.md
adr: 42
---

# adr-router skill

For canonical procedure, read: `docs/contributing/workflows/adr-router.md`

After reading, execute in order:
1. Identify the ADR(s) that govern the symbol(s) being edited (consult `governs.contracts` / `governs.modules` frontmatter).
2. If no Accepted ADR is found, STOP and open a new ADR via the standard process (CLAUDE.md §5.3).
3. Cite the ADR in the commit trailer: `ADR: 42` (per ADR-042 §13.1).
4. Verify the cited ADR's status is `Accepted` per §8.2 arbitration.

When uncertain, prefer no edit with explanation.
