# Phase 2C — I36c (ADR-036 ProjectTree + View source + reload + template)

> Dispatch prompt prepared by manager 2026-05-14. **Sequenced AFTER I36b merges.**

---

[DISPATCH-TEMPLATE-V1: implement]

You are **Agent I36c — ProjectTree + View source + reload + template** for ADR-036. Sub-issue **#851**, tracking branch **`track/adr-036/code-editor`**, base on merged I36b PR.

## STEP 0 — read

1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/implement-agent.md`
3. `docs/adr/ADR-036.md` — focus §3.4, §3.5, §3.7, §3.12
4. `docs/planning/adr-035-036-checklist.md` — your rows: "Phase 2C — ProjectTree + View source + reload + template (I36c)"
5. `frontend/src/components/ProjectTree.tsx:206-228` — existing handleDoubleClick + reload_blocks call site.
6. `frontend/src/components/Toolbar.tsx` — I36b's kind-swap is in place; you ADD buttons in the marked insertion points.
7. `src/scistudio/blocks/registry.py` — `BlockRegistry.hot_reload()`. Call only; do NOT modify.
8. `src/scistudio/api/routes/blocks.py` — existing block routes; you extend with template endpoint.

## STEP 1 — set up

```
git fetch origin
git checkout -b feat/issue-851/project-tree origin/track/adr-036/code-editor
cd frontend && npm install
cd ..
```
**No `pip install -e .` from worktree. No `npm run dev`.**

## STEP 2 — scope IN

**Frontend:**
- `frontend/src/components/ProjectTree.tsx` — extend `handleDoubleClick` so `.py / .txt / .md / .json / .csv` files (anywhere under the project) call `openFileTab(path)`. Existing `.yaml` → `onLoadWorkflow` and `blocks/*.py` → `onReloadBlocks` paths preserved.
- `frontend/src/components/Toolbar.tsx` "View source" button: visible ONLY when `activeTab.kind === "workflow"`. Click → `openFileTab("workflows/<workflowId>.yaml", {readOnly: true})` with id prefix `source:` for dedup. Re-clicking focuses existing tab.
- `frontend/src/components/Toolbar.tsx` "New" menu: split the existing New button into a dropdown with three options (per ADR-036 §3.7, §3.12): "New workflow" (existing behavior), "New custom block" (prompts for filename, POST scaffolds via template endpoint, opens in editor tab), "New note" (prompts for filename, creates empty `.md` under `notes/` or project root, opens in editor tab).
- `frontend/src/components/__tests__/ProjectTree.test.tsx` — double-click on `.py / .md / .json / .csv` triggers openFileTab.
- `frontend/src/components/__tests__/Toolbar.test.tsx` (extend) — View source dedup test, "New" menu actions.

**Backend:**
- `src/scistudio/api/routes/blocks.py` — implement `GET /api/blocks/template?kind=basic` returning `{content: <block_base_template.py contents>}`.
- `src/scistudio/blocks/_templates/block_base_template.py` — fill in the actual template content per ADR-036 §3.12: imports `from scistudio.blocks.base import Block, BlockSpec, PortSpec`; docstring with config_schema example + how to reference `inputs[port_name]` in `run`; class skeleton with `run()` body `raise NotImplementedError("...")` and `# >>> EDIT THIS <<<` marker comment. Must be syntactically valid Python (so `python -c "import ast; ast.parse(open('...').read())"` passes).
- `src/scistudio/api/routes/projects.py` PUT hook for reload-on-lint-pass: when the saved file path is under `<project>/blocks/` AND ends `.py` AND lint diagnostics on the new content are empty, call `BlockRegistry.hot_reload()`. Implementation: re-use lint logic from I36a's lint endpoint internally. Emit a WS event `blocks.reloaded` with `{added, removed, reloaded}` so frontend toasts.
- `tests/api/test_blocks_template.py` — endpoint returns 200 with valid Python; smoke that the served content parses with `ast.parse`.
- `tests/api/test_reload_on_save.py` — PUT a clean `.py` under `blocks/` → reload fires, blocks event emitted; PUT a syntactically broken `.py` → reload does NOT fire.

## STEP 3 — scope OUT

- `frontend/src/components/CodeEditor.tsx` — I36b territory.
- `frontend/src/store/types.ts`, `tabSlice.ts` — I36a territory (consume only).
- `frontend/src/App.tsx` content swap or auto-save — I36b territory (consume only).
- AIChat / WorkflowCanvas — out of scope.
- `src/scistudio/blocks/registry.py` — call `hot_reload()` only; do NOT modify.
- `src/scistudio/core/`, `blocks/base/`, `engine/runners/`, `engine/events.py` — frozen.

## STEP 4 — verify

```
ruff format --check . || (ruff format . && git add -u)
ruff check .
pytest tests/api -q --timeout=60
pytest -q --timeout=60
mypy src/scistudio/api/ --ignore-missing-imports
cd frontend
npm run build
npx vitest run --reporter=basic
cd ..
```

**Live Chrome smoke required**:
1. Start `scistudio gui` background.
2. Chrome MCP navigate.
3. Verify ProjectTree double-click on a `.py` opens editor tab.
4. Verify "New" menu shows three items; create-block scaffolds the template.
5. Verify View source on a workflow opens readonly Monaco; re-click dedups.
6. Modify a `blocks/*.py`, save → verify palette updates (or toast).
7. GIF + screenshots.

## STEP 5 — checklist + commit + PR

Tick Phase 2C rows. Commit, push, PR with `--base track/adr-036/code-editor`. Body `Closes #851`. Wait CI green.

## STEP 6 — Codex + report

Reconcile. Report PR URL + smoke evidence + confirmation no Toolbar collision with I36b's diff. Under 500 words.
