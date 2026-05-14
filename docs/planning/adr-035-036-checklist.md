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
- [ ] `src/scieasy/blocks/ai/ai_block.py` rewrite stub: `AIBlock(Block)` with `execution_mode=EXTERNAL`, `variadic_inputs/outputs=True`; all methods `raise NotImplementedError` with detailed implementation comments [§3.1]
- [ ] `src/scieasy/blocks/ai/run_dir.py` new module: `RunDir` class signature + per-run `.scieasy/ai-block-runs/{run_id}/` layout doc + manifest.json schema [§3.2, §3.4]
- [ ] `src/scieasy/blocks/ai/completion.py` new module: three completion paths sketched (MCP / FileWatcher / button) [§3.5]
- [ ] `src/scieasy/ai/agent/mcp/tools_workflow.py` add `finish_ai_block` ToolEntry stub returning `not_in_ai_block_context` envelope [§3.5]
- [ ] `src/scieasy/engine/pty_control.py` new module: `request_pty_tab()` + `notify_block_pty_event()` IPC helpers stubbed [§3.10]
- [ ] `src/scieasy/api/routes/ai_pty.py` add engine-initiated tab-open route stub (sibling to user-launched WS route — **do not modify** the existing route) [§3.10]
- [ ] `frontend/src/components/AIChat/TerminalTabs.tsx` accept engine-initiated open events stub [§3.10]
- [ ] `frontend/src/components/AIChat/TerminalTab.tsx` props extended for status badge + Mark-done button stubs [§3.9]
- [ ] `frontend/src/hooks/useWebSocket.ts` `block_pty_opened` / `block_pty_closed` switch-case stubs [§3.10]
- [ ] Test stubs created with detailed test plan comments

### Phase 2A — Backend block runtime (Owner: I35a)
- [ ] `AIBlock.run()` real implementation: writes manifest, requests PTY tab, enters PAUSED, awaits completion signal
- [ ] Manifest writer (path, type_chain, inputs, outputs, deadline) [§3.4]
- [ ] Output validation via existing IOBlock loaders [§3.6]
- [ ] State transitions IDLE→READY→RUNNING→PAUSED→DONE / ERROR / CANCELLED [§3.9]
- [ ] StubAgent fixture for tests (does not spawn claude; simulates `finish_ai_block` call)
- [ ] Unit tests: manifest contents, completion-signal precedence, validation failures, all three completion paths

### Phase 2B — Engine PTY control + MCP (Owner: I35b)
- [ ] `engine.request_pty_tab()` IPC: worker → engine sends spec, engine returns tab_id [§3.10]
- [ ] `engine.notify_block_pty_event()` IPC: completion / cancellation events [§3.10]
- [ ] `finish_ai_block` MCP tool real implementation: validates outputs dict, raises if not in AI Block context, writes signal file under `run_dir/`
- [ ] Engine-side route handler that allocates tab via existing `terminal.spawn_claude/codex` builder
- [ ] WS broadcast `block_pty_opened` to frontend
- [ ] Permission mode passthrough (safe / bypass) per block config [§3.7]
- [ ] Tests: IPC roundtrip with mock engine, finish_ai_block error envelope shapes, multi-call rejection

### Phase 2C — Frontend tab integration (Owner: I35c)
- [ ] `TerminalTabs.tsx` handles `block_pty_opened` event → auto-creates tab, switches focus
- [ ] `TerminalTab.tsx` renders title with 🤖 prefix + block name + status badge (✓ / ✗ / spinner)
- [ ] "Mark done" button visible when `tab.source === "ai-block"` and block is PAUSED
- [ ] Tab close while AI Block running → confirmation modal → emit cancel
- [ ] Tab survives DONE/ERROR (per ADR-035 §3.9)
- [ ] Vitest tests for new tab-source path; RTL render of status badge variants

### Audit & Fix (skeleton)
- [ ] Audit-skeleton report posted on umbrella issue (Owner: A35-skeleton)
- [ ] All P1 findings fixed (or explicitly justified deferral) (Owner: F35-skeleton, conditional)

### Audit & Fix (implementation)
- [ ] Audit-implementation report posted on umbrella issue, includes Chrome smoke results (Owner: A35-impl)
- [ ] All P1 findings fixed; deferred Codex P1 explicitly overridden (Owner: F35-impl)

