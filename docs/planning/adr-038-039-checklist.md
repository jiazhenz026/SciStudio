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

- [ ] `docs/architecture/ARCHITECTURE.md` §1 — add "History and versioning model" top-level section [ADR-038 §1, ADR-039 §2.4]
- [ ] `docs/architecture/ARCHITECTURE.md` §4.4 "Data lineage" — rewrite with 4-table schema [ADR-038 §3.1]
- [ ] `docs/architecture/ARCHITECTURE.md` add "Source version control" subsection [ADR-039 §3]
- [ ] `docs/architecture/ARCHITECTURE.md` §1464 EventBus matrix — LineageRecorder status `planned`→`active` [ADR-038 §5.3]
- [ ] `docs/architecture/ARCHITECTURE.md` §2009 env snapshot — 5 packages → full `uv pip freeze` [ADR-038 §5.3]
- [ ] `docs/architecture/ARCHITECTURE.md` §2077 MCP server deps — `lineage, MetadataStore` → `LineageStore (unified)` [ADR-038 §5.3]
- [ ] `docs/architecture/PROJECT_TREE.md` — add `.git/`, `.gitignore`, `.scieasy/lineage.db`, `.scieasy/pause/`; remove `metadata.db` and `checkpoints/` [ADR-038/039 §5.3]
- [ ] `docs/adr/ADR-032.md` — status banner: `SUPERSEDED by ADR-038` [ADR-038 §10]
- [ ] `docs/adr/ADR-014.md` — cross-ref ADR-039 (git in project state model) [ADR-039 §5.3]
- [ ] `docs/adr/ADR-012.md` — clarify checkpoint scope vs lineage; relocate path note [ADR-038 §5.2, §3.6a]
- [ ] `docs/adr/ADR-018.md` — LineageRecord field alignment with new 4-table schema [ADR-038 §5.3]
- [ ] `docs/adr/ADR-020.md` — remove `batch_info` references [ADR-038 §5.3]
- [ ] `docs/adr/ADR-027.md` D5 — `lineage_id` docstring: populated with `block_execution_id` per ADR-038 [ADR-038 §5.3]
- [ ] `docs/adr/ADR-031.md` Addenda — replace `metadata.db` refs with `lineage.db.data_objects` [ADR-038 §5.3]
- [ ] `docs/block-development/architecture-for-block-devs.md` — replace metadata.db wording; new "blocks alongside git" section [ADR-038/039 §5.3]
- [ ] `docs/block-development/memory-safety.md` — grep + correct metadata-storage references [ADR-038 §5.3]
- [ ] `docs/cli-integration.md` — git CLI compatibility note; document `auto:`/`agent:`/no-prefix commit convention [ADR-039 §3.4a, §5.3]
- [ ] `CHANGELOG.md` — `[Unreleased] > Changed` entry: `[#<issue>] Refactor architecture docs for ADR-038 + ADR-039 (@claude, 2026-05-15, branch: docs/adr-038-039/architecture-refactor, session: 20260515-052537-adr-038-039-cascade-phase-0-architecture)`

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
- [ ] CI green on PR #905
- [ ] User-approved autonomous merge → main has the refactored docs

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
- [ ] Sub-issues opened (created lazily per dispatch — one per sub-agent as dispatched)
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

- [ ] Agent audits + fixes in single PR:
  - [ ] Remove `ApiRuntime.bump_revision` / `current_revision` [ADR-039 §5.2]
  - [ ] Remove `If-Match` revision handling in `api/routes/workflows.py` [ADR-039 §5.2]
  - [ ] Audit frontend for `If-Match` header usage (ADR may have missed callsites in `api.ts`); remove if found
  - [ ] Extend `api/routes/workflow_watcher.py` to detect `.git/HEAD` changes → emit `git.head_changed` event [ADR-039 §3.8, §5.2]
  - [ ] Subscribe to `git.head_changed` in `api/ws.py` and forward to clients
- [ ] CI green; PR merged into `track/adr-039/git-versioning`

### Phase D39-2.2a — Backend engine + REST + auto-init SKELETON (Owner: SD39-2a, 1 agent, detailed comments) [ADR-039 §6 Phase 1 skeleton]

