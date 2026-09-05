---
title: "ADR-054 Assembly Follow-Up Register"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Assembly Follow-Up Register

This file exists because the owner forbade opening new GitHub issues during
the ADR-054 assembly:

> 除了实现代码对应的issue外，任何follow-up issue均不开，放到一个文件里等我醒了看。
>
> (Open no follow-up issue beyond the ones the implementation code needs; put
> them in one file for me to read when I wake up.)

Every deferral, edge case, cleanup, missing test, design question and drift
found during the assembly lands here instead of in the tracker. Each entry is
written so the owner can turn it into an issue in one step, or decide it is
not worth one.

The two issues that **were** opened, because they are the implementation
issues the directive permits:

- `#2253` — ADR-054 spec 4, the Explore tab and the notebook frontend.
- `#2254` — ADR-054 spec 5, the workspace focus, the panel skill, the session
  tools.

## How To Read An Entry

| Field | Meaning |
|---|---|
| **Severity** | `P1` blocks the feature; `P2` is a real defect that does not block; `P3` is cleanup or polish |
| **Found by** | The agent label, so its report and branch can be found |
| **Evidence** | A file and line, a test, or a command output — never a claim alone |
| **Suggested title** | Ready to paste into `gh issue create --title` |

## Register

### Manager

#### M-001 — PR #2255 needs the `admin-approved:core-change` label, applied by the owner

- **Severity**: P1 — CI's `Verify Workflow Compliance` job fails without it.
- **Found by**: manager, from PR #2238's CI run 33808346838.
- **Evidence**: `guard.core_change_guard` reports
  `protected core/runtime change requires admin-approved:core-change applied
  by an authorized maintainer or administrator approval`, affecting
  `src/scistudio/blocks/base/interactive.py`,
  `src/scistudio/blocks/process/builtins/data_router.py`,
  `pair_editor.py`, `src/scistudio/blocks/registry/__init__.py` and
  `_capability.py`.
- **Why it is here and not done**: the manager attempted
  `gh pr edit 2255 --add-label admin-approved:core-change` and the action was
  refused by this session's permission classifier. The owner's blanket
  pre-approval does not override that refusal, and the label's whole purpose
  is a human attestation whose actor provenance CI verifies — so it is the
  owner's to apply, deliberately.
- **What the label attests**: every affected file is named in the approved
  specs' own `governs.files`. ADR-054 spec 1 §3 changes the panel manifest on
  the block base and the registry's capability resolution; spec 3 §4.5 adds
  `on_new_input` to the same base and the packaged block's ask pause to the
  scheduler's dispatch. The change is what the approved specs ask for.
- **Action**: `gh pr edit 2255 --add-label "admin-approved:core-change"`, or
  the same from the PR page.
- **Suggested title**: N/A — this is an owner action, not an issue.

#### M-002 - `eslint-config.test.ts` flakes under machine load on a 5s timeout

- **Severity**: P3 - pre-existing, unrelated to ADR-054, and green in isolation.
- **Found by**: manager, taking the frontend baseline on the merged assembly
  branch before spec 4 lands.
- **Evidence**: `frontend/src/__tests__/eslint-config.test.ts:12`,
  `loads the project flat config without parser errors`, failed with
  `Test timed out in 5000ms` after running 12334ms during a full
  `npm run test` on a machine with several agents active. Re-run alone,
  `npx vitest run src/__tests__/eslint-config.test.ts` gives 8 passed.
  Full-suite baseline otherwise: **2315 passed, 1 failed, 198 files**; with
  the re-run the suite is 2316/2316.
- **Why it matters**: the test performs a real ESLint flat-config resolution,
  which is I/O-bound and easily exceeds 5s on a loaded runner. It will flake
  in CI on a busy day and will look like a frontend regression in whichever
  PR happens to be running.
- **Suggested title**: `flaky(frontend): eslint-config.test.ts resolves a real flat config on a 5s timeout`

### S4-A1

_No entries yet._

### S4-A2

_No entries yet._

### S4-A3

_No entries yet._

### S4-A4

_No entries yet._

### S5-B1

_No entries yet._

### S5-B2

_No entries yet._

### S5-B3

_No entries yet._

### S5-B4

_No entries yet._

### S4-D1 / S5-D1 (adversarial testing)

_No entries yet._

### S4-E1 / S5-E1 / INT-E1 (audits)

_No entries yet._