---

## ADR-036 — Embedded code editor (track/adr-036/code-editor)

### Skeleton (Owner: S36)
- [ ] `frontend/src/store/types.ts` — `WorkflowTab` + `FileTab` discriminated union scaffolding (no consumer migration yet — types only) [§3.10]
- [ ] `frontend/src/store/tabSlice.ts` — `openFileTab()` / `saveFileTab()` / `updateFileTabContent()` action stubs [§3.10]
- [ ] `src/scieasy/api/routes/projects.py` — file GET/PUT route stubs returning 501 with implementation-plan docstrings [§3.2]
- [ ] `src/scieasy/api/routes/lint.py` new module — `POST /api/lint/python` stub [§3.3]
- [ ] `src/scieasy/api/routes/blocks.py` — `GET /api/blocks/template` stub [§3.12]
- [ ] `src/scieasy/blocks/_templates/__init__.py` + `block_base_template.py` — placeholder template file [§3.12]
- [ ] `frontend/src/components/CodeEditor.tsx` — empty component shell with Monaco lazy-import scaffolding marked TODO [§3.1]
- [ ] `frontend/src/components/Toolbar.tsx` — kind-switch scaffolding marked TODO (existing buttons untouched) [§3.7]
- [ ] `frontend/src/components/ProjectTree.tsx` — double-click handler stub marked TODO [§3.5]
- [ ] Test stubs created with detailed test plan comments
- [ ] `frontend/package.json` lists `@monaco-editor/react` (PR body flags this for user `npm install` in main checkout)

### Phase 2A — TabState union + backend file/lint (Owner: I36a)
- [ ] All `TabState` consumers migrated to type-guard on `tab.kind === "workflow"` [§3.10]
- [ ] Store persistence updated: `FileTab` persists `{kind, id, filePath, displayName, language, readOnly}` only — content re-fetched on rehydrate [§3.11]
- [ ] `GET /api/projects/{project_id}/file?path=<rel>` real impl: allowlist `.py .txt .md .yaml .yml .json .csv .log`, 10 MB cap, `_resolve_safe_path` enforcement [§3.2]
- [ ] `PUT` real impl with atomic write (tempfile + rename) and `mark_self_write()` self-write suppression coordination with workflow_watcher [§3.2]
- [ ] `POST /api/lint/python` real impl: shells `ruff check --stdin --output-format json`; soft-fails to empty diagnostics if ruff missing [§3.3, §6]
- [ ] Backend tests: path traversal, allowlist, size cap, lint diagnostic shape, self-write suppression integration

### Phase 2B — CodeEditor component + Save UX (Owner: I36b)
- [ ] `CodeEditor.tsx` Monaco wrapper, lazy-imported (mirror `TerminalView.tsx` xterm pattern at lines 76-88) [§3.1]
- [ ] Props: `tab: FileTab`, `onContentChange`, `onSave`, diagnostics → `setModelMarkers`
- [ ] Lint debounce (600 ms idle) → POST /api/lint/python → render markers
- [ ] Save debounce (800 ms, same as canvas auto-save in App.tsx:478-487) [§3.9]
- [ ] `App.tsx` content-area kind switch (active tab.kind === "workflow" → WorkflowCanvas, else CodeEditor)
- [ ] Toolbar split per §3.7 (file-tab toolbar shows New / Import / Save only in v1)
- [ ] Ctrl+S works for both tab kinds
- [ ] Vitest tests: render Python tab, mock lint response, dirty-state propagation, save trigger

### Phase 2C — ProjectTree + View source + reload + template (Owner: I36c)
- [ ] `ProjectTree.tsx` double-click on `.py / .txt / .md / .json / .csv` → `openFileTab(path)` [§3.5]
- [ ] Workflow tab toolbar adds "View source" → opens `kind=file, readOnly=true` tab with id `source:<workflow_id>` (dedup by prefix) [§3.4]
- [ ] On `blocks/*.py` PUT: backend triggers existing `BlockRegistry.hot_reload()` only when lint diagnostics empty [§3.5]
- [ ] Backend `GET /api/blocks/template` real impl + serves `block_base_template.py` content [§3.12]
- [ ] "New" toolbar menu: workflow / custom block / note (markdown) [§3.7, §3.12]
- [ ] Frontend tests for double-click open, source-view dedup, "New" menu actions
- [ ] Backend test: reload-gated-on-lint-pass

