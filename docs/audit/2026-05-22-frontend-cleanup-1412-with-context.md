---
title: "Frontend Cleanup #1412 — With-Context Audit"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 45
language_source: en
---

# Frontend Cleanup #1412 — With-Context Audit

> Audit mode: with-context (issue #1426, checklist, PR #1428, six sub-PRs, gate
> records, and CHANGELOG were all available to the auditor).

## 1. TL;DR

- **Recommendation: pass-with-fixes** for Wave 4 manager integration.
- Five of the eight remaining waiver blocks in `frontend/eslint.config.js` are
  confirmed dead-weight (would lint clean if commented out today).
- **One waiver block — `#1422` god-file — is still ACTIVE**: removing it
  surfaces 5 hard ESLint errors that the umbrella diff did not retire.
  Specifically `src/App.tsx` (function 392 LOC, complexity 17),
  `src/components/nodes/BlockNode.tsx` (function 198 LOC, complexity 49), and
  `src/components/BottomPanel.test.tsx` (file 610 LOC) still violate
  `max-lines-per-function` / `complexity` / `max-lines`. The Wave 2 sub-PRs
  reduced these files' top-level sizes but did not reduce the top-level
  function size below 150 LOC and did not bring complexity under 15.
- The `#1415` eqeqeq waiver is correctly still active (Wave 4 manager-owned;
  not claimed retired by any sub-PR).
- All other claims hold: every merged sub-PR is scope-compliant, all 571
  vitest cases pass (including the 20 ADR-045 versionVector cases on
  `useWebSocket.ts` / `tabSlice.ts` / `workflowSlice.ts`), ruff is clean, full
  audit is clean, sentrux passes (5 cycles ≤ 5 threshold).
- Sub-issue closures #1413 #1414 #1416 (full) #1417 #1419 #1420 #1421 are
  delivered. #1422 is **only partially** delivered (file-size dropped, but
  function-size and complexity still over). #1415 is deferred-as-planned.

## 2. Findings

### P1 — Blocks Wave 4 manager strip of `GOD_FILE_SIZE_WAIVERS`

**P1.1 — `#1422` god-file waiver still hides 5 active lint errors.**

Reproducer (run from `frontend/`):

```
cp eslint.config.js eslint.config.js.bak
# Delete the GOD_FILE_SIZE_WAIVERS block (lines 181-189 of the file)
npx eslint .   # observe 5 errors
cp eslint.config.js.bak eslint.config.js
```

Output observed during this audit:

```
src/App.tsx:62:16  error  Function 'App' has too many lines (392). Maximum allowed is 150  max-lines-per-function
src/App.tsx:62:16  error  Function 'App' has a complexity of 17. Maximum allowed is 15     complexity
src/components/BottomPanel.test.tsx:553:1  error  File has too many lines (610). Maximum allowed is 500  max-lines
src/components/nodes/BlockNode.tsx:36:8  error  Function 'BlockNode' has too many lines (198). Maximum allowed is 150  max-lines-per-function
src/components/nodes/BlockNode.tsx:36:8  error  Function 'BlockNode' has a complexity of 49. Maximum allowed is 15     complexity
```

File-level totals after Wave 2:

| File | LOC | top-level fn LOC | top-level fn complexity |
|---|---|---|---|
| `src/App.tsx` | 494 ≤ 500 ✓ | 392 > 150 ✗ | 17 > 15 ✗ |
| `src/components/nodes/BlockNode.tsx` | 295 ≤ 500 ✓ | 198 > 150 ✗ | 49 > 15 ✗ |
| `src/components/BottomPanel.test.tsx` | 667 > 500 ✗ | — | — |

