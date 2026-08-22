---
title: "Issue 1595 Host Safety Runtime Manager Review"
status: Final
owners:
  - "@jiazhenz026"
related_adrs:
  - 22
language_source: en
---

# Issue 1595 Host Safety Runtime Manager Review

## 1. Change Summary

The reviewed change implements ADR-022 Addendum 1 and closes issue #1595 by
removing predictive local CPU/GPU accounting. One `ResourceManager` owned by an
`ApiRuntime` now grants opaque runtime-global concurrency permits, defaulting
to 255, while retaining live high/critical host-memory admission. Blocks retain
control of devices, batching, threads, processes, and library-level resource
behavior.

The review covered implementation commit `4859871a6`, the manager integration
fix described below, every changed source/test/document path, and the diff from
`origin/main` at `ed47cafee`.

## 2. Findings

No P1 or P2 finding remains open.

### M-01: scheduler release listeners were not always disposed

**Severity:** P2 before fix; resolved in this branch.

`ApiRuntime.start_workflow` disposed a completed scheduler only through the
lineage finalization callback. When lineage was disabled or recorder creation
failed, EventBus subscriptions already remained live; the new shared
`ResourceManager` release listener would also remain subscribed and receive
future workflow wakeups.

The manager integration fix registers scheduler teardown independently of
lineage construction. An API regression test runs a workflow with
`lineage_store = None` and verifies that its release listener is removed after
completion.

## 3. Contract Review

- Admission is synchronous and atomic before `RUNNING`, event emission, or any
  other await point.
- Permit identity is opaque and does not use block ids, so identical node ids
  in simultaneous workflows cannot release each other's capacity.
- The default limit rejects the 256th READY execution; explicit limits of one
  and greater than 255 are supported.
- A permit release notifies all schedulers sharing the runtime manager. Listener
  failures are isolated, and closed-loop races are guarded.
- Success, runner error/abnormal exit, block/workflow cancellation,
  pre-dispatch failure, task-launch failure, and final cleanup converge on an
  idempotent scheduler-owned release helper.
- High and critical host-memory decisions return distinct machine-readable
  reasons. Waiting nodes remain READY and clear stale reasons after admission
  or terminal propagation.
- `ResourceRequest`, predictive CPU/GPU counters, GPU auto-detection, and
  `ProcessHandle.resource_request` are absent from active runtime contracts.
- `ApiRuntime`, its environment override, and the headless CLI provide positive
  integer configuration without an automatic hardware-derived limit.

## 4. Verification Evidence

| Check | Result |
|---|---|
| Focused resource, scheduler, and API host-safety tests | 46 passed on implementer branch |
| ProcessHandle, LocalRunner, and import-coverage tests | 106 passed on implementer branch |
| Full engine suite | 493 passed, 4 Windows platform skips on implementer branch |
| CLI suite | 23 passed on implementer branch |
| Manager final targeted API/engine regression set | 171 passed |
| Ruff format/check | Passed for implementer paths and manager lifecycle fix |
| Mypy | 16 changed source files, no issues on implementer branch |
| Full audit | Passed with zero top-level findings on both implementer and final manager diffs |
| Browser e2e | N/A: no UI or browser-visible contract changed |
| Sentrux | N/A: no CLI or MCP integration was available in this session |

An earlier manager targeted run's single failure was caused by placing the
pre-existing rerun assertions under the new test function. It was a test-edit
error, not a product failure; the assertions were restored to their original
test and both affected tests passed on rerun.

## 5. Recommendation

**Pass**, subject to the final manager gate reconciliation and GitHub CI. The
implemented boundary matches the accepted addendum: SciStudio limits automatic
fan-out and new work under host-memory pressure without promising CPU or GPU
allocation.
