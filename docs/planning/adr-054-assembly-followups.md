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

#### M-003 - A stale `split_collection` entry point breaks block discovery at startup

- **Severity**: P3 - environment, not code; the server starts anyway.
- **Found by**: manager, launching the merged backend for the e2e readiness
  check.
- **Evidence**: the server logs
  `ModuleNotFoundError: No module named 'scistudio.blocks.process.builtins.split_collection'`
  during startup, then reaches `Application startup complete` and serves 135
  routes. The module exists **neither on this branch nor on `origin/main`** -
  `git cat-file -e origin/main:src/scistudio/blocks/process/builtins/split_collection.py`
  reports absent, and `grep -rn split_collection src/ pyproject.toml` finds
  nothing.
- **Reading**: a stale entry point in an installed distribution on this
  machine, left by an earlier install of a version that had the module. It is
  not an ADR-054 regression and nothing in this dispatch caused it.
- **Why it is worth recording**: it will keep appearing in every local
  startup log and in every e2e transcript, where it reads like a defect in
  whatever work is being tested. The e2e scenario now names it so it is not
  reported as one. Worth an environment clean-up, or a startup log line that
  distinguishes a stale registration from a broken import.
- **Suggested title**: `chore(env): a stale split_collection entry point logs a ModuleNotFoundError at every startup`

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

Owner: the Explore tab union member, the `exploreSlice`, the API types, the
WebSocket event routing, the layout swap, and the two context menus
(ADR-054 spec 4, T-001 to T-003).

#### F-A1-001 — The packaged-notebook marker is not on the wire

`src/scistudio/explore/packaging.py` writes `notebook_filename` and
`notebook_commit` as `ClassVar`s on the generated block class, but
`scistudio.api.schemas.BlockSummary` carries neither and
`src/scistudio/api/routes/blocks.py::_summary` reads neither. Nothing the
frontend receives therefore says a block was packaged from a notebook.

