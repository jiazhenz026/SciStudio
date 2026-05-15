# ADR-038 + ADR-039 Implementation Checklist

> **Mandatory tracking doc.** Every agent edits the rows it owns and only those rows.
> Drift = protocol violation. The dispatcher (Claude as agent manager) sweeps after every phase.
> Plan file: `~/.claude/plans/whimsical-soaring-pascal.md`. Session start: 2026-05-15.

## Conventions

- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- "Owner" is the agent role or "manager" for hands-on work
- Each row references the relevant ADR section in `[brackets]`
- When you tick a box, also append a one-line note: `→ <PR-or-commit-link>` or `→ <test-name passes>` or `→ <report-file-path>`
- Out-of-scope rules per agent are encoded in `docs/planning/dispatch-prompts/` (one prompt file per agent)

## Manager discipline (non-negotiable for this cascade)

1. Every `Agent` dispatch uses `isolation: "worktree"`, `model: "opus"`, `subagent_type: "general-purpose"`.
2. **MANDATORY (user direction 2026-05-15)**: After every Agent dispatch, the manager MUST immediately enter a foreground `until` loop polling for the next concrete artifact. Never reply "Waiting" and let the stop-hook fire repeatedly. Pattern: `until [ -n "$(git ls-remote origin '<branch-pattern>' 2>/dev/null)" ]; do sleep 60; done` or `until [ -f <report-path> ]; do sleep 60; done`.
3. Worktree isolation forbids `pip install -e .` from within the worktree (see `feedback_editable_install_contamination`).
4. Every `pytest` invocation uses `--timeout=60`. Plugin (`pytest-timeout`) is already in dev deps.
5. No `npm run dev` background processes — use `vitest run` and `npm run build`.
6. Every agent PR body contains `Closes #N`.
7. CI must be green before any agent reports done.
8. Mandatory live Chrome smoke for any UI-touching phase before report-done.
9. Codex P1/P2 findings on agent PRs override auditor "defer" calls — manager fixes in-PR per overnight merge protocol.
10. Tracking-branch convention: agent feature branches target the tracking branch (NOT main); umbrella PR `[DO NOT MERGE]` per track points to main for visibility only.

---

## Phase 0 — Architecture docs refactor (Owner: manager)

> Manager works on branch `docs/adr-038-039/architecture-refactor` off latest main.
> Single PR for review by user; gate workflow: standard 6-gate.

### Refactor targets (verify each by grep, not just by ADR §5.3 list)

- [x] `docs/architecture/ARCHITECTURE.md` §1 — add "History and versioning model" top-level section [ADR-038 §1, ADR-039 §2.4]
- [x] `docs/architecture/ARCHITECTURE.md` §4.4 "Data lineage" — rewrite with 4-table schema [ADR-038 §3.1]
- [x] `docs/architecture/ARCHITECTURE.md` add "Source version control" subsection [ADR-039 §3]
- [x] `docs/architecture/ARCHITECTURE.md` §1464 EventBus matrix — LineageRecorder status `planned`→`active` [ADR-038 §5.3]
- [x] `docs/architecture/ARCHITECTURE.md` §2009 env snapshot — 5 packages → full `uv pip freeze` [ADR-038 §5.3]
- [x] `docs/architecture/ARCHITECTURE.md` §2077 MCP server deps — `lineage, MetadataStore` → `LineageStore (unified)` [ADR-038 §5.3]
- [x] `docs/architecture/PROJECT_TREE.md` — add `.git/`, `.gitignore`, `.scieasy/lineage.db`, `.scieasy/pause/`; remove `metadata.db` and `checkpoints/` [ADR-038/039 §5.3]
- [x] `docs/adr/ADR-032.md` — status banner: `SUPERSEDED by ADR-038` [ADR-038 §10]
- [x] `docs/adr/ADR-014.md` — cross-ref ADR-039 (git in project state model) [ADR-039 §5.3]
- [x] `docs/adr/ADR-012.md` — clarify checkpoint scope vs lineage; relocate path note [ADR-038 §5.2, §3.6a]
- [x] `docs/adr/ADR-018.md` — LineageRecord field alignment with new 4-table schema [ADR-038 §5.3]
- [x] `docs/adr/ADR-020.md` — remove `batch_info` references [ADR-038 §5.3]
- [x] `docs/adr/ADR-027.md` D5 — `lineage_id` docstring: populated with `block_execution_id` per ADR-038 [ADR-038 §5.3]
- [x] `docs/adr/ADR-031.md` Addenda — replace `metadata.db` refs with `lineage.db.data_objects` [ADR-038 §5.3]
- [x] `docs/block-development/architecture-for-block-devs.md` — replace metadata.db wording; new "blocks alongside git" section [ADR-038/039 §5.3]
- [x] `docs/block-development/memory-safety.md` — grep + correct metadata-storage references [ADR-038 §5.3]
- [x] `docs/cli-integration.md` — git CLI compatibility note; document `auto:`/`agent:`/no-prefix commit convention [ADR-039 §3.4a, §5.3]
- [x] `CHANGELOG.md` — `[Unreleased] > Changed` entry: `[#904] Refactor architecture docs for ADR-038 + ADR-039 (@claude, 2026-05-15, branch: docs/adr-038-039/architecture-refactor, session: 20260515-052537-adr-038-039-cascade-phase-0-architecture)`

### Phase 0 manager-driven gate workflow

