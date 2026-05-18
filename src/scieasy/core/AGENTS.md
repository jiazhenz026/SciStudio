---
scope: src/scieasy/core/**
parent_agents_md: ../../../AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42, 43]
---

# Core Instructions

## Identity

`src/scieasy/core/**` owns stable primitive contracts, storage-facing models,
lineage foundations, metadata, units, and versioning surfaces. Core should stay
small, explicit, and conservative.

## Policy

- Root `AGENTS.md` applies first.
- Treat core contracts as frozen unless an accepted ADR/spec explicitly opens
  the change.
- Do not move plugin, frontend, or domain-specific behavior into core for
  convenience.
- Preserve typed models, explicit validation, deterministic behavior, and
  persisted/reference-based data flow.

## Routing

| Trigger | Route | Reference |
|---|---|---|
| Contract or primitive model change | Ask for ADR/spec confirmation | Root policy; ADR-042 |
| Core test work | Skill: `test-author` | ADR-043 §4.4 |
| Core path edit | Rule: `core-contracts.md` | `.claude/rules/core-contracts.md` |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/scieasy/core/**` | public | Public contract code; review compatibility |
| `src/scieasy/core/storage/**` | public | Avoid eager payload loading assumptions |
| `src/scieasy/core/**/__pycache__/**` | generated-code | Do not commit |

## Assessment rubric

| ID | Criterion | Verify with |
|---|---|---|
| CORE1 | Public contracts remain backward compatible or ADR-covered | Diff review |
| CORE2 | Validation behavior is explicit and tested | Focused `pytest tests/core` |
| CORE3 | No domain/plugin/frontend logic entered core | Diff review |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ⚠️ | `src/scieasy/core/**` | Frozen contracts require ADR/spec awareness |
| ✅ | `tests/core/**` | Core tests, when present, may be edited with `test-author` |
| 🚫 | `src/scieasy/core/**/__pycache__/**` | Generated cache output |