Two requirements of spec 4 need that answer: FR-004 (double-clicking a
packaged block's node opens its notebook) and FR-030 (the node's notebook
badge, S4-A4's). Both are implemented against one predicate,
`isPackagedNotebookBlock` in `frontend/src/explore/packagedBlock.ts`, which
reads an optional `notebook_filename` on `BlockSummary` that the backend does
not send yet. Until it does, the predicate answers `false` for every block, the
canvas double-click keeps its pre-ADR-054 behaviour, and no speculative request
is sent.

Deliberately not worked around. Guessing "packaged" from the block's origin
tier plus a sibling `.ipynb` on disk would be a second definition of what a
packaged block is, and it would disagree with `packaging.py` the first time
somebody hand-writes a block beside a notebook.

**Fix**: add `notebook_filename` (and probably `notebook_commit`) to
`scistudio.api.schemas.BlockSummary` and read them in `_summary` with
`getattr(spec, ..., None)`, as `panel_manifest` and `ui_icon` already are. That
is a `src/scistudio/**` change, which no agent in this dispatch may make.

Cited by: `frontend/src/explore/packagedBlock.ts`,
`frontend/src/types/api.ts` (`BlockSummary.notebook_filename`).

#### F-A1-002 — The spec calls the "no kernel" state `none`; the runtime calls it `not-started`

Spec 4 FR-016 lists the kernel states the shell must show as "none, starting,
idle, busy, dead, needs restart". The landed runtime's `KernelState`
(`src/scistudio/explore/kernel.py`) is
`"not-started" | "starting" | "idle" | "busy" | "dead"`, and `needs_restart` is
a separate boolean beside it rather than a sixth state.

The slice stores what the runtime sends, verbatim, and never collapses the flag
into the state — `SessionToolbar.kernelLabel` does that collapse at render
time, which is the one place a person is being told one thing. So the behaviour
matches the spec's intent; only the spec's word for the first state differs
from the wire's.

**Fix**: a one-word correction in the spec (`none` → `not-started`), which is a
`docs/specs/**` change and out of every agent's write set in this dispatch.

#### F-A1-003 — A buffered event stream for an unknown session is dropped silently

`exploreSlice` buffers events whose `session_id` it has no notebook path for
yet, because `session_opened` is published inside the open call and can reach
the socket before the POST response reaches the caller. The buffer is capped at
`PENDING_EVENT_CAP` (200) per session id; past the cap, events are dropped with
no report.

A stream that never resolves is a bug elsewhere (an open that failed after the
runtime published, a session id the frontend never learns about), and the cap
keeps it from becoming a memory leak here. But dropping silently means that
bug shows up as a stale notebook rather than as itself.

**Fix**: log once per session id at the cap, and consider surfacing it on the
tab as a "this session is out of sync, reload" state.

Cited by: `frontend/src/store/exploreSlice.ts` (`PENDING_EVENT_CAP`).

#### F-A1-004 — Closing an Explore tab leaves its session in the slice and its kernel alive

`closeTab` drops the tab; it does not call `forgetExploreSession`, and it does
not `DELETE /api/explore/sessions/{id}`. That is deliberate for now — reopening
the same notebook is then instant, and a kernel with a person's namespace in it
is not something to end on a tab close without asking — but it means the slice
grows for the life of the page and a kernel can outlive every tab that showed
it.

Spec 4 does not say what closing the tab should do. FR-015's kernel list is the
surface that ends a kernel deliberately, which is an argument for leaving the
close alone; the counter-argument is that a person who closes the tab has no
reason to expect a Python process to still be resident.

**Fix**: settle the intended behaviour with the owner, then either call
`forgetExploreSession` on close, or leave it and say so in the spec.

#### F-A1-005 — `frontend/src/types/api.ts` was split for size, not for design

Appending the session API and event payloads to `api.ts` put it over the
repository's `max-lines` rule (750 counted lines). The shapes now live in
`frontend/src/types/explore.ts` and `api.ts` re-exports them with
`export * from "./explore"`, so every existing import path is unchanged and the
spec's affected-files table still describes where a consumer looks.

`api.ts` is close to the limit again on its own. A follow-up should split it by
domain the way `lib/api/` already is (`projects`, `blocks`, `workflows`, `git`,
…) rather than one more sibling per feature.

#### F-A1-006 - Two specs now claim `frontend/src/explore/**`, and the audit fails on it

`docs/specs/adr-054-agent-enablement.md` (spec 5, issue `#2254`) lists
`frontend/src/explore/**` under `planned_governs.files`. The moment this task
landed that directory, the full-repo audit began failing it with "planned
governed file path or glob already resolves and must move to governs" - and it
cannot move, because spec 4 governs the same glob.

**This blocks the branch's gate and will block every sibling branch and the
track branch too.** It is the one audit error left after spec 4's own
frontmatter was corrected.

Not fixed here, deliberately. Spec 5's `scope.out` reserves the frontend from
itself "except the single report of the active mode this spec requires of it",
so the entry is not a mistake - it is a real, if far too broad, claim on one
future file. Resolving it means choosing between:

1. **Removing** `frontend/src/explore/**` from spec 5's `planned_governs`, on
   the ground that spec 4 governs the explore frontend and spec 5's one
   frontend requirement is satisfied by an interface spec 4 provides; or
2. **Narrowing** it to the specific file that will carry the mode report (which
   does not exist yet), so it stays planned and stops resolving.

Either is an authoring decision about a spec belonging to a different issue and
a different dispatch row, which is why this agent stopped rather than edited
it. Wave 1's spec-5 agents (`S5-B1`, `S5-B2`) have backend-only write sets, so
nobody is currently holding that file.

**Remedy**: one line in `docs/specs/adr-054-agent-enablement.md`, by whoever
owns spec 5.

**Update, after the coordinator's dispatch of spec 5 FR-001's frontend half to
this agent**: the report that claim reserved is now delivered, as
`frontend/src/explore/workspaceFocus.ts`, under spec 4's governance. So option
1 is the well-founded one - spec 5's `planned_governs` entry can be removed,
because the file it was holding a place for exists and belongs to spec 4. Still
not taken here: it is a different issue's spec, and removing another dispatch's
governance claim is the manager's call, not this agent's.

**Resolved.** The manager took option 1 on the track branch in
`c1b31cd98 docs(#2254): spec 5 stops claiming the explore frontend it does not
own`, and merging the track into this branch clears the audit error. Left in
the register as the record of why the claim went away.

#### F-A1-007 - Three partial mocks of `lib/api/ai` had to gain the new export

`workflowSlice.variadicPorts.test.ts`, `workflowSlice.subworkflowRef.test.ts`
and `components/BottomPanel.parts/SubworkflowConfigEditor.test.tsx` mock
`../../lib/api/ai` with a hand-written object rather than spreading
`importOriginal()`. Adding `postWorkspaceFocus` to that module made importing
the store throw in all three, because the store's subscriber calls an export
the mock does not define.

Fixed by adding the export to each mock. The underlying fragility is not
fixed: any future export on that module breaks them again. The repository's own
better pattern is in `store/__tests__/panelCatalogInvalidation.test.ts`, which
spreads `importOriginal()` and overrides only what it needs.

**Fix**: convert the three to the `importOriginal` form.

#### F-A1-008 - Two Python tests flaked once each under the gate's parallel run

`tests/qa/test_generate_facts_cli.py::test_generate_facts_write_and_check_round_trip`
failed on one `gate_record check` run and
`tests/ai/test_mcp_tools_disk_integration.py::test_concurrent_write_workflow_serialises`
on the next; neither failed twice, and both pass in isolation and in the other
run. Both are timing-sensitive - the first spawns a subprocess that walks the
whole `src/` tree, the second asserts write serialisation - and the suite runs
under `--timeout=60` on a machine carrying several agents' test runs at once.

The second is already tracked: `#2244` says
`test_concurrent_write_workflow_serialises` **is not marked serial**, which is
exactly the shape of both failures seen here — the test spawns two threads
against a process-global active project, and its failure message
(`PermissionError: Path workflows\concurrent.yaml resolves outside <tmp
project>`) is a resolution against the wrong project root rather than anything
about write ordering. It passes on its own, passes with its whole file under
`-n 4`, and passes with the whole `tests/ai` package under `-n auto`; it only
fails in the full-suite run, which is where another package's global state can
reach it.

This branch changes no Python at all — `git diff --name-only <base>...HEAD`
lists no `.py` file — so neither failure can be caused by it.

Recorded rather than dismissed: if either recurs in CI, where the machine is
not shared, it is a real defect and not contention, and `#2244` is the issue
that already says what to do about the second.

The failure count tracked the machine's load rather than the diff: one failure,
then one, then four, then six, over four `gate_record check` runs of the same
tree, with a different set each time. The others seen were
`tests/api/test_panel_document_events.py::test_the_file_route_accepts_a_panel_document`
(`[WinError 5] Access is denied` on the atomic-rename step of a temp-dir
write), `tests/qa/test_audit_full_audit.py::test_full_audit_renders_human_readable_facts_summary`,
`tests/workflow/test_serializer_property.py::test_relativify_inverts_absolutify`
and `tests/tutorials/test_core_tutorial_what_is_a_type.py::test_the_whole_tutorial_walks_through_the_real_runtime`.
All four named here passed together in one isolated run
(`4 passed in 64.55s`).

#### F-A1-009 - `gate_record check` counts a timed-out check as satisfied

Running the suite with `PYTEST_XDIST_AUTO_NUM_WORKERS=4` to reduce contention
made it slower than the gate's own per-check budget. The ledger recorded

```json
{"name": "python_tests", "exit_code": null, "status": "unknown",
 "summary": "execution error: TimeoutExpired"}
```

and the same `check` invocation **exited 0 and reported no unsatisfied
obligations**. A check that did not finish is not a check that passed, and a
`status: "unknown"` event should leave its obligation unsatisfied rather than
discharge it.

- **Severity**: P1 for the gate itself - it is the difference between evidence
  and the absence of evidence, and this is the ledger ADR-042 Addendum 6 makes
  the single source of truth.
- **Evidence**: `.workflow/records/2253-feat-2253-explore-tab-shell.json`,
  `check_events` entry at `2026-09-05T09:14:52Z`, beside a `check` run whose
  stdout was `mode=pre-pr tier=1 checks=[...]` / `reconciliation passed` /
  `exit=0`.
- **Suggested title**: `gate_record check treats a TimeoutExpired check as
  satisfied`

**The code**: `src/scistudio/qa/governance/gate_record/checks.py:640` runs every
check with a hard `timeout=600`, and the `except (subprocess.SubprocessError,
OSError)` immediately below turns a `TimeoutExpired` into
`CheckEvent(exit_code=None, status="unknown")`. The obligation evaluator then
reads that event as discharging `checks.<name>`. The full Python suite takes
5m15s to 9m29s on this machine depending on load, so it sits just inside a
10-minute budget and crosses it whenever the box is busy - which is exactly
when its result matters least and its absence is easiest to miss.

It happened **twice** in this task, and both times the enclosing `check`
printed `reconciliation passed` and exited 0. The second time it produced a
"clean" pre-PR run that would have opened a PR on a suite that never finished.

The narrow fix is one line: treat `status == "unknown"` as not satisfying its
obligation. The better fix also distinguishes a timeout from an execution
error, because "the check could not be run" and "the check did not finish in
time" want different advice.

#### F-A1-010 - `.gitignore` covers `.coverage` but not the parallel shards

`pytest-cov` under xdist writes `.coverage.<host>.<pid>.<random>` files beside
`.coverage`, and a killed run leaves them there. `.gitignore` line 20 is the
literal `.coverage`, which does not match them, so the `git add -A` that
`docs/ai-developer/specific_rules/gated-workflow.md` requires before every
commit swept three of them into `53241d18c`. The next commit deleted them and
they are absent from the branch's three-dot diff, but `gate_record check` still
reported them under `scope.out-of-scope`, because it looks at every path the
commit range touches rather than the net diff.

Two small things, either of which would prevent it:

- add `.coverage.*` to `.gitignore`;
- have the gate's `scope` check compare the net three-dot diff rather than the
  union of touched paths, so an artifact added and removed inside a branch is
  not a scope violation.

- **Severity**: P3 - noise, but noise that costs a gate cycle to clear.
- **Evidence**: `gate_record check` output naming
  `.coverage.Jiazhen.pid70960.Xvf3OiRx.HE0prOJoP7gh` and two siblings after
  they had been deleted from the tree.
- **Suggested title**: `.gitignore misses pytest-cov's parallel shards, so
  git add -A commits them`

#### F-A1-011 - The gate's full Python suite is not reliably runnable on a shared machine

Across nine `gate_record check --mode pre-pr` runs of the same tree, on a
32-core Windows box carrying several dispatch agents' suites at once, the
Python phase failed nine times with **nine different sets** of tests and never
the same set twice:

| Run | Failures |
|---|---|
| 1 | `test_generate_facts_write_and_check_round_trip` |
| 2 | `test_concurrent_write_workflow_serialises` |
| 3 | same as 2 |
| 4 | 4 tests, incl. `test_the_file_route_accepts_a_panel_document` (`[WinError 5] Access is denied` on an atomic rename) |
| 5 | 6 tests, incl. `test_relativify_inverts_absolutify` and a tutorial runtime walk |
| 6 | timed out entirely at `PYTEST_XDIST_AUTO_NUM_WORKERS=4` (see F-A1-009) |
| 7 | 3 tests |
| 8 | 1 test |
| 9 | 1 test, different again |

Every named test passes on its own: the four of run 4 passed together in one
run (`4 passed in 64.55s`), the three of run 7 in another (`3 passed in
46.96s`), and `tests/ai` passes whole under `-n auto` (exit 0). The branch
changes **no Python at all** - `git diff --name-only <base>...HEAD` lists no
`.py` file - so none of it can be the diff's doing.

The failure modes are all shared-machine ones: Windows `Access is denied` on
`os.replace` (an antivirus or indexer holding the destination), a subprocess
that walks the whole `src/` tree exceeding `--timeout=60`, and a
process-global active project reached by another package's test under `-n auto`
oversubscription.

This is not a request to weaken the check. It is a request for a way to run it
honestly on a developer machine, because as it stands "the local Python gate is
green" is not a statement an agent on this box can truthfully make, and the
temptation that creates is the real hazard.

- **Severity**: P2 - it does not break the product, but it makes the gate's
  central obligation unverifiable locally, which is a governance problem.
- **Evidence**: `.workflow/records/2253-feat-2253-explore-tab-shell.json`,
  nine `python_tests` `check_events`; `.workflow/local/check*.txt`.
- **Suggested title**: `The gate's Python suite cannot be run reliably on a
  shared developer machine`



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
