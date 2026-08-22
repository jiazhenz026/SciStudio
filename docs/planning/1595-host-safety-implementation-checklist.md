---
title: "Issue 1595 Host Safety Runtime Implementation Checklist"
status: In Progress
owners:
  - "@jiazhenz026"
related_adrs:
  - 22
language_source: en
---

# Issue 1595 Host Safety Runtime Implementation Checklist

> Manager-owned delivery record for ADR-022 Addendum 1. The owner requires one
> final public PR, so this single-agent dispatch intentionally has no umbrella
> PR. The manager owns integration, final gate evidence, and PR submission.

## 1. Change Summary

- Owner request: implement ADR-022 Addendum 1 completely and publish one PR.
- Task kind: `bugfix`
- Manager persona: `manager`
- Issue: `#1595`
- Gate record:
  `.workflow/records/1595-docs-1595-adr022-addendum1-host-safety.json`
- Manager branch: `feat/1595-host-safety-runtime`
- Manager worktree: `../SciStudio-wt-1595-adr022`
- Protected branch: `main`
- Umbrella branch/PR: N/A; owner explicitly requested one public PR.
- Final PR target: `main`
- Work prompt:
  `docs/planning/dispatch-prompts/1595/implementer.md`

## 2. Scope

- In scope:
  - runtime-global concurrency permits with default `255`;
  - live host-memory admission and machine-readable wait reasons;
  - removal of predictive CPU/GPU/resource-request scheduling plumbing;
  - scheduler, runtime, CLI, process-handle, tests, and current documentation;
  - manager review report, gate evidence, one public PR, and CI follow-through.
- Out of scope:
  - hard CPU, RAM, GPU, VRAM, affinity, quota, fairness, or preemption;
  - remote-runner resource profiles;
  - UI changes and browser e2e;
  - automatic cancellation of running work under memory pressure.
- Protected paths:
  - `src/scistudio/engine/**`; owner authorized complete implementation and the
    final PR requires `admin-approved:core-change`.
- Deferred work: N/A. Any newly discovered deferral requires a tracked issue.

## 3. Conventions

- `[ ]` not started; `[~]` in progress; `[x]` done; `[!]` blocked.
- Every completed row names a commit, file, test, report, PR, or gate event.
- The implementer edits only its assigned implementation files.
- Scope changes require a gate-record amendment before editing.

## 4. Manager Preflight

- [x] Dedicated manager branch/worktree created ->
  `feat/1595-host-safety-runtime`.
- [x] Existing issue linked -> `#1595`.
- [x] Gate ledger initialized and expanded to implementation scope ->
  `.workflow/records/1595-docs-1595-adr022-addendum1-host-safety.json`.
- [x] Current `origin/main` integrated -> `4345232e7` via merge
  `425b995bf`.
- [x] One-public-PR constraint recorded -> owner directive, 2026-08-21.
- [x] Addendum/checklist baseline committed -> `3118790a4`.
- [x] Implementer branch and worktree created from the baseline ->
  `fix/1595-host-safety-implementation`, `../SciStudio-wt-1595-impl`.
- [x] Import path checked for editable-install pollution -> bare Python cannot
  import `scistudio`; repository checks use `PYTHONPATH=src`.
- [x] Main CI baseline checked -> CI, Docs, CodeQL, and deferral scan passed for
  `ed47cafee`.
- [x] Sentrux availability checked -> CLI/MCP unavailable; final repository gate
  remains authoritative for applicable evidence.

## 5. Dispatch Matrix

| Agent | Persona | Prompt | Task | Branch | Worktree | Write set | Status |
|---|---|---|---|---|---|---|---|
| I1 | `implementer` | `docs/planning/dispatch-prompts/1595/implementer.md` | Runtime, tests, and implementation-linked docs | `fix/1595-host-safety-implementation` | `../SciStudio-wt-1595-impl` | Prompt Section 3 plus manager-approved drift paths | `[x]` -> `1706848e9` |
| I2 | `implementer` | manager follow-up directive | Deleted-path handling in diff-scoped gate commands | `impl/1595-gate-deleted-test` | `../SciStudio-wt-1595-gate-deleted-test` | Gate selector, focused tests, and branch ledger | `[x]` -> `8cf10e0a2`, `8b404c3c1` |
| I3 | `implementer` | manager PR-review directive | Workflow-cancel permit-release race | `impl/1595-review-cancel-race` | `../SciStudio-wt-1595-review-cancel-race` | Scheduler cancellation, concurrency regression, and branch ledger | `[x]` -> `a82785cbd` |

## 6. Implementation Track

### 6.1 Runtime And Contracts

- [x] Replace predictive CPU/GPU accounting with a global permit pool.
- [x] Default the runtime-global limit to `255` and validate positive values.
- [x] Preserve high/critical live-memory admission semantics.
- [x] Expose deterministic concurrency and memory wait reasons.
- [x] Remove `ResourceRequest` and process-handle resource plumbing.
- [x] Preserve READY-and-retry behavior and release permits on every terminal
  or launch-failure path.

### 6.2 Tests

- [x] Resource-manager unit tests cover defaults, validation, memory rules,
  permit idempotence, and diagnostics.
- [x] Scheduler integration tests cover 256 READY blocks, shared runtime
  permits, retry, and success/error/cancel/launch-failure release paths.
- [x] Process-handle and import-coverage tests reflect removed contracts.
- [x] API runtime tests cover default, explicit override, and invalid global
  concurrency configuration.
