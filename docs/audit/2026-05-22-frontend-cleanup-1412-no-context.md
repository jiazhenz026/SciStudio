---
title: "Frontend Cleanup #1412 — No-Context Audit (2026-05-22)"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs: []
language_source: en
---

# Frontend Cleanup #1412 — No-Context Audit (2026-05-22)

## 1. Audit mode

`no-context`. I did not read the issue, the manager checklist, the PR
description, dispatch prompts, chat summaries, or any gate record for this
work. All claims below are grounded in repository docs, code, tests, and
tools I ran myself in this audit worktree.

## 2. Scope examined

- `frontend/eslint.config.js`
- `frontend/.prettierignore`, `frontend/.prettierrc.json`
- `frontend/package.json`, `frontend/package-lock.json`
- `frontend/src/` — all source and test files, with deep reads on:
  - `frontend/src/App.tsx` and every file under `frontend/src/App.parts/`
  - `frontend/src/lib/api.ts` and every file under `frontend/src/lib/api/`
  - `frontend/src/components/nodes/BlockNode.tsx` and every file under
    `frontend/src/components/nodes/BlockNode.parts/`
  - spot reads on `BottomPanel.parts/`, `DataPreview.parts/`,
    `CodeEditor.parts/`, `WorkflowCanvas.parts/`, `ProjectTree.parts/`,
    `Toolbar.parts/`, `DataRouterModal.parts/`, `ProjectDialog.parts/`,
    `store/executionSlice.parts/`, `store/tabSlice.parts/`,
    `store/workflowSlice.parts/`
  - downstream import-surface check across all of `frontend/src/`
- `.github/workflows/ci.yml` (frontend job + wheel-release-smoke build)
- `.sentrux/rules.toml`
- `docs/specs/adr-045-workflow-state-version.md` (only because `lib/api.ts`
  references it via comments — confirmed it does not govern any frontend
  file via `governs.files`)

## 3. Context I did NOT read

- The current owner request.
- Any issue or PR for #1412, #1413, #1414, #1415, #1416, #1417, #1419, #1420,
  #1421, #1422, #1426, #1410, or #1427 — I did not call `gh issue view`,
  `gh pr view`, or any equivalent.
- The manager checklist (`docs/planning/frontend-cleanup-1412-checklist.md`
  or any equivalent under `docs/planning/`).
- Any dispatch prompt.
- PR descriptions and PR comments.
- Chat summaries or manager summaries.
- Gate records under `.workflow/records/` whose `task_id` references the
  current work.
- `CHANGELOG.md` entries dated 2026-05-22.
- Recent dated audit reports under `docs/audit/2026-05-22-*` other than my
  own output.

I did read commit subject lines via `git log --oneline origin/main..HEAD`
to confirm which files moved in this branch — that surfaces the file
provenance I am auditing, not the manager intent. Commit subjects use
references like `(#1422)` and `(#1413)(#1414)` but I did not look up those
issues; I treated them only as text in the code/commit headers.

## 4. Tool output captured

### 4.1 `frontend/` toolchain (run in worktree)

| Command | Result |
| --- | --- |
| `npm ci` | 844 packages installed, 3 moderate severity advisories (pre-existing) |
| `npm run lint` | 0 errors, 31 warnings (all `react-refresh/only-export-components`, `react/no-array-index-key`, or stale `eslint-disable`) |
| `npm run typecheck` (`tsc --noEmit`) | exit 0, no output |
| `npm run format:check` | "All matched files use Prettier code style!" |
| `npm test` (`vitest run`) | 59 test files, 571 passed, 13 skipped, 0 failed in 10.34s |
| `npm run build` (`tsc -b && vite build`) | 2193 modules transformed, built in 21.88s. Chunk-size warning on the main bundle (>500 kB) — pre-existing, not introduced by this work. |

### 4.2 Python toolchain (smoke)

| Command | Result |
| --- | --- |
| `ruff check .` | "All checks passed!" |
| `ruff format --check .` | "733 files already formatted" |
| `PYTHONPATH=src python -m scistudio.qa.audit.full_audit ...` | top-level **`pass`**, 0 findings. Children: `generate_facts` pass (2576 facts), `frontmatter_lint` pass (0), `fact_drift` pass (208 docs), `doc_drift` pass (379 contracts), `closure` pass, `signature_drift` pass, `architecture_drift` pass, `vulture` pass (6 pre-existing dead-variable warnings in `src/scistudio/blocks/`, `core/`, `engine/`, `utils/` — **not** in any frontend cleanup scope). `semantic_dup` deferred (expected). |

### 4.3 Sentrux MCP

| Command | Result |
| --- | --- |
| `scan(path=<worktree>)` | 1413 files, 3176 import edges, 326650 lines, quality_signal=4128 |
| `check_rules` | **pass**, 3 rules checked, 0 violations |
| `health` | acyclicity raw=5 (== `.sentrux/rules.toml` `max_cycles = 5`), modularity 0.22, depth raw=20, equality 0.43, redundancy 0.086 |