### Audit & Fix (skeleton)
- [x] Audit-skeleton report posted on umbrella issue (Owner: A36-skeleton) → audit-output PR #857; umbrella comment https://github.com/zjzcpj/SciEasy/issues/843#issuecomment-4448807888 ; verdict: pass-with-fixes (3 P1 Codex findings accepted)
- [ ] All P1 findings fixed (or explicitly justified deferral) (Owner: F36-skeleton, conditional)

### Audit & Fix (implementation)
- [ ] Audit-implementation report posted on umbrella issue, includes Chrome smoke results (Owner: A36-impl)
- [ ] All P1 findings fixed; deferred Codex P1 explicitly overridden (Owner: F36-impl)

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

### ADR-036 e2e (Chrome visual + 6 sub-tests)
Open SciEasy in Chrome via Chrome MCP. Take screenshots at each milestone for visual verification.

- [ ] **(a) Create-new triple** from toolbar "New" menu:
  - [ ] new workflow → file appears in `workflows/` on disk
  - [ ] new custom block (`my_block.py`) → file appears in `blocks/`, content matches `block_base_template.py`
  - [ ] new note (`scratch.md`) → file appears, empty
  - [ ] All three open as editor tabs; Monaco renders correctly; syntax highlighting per language
  - [ ] Block template scaffold has correct imports (`from scieasy.blocks.base import Block, BlockSpec, PortSpec`)
- [ ] **(b) Edit + auto-save** on the `.py` and `.md` from (a):
  - [ ] Type a character; wait 800 ms+; verify mtime on disk advanced
  - [ ] No "save" button click required
- [ ] **(c) View source on workflow**: open existing workflow canvas; click "View source"
  - [ ] New tab opens with `(source)` suffix
  - [ ] YAML rendered, Monaco read-only mode active (typing produces no change)
  - [ ] Re-clicking "View source" focuses existing tab (no duplicate)
- [ ] **(d) Sample workflow regression**: build `Generate beads (5 circles synthetic image) → Otsu Threshold → Save Mask`
  - [ ] Workflow runs to completion
  - [ ] Mask file saved
  - [ ] Confirms canvas-mode features unaffected by ADR-036 changes
- [ ] **(e) Toolbar swap** by switching active tab between workflow and file:
  - [ ] On workflow tab: Run / Pause / Stop / Reset / Reload / Delete / Note / Group all visible
  - [ ] On file tab: those buttons hidden; only New / Import / Save shown
  - [ ] "View source" button visible only on workflow tab
- [ ] **(f) Custom block hot-load**: use editor to create `blocks/threshold_custom.py` implementing Otsu identically (skimage)
  - [ ] Save → palette refreshes (reload_blocks fired)
  - [ ] Drag the new block onto canvas, replace the original Otsu node, run
  - [ ] Compare output mask byte-equal to original. **PASS = identical.**

---

## Acceptance criteria
- [x] Pre-flight Phase 0 complete (2026-05-14). → tracking branches `track/adr-035/ai-block-pty` + `track/adr-036/code-editor` (commits 36a61c0 + baa7471 + ef30417); umbrella issues #842 (ADR-035) + #843 (ADR-036); sub-issues #844-#851; umbrella `[DO NOT MERGE]` PRs #852 + #853; checklist doc + 4 templates + audit-output rule + discipline hook + agent-manager skill + 3 memory entries committed.
- [ ] All 8 sub-issue PRs opened, audited, fixed, merged into their tracking branches
- [ ] Both tracking-branch umbrella PRs remain `[DO NOT MERGE]` open → #852 (ADR-035), #853 (ADR-036)
- [ ] Every checkbox in this document checked
- [ ] ADR-035 e2e mask compare = identical
- [ ] ADR-036 e2e custom-block mask compare = identical
- [ ] No drift: every checkbox has a corresponding artifact (commit, PR comment, test result) the dispatcher can point to

---

## Drift log (append-only)

When an agent ticks a box without producing the expected artifact, or modifies an out-of-scope file, log it here in the form:
```
2026-05-14 03:21 — agent <name> on PR #<n> ticked "<row>" but artifact missing / out-of-scope file <path> modified. Action: <revert / required additional commit / escalation>.
```

(empty until first violation)
