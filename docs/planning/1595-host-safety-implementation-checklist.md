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
- [x] Current `origin/main` integrated -> `ed47cafee`.
- [x] One-public-PR constraint recorded -> owner directive, 2026-08-21.
- [ ] Addendum/checklist baseline committed.
- [ ] Implementer branch and worktree created from the baseline.
- [x] Import path checked for editable-install pollution -> bare Python cannot
  import `scistudio`; repository checks use `PYTHONPATH=src`.
- [x] Main CI baseline checked -> CI, Docs, CodeQL, and deferral scan passed for
  `ed47cafee`.
- [x] Sentrux availability checked -> CLI/MCP unavailable; final repository gate
  remains authoritative for applicable evidence.

## 5. Dispatch Matrix

| Agent | Persona | Prompt | Task | Branch | Worktree | Write set | Status |
|---|---|---|---|---|---|---|---|
| I1 | `implementer` | `docs/planning/dispatch-prompts/1595/implementer.md` | Runtime, tests, and implementation-linked docs | `fix/1595-host-safety-implementation` | `../SciStudio-wt-1595-impl` | Prompt Section 3 | `[ ]` |

## 6. Implementation Track

### 6.1 Runtime And Contracts

- [ ] Replace predictive CPU/GPU accounting with a global permit pool.
- [ ] Default the runtime-global limit to `255` and validate positive values.
- [ ] Preserve high/critical live-memory admission semantics.
- [ ] Expose deterministic concurrency and memory wait reasons.
- [ ] Remove `ResourceRequest` and process-handle resource plumbing.
- [ ] Preserve READY-and-retry behavior and release permits on every terminal
  or launch-failure path.

### 6.2 Tests

- [ ] Resource-manager unit tests cover defaults, validation, memory rules,
  permit idempotence, and diagnostics.
- [ ] Scheduler integration tests cover 256 READY blocks, shared runtime
  permits, retry, and success/error/cancel/launch-failure release paths.
- [ ] Process-handle and import-coverage tests reflect removed contracts.
- [ ] Relevant existing engine tests pass with a timeout.

### 6.3 Documentation

- [ ] `ARCHITECTURE.md` describes the implemented host-safety boundary.
- [ ] Block-authoring guidance assigns algorithmic resource behavior to blocks.
- [ ] Current project-tree/resource references no longer claim dead accounting.
- [ ] Addendum status/phase accurately distinguish accepted and implemented
  state.

## 7. Manager Review And Integration

- [ ] Implementer output reviewed file-by-file.
- [ ] Scope compliance verified before integration.
- [ ] Manager review committed to
  `docs/audit/2026-08-21-1595-host-safety-manager-review.md`.
- [ ] All P1/P2 findings fixed or tracked with owner-approved rationale.
- [ ] Implementation commit integrated into manager branch.

## 8. Verification Evidence

| Check | Status | Evidence |
|---|---|---|
| Targeted resource/scheduler/process tests | `[ ]` | pending |
| Relevant engine regression tests | `[ ]` | pending |
| `gate_record check --mode local` | `[ ]` | pending |
| `gate_record check --mode pre-pr` | `[ ]` | pending |
| Pre-PR finalize | `[ ]` | pending |
| PR wrapper preflight | `[ ]` | pending |
| Public PR and post-PR finalize | `[ ]` | pending |
| GitHub CI | `[ ]` | pending |

## 9. Drift Log

| Date | Actor | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-08-21 | manager | Canonical multi-agent flow normally opens an umbrella PR, but the owner requires one public PR. | Use one implementer worktree and keep the manager branch as the sole final PR branch. | N/A |

## 10. Final Readiness

- [ ] Every changed file reviewed by the manager.
- [ ] Gate record reconciles exact final diff and closes `#1595`.
- [ ] Documentation and tests match implemented behavior.
- [ ] One public PR targets `main`.
- [ ] Required labels are applied with valid owner provenance.
- [ ] CI and review are green.
