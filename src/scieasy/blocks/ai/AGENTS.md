---
scope: src/scieasy/blocks/ai/**
parent_agents_md: ../../../../AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [35, 42, 43]
---

# AI Block Instructions

## Identity

`src/scieasy/blocks/ai/**` owns AI block orchestration, provider boundaries,
prompt/completion plumbing, run directories, and parsing surfaces.

## Policy

- Root and parent block instructions apply first.
- AI may propose work, but runtime contracts, schemas, lineage, and execution
  policy validate and execute it.
- Do not add hidden provider behavior, implicit tool access, or frontend-owned
  execution truth.

## Routing

| Trigger | Route | Reference |
|---|---|---|
| AI block contract change | ADR/spec review | ADR-035; ADR-042 |
| Parser/provider edit | Focused regression tests | `test-author` |
| Prompt or orchestration drift | Ask for scope confirmation | Root policy |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `src/scieasy/blocks/ai/**` | public | Runtime behavior; avoid secret capture |
| `src/scieasy/blocks/ai/run_dir.py` | public | Artifact-path behavior; preserve lineage |
| Prompt/provider examples | internal | Do not include live secrets or private data |

## Assessment rubric

| ID | Criterion | Verify with |
|---|---|---|
| AI1 | Runtime validation remains authoritative | Diff review |
| AI2 | Provider changes avoid secret logging | Focused tests/review |
| AI3 | Parser behavior has observable assertions | Focused `pytest` |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ⚠️ | `src/scieasy/blocks/ai/**` | AI execution policy and ADR-035 constraints |
| ✅ | `tests/**/ai/**` | AI tests, when present, may be edited with `test-author` |
| 🚫 | Credential, token, or live-provider dumps | Secret material |
