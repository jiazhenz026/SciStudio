---
name: adr-author
description: Draft or revise SciEasy ADRs, specs, and governance documents. Use when writing architectural decisions, SpecKit-compatible specs, repository rules, or governance text that must align with ADR-042 document structure and AGENTS.md.
---

# ADR Author

Use this skill when the main artifact is an ADR, spec, or governance document.

Start by reading:

- `AGENTS.md`
- `ai_developers/rules/docs-governance.md`
- `ai_developers/rules/gate-workflow.md`
- `docs/adr/ADR-042.md` when changing governance or documentation structure

Rules:

- Identify whether the change needs an ADR, spec, or both.
- Keep the document's responsibility narrow.
- Use `## 1. Decision Summary` for ADRs and governance decisions.
- Use `## 1. Change Summary` for specs, plans, audit reports, and task docs.
- Link governed modules, files, tests, and issues when the schema requires it.
- Do not invent unimplemented enforcement as if it already exists.

Examples:

- "Draft an ADR for plugin boundary rules."
- "Normalize this spec so it follows ADR-042 section expectations."
- "Write a repository rule module for the active gate workflow."

If the document requires code changes, coordinate with `implementation-worker`
after the issue and change plan are clear.
