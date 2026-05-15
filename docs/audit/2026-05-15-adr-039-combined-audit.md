# Audit report — D39-3.1 combined audit (track/adr-039/git-versioning)

Date: 2026-05-15
Tracking branch HEAD: `85858972a5102a41bb2c961a104254b665e3e565`
PRs reviewed: #918, #922, #924, #927, #930, #940, #945, #952, #958, #959
Sub-issue: #964
Checklist rows verified: ADR-039 phases D39-2.1 → D39-2.5 (all `[x]`-marked rows scanned for artifact links + ADR compliance)

## Summary

**pass-with-fixes** — All four sub-scopes (skeleton-vs-ADR, impl-vs-design, wiring reliability, Chrome smoke) reviewed. Local CI is green (89 backend tests + 106 frontend tests pass, ruff/format clean, all skeleton phases reached IMPL on time). Findings concentrate on two areas: (a) a **dual git-watcher subsystem** with inconsistent payload keys that silently breaks the `commit_sha` field on one of the two paths (P1), and (b) **integration-boundary** concerns flagged by the existing Phase 3.5 audit (H-A1, H-D1, H-D2) — Phase 3.5 is the correct venue for the structural fix; this audit corroborates the hazards from the ADR-039 side. The live Chrome smoke could not be completed automatically because the Chrome MCP protocol requires interactive user selection of the browser device; falling back to a static walk-through of the build pipeline + dispatched smoke tests in the upstream impl PRs.

## Checklist drift

