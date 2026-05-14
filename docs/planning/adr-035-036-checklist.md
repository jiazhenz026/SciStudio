# ADR-035 + ADR-036 Implementation Checklist

> **Mandatory tracking doc.** Every agent edits the rows it owns and only those rows.
> Drift = protocol violation. The dispatcher (Claude as agent manager) sweeps after every phase.

## Conventions
- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- "Owner" is the issue / agent role responsible for that row
- Each row references the relevant ADR section in `[brackets]`
- When you tick a box, also append a one-line note: `→ <PR-or-commit-link>` or `→ <test-name passes>`

---

## ADR-035 — AI Block on PTY (track/adr-035/ai-block-pty)

### Skeleton (Owner: S35)
- [x] `src/scieasy/blocks/ai/ai_block.py` rewrite stub: `AIBlock(Block)` with `execution_mode=EXTERNAL`, `variadic_inputs/outputs=True`; all methods `raise NotImplementedError` with detailed implementation comments [§3.1] → PR #844-skeleton (sha pending commit)
- [x] `src/scieasy/blocks/ai/run_dir.py` new module: `RunDir` class signature + per-run `.scieasy/ai-block-runs/{run_id}/` layout doc + manifest.json schema [§3.2, §3.4] → PR #844-skeleton
- [x] `src/scieasy/blocks/ai/completion.py` new module: three completion paths sketched (MCP / FileWatcher / button) [§3.5] → PR #844-skeleton
- [x] `src/scieasy/ai/agent/mcp/tools_workflow.py` add `finish_ai_block` ToolEntry stub returning `not_in_ai_block_context` envelope [§3.5] → PR #844-skeleton (registry now exposes 26 tools)
- [x] `src/scieasy/engine/pty_control.py` new module: `request_pty_tab()` + `notify_block_pty_event()` IPC helpers stubbed [§3.10] → PR #844-skeleton
- [x] `src/scieasy/api/routes/ai_pty.py` add engine-initiated tab-open route stub (sibling to user-launched WS route — **do not modify** the existing route) [§3.10] → PR #844-skeleton (`open_engine_initiated_tab` added; lines 1-318 of existing route untouched)
- [x] `frontend/src/components/AIChat/TerminalTabs.tsx` accept engine-initiated open events stub [§3.10] → PR #844-skeleton (`handleBlockPtyOpened` / `handleBlockPtyClosed` exports)
- [x] `frontend/src/components/AIChat/TerminalTab.tsx` props extended for status badge + Mark-done button stubs [§3.9] → PR #844-skeleton (`AiBlockStatusBadge` / `MarkDoneButton` component stubs)
- [x] `frontend/src/hooks/useWebSocket.ts` `block_pty_opened` / `block_pty_closed` switch-case stubs [§3.10] → PR #844-skeleton
- [x] Test stubs created with detailed test plan comments → PR #844-skeleton (5 test files: `test_ai_block_skeleton.py`, `test_run_dir_skeleton.py`, `test_completion_skeleton.py`, `test_finish_ai_block_skeleton.py`, `test_pty_control_skeleton.py`, `TerminalTabs.skeleton.test.tsx`)

### Phase 2A — Backend block runtime (Owner: I35a)
- [x] `AIBlock.run()` real implementation: writes manifest, requests PTY tab, enters PAUSED, awaits completion signal → `src/scieasy/blocks/ai/ai_block.py::AIBlock.run`
- [x] Manifest writer (path, type_chain, inputs, outputs, deadline) [§3.4] → `src/scieasy/blocks/ai/run_dir.py::RunDir.write_manifest`
- [x] Output validation via existing IOBlock loaders [§3.6] → `AIBlock._validate_and_load_outputs` (dispatches to `LoadData`)
- [x] State transitions IDLE→READY→RUNNING→PAUSED→DONE / ERROR / CANCELLED [§3.9] → `AIBlock._safe_transition` calls in `run()`
- [x] StubAgent fixture for tests (does not spawn claude; simulates `finish_ai_block` call) → `tests/blocks/ai/conftest.py::StubAgent`
- [x] Unit tests: manifest contents, completion-signal precedence, validation failures, all three completion paths → 55 tests in `tests/blocks/ai/test_{ai_block,run_dir,completion}_skeleton.py` (skeleton xfails flipped green)

