# Phase 3.5 — ADR-038/039 cross-track integration audit

Date: 2026-05-15
Auditor: Phase 3.5 audit agent (no implementation scope)
ADR-038 track head: `6436561` (`Merge pull request #967 from zjzcpj/fix/issue-963/d38-3-2-audit-findings`)
ADR-039 track head: `afb850d` (`Merge pull request #970 from zjzcpj/fix/issue-968/d39-3-2-audit-fixes`)
Main baseline: `b05bb1b`
Simulated integration approach: **Approach A — local `git merge origin/track/adr-039/git-versioning`** on a worktree branch (`_audit_integration_simulation`) created from `origin/track/adr-038/lineage-db`. The simulation produced 8 conflicted files; conflicts were inspected in place and the merge was aborted before reporting. No fix code was written.

## Summary

**Verdict: pass-with-fixes** — the integration is feasible and the two known hazards (H-A1, H-D1) are well-anticipated. **Three new P1 findings** require source edits at integration time, all in `src/scistudio/api/runtime.py` and one in `src/scistudio/core/lineage/store.py`. **Six P2** and **five P3** findings are documented for the integration / Phase 4 fix PR to decide upon.

The H-A1 hazard is **half-resolved**: D38-3.2 (PR #967) added `LineageStore.set_pending_git_commit`, so the method now exists — but the **call ordering** in the integrated `start_workflow` will stamp the SHA on the **previous** run because the 039 code calls `set_pending_git_commit` **before** the 038 `_build_lineage_recorder` runs `LineageStore.insert_run`. See finding P1-1 below.

The H-D1 hazard is **real and unresolved**: the two `RunDetail.tsx` files have **different `export` shapes**, so a naive textual merge will lose either the full ADR-038 UI body (load from store, BlockExecutionCard list, methods/rerun dialogs) or the ADR-039 `RestoreWorkflowButton` + `runRestoreWorkflow` + `workflowYamlPathForRun` exports. Both shapes must coexist post-integration.

## Conflict resolution log (simulation)

`git merge origin/track/adr-039/git-versioning` on a fresh branch of `origin/track/adr-038/lineage-db` produced **8 textual conflicts**. Resolution intent is recorded for the Phase 4 integration PR (the audit itself made no edits).

| File | Conflict shape | Resolution intent |
|---|---|---|
| `frontend/src/components/Lineage/RunDetail.tsx` | add/add (different file bodies) | **Manual reconcile**. Keep ADR-038 full body; overlay 039's `RestoreWorkflowButton` into the affordance row alongside Re-run / Export methods; re-export `RestoreWorkflowButton`, `runRestoreWorkflow`, `workflowYamlPathForRun` from the merged file so 039's test imports still resolve. See **P1-4** below. |
| `frontend/src/components/Lineage/__tests__/RunDetail.test.tsx` | add/add (different test bodies) | **Union** — two test suites with non-overlapping `describe` blocks. Either keep both files (rename one to `RunDetail.restore.test.tsx`) or merge into a single file. See **P2-3** below. |
| `frontend/src/lib/api.ts` | content (`lineage.*` namespace vs flat `git*` methods) | **Union** — both blocks are non-overlapping methods on the `api` object literal. Simple concat. |
| `frontend/src/store/index.ts` | content (import + slice spread for `createLineageSlice` vs `createGitSlice`) | **Union** — import both, spread both. |
| `frontend/src/store/types.ts` | content (intersection chain ends in `LineageSlice` vs `GitSlice`) | **Union** — chain `& LineageSlice & GitSlice`. |
| `frontend/tsconfig.tsbuildinfo` | generated build artifact | **Regenerate** — delete file or take either side; `tsc --build` rewrites it. Not a real conflict. |
| `src/scistudio/api/app.py` | content (router imports + `app.include_router(runs.router)` vs `git_routes.router`) | **Union** — import both routers, include both. |
| `src/scistudio/api/runtime.py` | content (three conflict regions: `open_project` lineage init vs git auto-init; `delete_project` store close + rmtree; `start_workflow` git auto-commit prepended) | **Union with reordering** — see findings **P1-1** (start_workflow ordering), **P1-2** (workflow_dirty plumbing), **P1-3** (delete_project rmtree union), and **P2-1** (open_project degraded-mode tests) below. |

Additional non-conflicting incoming files (clean merge): every `frontend/src/components/Git/**` skeleton + impl tree, every `src/scistudio/core/versioning/**`, `desktop/scripts/fetch-git-portable.*`, `docs/audit/2026-05-15-adr-039-*.md`. None of these collide with track/adr-038.

## Section A — Backend wiring

### P1-1 (HAZARD H-A1, half-resolved → ordering bug) — `start_workflow` calls `set_pending_git_commit` BEFORE the run row exists

**File:** `src/scistudio/api/runtime.py` (integration state; lines ~1476–1564 on the 039 track / 1240–1331 on the 038 track once merged)

**What the audit found:**

- D38-3.2 (PR #967) added `LineageStore.set_pending_git_commit(workflow_id, sha)` at `src/scistudio/core/lineage/store.py:271` ([verified by `git show origin/track/adr-038/lineage-db:src/scistudio/core/lineage/store.py | sed -n '271,304p'`]). It executes `UPDATE runs SET workflow_git_commit = ? WHERE run_id = (SELECT run_id FROM runs WHERE workflow_id = ? ORDER BY started_at DESC LIMIT 1)`.
- D39-2.5 (PR #959) added the `set_pending_git_commit` **call** inside `ApiRuntime.start_workflow` ([`src/scistudio/api/runtime.py:1554-1564` on track/adr-039](https://github.com/zjzcpj/SciStudio/blob/track/adr-039/git-versioning/src/scistudio/api/runtime.py#L1554-L1564)). On the 039 track alone this is a no-op (no `lineage_store` exists) — D39-2.5's own test asserts the no-op path.
- On the integrated tree, the 039 call site runs **at the top of `start_workflow`, before** the 038 `_build_lineage_recorder` block (which calls `LineageRecorder.begin_run(run)` → `LineageStore.insert_run` and creates the `runs` row for THIS run). Result: the `SELECT run_id ... ORDER BY started_at DESC LIMIT 1` matches the **previous** run of the same workflow (or returns no rows for the very first run), so the SHA is silently stamped on the wrong row — or silently dropped if it's the first run.
- The Phase 4a e2e pass-criterion (a) "Each of 6 runs answers ADR-038's 4 user questions" includes the lineage row's `workflow_git_commit` join key. With this bug, runs N=1..5 carry SHA N-1's value (or NULL for N=1) instead of their own.

**Severity:** P1 — silent data corruption on the run's authoritative join key; cannot be detected without comparing to git head at insert time.

**Recommended fix (Phase 4 integration PR):**

In the merged `start_workflow`, move the `set_pending(workflow_id, workflow_git_commit)` call **after** `lineage_recorder = self._build_lineage_recorder(...)` and the `recorder.begin_run(run)` it executes internally. The reordered shape:

```python
def start_workflow(self, workflow_id, *, execute_from=None, parent_run_id=None):
    # 1. ADR-039 pre-run auto-commit (compute workflow_git_commit, do NOT call set_pending here)
    workflow_git_commit = self._maybe_pre_run_autocommit(workflow_id)

    # 2. Load workflow + build LineageRecorder + insert runs row
    workflow = self.load_workflow(workflow_id)
    lineage_recorder = self._build_lineage_recorder(
        workflow_id=workflow_id, workflow=workflow,
        execute_from=execute_from, parent_run_id=parent_run_id,
    )

    # 3. NOW the runs row exists — stamp the SHA on it.
    if workflow_git_commit and self.lineage_store is not None:
        try:
            self.lineage_store.set_pending_git_commit(workflow_id, workflow_git_commit)
        except Exception:
            logger.warning("ADR-039: set_pending_git_commit failed", exc_info=True)

    # 4. rest of start_workflow (scheduler, task, etc.) unchanged.
```

Better: thread the SHA through `_build_lineage_recorder`'s `RunRecord(workflow_git_commit=...)` constructor so the row gets the field at INSERT time. `RunRecord` already has `workflow_git_commit: str | None` (`src/scistudio/core/lineage/record.py:36`), so add a single keyword argument and replace `set_pending_git_commit` with an in-insert write. This eliminates the cross-table UPDATE entirely.

### P1-2 — `runs.workflow_dirty` is never populated despite the 039 code claiming it's "the source of truth"

**File:** `src/scistudio/api/runtime.py` (integration `start_workflow`, lines ~1500-1515 of the 039 source) and `src/scistudio/core/lineage/record.py:41` / `src/scistudio/core/lineage/store.py:64`.

**What the audit found:**

- `LineageStore.runs.workflow_dirty INTEGER NOT NULL` is part of the ADR-038 schema (`src/scistudio/core/lineage/store.py:64`).
- `RunRecord.workflow_dirty: int = 0` defaults to 0 on every insert (`src/scistudio/core/lineage/record.py:41`).
- `_build_lineage_recorder` never threads any value into this field (`src/scistudio/api/runtime.py:1347-1357` on the 038 track).
- D39-2.5's `start_workflow` comment at line 1504-1506 of the 039 source says: *"Degrade to `None` so the lineage row's `workflow_dirty=1` safety net (ADR-038 §3.1 + ADR-039 §3.4) is the source of truth instead."* — but **nothing ever sets `workflow_dirty=1`**.
- Phase 4a e2e pass-criterion (b) "Auto-commit functional (`auto:` prefix; `runs.workflow_dirty = 0` after auto-commit)" assumes this field works. Without the fix, the `=0` half is true trivially (default), but the dirty-tree-failed-to-commit detection is silent.
- D38-3.2 commit message explicitly lists "D38-3.1a P2 (workflow_dirty / size_bytes / mtime_at_write)" as **deferred** to follow-up — that follow-up is now this row.

**Severity:** P1 — the safety net the 039 auto-commit path advertises does not exist; a user looking at the Lineage tab cannot distinguish "ran against the committed tree" from "auto-commit failed; ran against an uncommitted tree."

**Recommended fix:** Add `set_pending_workflow_dirty(workflow_id, dirty: bool)` to `LineageStore` (mirror of `set_pending_git_commit`), or — preferred — thread `workflow_dirty` into `_build_lineage_recorder`'s `RunRecord` constructor at the same time as `workflow_git_commit` (P1-1). Set `workflow_dirty=True` when 039 auto-commit failed AND the tree was dirty; `False` otherwise. `engine.head_state().dirty` carries the input.

### P2-1 — `open_project` interleaves lineage init and git auto-init, but does not coordinate failure modes

**File:** `src/scistudio/api/runtime.py:670-711` (post-merge state)

**What the audit found:** Both inits are best-effort with their own `try/except`. After integration, `open_project` runs `_init_metadata_store` → `_init_lineage_store` (ADR-038) → git auto-init (ADR-039) → `_publish_mcp_port` in that order. The failure semantics are independent: lineage failure leaves `self.lineage_store = None`; git failure leaves `engine.is_repository` false. The project still opens. **This is correct** but undocumented.

**Severity:** P2 — works, but the degraded-mode matrix is not asserted by tests. The cascade checklist row "*on failure of either, degraded mode is correct*" requires a regression test.

**Recommended fix:** Add a test `tests/api/test_open_project_degraded_modes.py` covering 2×2 of (lineage init fails, git init fails). For each, assert project opens, the missing subsystem is `None`/false, and `start_workflow` still runs (skipping the failed side).

### P2-2 — Branch switch does NOT trigger `BlockRegistry.hot_reload()`

**File:** `src/scistudio/api/routes/git.py:208-216` (the `/branch/switch` endpoint)

**What the audit found:**

- The Phase 3.5 checklist Section A row says "*`BlockRegistry.hot_reload()` triggers on branch switch*" (per the ADR's "blocks alongside git" doc, `docs/block-development/architecture-for-block-devs.md`).
- `BlockRegistry.hot_reload` exists at `src/scistudio/blocks/registry.py:536`.
- The `/branch/switch` endpoint at `src/scistudio/api/routes/git.py:208-216` only calls `engine.branch_switch(body.branch_name)` and returns. There is no `runtime.refresh_block_registry()` call, no `runtime.block_registry.hot_reload()` call, no `git.head_changed` listener on the backend that triggers it (only the frontend listens on the WebSocket).
- Project-level custom blocks shipped under `<project>/blocks/` (per `docs/block-development/architecture-for-block-devs.md` "blocks alongside git" section) will not refresh when a branch switch swaps the on-disk block source files. The user sees the old version of the block until the next `open_project` or manual restart.

**Severity:** P2 — affects custom-block authors but not the core workflow YAML / built-in block paths. ADR-039 §3.5b "blocks alongside git" claims this works; the test suite does not exercise it.

**Recommended fix:** Inside `branch_switch` route handler (after `engine.branch_switch` succeeds), call `request.app.state.runtime.refresh_block_registry()`. Or subscribe `BlockRegistry.hot_reload` to the `git.head_changed` event in `ApiRuntime.__init__`. Test: switch branches between two branches that ship different `blocks/custom_block.py` bodies; assert the registry serves the new body on the second call.

### P3-1 — Agent `agent:` commit prefix is documented but never enforced or instructed

**Files:** `src/scistudio/ai/agent/system_prompt.py` (no occurrences of "agent:" prefix); `src/scistudio/blocks/ai/ai_block.py:34-36` (docstring acknowledges no enforcement)

**What the audit found:**

- ADR-039 §3.4a defines `agent:` as the commit prefix for AI-authored commits ([line 197](https://github.com/zjzcpj/SciStudio/blob/main/docs/adr/ADR-039.md#L197)).
- `ai_block.py:29-36` explicitly states the prefix is "enforced **convention-by-prompt**: the agent's system prompt (and `docs/cli-integration.md`) instructs claude / codex to prefix any `git commit -m` invocation it issues in its PTY shell with `agent:`."
- Grep across `src/scistudio/ai/agent/` for `"agent:"` returns **zero matches**. The system prompt at `src/scistudio/ai/agent/system_prompt.py` does not mention the prefix convention at all.
- D39-2.5 checklist row "Verifies ADR-035 AI Block / ADR-034 PTY agent flows emit commits with `agent:` prefix" is ticked but the verification was only "documented in `docs/cli-integration.md`" — the prompt itself is silent.
- Phase 4b e2e pass-criterion (d) "Agent updates git via terminal; commit shows `agent:` prefix" is expected to fail; the checklist already says "If missing: file follow-up issue for agent system prompt update".

**Severity:** P3 — pre-known gap, already in the e2e follow-up queue; not a release-blocker for integration.

**Recommended fix (post-integration, not in Phase 4 fix PR):** Update `src/scistudio/ai/agent/system_prompt.py` to instruct the agent to use `git commit -m "agent: ..."` for any commit it authors. File a tracking issue.

### Section A items verified clean

- **`git.head_changed` reaches the UI**: `src/scistudio/api/routes/workflow_watcher.py:304` (`_GitHeadHandler` class) emits the event; `src/scistudio/api/ws.py` forwards it; `frontend/src/hooks/useWebSocket.ts:147-166` consumes it and calls `useAppStore.getState().invalidateHistory()`. (See P3-2 for the lineage side.)
- **Dual watcher collapse (D39-3.2)**: `src/scistudio/api/routes/workflow_watcher.py` correctly attaches `.git/` as a second `Observer.schedule()` inside `WorkflowWatcher.start_for_project`. The collapse from the previously-separate `core.versioning.watcher.GitChangeWatcher` (asyncio-poll) into the unified watchdog Observer is sound; verified at `app.py:84-94` post-merge.

## Section B — Frontend cross-slice

### P2-3 — `frontend/src/components/Lineage/__tests__/RunDetail.test.tsx` add/add conflict needs a deliberate split

**Files:**

- `frontend/src/components/Lineage/__tests__/RunDetail.test.tsx` on track/adr-038 (full Lineage tab body tests, 436 lines)
- `frontend/src/components/Lineage/__tests__/RunDetail.test.tsx` on track/adr-039 (Restore button tests, 325 lines)

**What the audit found:** Both files use `describe`/`it` blocks that are mutually exclusive. Imports differ: 038 imports `useAppStore` + `LineageRunDetail` etc; 039 imports the exported helpers. The naive merge keeps one and loses the other.

**Severity:** P2 — silently loses test coverage on whichever side the merge favours.

**Recommended fix:** Rename the 039 test file to `RunDetail.restore.test.tsx` (or `RunDetail.integration.test.tsx`) so both Vitest files coexist. Update the `import RunDetail, { ... }` line to use the integrated `RunDetail.tsx` (post-P1-2 resolution); the helper exports must still be live for these tests to compile.

### P3-2 — `git.head_changed` does NOT invalidate `lineageSlice` (by design, but checklist row should be ticked with rationale)

**File:** `frontend/src/hooks/useWebSocket.ts:147-166`; `frontend/src/store/lineageSlice.ts:160-167`

**What the audit found:**

- The Phase 3.5 checklist row says "*`useWebSocket.ts` `git.head_changed` invalidates both slice caches **as needed**.*"
- 039 only calls `useAppStore.getState().invalidateHistory()` (the git slice action).
- `lineageSlice.ts:160-167` documents the design intent: lineage runs are server-authoritative and don't depend on git HEAD state. A new git commit does not change the historical runs table; only running a new workflow does.

**Severity:** P3 — design-intentional. The checklist row's "as needed" qualifier allows this, but it's worth ticking the row with the rationale recorded so a future reader doesn't think it's a gap.

**Recommended fix:** None. Annotate the integration PR or this audit report.

### Section B items verified clean

- **`store/index.ts` registers both slices**: simulation post-resolution registers `createLineageSlice` and `createGitSlice` with no selector collision (different namespace prefixes: `runs*`/`run*`/`selectedRunId` vs `branches`/`commits`/`status` etc).
- **`Toolbar.tsx` and `BottomPanel.tsx` mount different surfaces**: `Toolbar.tsx` hosts `BranchPicker` + `GitStatusBadge` + Commit button (Git slice); `BottomPanel.tsx` hosts the `LineageTab` (Lineage slice). No layout overlap; verified by `grep -n` for both component names in the merged tree.
- **`useWebSocket.test.ts` merged cleanly** — no add/add conflict; both tracks edited disjoint test cases.

## Section C — Schema / contract

### P1-3 — `delete_project` integration must use BOTH `_rmtree_force` AND `lineage_store.close()`

**File:** `src/scistudio/api/runtime.py:793-822` (conflict region 2 of 3 in `delete_project`)

**What the audit found:**

- 038 version: `lineage_store.close()` then `shutil.rmtree(project_path)`.
- 039 version: `MetadataStore.close()` (stale — D38-2.3 collapsed `MetadataStore` into a deprecation shim) then `_rmtree_force(project_path)` (a force-rmtree at line 42 that handles Windows read-only `.git/` files).
- A naive "take 038" loses `_rmtree_force` and `delete_project` fails on Windows with `PermissionError [WinError 32]` when the project's `.git/` contains read-only refs/packs.
- A naive "take 039" closes the dead-code MetadataStore shim (harmless) but leaves the live `lineage_store` SQLite handle open, and `shutil.rmtree` (or even `_rmtree_force` calling `shutil.rmtree` internally) refuses to delete the locked `.scistudio/lineage.db` on Windows.

**Severity:** P1 — Windows users cannot delete projects after this lands integrated; CI Windows job will break.

**Recommended fix:** Integration takes the **union**:

```python
# Close the per-project lineage store (ADR-038) so its SQLite WAL
# handle is released before we rmtree.
if self.active_project is not None and self.active_project.id == project.id:
    store = getattr(self, "lineage_store", None)
    if store is not None:
        try:
            store.close()
        except Exception:
            logger.debug("ApiRuntime: close lineage store before delete failed", exc_info=True)
        self.lineage_store = None

# ADR-039: _rmtree_force handles read-only files in .git/ (refs, packs)
# on Windows; plain shutil.rmtree does not.
_rmtree_force(project_path)
```

Drop the `MetadataStore.get_metadata_store()` block entirely — it's a no-op shim after D38-2.3.

### P2-4 — `MetadataStore` shim deprecation-warning leaks into agent MCP tool calls

**File:** `src/scistudio/core/metadata_store.py` (D38-2.3 deprecation shim)

**What the audit found:** The shim issues `DeprecationWarning` per `import`. Any agent MCP tool (`inspect_data`, `get_lineage`, `preview_data`) that imports `metadata_store` will surface the warning in the PTY stderr stream. On the integrated tree this is benign (the underlying `_set_active_lineage_store` machinery still answers reads), but it adds noise.

**Severity:** P2 — UX clutter, not correctness.

**Recommended fix:** Suppress the deprecation warning inside `src/scistudio/ai/agent/mcp/tools_inspection.py` and `tools_workflow.py` callers via `warnings.filterwarnings("once", category=DeprecationWarning, module="scistudio.core.metadata_store")` at import boundary. Or migrate the MCP tools to import from `scistudio.core.lineage.store` directly.

### Section C items verified clean

- **`lineage.db.runs` schema**: confirmed at `src/scistudio/core/lineage/store.py:57-79`; includes `workflow_git_commit TEXT`, `workflow_dirty INTEGER NOT NULL`, `parent_run_id TEXT REFERENCES runs(run_id)`, `execute_from_block_id TEXT`.
- **`block_version` force-injection**: `src/scistudio/blocks/registry.py` post-D38-2.2 calls `importlib.metadata.packages_distributions()` and stamps `scistudio.__version__` for in-tree blocks. D38-3.2 (#967) added `BlockRegistrationError` so unknown distributions raise per ADR §3.3 instead of returning literal `"unknown"`. The recent fix `3cf254f` ("scistudio_blocks_* monorepo packages fall back to scistudio version") confirms `scistudio_blocks_imaging|lcms|srs` are covered.
- **`If-Match` / `bump_revision` removal (D39-2.1)**: grep across the full integrated tree shows no remaining `If-Match` header references in `frontend/src/lib/api.ts`. The single stale test fixture was removed in commit `e981303`.

## Section D — File conflicts between tracks

### P1-4 (HAZARD H-D1, real and unresolved) — `RunDetail.tsx` add/add conflict loses exports if naively merged

**Files:**

- `frontend/src/components/Lineage/RunDetail.tsx` on track/adr-038 (464 lines, default export `RunDetail` reads from `useAppStore`, no named exports)
- `frontend/src/components/Lineage/RunDetail.tsx` on track/adr-039 (166 lines, default export `RunDetail` PLUS named exports `RestoreWorkflowButton`, `runRestoreWorkflow`, `workflowYamlPathForRun`)

**What the audit found:** The 039 test (`RunDetail.test.tsx:14-18`) imports those three named symbols. If the merge picks the 038 file, the test fails to compile. If it picks the 039 file, the entire ADR-038 Lineage tab is silent (no block list, no methods dialog, no rerun dialog), and Phase 4a (a) / (b) / (c) e2e all fail.

**Severity:** P1 — release-blocker for integration. This is the hazard the checklist named in advance.

**Recommended fix (Phase 4 integration PR):** Manual reconcile, no automation:

1. Start from the ADR-038 full body of `RunDetail.tsx`.
2. Add the three named exports (`RestoreWorkflowButton`, `runRestoreWorkflow`, `workflowYamlPathForRun`) from the ADR-039 file as top-level exports of the merged file.
3. Insert `<RestoreWorkflowButton run={detail.run} onRestored={...} />` into the affordance row of the 038 RunDetail's render JSX (next to the Re-run + Export methods buttons).
4. The 038 RunDetail consumes `useAppStore` for `selectedRunId`; pass `detail.run` (the `LineageRunSummary`) into `RestoreWorkflowButton` after verifying `RunRecordForRestore` is a structural subset of `LineageRunSummary` (it is — `run_id`, `workflow_id`, `workflow_git_commit: string | null` are all present in `LineageRunSummary`).
5. The 039 `default export RunDetail({ run, onRestored })` interface is shed (the integrated component reads from the store). The named-export helpers stay.

### P1-5 (HAZARD H-D2 partial) — D39-2.5 out-of-scope items: confirmed safe IF integration follows P1-4

**Files referenced in D39-2.5's PR body as out-of-scope:**

| Out-of-scope item | Status in integration |
|---|---|
| ADR-038 lineage schema files (`core/lineage/`) | Arrive via 038 track merge — clean (no add/add conflict). |
| Other Lineage/* components (`LineageTab.tsx`, `RunsList.tsx`, `BlockExecutionCard.tsx`, `MethodsExportDialog.tsx`, `RerunDialog.tsx`) | Only exist on track/adr-038; arrive via merge — clean. |
| 038 frontend wiring chain (`store/lineageSlice.ts`, `store/types.ts` `LineageSlice`, `lib/api.ts` `lineage.*`) | Arrive via 038 merge with manual conflict resolution per Section B above. |
| `BottomPanel.tsx` mount of `<LineageTab/>` | Only on track/adr-038; not touched by 039. Clean merge. |
| `Toolbar.tsx` mount of `<MergeFlow/>` (and `BranchPicker`, `GitStatusBadge`) | Only on track/adr-039; not touched by 038. Clean merge (verified — no conflict markers in `Toolbar.tsx`). |

**What the audit found:** All five converge **cleanly** at integration **except** for the `RunDetail.tsx` add/add conflict already enumerated (P1-4). No other D39-2.5 out-of-scope edits leak.

**Severity:** P1 if P1-4 is not addressed; otherwise the rest is **pass**.

### Section D items verified clean

- `src/scistudio/api/app.py` lifespan — verified: `runtime = ApiRuntime()` initializes both lineage store (`_init_lineage_store` chain) and git (via `open_project` → auto-init); the `WorkflowWatcher` schedule attaches both project workflows dir AND `.git/` (the D39-3.2 collapse).
- `frontend/src/store/index.ts` — verified clean after union resolution.
- `frontend/src/hooks/useWebSocket.ts` — verified clean (no add/add; both edits merged without overlap).

## Section E — Codex review reconcile sweep

Cross-track-relevant Codex auto-review comments on cascade PRs were swept. Findings:

### P2-5 — Reply-on-comment drift across three cascade PRs

- **PRs with all Codex P1s addressed by follow-up commits but no on-comment reply** (D-class drift, not release-blockers):
  - PR #926 (D38-2.2 wire-up): 2 Codex comments (1 P1 recorder-unsubscribe, 1 P2 collection wire-format), addressed in PR #967 D38-3.2. No on-comment reply was posted.
  - PR #927 (D39-2.2b backend impl): 3 Codex P1 comments (merge error envelope, lazy GitEngine resolve, tarball SHA placeholder), all addressed in commit `6d21347` and PR #930. No on-comment reply.
  - PR #960 (D38-3.1b audit): 1 Codex P2 (cosmetic — summary 6 vs 7 P2s in audit report). Addressed in subsequent audit revision; no on-comment reply.

- **Reconcile recommendation for Phase 4 fix PR:** post explicit `accepted (fixed in <sha>)` replies on the three PR conversations above. Silence on a Codex P1 is documented manager-discipline drift (per memory `audit_agent_codex_review`), even when the work is done.

- **All other cascade PR Codex comments**: have on-record replies (#937/#944/#940/#945/#950/#951/#952/#959/#931/#935/#965/#967/#970). Verified by sampling — e.g. PR #944's 2 Codex comments have explicit `accepted (fixed in f23ebd7)` replies from `zjzcpj`. No outstanding Codex P1 deferrals on the live tracking branches.

## Pre-known hazards verification

### H-A1 — `set_pending_git_commit` end-to-end: **half-resolved**

- **Verified**: `LineageStore.set_pending_git_commit` method exists on track/adr-038 at `src/scistudio/core/lineage/store.py:271`. Implementation: SELECT most-recent run, UPDATE its `workflow_git_commit`. Supports `sha=None` to clear.
- **Not verified — broken at integration**: the **call ordering** in `start_workflow` puts the `set_pending` call BEFORE `_build_lineage_recorder`, so the SHA stamps the previous run. See P1-1 for fix.
- **Bonus gap surfaced**: `set_pending_workflow_dirty` does not exist, and `RunRecord.workflow_dirty` is never threaded by 039. See P1-2.

### H-D1 — RunDetail.tsx dual track: **conflict confirmed; manual reconcile mandatory**

- **Conflict observed**: simulation produced `CONFLICT (add/add): Merge conflict in frontend/src/components/Lineage/RunDetail.tsx` (verified by `git merge` output, lines 1 / 464 / 629 of the in-conflict file).
- **Resolution path**: documented in P1-4. Phase 4 integration PR cannot be a naive auto-merge.

### H-D2 — D39-2.5 out-of-scope items convergence: **clean except for H-D1**

- (a) Schema files arrive intact via `git merge track/adr-038/lineage-db` — verified.
- (b) Lineage tab full chain (LineageTab → RunsList → RunDetail → BlockExecutionCard → MethodsExportDialog → RerunDialog) survives the merge — verified by grep across the simulated post-merge tree.
- (c) `BottomPanel.tsx`'s mount of `<LineageTab>` AND `Toolbar.tsx`'s mount of `<MergeFlow>` BOTH survive — verified (no conflicts on either file).
- (d) D39-2.5's Restore button is **NOT** the only D39 edit to the Lineage namespace once the test file is counted — `RunDetail.test.tsx` on track 039 is a second edit. See P2-4 for the test-file-split resolution. Functionally still clean — the test file is a separate add/add that splits cleanly.

## Findings table (sorted by severity)

| ID | Section | Severity | Description | Recommended fix |
|---|---|---|---|---|
| P1-1 | A (H-A1) | P1 | `set_pending_git_commit` called before `_build_lineage_recorder` → SHA stamped on PREVIOUS run | Move call after `_build_lineage_recorder`, or thread SHA into `RunRecord` constructor |
| P1-2 | A | P1 | `runs.workflow_dirty` never populated; "safety net" comment is dead | Add `set_pending_workflow_dirty` or thread into `RunRecord` |
| P1-3 | C, D | P1 | `delete_project` merge must use `_rmtree_force` (Windows .git/) AND `lineage_store.close()` | Union resolution; drop dead `MetadataStore` shim block |
| P1-4 | D (H-D1) | P1 | `RunDetail.tsx` add/add conflict will lose either UI or Restore exports | Manual merge: 038 body + 039 named exports + Restore button in affordance row |
| P1-5 | D (H-D2) | P1 if P1-4 unfixed | D39-2.5 out-of-scope chain converges cleanly EXCEPT for `RunDetail.tsx` | Resolved by fixing P1-4 |
| P2-1 | A | P2 | `open_project` lineage-init / git-init failure matrix not tested | Add `test_open_project_degraded_modes.py` |
| P2-2 | A | P2 | `/api/git/branch/switch` does not call `BlockRegistry.hot_reload()` | Add call after `engine.branch_switch` or subscribe registry to `git.head_changed` |
| P2-3 | B | P2 | `__tests__/RunDetail.test.tsx` add/add loses one test suite | Rename 039 test file to `RunDetail.restore.test.tsx` |
| P2-4 | C | P2 | MetadataStore shim DeprecationWarning leaks into MCP tool stderr | Suppress at MCP-tool import boundary or migrate to lineage.store |
| P2-5 | E | P2 | 3 PRs (#926, #927, #960) have Codex P1/P2 comments without on-comment replies | Post `accepted (fixed in <sha>)` retroactively |
| P3-1 | A | P3 | Agent system prompt does not instruct `agent:` git-commit prefix | Update `system_prompt.py`, file follow-up issue |
| P3-2 | B | P3 | `git.head_changed` does not invalidate `lineageSlice` | Annotate as design-intentional; tick checklist row with rationale |
| P3-3 | log | P3 | `frontend/tsconfig.tsbuildinfo` shown as conflict — generated artifact | Delete; regenerate via `tsc --build` |
| P3-4 | log | P3 | `docs/audit/2026-05-15-adr-039-combined-audit.md` arrives only via 039 merge | Take as-is; no other source |
| P3-5 | A | P3 | 038 `start_workflow` does NOT call any git code on its own; integration depends on 039's call site being merged in | Verify Phase 4 PR for ADR-038 final-merge to main includes the 039 wiring |

**Totals: 5 P1, 5 P2, 5 P3.**

## Recommendation for Phase 4 fix agent

Folded into the post-Phase-4-e2e fix pass (per the checklist's Phase 3.5 fix protocol). Ordered task list:

1. **P1-1 + P1-2 + P1-3 + P1-4** must all land in the **final integration PRs** (one per ADR, against main) — they are the conflict-resolution work. Cannot be deferred.
2. **P2-1 + P2-3** belong in the same PRs (test additions, no risk).
3. **P2-2 (`BlockRegistry.hot_reload` on branch switch)** can land in the same PR or in a follow-up issue if release pressure is high. Mark as a release-blocker only if the e2e Phase 4b Test 3 (branch + checkout + canvas/editor sync) reveals user-facing breakage.
4. **P2-4 (DeprecationWarning suppression)** is independent; can be a follow-up issue.
5. **P2-5 (Codex reply-on-comment drift)** — post retroactive replies BEFORE merging the final integration PRs to avoid more drift accumulating in the merge window.
6. **P3-* findings** — file as follow-up issues; do not block release.

## CI status (NOT run)

This audit did NOT run local CI (ruff / pytest / mypy / vitest). Audits per `audit-agent.md` §5 normally run full CI; the **simulated integration state** intentionally never lives on a real branch (the simulation was aborted), so running CI against the conflict-marker-bearing tree would produce noise. The two tracking branches **individually** have green CI per their merged-PR status (`#967` and `#970` both passed). The integration PRs at Phase 4 will run real CI; the present audit predicts which Phase 4 tests will fail without the fixes above.

Specifically: without P1-1, the Phase 4a e2e (a) "Each of 6 runs answers ADR-038's 4 user questions" fails — `runs.workflow_git_commit` is wrong on 5 of 6 runs. Without P1-3, the Windows job's `test_list_projects_prunes_deleted_directories` or equivalent project-delete test fails. Without P1-4, `RunDetail.test.tsx` fails to compile in vitest.

## Pointers for the e2e dispatcher

When Phase 4 e2e runs (parallel-allowed per #971 body), watch for:

- Phase 4a (a) — `sqlite3 .scistudio/lineage.db "SELECT run_id, workflow_id, workflow_git_commit, workflow_dirty FROM runs"` should produce non-NULL SHAs aligned to the correct run (per P1-1 fix). Compare to `git rev-parse HEAD` immediately after each `start_workflow`.
- Phase 4b (b) — observe `runs.workflow_dirty = 1` after a forced-dirty auto-commit failure (per P1-2 fix). Currently always 0.
- Phase 4b (d) — `agent:` prefix likely missing per P3-1; file the agent-prompt issue (already pre-queued in the checklist).
