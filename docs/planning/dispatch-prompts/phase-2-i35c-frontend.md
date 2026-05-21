# Phase 2C — I35c (ADR-035 Frontend block-tab integration)

> Dispatch prompt prepared by manager 2026-05-14.

---

[DISPATCH-TEMPLATE-V1: implement]

You are **Agent I35c — Frontend block-tab integration** for ADR-035. Sub-issue **#847**, tracking branch **`track/adr-035/ai-block-pty`**, base on merged skeleton PR #<SKELETON-PR>.

## STEP 0 — read

1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/implement-agent.md`
3. `docs/adr/ADR-035.md` — focus §3.9, §3.10
4. `docs/planning/adr-035-036-checklist.md` — your rows: "Phase 2C — Frontend tab integration (I35c)"
5. `frontend/src/components/AIChat/TerminalTabs.tsx`, `TerminalTab.tsx`, `TerminalView.tsx` — read first to understand the current contract (skeleton stubs from S35 are already in place).
6. `frontend/src/hooks/useWebSocket.ts:20-119` — current WS message dispatch.

## STEP 1 — set up

```
git fetch origin
git checkout -b feat/issue-847/frontend-tabs origin/track/adr-035/ai-block-pty
cd frontend && npm ci 2>&1 || npm install
```
**No `npm run dev`.** Use `vitest run` and `npm run build` only.

## STEP 2 — scope IN

- `frontend/src/components/AIChat/TerminalTabs.tsx` — handle `block_pty_opened` event from useWebSocket: auto-create a tab with `source: "ai-block"`, switch focus, set initial title to `🤖 ${blockName}`. Tab is identified by `block_run_id` (carry it on the tab state).
- `frontend/src/components/AIChat/TerminalTab.tsx` — render title with status badge: spinner while PAUSED (in-progress), ✓ on DONE, ✗ on ERROR. Add "Mark done" button visible ONLY when `tab.source === "ai-block"` AND block state is PAUSED. Clicking sends a WS message `block_user_marked_done` with `{block_run_id}`. Tab survives DONE/ERROR — closing while running prompts confirm + emits cancel WS message.
- `frontend/src/hooks/useWebSocket.ts` — add `block_pty_opened` and `block_pty_closed` switch cases. The `block_pty_opened` payload includes `{block_run_id, tab_id, block_name, status}`; dispatch to TerminalTabs to auto-create. The `block_pty_closed` payload includes `{block_run_id, status}` ('done'|'error'|'cancelled'); dispatch to update the tab's status badge.
- `frontend/src/components/AIChat/__tests__/TerminalTabs.test.tsx` — extend with tests for block-PTY-opened auto-create + focus, status badge variants, Mark-done button visibility, close-while-running confirm.
- `frontend/src/components/AIChat/__tests__/TerminalTab.test.tsx` — RTL tests for status badge rendering + Mark-done click.

## STEP 3 — scope OUT

- `frontend/src/store/types.ts` — that's ADR-036 territory. Do NOT touch the `TabState` type. Carry block-tab state inside the existing `terminalTabs` slice with new optional fields (`source?: "user" | "ai-block"`, `blockRunId?: string`, `blockStatus?: "running" | "paused" | "done" | "error" | "cancelled"`). Note `cancelled` MUST be in the union — terminal state when the user closes the tab while running OR when the workflow cancels mid-block (per ADR-035 §3.9).
- App-level Toolbar / Canvas / WorkflowCanvas — out of scope.
- `frontend/src/components/AIChat/TerminalView.tsx` — already handles xterm rendering; do NOT modify the xterm logic. You may add an optional `extraToolbar` prop slot for the Mark-done button if needed, but keep changes minimal.
- All backend files — those are I35a/I35b's territories.

## STEP 4 — verify

```
ruff format --check . 2>&1; ruff check . 2>&1   # mostly N/A but should be clean
cd frontend
npm run build
npx vitest run --reporter=basic
cd ..
pytest -q --timeout=60   # ensure backend tests not broken by store/types changes (you didn't touch them)
```

**Live Chrome smoke required** (per `feedback_mandatory_chrome_smoke_test`). Use `mcp__claude-in-chrome__*`:
1. Start `scistudio gui --port <free> --no-browser` (background).
2. Navigate Chrome to `http://127.0.0.1:<port>/`.
3. Manually open the AIChat panel (existing UI).
4. Simulate a `block_pty_opened` WS message via the JS console (or by spawning a test workflow with AIBlock that uses I35a + I35b's wiring, if those have landed).
5. Verify tab opens, status badge renders, Mark-done button visible only when expected, close-while-running prompts confirm.
6. Take a GIF via `mcp__claude-in-chrome__gif_creator` and link in PR body.
7. Kill the gui process and close the Chrome tab.

## STEP 5 — checklist + commit + PR

Tick rows in checklist Phase 2C. Commit, push, PR with `--base track/adr-035/ai-block-pty`. Body `Closes #847` + screenshots/GIF. Wait CI green.

## STEP 6 — Codex + report

Reconcile every Codex comment. Report PR URL + smoke evidence summary. Under 500 words.