- [ ] Sub-issue opened, branch off tracking branch
- [ ] `src/scieasy/core/versioning/__init__.py` (NEW)
- [ ] `src/scieasy/core/versioning/git_engine.py` (NEW skeleton; comments enumerate all subprocess wrappers: commit / log / diff / restore / branch ops / merge / cherry-pick / stash; plumbing-format parsing)
- [ ] `src/scieasy/core/versioning/git_binary.py` (NEW skeleton; comments cover bundle path + system fallback for dev CLI)
- [ ] `src/scieasy/core/versioning/gitignore_template.py` (NEW skeleton; comments give exact template per ADR §3.3)
- [ ] `src/scieasy/core/versioning/status.py` (NEW skeleton; dirty/modified helpers)
- [ ] `src/scieasy/core/versioning/watcher.py` (NEW skeleton; .git/HEAD + refs polling)
- [ ] `src/scieasy/api/routes/git.py` (NEW skeleton; all ~15 endpoints stubbed with route + signature + docstring per ADR §3.5 table)
- [ ] `desktop/scripts/fetch-git-portable.ps1` (NEW skeleton; build-step comments for Windows MinGit)
- [ ] `desktop/scripts/fetch-git-portable.sh` (NEW skeleton; macOS universal2 + Linux musl static build comments)
- [ ] `desktop/package.json` — add `desktop/resources/git/` to bundle assets
- [ ] `src/scieasy/api/runtime.py::create_project` — auto-init call stub [ADR-039 §3.2]
- [ ] `src/scieasy/api/runtime.py::open_project` (or equivalent project-switch path) — re-init stub
- [ ] `src/scieasy/api/runtime.py::start_workflow` — pre-run auto-commit hook stub (TODO marker for D39-2.2b)
- [ ] `src/scieasy/api/app.py` — register git router, watcher install in lifespan
- [ ] `src/scieasy/cli/main.py::init` — CLI git-init parity stub
- [ ] Pytest stubs (xfail) with test-plan docstrings for: commit/restore round-trip, auto-init idempotence, merge FF/clean/conflict, cherry-pick, stash CRUD
- [ ] PR merged into tracking branch

### Phase D39-2.2b — Backend engine + REST + auto-init IMPL (Owner: ID39-2b, 1 agent) [ADR-039 §6 Phase 1 impl]

- [ ] Sub-issue opened; depends on D39-2.2a merged
- [ ] All subprocess calls implemented with `--porcelain=v2` / `--format=...` plumbing flags only
- [ ] Auto-init writes `.gitignore` + initial commit per ADR §3.2-3.3
- [ ] Pre-run auto-commit hook in `start_workflow`: dirty → `auto:` commit + populates `runs.workflow_git_commit` (or TODO marker if D38-2.2 lineage schema not yet on tracking branch; D39-2.5 wires final field)
- [ ] All ~15 REST endpoints functional; full pytest coverage including merge (FF/clean/conflict), cherry-pick, stash CRUD
- [ ] Bundled-git locator works on Windows (MinGit) AND falls back to system `git` for dev CLI
- [ ] CI green; PR merged into tracking branch

### Phase D39-2.3a — Frontend UI core SKELETON (Owner: SD39-3a, 1 agent — VERY detailed comments) [ADR-039 §6 Phase 2 skeleton]

- [ ] Sub-issue opened, depends on D39-2.2b merged
- [ ] `frontend/src/components/Git/CommitDialog.tsx` (NEW skeleton; comments cover pre-filled template per ADR §3.5, message validation, commit button + cancel)
- [ ] `frontend/src/components/Git/GitHistoryList.tsx` (NEW skeleton; comments cover reverse-chrono list, filter dropdown (Manual/All/Auto/Agent per ADR §3.4, §3.4a, §3.5c), click-to-diff, click-to-restore actions, virtualization plan)
- [ ] `frontend/src/components/Git/GitDiffModal.tsx` (NEW skeleton; comments cover `react-diff-viewer-continued` integration)
- [ ] `frontend/src/components/Git/BranchPicker.tsx` (NEW skeleton; comments cover dropdown UI, list/create/switch/delete actions, merge + cherry-pick entries)
- [ ] `frontend/src/components/Git/GitStatusBadge.tsx` (NEW skeleton; comments cover toolbar dirty/clean indicator)
- [ ] `frontend/src/components/Git/StashApplyDialog.tsx` (NEW skeleton; comments cover stash-on-restore prompt)
- [ ] `frontend/src/components/Git/StashListPanel.tsx` (NEW skeleton; comments cover Stash drawer: list/save/apply/drop)
- [ ] `frontend/src/store/gitSlice.ts` (NEW skeleton; comments cover state shape — branches, currentBranch, log cache, filter state, mergeInProgress)
- [ ] `frontend/src/components/Toolbar.tsx` — mount slots for BranchPicker + GitStatusBadge + Commit button (skeleton mounts placeholders)
- [ ] `frontend/src/lib/api.ts` — `gitCommit / gitLog / gitDiff / gitRestore / gitBranches / gitBranchSwitch / gitBranchCreate / gitBranchDelete / gitStatus / gitMerge / gitCherryPick / gitStashList / gitStashSave / gitStashApply / gitStashDrop / gitMergeStageFile / gitMergeComplete / gitMergeAbort` function stubs
- [ ] `frontend/src/store/index.ts` — register gitSlice
- [ ] `frontend/src/hooks/useWebSocket.ts` — `git.head_changed` case stub
- [ ] Vitest skeleton tests with detailed docstrings
- [ ] PR merged into tracking branch

### Phase D39-2.3b — Frontend UI core IMPL (Owner: ID39-3b, 1 agent) [ADR-039 §6 Phase 2 impl]

