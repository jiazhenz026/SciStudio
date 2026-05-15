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

- [ ] Sub-issue opened, branch `feat/issue-<N>/d38-wire-up-schema` off `track/adr-038/lineage-db`
- [ ] `src/scieasy/core/lineage/` new package: `__init__.py`, `store.py` (4-table), `record.py`, `recorder.py` (moved from engine/), `environment.py`, `graph.py`, `run_context.py` [ADR-038 §3.1, §5.1]
- [ ] `src/scieasy/engine/scheduler.py` — construct LineageRecorder; extend BLOCK_DONE event data (`config`, `block_version`, `environment`, `input_object_ids`, `output_object_ids`) [ADR-038 §3.2]
- [ ] `src/scieasy/engine/lineage_recorder.py` — relocated to core; engine stub deleted with redirect comment [ADR-038 §5.1, §5.2]
- [ ] `src/scieasy/engine/runners/local.py:229` — lift `environment` from worker envelope into event data [ADR-038 §5.2]
- [ ] `src/scieasy/api/runtime.py::start_workflow` — create RunRecord, construct LineageRecorder, pass to DAGScheduler, finalize on completion [ADR-038 §3.2]
- [ ] `src/scieasy/api/deps.py::get_lineage_store` — rewrite to return unified store [ADR-038 §5.2]
- [ ] `src/scieasy/api/app.py` — register `runs` router placeholder [ADR-038 §5.2]
- [ ] `src/scieasy/blocks/registry.py` — force-inject `block_version` from `importlib.metadata`; fail loudly on resolution failure [ADR-038 §3.3]
- [ ] `tests/engine/test_lineage_recorder.py` + `tests/core/test_lineage*.py` — migrate to new schema
- [ ] Smoke test passes: 3-block workflow run produces 1 row in `runs`, 3 in `block_executions`, ≥3 in `data_objects`, ≥6 in `block_io`
- [ ] CI green; mandatory live test of full happy-path workflow execution
- [ ] PR merged into `track/adr-038/lineage-db`

### Phase D38-2.3 — Collapse metadata.db (Owner: ID38-3, 1 agent, migration) [ADR-038 §6 Phase 2]

- [ ] Sub-issue opened, branch off tracking branch after D38-2.2 merged
- [ ] `src/scieasy/core/metadata_store.py` → 6-month deprecation shim re-exporting unified store + DeprecationWarning [ADR-038 §5.2]
- [ ] `src/scieasy/core/meta/framework.py` — `FrameworkMeta.lineage_id` populated with `block_execution_id` in run context [ADR-038 §3.2, §5.2]
- [ ] `src/scieasy/engine/scheduler.py::_persist_output_metadata` — write to new `data_objects` table [ADR-038 §5.2]
- [ ] `src/scieasy/engine/checkpoint.py` — relocate `<project>/checkpoints/` to `<project>/.scieasy/pause/`; docstring clarifies pause/resume scope vs lineage [ADR-038 §5.2]
- [ ] Project-open auto-creates lineage.db if missing; no historical metadata.db migration (per user direction 2026-05-15)
- [ ] Tests pass; CI green; PR merged into tracking branch

### Phase D38-2.4a — Backend REST + AIBlock rename (Owner: ID38-4a, 1 agent) [ADR-038 §6 Phase 3 backend]

- [ ] Sub-issue opened; parallel with D38-2.4b
- [ ] `src/scieasy/api/routes/runs.py` (NEW) — GET /api/runs, GET /api/runs/{run_id}, GET /api/runs/{run_id}/methods, POST /api/runs/{run_id}/rerun [ADR-038 §3.7, §3.8]
- [ ] `src/scieasy/core/lineage/methods_export.py` (NEW) — markdown methods renderer [ADR-038 §5.1]
- [ ] `src/scieasy/blocks/ai/ai_block.py` — rename internal `run_id` → `block_execution_id` [ADR-038 §5.2]
- [ ] `src/scieasy/blocks/ai/run_dir.py` — rename path to use `block_execution_id` [ADR-038 §5.2]
- [ ] Pytest covers all 4 routes (happy path + 404 + validation errors)
- [ ] CI green; PR merged into tracking branch