### Phase 2B — Engine PTY control + MCP (Owner: I35b)
- [x] `engine.request_pty_tab()` IPC: worker → engine sends spec, engine returns tab_id [§3.10] → src/scieasy/engine/pty_control.py (HTTP loopback + in-process test seam)
- [x] `engine.notify_block_pty_event()` IPC: completion / cancellation events [§3.10] → src/scieasy/engine/pty_control.py
- [x] `finish_ai_block` MCP tool real implementation: validates outputs dict, raises if not in AI Block context, writes signal file under `run_dir/` → src/scieasy/ai/agent/mcp/tools_workflow.py::finish_ai_block
- [x] Engine-side route handler that allocates tab via existing `terminal.spawn_claude/codex` builder → src/scieasy/api/routes/ai_pty.py::open_engine_initiated_tab + POST /api/ai/pty/internal/request-tab
- [x] WS broadcast `block_pty_opened` to frontend → register/unregister_ai_pty_subscriber in ai_pty.py + minimal subscribe hook in api/ws.py (no new EngineEvent type)
- [x] Permission mode passthrough (safe / bypass) per block config [§3.7] → spawn_argv translates to dangerous=True/False inside open_engine_initiated_tab
- [x] Tests: IPC roundtrip with mock engine, finish_ai_block error envelope shapes, multi-call rejection → tests/engine/test_pty_control.py (17), tests/ai/test_finish_ai_block.py (17), tests/api/test_ai_pty_engine_spawn.py (20)

### Phase 2C — Frontend tab integration (Owner: I35c)
- [x] `TerminalTabs.tsx` handles `block_pty_opened` event → auto-creates tab, switches focus → `frontend/src/components/AIChat/blockPtyHandlers.ts::handleBlockPtyOpened`
- [x] `TerminalTab.tsx` renders title with 🤖 prefix + block name + status badge (✓ / ✗ / spinner) → `TerminalTab.tsx::AiBlockStatusBadge` (lines 45-105)
- [x] "Mark done" button visible when `tab.source === "ai-block"` and block is PAUSED → `TerminalTab.tsx::MarkDoneButton` (lines 121-144)
- [x] Tab close while AI Block running → confirmation modal → emit cancel → `TerminalTabs.tsx::ConfirmDialog` (lines 30-67) + `pendingClose` flow
- [x] Tab survives DONE/ERROR (per ADR-035 §3.9) → render path always mounts `TerminalView` regardless of `blockStatus`
- [x] Vitest tests for new tab-source path; RTL render of status badge variants → `__tests__/TerminalTab.test.tsx` (15 tests) + `TerminalTabs.test.tsx` (19 tests)

