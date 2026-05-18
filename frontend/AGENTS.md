---
scope: frontend/**
parent_agents_md: ../AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42, 43]
---

# Frontend Instructions

## Identity

`frontend/**` owns the React/Vite workflow editor/viewer experience. It edits
and visualizes workflow state; backend/runtime layers remain authoritative.

## Policy

- Root `AGENTS.md` applies first.
- Do not encode workflow truth only in frontend state.
- After meaningful frontend changes, run a local smoke check with the in-app
  browser or documented fallback; do not start long-lived services without need.
- Do not edit generated build output.

## Routing

| Trigger | Route | Reference |
|---|---|---|
| UI behavior change | Browser smoke rule | `.claude/rules/frontend-smoke-test.md` |
| Component/test change | Existing frontend test stack | `frontend/package.json` |
| Runtime/API semantics | Backend owner and ADR/spec review | Root policy |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `frontend/src/**` | public | User-facing UI code |
| `frontend/package*.json` | internal | Dependency/governance surface |
| `frontend/dist/**`, `frontend/node_modules/**` | generated-code | Do not edit or commit generated/vendor output |

## Assessment rubric

| ID | Criterion | Verify with |
|---|---|---|
| FE1 | No frontend-only runtime truth was introduced | Diff review |
| FE2 | UI changes are smoke-tested | Browser screenshot or documented fallback |
| FE3 | Tests/lint run when available and scoped | Frontend package scripts |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `frontend/src/**` | Normal UI implementation |
| ⚠️ | `frontend/package*.json`, `frontend/vite.config.ts` | Dependency/build governance |
| 🚫 | `frontend/dist/**`, `frontend/node_modules/**` | Generated/vendor output |