### Phase D38-2.4b — Frontend Lineage tab SKELETON (Owner: SD38-4b, 1 agent — VERY detailed comments) [ADR-038 §6 Phase 3 frontend skeleton]

- [ ] Sub-issue opened; parallel with D38-2.4a
- [ ] `frontend/src/components/Lineage/LineageTab.tsx` (NEW skeleton, comments cover state shape, props, layout per ADR §3.8)
- [ ] `frontend/src/components/Lineage/RunsList.tsx` (NEW skeleton, comments cover reverse-chrono list, click handler, live-updating running row per OQ-3, copy strings)
- [ ] `frontend/src/components/Lineage/RunDetail.tsx` (NEW skeleton, comments cover right pane layout, click block → expand, Re-run button, Export methods button)
- [ ] `frontend/src/components/Lineage/BlockExecutionCard.tsx` (NEW skeleton, comments cover expandable per-block view with params + I/O DataObject list)
- [ ] `frontend/src/components/Lineage/MethodsExportDialog.tsx` (NEW skeleton, comments cover preview + copy + download .md)
- [ ] `frontend/src/components/Lineage/RerunDialog.tsx` (NEW skeleton, comments cover input + env validation warnings per ADR §3.6)
- [ ] `frontend/src/store/lineageSlice.ts` (NEW skeleton, comments cover state shape: runs list, selected run cache, loading state)
- [ ] `frontend/src/components/BottomPanel.tsx` — remove "jobs" from `ALL_TABS` (line 33) + label (line 27); render `<LineageTab/>` when activeTab === "lineage" [ADR-038 §3.8]
- [ ] `frontend/src/types/ui.ts` — remove `"jobs"` from `BottomTab` discriminated union
- [ ] `frontend/src/store/index.ts` — register lineageSlice
- [ ] Vitest skeleton tests with detailed test-plan docstrings (xfail/skip)
- [ ] PR merged into tracking branch

### Phase D38-2.4c — Frontend Lineage tab IMPL (Owner: ID38-4c, 1 agent) [ADR-038 §6 Phase 3 frontend impl]

- [ ] Sub-issue opened; depends on D38-2.4a + D38-2.4b merged
- [ ] All skeleton bodies filled
- [ ] `frontend/src/lib/api.ts` — `getRuns`, `getRun`, `getRunMethods`, `rerunRun` functions wired
- [ ] Vitest xfail/skip flipped to passing
- [ ] **Mandatory live Chrome smoke** on Lineage tab — open project, run 2 workflows, verify Lineage tab populates, click a run, click a block, click Re-run, click Export methods, verify each affordance
- [ ] CI green; PR merged into tracking branch

### Phase D38-2.5 — Polish + status promotion (Owner: ID38-5, 1 agent) [ADR-038 §6 Phase 4]

- [ ] Methods markdown template refinement; re-run chain visualization (`parent_run_id` linkage in UI)
- [ ] ADR-038 status `proposed` → `accepted` (in `docs/adr/ADR-038.md`)
- [ ] Verify ADR-032 status `superseded by ADR-038` (already done in Phase 0)
- [ ] CI green; PR merged into tracking branch

### Phase D38-3.1a — Drift audit (Owner: AD38-3a, no-context agent)

- [ ] No-context audit dispatched (ADR-038 + refactored docs only)
- [ ] Report at `docs/audit/2026-05-15-adr-038-drift-audit.md`
- [ ] Findings categorized P1/P2/P3 against ADR/docs

### Phase D38-3.1b — Bug / robustness / wiring audit (Owner: AD38-3b, context-aware agent)

- [ ] Context-aware audit dispatched (session PRs + diffs + sub-issues)
- [ ] **Mandatory live Chrome smoke** on Lineage tab + Run from here + Rerun dialog
- [ ] Codex auto-review reconciled for every D38 sub-issue PR
- [ ] Report at `docs/audit/2026-05-15-adr-038-bug-audit.md`

### Phase D38-3.2 — Fix (Owner: FD38, 1 agent)

- [ ] Manager classifies every P1/P2 finding from both audits; overrides any auditor "defer" calls for P1/P2 per overnight merge protocol
- [ ] Fix PR merged into `track/adr-038/lineage-db`; CI green
- [ ] Drift log updated if any owned-file violations during cascade

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
