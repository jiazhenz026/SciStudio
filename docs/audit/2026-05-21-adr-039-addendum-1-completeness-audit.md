---
title: "ADR-039 Addendum 1 Completeness + Edge-Case Audit"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: [39, 42]
language_source: en
---

# ADR-039 Addendum 1 Completeness + Edge-Case Audit (2026-05-21)

## Recommendation

**Recommendation: pass-with-fixes (one P1 blocker before umbrella → `main` merge).**

The implementation of ADR-039 Addendum 1 across PR-A (#1378), PR-B (#1383), and
PR-C (#1381) is functionally complete, scope-clean, well-tested, and matches
the §11.3 / §11.4 contract. The 4 claims from the dispatch all pass; 26 of 28
enumerated edge cases are covered or do not apply; the 3 follow-up issues
(#1380, #1389, #1390) accurately describe the residual concerns; and the
drift log entries match the actual diffs.

However, the **umbrella PR #1364 itself has 2 FAILED `Verify Workflow
Compliance` CI runs** because the manager gate record's `scope.include`
patterns do not cover any of the sub-PR file paths that appear in the umbrella's
diff vs `main`. Per the manager checklist Final Readiness row 5
("`[x]` CI passed on umbrella"), this is a checklist drift that masks a real
merge blocker. The owner cannot merge the umbrella → `main` until either
the umbrella gate record's `scope.include` widens to cover all sub-PR paths
OR an `admin-approved:ai-override` label is applied with rationale.

Everything below is supporting evidence.

---

## Findings (severity-ordered)

### P1 — Blocking the umbrella → `main` merge

#### P1-1: Umbrella PR #1364 fails `Verify Workflow Compliance` — gate record scope is too narrow

- **Where:** `.workflow/records/1352-adr-039-addendum-1-impl-manager.json` `scope.include` block; umbrella PR #1364 CI runs https://github.com/zjzcpj/SciStudio/actions/runs/26254238688/job/77272906959 and https://github.com/zjzcpj/SciStudio/actions/runs/26254203794
- **What:** The manager gate record's `scope.include` is:
  ```
  docs/planning/adr-039-addendum-1-impl-checklist.md
  docs/planning/dispatch-prompts/**
  .workflow/records/1352-adr-039-addendum-1-impl-manager.json
  ```
  But the umbrella PR diff vs `main` contains 24+ sub-PR file paths (everything PR-A, PR-B, and PR-C touched). CI emits `gate-record.scope.outside-include` for each one and exits 1.
- **Manager checklist drift:** §11 Final Readiness row 5 marks `[x] CI passed on umbrella — Verify Workflow Compliance SUCCESS on each sub-PR pre-merge`. That is true for the **sub-PRs**, not the umbrella PR. The umbrella's own CI is RED.
- **Rule violated:** ADR-042 gate workflow — gate records must cover every changed file in the PR diff. Per memory `feedback_sentrux_applicability_gap_for_docs_prs` the recipe is either widen the include list or apply an `admin-approved:ai-override` label with rationale.
- **Proposed fix (manager action):** Pre-merge, either
  - **Option A — widen the umbrella manager gate record:** add the 24 sub-PR paths and CHANGELOG.md + the per-sub-PR record JSONs + smoke transcripts to `scope.include`, then re-run `python -m scistudio.qa.governance.gate_record finalize` and force-push. This re-establishes "every changed file is in scope" semantically.
  - **Option B — apply `admin-approved:ai-override` label with rationale** that the umbrella PR is a meta-PR composed of 3 already-gated sub-PRs and the per-file scope-include re-listing would be tautological. Sub-PRs already each passed scope-include with their narrower records committed in-tree.
  - Owner directive (memory `reference_umbrella_pr_merge_protocol`) makes this an owner decision; manager should surface both options and act on the owner's pick.
- **Severity rationale:** This is the ONLY thing standing between the umbrella PR and a clean merge. Behavior is correct; the gate record is metadata.

### P2 — Should fix before umbrella → `main` merge but not strictly blocking

None.

### P3 — Improvement / nit / follow-up

#### P3-1: Same-branch dirty-tree switch creates a phantom `auto: pre-switch` commit
- **Where:** `src/scistudio/api/routes/git.py:411-422` (`branch_switch`)
- **What:** Edge case 7 — calling `POST /api/git/branch/switch {branch_name: <current_branch>}` with a dirty tree passes the `known_branches` validator (the current branch is in the list), then `_auto_commit_if_dirty` creates an `auto: pre-switch @ ... (from=main, to=main)` commit. `engine.branch_switch` then runs `git checkout main`, which is a no-op for branch but produces a successful response. The auto-commit, which has `from=X, to=X`, is essentially a "checkpoint commit" with a slightly weird message.
- **Severity rationale:** The user-observable effect is a recoverable commit on the same branch. Not destructive. The auto-commit semantics are "save the dirty tree before doing X"; saving before a no-op is harmless but produces a wart-y commit message.
- **Proposed fix:** Add `if body.branch_name == engine.current_branch(): return early` before the auto-commit. Defer as follow-up — fix not blocking merge.

#### P3-2: Graph dot click on virtualized list sets focus but does not scroll-into-view
- **Where:** `frontend/src/components/Git/GitGraph/interactions.ts:134-151` (`onCommitClick`)
- **What:** Edge case 20 — clicking a graph dot whose corresponding list row is virtualized out sets `focusedRow` (state) but does not call `scrollIntoView`. The user clicks a dot and sees no visible effect because the focused row is offscreen.
- **Severity rationale:** PR-B's design choice (per checklist §8.1) is "focus-and-scroll subset; no floating chip." The "focus" part works; the "scroll" part is missing. Cosmetic UX gap; not a regression vs pre-PR-B (which had no focus behavior either, just modal open).
- **Proposed fix:** In `GitGraphPane` (or wherever the focused row index is consumed), add a `useEffect` that calls `scrollIntoView({ block: "center", behavior: "smooth" })` on the focused row's DOM node whenever `focusedRow` changes. Defer as a polish follow-up.

#### P3-3: `engine.tag` could silently clobber a pre-existing user tag at the same name
- **Where:** `src/scistudio/core/versioning/git_engine.py:558-588` (`tag`)
- **What:** Edge case 16 — `git update-ref <name> <sha>` is overwrite-by-default. If a user (somehow) created a ref under the `refs/scistudio/lineage/<sha>` namespace pointing at a different SHA, `engine.tag` would overwrite silently. The namespace is application-private and users are not expected to write to it, so in practice this is benign — but the engine method's `force` parameter is documented as "Accepted for API symmetry with `git tag`; ignored because `update-ref` is already overwrite-by-default", which means callers cannot opt into refusal-on-collision even if they wanted to.
- **Severity rationale:** Hypothetical (no user writes to `refs/scistudio/lineage/*`). Documented in the docstring.
- **Proposed fix:** Optional — wire `force=False` to use `git update-ref <name> <sha> ""` (the "create iff absent" form that takes an empty old-SHA). Defer as a polish follow-up.

#### P3-4: `_files_unchanged_vs_commit` short-circuit + auto-commit ordering is correct but undocumented in `engine.restore` docstring
- **Where:** `src/scistudio/core/versioning/git_engine.py:386-409` + `src/scistudio/api/routes/git.py:336-345`
- **What:** Edge case 2 — when restore target is byte-identical to the working tree, `engine.restore` short-circuits via `_files_unchanged_vs_commit`. The route-layer `_auto_commit_if_dirty` runs BEFORE this short-circuit, so the auto-commit captures the dirty tree even when the restore itself is a no-op. This is correct (you want the recoverable point before any potentially overwriting action), but the `engine.restore` docstring describes the short-circuit as "no-op" without noting that the route layer's auto-commit may still fire. The `test_restore_skips_when_file_unchanged` test docs the correct contract (clean tree → no auto-commit, no restore) but doesn't cover dirty-tree → auto-commit lands → restore short-circuits separately.
- **Severity rationale:** Code is correct. Behavior is intentional. Docs/tests could be tighter.
- **Proposed fix:** Add a one-paragraph note in `engine.restore` docstring noting that the route layer's auto-commit fires before this method even when the short-circuit returns early. Optionally add a 3-line test asserting the dirty + unchanged-files case creates an auto-commit. Defer as docs/test polish.

---

## Per-claim verification

### Claim 1 — Stash GUI/REST/engine removed (PR-A / #1353): PASS

| Check | Evidence |
|---|---|
| No active stash code in `src/scistudio` | `grep -ri stash src/scistudio`: matches are only comments in `app.py:256`, `versioning/__init__.py:6-7`, `git_engine.py:373-376`, `routes/git.py:189-340`, + false-positive `axis_iter.py:253` ("_data stashing pattern"), `core/types/array.py:254` ("instead of stashing in _data") |
| No `def stash_*` or `Stash*Request` in src/scistudio | `grep -E "def stash_|stash_list\|stash_save\|stash_apply\|stash_drop\|StashSaveRequest\|StashApplyRequest" src/scistudio`: 0 matches |
| No `/stash*` REST endpoints | `grep -E 'router\.(get\|post\|delete\|put\|patch).*stash\|"/stash' src/scistudio/api/routes/git.py`: 0 matches |
| No stash frontend exports | `grep -E "gitStashList\|gitStashSave\|gitStashApply\|gitStashDrop\|GitStashEntry\|GitStashApplyResult\|loadStashes\|stashes:" frontend/src`: 0 matches |
| `StashListPanel.tsx` + `StashApplyDialog.tsx` deleted | `ls frontend/src/components/Git/`: files absent |
| `GitTab.tsx` Stashes button gone | `git diff` shows the button removed; negative-assertion test at `GitTab.test.tsx:95-99` (`expect(screen.queryByTestId("git-tab-stashes-button")).toBeNull()`) |
| `RunDetail.tsx` `status === "stashed"` branch gone | Read of `RunDetail.tsx:540-650`: no stash branch; only `auto_commit_sha` handling |
| `GitHistoryList.tsx` `stashPrompt` state + `StashApplyDialog` mount gone | `git diff 8a009658^..8a009658 -- frontend/src/components/Git/GitHistoryList.tsx`: shows deletion of `stashPrompt` state, `status === "stashed"` branch, `StashApplyDialog` import + mount |
| Test files updated | `RunDetail.restore.test.tsx:114-138` asserts NO stash language + old stash testid absent |

### Claim 2 — Auto-commit replaces auto-stash on dirty switch + restore (PR-A / #1354): PASS

| Check | Evidence |
|---|---|
| Pre-validation in `restore` route happens BEFORE auto-commit | `src/scistudio/api/routes/git.py:332-345`: `engine._run(["rev-parse", "--verify", ...])` runs at line 333; `_auto_commit_if_dirty` runs at line 341. Codex P2 fix on #1378 is in. |
| Pre-validation in `branch_switch` happens BEFORE auto-commit | `src/scistudio/api/routes/git.py:405-419`: `known_branches` validator runs at line 405; `_auto_commit_if_dirty` runs at line 416. Codex P1 fix on #1378 is in. |
| `restore` response includes `auto_commit_sha` | `src/scistudio/api/routes/git.py:350`: `return {"status": "ok", "auto_commit_sha": auto_sha}` |
| `branch/switch` response includes `auto_commit_sha` | `src/scistudio/api/routes/git.py:437-441`: `return {"status": "ok", "current_branch": body.branch_name, "auto_commit_sha": auto_sha}` |
| `engine.restore` no longer auto-stashes | `src/scistudio/core/versioning/git_engine.py:366-409`: pure soft-restore, no `stash` calls |
| Hotfix #997 `_files_unchanged_vs_commit` retained | `src/scistudio/core/versioning/git_engine.py:411-429`: helper present; called at line 391 |
| `commit` raising "nothing to commit" handled as no-op | `src/scistudio/api/routes/git.py:201-208`: `_auto_commit_if_dirty` catches `GitError` with `"nothing to commit"` or `"no local changes"` in stderr |
| `lastNotice` state slot added | `frontend/src/store/gitSlice.ts:149-157, 206, 275, 310` |
| `RunDetail.tsx` shows "committed as <sha>" hint | `frontend/src/components/Lineage/RunDetail.tsx:601-603, 638-646` |
| `BranchPicker.tsx` renders toast on `lastNotice` for branch switch | `frontend/src/components/Git/BranchPicker.tsx:53-80, 275` (testid `branch-picker-auto-commit-toast`) |
| Backend tests cover the new shape | `test_branch_switch_auto_commits_dirty_tree`, `test_restore_endpoint_auto_commits_dirty_tree`, `test_restore_endpoint_clean_tree_no_auto_commit`, `test_branch_switch_rejects_unknown_branch_without_mutating_history`, `test_restore_rejects_unknown_commit_without_mutating_history` |

### Claim 3 — Inline `[Diff]` `[Restore]` buttons on history rows (PR-B / #1355): PASS

| Check | Evidence |
|---|---|
| Row `<li>` has no `onClick` | `frontend/src/components/Git/GitHistoryList.tsx:259-265`: only `onKeyDown` and `tabIndex={0}` |
| `[Diff]` button beside `[Restore]` button | `frontend/src/components/Git/GitHistoryList.tsx:296-319`: both `<button>` elements with `e.stopPropagation()` |
| Row click does NOT open modal | Test: `GitHistoryList.test.tsx:117-123` |
| `[Diff]` button opens modal | Test: `GitHistoryList.test.tsx:138-146` |
| Graph dot click no longer opens modal | `frontend/src/components/Git/GitGraph/interactions.ts:134-151`: only sets `focusedRow`; `onOpenDiff?.()` is undefined from the only consumer (`GitGraphPane` at `GitHistoryList.tsx:214` passes no prop) |
| `r` hotkey works | Test: `GitHistoryList.test.tsx:177-186` |
| `d` hotkey works | Test: `GitHistoryList.test.tsx:166-175` |
| `Enter` does nothing | Test: `GitHistoryList.test.tsx:188-203` |
| Buttons stop propagation | Verified via `e.stopPropagation()` calls at lines 300, 312 + test at lines 148-164 |

### Claim 4 — Silent auto-tag safety net on branch delete (PR-C / #1356): PASS

| Check | Evidence |
|---|---|
| `LineageStore.workflow_git_commits_in` exists with `set[str]` return | `src/scistudio/core/lineage/store.py:328-369` |
| Empty input → empty set, no SQL | `src/scistudio/core/lineage/store.py:357-362`: short-circuit `if not sha_list` AND `if not unique` |
| `GitEngine.commits_reachable_only_from` uses fully-qualified ref | `src/scistudio/core/versioning/git_engine.py:493-556`: line 531 `target_ref = f"refs/heads/{branch}"`; line 548 `["rev-list", target_ref, "--not", *other_refs]`. Codex P1 fix on #1381 is in. |
| `GitEngine.tag` uses `git update-ref` (overwrite-by-default = idempotent) | `src/scistudio/core/versioning/git_engine.py:558-587`: `self._run(["update-ref", name, target_sha])` |
| Three-phase ordering in `branch_delete` route | `src/scistudio/api/routes/git.py:484-522`: lines 493-497 compute intersection (read-only), lines 499-505 attempt delete, lines 507-520 pin only on success. Codex P2 fix on #1381 is in. |
| `BranchPicker.tsx::handleDelete` UNCHANGED | `frontend/src/components/Git/BranchPicker.tsx:131-143`: same `window.confirm` + `deleteBranch` shape as before |
| TODO comment citing #1380 follow-up | `src/scistudio/api/routes/git.py:480-483`: cites `Followup: https://github.com/zjzcpj/SciStudio/issues/1380` |
| Tests | `test_branch_delete_endpoint` (basic), `test_branch_delete_endpoint_no_lineage_reference_leaves_no_refs` (clean delete), `test_branch_delete_endpoint_safety_net_keeps_sha_reachable` (end-to-end Lineage Restore round-trip), `test_branch_delete_failed_delete_creates_no_lineage_refs` (Codex P2 regression), `test_commits_reachable_only_from_disambiguates_branch_vs_tag` (Codex P1 regression), `test_commits_reachable_only_from_lineage_ref_excludes_pinned_sha` (idempotency) |

---

## Edge case verification

| # | Edge case | Status | Evidence |
|---|---|---|---|
| 1 | Clean tree restore — auto-commit skipped | COVERED | `test_restore_endpoint_clean_tree_no_auto_commit` asserts `body["auto_commit_sha"] is None` and HEAD unchanged. Path: `_auto_commit_if_dirty` short-circuits via `if not engine.status()["dirty"]: return None`. |
| 2 | Restore short-circuit + auto-commit ordering | COVERED | Auto-commit runs BEFORE `engine.restore` (routes/git.py:341 → 345). The short-circuit in `engine.restore` (line 388) does NOT prevent the auto-commit. See P3-4 for a docs/test polish recommendation. |
| 3 | Restore on deleted-target file | COVERED IMPLICITLY | `engine.restore` runs `git checkout <sha> -- <files>`; git correctly recreates the file. Auto-commit captures the "deleted" state. No explicit test, but the round-trip is exercised by `test_restore_endpoint_emits_workflow_changed`. |
| 4 | Multi-file restore with some unchanged | COVERED IMPLICITLY | `_files_unchanged_vs_commit` only short-circuits when ALL files are unchanged (line 388 `if files: try: all_unchanged = ...`). Mixed case falls through to `git checkout`. |
| 5 | Empty-repo edge | NOT APPLICABLE | Restore pre-validates the target commit via `rev-parse --verify ^{commit}`. On an empty repo (no commits), the pre-validation fails 404 before auto-commit. The route never reaches the auto-commit on empty repos. |
| 6 | Switch to non-existent branch with dirty tree | COVERED | `test_branch_switch_rejects_unknown_branch_without_mutating_history` proves the 404 fires BEFORE any commit lands. |
| 7 | Switch to the SAME branch with dirty tree | PARTIAL — see P3-1 | The current-branch check is implicit: `body.branch_name in known_branches` includes the current branch. Auto-commit fires, then `git checkout main` is a no-op. Phantom auto-commit. P3 nit. |
| 8 | Switch with untracked-only dirty state | COVERED | `engine.status()["dirty"]` includes untracked (git_engine.py:664 `dirty = bool(modified or staged or untracked or conflicted)`). `engine.commit` with `files=None` calls `git add -A` (line 211), capturing untracked. No explicit test, but the behavior is correct by construction. |
| 9 | Switch FROM detached HEAD | COVERED | `engine.current_branch() or "(detached)"` (routes/git.py:396) handles detached HEAD; message includes `from=(detached), to=<new>`. |
| 10 | Concurrent switch + restore race | OUT OF SCOPE | Concurrency is not in scope for this audit (per the dispatch prompt). |
| 11 | Delete branch with NO lineage references | COVERED | `test_branch_delete_endpoint_no_lineage_reference_leaves_no_refs` asserts `refs/scistudio/*` is empty. |
| 12 | Delete branch with already-pinned SHA | COVERED | `test_commits_reachable_only_from_lineage_ref_excludes_pinned_sha`: after pinning, the next call returns `[]`. Idempotent. |
| 13 | Delete branch with SHA reachable from main | COVERED | `test_commits_reachable_only_from_returns_branch_only_shas` + `test_commits_reachable_only_from_merged_branch_returns_empty` cover the orphan-set logic. |
| 14 | Failed delete (unmerged + `-d`) | COVERED | `test_branch_delete_failed_delete_creates_no_lineage_refs`: Codex P2 three-phase ordering prevents pin creation on failure. |
| 15 | Branch + tag share short name | COVERED | `test_commits_reachable_only_from_disambiguates_branch_vs_tag`: engine layer uses fully-qualified ref. Pre-existing `engine.branches()` short-form bug surfaced as #1390 (route-layer; OUT of #1356 scope). |
| 16 | `engine.tag` clobbers pre-existing user tag | DOCUMENTED — see P3-3 | `git update-ref` is overwrite-by-default. Namespace `refs/scistudio/lineage/*` is application-private. Hypothetical concern only. |
| 17 | Row click is focus-only | COVERED | `GitHistoryList.tsx:259-265` — no `onClick`; test `clicking a row does NOT dispatch onCommitClick`. |
| 18 | Tab order through `[Diff]` and `[Restore]` | COVERED | Native `<button>` elements are inherently Tab-reachable. Test asserts `tagName === "BUTTON"`. |
| 19 | `d` hotkey when focus is in text input | NOT APPLICABLE | The `onKeyDown` handler is bound to the `<li>` row, not document-global. No text inputs exist inside the row. Edge case doesn't arise. |
| 20 | Graph dot click on virtualized list | PARTIAL — see P3-2 | Focus is set via `setFocusedRow`; no `scrollIntoView` wired. Cosmetic UX gap; defer to follow-up. |
| 21 | PR-A `lastNotice` interacts with PR-C silent delete | COVERED | `deleteBranch` in gitSlice (lines 405-413) does NOT write `lastNotice`. Silent delete stays silent. Verified by reading gitSlice.ts. |
| 22 | All `gitRestore` / `gitBranchSwitch` consumers use new shape | COVERED | Only two call sites: `gitSlice.ts:369` (handled) and `RunDetail.tsx:560` (handled). `api.ts:441-459` types match backend response. |
| 23 | PR-A + PR-B integration on `GitHistoryList.tsx` | COVERED | PR-A removed `stashPrompt` state; PR-B added inline buttons. Diffs are disjoint (PR-A touched lines 19, 60, 104-110, 322-328; PR-B touched lines 2-12, 73-103, 121-137, 207-214, 251-322). Merge was clean. |
| 24 | Workflow.changed emit (hotfix #988) still works | COVERED | `_emit_workflow_diff` runs after `engine.branch_switch` / `engine.restore`. The `before` snapshot is taken before `_auto_commit_if_dirty`. Auto-commit doesn't modify file content (only stages + commits), so the diff correctly captures the post-checkout YAML changes. Tests: `test_branch_switch_emits_workflow_changed_per_modified_yaml`, `test_restore_endpoint_emits_workflow_changed`, `test_branch_switch_emits_created_for_new_yaml`. |
| 25 | Drift log entry 1 — Agent A's 4 docstring files | VERIFIED | `git diff 8a009658^..8a009658 -- frontend/src/components/BottomPanel.tsx frontend/src/components/Toolbar.tsx src/scistudio/api/app.py src/scistudio/core/versioning/__init__.py`: all 4 diffs are comment/docstring-only (Stash mention removed from comment lines). Zero code-semantics change. |
| 26 | Drift log entry 2 — `_is_test_path` vitest gap | VERIFIED | `src/scistudio/qa/governance/gate_record.py:318-326`: `_is_test_path` matches only `tests/`, `/tests/`, `test_`, `_test.py`. Does NOT match `**/__tests__/**`, `*.test.ts`, `*.test.tsx`. Issue #1389 accurately describes this. |
| 27 | Drift log entry 3 — `engine.branches()` quirk | VERIFIED | `src/scistudio/core/versioning/git_engine.py:435-459`: uses `for-each-ref --format=%(refname:short)`. Git's disambiguation returns `heads/<name>` when a tag shares the short name. PR-A's `known_branches` validator then rejects the colliding name as 404. Issue #1390 accurately describes this. |
| 28 | Follow-up issues #1380, #1389, #1390 accuracy | VERIFIED | Each issue read in full via `gh issue view`. Content matches the residual concern. #1380 = ref cleanup (deferred from #1356). #1389 = `_is_test_path` + `scistudio_pr_create.py --base` hardcode. #1390 = `engine.branches()` short-name disambiguation. All three are filed and OPEN. |

---

## Drift log accuracy

All 4 drift log entries in `docs/planning/adr-039-addendum-1-impl-checklist.md` §10 are accurate:

- **Entry 1 (Agent A 4 docstring files):** Verified comment-only via `git show` diffs. ACCEPT.
- **Entry 2 (Agent B `_is_test_path` gap):** Verified by reading the classifier source. The `admin-approved:ai-override` label rationale is sound. ACCEPT.
- **Entry 3 (Agent C `engine.branches()` quirk):** Verified by reading the engine source. Pre-existing bug; PR-C correctly out-of-scope. ACCEPT.
- **Entry 4 (Manager filed Agent B's promised issue):** Verified — #1389 exists and covers both gaps. ACCEPT.

---

## Checks executed

| Check | Result | Detail |
|---|---|---|
| `ruff check .` | PASS | All checks passed. |
| `ruff format --check .` | PASS | 651 files already formatted. |
| `pytest tests/core/test_git_engine.py tests/api/test_git_endpoints.py tests/core/test_lineage_store.py --timeout=60` | PASS | 94 passed. |
| `python -m scistudio.qa.audit.full_audit --repo-root .` | PASS | status=pass, findings=[]; 6 baseline vulture warnings unchanged. |
| `mcp__plugin_sentrux_sentrux__scan` | PASS | files=1119, quality_signal=4444. |
| `mcp__plugin_sentrux_sentrux__check_rules` | PASS | 3/3 rules pass, 0 violations. |
| `mcp__plugin_sentrux_sentrux__health` | PASS | bottleneck=acyclicity, quality_signal=4444. |
| Grep guard `stash` in src/scistudio + frontend/src + tests | PASS | All matches are legitimate: comments documenting the removal, negative test assertions, unrelated false positives (axis_iter, GitGraph octopus-test fixtures, CodeEditor OnMount handler). Zero active stash code. |
| Frontend vitest (manager worktree) | N/A | manager worktree has no node_modules; CI on each sub-PR already validated the full suite (Verify Workflow Compliance SUCCESS on PR-A #1378, PR-B #1383, PR-C #1381). |
| Chrome smoke | N/A | Audit is read-only; defer to owner pre-merge spot-check per umbrella PR #1364 body's owner-action section. |
| Umbrella PR #1364 CI | **FAIL — see P1-1** | 2 FAILED `Verify Workflow Compliance` runs due to gate-record `scope.include` not covering sub-PR file paths. |

---

## Scope-clean verification

Files changed across PR-A + PR-B + PR-C (deduplicated, excluding gate records / docs / CHANGELOG / smoke transcripts):

```
frontend/src/components/BottomPanel.tsx           (PR-A, comment-only)
frontend/src/components/Git/BranchPicker.tsx      (PR-A)
frontend/src/components/Git/GitGraph/interactions.ts  (PR-B)
frontend/src/components/Git/GitHistoryList.tsx    (PR-A + PR-B, disjoint diffs)
frontend/src/components/Git/GitTab.tsx            (PR-A)
frontend/src/components/Git/StashApplyDialog.tsx  (PR-A: DELETED)
frontend/src/components/Git/StashListPanel.tsx    (PR-A: DELETED)
frontend/src/components/Lineage/RunDetail.tsx     (PR-A)
frontend/src/components/Toolbar.tsx               (PR-A, comment-only)
frontend/src/lib/api.ts                           (PR-A)
frontend/src/store/gitSlice.ts                    (PR-A)
frontend/src/types/api.ts                         (PR-A)
src/scistudio/api/app.py                          (PR-A, comment-only)
src/scistudio/api/routes/git.py                   (PR-A + PR-C, disjoint regions)
src/scistudio/core/lineage/store.py               (PR-C)
src/scistudio/core/versioning/__init__.py         (PR-A, comment-only)
src/scistudio/core/versioning/git_engine.py       (PR-A + PR-C, disjoint regions)
tests/api/test_git_endpoints.py                   (PR-A + PR-C)
tests/core/test_git_engine.py                     (PR-A + PR-C)
tests/core/test_lineage_store.py                  (PR-C)
+ corresponding __tests__/*.test.tsx files for PR-A and PR-B
```

None of the §11.6 out-of-scope items were touched:
- Stash removed from bundled git binary: NOT TOUCHED (correct — only GUI/REST/engine).
- Merge / cherry-pick conflict resolution (§3.5a): NOT TOUCHED.
- Branch graph rendering / lane algorithm (§3.5b + addenda #988/#990/#1002): NOT TOUCHED.
- History panel filter dropdown (§3.4 / §3.5c): NOT TOUCHED.
- Periodic `git gc` policy: NOT TOUCHED.

Protected paths:
- `docs/adr/ADR-039.md`: NOT TOUCHED by any sub-PR (correct — addendum text was already merged via #1358).

**Scope-clean: PASS.**

---

## Test coverage assessment

| File | Pre-PR-A LOC | Post-PR-A LOC | New tests added |
|---|---|---|---|
| `tests/core/test_git_engine.py` | ~600 | ~700 | 6 new (4 from PR-A regression + 2 from PR-C: orphan-set, idempotency, branch/tag disambiguation, plus Codex regression test) |
| `tests/api/test_git_endpoints.py` | ~700 | ~890 | 9 new (auto-commit dirty switch, auto-commit dirty restore, clean tree no-auto-commit, restore unchanged short-circuit, Codex P1 + P2 regressions on PR-A, branch delete + lineage refs + clean delete + safety net + Codex P2 regression on PR-C) |
| `tests/core/test_lineage_store.py` | (new) | ~110 | 6 new (intersect, empty input, absent SHAs, null rows, duplicates collapsed, set type) |
| `frontend/src/components/Git/__tests__/GitHistoryList.test.tsx` | rewritten | 16 cases | 16 (row click no-op, inline diff button, inline restore button, d hotkey, r hotkey, Enter no-op, etc.) |
| `frontend/src/components/Lineage/__tests__/RunDetail.restore.test.tsx` | ~70 | ~160 | 3 new (auto-commit hint, NO stash language, clean tree hint absent) |
| `frontend/src/store/__tests__/gitSlice.test.ts` | extended | + 3 cases | switchBranch clean tree, switchBranch dirty tree, restore dirty tree |
| `frontend/src/components/Git/__tests__/GitTab.test.tsx` | extended | + 2 cases | Stashes button absent |

**Test coverage: SUFFICIENT.** The user-reported repro (Lineage Restore confusion) is covered by component-level DOM assertion in `RunDetail.restore.test.tsx:114-138`.

---

## Cross-PR integration confirmation

- PR-A + PR-B both touched `frontend/src/components/Git/GitHistoryList.tsx`. The diffs are on disjoint lines/regions (PR-A removed stash code; PR-B restructured handlers and added inline buttons). Manual diff review confirms a clean merge with no dead state.
- PR-A + PR-C both touched `src/scistudio/api/routes/git.py` and `src/scistudio/core/versioning/git_engine.py`. The regions are disjoint (PR-A: `restore`, `branch_switch`, `_auto_commit_if_dirty` helper; PR-C: `branch_delete`, `commits_reachable_only_from`, `tag`). Manual diff review confirms a clean merge.
- The `_emit_workflow_diff` (hotfix #988) integration still fires correctly per `test_branch_switch_emits_workflow_changed_per_modified_yaml`, `test_restore_endpoint_emits_workflow_changed`, etc.
- The `lastNotice` (PR-A) does NOT trigger on the silent delete path (PR-C) — `deleteBranch` does not write `lastNotice`. Verified by reading `gitSlice.ts:405-413`.

---

## Codex auto-review reconciliation

Each sub-PR's gate record references its Codex auto-review reconciliation:

- PR-A #1378: Codex P1 (`branch_switch` validates target before auto-commit) + Codex P2 (`restore` validates target before auto-commit) — both reconciled in commit `8aed59bf`, regression-tested by `test_branch_switch_rejects_unknown_branch_without_mutating_history` and `test_restore_rejects_unknown_commit_without_mutating_history`.
- PR-B #1383: no Codex P1 / P2 reconciliation needed; admin override label applied per drift log entry 2.
- PR-C #1381: Codex P1 (fully-qualified ref form in `commits_reachable_only_from`) + Codex P2 (three-phase delete-then-pin ordering) — both reconciled in commit `6115d9e3`, regression-tested by `test_commits_reachable_only_from_disambiguates_branch_vs_tag` and `test_branch_delete_failed_delete_creates_no_lineage_refs`.

All Codex findings accepted-as-fixed in-PR. No deferred Codex P1 / P2.

---

## Closing summary

Implementation correctness: PASS.
Test coverage: SUFFICIENT (94 backend tests + 16 + 3 + 3 + 2 frontend tests).
Scope discipline: PASS (no §11.6 out-of-scope touched).
Drift log: ACCURATE (4/4 entries verified).
Follow-up issues: ACCURATE (3/3 issues #1380 / #1389 / #1390 describe real residual concerns).
Codex reconciliation: COMPLETE for all 3 PRs.

The umbrella → `main` merge is blocked by ONE meta-issue: the umbrella PR's own
gate record (`.workflow/records/1352-adr-039-addendum-1-impl-manager.json`)
has `scope.include` patterns that don't cover the sub-PR files visible in the
umbrella diff vs `main`. This is a manager-side fix (widen `scope.include` OR
apply admin override label) and does not require any source/test code change.

After the manager closes P1-1, the implementation work is ready for owner
spot-check (per umbrella PR #1364 body) and final merge.
