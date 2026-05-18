---
scope: docs/**
parent_agents_md: ../AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42, 43, 44]
---

# Documentation Instructions

## Identity

`docs/**` owns ADRs, specs, architecture notes, audits, planning records, and
user/developer documentation. Docs are product and governance surfaces.

## Policy

- Root `AGENTS.md` applies first.
- ADR edits require scope confirmation and preserve amendment/frontmatter rules.
- Do not create the full ADR-044 `docs/contributing/**` set until that slice is
  assigned.
- Treat audit logs as append-only or session-owned unless an ADR says otherwise.

## Routing

| Trigger | Route | Reference |
|---|---|---|
| ADR edit | Rule: `adr-edits.md` | ADR-042 §27; ADR-043 |
| Contributor doc gap | Defer to ADR-044 slice | ADR-044 §6 |
| Changelog edit | Rule: `changelog-format.md` | Root policy |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `docs/adr/**`, `docs/specs/**`, `docs/architecture/**` | public | Governance/public design surface |
| `docs/audit/**` | internal | Append-only/session-owned records |
| `docs/identity/humans.yml` | user-data | Do not auto-edit |

## Assessment rubric

| ID | Criterion | Verify with |
|---|---|---|
| DOC1 | ADR/spec references match accepted scope | Diff review |
| DOC2 | New docs avoid duplicating canonical workflow text | Pointer review |
| DOC3 | Audit files are append-only/session-owned | `git diff -- docs/audit` |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `docs/specs/**`, normal planning docs | Scoped documentation work |
| ⚠️ | `docs/adr/**`, `docs/architecture/**`, `docs/audit/**` | Governance and audit sensitivity |
| 🚫 | `docs/identity/humans.yml`, generated docs | Identity or generated surfaces |