- [x] `gate.py start` → task ID `20260515-052537-adr-038-039-cascade-phase-0-architecture`
- [x] `gh issue create` (Phase 0 docs PR's tracking issue) → gate.py advance create_issue → https://github.com/zjzcpj/SciEasy/issues/904
- [x] Change Plan comment on the issue → gate.py advance write_change_plan → https://github.com/zjzcpj/SciEasy/issues/904#issuecomment-4459069604
- [x] Branch `docs/adr-038-039/architecture-refactor` created and pushed; commits `e6776a7`, `22014b1`, `6dc0ad8`
- [x] Doc updates committed → gate.py advance update_docs
- [x] CHANGELOG entry → gate.py advance update_changelog
- [x] `gh pr create` against main → gate.py advance submit_pr → https://github.com/zjzcpj/SciEasy/pull/905

---

## Phase 0.5 — Docs audit (Owner: A0 — no-context agent)

- [x] 1 audit agent dispatched, no session context; inputs limited to ADR-038/039 + refactored docs → agent ID `a83ab64ede13c85db`
- [x] Audit report at `docs/audit/2026-05-15-adr-038-039-docs-audit.md` with P1/P2/P3 categorization (3 P1 + 4 P2 + 4 P3 + 1 OOS)
- [x] Agent committed audit report to `audit-output-phase-0.5` branch + opened PR #907 → https://github.com/zjzcpj/SciEasy/pull/907

---

## Phase 0.75 — Docs fix + scope-out + docs PR (Owner: manager)

- [x] All P1 audit findings within ADR-038/039 scope: fixed on docs branch
  - P1-1 (ADR-039 §10 pygit2 → bundled git CLI) → ADR-039.md:615
  - P1-2 (ADR-038 §5.2 checkpoint/ → pause/) → ADR-038.md:384
  - P1-3 (ARCHITECTURE.md §11 Metadata DB → Lineage DB) → ARCHITECTURE.md:3028
- [x] All P2 audit findings within ADR-038/039 scope: fixed
  - P2-1 (key_dependencies clarification) → block-development/{architecture-for-block-devs,memory-safety}.md
  - P2-2 (ADR-031 ADR-038 cross-ref) → ADR-031.md Addendum 3
  - P2-3 (ADR-038 §5.1 LineageRecorder move clarification) → ADR-038.md
  - P2-4 (ADR-038 §5.2 app.py row dedup) → ADR-038.md
- [x] P3 fixes applied (P3-1 Layer 1 caption, P3-3 §5.3 ADR.md file refs); P3-4 same root as P2-1 (resolved); P3-2 → out-of-scope issue
- [x] Out-of-scope findings filed as separate GitHub issues; tracked in "Out-of-scope from docs audit" section below (#908)
- [x] Docs PR #905 opened against main → https://github.com/zjzcpj/SciEasy/pull/905
- [x] CI green on PR #905 (Codex P2 reconciled; all required checks pass before merge)
- [x] User-approved autonomous merge → main has the refactored docs (merged 2026-05-15T11:09:07Z, commit 0cc8a8f)

---

## Phase 1 — Preflight (Owner: manager)

- [x] Re-sync main: `git checkout main && git pull origin main` (main at `0cc8a8f` Phase 0 docs merge)
- [x] Tool checks: python 3.13.12, pytest 9.0.2, ruff 0.15.9, mypy 1.20.0, node v24.14.0, npm 11.9.0, gh 2.89.0, claude 2.1.142 — all on PATH
- [x] `python -c "import scieasy; print(scieasy.__file__)"` → `src/scieasy/__init__.py` (clean, not editable-install contamination)
- [ ] Chrome MCP probe (deferred to Phase D38-3.1b / D39-3.1 audit + Phase 4 e2e where it's mandatory)
- [x] Discipline hook present at `scripts/hooks/remind-checklist-discipline.sh`; `.claude/settings.json` wires it to PostToolUse on Edit/Write/MultiEdit/TaskCreate/TaskUpdate/TaskStop/TodoWrite (verified from `.claude/settings.json` lines 30-46 during Phase 0)
- [x] Tracking branch created: `track/adr-038/lineage-db` off main, pushed to origin (commit 7c1ae58 seed)
- [x] Tracking branch created: `track/adr-039/git-versioning` off main, pushed to origin (commit 6549c5f seed)
- [x] Umbrella issue opened: `ADR-038: Unified Run Lineage Database — implementation track` → https://github.com/zjzcpj/SciEasy/issues/910
- [x] Umbrella issue opened: `ADR-039: Git-backed source version control — implementation track` → https://github.com/zjzcpj/SciEasy/issues/911
- [x] Sub-issues opened (created lazily per dispatch — one per sub-agent as dispatched): #920 #925 #929 #933 #934 #939 #941 
- [x] Umbrella PR `[DO NOT MERGE]` opened from `track/adr-038/lineage-db` to main with checklist link → https://github.com/zjzcpj/SciEasy/pull/912
- [x] Umbrella PR `[DO NOT MERGE]` opened from `track/adr-039/git-versioning` to main with checklist link → https://github.com/zjzcpj/SciEasy/pull/913
- [x] CI baseline checked (main commit 0cc8a8f workflows queued; #909 tracks pre-existing Python 3.11 flake; no other regressions)

---

## ADR-038 — Unified Run Lineage DB (track/adr-038/lineage-db)

### Phase D38-2.1 — Code-scope audit (Owner: AD38-1, no-context agent)

- [ ] Audit agent dispatched with ADR-038 + main-tree only; explicit instruction "no session context"
- [ ] Scans entire repo for: `MetadataStore`, `metadata_store`, `metadata.db`, `LineageStore`, `LineageRecord`, `LineageRecorder`, `lineage.db`, `_persist_output_metadata`, `block_version` defaults, `lineage_id`, `framework.lineage_id`, `BLOCK_DONE` consumers/producers, `api/deps.py::get_lineage_store`, `tests/.../test_lineage*`
- [ ] Report at `docs/audit/2026-05-15-adr-038-code-scope-audit.md` with file×symbol×line table marking "in ADR §5.2" vs "newly discovered"
- [ ] Manager folds newly-discovered files into D38-2.2 / 2.3 / 2.4 owned-file lists before dispatch

### Phase D38-2.2 — Wire-up + schema (Owner: ID38-2, 1 agent, refactor) [ADR-038 §6 Phase 1]

- [x] Sub-issue opened, branch `feat/issue-920/d38-2-2-wire-up-schema` off `track/adr-038/lineage-db` → https://github.com/zjzcpj/SciEasy/issues/920
- [x] `src/scieasy/core/lineage/` new package: `__init__.py`, `store.py` (4-table), `record.py`, `recorder.py` (moved from engine/), `environment.py`, `run_context.py`; `graph.py` DELETED per ADR §3.4 [ADR-038 §3.1, §5.1]
- [x] `src/scieasy/engine/scheduler.py` — construct LineageRecorder; extend BLOCK_DONE event data (`config`, `block_type`, `block_version`, `environment`, `input_object_ids`, `output_object_ids`, `inputs`) [ADR-038 §3.2]
- [x] `src/scieasy/engine/lineage_recorder.py` — relocated to `core/lineage/recorder.py`; engine path is a re-export shim for one minor-version compat window [ADR-038 §5.1, §5.2]
- [x] `src/scieasy/engine/runners/local.py` — lift `environment` from worker envelope into event data via `__scieasy_env__` sentinel (scheduler pops before downstream blocks see it) [ADR-038 §5.2]
- [x] `src/scieasy/api/runtime.py::start_workflow` — create RunRecord, construct LineageRecorder, pass to DAGScheduler, finalize on completion via `_finalize_lineage_run` task callback [ADR-038 §3.2]
- [x] `src/scieasy/api/runtime.py::create_project` — `.scieasy/` replaces legacy `checkpoints/`+`lineage/` scaffold dirs
- [x] `src/scieasy/api/deps.py::get_lineage_store` — rewrite to return the unified store owned by `ApiRuntime` (no per-request store allocation) [ADR-038 §5.2]
- [x] `src/scieasy/api/app.py` — register `runs` router placeholder for D38-2.4a [ADR-038 §5.2]
- [x] `src/scieasy/blocks/registry.py` — force-inject `block_version` from `importlib.metadata` (cached `packages_distributions`); in-tree blocks stamp `scieasy.__version__`; no `"unknown"` default [ADR-038 §3.3]
- [x] `src/scieasy/cli/main.py` — `init` scaffold list parity with `runtime.py::create_project`
- [x] `tests/engine/test_lineage_recorder.py` + `tests/core/test_lineage*.py` + `tests/api/test_deps.py` + `tests/cli/test_cli.py` — migrated to new schema
- [x] Smoke test `tests/core/test_lineage_store_4table.py` passes: 3-block linear workflow produces 1 run + 3 block_executions + 3 data_objects + 5 block_io rows (linear DAG: A has no input → 5 not 6; spec note inline)
- [ ] CI green
- [ ] PR merged into `track/adr-038/lineage-db`

### Phase D38-2.3 — Collapse metadata.db (Owner: ID38-3, 1 agent, migration) [ADR-038 §6 Phase 2]

- [x] Sub-issue opened, branch off tracking branch after D38-2.2 merged → [#929](https://github.com/zjzcpj/SciEasy/issues/929)
- [x] `src/scieasy/core/metadata_store.py` → 6-month deprecation shim re-exporting unified store + DeprecationWarning [ADR-038 §5.2] → [PR #929 — deprecation shim](https://github.com/zjzcpj/SciEasy/pull/929)
- [~] `src/scieasy/core/meta/framework.py` — `FrameworkMeta.lineage_id` populated with `block_execution_id` in run context [ADR-038 §3.2, §5.2] → `with_lineage_id` helper added; end-to-end stamping escalated on #929 (requires moving allocation site from recorder to scheduler per ADR §3.2 — core/lineage/ is out of scope for D38-2.3)
- [x] `src/scieasy/engine/scheduler.py::_persist_output_metadata` — write to new `data_objects` table [ADR-038 §5.2] → [PR #929](https://github.com/zjzcpj/SciEasy/pull/929)
- [x] `src/scieasy/engine/checkpoint.py` — relocate `<project>/checkpoints/` to `<project>/.scieasy/pause/`; docstring clarifies pause/resume scope vs lineage [ADR-038 §5.2] → [PR #929 — checkpoint_dir_for relocation in api/runtime.py](https://github.com/zjzcpj/SciEasy/pull/929)
- [x] Project-open auto-creates lineage.db if missing; no historical metadata.db migration (per user direction 2026-05-15) → existing D38-2.2 wiring honoured; legacy metadata.db detection logs INFO line and is otherwise ignored
- [ ] Tests pass; CI green; PR merged into tracking branch

### Phase D38-2.4a — Backend REST + AIBlock rename (Owner: ID38-4a, 1 agent) [ADR-038 §6 Phase 3 backend]

- [x] Sub-issue opened; parallel with D38-2.4b → [#933](https://github.com/zjzcpj/SciEasy/issues/933)
- [x] `src/scieasy/api/routes/runs.py` (NEW) — GET /api/runs, GET /api/runs/{run_id}, GET /api/runs/{run_id}/methods, POST /api/runs/{run_id}/rerun [ADR-038 §3.7, §3.8] → branch `feat/issue-933/d38-2-4a-backend-rest`
- [x] `src/scieasy/core/lineage/methods_export.py` (NEW) — markdown methods renderer [ADR-038 §5.1] → branch `feat/issue-933/d38-2-4a-backend-rest`
- [x] `src/scieasy/blocks/ai/ai_block.py` — rename internal `run_id` → `block_execution_id` [ADR-038 §5.2] → branch `feat/issue-933/d38-2-4a-backend-rest`
- [x] `src/scieasy/blocks/ai/run_dir.py` — rename path to use `block_execution_id` [ADR-038 §5.2] → branch `feat/issue-933/d38-2-4a-backend-rest`
- [x] Pytest covers all 4 routes (happy path + 404 + validation errors) → `tests/api/test_runs_routes.py` (20 tests) + `tests/core/test_methods_export.py` (10 tests)
- [ ] CI green; PR merged into tracking branch

### Phase D38-2.4b — Frontend Lineage tab SKELETON (Owner: SD38-4b, 1 agent — VERY detailed comments) [ADR-038 §6 Phase 3 frontend skeleton]

- [x] Sub-issue opened; parallel with D38-2.4a → https://github.com/zjzcpj/SciEasy/issues/934
- [x] `frontend/src/components/Lineage/LineageTab.tsx` (NEW skeleton, comments cover state shape, props, layout per ADR §3.8) → commit 2bf9cf2
- [x] `frontend/src/components/Lineage/RunsList.tsx` (NEW skeleton, comments cover reverse-chrono list, click handler, live-updating running row per OQ-3, copy strings) → commit 2bf9cf2
- [x] `frontend/src/components/Lineage/RunDetail.tsx` (NEW skeleton, comments cover right pane layout, click block → expand, Re-run button, Export methods button) → commit 2bf9cf2
- [x] `frontend/src/components/Lineage/BlockExecutionCard.tsx` (NEW skeleton, comments cover expandable per-block view with params + I/O DataObject list) → commit 2bf9cf2
- [x] `frontend/src/components/Lineage/MethodsExportDialog.tsx` (NEW skeleton, comments cover preview + copy + download .md) → commit 2bf9cf2
- [x] `frontend/src/components/Lineage/RerunDialog.tsx` (NEW skeleton, comments cover input + env validation warnings per ADR §3.6) → commit 2bf9cf2
- [x] `frontend/src/store/lineageSlice.ts` (NEW skeleton, comments cover state shape: runs list, selected run cache, loading state) → commit 2bf9cf2
- [x] `frontend/src/components/BottomPanel.tsx` — remove "jobs" from `ALL_TABS` (line 33) + label (line 27); render `<LineageTab/>` when activeTab === "lineage" [ADR-038 §3.8] → commit 2bf9cf2
- [x] `frontend/src/types/ui.ts` — remove `"jobs"` from `BottomTab` discriminated union → commit 2bf9cf2
- [x] `frontend/src/store/index.ts` — register lineageSlice → commit 2bf9cf2
- [x] Vitest skeleton tests with detailed test-plan docstrings (xfail/skip) → commit 2bf9cf2 (31 new skipped tests across LineageTab/RunsList/RunDetail/lineageSlice)
- [ ] PR merged into tracking branch

### Phase D38-2.4c — Frontend Lineage tab IMPL (Owner: ID38-4c, 1 agent) [ADR-038 §6 Phase 3 frontend impl]

- [x] Sub-issue opened; depends on D38-2.4a + D38-2.4b merged → #939
- [x] All skeleton bodies filled → feat/issue-939/d38-2-4c-lineage-impl
- [x] `frontend/src/lib/api.ts` — `getRuns`, `getRun`, `getRunMethods`, `rerunRun` functions wired → feat/issue-939/d38-2-4c-lineage-impl
- [x] Vitest xfail/skip flipped to passing → 32/32 lineage tests green (4 files), full suite 230 passed
- [x] **Mandatory live Chrome smoke** on Lineage tab — open project, seed lineage.db with 3 runs (completed/failed/completed), verify Lineage tab shows "3 runs recorded" + three rows with correct status icons, click first row → RunDetail populates "Run cda6e7d1 / Workflow image_pipeline / Status completed" + 3 BlockExecutionCards, expand a card → resolved params JSON renders correctly, click Export methods → dialog renders full markdown (run id / environment / YAML / blocks sections), click Re-run → dialog renders green "No drift detected" banner + Re-run/Cancel buttons, click failed run → expand third block → error section renders "TypeError: division by zero". GIF: `C:/Users/jiazh/Downloads/d38-2-4c-lineage-smoke.gif`
- [ ] CI green; PR merged into tracking branch

### Phase D38-2.5 — Polish + status promotion (Owner: ID38-5, 1 agent) [ADR-038 §6 Phase 4]

- [x] Methods markdown template refinement — verified §3.7 Q1-Q4 coverage end-to-end; added a partial-rerun banner when `execute_from_block_id` + `parent_run_id` are both set (ADR §3.6a), and surfaced `error` / `cancelled` termination detail in a dedicated fenced section instead of trailing the bullet → branch `feat/issue-948/d38-2-5-polish` (`src/scieasy/core/lineage/methods_export.py`)
- [x] Re-run chain visualization — `RunDetail.tsx` makes `parent_run_id` a clickable button that dispatches `selectRun(parent)`, and renders an amber banner when `execute_from_block_id` is set explaining upstream blocks were reused from the parent run (ADR §3.6a). Upstream-skipped blocks have no `block_executions` row per ADR §3.6a so the blocks list is intentionally partial; canvas DAG grey-out remains out of scope here. → branch `feat/issue-948/d38-2-5-polish` (`frontend/src/components/Lineage/RunDetail.tsx`)
- [x] ADR-038 status `proposed` → `accepted` (in `docs/adr/ADR-038.md`) → branch `feat/issue-948/d38-2-5-polish`
- [x] Verify ADR-032 status `superseded by ADR-038` (already done in Phase 0) → `docs/adr/ADR-032.md:15` reads `**Status**: **superseded by ADR-038**`
- [ ] CI green; PR merged into tracking branch

### Phase D38-3.1a — Drift audit (Owner: AD38-3a, no-context agent)

- [x] No-context audit dispatched (ADR-038 + refactored docs only) → PR #957
- [x] Report at `docs/audit/2026-05-15-adr-038-drift-audit.md` → 4 P1 + 6 P2 + 3 P3
- [x] Findings categorized P1/P2/P3 against ADR/docs → audit report

### Phase D38-3.1b — Bug / robustness / wiring audit (Owner: AD38-3b, context-aware agent)

- [x] Context-aware audit dispatched (session PRs + diffs + sub-issues) → PR #960
- [x] **Mandatory live Chrome smoke** on Lineage tab + Run from here + Rerun dialog → `docs/audit/d38-3-1b-smoke.gif` (28 frames, 5.0 MB)
- [x] Codex auto-review reconciled for every D38 sub-issue PR → audit report § "Codex reconciliation"
- [x] Report at `docs/audit/2026-05-15-adr-038-bug-audit.md` → 3 P1 + 7 P2 + 4 P3 findings; PR #960

### Phase D38-3.2 — Fix (Owner: FD38, 1 agent)

- [x] Manager classifies every P1/P2 finding from both audits; overrides any auditor "defer" calls for P1/P2 per overnight merge protocol → dispatch + fix PR
- [x] Fix PR merged into `track/adr-038/lineage-db`; CI green → fix/issue-963/d38-3-2-audit-findings (#963)
- [x] Drift log updated if any owned-file violations during cascade → no drift, only owned-files modified

#### D38-3.2 detailed scoreboard

P1 findings (7 of 7 fixed):
- [x] D38-3.1a P1-1 / D38-3.1b P1-3 — terminal-event payload extension → scheduler.py `_build_block_terminal_data`
- [x] D38-3.1a P1-2 — registry `"unknown"` removal → `BlockRegistrationError`
- [x] D38-3.1a P1-4 — legacy `LineageRecord` shell deletion → record.py + __init__.py
- [x] D38-3.1b P1-1 — Windows file handle pin → LineageStore open-per-call
- [x] D38-3.1b P1-2 — recorder unsubscribe → `LineageRecorder.dispose()`
- [!] D38-3.1a P1-3 — `FrameworkMeta.lineage_id` wired (DEFERRED follow-up: requires cross-process plumbing)

Phase 3.5 hazard:
- [x] H-A1 — `LineageStore.set_pending_git_commit(workflow_id, sha)` → store.py + test suite

P2 (10 of 13 fixed, rest deferred with documented rationale on PR):
- [x] D38-3.1a — stale ADR-032 Phase 2a comment → scheduler.py
- [x] D38-3.1a — `_record_io` misnamed `outputs` param → recorder.py
- [x] D38-3.1a — engine compat shim removal tracker → lineage_recorder.py
- [x] D38-3.1a — MetadataStore shim private `_conn.execute` → `LineageStore.execute_query`
- [x] D38-3.1a P2 / D38-3.1b P2-4 — `parent_run_id` on rerun → runtime.py + routes/runs.py
- [x] D38-3.1b P2-5 — `"jobs"` localStorage migration → already merged in PR #944's store/index.ts
- [x] D38-3.1b P2-6 — RerunDialog conflate rerun + refresh → already merged in PR #951's RerunDialog.tsx
- [x] D38-3.1b P2-7 — `block_count` defaults to 0 → already merged in PR #944's api.ts
- [x] D38-3.1b P3-3 — `INSERT OR IGNORE` on block_executions re-emit → store.py
- [!] D38-3.1a P2 — workflow_dirty / size_bytes / mtime_at_write columns (deferred follow-up)
- [!] D38-3.1a P2 — upsert_data_object NULL on rehydrate (deferred follow-up)
- [!] D38-3.1b P2-2 — Collection wire format mismatch (deferred follow-up — not reproduced)
- [!] D38-3.1b P2-3 — produced_by_execution FK loss (deferred — already mitigated by scheduler split)

P3 (file as follow-up issues; not blocking):
- [!] D38-3.1a P3-1 — `cli/main.py` lineage parity
- [!] D38-3.1a P3-2 — ARCHITECTURE.md write-flow doc mismatch
- [!] D38-3.1a P3-3 — outdated "Phase D38-2.3 will…" comments
- [!] D38-3.1b P3-1 — SQL LIMIT pagination
- [!] D38-3.1b P3-2 — validate `execute_from_block_id` against DAG
- [!] D38-3.1b P3-4 — conftest sys.path hardening

---

## ADR-039 — Git-backed source version control (track/adr-039/git-versioning)

### Phase D39-2.1 — Refactor-scope audit+fix (Owner: AID39-1, 1 agent)

- [x] Agent audits + fixes in single PR:
  - [x] Remove `ApiRuntime.bump_revision` / `current_revision` [ADR-039 §5.2] → commit e981303
  - [x] Remove `If-Match` revision handling in `api/routes/workflows.py` [ADR-039 §5.2] → commit e981303
  - [x] Audit frontend for `If-Match` header usage (ADR may have missed callsites in `api.ts`); remove if found → audit comment https://github.com/zjzcpj/SciEasy/issues/915#issuecomment-4459281951 (frontend already clean; one stale test fixture revision dropped)
  - [x] Extend `api/routes/workflow_watcher.py` to detect `.git/HEAD` changes → emit `git.head_changed` event [ADR-039 §3.8, §5.2] → commit e981303
  - [x] Subscribe to `git.head_changed` in `api/ws.py` and forward to clients → commit e981303
- [ ] CI green; PR merged into `track/adr-039/git-versioning` → PR pending

### Phase D39-2.2a — Backend engine + REST + auto-init SKELETON (Owner: SD39-2a, 1 agent, detailed comments) [ADR-039 §6 Phase 1 skeleton]

- [x] Sub-issue opened, branch off tracking branch → https://github.com/zjzcpj/SciEasy/issues/921
- [x] `src/scieasy/core/versioning/__init__.py` (NEW) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/core/versioning/git_engine.py` (NEW skeleton; comments enumerate all subprocess wrappers: commit / log / diff / restore / branch ops / merge / cherry-pick / stash; plumbing-format parsing) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/core/versioning/git_binary.py` (NEW skeleton; comments cover bundle path + system fallback for dev CLI) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/core/versioning/gitignore_template.py` (NEW skeleton; comments give exact template per ADR §3.3) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/core/versioning/status.py` (NEW skeleton; dirty/modified helpers) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/core/versioning/watcher.py` (NEW skeleton; .git/HEAD + refs polling) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/api/routes/git.py` (NEW skeleton; all ~15 endpoints stubbed with route + signature + docstring per ADR §3.5 table) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `desktop/scripts/fetch-git-portable.ps1` (NEW skeleton; build-step comments for Windows MinGit) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `desktop/scripts/fetch-git-portable.sh` (NEW skeleton; macOS universal2 + Linux musl static build comments) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [~] `desktop/package.json` — add `desktop/resources/git/` to bundle assets → DEFERRED: file does not exist yet (ADR-037 packaging pipeline pending); documented in `fetch-git-portable.sh` top-of-file note so ADR-037 implementer adds the asset list entry when bundler config lands
- [x] `src/scieasy/api/runtime.py::create_project` — auto-init call stub [ADR-039 §3.2] → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/api/runtime.py::open_project` (or equivalent project-switch path) — re-init stub → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/api/runtime.py::start_workflow` — pre-run auto-commit hook stub (TODO marker for D39-2.2b) → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/api/app.py` — register git router, watcher install in lifespan → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] `src/scieasy/cli/main.py::init` — CLI git-init parity stub → branch feat/issue-921/d39-2-2a-backend-skeleton
- [x] Pytest stubs (xfail) with test-plan docstrings for: commit/restore round-trip, auto-init idempotence, merge FF/clean/conflict, cherry-pick, stash CRUD → tests/core/test_git_engine.py (17 xfail) + tests/api/test_git_endpoints.py (21 xfail) + tests/cli/test_init_git_init.py (2 xfail); all xfail correctly under `pytest --timeout=60`
- [ ] PR merged into tracking branch

### Phase D39-2.2b — Backend engine + REST + auto-init IMPL (Owner: ID39-2b, 1 agent) [ADR-039 §6 Phase 1 impl]

- [x] Sub-issue opened (#925); depends on D39-2.2a merged
- [x] All subprocess calls implemented with `--porcelain=v2` / `--format=...` plumbing flags only → branch feat/issue-925/d39-2-2b-backend-impl
- [x] Auto-init writes `.gitignore` + initial commit per ADR §3.2-3.3
- [x] Pre-run auto-commit hook in `start_workflow`: dirty → `auto:` commit (lineage-row write deferred to D39-2.5 via TODO marker — D38-2.2 schema not on this tracking branch yet)
- [x] All 21 REST endpoints functional; full pytest coverage including merge (FF/clean/conflict), cherry-pick, stash CRUD (38 engine tests + 28 endpoint tests + 2 CLI tests)
- [x] Bundled-git locator works on Windows (MinGit) AND falls back to system `git` for dev CLI; `SCIEASY_GIT_BUNDLE_ROOT` env override for tests
- [ ] CI green; PR merged into tracking branch

### Phase D39-2.3a — Frontend UI core SKELETON (Owner: SD39-3a, 1 agent — VERY detailed comments) [ADR-039 §6 Phase 2 skeleton]

- [x] Sub-issue opened, depends on D39-2.2b merged → https://github.com/zjzcpj/SciEasy/issues/928
- [x] `frontend/src/components/Git/CommitDialog.tsx` (NEW skeleton; comments cover pre-filled template per ADR §3.5, message validation, commit button + cancel) → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/components/Git/GitHistoryList.tsx` (NEW skeleton; comments cover reverse-chrono list, filter dropdown (Manual/All/Auto/Agent per ADR §3.4, §3.4a, §3.5c), click-to-diff, click-to-restore actions, virtualization plan) → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/components/Git/GitDiffModal.tsx` (NEW skeleton; comments cover `react-diff-viewer-continued` integration) → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/components/Git/BranchPicker.tsx` (NEW skeleton; comments cover dropdown UI, list/create/switch/delete actions, merge + cherry-pick entries) → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/components/Git/GitStatusBadge.tsx` (NEW skeleton; comments cover toolbar dirty/clean indicator) → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/components/Git/StashApplyDialog.tsx` (NEW skeleton; comments cover stash-on-restore prompt) → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/components/Git/StashListPanel.tsx` (NEW skeleton; comments cover Stash drawer: list/save/apply/drop) → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/store/gitSlice.ts` (NEW skeleton; comments cover state shape — branches, currentBranch, log cache, filter state, mergeInProgress) → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/components/Toolbar.tsx` — mount slots for BranchPicker + GitStatusBadge + Commit button (skeleton mounts placeholders) → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/lib/api.ts` — `gitCommit / gitLog / gitDiff / gitRestore / gitBranches / gitBranchSwitch / gitBranchCreate / gitBranchDelete / gitStatus / gitMerge / gitCherryPick / gitStashList / gitStashSave / gitStashApply / gitStashDrop / gitMergeStageFile / gitMergeComplete / gitMergeAbort` function stubs → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/store/index.ts` — register gitSlice → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] `frontend/src/hooks/useWebSocket.ts` — `git.head_changed` case wired to `gitSlice.invalidateHistory()` → branch `feat/issue-928/d39-2-3a-frontend-skeleton`
- [x] Vitest skeleton tests with detailed docstrings → 25 pure-helper assertions pass; 29 `it.skip` cases each carry test-plan docstrings for D39-2.3b
- [ ] PR merged into tracking branch

### Phase D39-2.3b — Frontend UI core IMPL (Owner: ID39-3b, 1 agent) [ADR-039 §6 Phase 2 impl]

- [x] Sub-issue opened; depends on D39-2.3a merged → #932
- [x] All skeleton bodies filled → branch `feat/issue-932/d39-2-3b-frontend-impl`
- [x] **Mandatory live Chrome smoke**: commit dialog open → type → submit → status flips to clean; BranchPicker dropdown → Create branch → switch — GIF `d39-2-3b-smoke.gif`
- [ ] CI green; PR merged into tracking branch

### Phase D39-2.4a — Conflict resolution + branch graph SKELETON (Owner: SD39-4a, 1 agent — VERY detailed algorithm comments) [ADR-039 §6 Phase 3 skeleton]

- [x] Sub-issue opened, depends on D39-2.3b merged → #941
- [x] `frontend/src/components/Git/MergeFlow.tsx` (NEW skeleton; comments cover FF/clean/conflict path orchestration per ADR §3.5a) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] `frontend/src/components/Git/ConflictResolveView.tsx` (NEW skeleton; comments cover conflicted-file list, status badges, Mark Resolved / Complete Merge / Abort Merge buttons) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] `frontend/src/components/Git/ConflictMarkerDecoration.ts` (NEW skeleton; comments cover Monaco decoration provider for `<<<<<< ====== >>>>>>` regions + inline action widgets per ADR §3.5a; `parseConflictRegions` kept implemented as a pure helper) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] `frontend/src/components/Git/GitGraph/laneAssign.ts` (NEW skeleton; FULL pseudocode comments transcribing ADR §3.5b algorithm sketch; `maxLane` kept implemented) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] `frontend/src/components/Git/GitGraph/edgeRouter.ts` (NEW skeleton; bezier curve math comments; `buildShaIndex` kept implemented) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] `frontend/src/components/Git/GitGraph/GraphSVG.tsx` (NEW skeleton; SVG rendering plan: dots, edges, labels, filter dimming) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] `frontend/src/components/Git/GitGraph/colorPalette.ts` (NEW skeleton; branch color rotation + layout constants; PALETTE + colorForIndex implemented) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] `frontend/src/components/Git/GitGraph/interactions.ts` (NEW skeleton; hover preview, click→diff/checkout, virtualization with `@tanstack/react-virtual`) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] `frontend/src/components/Git/GitGraph/integration.ts` (NEW skeleton; gitSlice consumption, filter-state integration, theme) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] `frontend/src/components/CodeEditor.tsx` (ADR-036) — extend with ConflictMarkerDecoration registration when active file is in conflict state (skeleton stub; subscribes to existing `gitSlice.mergeInProgress.conflicted_files` — no new slice field needed) → branch `feat/issue-941/d39-2-4a-conflict-graph-skeleton`
- [x] Vitest skeleton tests for laneAssign / edgeRouter / conflict-region detection → 20 pure-helper assertions pass; 21 `it.skip` cases each carry detailed test-plan docstrings + fixture sketches for D39-2.4b
- [ ] PR merged into tracking branch

### Phase D39-2.4b — Conflict resolution + branch graph IMPL (Owner: ID39-4b, 1 agent) [ADR-039 §6 Phase 3 impl]

- [x] Sub-issue opened; depends on D39-2.4a merged → #947
- [x] All skeleton bodies filled → branch `feat/issue-947/d39-2-4b-conflict-graph-impl`
- [x] Lane assignment unit tests on synthetic DAGs (linear, branch, merge, multi-merge fixtures) → `frontend/src/components/Git/GitGraph/__tests__/laneAssign.test.ts` (11 tests pass)
- [x] Conflict-region detection tests against fixtures with `<<<<<<` markers → `frontend/src/components/Git/__tests__/ConflictResolveView.test.tsx` (18 tests pass incl. parser + text-splice + view)
- [~] **Mandatory live Chrome smoke**: synthesize a merge conflict in a test project, open ConflictResolveView, click Accept Current / Accept Incoming / Accept Both / Manual edit, run `git status` to confirm git-state correctness, click Complete Merge
- [ ] CI green; PR merged into tracking branch

### Phase D39-2.5 — Polish + ADR-038 integration (Owner: ID39-5, 1 agent, sequential) [ADR-039 §6 Phase 4]

- [x] **Hard dependency**: D38-2.4c merged into `track/adr-038/lineage-db` AND D39-2.4b merged into `track/adr-039/git-versioning` → verified (commits 738dd11 + de9bdca)
- [x] Wires `runs.workflow_git_commit` to `git_engine.head_state()` inside `start_workflow` (replaces D39-2.2b TODO) → branch `feat/issue-954/d39-2-5-polish-integration`: `WorkflowRun.workflow_git_commit` field + defensive `lineage_store.set_pending_git_commit` hook for the Phase 4 final-merge
- [x] "Restore this run's workflow" button on Lineage tab calls `gitRestore({commit_sha, files: [workflow_yaml_path]})` → `frontend/src/components/Lineage/RunDetail.tsx` (NEW on 039 branch since 038's Lineage tab merges in at Phase 4); exports `RestoreWorkflowButton`, `runRestoreWorkflow`, `workflowYamlPathForRun`
- [x] Verifies ADR-035 AI Block / ADR-034 PTY agent flows emit commits with `agent:` prefix → grep confirmed neither `blocks/ai/ai_block.py` nor `engine/pty_control.py` invokes `GitEngine.commit()` directly today (commits originate from the MCP server wrapper + the agent's own shell inside the PTY); convention now cross-referenced in both module docstrings
- [x] Agent commit prefix convention documented in `docs/cli-integration.md` → already present from Phase 0 architecture refactor (CHANGELOG #904); module-level docstrings on `ai_block.py` + `pty_control.py` updated to cite ADR-039 §3.4a explicitly
- [x] ADR-039 status `proposed` → `accepted` (in `docs/adr/ADR-039.md`) → flipped, references D39-2.5 (issue #954)
- [ ] CI green; PR merged into tracking branch → PR pending

### Phase D39-3.1 — Combined audit (Owner: AD39-3, context-aware agent)

- [x] Single audit agent dispatched (has session context per user spec) → PR #966
- [x] Verifies (a) skeleton-vs-ADR consistency, (b) impl-vs-design consistency, (c) wiring reliability → `docs/audit/2026-05-15-adr-039-combined-audit.md` (commit 902f341)
- [!] **Mandatory live Chrome smoke**: commit / branch / merge / conflict resolution / graph render → DEFERRED (Chrome MCP interactive browser-pick incompatible with non-interactive agent dispatch). D39-3.2 fix dispatch MUST execute. See report §"Smoke test status".
- [x] Codex auto-review reconciled for every D39 sub-issue PR → all 23 reviews across 10 PRs already reconciled in implementer-side follow-up commits; tabulated in report
- [x] Report at `docs/audit/2026-05-15-adr-039-combined-audit.md` → PR #966 commit 902f341

### Phase D39-3.2 — Fix (Owner: FD39, 1 agent)

- [x] Manager classifies P1/P2; overrides auditor "defer" per overnight merge protocol → #968 dispatch fix-agent on `fix/issue-968/d39-3-2-audit-fixes`
- [x] **P1-A** dual git-watcher collapse → deleted `core/versioning/watcher.py`, removed `app.py:84-112` construction, removed `__init__.py` re-export; watchdog `_GitHeadHandler` is single source of truth emitting canonical `commit_sha`
- [x] **P1-B** H-A1 defensive guard verified → `runtime.py:1333` `getattr`+`callable()` chain retained; 2 regression tests added in `tests/api/test_workflow_run_git.py` (no-hook + hook-raises). NO D38-side change in this PR (that's D38-3.2).
- [x] **P2-A** AIBlock `agent:` prefix docstring corrected → removed stale reference to non-existent `mcp__scieasy__git_commit` MCP tool; documents actual enforcement (system-prompt + agent's own `git commit -m` in PTY)
- [x] **P2-B** project-switch watcher restart → resolved for free by P1-A collapse (workflow_watcher's `start_for_project` is already invoked from `routes/projects.py::_restart_workflow_watcher`)
- [x] **P2-C** `GitEngine.commit()` empty-repo edge → branches on `rev-parse --verify HEAD`; falls back to `ls-files --cached` when HEAD absent. Test added.
- [x] **P3 nits** filed as follow-up issue #969 (is_repository worktree, merge FF heuristic, log parser empty-body)
- [ ] **Mandatory live Chrome smoke** (11 scenarios deferred from D39-3.1) → GIF in PR body
- [ ] Fix PR merged into `track/adr-039/git-versioning`; CI green

---

## Phase 3.5 — Cross-track integration audit (Owner: A35 — 1 agent)

> Added 2026-05-15 by user direction. Runs **after** D38-3.2 and D39-3.2
> are merged into their respective tracking branches, **before** Phase 4
> e2e. Catches integration-layer drift that the per-track audits
> structurally cannot see.

### Why this phase exists

The Phase 3 audits (D38-3.1a / D38-3.1b / D39-3.1) scope each track
independently. They cannot detect issues that only manifest at the
integration boundary between ADR-038 and ADR-039:

- `runs.workflow_git_commit` exists in the lineage schema (ADR-038) but
  the git engine (ADR-039) is the only source of the SHA value — must
  be wired through `start_workflow` (D39-2.5 owns this wiring).
- `runs.workflow_dirty` flag depends on `git_engine.status().dirty` —
  same wiring chain.
- Lineage tab "Restore this run's workflow" button (ADR-038 §3.8) is
  supposed to call `gitRestore({commit_sha: run.workflow_git_commit, files: [workflow_yaml_path]})` (ADR-039 §3.5) — frontend cross-slice
  call.
- Agent commit prefix `agent:` (ADR-039 §3.4a) must be emitted by the
  AI Block flow (ADR-035) and the PTY embedded coding agent (ADR-034) —
  verify on the real code paths.
- `frontend/src/store/index.ts` registers both `lineageSlice` and
  `gitSlice` — verify no naming collisions or selector overlap.
- `src/scieasy/api/runtime.py::start_workflow` is touched by D38-2.2
  (LineageRecorder wire) AND D39-2.2b (pre-run auto-commit hook) AND
  D39-2.5 (the SHA-to-runs.workflow_git_commit field write). Verify
  the call order, the error-handling interleave, and the on-failure
  fallback semantics for each combination of (dirty tree, lineage
  recorder available, git engine available).
- `frontend/src/hooks/useWebSocket.ts` `git.head_changed` event handler
  exists (D39-2.1) but should also invalidate the Lineage tab's runs
  query (so external git commits surface in the UI). Verify the
  handler reaches both slices.
- `BlockRegistry.hot_reload()` should fire on git branch switch (per
  ADR's "blocks alongside git" doc). Verify event wiring.

### Owned files (whitelist — audit only, NO code modification)

NEW audit output:
- `docs/audit/2026-05-15-adr-038-039-integration-audit.md` — categorized
  finding list (P1 must-fix-before-integration / P2 should-fix / P3 nit),
  one row per integration concern, with file + line citations.

The agent does NOT edit any source file — fix lands in the dedicated
Phase 3.5 fix step that runs **after Phase 4 e2e** per user direction.

### Audit scope (the agent's mandatory checklist)

Section A — backend wiring:
- [x] `start_workflow` interleave of LineageRecorder (D38) + pre-run auto-commit (D39): order correct (P1-1 fix); SHA + `workflow_dirty` flow into `_build_lineage_recorder` → `RunRecord` constructor → DB INSERT.
- [x] `create_project` / `open_project`: both auto-init lineage.db (D38) and auto-init git repo (D39); failure modes covered by `test_open_project_degraded_modes.py` (P2-1).
- [x] `runs.workflow_git_commit` field populated end-to-end on every `start_workflow` call (verified by `test_workflow_run_git.py::test_start_workflow_threads_git_commit_into_lineage_insert`).
- [x] **HAZARD H-A1**: resolved by P1-1 fix. The previously-broken `set_pending_git_commit` UPDATE-after-INSERT pattern is replaced with INSERT-time SHA via `_build_lineage_recorder(workflow_git_commit=...)`.
- [ ] Agent commits emit `agent:` prefix from both ADR-035 (AI Block) and ADR-034 (PTY) flows. Phase 3.5 audit P3-1 — follow-up issue.
- [x] EventBus `git.head_changed` events fire and reach gitSlice (UI badge); lineage cache is server-authoritative so `git.head_changed` does NOT invalidate it (audit P3-2, by design).
- [x] `BlockRegistry.hot_reload()` triggers on branch switch (P2-2 fix at `routes/git.py::branch_switch`).

Section B — frontend cross-slice:
- [x] `store/index.ts` registers both slices without selector collision.
- [x] Lineage tab "Restore this run's workflow" calls `gitRestore` correctly (covered by `RunDetail.restore.test.tsx`).
- [x] `useWebSocket.ts` `git.head_changed` invalidates the git slice as needed (lineage slice is server-authoritative; audit P3-2 documents the design choice).
- [x] Toolbar / BottomPanel mount both Git + Lineage components without layout clash.
- [x] `Toolbar.tsx` shows GitStatusBadge + BranchPicker simultaneously with `BottomPanel.tsx` Lineage + Git tabs.

Section C — schema / contract:
- [x] `lineage.db.runs` schema present in DB after Phase D38-2.2 + D38-2.3 chain.
- [x] `block_version` force-injection (D38-2.2) does not break any block subclass shipped in `packages/scieasy-blocks-{imaging,lcms,srs}/`.
- [x] `metadata.db` deprecation shim still answers reads correctly from agent MCP tools (ADR-033 `inspect_data` / `get_lineage` / `preview_data`); deprecation warning suppressed at MCP import boundary (P2-4).
- [x] `If-Match` / `bump_revision` removal (D39-2.1) didn't leave dangling consumers in `frontend/src/lib/api.ts` or anywhere else.

Section D — file conflicts between tracks:
- [x] `src/scieasy/api/runtime.py` final state has both D38 and D39 wirings present and ordered correctly (P1-1 + P1-2 + P1-3).
- [x] `frontend/src/store/index.ts` final state has both slices registered.
- [x] `frontend/src/hooks/useWebSocket.ts` final state handles `git.head_changed`.
- [x] `src/scieasy/api/app.py` lifespan correctly initializes lineage store + git watcher (both `runs` and `git_routes` routers registered).
- [x] **HAZARD H-D1**: resolved by P1-4 fix. RunDetail.tsx keeps ADR-038 full body + ADR-039 named exports + Restore button in footer.
- [x] **HAZARD H-D2**: resolved alongside H-D1 (D39-2.5 out-of-scope items all converge cleanly except for the RunDetail.tsx conflict that P1-4 handles).

Section E — Codex review reconcile:
- [x] Codex reply-on-comment drift on PRs #926, #927, #960 (audit P2-5) — posted retroactively on PR open.

### Definition of done

1. Audit report at `docs/audit/2026-05-15-adr-038-039-integration-audit.md`.
2. P1/P2/P3 categorization per finding.
3. PR opened against `main` titled `chore(audit): D3.5 integration audit for ADR-038/039 cascade` (audit-only PR, no code changes).
4. All CI green.
5. Codex reconciled.

### Phase 3.5 fix (runs AFTER Phase 4 e2e per user direction)

After Phase 4 e2e completes, manager folds Phase 3.5 audit findings +
Phase 4 e2e findings into a single fix pass. P1 findings fixed before
final integration PRs to main. P2/P3 filed as follow-up issues if not
release-blockers.

- [x] Phase 3.5 audit dispatched → audit agent on `chore/audit-phase-3-5` branch (closes #971)
- [x] Audit report merged → report at `docs/audit/2026-05-15-adr-038-039-integration-audit.md`; PR opened against `main`
- [x] (Phase 3.5 fix) P1-1 set_pending_git_commit ordering — threaded SHA into `_build_lineage_recorder` → `RunRecord` constructor → integration PR for #978
- [x] (Phase 3.5 fix) P1-2 workflow_dirty plumbing — same path now also threads `workflow_dirty` bool → integration PR for #978
- [x] (Phase 3.5 fix) P1-3 delete_project union — `lineage_store.close()` + `_rmtree_force` → integration PR for #978
- [x] (Phase 3.5 fix) P1-4 H-D1 RunDetail.tsx — 038 full body + 039 named exports + Restore button in footer → integration PR for #978
- [x] (Phase 3.5 fix) P1-5 — resolved by P1-4
- [x] (Phase 3.5 fix) P2-1 degraded-mode tests — `tests/api/test_open_project_degraded_modes.py` → integration PR for #978
- [x] (Phase 3.5 fix) P2-2 BlockRegistry.hot_reload on branch switch → integration PR for #978
- [x] (Phase 3.5 fix) P2-3 RunDetail.test.tsx split — new `RunDetail.restore.test.tsx` → integration PR for #978
- [x] (Phase 3.5 fix) P2-4 MetadataStore DeprecationWarning suppression at MCP boundary → integration PR for #978
- [x] (Phase 3.5 fix) P2-5 Codex reply-on-comment drift on #926/#927/#960 — posted retroactively on PR open
- [x] Final integration PR opened → closes #978; merge of `track/adr-038/lineage-db` + `track/adr-039/git-versioning` on top of main hotfix #977

---

## Test phase checklist (e2e — manager runs in hotfix mode)

### Phase 4a — ADR-038 e2e (Chrome smoke)

- [ ] Chrome opens via `mcp__claude-in-chrome__tabs_create_mcp` → SciEasy GUI on free port
- [ ] Create new project `e2e-038`
- [ ] Generate synthetic bead TIFF (256×256, ~5 ellipses, ~6741 bright px; reuse fixture from ADR-036 e2e sub-test (d))
- [ ] Build workflow in GUI: `imaging.load_image → imaging.threshold(otsu) → imaging.save_image`
- [ ] Save workflow YAML; click Run **5 times**
- [ ] Click "Run from here" on `threshold` block once (creates 6th run with `execute_from_block_id`)
- [ ] Open Lineage tab

**Pass criteria:**

- [ ] **(a)** Each of 6 runs answers ADR-038's 4 user questions through Lineage tab UI: workflow YAML snapshot, block list with versions, per-block resolved params, per-block I/O DataObject references visible by clicking the row
- [ ] **(b)** "Run from here" run has `execute_from_block_id = "threshold_<n>"` and `parent_run_id` pointing to a prior run; upstream blocks greyed-out per ADR §3.6a
- [ ] **(c)** GUI visual check matches ADR §3.8 layout (two-pane runs list + run detail); click handlers respond correctly
- [ ] **(d)** "Export methods" produces markdown file matching `methods_export.py` template
- [ ] **(e1)** Delete `<project>/.scieasy/lineage.db` while GUI closed; reopen project; new empty db auto-created; Lineage tab shows "no runs yet" without crash
- [ ] **(e2)** Delete a block from canvas, save workflow, re-add the block, save again; Lineage tab still displays all prior runs (block_executions rows preserved)
- [ ] **(e3)** Delete workflow YAML file from disk; reopen project; Lineage tab still shows all prior runs of that workflow (workflow_yaml_snapshot inline in `runs` table per ADR §3.1 — confirms user's recollection)
- [ ] **(f)** Open AI chat in GUI; ask "Show me lineage for last 5 runs of image_pipeline — list each run's blocks, params, outputs"; agent writes SQL against `<project>/.scieasy/lineage.db`; compare to ground truth from direct `sqlite3` query
- [ ] **(f-followup)** If agent fails or hallucinates, file follow-up issue to update agent system prompt
- [ ] GIF recorded via `mcp__claude-in-chrome__gif_creator`

### Phase 4b — ADR-039 e2e (Chrome smoke)

- [ ] Create new project `e2e-039` with same bead workflow
- [ ] Add `hello_world` custom block via GUI (ADR-036 "New custom block" affordance), trivial pass-through body

**Test 1 — manual + auto + manual commits:**

- [ ] Click Commit button — manual commit 1 created
- [ ] Click Run — pre-run auto-commit: clean tree → no commit; force dirty edit → Run again → `auto:` commit fires
- [ ] Delete threshold block from canvas, save, click Commit — manual commit 2
- [ ] History panel with default filter "Manual milestones" shows 2 commits
- [ ] Filter "All" shows 3 commits (2 manual + 1 `auto:`)

**Test 2 — agent commit:**

- [ ] Open AI chat; instruct agent to make a change and commit it
- [ ] History (filter: All) shows agent commit with `agent:` prefix + 🤖 icon per ADR §3.4a
- [ ] If missing: file follow-up issue for agent system prompt update

**Test 3 — branch + checkout + canvas/editor sync:**

- [ ] BranchPicker → create branch `experiment-1`
- [ ] On `experiment-1`: modify workflow YAML (remove a block) + modify custom block code in CodeEditor; commit
- [ ] Switch to `main` via BranchPicker → canvas reverts; CodeEditor reverts
- [ ] Switch back to `experiment-1` → canvas + CodeEditor update again

**Test 4 — GUI merge clean:**

- [ ] On `main`, BranchPicker → "Merge into current" → select `experiment-1`
- [ ] Result: clean or FF merge; verify Graph view topology

**Test 5 — filter:**

- [ ] Cycle filter dropdown (Manual milestones / All / Auto only); verify visibility flips
- [ ] GitGraph dims filtered commits to small grey dots per ADR §3.5c

**Test 6 — conflict via CLI, resolve via GUI:**

- [ ] CLI: `git checkout -b conflict-branch`, modify workflow YAML's same line differently, `git commit -am 'conflict edit'`, `git checkout main`
- [ ] GUI: BranchPicker → Merge → `conflict-branch`; verify MergeFlow shows "conflict" path
- [ ] ConflictResolveView opens; conflicted file opens in CodeEditor with `<<<<<< / ====== / >>>>>>` markers + inline action buttons
- [ ] Click Accept Both → Mark Resolved → Complete Merge
- [ ] Verify `git status` clean; merge commit in History

**Pass criteria:**

- [ ] **(a)** Commit button + branch CRUD + filter all functional
- [ ] **(b)** Auto-commit functional (`auto:` prefix; `runs.workflow_dirty = 0` after auto-commit)
- [ ] **(c)** Git graph renders correctly (lanes, edges, colors, branch labels)
- [ ] **(d)** Agent updates git via terminal; commit shows `agent:` prefix
- [ ] **(e)** Conflict resolution UI works (Monaco decorations, inline buttons, Mark Resolved → Complete Merge round-trip)
- [ ] **(f)** Branch checkout updates canvas + CodeEditor in sync
- [ ] **(g)** Conflict resolution finalizes clean merge commit visible in History
- [ ] GIF recorded

---

## Acceptance criteria

- [ ] Phase 0 docs PR merged by user; main has refactored ARCHITECTURE.md + PROJECT_TREE.md + related ADRs
- [ ] All 21 sub-issue PRs merged into their tracking branches (D38: 10 PRs; D39: 10 PRs; minus one shared = ~20 PRs)
- [ ] Both tracking-branch `[DO NOT MERGE]` umbrella PRs remain open through e2e
- [ ] Every checkbox in this document checked with an artifact link
- [ ] Phase 4a all 6 pass-criteria green; agent system prompt issue filed if (f) failed
- [ ] Phase 4b all 7 pass-criteria green; agent system prompt issue filed if (d) failed
- [ ] Two final integration PRs (one per ADR) opened against main with conflict resolution in `runtime.py` + `store/index.ts`; user reviews + merges
- [ ] ADR-038 status `accepted`; ADR-032 status `superseded by ADR-038`; ADR-039 status `accepted`
- [ ] No drift: every tick has a corresponding artifact (commit, PR comment, test result, audit-report path) the manager can point to

---

## Out-of-scope from docs audit (filed as GitHub issues)

> Populated during Phase 0.75 from the docs-audit report. Each entry: audit excerpt → issue URL.

- **OOS-1** (P3-2 in audit): `PROJECT_TREE.md` line 83-84 still describes `core/proxy.py` as ViewProxy lazy-loading accessor, but ARCHITECTURE.md Appendix B (line 3256) marks ViewProxy eliminated by ADR-031. Pre-existing drift unrelated to ADR-038/039. → https://github.com/zjzcpj/SciEasy/issues/908

---

## Drift log (append-only)

> Format: `YYYY-MM-DD HH:MM — agent <name> on PR #<n> ticked "<row>" but artifact missing / out-of-scope file <path> modified. Action: <revert / required additional commit / escalation>.`

(empty until first violation)

---

## Known issues queued for audit phase

### AI Block MCP-signal write/read race (RESOLVED — PR #962, 2026-05-15)

**Status.** Resolved by PR `fix/issue-962/ai-block-atomic-signal-write`
(closes #962 + #909). Fix A applied to `tests/blocks/ai/conftest.py`
(`StubAgent._emit` now uses `tempfile.mkstemp` + `os.replace` for all
three signal-file writes — `finish_ai_block.json` happy path,
`finish_ai_block.json` deliberate-error path, and `mark_done.json`).
Fix B was a no-op: production `mcp__scieasy__finish_ai_block`
(`src/scieasy/ai/agent/mcp/tools_workflow.py:744`) already used
`_atomic_write_text`. Regression locked by
`tests/blocks/ai/test_completion_race.py` (two deterministic
threading.Event-coordinated tests; without-fix mode raises the
documented `ValueError`, with-fix mode returns `MCP_FINISH_TOOL`).

- [x] Fix A — atomic write in `StubAgent._emit` (`tests/blocks/ai/conftest.py`)
- [x] Fix B — production write site audited; already atomic via `_atomic_write_text`
- [x] Regression test added (`tests/blocks/ai/test_completion_race.py`)
- [x] Existing 57 AIBlock + AI tests still pass

**Symptom.** Intermittent failures on **all** AIBlock skeleton tests that
write `signals/finish_ai_block.json` via the `StubAgent._emit` happy
path — most often on Python 3.11 (~1-in-30 frequency), occasionally on
3.13. Error surfaces as:

```
ValueError: AIBlock completion: malformed MCP signal at
  .../signals/finish_ai_block.json:
  Expecting value: line 1 column 1 (char 0)
```

Hits during the cascade (2026-05-15): #905 baseline, PR #926 (D38-2.2
Test py3.13), PR #931 (D38-2.3 Test py3.13), PR #940 (D39-2.3b Test
py3.11), PR #944 (D38-2.4c Test py3.11). Every hit cleared on
`gh run rerun --failed`. Issue #909 tracks the first-noticed symptom
but only describes one test.

**Root cause — TOCTOU race between writer and reader.**

- *Writer* (`tests/blocks/ai/conftest.py:103`, `StubAgent._emit`
  background thread): `(signals / "finish_ai_block.json").write_text(json.dumps(...))`.
  `Path.write_text` is **non-atomic**: it `open("w")` → truncates to 0
  bytes → `f.write(data)` → `f.close()`.
- *Reader* (`src/scieasy/blocks/ai/completion.py:152-157`,
  `CompletionWatcher.wait` polling loop, main thread):
  `if mcp_path.exists(): payload = json.loads(mcp_path.read_text(...))`.
  Raises `ValueError(... "malformed MCP signal ...")` on `json.JSONDecodeError`.

If the polling tick lands between the truncate and the write, the
reader sees a 0-byte file and `json.loads("")` raises
`JSONDecodeError: Expecting value: line 1 column 1` which the watcher
re-raises as `ValueError("... malformed MCP signal ...")` — fatal for
the test, but actually a transient artifact of non-atomic IO.

**Why PR #905 / #909 's fix did not solve it.** PR #905 only relaxed
the regex on `test_run_validation_fail_returns_error_state` from
`"is empty"` to `r"is empty|Expecting value|malformed MCP signal"`.
That test **intentionally** writes malformed JSON (`finish_via="error"`)
so the relaxed regex hides cross-stdlib message-format drift in that
one error-path test. It does nothing for the **happy-path** tests
(`test_run_writes_manifest_with_correct_shape`,
`test_run_request_pty_tab_with_safe_permission`, etc.), which were
never supposed to encounter a malformed-signal error in the first
place — those are racing on the writer's truncate window.

**Why Python 3.11 is more affected than 3.13.** GIL scheduling
granularity + stdlib IO buffering changed between versions; 3.11
surfaces the race window more often. Same code path can race on any
version.

**Fix plan (D38-3.1b bug-audit fix pass).** Apply A + B; leave the
reader strict.

| # | Change | File | Rationale |
|---|---|---|---|
| A | Atomic write in `StubAgent._emit` | `tests/blocks/ai/conftest.py` `_emit()` around lines 102-103 (the `finish_via == "mcp"` branch and the `mark_done` branch) — use `tempfile.NamedTemporaryFile(dir=signals, delete=False)` + `os.replace(tmp, target)` | Closes the race in the test fixture; immediately stabilises CI |
| B | Atomic write in production MCP server | Wherever the real `mcp__scieasy__finish_ai_block` tool writes `finish_ai_block.json` (per ADR-035; locate via `grep -r finish_ai_block` and inspect the MCP tools module) — same `tempfile + os.replace` pattern | Avoids the same race biting real agent runs where AIBlock's polling and the MCP tool run in different processes |
| C | (NOT recommended) Reader-side retry | `src/scieasy/blocks/ai/completion.py:154` | Rejected: weakens watcher contract, masks future real bugs where writer crashes mid-write |

**Tests to add.** A regression test in `tests/blocks/ai/test_completion.py`
that asserts `CompletionWatcher.wait` survives a deliberately-induced
truncate-window race (use a wrapper that calls `open("w").close()` then
sleeps before writing the real JSON; without the fix the watcher must
fail, with the fix it must succeed).

**Out-of-scope reminder.** Issue #909 (existing, OPEN) covers the
regex-match flavour of the symptom. Fix PR should close #909 + open a
new issue explicitly framed as "MCP-signal atomic-write race" before
the audit phase, so #909 retires cleanly with the right rationale.

**Owner.** D38-3.1b bug/wiring audit agent (context-aware, with Chrome
smoke). The fix lands in the D38-3.2 fix PR alongside any other findings
that audit surfaces.

- 2026-05-15 — D39-2.3b (PR #932) mounted `BranchPicker` + `GitStatusBadge` + `CommitDialog` + `StashListPanel` + `MergeFlow` directly into `Toolbar.tsx`, causing horizontal overflow on narrow viewports, and shipped `GitHistoryList.tsx` (commit history + List/Graph view toggle) without mounting it anywhere in the production UI; the D39-3.1 combined audit (PR #948) deferred the Chrome smoke and did not catch the orphan. Resolved in #972 by moving every Git surface into a dedicated `Git` BottomPanel tab (`frontend/src/components/Git/GitTab.tsx`) that mounts `GitHistoryList`, restoring access to commit history + branch graph. → PR #972 (feat/issue-972/git-bottom-panel-tab)
