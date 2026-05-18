---
name: scieasy-skill-creator
description: Author and validate SciEasy skills (frontmatter + ≤30 body lines).
allowed-tools: [Read, Write, Edit]
kind: bootstrap-meta
priority: P0
pointer: docs/doc-guide/scieasy-skill-creator.md
adr: 42
---

# scieasy-skill-creator skill

For canonical procedure, read: `docs/doc-guide/scieasy-skill-creator.md`

After reading, execute in order:
1. Validate every authored SKILL.md has the required frontmatter (`name`, `description`, `kind`, `pointer`).
2. Confirm the body length ≤ 30 lines (excluding frontmatter) per ADR-044 §11.2.
3. Confirm the `pointer` target exists; for tool-wrapping skills, the pointer must resolve to a real `scieasy.qa.*` module path.
4. Run `python -m scieasy.qa.audit.skill_pointer_sync` once that tool lands (Phase 1D).

When uncertain, prefer no edit with explanation.