No drift observed. Every `[x]` row inspected on the cascade checklist (`docs/planning/adr-038-039-checklist.md` ADR-039 section) has either an artifact link to a real merged PR (#924, #927, #930, #940, #945, #952, #958, #959) or an in-tree commit reference (commit `e981303` for D39-2.1). The only `[~]` partial is `desktop/package.json` in D39-2.2a, correctly deferred — verified that `desktop/` contains only `scripts/` and no `package.json`, so the deferral note in the checklist (`ADR-037 packaging pipeline pending`) is accurate.

## ADR compliance

### Major divergences

None. ADR §3.1 (bundled git CLI subprocess), §3.2 (auto-init), §3.3 (.gitignore), §3.4 (pre-run auto-commit + filter), §3.4a (commit prefixes), §3.5 / §3.5a / §3.5b / §3.5c (REST surface, Monaco conflict UX, lane-assigned graph, filter), §3.6 (restore), §3.7 (branch ops), §3.8 (external git watcher), §3.9 (no-git opt-out) are all materially implemented.

### Minor divergences (each surfaced as a finding below)

- §3.4a "Agent commit prefix" — only the `git log --format` plumbing knows about `agent:`; **no in-tree code path actually emits an `agent:` commit**. AIBlock docstring claims `mcp__scieasy__git_commit` does, but that MCP tool does not exist in the repo. See P2-A.
- §3.8 "External git changes are respected" — implemented via **two independent watcher subsystems** with overlapping responsibilities and inconsistent payload shapes. See P1.

## CI status

- ruff: **pass** (`ruff check src/scieasy/core/versioning/ src/scieasy/api/routes/git.py` → "All checks passed")
- ruff format: **pass** (7 files already formatted)
- pytest (ADR-039 surface, `--timeout=60 --no-cov`): **89/89 passed** in 28.66s — `tests/core/test_git_engine.py`, `tests/api/test_git_endpoints.py`, `tests/api/test_workflow_run_git.py`, `tests/api/test_workflow_watcher_git.py`, `tests/api/test_ws_git_events.py`, `tests/cli/test_init_git_init.py`
- vitest (Git surface): **106/106 passed** in 1.88s — `Git/__tests__/*`, `Git/GitGraph/__tests__/*`, `store/__tests__/gitSlice.test.ts`
- frontend build: **pass** (`npm run build` succeeded; chunk-size warnings unrelated to this work)
- backend boot smoke: **pass** (`scieasy serve --port 8123` answers `/health` → 200 and `/api/git/status` → 409 "No active project" as expected for a no-project boot)
- live Chrome smoke: **deferred** — see "Smoke test status" below.

## Smoke test status

**Mandatory live Chrome smoke not executable in this audit session.** Two factors:

1. `mcp__claude-in-chrome__list_connected_browsers` reports 2 devices and its protocol requires asking the user to pick one before any browser action. The agent dispatch runs non-interactively (no user available to answer), so the audit must defer the live smoke.
2. **D39-2.3b's PR #940 already shipped a Chrome smoke GIF** (`d39-2-3b-smoke.gif` per the checklist row, covers commit dialog + branch create + switch). D39-2.4b's PR #952 was supposed to ship a conflict-resolution smoke per its checklist row but **that GIF is not referenced in the checklist artifact link** — recommend checking PR #952 body for the GIF and, if missing, flagging as P2 for D39-3.2.

**Recommendation**: D39-3.2 fix dispatch (or the Phase 4b e2e dispatch) MUST perform the live smoke covering the 11 scenarios in the dispatch (project create → auto-init → edit → commit → history → filter → branch → merge clean → merge conflict → graph render). Do **not** treat the absence of this smoke as audit pass — it is a known gap.

## Findings (P1 — must fix; P2 — should fix; P3 — nice to have)

### P1 — Dual git-watcher subsystems with inconsistent payload shape

**Affected files**:
- `src/scieasy/api/app.py:84-112` (constructs `core.versioning.watcher.GitChangeWatcher`)
- `src/scieasy/core/versioning/watcher.py:153-167` (emits `git.head_changed` with key `head_sha`)
- `src/scieasy/api/routes/workflow_watcher.py:427-453` (`_GitHeadHandler.on_any_event` emits `git.head_changed` with key `commit_sha`)
- `frontend/src/hooks/useWebSocket.ts:147-166` (reads `data.commit_sha`)

**Symptom**: `git.head_changed` events arrive at the frontend with `commitSha = null` whenever they originate from the asyncio-poll watcher (`core/versioning/watcher.py`), because that watcher emits `{project, head_sha, branches_changed}` while the watchdog-based handler (`workflow_watcher._GitHeadHandler`) emits `{commit_sha, ref, kind}`. The frontend keyed on `commit_sha`. The `invalidateHistory()` call still fires (the gate is `payload.type === "git.head_changed"`), so caches still clear; but the debug log line `[git.head_changed] commit=null ref=HEAD kind=head` is the visible canary of the drift, and any future consumer that depends on the SHA will silently get null on half the events.

**Secondary symptom**: Two watchers running in parallel doubles event volume. With external git CLI commits the user can get two `invalidateHistory()` round-trips back-to-back within a couple of seconds (watchdog fires immediately on the mtime change; the 1s poll then catches the same change). Cache thrash, not correctness.

**Recommended fix**:
1. Pick one watcher as canonical for ADR-039 §3.8. `workflow_watcher._GitHeadHandler` is preferable — it uses the same watchdog Observer that already lives on `app.state` for the YAML watcher, so adding a polling task is dead code by comparison.
2. Delete `src/scieasy/core/versioning/watcher.py` (or downgrade it to a `from .._compat import ...` shim) + remove the construction in `app.py:84-112`.
3. Standardize the WS payload key on `commit_sha` (matches the frontend reader and matches the rest of the codebase's lineage naming).

**Severity**: P1 — drift between watchers will compound: every D39-3.2 / Phase 4b smoke that re-tests external git CLI commits will rediscover this. The frontend already had a Codex-flagged "commit=null" log entry that nobody investigated.

### P1 — `runs.workflow_git_commit` join key never persisted on the integration boundary

**Affected files**:
- `src/scieasy/api/runtime.py:1333-1343` (calls `lineage_store.set_pending_git_commit(...)` defensively)
- `src/scieasy/core/lineage/store.py` on `track/adr-038/lineage-db` (the method does NOT exist)

**Status**: This is the H-A1 hazard already enumerated in `docs/planning/adr-038-039-checklist.md` Phase 3.5 Section A. ADR-039 side is **correct in isolation** (the SHA is captured on `WorkflowRun.workflow_git_commit` and the `set_pending_git_commit` forward-compatible hook is defensive `getattr` + `callable()`-guarded). However, on the integration tracking-branch state, `LineageStore.set_pending_git_commit` is not defined, so the captured SHA never reaches the database column. Phase 4b e2e test (a) — "Each of 6 runs answers ADR-038's 4 user questions through Lineage tab UI" — will fail silently with `workflow_git_commit IS NULL` on every run.

**Recommended fix path**: D38-3.2 fix PR adds `LineageStore.set_pending_git_commit(workflow_id, sha)` writing to `runs.workflow_git_commit` for the most recent run with the matching `workflow_id`. ADR-039 side requires **no change** — its defensive hook will activate the moment ADR-038 adds the method.

**Severity**: P1 — release-blocker for the join semantics that motivate the entire ADR-038/039 split. Tracked under the existing Phase 3.5 audit row; this audit reaffirms it from the ADR-039 angle and recommends the D38 fix happen **before** Phase 4b.

### P2-A — `agent:` commit prefix has no in-tree emitter

**Affected file**: `src/scieasy/blocks/ai/ai_block.py:11-32` (claims two emission layers)

**Symptom**: The AIBlock docstring states the `agent:` prefix is enforced via (1) `scieasy.api.routes.mcp_tools.git_commit` passing `prefix="agent"` to `GitEngine.commit()`, and (2) the agent's system-prompt being told the convention. Layer (1) does **not exist in the repo** — `grep -rn "mcp_tools" src/scieasy/` returns no matches, and there is no `git_commit` MCP tool registered anywhere under `src/scieasy/ai/`. The convention is therefore documented but unenforced: the only way a real `agent:` commit appears in `git log` is if the agent itself types `git commit -m "agent: ..."` in the PTY, relying entirely on the system-prompt rule. The History "Manual milestones" filter (default) then works as long as agents obey the prompt — but Phase 4b Test 2 ("Open AI chat; instruct agent to make a change and commit it") will likely fail the "shows `agent:` prefix + 🤖 icon" criterion unless the system prompt is verified.

**Recommended fix**:
1. Either implement the `mcp__scieasy__git_commit` MCP tool (a thin wrapper around `GitEngine.commit(prefix="agent")`) and register it on the MCP server, **or**
2. Update the AIBlock docstring to remove the false claim about layer (1), and add a Phase 4b sub-task to verify the agent system prompt teaches the convention.

**Severity**: P2 — does not break user flows today (no agent path is wired), but ships a misleading contract into the codebase and creates a known gap for D39-2.5's "verify agent flows emit `agent:` prefix" checklist row (currently `[x]` — the audit can't substantiate that tick).

### P2-B — `git_watcher` in `app.py` only starts for the project that was active at lifespan-startup

**Affected file**: `src/scieasy/api/app.py:84-112`

**Symptom**: `git_watcher.start_for_project(...)` runs once inside the lifespan context manager, gated on `runtime.active_project is not None`. There is **no equivalent restart hook in `runtime.open_project`** or anywhere else, so opening a different project mid-session leaves the watcher pointed at the original project's `.git/`. The user will see HEAD-change events for the previous project after switching — or, if the original project was deleted, no events at all.

**Note**: The `workflow_watcher` (YAML watcher) has the same general shape, but it ships a `start_for_project` re-entry point that is called from `runtime.open_project` (verified at `runtime.py` references to `workflow_watcher_module.set_active_watcher`). The git-watcher needs the same hook.

**Recommended fix**: When fixing P1 above by collapsing onto the single `workflow_watcher._GitHeadHandler`, this gap closes for free (that watcher's `start_for_project` is already called on project switch, per its existing design). If P1 fix is deferred, add a `runtime.open_project` hook that calls `app.state.git_watcher.start_for_project(...)`.

**Severity**: P2 — user-facing but only after a project-switch + external git operation, and per memory `phase_audit_smoke_test` the dispatch's Phase 4b smoke MUST exercise project-switch to surface this. Recommend reusing the P1 fix's collapse as the resolution.

### P2-C — `start_workflow` pre-run auto-commit silently captures empty-string SHA on a brand-new uncommitted repo

**Affected file**: `src/scieasy/api/runtime.py:1255-1294`

**Symptom**: In the rare case where the project's `.git/` exists but has no commits (e.g. `git init` happened externally and the user clicks Run before any commit), `engine.head_state()` returns `HeadState("", False)` (per `git_engine.py:507-511`, which swallows the `rev-parse HEAD` failure). The runtime then assigns `workflow_git_commit = state.commit_sha or None` (line 1294) — the `or None` does the right thing here, but the surrounding branch (line 1266-1272) for the dirty case calls `engine.commit(msg, prefix="auto")` which depends on `git diff --cached --quiet` returning non-zero. On an empty repo with no commits, `git diff --cached` against a non-existent HEAD has historically returned 0 even when the tree is non-empty (git plumbing edge case). The pre-run auto-commit will therefore raise `GitError("nothing to commit, working tree clean")`, the broad `except Exception` swallows it, and the run executes with `workflow_git_commit = None`. Not a crash, but the join key is null for the first run on a freshly-inited project — surprising for users.

**Recommended fix**: Adjust the `commit()` empty-tree detection (`git_engine.py:215-217`) to consider `git rev-parse HEAD` failing → treat any non-empty index as "this will create the first commit". Or: ensure project auto-init (which is supposed to make the initial commit per ADR §3.2) actually ran — verify by `engine.is_repository(...)` AND `engine.head_state().commit_sha != ""`; if the latter fails, force an initial commit on the spot.

**Severity**: P2 — corner case (project created by a non-SciEasy path), but it's the failure mode users blame on "SciEasy lost my history".

### P3-A — `is_repository` may return false negative on `.git` worktree-link files

**Affected file**: `src/scieasy/core/versioning/git_engine.py:171-183`

**Symptom**: `is_repository` first checks `(Path(path) / ".git").exists()` and returns True if so. In a **git worktree** (used by sub-agent isolation in this very repo, per `.claude/worktrees/`), `.git` is a **file**, not a directory — `exists()` still returns True, so this branch is fine. But the **fallback** path runs `git -C <path> rev-parse --git-dir` with no further filtering; on a worktree this returns the absolute path of the main `.git/worktrees/<name>` dir, which the caller may interpret literally. None of the call sites in this repo inspect the return value beyond truthiness, so this is presently latent.

**Recommended fix**: Document the worktree case in the docstring; consider returning a `Literal["repo", "worktree", "not-a-repo"]` tri-state if any consumer ever needs the distinction.

**Severity**: P3 — no current consumer affected.

### P3-B — `git_engine.merge()` FF-detection relies on parent-count heuristic

**Affected file**: `src/scieasy/core/versioning/git_engine.py:553-563`

**Symptom**: After a `git merge --no-edit`, FF is detected by comparing the pre-merge HEAD against the post-merge HEAD and the parent count of the new HEAD. A two-parent HEAD with FF-ancestor relationship is correctly labelled `fast-forward`. A clean three-way merge produces a two-parent HEAD without the FF ancestor relationship, labelled `clean`. This works for the common cases but the heuristic is more brittle than the canonical "did `git merge --ff-only` succeed?" check. If git ever changes `--no-edit` semantics, the labels drift. Acceptable for v1; flag for future hardening.

**Recommended fix**: Optional — pre-check FF with `git merge-base --is-ancestor HEAD source` (already done, line 524-530) and on success run `git merge --ff-only` first; only fall back to three-way if that returns 0 with HEAD unchanged.

**Severity**: P3 — no observed misclassification today.

### P3-C — `git log` template parser drops records with missing/empty body field

**Affected file**: `src/scieasy/core/versioning/git_engine.py:283-307`

**Symptom**: The custom-delimited template `%H{US}%h{US}%P{US}%an{US}%ae{US}%aI{US}%s{US}%b{RS}` produces 8 fields per record; the parser requires `len(fields) >= 8` (line 290-291). A commit with an empty body still emits 8 fields (the trailing `%b` produces a 0-length string). However the per-record `lstrip("\n")` immediately before the `split` (line 286) followed by an `if not rec: continue` (line 287) handles the leading-newline-record-separator artifact correctly. Risk is low; flag for note only.

**Severity**: P3.

## Codex reconciliation

Walked the merged-PR Codex review counts:

| PR | Codex reviews | Status |
|---|---|---|
| #918 (D39-2.1) | 3 | All reconciled in #922 follow-up + commit references (e.g. `.git lockfiles + worktree idempotency`). No outstanding. |
| #922 | 0 | Follow-up commit, no review. |
| #924 (D39-2.2a skeleton) | 2 | Reconciled inline; no outstanding. |
| #927 (D39-2.2b impl) | 1 | Reconciled — see commits `6d21347` (Codex P1: merge() error envelope + lazy git locate), `91d110d` (lint), `8ebb17a` (rmtree dir perms). All accepted. |
| #930 (D39-2.3a skeleton) | 4 | Reconciled — see commit `0b5e6b8` ("align frontend types with PR #927 backend wire shapes (Codex P2)"). |
| #940 (D39-2.3b impl) | 5 | Reconciled — commit `c934b6f` ("Codex P1+P2 reconciliation on PR #940"). |
| #945 (D39-2.4a skeleton) | 2 | Reconciled — commit `20fee29` (Codex P1: re-run conflict-decoration effect after Monaco lazy-mounts). |
| #952 (D39-2.4b impl) | 4 | Reconciled — commit `6ed0324` ("reconcile Codex P1 + P2s on PR #952"). #958 followed up to recover an orphan reconcile commit. |
| #958 | 0 | Follow-up. |
| #959 (D39-2.5 polish) | 2 | Reconciled — commit `4d2b533` (Codex P1: degrade `workflow_git_commit` to None on commit failure) + `bc10a09` (REST-route integration test refactor). |

No silent-deferred Codex P1 found. The above table demonstrates the cascade kept its reconciliation discipline.

This audit does **not** add new Codex-reply comments because it found no P1 that the implementer-side cascade missed; the P1s in this audit (the dual-watcher + the integration H-A1) emerge from cross-track wiring, which the implementer-side Codex review cannot see in isolation.

## Recommendation for fix agent (D39-3.2)

In priority order:

1. **P1 dual-watcher**: collapse `core/versioning/watcher.py` into the `workflow_watcher._GitHeadHandler` path; standardize the WS payload key on `commit_sha`; remove `app.py:84-112` construction. This also resolves P2-B (project-switch watcher restart).
2. **P1 H-A1 (already filed)**: dispatch the D38-3.2 fix to add `LineageStore.set_pending_git_commit(workflow_id, sha)`. ADR-039 needs no change.
3. **P2-A**: decide between (a) implementing the missing `mcp__scieasy__git_commit` tool and (b) correcting the AIBlock docstring + adding the system-prompt verification to Phase 4b.
4. **P2-C**: harden `GitEngine.commit()` empty-repo detection.
5. **MANDATORY before D39-3.2 reports done**: live Chrome smoke covering the 11 scenarios in this audit's dispatch (project create + auto-init, edit + commit, history filter cycle, branch create/switch, merge clean, merge conflict + resolution, graph render). Without this smoke, the audit cannot pass per memory `phase_audit_smoke_test`. The audit deferred it because of the Chrome MCP interactive-browser-pick gate; the fix dispatch (or its operator) must drive Chrome MCP under a user who can answer the device prompt.

P3 items are not release-blockers; file as follow-ups.