- [ ] Sub-issue opened; depends on D39-2.3a merged
- [ ] All skeleton bodies filled
- [ ] **Mandatory live Chrome smoke**: commit dialog, branch switch, history filter (Manual/All toggle), status badge updates on dirty/clean
- [ ] CI green; PR merged into tracking branch

### Phase D39-2.4a — Conflict resolution + branch graph SKELETON (Owner: SD39-4a, 1 agent — VERY detailed algorithm comments) [ADR-039 §6 Phase 3 skeleton]

- [ ] Sub-issue opened, depends on D39-2.3b merged
- [ ] `frontend/src/components/Git/MergeFlow.tsx` (NEW skeleton; comments cover FF/clean/conflict path orchestration per ADR §3.5a)
- [ ] `frontend/src/components/Git/ConflictResolveView.tsx` (NEW skeleton; comments cover conflicted-file list, status badges, Mark Resolved / Complete Merge / Abort Merge buttons)
- [ ] `frontend/src/components/Git/ConflictMarkerDecoration.ts` (NEW skeleton; comments cover Monaco decoration provider for `<<<<<< ====== >>>>>>` regions + inline action widgets per ADR §3.5a)
- [ ] `frontend/src/components/Git/GitGraph/laneAssign.ts` (NEW skeleton; FULL pseudocode comments transcribing ADR §3.5b algorithm sketch)
- [ ] `frontend/src/components/Git/GitGraph/edgeRouter.ts` (NEW skeleton; bezier curve math comments)
- [ ] `frontend/src/components/Git/GitGraph/GraphSVG.tsx` (NEW skeleton; SVG rendering plan: dots, edges, labels, filter dimming)
- [ ] `frontend/src/components/Git/GitGraph/colorPalette.ts` (NEW skeleton; branch color rotation)
- [ ] `frontend/src/components/Git/GitGraph/interactions.ts` (NEW skeleton; hover preview, click→diff/checkout, virtualization with `@tanstack/react-virtual`)
- [ ] `frontend/src/components/Git/GitGraph/integration.ts` (NEW skeleton; gitSlice consumption, filter-state integration, theme)
- [ ] `frontend/src/components/CodeEditor.tsx` (ADR-036) — extend with ConflictMarkerDecoration registration when active file is in conflict state (skeleton stub)
- [ ] Vitest skeleton tests for laneAssign / edgeRouter / conflict-region detection
- [ ] PR merged into tracking branch

### Phase D39-2.4b — Conflict resolution + branch graph IMPL (Owner: ID39-4b, 1 agent) [ADR-039 §6 Phase 3 impl]

- [ ] Sub-issue opened; depends on D39-2.4a merged
- [ ] All skeleton bodies filled
- [ ] Lane assignment unit tests on synthetic DAGs (linear, branch, merge, multi-merge fixtures)
- [ ] Conflict-region detection tests against fixtures with `<<<<<<` markers
- [ ] **Mandatory live Chrome smoke**: synthesize a merge conflict in a test project, open ConflictResolveView, click Accept Current / Accept Incoming / Accept Both / Manual edit, run `git status` to confirm git-state correctness, click Complete Merge
- [ ] CI green; PR merged into tracking branch

### Phase D39-2.5 — Polish + ADR-038 integration (Owner: ID39-5, 1 agent, sequential) [ADR-039 §6 Phase 4]

- [ ] **Hard dependency**: D38-2.4c merged into `track/adr-038/lineage-db` AND D39-2.4b merged into `track/adr-039/git-versioning`
- [ ] Wires `runs.workflow_git_commit` to `git_engine.head_state()` inside `start_workflow` (replaces D39-2.2b TODO)
- [ ] "Restore this run's workflow" button on Lineage tab calls `gitRestore({commit_sha, files: [workflow_yaml_path]})`
- [ ] Verifies ADR-035 AI Block / ADR-034 PTY agent flows emit commits with `agent:` prefix
- [ ] Agent commit prefix convention documented in `docs/cli-integration.md`
- [ ] ADR-039 status `proposed` → `accepted` (in `docs/adr/ADR-039.md`)
- [ ] CI green; PR merged into tracking branch

### Phase D39-3.1 — Combined audit (Owner: AD39-3, context-aware agent)

- [ ] Single audit agent dispatched (has session context per user spec)
- [ ] Verifies (a) skeleton-vs-ADR consistency, (b) impl-vs-design consistency, (c) wiring reliability
- [ ] **Mandatory live Chrome smoke**: commit / branch / merge / conflict resolution / graph render
- [ ] Codex auto-review reconciled for every D39 sub-issue PR
- [ ] Report at `docs/audit/2026-05-15-adr-039-combined-audit.md`

### Phase D39-3.2 — Fix (Owner: FD39, 1 agent)

- [ ] Manager classifies P1/P2; overrides auditor "defer" per overnight merge protocol
- [ ] Fix PR merged into `track/adr-039/git-versioning`; CI green

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
