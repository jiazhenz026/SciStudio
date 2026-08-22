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
fixes described below, every changed source/test/document path, and the diff
from `origin/main` at `4345232e7`.

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

### M-02: diff-scoped checks selected a deleted test path

**Severity:** pre-PR blocker before fix; resolved in this branch.

The current-main incremental gate initially passed the intentionally deleted
`tests/engine/test_resource_manager_gpu_autodetect.py` to pytest and then to
Ruff format/check. Both failures were deterministic command-construction bugs,
not host-safety product failures. The integrated fix filters non-existent
Python paths from pytest, Ruff, format, and Mypy targets. A deleted-only diff
widens to the repository command instead of producing an empty narrow pass;
mixed diffs retain only provably existing targets.

### M-03: workflow cancellation could retry a waiting block

**Severity:** P1 before fix; resolved in this branch.

The resource release listener schedules a READY scan immediately when a
running block releases its permit. Workflow cancellation previously released
that permit before its later IDLE/READY sweep, then awaited the
`BLOCK_CANCELLED` event. An asynchronous subscriber could yield long enough for
the scan to launch an independent waiting block that was absent from the
earlier running-block snapshot.

The fix synchronously marks every IDLE/READY block SKIPPED, records its reason,
and clears its wait state before releasing any running permit. External event
ordering remains CANCELLED before SKIPPED. A test-only mutation against
`f963bfd2a` reproduced the old launch; the same deterministic test passes with
the fix.

### Other PR review comments

- The compatibility fallback's opaque `object()` permit cannot reach
  `ResourceManager.release`: production managers always provide
  `try_acquire()`, while fallback stubs without it also omit `release`; the
  release helper checks callability before use. The reported `AttributeError`
  has no runtime path.
- `EventBus.emit()` isolates ordinary subscriber exceptions. The dispatch
  `BaseException` branch handles external cancellation and releases its permit;
  converting cancellation into ERROR would misclassify the lifecycle.
- Sampling host memory under the manager lock is intentional: the addendum
  requires the memory decision and permit claim to form one admission critical
  section.
- Suggested finalization deduplication is a non-behavioral refactor outside the
  accepted contract change; no correctness drift was identified. The comment
  grammar noted by review was corrected.

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
| Incremental-gate deleted-path regressions | 42 passed |
| PR-review cancellation regression | Test-only mutation failed on old head as expected; fixed cancel/concurrency set: 56 passed |
| Ruff format/check | Passed for implementer paths and manager lifecycle fix |
| Mypy | 16 changed source files, no issues on implementer branch |
| Full audit | Passed with zero top-level findings on both implementer and final manager diffs |
| Tier-1 local gate | All non-Python checks passed; full Python suite was blocked by unrelated Windows Zarr rename flakes described below |
| Tier-1 pre-PR gate | Reconciliation passed; 487 architecture tests passed with 1 skip; diff-scoped Python runner passed both phases (1,692 passed/13 skipped and 112 passed); Ruff, Mypy, full audit, imports, and deferral scan passed |
| GitHub CI and review | All 16 checks passed on `ab2a1bcce`; both Python versions passed, semantic ratchet passed in 25m20s, and all six automated review threads were resolved |
| Browser e2e | N/A: no UI or browser-visible contract changed |
| Sentrux | N/A: no CLI or MCP integration was available in this session |

An earlier manager targeted run's single failure was caused by placing the
pre-existing rerun assertions under the new test function. It was a test-edit
error, not a product failure; the assertions were restored to their original
test and both affected tests passed on rerun.

Before the current-main incremental gate was integrated, the tier-1 gate's full
Python runs consistently completed more than 6,800 tests
but encountered changing failures in unmodified paths. The first run reported
one timing-sensitive AI watcher failure and one Zarr `WinError 5`; later runs
reported different Zarr tests failing at the same `Path.rename` call in
`core/storage/zarr_backend.py`. Using the gate's isolated venv against current
`origin/main` reproduced the same Zarr permission failure in 2 of 10 repeated
baseline runs. A one-worker diagnostic exceeded the gate timeout; although the
recovery reconciliation returned zero, its check event is `unknown`, so this
audit does not count that command as a pass. GitHub's Linux Python job remains
the authoritative complete-suite verdict. The Zarr race is already tracked by
issue #2047. The changing tutorial/coverage worker failure on a loaded Windows
host is tracked by #2103; that issue records the same tutorial test and states
that Ubuntu CI is unaffected. The final local gate uses the accepted
diff-scoped mode and passed; GitHub CI still owns the authoritative full-suite
verdict.

## 5. Recommendation

**Pass.** Pre-PR reconciliation, post-PR finalization, all GitHub CI checks,
and review resolution passed on the reviewed code candidate. The implemented
boundary matches the accepted addendum: SciStudio limits automatic fan-out and
new work under host-memory pressure without promising CPU or GPU allocation.