### fix-kernel

#### FK-001 — `test_kernel_session.py` carries a second `_process_gone` that still counts a zombie as alive

- **Severity**: P3 — latent, not currently failing.
- **Found by**: fix-kernel, while fixing #2240's death detection.
- **Evidence**: `tests/explore/test_kernel_session.py:98` checks only
  `psutil.pid_exists` and `Process.is_running()`. psutil reports both as true
  for an unreaped zombie, so this copy has exactly the defect the manager
  fixed in `tests/explore/test_explore_session.py:113`. It passes today only
  because every one of its callers reaps first — either
  `psutil.Process(pid).wait(...)` in the test, or `KernelHandle.stop()`'s
  `_wait_for_exit` — so nothing currently reaches it with a live zombie.
- **Why it is here and not done**: changing it is not needed to fix #2240 and
  the bug-fix rule forbids widening a fix past its cluster. The moment a new
  test in that file kills a kernel without reaping it, it will hang for its
  full 10 s timeout and then report a dead kernel as alive.
- **Suggested title**: `Unify the three _process_gone test helpers on the
  zombie-aware reading`

#### FK-002 — three copies of `_process_gone` now exist across the explore tests

- **Severity**: P3 — duplication, not a defect.
- **Found by**: fix-kernel.
- **Evidence**: `tests/explore/test_explore_session.py:113`,
  `tests/explore/test_kernel_session.py:98`, and the branch-switch assertions
  in `tests/api/test_explore_branch_switch.py` all need the same "is this pid
  really gone" reading, and they have drifted apart (only one of them counts
  a zombie). A shared helper — plausibly next to `KernelHandle` itself, since
  the product now needs the same reading — would keep them honest.
- **Suggested title**: `Share one zombie-aware process-liveness helper between
  the explore kernel tests`

#### FK-003 — the death-detection test is a race the suite only loses under load

- **Severity**: P2 — the fix holds, but the end-to-end test does not prove it
  reliably.
- **Found by**: fix-kernel, reproducing #2240 in WSL.
- **Evidence**: `test_a_kernel_killed_from_outside_is_reported_dead_and_offers_a_restart`
  passes in isolation and passes when only `tests/explore` runs; it fails only
  in the full `-m serial` phase, where the process holds eight live threads and
  the killed kernel's thread group takes long enough to drain that
  `/proc` says `Z` while `waitpid` still says "not yet". A test that only
  fails on a loaded machine is a test that will go quiet again. The
  platform-independent guarantee now lives in the stub-driven tests added to
  `tests/explore/test_kernel_session.py`; the end-to-end test is kept because
  it is the only one that proves the wiring, not because it is dependable.
- **Suggested title**: `Make the explore kernel-death end-to-end test
  deterministic rather than load-dependent`

## Already-Tracked Follow-Ups Inherited From Specs 1 To 3

These already have issues. They are listed so the owner sees the whole
ADR-054 debt in one place, not so they are opened again.

| Issue | Subject | Source |
|---|---|---|
| `#2212` | Let a plot panel declare the producing capability | ADR-054 §10.2, explicitly out of scope |
| `#2233` | A producing panel's emission has no time bound and runs on the scheduler's event loop | spec 1 dispatch |
| `#2236` | Revise the human-facing panel vocabulary and documentation (ADR-054 spec 6) | ADR-054 §10.1 |
| `#2237` | Nothing checks the API wire between `schemas.py` and `types/api.ts` | spec 1 dispatch — the mechanism behind three fixed wire breaks |
| `#2242` | The ADR and the explore-frontend spec name `ExploreTab.test.tsx` at two different paths | spec 4 input defect |
| `#2243` | Spec 2 FR-015's unresolved-read exception rests on a false premise | needs an owner decision |
| `#2244` | `test_concurrent_write_workflow_serialises` is not marked serial | spec 2 dispatch |
| `#2245` | `gate_record` cannot correct a runtime recorded wrong at init | spec 3 dispatch |
| `#2249` | A concurrent `gate_record check` silently overwrites an amend | spec 3 dispatch |
| `#2250` | Spec 3 FR-050's panel channel needs an event type FR-057 does not list | needs an owner decision |

`#2242`, `#2243` and `#2250` are **input defects in the approved specs** and
may change what spec 4 and spec 5 should build. The manager's reading of each
is recorded in the assembly checklist's drift log as the agents hit them.
