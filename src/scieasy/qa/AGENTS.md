---
scope: src/scieasy/qa/**
parent_agents_md: ../../../AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42, 43, 44]
---

# QA Infrastructure Instructions

## Identity

`src/scieasy/qa/**` is the ADR-042/043/044 QA infrastructure surface:
schemas, audits, trackers, workflow checks, and documentation consistency tools.

## Policy

- Root `AGENTS.md` applies first.
- During the cascade, coordinate ownership before touching QA files; other
  agents may own schema/tracker slices in parallel worktrees.
- Do not edit schema/tracker/audit files outside the accepted ADR slice.
- Placeholder QA behavior must carry a tracked `TODO(#1113)` when deferred.

## Routing

| Trigger | Route | Reference |
|---|---|---|
| QA schema/tracker work | Owning cascade slice only | ADR-042/043 |
| Classification lint request | Deferred to QA skeleton/implementation | ADR-043 §6 |
| QA test work | Skill: `test-author` | ADR-043 §4.4 |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/scieasy/qa/**` | internal | Governance tooling; coordinate ownership |
| `src/scieasy/qa/schemas/**` | public | Schema contract; avoid parallel edits |
| `src/scieasy/qa/**/__pycache__/**` | generated-code | Do not commit |

## Assessment rubric

| ID | Criterion | Verify with |
|---|---|---|
| QA1 | Change maps to ADR-042/043/044 cascade scope | Diff and ADR review |
| QA2 | Schema changes include validation tests | Focused `pytest tests/qa` |
| QA3 | Deferred behavior has `TODO(#1113)` | `rg "TODO\\(#1113\\)" src/scieasy/qa tests/qa` |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `src/scieasy/qa/AGENTS.md` | Layered instruction scaffold for this subtree |
| ⚠️ | `src/scieasy/qa/**` | Cascade-owned QA tooling |
| ⚠️ | `tests/qa/**` | QA tests; coordinate with active slices |
| 🚫 | `src/scieasy/qa/**/__pycache__/**` | Generated cache output |
