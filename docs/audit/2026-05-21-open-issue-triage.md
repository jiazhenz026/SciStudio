# Open Issue Triage — 2026-05-21

Read-only audit of every open issue on `zjzcpj/SciStudio` at the post-umbrella-merge
state of `main` (`c6431a19` + the `#1389`/`#1396` follow-up at `8fc8595e`).

This report is recommendations only. **No issues were closed by the audit.** The
owner decides what to act on.

## Methodology

For each open issue I cross-referenced:

1. The closing-keyword body in every merged PR (`gh pr view`, `Closes #N`).
2. Direct evidence in `origin/main` via `git log --all --grep` + targeted `grep` on
   the canonical fix surface named in the issue.
3. Open PRs that target the issue (`gh pr list --state open`), especially the
   bug-sweep umbrella PR #1377 which is `[DO NOT MERGE]` and tracks 16 of the
   currently-open audit-followup issues.
4. Memory `feedback_umbrella_subpr_manual_close` — a sub-PR merged into an
   umbrella that has not yet merged to `main` is **NOT** "fixed-close"; the issue
   stays open until the umbrella lands.
5. Memory `reference_umbrella_pr_merge_protocol` — owner removes `[DO NOT MERGE]`
   prefix as explicit go-ahead.

## Header Summary

| Category | Count |
|---|---|
| **FIXED-CLOSE** (code in `main`, safe to close) | 0 |
| **STALE-CLOSE** (superseded / no longer reproduces) | 0 |
| **KEEP-OPEN** (real, current, no fix landed) | 46 |
| **AWAITING-UMBRELLA** (fix merged into umbrella #1377, not yet on `main`) | 16 |
| **NEEDS-OWNER** (owner decision required) | 0 |
| **Total open issues** | 62 |

**Headline finding:** There are no slam-dunk "stale, should close" issues. The
recent owner-led housekeeping cascades (ADR-039 Addendum 1 umbrella #1364,
no-cycles umbrella #1344, brand rename #1319) already closed everything that had
landed; what remains is genuinely-open work.

The single biggest cleanup opportunity is **owner-side**: spot-check the
bug-sweep umbrella PR #1377 and authorize its final merge. That single action
will close 16 of the 62 open issues at once.

## AWAITING-UMBRELLA — wait for PR #1377 merge

These 16 issues all have fix PRs already **merged into** the umbrella branch
`umbrella/2026-05-21-bug-sweep`, but the umbrella PR itself is still
`[DO NOT MERGE]` (open against `main`). They will auto-close on umbrella merge
via the `Closes #N` block in PR #1377's body.

**Owner action:** review PR #1377 + remove `[DO NOT MERGE]` prefix when ready.

| # | Title | Sub-PR | Sub-PR status |
|---|---|---|---|
| #617  | escape apostrophes in PowerShell file dialog commands | [#1379](https://github.com/zjzcpj/SciStudio/pull/1379) | merged → umbrella |
| #902  | CI flake: test_ai_block_skeleton.py StubAgent/CompletionWatcher race | [#1395](https://github.com/zjzcpj/SciStudio/pull/1395) | open → umbrella |
| #1109 | BlockRegistry.find_loader/find_saver compound-extension fallback | [#1392](https://github.com/zjzcpj/SciStudio/pull/1392) | merged → umbrella |
| #1110 | SaveData.supported_extensions: include .markdown / .htm | [#1379](https://github.com/zjzcpj/SciStudio/pull/1379) | merged → umbrella |
| #1281 | prevent same-named input/output manifest overwrite | [#1379](https://github.com/zjzcpj/SciStudio/pull/1379) | merged → umbrella |
| #1282 | narrow CodeBlock v2 validator detection | [#1379](https://github.com/zjzcpj/SciStudio/pull/1379) | merged → umbrella |
| #1306 | TIFF loader ignores OME-TIFF metadata despite capability claim | [#1388](https://github.com/zjzcpj/SciStudio/pull/1388) | merged → umbrella |
| #1309 | CodeBlock backends ignore working_directory, hardcode cwd=exchange_dir | [#1392](https://github.com/zjzcpj/SciStudio/pull/1392) | merged → umbrella |
| #1343 | Register drop-in modules in sys.modules before storing type specs | [#1386](https://github.com/zjzcpj/SciStudio/pull/1386) | merged → umbrella |
| #1365 | worker reconstruction does not load project/user TypeRegistry scan dirs | [#1386](https://github.com/zjzcpj/SciStudio/pull/1386) | merged → umbrella |
| #1366 | PortEditorTable capability_id stays stale after type/extension change | [#1397](https://github.com/zjzcpj/SciStudio/pull/1397) | open → umbrella |
| #1367 | BLOCK_READY missing on resume/rerun/reset READY transitions | [#1391](https://github.com/zjzcpj/SciStudio/pull/1391) | merged → umbrella |
| #1368 | Fiji/AppBlock integration helper still calls removed Block.transition | [#1379](https://github.com/zjzcpj/SciStudio/pull/1379) | merged → umbrella |
| #1369 | Save Image browse selects a directory for single-file save paths | [#1395](https://github.com/zjzcpj/SciStudio/pull/1395) | open → umbrella |
| #1370 | interactive scheduler path skips collection output normalization | [#1391](https://github.com/zjzcpj/SciStudio/pull/1391) | merged → umbrella |
| #1371 | imaging metadata fidelity overclaims OME, lossy-warning too exact | [#1388](https://github.com/zjzcpj/SciStudio/pull/1388) | merged → umbrella |

**Notes**

- PRs #1395 and #1397 are still OPEN against the umbrella branch; they need to
  merge into the umbrella first before the umbrella can sensibly merge to main.
- All 16 issues are explicitly listed in the `Closes` block of PR #1377's body —
  GitHub will auto-close on the umbrella's merge to main. No manual close needed.

## KEEP-OPEN — 46 issues, genuine work

### Category 1 — Major features / specs not yet implemented (10)

| # | Title | Evidence kept-open |
|---|---|---|
| #56   | subprocess-to-engine status communication channel (ADR-017) | `grep report_status/report_progress src/scistudio` → 0 matches; explicitly reopened 2026-05-21 with audit evidence. |
| #819  | Spec: scieasy-blocks-metadata plugin package | Doc-only spec; no PR has landed. |
| #822  | LoadData type-picker wizard | No frontend wizard implementation in `frontend/src/components/Palette*`. |
| #827  | central event/log helper subscribing to all engine events | Module `scistudio/utils/logging.py` still `NotImplementedError`; `_bind_event_logging` still subscribes to 7/14 events. |
| #835  | Bottom-panel Lineage + Jobs tabs | `BottomPanel.tsx` still falls through to `PlaceholderTab` for lineage/jobs. |
| #887  | Engine resource accounting (L1 GPU/CPU slots) | `scheduler.py:197` still calls `can_dispatch(ResourceRequest(), ...)`. |
| #1015 | ADR-041 placeholder: Layer 7 filesystem ACL on blocks/ | Explicit placeholder for ADR-040 TODO tags. |
| #1016 | ADR-041 placeholder: BlockRegistry reject DataObject-typed ports | Explicit placeholder. |
| #1204 | ADR-043 package migration — explicit IO format capabilities | Tracking issue for cross-package migration. |
| #1384 | Non-blocking Playwright GUI E2E discovery suite | PR #1387 open; not yet merged. |

### Category 2 — Active P0/P1 bugs needing implementation (5)

| # | Title | Evidence kept-open |
|---|---|---|
| #679  | communicate user-configured output_dir to launched app | P1; no fix PR. |
| #841  | Codex not-installed / terminal hang on Windows when backend runs Python 3.12.0 | P1; no fix PR; PATHEXT regression specific to CPython 3.12.0 still in place. |
| #888  | iterate_over_axes materializes full source (Zarr O(one slice) violation) | P1; `axis_iter.py:151-154` still calls `source.to_memory()`. |
| #889  | API validate_connection + edge coloring ignore node config | P1 ADR-028/029 drift; no fix PR. |
| #1336 | Circular import: blocks.registry ↔ ai.agent.* (10-module SCC) | **P0**; no fix PR. Cited as the remaining cluster after #1335/#1337 cleaned 3 of 5. |

### Category 3 — Pending docs / spec follow-ups (5)

| # | Title | Evidence kept-open |
|---|---|---|
| #661  | align Block SDK docs with ADR-031 Addendum 2 — data= constructor | Mechanical doc rewrite still required; no PR. |
| #882  | ADR-035 §3.5 amend: completion semantics OR → conditional-AND | Spec amendment, no PR. |
| #1098 | MCP qa tools serve packaged user-facing docs | P1; #1097 closed but the broader gap remains. |
| #1246 | Add ADR-042 interface wiring + schema compatibility audit | Tool not built. |
| #1331 | ARCHITECTURE §5.3 overstates subprocess isolation | P1 docs-only carve-out; no PR. |

### Category 4 — UX/spec needs design (5, all "issue-only" per owner)

| # | Title | Evidence kept-open |
|---|---|---|
| #1322 | investigate: prod yaml auto-open intermittently fails after agent write_workflow | Owner-reported, couldn't reproduce; spec needed if it recurs. |
| #1323 | GUI hydrates block status + checkpoint outputs from completed lineage runs | Spec needed. |
| #1324 | UX/spec: Code Block panel mirror Fiji block | Spec needed (owner explicit issue-only). |
| #1325 | UX/spec: Code Block canvas variable ports + `+` button | Spec needed. |
| #1326 | UX/spec: port behavior annotations in right-side preview pane | Spec needed. |

### Category 5 — P2/P3 cleanup / tech debt (16)

| # | Title | Evidence kept-open |
|---|---|---|
| #177  | useSSE/useWebSocket reconnection logic | Hooks still ~26-29 LOC, no reconnect logic in `frontend/src/hooks`. |
| #490  | tracking(macOS): macOS platform compatibility | Living tracking issue, sub-issues #493/#495/#499/#796 still open. |
| #709  | FijiBlock ignores user-added variadic input ports | `fiji_block.py` still hard-codes `"image"` port. |
| #881  | AI Block prompt sits in input box, waits for manual Enter | No deterministic ready-signal solution shipped. |
| #891  | Wheel build silently succeeds without SPA | `setup.py:86-103` unchanged. |
| #969  | ADR-039 P3 nits (is_repository worktree, FF heuristic, log parser) | Cleanup, no PR. |
| #1245 | ADR-041 backend-managed CodeBlock artifact outputs | Track C2 follow-up, no PR. |
| #1283 | gate-record support for integration PRs (worker scope false fail) | P2; partial fix `90eb6e40` is for AI override only, not integration scope. |
| #1329 | Storage reference invalidation surfaces raw backend tracebacks | P1; no fix PR. |
| #1337 | Circular import: pairwise cycles in engine.runners + core.versioning | **CLOSED** in PR #1348? Check below. |
| #1341 | Add `no_cycles` import-linter contract once #1336 lands | Blocked by #1336. |
| #1342 | Eliminate lazy import in core.storage.backend_router.get_router | Transitional debt after #1335. |
| #1345 | gate-record PreToolUse hook fails on stacked PRs | P2 governance hook bug, no fix. |
| #1349 | degrade Sentrux failure from hard-block to warning | Policy change, no PR. |
| #1372 | scistudio_pr_create.py support gh pr create fill body modes | No fix. |
| #1373 | BottomPanel native file-browser fallback regression coverage | Test gap. |

> **Note on #1337**: PR #1348 merged `e13e5d6d refactor(#1337)` to break the
> pairwise cycles. Issue #1337 is currently OPEN in GitHub but its scope is
> partly done. See "NEEDS-OWNER" subsection below.

### Category 6 — Just-filed (post-audit followups, ≤2 days old, all real) (5)

| # | Title | Evidence kept-open |
|---|---|---|
| #1374 | TypeRegistry drop-in synthetic module names can collide | Filed 2026-05-21 audit followup; no PR. |
| #1375 | reconcile failed workflow-gate evidence on recently merged PRs | Filed 2026-05-21 audit followup; no PR. |
| #1376 | align cancel_block with scheduler state-machine contract | Filed 2026-05-21; no PR. |
| #1380 | cleanup mechanism for refs/scistudio/lineage/* tags | Follow-up from #1356/#1381; deferred by owner. |
| #1390 | engine.branches() heads/<name> when tag shares branch short name | Filed 2026-05-21 by Agent C; no PR. |

### Category 7 — Polish nits already deferred (1)

| # | Title | Evidence kept-open |
|---|---|---|
| #1394 | ADR-039 Addendum 1 audit P3 findings (4 nits) | Explicitly deferrable; owner can leave open or batch later. |

## FIXED-CLOSE candidates

**None confirmed.** Every issue I expected to be "fixed-but-not-closed" turned
out to be one of:

- Already closed (and not in the open-list) — e.g. #1335, #1340, #1332, #1330,
  #1334, #560 all already CLOSED.
- Or stuck in the bug-sweep umbrella (AWAITING-UMBRELLA category above).

## STALE-CLOSE candidates

**None confirmed.** No issue tracks behavior that no longer exists. The closest
candidate was **#1337** (see NEEDS-OWNER below) but it's an active multi-part
issue; PR #1348 addressed one of the two cycles + added the import-linter
foundation, but neither the import-linter contract (#1341) nor #1336's SCC are
yet done. Closing #1337 would orphan its tracker role for #1341/#1336.

## NEEDS-OWNER

### 1. #1337 — partial completion question

`refactor(#1337): break engine.runners + core.versioning pairwise cycles`
(commit `e13e5d6d`) is merged on `main`. The pairwise cycles are gone.

The remaining scope listed in #1337's body is "add no_cycles contract" — which
was correctly extracted into #1341 once #1336 is done. So the issue's
**original P3 work is complete**.

**Question for owner:** close #1337 with reference to PR #1348 + #1341 carrying
the contract follow-up? Or leave it open as the umbrella for #1341+#1336?

Suggested command if owner says close:
```
gh issue close 1337 -c "Pairwise cycles in engine.runners + core.versioning are fixed (PR #1348, commit e13e5d6d on main). The no_cycles import-linter contract is tracked separately by #1341 (blocked by #1336). Closing the parent; the two children carry the remaining scope."
```

### 2. #56 — recent reopen + comment thread, no plan

#56 was previously closed-and-reopened on 2026-05-21 with audit evidence that
the documented `report_status`/`report_progress` protocol does not exist in
`src/scistudio/`. The reopener's verdict matches my own grep evidence.

**Question for owner:** is #56 currently planned, or is "PAUSED never reaches
the GUI" an accepted limitation? If planned, this is a moderately-sized feature
(needs subprocess→engine stdout JSON protocol; estimated ~150 LOC for the
helper + ~50 LOC per consumer). If accepted, add a `wontfix` label + close.

### 3. #1283 — partial-fix tracking

Commit `90eb6e40 fix(#1283): honor AI override in workflow gate` is on main.
Issue #1283 is technically about integration-PR gate records, of which
AI-override is one case. The other case (umbrella PRs with worker-scope
records) is partly handled by ADR-042 Addendum 1 (PR #1272).

**Question for owner:** is #1283 considered done by `90eb6e40`+ADR-042
Addendum 1, or are there remaining acceptance criteria? Recommend reading
the issue acceptance list against current gate-record CI behavior.

## Owner top-5 recommendations

1. **Spot-check + authorize bug-sweep umbrella PR #1377 merge** — this closes
   16 issues in one merge. Single highest leverage action.
2. **Decide on #1337** — close with reference to #1341 if the original P3 scope
   is what's tracked; or rename to be the umbrella for #1341+#1336.
3. **Decide on #56** — concrete plan or `wontfix`. It's blocking #560's
   meaningfulness and surfaced as audit evidence in the 2026-05-21 architecture
   audit.
4. **Triage #1336 (P0)** — circular import `blocks.registry ↔ ai.agent.*`
   crosses the documented Layer 2 vs Layer 4 boundary. Either fix or
   downgrade the priority.
5. **Triage stale UX/spec issues (#1324, #1325, #1326)** — owner tagged them
   "issue-only" on 2026-05-21. If a Code Block UX rework isn't on the near-term
   roadmap, consider labeling them `roadmap` so they don't show as "open work".

## P1 blockers found

**None.** The audit did not find any correctness or security issue that should
block PR #1364 (already merged) or PR #1377 (pending owner authorization).

## Methodology notes / coverage limits

- I read titles + first 1-1.5 KB of body for all 62 issues, plus the full body
  of issues that needed root-cause cross-referencing.
- For evidence-by-grep I used `git log --all --grep="#NNN"` and targeted
  `grep` on the canonical file paths called out in each issue body.
- I did not run the test suite or live-Chrome-smoke any of the issues —
  per the read-only audit charter.
- The 62-issue total is consistent across `gh issue list --state open --limit 100`
  and `gh issue list --state open --limit 200 | sort -nu` (issue #1389 closed
  during the audit window).
