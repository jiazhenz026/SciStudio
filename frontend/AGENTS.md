---
scope: frontend/**
parent_agents_md: AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [33, 36, 38, 42]
---

# frontend/AGENTS.md — Frontend (React + TypeScript)

## Scope

The Vite + React + TypeScript frontend in `frontend/`. Workflow graph editor, block configuration UI, AI orchestration panels, run viewers. The frontend is the editor; the backend/runtime owns truth (root AGENTS.md §Policy item 1).

## Policy

- **Chrome smoke test is MANDATORY** before any PR touching `frontend/src/**` is reported ready. Unit tests do not catch wiring bugs. See user memory `mandatory_chrome_smoke_test` for context.
- Never call `npm run dev` from a sub-agent context — server survives agent exit and serves stale UI from old worktrees. Use `vitest run` or production-like build for tests.
- No backend logic in frontend. Workflow state, block contracts, execution semantics belong to the runtime, not React state.
- Type-safety: `tsc --noEmit` must be clean. `any` only in escape hatches with `// FIXME(#NNN):` comment.
- React 18+ concurrent rules: no synchronous state updates inside `useEffect` cleanup; no setState in render.
- Lint: `eslint` + `prettier --check`.
- Accessibility: keyboard navigation + ARIA labels on interactive surfaces.

## Routing

| Need | Where |
|---|---|
| Workflow graph editor | `frontend/src/components/graph/**` |
| Block config UI generation | ADR-030 (`config_schema` → form) |
| AI orchestration panels | ADR-035 + `frontend/src/features/ai/**` |
| Run viewer / log streaming | ADR-038 + `frontend/src/features/run/**` |
| Backend API contract | `src/scieasy/api/` + OpenAPI spec |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `frontend/src/**` | public | Free edit per §Paths |
| `frontend/dist/**` | generated-code | Never hand-edit; regenerate via `npm run build` |
| `frontend/node_modules/**` | internal | Never commit |
| `frontend/public/**` | public | Static assets; no large binaries |

## Assessment rubric

In addition to root R1–R11:

| ID | Criterion | Verify with |
|---|---|---|
| R1-fe | Chrome smoke test recorded (live click-through of the touched feature) | Linked Chrome MCP transcript or screenshot |
| R2-fe | `tsc --noEmit` clean | `cd frontend && npx tsc --noEmit` |
| R3-fe | `eslint` + `prettier --check` clean | `cd frontend && npm run lint` |
| R4-fe | `vitest run` passes (no `npm run dev` left running) | `cd frontend && npx vitest run` |
| R5-fe | No new `any` without `// FIXME(#NNN):` comment | `grep -rn ": any" frontend/src/ \| grep -v FIXME` |
| R6-fe | No new bundle dependency added without justification in PR body | `git diff frontend/package.json` |
| R7-fe | Keyboard + screen-reader path verified for interactive surfaces | Visual review |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `frontend/src/**` (non-generated) | Free edit; Chrome smoke test required |
| ✅ | `frontend/tests/**` | Free edit |
| ⚠️ | `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json` | Build config; justify changes |
| ⚠️ | `frontend/src/api/**` (generated from OpenAPI) | Regenerate, do not hand-edit |
| 🚫 | `frontend/dist/**` | Generated build artifacts |
| 🚫 | `frontend/node_modules/**` | Dependency cache |

## Out-of-scope

Per root AGENTS.md `## Out-of-scope format`. UI features deferred to a later phase MUST have a tracking issue and a `// TODO(#NNN):` comment at the wiring site, NOT a silent disabled-state.