The Wave 2 sub-PRs (#1450 / #1447 / #1446) reduced each god file's _file_
length below 500 LOC by extracting sibling modules under `*.parts/`, but
they did not reduce the orchestrator function size below 150 LOC and did not
reduce its complexity below 15. The `GOD_FILE_SIZE_WAIVERS` block waives all
three rules (`max-lines`, `max-lines-per-function`, `complexity`) on every
listed file simultaneously, so the umbrella PR's green CI hides three real
violations on App.tsx + BlockNode.tsx and one file-size violation on
BottomPanel.test.tsx.

**Impact on Wave 4 strip:** the manager cannot strip the
`GOD_FILE_SIZE_WAIVERS` block as a single step. Either (a) the App and
BlockNode orchestrators must be split further so the top-level function is
≤150 LOC and complexity ≤15, **or** (b) `App.tsx` / `BlockNode.tsx` /
`BottomPanel.test.tsx` must remain in a narrower per-file waiver list with
documented rationale and a tracking issue.

Recommendation: open follow-up issues for the three residual files (or
absorb into #1422 as a phase 2) and either (i) split the orchestrators
further before stripping the block, or (ii) record a deliberate, narrower
waiver carve-out for the three files in the Wave 4 integration commit with
an inline rationale and a tracking issue, then close #1422 as
"partially retired — three files deferred to follow-up". The acceptance
criterion in #1426 ("zero waiver blocks in `frontend/eslint.config.js`")
cannot be met without one of these.

### P2 — Gate-record top-level `issue` is null on every record

**P2.1 — Manager + six sub-records leave the top-level `issue` field unset.**

Every record under `.workflow/records/` for this cascade has `"issue": null`
at the top level. Evidence is correctly persisted in two adjacent fields:

- `issues: [{number: <n>, close_in_pr: true, url: ...}]` (single primary)
- `pull_request.body_closes_issues: [<n>, ...]` (full closes list)

`issues` is the binding field for the closing-keyword CI check. Top-level
`issue=null` is permitted by the schema (it appears to be a legacy single-issue
slot), but the inconsistency makes per-record audits harder. Not blocking,
but recommend the Wave 4 integration commit set `"issue": 1426` on the
manager record.

**P2.2 — Sub-records for multi-issue PRs only list one issue in `issues`.**

- `1413-1414-lint-fn-complexity.json`: `issues=[1413]` but PR closes
  `[1413, 1414]`.
- `1416-1417-1419-tests-unused-depth.json`: `issues=[1416]` but PR title
  claims `#1416 #1417 #1419` and the CHANGELOG line scopes #1416 + partial
  #1417 + partial #1419. The PR body's `Closes #N` keywords govern; verify
  in PR view that all three are closed.

Recommend backfilling `issues` to match `body_closes_issues` so the gate
record matches reality.

### P3 — Minor

**P3.1 — Five waiver blocks are now dead-weight; Wave 4 can strip them
trivially.** Evidence per block (errors observed when block alone is removed):

| Block | Issue | Removed alone → errors |
|---|---|---|
| `MAX_LINES_PER_FN_WAIVERS` | #1413 | 0 |
| `COMPLEXITY_WAIVERS` | #1414 | 0 |
| `CONSISTENT_TYPE_IMPORT_WAIVERS` | #1416 | 0 |
| `NO_UNUSED_VARS_WAIVERS` | #1417 | 0 |
| `laneAssign.ts max-depth` | #1419 | 0 |
| `useWebSocket.test.ts ban-ts-comment` | #1419 | 0 |

Wave 4 manager can strip these six blocks in one focused commit with no
follow-up fix required.

**P3.2 — `EQEQEQ_WAIVERS` block still active (expected).** Removing it
surfaces 10 `eqeqeq` errors across the listed files. This matches the
checklist: #1415 is deferred to Wave 4 manager integration.

**P3.3 — `src/scistudio/api/static/**` is in the ignores list.** This is the
production build output for the frontend (vite-built bundle copied into the
backend during release). It is correct to ignore it from lint; flagging only
because Wave 4 should preserve this entry.

**P3.4 — `BottomPanel.test.tsx` is the only test file that violates
`max-lines`.** Test files are already exempt from `max-lines-per-function` via
the test-specific override block; the `max-lines` (500) rule still applies and
this file is 667 LOC. Either split the test file, raise `max-lines` for the
test glob, or carve it out with rationale.

## 3. Per-PR Verdicts

| PR | Scope-compliant? | Tests cover claim? | Gate record complete? | Behavior preserved? |
|---|---|---|---|---|
| #1435 (W1, #1420+#1421) | ✓ | ✓ — 3 new `BlockNode.test.tsx` cases + flipped guard | ✓ — all stages done, sentrux pass, full_audit pass | ✓ |
| #1450 (W2-A, #1422 App+BlockNode) | ✓ scope-wise | ✓ — split out 14 unit cases for `inlineConfigHelpers` | ✓ | ✓ but see P1.1 |
| #1447 (W2-B, #1422 DataPreview+BottomPanel) | ✓ | ✓ — new `codeBlockPorts.test.ts` (15) + `refEntries.test.ts` (8) | ✓ | ✓ |
| #1446 (W2-C, #1422 RunDetail/api/ConflictMarker) | ✓ | ✓ — new `api-surface.test.ts` (5) + `ConflictMarkerDecoration.test.ts` | ✓ | ✓ |
| #1457 (W3-E, #1416+#1417+#1419 partial) | ✓ | ✓ (test files only changed import shape) | ✓ | ✓ |
| #1478 (W3-D, #1413+#1414) | ✓ | ✓ — new `eventReducer.test.ts` (15) | ✓ | ✓ — all 20 ADR-045 versionVector tests pass without modification |
| Main-merge commit `8d1e3262` + #1465 merge | ✓ | ✓ — 3 new versionVector tests absorbed unmodified | ✓ — recorded as manager amendment | ✓ |

## 4. Per-Waiver-Block Dead-Weight Assessment

Methodology: for each waiver block, generate a variant of `eslint.config.js`
with that block alone removed, run `npx eslint .`, and record the
`(errors, rule_breakdown)` summary.

| Block (#issue) | Rules off | Dead-weight? | Errors when removed | Notes |
|---|---|---|---|---|
| `#1422` god-file (lines 181-189) | `max-lines`, `max-lines-per-function`, `complexity` | **ACTIVE** | 5 errors | See P1.1 — App.tsx fn 392 LOC + cc 17, BlockNode.tsx fn 198 LOC + cc 49, BottomPanel.test.tsx file 610 LOC |
| `#1413` max-lines-per-function | `max-lines-per-function` | DEAD | 0 | Wave 3-D fully refactored all 18 files; safe to strip |
| `#1414` complexity | `complexity` | DEAD | 0 | Wave 3-D fully refactored all 10 files; safe to strip |
| `#1415` eqeqeq | `eqeqeq` | **ACTIVE** | 10 errors | Deferred-as-planned to Wave 4 manager strip |
| `#1416` consistent-type-imports | `@typescript-eslint/consistent-type-imports` | DEAD | 0 | Wave 3-E retired all 12 test files; safe to strip |
| `#1417` no-unused-vars | `@typescript-eslint/no-unused-vars` | DEAD | 0 | All 7 files now clean (W2 + W3-D + W3-E coverage); safe to strip |
| `#1419` max-depth on laneAssign.ts | `max-depth` | DEAD | 0 | Wave 3-D restructured; safe to strip |
| `#1419` ban-ts-comment on useWebSocket.test.ts | `@typescript-eslint/ban-ts-comment` | DEAD | 0 | Wave 3-E added descriptions; safe to strip |

Combined-removal test (strip all 8 blocks at once): 15 errors total = 5 (god)
+ 10 (eqeqeq). Wave 4 must address both before the umbrella PR can land.

## 5. Sub-Issue Closure Verdict

| Issue | Claim | Verdict |
|---|---|---|
| #1413 max-lines-per-function | retired | ✓ FULLY retired (PR #1478) |
| #1414 complexity | retired | ✓ FULLY retired (PR #1478) |
| #1415 eqeqeq | deferred to Wave 4 | ✓ correctly deferred (per checklist §7.4.4) |
| #1416 consistent-type-imports (tests) | retired | ✓ FULLY retired (PR #1457) |
| #1417 no-unused-vars | retired | ✓ FULLY retired (split across PR #1457 + #1478) |
| #1419 max-depth + ban-ts-comment | retired | ✓ FULLY retired (PR #1478 max-depth, PR #1457 ban-ts-comment) |
| #1420 rules-of-hooks | retired | ✓ FULLY retired (PR #1435) |
| #1421 exhaustive-deps | retired | ✓ FULLY retired (PR #1435) |
| #1422 god-file (max-lines) | retired | **PARTIAL** — file-size cleared on 6 of 9 files; App.tsx / BlockNode.tsx / BottomPanel.test.tsx still violate `max-lines-per-function` and/or `complexity` and/or `max-lines`. See P1.1. |

Closing #1422 with the umbrella merge today would close it while three of
its files still fail the lint rule it was meant to retire. Recommend
splitting #1422 into "phase 1 — file size" (close) and "phase 2 — fn size
+ complexity" (defer to follow-up issue).

## 6. Gate-Record Completeness Verdict

| Record | Stages all done? | Issues recorded? | PR / commit recorded? | Sentrux | Full audit | check_results |
|---|---|---|---|---|---|---|
| 1426-manager | ✓ | ✓ (via `issues` field; top-level `issue` null — see P2.1) | ✓ #1428 | pass | pass | 8 checks |
| 1420-1421-hooks-order | ✓ | ✓ | ✓ #1435 | pass | pass | 5 |
| 1422-god-app-blocknode | ✓ | ✓ | ✓ #1450 | pass | pass | 8 |
| 1422-god-datapreview-bottompanel | ✓ | ✓ | ✓ #1447 | pass | pass | 7 |
| 1422-god-rundetail-api-conflict | ✓ | ✓ | ✓ #1446 | pass | pass | 7 |
| 1416-1417-1419-tests-unused-depth | ✓ | ⚠ only [1416] in `issues`; `body_closes_issues=[1416]` (see P2.2) | ✓ #1457 | pass | pass | 8 |
| 1413-1414-lint-fn-complexity | ✓ | ⚠ only [1413] in `issues`; `body_closes_issues=[1413, 1414]` (P2.2) | ✓ #1478 | pass | pass | 8 |

All 6 sub-records and the manager record have all six stages marked done,
sentrux=pass evidence, full_audit=pass evidence, and check_results
populated with green outcomes.

## 7. Behavior-Preservation Verdict

- **ADR-045 version-vector contract: PRESERVED.** The 3 versionVector test
  files (`useWebSocket.versionVector.test.ts` 10 cases,
  `tabSlice.versionVector.test.ts` 5 cases,
  `workflowSlice.versionVector.test.ts` 5 cases) all pass without
  modification on the umbrella tip. Verified by isolated run during this
  audit (20/20 pass in 1.36s).
- **Full vitest run: 571 passed, 13 skipped, 0 failed.** No new test
  failures introduced by the cascade.
- **Frontend build: clean (vite 17.77s, 2193 modules).**
- **Typecheck: clean (`tsc --noEmit`).**
- **Format: clean (prettier --check, all matched).**
- **Lint: 0 errors, 31 warnings** (all warnings pre-exist; mostly
  `react-refresh/only-export-components` and `react/no-array-index-key`).
- **Ruff: clean (663 files).** `ruff format --check`: clean (733 files).
- **Full audit: pass — 0 findings across 8 implemented children
  (generate_facts, frontmatter_lint, fact_drift, doc_drift, closure,
  signature_drift, architecture_drift, vulture).**

Live Chrome smoke skipped — the behavior-preservation contract is captured
by the unit test suite (especially the 20 ADR-045 versionVector cases) and
the umbrella PR #1428 Frontend job is green (running the same suite in CI).

## 8. CI Status of Umbrella PR #1428

14/14 jobs PASS (per `gh pr view 1428 --json statusCheckRollup`):
Lint & Format, CodeQL Analyze (actions / javascript-typescript / python),
Verify Workflow Compliance, Type Check, Architecture Tests, Full Audit,
Test (Python 3.11), Test (Python 3.13), Import Contracts, Frontend, Wheel
Release Smoke, CodeQL.

## 9. Tool Output Captured

- `cd frontend && npm ci` → clean install (746 packages added; tail
  truncated by the harness).
- `cd frontend && npm run lint` → "✖ 31 problems (0 errors, 31 warnings)".
- `cd frontend && npm run format:check` → "All matched files use Prettier
  code style!".
- `cd frontend && npm run typecheck` → no output, exit 0.
- `cd frontend && npm test` → "Test Files  59 passed (59) | Tests  571
  passed, 13 skipped (584) | Duration 15.23s".
- `cd frontend && npm run build` → "✓ built in 17.77s".
- `ruff check .` → "All checks passed!".
- `ruff format --check .` → "733 files already formatted".
- `PYTHONPATH=src python -m scistudio.qa.audit.full_audit ...` → status
  pass, 0 findings.
- Sentrux MCP `scan` + `check_rules` + `health`: pass, 5 cycles ≤ 5
  threshold, quality_signal=4128, 1413 files, 326650 lines.

## 10. Recommendation

**pass-with-fixes** for Wave 4 manager integration.

### Required before Wave 4 manager strip

1. **Fix P1.1.** Either (a) further split `App.tsx` / `BlockNode.tsx`
   orchestrators so the top-level function is ≤150 LOC and complexity ≤15
   and split `BottomPanel.test.tsx` so the file is ≤500 LOC; or (b) record
   a narrower per-file waiver with rationale and a tracking issue (e.g.
   keep only `App.tsx`, `BlockNode.tsx`, `BottomPanel.test.tsx` in a
   narrow new block; close #1422 with "partially retired" and a follow-up
   issue for the three files). Option (a) honours #1426's acceptance
   criterion verbatim; option (b) is a deliberate carve-out and needs
   issue.

2. **Apply #1415 eqeqeq fixes** across the 9 files in `EQEQEQ_WAIVERS`,
   then strip the block.

3. **Strip the six dead-weight waiver blocks** (#1413, #1414, #1416, #1417,
   #1419 max-depth, #1419 ban-ts-comment) in one focused commit; verify
   `npm run lint` stays at 0 errors.

### Nice-to-have

4. Backfill top-level `issue` and `issues` fields on the manager + W3-D +
   W3-E records to match `body_closes_issues` (P2.1, P2.2).

5. Consider lifting the `max-lines` 500 cap for `src/**/*.test.tsx`
   specifically, since test files commonly grow long and aren't shipped to
   production (matches the existing `max-lines-per-function: off` for
   tests).

## 11. Audit Report Provenance

- Audit branch: `audit/2026-05-22-frontend-cleanup-with-context`
- Audit worktree: `.claude/worktrees/frontend-cleanup-mgr/.claude/worktrees/w4-audit-wc`
- Audit report file: `docs/audit/2026-05-22-frontend-cleanup-1412-with-context.md`
- Source SHA at audit time: umbrella tip `4d5b0b12` (Merge PR #1478)

Auditor confirms no implementation code was modified during this audit.
