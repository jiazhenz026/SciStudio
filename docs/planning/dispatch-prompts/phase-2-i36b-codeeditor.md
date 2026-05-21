# Phase 2B — I36b (ADR-036 CodeEditor Monaco component + Save UX)

> Dispatch prompt prepared by manager 2026-05-14.

---

[DISPATCH-TEMPLATE-V1: implement]

You are **Agent I36b — CodeEditor (Monaco) + Save UX** for ADR-036. Sub-issue **#850**, tracking branch **`track/adr-036/code-editor`**, base on merged I36a PR (you depend on the TabState union and the file/lint endpoints).

## STEP 0 — read

1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/implement-agent.md`
3. `docs/adr/ADR-036.md` — focus §3.1, §3.7, §3.9
4. `docs/planning/adr-035-036-checklist.md` — your rows: "Phase 2B — CodeEditor component (I36b)"
5. `frontend/src/components/AIChat/TerminalView.tsx:76-88` — xterm lazy-import pattern (Monaco MUST mirror)
6. `frontend/src/App.tsx:478-487` — auto-save loop pattern to mirror; `:497-556` Ctrl+S handler; `:589-623` Toolbar mount; `:716-763` canvas mount (your kind-switch goes here).
7. `frontend/src/components/Toolbar.tsx:138-365` — current button groups for kind-swap.

## STEP 1 — set up

```
git fetch origin
git checkout -b feat/issue-850/code-editor origin/track/adr-036/code-editor
cd frontend && npm install
cd ..
```
**No `npm run dev`.**

## STEP 2 — scope IN

- `frontend/src/components/CodeEditor.tsx` — full Monaco wrapper. Lazy-imports `@monaco-editor/react` inside `useEffect` (cancellation token, mirror `TerminalView.tsx:76-88`). Props: `tab: FileTab`, `onContentChange(content)`, `onSave()`. Renders Monaco with language detected from `tab.language`. Diagnostics from POST `/api/lint/python` rendered via `monaco.editor.setModelMarkers`. Lint debounce 600 ms idle. Save debounce 800 ms (same as canvas).
- `frontend/src/App.tsx` content-area switch: in the panel currently rendering `<WorkflowCanvas />` (line ~715), branch on `activeTab.kind`. If `"workflow"` → `<WorkflowCanvas />` (existing); if `"file"` → `<CodeEditor tab={activeTab} ... />`. Make sure no workflow-only state reads happen when the tab is a file tab (use the type guard from I36a's exhaustive switch).
- `frontend/src/App.tsx` Ctrl+S handler: when `activeTab.kind === "file"` and dirty, call `saveFileTab(activeTab.id)` from the store; otherwise existing workflow-save path.
- `frontend/src/App.tsx` auto-save loop: extend the existing 800 ms-debounce loop (or add a parallel one) for file tabs — when `tab.kind === "file"` and `tab.dirty`, call `saveFileTab(tab.id)` after 800 ms of no content changes.
- `frontend/src/components/Toolbar.tsx` kind-swap (per ADR-036 §3.7): when `activeTab.kind === "file"` hide Run / Pause / Stop / Reset / Reload / Delete / Note / Group; show only New / Import / Save in the file-tab variant. v1 simplification: hide Find/Format/Goto-line buttons (Monaco built-ins handle Ctrl+F).
- `frontend/src/components/__tests__/CodeEditor.test.tsx` — render Python tab; mock POST `/api/lint/python` response; verify markers set; trigger content change; verify dirty propagates; trigger save (Ctrl+S) and verify PUT called.
- `frontend/src/components/__tests__/Toolbar.test.tsx` (extend or new) — kind-swap test: render with workflow tab, assert Run visible; render with file tab, assert Run hidden + Save visible.

## STEP 3 — scope OUT

- `frontend/src/store/types.ts` / `tabSlice.ts` — I36a's territory (consume only).
- `frontend/src/components/ProjectTree.tsx` — I36c's territory.
- `frontend/src/components/Toolbar.tsx` "View source" button — I36c adds it; you handle the kind-swap structure ONLY (leave a documented insertion point for the View source button).
- "New" menu (workflow / custom block / note) — I36c's territory.
- All backend — I36a/I36c territory.
- AIChat — out of scope.

## STEP 4 — verify

```
cd frontend
npm run build
npx vitest run --reporter=basic
cd ..
ruff format --check . && ruff check .
pytest -q --timeout=60   # ensure backend not broken
```

**Live Chrome smoke required**:
1. Start `scistudio gui --port <free> --no-browser` (background).
2. Chrome MCP navigate.
3. Programmatically open a file tab via the JS console (`window.__store.openFileTab('<some path>')`) — you may need to expose the store on window in dev mode for testing.
4. Verify Monaco renders, lint markers appear, edit + Ctrl+S triggers PUT.
5. Verify Toolbar swap visually.
6. GIF + screenshot.
7. Kill gui + close tab.

## STEP 5 — checklist + commit + PR

Tick Phase 2B rows. Commit, push, PR with `--base track/adr-036/code-editor`. Body `Closes #850` + smoke GIF. Wait CI green.

## STEP 6 — Codex + report

Reconcile. Report PR URL + smoke evidence. Under 500 words.

## NOTE on Toolbar.tsx coordination

You and I36c both touch `frontend/src/components/Toolbar.tsx`. Your changes: kind-swap structure (the conditional rendering wrapper). I36c's changes: ADD the "View source" button + "New" menu options. Dispatcher sequences I36c AFTER your PR merges so I36c rebases on your kind-swap and only adds new buttons. Leave a clearly-marked insertion point in your code (e.g. `{/* TODO(I36c): View source button here */}`).
