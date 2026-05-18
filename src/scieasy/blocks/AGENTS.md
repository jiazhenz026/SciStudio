---
scope: src/scieasy/blocks/**
parent_agents_md: ../../../AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42, 43]
---

# Block Instructions

## Identity

`src/scieasy/blocks/**` owns block implementations and registry-facing block
contracts. Blocks connect workflows to code, external apps, IO, processing, and
subworkflows without making the frontend the source of truth.

## Policy

- Root `AGENTS.md` applies first.
- Preserve block I/O contracts and validation surfaces.
- Manual GUI review remains an `AppBlock` file-exchange pattern, not a new
  informal block class.
- Keep category/subcategory behavior aligned with block development docs and
  accepted ADRs.

## Routing

| Trigger | Route | Reference |
|---|---|---|
| Generic block behavior | Block contract docs | `docs/block-development/block-contract.md` |
| AI block behavior | Nested instructions | `src/scieasy/blocks/ai/AGENTS.md` |
| Block tests | Skill: `test-author` | ADR-043 §4.4 |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/scieasy/blocks/**` | public | Public runtime behavior; test observable contracts |
| `src/scieasy/blocks/_templates/**` | internal | Templates; preserve provenance |
| `src/scieasy/blocks/**/__pycache__/**` | generated-code | Do not commit |

## Assessment rubric

| ID | Criterion | Verify with |
|---|---|---|
| BLK1 | Block inputs/outputs remain schema-valid | Focused block tests |
| BLK2 | Runtime truth stays backend-owned | Diff review |
| BLK3 | AppBlock/manual-review changes preserve file exchange | Contract review |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `src/scieasy/blocks/**` except `src/scieasy/blocks/ai/**` | Normal block implementation |
| ⚠️ | `src/scieasy/blocks/ai/**` | AI orchestration constraints |
| 🚫 | `src/scieasy/blocks/**/__pycache__/**` | Generated cache output |
