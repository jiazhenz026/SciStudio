# Phase 2A — I36a (ADR-036 TabState union + backend file/lint)

> Dispatch prompt prepared by manager 2026-05-14.

---

[DISPATCH-TEMPLATE-V1: implement]

You are **Agent I36a — TabState union + backend file/lint** for ADR-036. Sub-issue **#849**, tracking branch **`track/adr-036/code-editor`**, base on merged skeleton PR #<SKELETON-PR>.

## STEP 0 — read

1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/implement-agent.md`
3. `docs/adr/ADR-036.md` — focus §3.2, §3.3, §3.10, §3.11
4. `docs/planning/adr-035-036-checklist.md` — your rows: "Phase 2A — TabState union + backend file/lint (I36a)"
5. `frontend/src/store/types.ts:168-181`, `frontend/src/store/tabSlice.ts:8-183`, `frontend/src/store/index.ts:1-66` — current TabState shape, slice actions, persist middleware whitelist.
6. `src/scistudio/api/routes/filesystem.py:47-65` — `_resolve_safe_path` to reuse.
7. `src/scistudio/api/routes/projects.py:13-88` — project route pattern to extend.
8. `src/scistudio/api/routes/workflow_watcher.py:146-167, 415` — `mark_self_write` + dedup deque.

## STEP 1 — set up

```
git fetch origin
git checkout -b feat/issue-849/tabstate-and-backend origin/track/adr-036/code-editor
python -c "import scistudio; print(scistudio.__file__)"
cd frontend && npm install   # picks up @monaco-editor/react added in skeleton
cd ..
```
**No `pip install -e .` from worktree.** **No `npm run dev`.**

## STEP 2 — scope IN

**Frontend (TabState + store):**
- `frontend/src/store/types.ts` — finalize `WorkflowTab` + `FileTab` discriminated union (skeleton from S36 already added the types — fill in any TODOs).
- `frontend/src/store/tabSlice.ts` — implement `openFileTab(filePath, opts?: {readOnly?: boolean})`, `saveFileTab(id)`, `updateFileTabContent(id, content)`. `openFileTab` dedups by id (`file:<path>` or `source:<path>`) and fetches content from new GET endpoint. `saveFileTab` POSTs to PUT endpoint. Both update store state with mtime tracking.
- `frontend/src/store/index.ts` — extend persist whitelist for FileTab metadata (per ADR-036 §3.11): `{kind, id, filePath, displayName, language, readOnly}` ONLY; never persist `content` (re-fetched on rehydrate). On rehydrate, file tabs start in "loading" state.
- Migrate ALL `TabState` consumers to type-guard on `tab.kind === "workflow"`. Hot spots: `App.tsx` (every read of `workflowName`/`workflowDirty`/etc.), `TabBar.tsx`, anywhere the captureTab/restoreTab functions read workflow-only fields. Use TypeScript exhaustiveness check (`switch (tab.kind)` with `default: const _: never = tab`) to ensure no consumer site is missed.

**Backend (file + lint endpoints):**
- `src/scistudio/api/routes/projects.py` — implement `GET /api/projects/{project_id}/file?path=<rel>` → `{content, mtime, size, encoding}` and `PUT /api/projects/{project_id}/file?path=<rel>` body `{content}` → `{mtime, size}`. Allowlist: `.py .txt .md .yaml .yml .json .csv .log`. Cap: 10 MB. Use `_resolve_safe_path` for path traversal protection. Atomic write (tempfile + os.replace) for PUT. Before write, call `mark_self_write(absolute_path, mtime, size)` to suppress watcher echo.
- `src/scistudio/api/routes/lint.py` — implement `POST /api/lint/python` body `{content, filename}` → `{diagnostics: [{line, column, end_line, end_column, code, severity, message}]}`. Shell `ruff check --stdin-filename=<filename> --output-format=json --quiet -` with `content` on stdin. Parse Ruff JSON to the diagnostics shape. If ruff binary missing → return `{diagnostics: [], note: "ruff unavailable"}` + WARN log (per ADR-036 §6 Risks).
- `src/scistudio/api/__init__.py` (or wherever routers are mounted) — register the new `lint` router.

**Tests:**
- `tests/api/test_file_endpoints.py` — path traversal (try `../etc/passwd` etc., expect 403), allowlist (try `.exe`, expect 415), size cap (10 MB + 1, expect 413), atomic write semantics, mark_self_write integration (no echo).
- `tests/api/test_lint_endpoint.py` — well-formed Python (no diagnostics), syntax error (1 diagnostic), missing-ruff fallback (monkeypatch `shutil.which` returning None).
- `frontend/src/store/__tests__/tabState.test.ts` — discriminated union exhaustiveness, openFileTab dedup, persistence whitelist (ensures `content` isn't persisted).

## STEP 3 — scope OUT

- `frontend/src/components/CodeEditor.tsx` — I36b's territory.
- `frontend/src/components/Toolbar.tsx`, `App.tsx` content swap, Ctrl+S handler — I36b's territory (you only update consumers' type guards in App.tsx, not the canvas/toolbar swap logic).
- `frontend/src/components/ProjectTree.tsx` real handlers, View source button, reload-blocks gate, block template route — I36c's territory.
- AIChat / TerminalTab / WorkflowCanvas — entirely out of scope (ADR-035 territory or unaffected by ADR-036).
- `src/scistudio/core/`, `blocks/base/`, `blocks/registry.py`, `engine/runners/`, `engine/events.py` — frozen.

## STEP 4 — verify

```
ruff format --check . || (ruff format . && git add -u)
ruff check .
pytest tests/api -q --timeout=60
pytest -q --timeout=60
mypy src/scistudio/api/ --ignore-missing-imports
cd frontend
npm run build  # type errors from incomplete consumer migration block this
npx vitest run --reporter=basic
cd ..
```

## STEP 5 — checklist + commit + PR

Tick checklist Phase 2A rows. Commit, push, PR with `--base track/adr-036/code-editor`. Body `Closes #849`. Wait CI green.

## STEP 6 — Codex + report

Reconcile Codex. Report back with PR URL + summary. Under 500 words.