### Audit & Fix (skeleton)
- [x] Audit-skeleton report posted on umbrella issue (Owner: A35-skeleton) → `docs/audit/2026-05-14-adr-035-skeleton.md` (PR #858)
- [ ] All P1 findings fixed (or explicitly justified deferral) (Owner: F35-skeleton, conditional)

### Audit & Fix (implementation)
- [x] Audit-implementation report posted on umbrella issue, includes Chrome smoke results (Owner: A35-impl) → `docs/audit/2026-05-14-1253-adr-035-implementation.md` (5 P1 + 1 P2 + 1 drift)
- [x] All P1 findings fixed; deferred Codex P1 explicitly overridden (Owner: F35-impl) → fix PR `fix/adr-035-impl-audit-p1` (5 P1 + 1 P2 addressed in-PR per `audit_p1_override`)

---

## ADR-036 — Embedded code editor (track/adr-036/code-editor)

### Skeleton (Owner: S36)
- [x] `frontend/src/store/types.ts` — `WorkflowTab` + `FileTab` discriminated union scaffolding (no consumer migration yet — types only) [§3.10] → branch `feat/issue-848/skeleton`
- [x] `frontend/src/store/tabSlice.ts` — `openFileTab()` / `saveFileTab()` / `updateFileTabContent()` action stubs [§3.10] → branch `feat/issue-848/skeleton`
- [x] `src/scieasy/api/routes/projects.py` — file GET/PUT route stubs returning 501 with implementation-plan docstrings [§3.2] → branch `feat/issue-848/skeleton`
- [x] `src/scieasy/api/routes/lint.py` new module — `POST /api/lint/python` stub [§3.3] → branch `feat/issue-848/skeleton`
- [x] `src/scieasy/api/routes/blocks.py` — `GET /api/blocks/template` stub [§3.12] → branch `feat/issue-848/skeleton`
- [x] `src/scieasy/blocks/_templates/__init__.py` + `block_base_template.py` — placeholder template file [§3.12] → branch `feat/issue-848/skeleton`
- [x] `frontend/src/components/CodeEditor.tsx` — empty component shell with Monaco lazy-import scaffolding marked TODO [§3.1] → branch `feat/issue-848/skeleton`
- [x] `frontend/src/components/Toolbar.tsx` — kind-switch scaffolding marked TODO (existing buttons untouched) [§3.7] → branch `feat/issue-848/skeleton`
- [x] `frontend/src/components/ProjectTree.tsx` — double-click handler stub marked TODO [§3.5] → branch `feat/issue-848/skeleton`
- [x] Test stubs created with detailed test plan comments → branch `feat/issue-848/skeleton` (3 pytest xfail files + 2 vitest skip files)
- [x] `frontend/package.json` lists `@monaco-editor/react` (PR body flags this for user `npm install` in main checkout) → branch `feat/issue-848/skeleton`

### Phase 2A — TabState union + backend file/lint (Owner: I36a)
- [x] All `TabState` consumers migrated to type-guard on `tab.kind === "workflow"` [§3.10] → branch `feat/issue-849/tabstate-and-backend` (TabBar.tsx, useWebSocket.ts, tabSlice.ts capture/restore, tabSlice.test.ts)
- [x] Store persistence updated: `FileTab` persists `{kind, id, filePath, displayName, language, readOnly}` only — content re-fetched on rehydrate [§3.11] → `frontend/src/store/index.ts` `partializeFileTab` + `onRehydrateStorage`
- [x] `GET /api/projects/{project_id}/file?path=<rel>` real impl: allowlist `.py .txt .md .yaml .yml .json .csv .log`, 10 MB cap, sandbox enforcement [§3.2] → `_resolve_project_file` + `read_project_file` in `routes/projects.py`
- [x] `PUT` real impl with atomic write (tempfile + rename) and `mark_self_write()` self-write suppression coordination with workflow_watcher [§3.2] → `write_project_file` in `routes/projects.py`
- [x] `POST /api/lint/python` real impl: shells `ruff check --stdin --output-format json`; soft-fails to empty diagnostics if ruff missing [§3.3, §6] → `routes/lint.py` `lint_python` + registered in `api/app.py`
- [x] Backend tests: path traversal, allowlist, size cap, lint diagnostic shape, self-write suppression integration → `tests/api/test_file_endpoints.py` (12) + `tests/api/test_lint_endpoint.py` (7); frontend `tabState.test.ts` (8) covers union exhaustiveness + dedup + persistence-stripping

### Phase 2B — CodeEditor component + Save UX (Owner: I36b)
- [x] `CodeEditor.tsx` Monaco wrapper, lazy-imported (mirror `TerminalView.tsx` xterm pattern at lines 76-88) [§3.1] → branch `feat/issue-850/code-editor`
- [x] Props: `tab: FileTab`, `onContentChange`, `onSave`, diagnostics → `setModelMarkers` → branch `feat/issue-850/code-editor`
- [x] Lint debounce (600 ms idle) → POST /api/lint/python → render markers → vitest `CodeEditor.test.tsx::debounces lint requests`
- [x] Save debounce (800 ms, same as canvas auto-save in App.tsx:478-487) [§3.9] → App.tsx file-tab auto-save useEffect
- [x] `App.tsx` content-area kind switch (active tab.kind === "workflow" → WorkflowCanvas, else CodeEditor) → branch `feat/issue-850/code-editor`
- [x] Toolbar split per §3.7 (file-tab toolbar shows New / Import / Save only in v1) → vitest `Toolbar.test.tsx::file tab: only New / Import / Save are visible`
- [x] Ctrl+S works for both tab kinds → App.tsx keydown listener routes by `activeFileTab`
- [x] Vitest tests: render Python tab, mock lint response, dirty-state propagation, save trigger → `CodeEditor.test.tsx` (7 cases) + `Toolbar.test.tsx` (3 cases)

### Phase 2C — ProjectTree + View source + reload + template (Owner: I36c)
- [x] `ProjectTree.tsx` double-click on `.py / .txt / .md / .json / .csv` → `openFileTab(path)` [§3.5] → branch `feat/issue-851/project-tree` (vitest `ProjectTree.test.tsx` 6 cases)
- [x] Workflow tab toolbar adds "View source" → opens `kind=file, readOnly=true` tab with id `source:<workflow_id>` (dedup by prefix) [§3.4] → branch `feat/issue-851/project-tree` (vitest `Toolbar.test.tsx::View source` 4 cases)
- [x] On `blocks/*.py` PUT: backend triggers existing `BlockRegistry.hot_reload()` only when lint diagnostics empty [§3.5] → branch `feat/issue-851/project-tree` (pytest `tests/api/test_reload_on_save.py` 4 cases)
- [x] Backend `GET /api/blocks/template` real impl + serves `block_base_template.py` content [§3.12] → branch `feat/issue-851/project-tree` (pytest `tests/api/test_blocks_template.py` 4 cases)
- [x] "New" toolbar menu: workflow / custom block / note (markdown) [§3.7, §3.12] → branch `feat/issue-851/project-tree` (vitest `Toolbar.test.tsx::New menu` 4 cases)
- [x] Frontend tests for double-click open, source-view dedup, "New" menu actions → branch `feat/issue-851/project-tree` (vitest 14 cases across `ProjectTree.test.tsx` + `Toolbar.test.tsx`)
- [x] Backend test: reload-gated-on-lint-pass → branch `feat/issue-851/project-tree` (`tests/api/test_reload_on_save.py::test_broken_block_save_does_not_reload_or_emit`)

### Audit & Fix (skeleton)
- [x] Audit-skeleton report posted on umbrella issue (Owner: A36-skeleton) → audit-output PR #857; umbrella comment https://github.com/zjzcpj/SciEasy/issues/843#issuecomment-4448807888 ; verdict: pass-with-fixes (3 P1 Codex findings accepted)
- [x] All P1 findings fixed (or explicitly justified deferral) (Owner: F36-skeleton, conditional) → fix PR #860 squash-merged into feat/issue-848/skeleton; route ordering + lockfile regen + atomic write coordination

### Audit & Fix (implementation)
- [x] Audit-implementation report posted on umbrella issue, includes Chrome smoke results (Owner: A36-impl) → `docs/audit/2026-05-14-adr-036-implementation.md`; verdict: NEEDS-FIX (2 P1, 4 P2)
- [x] All P1 findings fixed; deferred Codex P1 explicitly overridden (Owner: F36-impl) → fix branch `fix/adr-036-impl-audit-p1`; both P1s landed (saveFileTab race + new-block/note overwrite probe), P2 #6 (`createNewNote` 404 branch) fixed in-PR; P2 #3 / #4 / #5 deferred to backlog issues

---

## Test phase checklist (e2e — dispatcher runs in hotfix mode)

### ADR-035 e2e (Chrome smoke + ground-truth comparison)
- [ ] Chrome opens via `mcp__claude-in-chrome__tabs_create_mcp` → SciEasy GUI on free port
- [ ] Generate 4 random-noise TIFFs in test workspace: `A_01.tiff`, `A_02.tiff`, `B_01.tiff`, `C_01.tiff` (script writes them; saved as ground-truth fixture under `tests/e2e/adr-035/`)
- [ ] Generate ground-truth `metadata.csv` with columns `image_id, group, FOV` matching the 4 files
- [ ] In GUI: build new workflow `LoadImage → AIBlock → SaveData`
  - [ ] LoadImage: variadic, configured for the 4 TIFFs as a Collection
  - [ ] AIBlock: provider = Claude Code, permission mode = Bypass, prompt instructs reading manifest + writing `./outputs/metadata.csv` + calling `mcp__scieasy__finish_ai_block`
  - [ ] SaveData: writes the AI Block's `metadata` output port to `./outputs/metadata_saved.csv`
- [ ] Run workflow → AI Block tab opens automatically (block_pty_opened event)
- [ ] Tab shows claude TUI; agent autonomously reads manifest, writes CSV, calls finish_ai_block
- [ ] Workflow continues PAUSED → DONE; SaveData persists the CSV
- [ ] Compare `outputs/metadata_saved.csv` vs ground truth (sorted, deep-equal). **PASS = identical.**
- [ ] Record GIF via `mcp__claude-in-chrome__gif_creator`

### ADR-036 e2e (Chrome visual + 6 sub-tests) — **ALL PASS 2026-05-14** (Home PC Chrome MCP, port 50338, project `e2e-036` at `C:/temp/scieasy-e2e-036/e2e-036`)

- [x] **(a) Create-new triple** — New menu shows 3 items (workflow / custom block / note) ✓ per ADR-036 §3.7. File creation via API PUT works (notes/scratch.md, blocks/my_first.py); double-click opens Monaco tab. **Finding #1**: GUI uses `window.prompt()` for filename, blocks Chrome MCP — out of scope per user (not a SciEasy bug, browser limitation).
- [x] **(b) Edit + auto-save** — Typed in scratch.md editor, waited 2 s; disk mtime 1778792781→1778792844, size 29→54, content identical to editor. No Save click needed. ✓
- [x] **(c) View source dedup** — First click opened `main.yaml (source)` tab with Monaco YAML highlight. Second click: tab count unchanged (3: main / scratch.md / main.yaml (source)). ✓ **Finding #878**: View source on unsaved workflow alerts "main 不存在" instead of graceful save-or-prompt. **Finding #879**: New project does not auto-create empty `workflows/main.yaml`; must Ctrl+S manually.
- [x] **(d) Sample workflow regression** — Substituted "Generate beads" with manually-generated 256×256 synthetic TIFF (5 ellipses, 6741 bright px) since no `imaging.beads` block exists. Workflow `imaging.load_image → imaging.threshold(otsu) → imaging.save_image` ran 3/3 Done. Output mask: 6741 True / 6741 input bright px = 100% match. Canvas mode unaffected by ADR-036 changes. ✓
- [x] **(e) Toolbar swap** — Workflow tab toolbar: Projects / New / Import / Save / Run / Pause / Stop / Reset / Delete / Reload / Note / Group / View source ✓. File tab toolbar: Projects / New / Import / Save (hidden: Run/Pause/Stop/Reset/Delete/Reload/Note/Group/View source) ✓ per ADR-036 §3.7.
- [x] **(f) Custom block hot-load** — PUT `blocks/threshold_custom.py` (Otsu via skimage, mirrors `imaging.threshold`) → palette grew with `e2e.threshold_custom` ✓ (reload-on-save hook fired). Built workflow `main_custom` via API using the new block, executed. Mask byte-equal to original via `cmp` exit 0; md5 `d4c240d10711899016031c12540d72b0` identical. ✓

---

## Acceptance criteria
- [x] Pre-flight Phase 0 complete (2026-05-14). → tracking branches `track/adr-035/ai-block-pty` + `track/adr-036/code-editor` (commits 36a61c0 + baa7471 + ef30417); umbrella issues #842 (ADR-035) + #843 (ADR-036); sub-issues #844-#851; umbrella `[DO NOT MERGE]` PRs #852 + #853; checklist doc + 4 templates + audit-output rule + discipline hook + agent-manager skill + 3 memory entries committed.
- [ ] All 8 sub-issue PRs opened, audited, fixed, merged into their tracking branches
- [ ] Both tracking-branch umbrella PRs remain `[DO NOT MERGE]` open → #852 (ADR-035), #853 (ADR-036)
- [ ] Every checkbox in this document checked
- [ ] ADR-035 e2e mask compare = identical
- [x] ADR-036 e2e custom-block mask compare = identical (md5 `d4c240d10711899016031c12540d72b0`, sub-test (f) 2026-05-14)
- [ ] No drift: every checkbox has a corresponding artifact (commit, PR comment, test result) the dispatcher can point to

---

## Drift log (append-only)

When an agent ticks a box without producing the expected artifact, or modifies an out-of-scope file, log it here in the form:
```
2026-05-14 03:21 — agent <name> on PR #<n> ticked "<row>" but artifact missing / out-of-scope file <path> modified. Action: <revert / required additional commit / escalation>.
```

(empty until first violation)
