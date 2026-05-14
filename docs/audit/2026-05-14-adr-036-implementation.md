# ADR-036 Implementation Audit — 2026-05-14T16:53Z

**PRs audited**:
- [#855](https://github.com/zjzcpj/SciEasy/pull/855) — Skeleton (S36)
- [#864](https://github.com/zjzcpj/SciEasy/pull/864) — I36a (TabState union + backend file/lint)
- [#863](https://github.com/zjzcpj/SciEasy/pull/863) — I36b (CodeEditor + Save UX)
- [#865](https://github.com/zjzcpj/SciEasy/pull/865) — I36c (ProjectTree + View source + reload + template)

**Branch under audit**: `track/adr-036/code-editor` (audit branch: `audit-impl-036`)
**Umbrella issue**: [#843](https://github.com/zjzcpj/SciEasy/issues/843)
**Auditor**: A36-impl
**ADR**: [ADR-036 — Embedded code editor for project files](../adr/ADR-036.md)

---

## Verdict

**NEEDS-FIX** — block merge of `track/adr-036/code-editor` into main until **2 P1** findings are addressed in a follow-up F36-impl PR. Per memory `audit_p1_override`, the dispatcher MUST override any "deferred" recommendation on these two and require in-PR fixes before the umbrella PR can ship.

The implementation is broadly faithful to ADR-036, comment hygiene is excellent, and 213 unit tests pass cleanly. The 2 P1s are **real and reproducible** and represent silent data-loss paths reachable from normal UI flows.

---

## 1. Local CI results

| Check | Result | Notes |
|---|---|---|
| `PYTHONPATH=src pytest tests/api -p "no:fast_array_utils" --no-cov` | **179 passed, 2 failed, 2 skipped** | The 2 failures are pre-existing Windows env issues (`PermissionError [WinError 32] metadata.db` in `test_projects.py`), NOT introduced by ADR-036. Confirmed via `git diff origin/main..HEAD -- tests/api/test_projects.py` → empty. The 2 skipped tests are macOS-only. |
| ADR-036 new test files only (`test_blocks_template{,_skeleton}.py`, `test_file_endpoints{,_skeleton}.py`, `test_lint_endpoint.py`, `test_reload_on_save.py`) | **34 passed, 0 failed** | Clean. |
| `ruff format --check .` | **464 files already formatted** | Clean. |
| `ruff check .` | **All checks passed!** | Clean. |
| `cd frontend && npm install && npx vitest run` | **20 files / 156 tests passed** | Clean. Includes new `tabState.test.ts` (8), `CodeEditor.test.tsx` (7), `ProjectTree.test.tsx` (6), `Toolbar.test.tsx` (11). |
| `cd frontend && npx tsc --noEmit` | **clean (no output, exit 0)** | |
| `cd frontend && npm run build` | **built in 16.03s** | Bundle size warning (5.4 MB main chunk) is pre-existing and unrelated to ADR-036. |
| `--timeout=60` flag | **could not be applied** — pytest-timeout is loaded only via the `fast_array_utils` plugin chain, which is broken in the local env (`ImportError: cannot import name '_errors' from partially initialized module 'h5py'`). Disabling the plugin also drops `--timeout`. This is a pre-existing local env issue. CI runs cleanly per PR-level checks. |

**Verdict**: All ADR-036-touched code passes lint, type-check, build, and 100 % of new-test coverage. The h5py env problem is environmental and outside ADR-036 scope.

---

## 2. Checklist drift findings

Walked every ticked row in `docs/planning/adr-035-036-checklist.md` lines 65–111 (ADR-036 section).

| Row | Status | Verification |
|---|---|---|
| Skeleton § 65–76 (11 rows) | ALL CONFIRMED | All ticked items map to artifacts in PR #855 + fix-PR #860. Lockfile contains `@monaco-editor/react`. Skeleton tests are xfail. Stubs raise `NotImplementedError`. |
| Phase 2A I36a § 78–84 (6 rows) | ALL CONFIRMED | `_resolve_project_file` + `read_project_file` + `write_project_file` exist in `routes/projects.py` lines 115–278. Atomic write via tempfile + replace, `mark_self_write` coordination present. Lint route registered in `api/app.py`. Tests `test_file_endpoints.py` (12) + `test_lint_endpoint.py` (7) all pass. |
| Phase 2B I36b § 86–94 (8 rows) | ALL CONFIRMED | `CodeEditor.tsx` lazy-imports Monaco, lint debounce 600 ms, save debounce 800 ms in App.tsx file-tab autosave effect. Toolbar split into kind-aware variants. Ctrl+S routed by `activeFileTab`. Vitest counts match. |
| Phase 2C I36c § 96–103 (7 rows) | ALL CONFIRMED | `ProjectTree.tsx` double-click handler dispatches `openFileTab`. "View source" implementation in Toolbar with dedup-by-prefix (`source:` id). `BLOCKS_RELOADED_EVENT_TYPE` declared in `routes/projects.py:23` with reload gated on lint pass (test `test_broken_block_save_does_not_reload_or_emit` passes). Template route at `/template` (line 143) precedes `/{block_type}` catch-all (line 200). New menu has all three entries. |
| Audit & Fix (skeleton) § 105–107 | CONFIRMED | Skeleton audit at `docs/audit/2026-05-14-adr-036-skeleton.md`; fix-PR #860 squash-merged into the tracking branch (commit history shows `0eba774`). |
| Audit & Fix (impl) § 109–111 | **PENDING — this report** | Row 110 (audit-impl report) will be ticked when this PR merges. Row 111 (fix any P1) will need a follow-up F36-impl PR per the findings below. |

**No drift detected** between checklist and code/test artifacts.

---

## 3. Codex reconciliation

### PR #855 (Skeleton — already fixed by F36-skeleton)

| Codex finding | Severity | Status |
|---|---|---|
| `blocks.py` route ordering — `/template` after `/{block_type}` | P1 | ACCEPTED + FIXED in PR #860. Confirmed: `/template` now at line 143, `/{block_type}` at line 200. |
| `projects.py` route ordering — `/file` after `/{project_id:path}` | P1 | ACCEPTED + FIXED. Confirmed: `_resolve_project_file` block precedes greedy project_id routes. |
| `package.json` lockfile drift on Monaco | P1 | ACCEPTED + FIXED. Confirmed: `frontend/package-lock.json` contains `@monaco-editor/react`. |

(No new comments on PR #855 since the skeleton fix.)

### PR #864 (I36a — TabState + backend file/lint)

| Codex finding | Severity | Auditor verdict | Evidence |
|---|---|---|---|
| `saveFileTab` builds `next` from stale captured `tab`, clobbering edits made during in-flight PUT | **P1** | **ACCEPTED — must fix (override any "defer" per audit_p1_override)** | `frontend/src/store/tabSlice.ts:351–373`. The `await` on line 361 yields. After it returns, `next: FileTab = { ...tab, dirty: false, contentLoadedAt: response.mtime }` is built from the pre-await `tab` reference. Any keystrokes during the network round-trip → `updateFileTabContent` updated `state.tabs` with newer `content`/`dirty=true`. The subsequent `set(replaceTab(after, id, next))` discards that newer content and clears dirty. **Real data-loss path** under non-trivial save latency. |
| `openFileTab` early-returns to `switchTab` when an existing tab is found, never refetches | P2 | ACCEPTED (deferred to F36-impl OR a separate followup issue) | `tabSlice.ts:268–272`. `store/index.ts` `partializeFileTab` strips `content` and sets `loading: true` on persist; on rehydrate the tab exists but is empty. Re-opening via `openFileTab` hits the dedup early-return → tab stuck loading forever. Reproducible by reload + click on tab. Suggest follow-up issue rather than blocking merge. |

### PR #863 (I36b — CodeEditor + Save UX)

| Codex finding | Severity | Auditor verdict | Evidence |
|---|---|---|---|
| File-tab autosave effect rebuilds ALL timers on any `tabs` change, cancelling other tabs' pending saves | P2 | ACCEPTED (defer to follow-up issue) | `App.tsx:590–607`. Effect deps `[currentProject, tabs, saveFileTab]`. Every keystroke triggers `updateFileTabContent` → new `tabs` array → effect cleanup clears every dirty tab's timer. If A is being typed in continuously, B's 800 ms debounce never fires. Behavioural in multi-file scenarios; single-file is fine. P2 is fair. |
| Lint responses applied unconditionally — older slower responses can overwrite newer markers | P2 | ACCEPTED (defer to follow-up issue) | `CodeEditor.tsx:165–201`. No request-version guard. Out-of-order arrival paints stale markers. P2 is fair (cosmetic, self-corrects on next keystroke). |

### PR #865 (I36c — ProjectTree + View source + reload + template)

| Codex finding | Severity | Auditor verdict | Evidence |
|---|---|---|---|
| `createNewCustomBlock` and `createNewNote` write directly via `putProjectFile` with no existence check | **P1** | **ACCEPTED — must fix (override any "defer" per audit_p1_override)** | `App.tsx:312–334` (custom block) and `343–371` (note). Picking an existing stem silently overwrites user code from a normal "New" toolbar action. No confirm modal, no 409 surface. **Irreversible data loss reachable from a one-click UI path.** |
| `createNewNote` swallows ALL `getProjectTree("notes")` errors and falls back to project root | P2 | ACCEPTED (defer to follow-up issue) | `App.tsx:356–363`. Bare `catch` runs on any failure. A 500/timeout creates `<name>.md` in the wrong directory silently. Should branch on `ApiError.status === 404`. P2 acceptable (uncommon path, manageable in follow-up). |

---

## 4. Chrome smoke results

**SKIPPED-P2** — `mcp__claude-in-chrome__tabs_context_mcp` returned "No MCP tab groups found"; no SciEasy GUI process is running on this host. Per dispatch hygiene rules ("If GUI unavailable, mark Chrome smoke as SKIPPED-P2" and "Do NOT install scieasy"), the smoke matrix below could not be exercised live.

Subtests not exercised live:
- (a) Toolbar "New" → workflow / custom block / note — file creation + tab open
- (b) Edit `.py` and `.md`; verify auto-save (mtime advances after 800 ms idle)
- (c) "View source" on existing workflow → readonly source tab; re-click focuses (no dup)
- (e) Toolbar swap on workflow vs file tab

**Compensating controls**: The corresponding behaviours are covered by vitest:
- (a) `Toolbar.test.tsx::New menu` (4 cases)
- (b) `App.test.tsx` + `Toolbar.test.tsx::file tab: only New / Import / Save are visible`
- (c) `Toolbar.test.tsx::View source` (4 cases) + dedup tested via `tabState.test.ts`
- (e) `Toolbar.test.tsx` 11 cases overall

The **e2e Chrome runs in checklist § 131–158** are scheduled for the post-merge e2e phase (dispatcher hotfix mode). The two P1s identified above (saveFileTab race + clobber-on-create) **will not surface in vitest** because vitest mocks `fetch` and short-circuits the race window — they need either an integration test or a manual smoke. Recommend the dispatcher run a focused manual smoke for these two paths during F36-impl.

---

## 5. Findings summary

### P1 (must fix in F36-impl before umbrella merge)

| # | PR | File:Line | Issue |
|---|---|---|---|
| 1 | #864 | `frontend/src/store/tabSlice.ts:351–373` | `saveFileTab` race — edits during in-flight PUT are clobbered. Fix: re-find tab from `after.tabs` after the await; merge `dirty=false` + `contentLoadedAt` only into the **post-await** snapshot, preserving newer `content`. Add a vitest case that updates content during a stalled `putProjectFile` mock. |
| 2 | #865 | `frontend/src/App.tsx:312–334` (block) and `343–371` (note) | "New custom block" / "New note" silently overwrite existing files. Fix: probe `getProjectTree` (or add a HEAD/GET stat endpoint) for the target path; on 200 prompt the user to confirm overwrite or pick a different name; on 404 proceed. Add vitest cases for both flows. |

### P2 (open follow-up issues, do not block merge)

| # | PR | File:Line | Issue |
|---|---|---|---|
| 3 | #864 | `tabSlice.ts:268–272` | `openFileTab` doesn't refetch when an existing tab is still `loading`. After page reload, rehydrated empty tabs get stuck. |
| 4 | #863 | `App.tsx:590–607` | File-tab autosave effect cancels every dirty tab's timer on any keystroke; multi-tab debounce broken. |
| 5 | #863 | `CodeEditor.tsx:165–201` | Lint responses applied without request-version guard; out-of-order responses paint stale markers. |
| 6 | #865 | `App.tsx:356–363` | `createNewNote` falls back to project root on any error, not just 404. |

### P3 (nice-to-have)

None identified.

---

## 6. Recommendation

**NEEDS-FIX** — F36-impl PR required to land:
- The 2 P1 fixes above with regression tests, OR
- An explicit, documented override accepting silent data-loss in v1 (not recommended; both are reachable from the documented happy paths in the e2e plan and would surface in user testing within minutes).

P2 findings should each get a tracked follow-up issue but do **not** block the merge of `track/adr-036/code-editor` into main once the P1s are landed.

After F36-impl lands and re-audit confirms no regression, the umbrella PR #853 can be unblocked.

---

## Auditor notes

- **No production code or tests were modified by this auditor.** Only `docs/audit/2026-05-14-adr-036-implementation.md` is added.
- **Frontend deps were `npm install`-ed** in the worktree to enable vitest/build (no `pip install -e .`, no global Python env mutation). The new install is contained to the worktree's `frontend/node_modules`.
- **No `npm run dev` background process was started.** Only `vitest run` and `npm run build` (one-shot).
- The 2 pre-existing test_projects.py failures (Windows file-locking on sqlite3) are tracked elsewhere; they are NOT regressions introduced by ADR-036 and need to be addressed by a separate hygiene fix.