- [x] Relevant existing engine tests pass with a timeout -> 493 passed, 4
  platform skips.

### 6.3 Documentation

- [x] `ARCHITECTURE.md` describes the implemented host-safety boundary.
- [x] Block-authoring guidance assigns algorithmic resource behavior to blocks.
- [x] Current project-tree/resource references no longer claim dead accounting.
- [x] Addendum status/phase accurately distinguish accepted and implemented
  state.

## 7. Manager Review And Integration

- [x] Implementer output reviewed file-by-file.
- [x] Scope compliance verified before integration.
- [x] Manager review committed with the integration-fix commit to
  `docs/audit/2026-08-21-1595-host-safety-manager-review.md`.
- [x] All P1/P2 findings fixed -> conditional scheduler-listener teardown fixed.
- [x] Implementation commit integrated into manager branch -> `4859871a6`.

## 8. Verification Evidence

| Check | Status | Evidence |
|---|---|---|
| Targeted resource/scheduler/process tests | `[x]` | Manager final targeted set: 171 passed |
| Relevant engine regression tests | `[x]` | Implementer full engine: 493 passed, 4 Windows platform skips |
| Incremental-gate regression tests | `[x]` | 42 passed; deleted-only and mixed diffs covered for pytest, Ruff, format, and Mypy |
| PR-review cancellation regression | `[x]` | Test-only mutation failed on `f963bfd2a` because the waiting block launched; fixed concurrency/cancel suite: 56 passed |
| `gate_record check --mode local` | `[!]` | Tier-1 non-Python checks passed; full Python runs hit #2047 Windows Zarr races and #2103 loaded-host xdist failures; final Linux CI required |
| `gate_record check --mode pre-pr` | `[x]` | Reconciliation passed; 487 architecture tests passed with 1 skip; diff-scoped Python runner passed both phases (1,692 passed/13 skipped and 112 passed); Ruff, Mypy, full audit, imports, and deferral scan passed |
| Pre-PR finalize | `[x]` | Manager ledger reported `ledger is PR-ready` |
| PR wrapper preflight | `[x]` | Gate-aware wrapper dry-run passed |
| Public PR and post-PR finalize | `[x]` | Public PR `#2121`; post-PR reconciliation passed |
| GitHub CI | `[ ]` | pending |

## 9. Drift Log

| Date | Actor | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-08-21 | manager | Canonical multi-agent flow normally opens an umbrella PR, but the owner requires one public PR. | Use one implementer worktree and keep the manager branch as the sole final PR branch. | N/A |
| 2026-08-21 | I1 | Removing `ProcessHandle.resource_request` affects two stale constructors in `tests/engine/test_local_runner.py`, outside the initial write set. | Manager amended the gate and dispatch prompt before implementation edits. | `#1595` |
| 2026-08-21 | manager | Incremental review found the runtime option was initially placed on `LogBroadcaster` instead of `ApiRuntime`. | Correct the ownership boundary and add focused `ApiRuntime` construction tests. | `tests/api/test_runtime_host_safety.py` |
| 2026-08-21 | I1 | `engine/events.py` still routed terminal events to the removed CPU/GPU allocation release contract. | Manager added the single stale routing row to scope and recorded the core-change label requirement. | `src/scistudio/engine/events.py` |
| 2026-08-21 | I1 | The commit hook could not discover the manager ledger because gate ledgers are branch-scoped. | Manager authorized a separate implementer ledger, without hook bypass, and added it to final integration scope. | `.workflow/records/1595-impl-host-safety-runtime.json` |
| 2026-08-21 | I1 | Full-audit found legacy ADR governed contracts and expected signatures still named the removed resource-request API. | Manager amended scope, authored the minimal ADR contract patch, and authorized I1 to apply that exact patch before committing. | `docs/adr/ADR-017.md`, `ADR-019.md`, `ADR-022.md`, `ADR-027.md`, `ADR-022-addendum1.md` |
| 2026-08-22 | manager | Tier-1 full Python runs hit changing Windows Zarr rename failures in unmodified storage tests; the same `WinError 5` reproduced on current `origin/main` in the gate venv. A later tutorial/coverage worker failure matches the loaded-host signature. | Preserve failed/timeout gate events, retain passing targeted and full-engine evidence, and require green Linux CI before completion. | `#2047`, `#2103`, manager review Section 4 |
| 2026-08-22 | I2 | The newly merged diff-scoped gate passed the deleted GPU test path first to pytest, then to Ruff format/check. | Declare `governance_touch`, filter non-existent Python paths for every local file strategy, preserve repo-wide fallback for deleted-only diffs, and add 8 focused regression cases. | `7406e2207`, `618b76cec`, manager review M-02 |
| 2026-08-22 | I3 | PR #2121 review found that releasing a running permit before the later IDLE/READY cancellation sweep could retry and launch a waiting block. | Mark every not-yet-started block terminal before any running permit release; preserve CANCELLED-before-SKIPPED event order; prove the old failure with a test-only mutation. | `19e17908e`, manager review M-03 |

## 10. Final Readiness

- [x] Every changed file reviewed by the manager.
- [x] Gate record reconciles the PR diff and closes `#1595`.
- [x] Documentation and tests match implemented behavior; final full-audit passed with zero top-level findings.
- [x] One public PR targets `main` -> `#2121`.
- [x] Required labels are applied with valid owner provenance ->
  `admin-approved:architecture-doc`, `admin-approved:core-change`.
- [ ] CI and review are green.