Sentrux is **at** the configured ceiling (`max_cycles = 5`), not above it.
The TOML file's preamble (lines 7-21) documents the headroom and tracks
ratchet-back follow-ups (#1336, #1465). Frontend cleanup did not regress
this number.

## 5. Findings

### 5.1 P1 (blocking)

None.

### 5.2 P2 (should-fix before merge)

None observed. The work passes every gate I could exercise locally.

### 5.3 P3 (nice-to-have / followup)

#### P3-1 — `GOD_FILE_SIZE_WAIVERS` is stale for several entries

Evidence — `frontend/eslint.config.js` lines 13–23 waives `max-lines` /
`max-lines-per-function` / `complexity` for these paths, but their current
raw LOC is well under the 500 cap:

| File | Raw LOC | Status |
| --- | --- | --- |
| `src/App.tsx` | 494 | At cap, waiver still earns it ~6 lines of headroom |
| `src/components/nodes/BlockNode.tsx` | 295 | Waiver effectively dead |
| `src/components/nodes/BlockNode.test.tsx` | 40 | Waiver effectively dead |
| `src/components/DataPreview.tsx` | 126 | Waiver effectively dead |
| `src/components/BottomPanel.tsx` | 108 | Waiver effectively dead |
| `src/components/Lineage/RunDetail.tsx` | 186 | Waiver effectively dead |
| `src/lib/api.ts` | 64 | Waiver effectively dead |
| `src/components/Git/ConflictMarkerDecoration.ts` | 222 | Waiver effectively dead |
| `src/components/BottomPanel.test.tsx` | 667 | Genuine waiver still required |

After Wave 2 (`#1422`) split the god files, most paths in
`GOD_FILE_SIZE_WAIVERS` no longer need the waiver. Pruning them now would
turn the waiver list into a meaningful tripwire — a future regression that
re-bloats one of these files would lint-fail. As-is, those eight paths can
silently grow back to 499 LOC. **Recommend** trimming dead entries in a
follow-up PR (this is hygiene, not a blocker).

#### P3-2 — pre-existing TODO without an issue reference

`frontend/src/lib/api/workflows.ts:35`:

```
// TODO: replace the dedicated /api/workflows/import-path endpoint with a
// fetch-then-import flow that reuses /api/projects/{id}/file.
```

AGENTS rule 3.6 requires `TODO(#NNN)` form. This TODO was extracted from
the pre-split `lib/api.ts` monolith by the `#1422` refactor (the comment
predates the cleanup work — the cleanup only moved the line). It is not
introduced by this work, but it now lives in a newly extracted file so it
gets fresh attention. **Recommend** filing a follow-up issue and
back-stamping the TODO. Not a blocker because the rule applies to deferred
work introduced by this PR, not to pre-existing TODOs that the refactor
relocated unchanged.

#### P3-3 — `.parts/` directory naming is informal

The `.parts/` pattern is widely adopted (App.parts, BlockNode.parts,
BottomPanel.parts, etc., plus the older `executionSlice.parts/`,
`tabSlice.parts/`, `workflowSlice.parts/` in `src/store/`). It is not
documented anywhere I could find (no `frontend/AGENTS.md`, no spec section
on frontend module layout). Each `.parts/` file has a concise
"Extracted from X.tsx as part of #1422" header docstring, but a single
README under e.g. `frontend/src/AGENTS.md` codifying the convention would
help future agents avoid arbitrary chops. **Recommend** adding a short
frontend module-layout note in a follow-up.

## 6. Spot-checks the dispatch asked for

### 6.1 `frontend/eslint.config.js`

- The file exists and parses (the `eslint-config.test.ts` test exercises
  `linter.calculateConfigForFile("src/main.tsx")` and asserts a config is
  returned).
- All rule names spelled correctly — the test also asserts each enforced
  rule fires on a fixture (eqeqeq, react-hooks/rules-of-hooks,
  @typescript-eslint/no-explicit-any, max-lines).
- The `ignores` glob includes `.claude/**` to keep nested agent worktrees
  out of lint (line 112). No other ignores shadow meaningful frontend
  directories.
- I verified that every path listed in every waiver array
  (`GOD_FILE_SIZE_WAIVERS`, `MAX_LINES_PER_FN_WAIVERS`,
  `COMPLEXITY_WAIVERS`, `EQEQEQ_WAIVERS`, `CONSISTENT_TYPE_IMPORT_WAIVERS`,
  `NO_UNUSED_VARS_WAIVERS`, and the inline `max-depth` /
  `ban-ts-comment` files) exists on disk in this worktree. No
  dangling references.

### 6.2 `frontend/src/lib/api.ts` + `api/` directory

- `lib/api.ts` is now a thin 64-LOC re-export shell pulling
  `projects | blocks | workflows | data | filesystem | code | lineage | git`
  domain bundles and re-exporting `ApiError`,
  `consumePendingWorkflowSourceId`, `createClientSourceId`,
  `setWorkflowWriteStartedListener`, and the four `Versioned*` / `ProjectFile*`
  types.
- 60+ downstream files import from `"../lib/api"` /
  `"../../lib/api"` / `"../../../lib/api"` — every import in the codebase
  resolves to the shell. `npm run typecheck` (`tsc --noEmit`) returns exit 0.
- `frontend/src/lib/api/__tests__/api-surface.test.ts` pins the public
  key-set (47 method names + the `lineage` namespace methods) and
  validates `ApiError` is still a constructable `Error` subclass.

### 6.3 `BlockNode.tsx` + `BlockNode.parts/`

- All hooks in `BlockNode.tsx` (`useLayoutEffect`, `useRef`, `useState`)
  sit at the top level of the `BlockNode` function — no hook is called
  after any early return. The `useLayoutEffect` block on lines 108-118
  measures `configSectionRef.current.offsetTop`; it is conditional on a
  null check **inside** the effect callback, not as an early return that
  skips the effect.
- `InlineConfigField.tsx` has no hooks itself (line 126); each branch
  delegates to a dedicated sub-component, and the default text-input
  branch delegates to `InlineTextInputField` so its `useState` / `useRef`
  / `useLayoutEffect` chain sits at the top of its own component (the
  `#1420` regression coverage in `BlockNode/hooks1420.test.tsx`
  validates this).
- `PortHandles.tsx` calls `useEdges()` and `useReactFlow()` at the top of
  the function (lines 166-167), before any branch.
- `react-hooks/rules-of-hooks` is enforced project-wide (only `BlockNode`
  /`App` waivers were retired per the `#1420`/`#1421` Wave-1 trace, and
  the `eslint-config.test.ts` regression suite verifies the rule still
  fires on a synthetic violation at `BlockNode.tsx`).

### 6.4 `*.parts/` cohesion

Each `.parts/` module I read carries a clear single-responsibility
docstring naming the parent file and the issue that drove the extraction
(`#1422` god-file refactor, `#1420`/`#1421` rules-of-hooks fix,
`#1414` complexity reduction in `eventReducer.ts`, etc.). The split lines
are reasonable: hook bundles get one file per concern (autosave,
keyboard shortcuts, lifecycle effects), modal components get one file per
modal, data-rendering components are split by viewer kind (`ImageViewer`,
`TableViewer`, `PreviewRenderer`). I did not find any "arbitrary chop" —
each file has a coherent description that matches its imports and exports.

### 6.5 Test naming vs coverage

Spot-checked:

- `BottomPanel.parts/codeBlockPorts.test.ts` covers every exported helper
  in `codeBlockPorts.ts` (`isRecord`, `isCodeBlockConfigTarget`,
  `codeBlockFolder`, `nextCodeBlockPortName`, `normalizeCodeBlockPort`,
  `persistCodeBlockPort`).
- `executionSlice.parts/eventReducer.test.ts` covers every exported helper
  in `eventReducer.ts` (`extractBlockError`, `maybeAppendErrorLog`,
  `nextBlockOutputs`, `nextBlockStates`, `nextErrorMaps`,
  `nextIsRunning`).
- `BlockNode/hooks1420.test.tsx` actually exercises the
  `InlineTextInputField` extraction (default branch, file_browser
  branch, directory_browser branch) — the comment-claim and the test
  body match.
- `api/__tests__/api-surface.test.ts` enumerates all 47 expected `api.*`
  methods plus the 5 `api.lineage.*` methods, matching what
  `lib/api.ts`'s re-export shell composes.

### 6.6 `.sentrux/rules.toml` vs repository state

- `max_cycles = 5` (line 22), `max_cc = 100` (line 26), `no_god_files = false`
  (line 27).
- Sentrux scan reports `acyclicity.raw = 5` — exactly at the ceiling.
- `check_rules` returns 0 violations. No drift.

## 7. Recommendation

**Pass-with-fixes** is overkill. **Pass.**

The frontend cleanup is internally consistent: every governing
ESLint/Prettier rule passes, every test passes, the build succeeds, full
audit comes back green, and sentrux is at-but-not-above its ceiling.
Every `.parts/` extraction has a docstring identifying its parent and the
issue that drove the extraction. The public `lib/api` re-export surface
matches downstream imports and is pinned by a regression test.

The three P3 items are tracker hygiene (prune dead waiver entries, file an
issue for the pre-existing `TODO:` line, document the `.parts/` convention).
None block merge.

## 8. PR

PR for this audit report will be opened against `track/frontend-cleanup-1412`
after this file is committed; see the trailing section for PR number/URL
once published.

Branch: `audit/2026-05-22-frontend-cleanup-no-context`
Worktree: `C:\Users\jiazh\Desktop\workspace\SciStudio\.claude\worktrees\frontend-cleanup-mgr\.claude\worktrees\w4-audit-nc`
Audit base commit (before this report): `4d5b0b12730cfd2827ad08e68effedf9619e205d`

## 9. Confirmation

I confirm I did not read any forbidden context per the dispatch
context-limit list in §3 above.
