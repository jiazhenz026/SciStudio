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

#### M-005 - READ THIS ONE FIRST: the gate counts a timed-out test run as a passing one

- **Severity**: P1, and it is about the evidence rather than the feature.
- **Found by**: S5-B4, blocked by it; corroborated by S5-B1, the kernel fix
  agent, and the manager, each of whom hit a piece of it separately.
- **The chain**, which is worse than any of its three links alone:
  1. Two tests in `tests/qa/**` walk the whole repository and are not
     `serial`-marked, so they crash their xdist worker (`[gwN] node down`).
     That is the class `pyproject.toml` already documents as serial-only
     (#1867, #1896). Registered by S5-B4 as **F-B4-10**.
  2. A parallel-phase failure makes the runner **skip the serial phase**. So
     `test_a_branch_switch_kills_the_real_kernel_process`, genuinely red on
     the spec 5 track, was never reported at all. Registered as **F-B4-9**.
     A red test that cannot be seen is worse than a red test.
  3. When the run instead exceeds the gate CLI's own 600-second
     `subprocess.run(timeout=...)` budget, **the gate records `python_tests` as
     satisfied**. Registered as **F-B4-8** (and independently as **F-A1-009**).
     **FIXED** on `fix/2253-gate-timeout-not-satisfied` — see the `fix-gate`
     section below. Do not open an issue for it.
- **Why the manager is elevating it here.** Step 3 means a `gate_record`
  reconciliation can pass on a test run that never finished. Every branch in
  this dispatch went through that path, so it bears on how much the gate
  evidence in this PR is worth — not because anything is known to be wrong,
  but because the mechanism that would have told us is unreliable in exactly
  the case we kept hitting. The manager has **not** touched the gate tooling
  to fix it: `src/scistudio/qa/governance/**` is a governance surface, the
  change needs owner review, and repairing the evaluator mid-dispatch would
  change the meaning of evidence already recorded under the old behaviour.
- **What was done instead**: S5-B4 marks the two `tests/qa/**` tests `serial`
  under a manager scope amendment, which breaks link 1 and therefore link 2.
- **Link 3 is now closed**, on its own branch and under its own gate record so
  the change is reviewable in isolation: `fix/2253-gate-timeout-not-satisfied`
  makes a timeout its own recorded outcome, makes it unsatisfied, gives the
  budget an env knob defaulting to today's 600s, and makes `check` and
  `finalize` share one predicate. **Evidence already recorded under the old
  behaviour was left exactly as it stands** — no ledger event was rewritten or
  re-evaluated — so the manager's reservation above still applies to every gate
  record written before that branch, and this fix does not retroactively make
  any of it worth more.
- **Status of the hidden red test**: on the integration branch, which carries
  the kernel-death fix (#2262), `-k "branch_switch or branch_change"` runs
  4 tests and all 4 pass on Windows — they run, they are not skipped. So
  F-B4-9 is likely a symptom the kernel fix already cured on the spec 5 track
  rather than a live defect. Likely, not certain: it has not been seen green
  on Linux in the serial phase, because the serial phase is what gets skipped.
- **Suggested title**: `fix(qa): gate_record must not record a timed-out python_tests as satisfied`

#### M-004 - The frontend's `ActiveContextResponse` does not declare the `focus` the server echoes

- **Severity**: P3 - not a break; the frontend ignores the extra field and
  nothing reads it today.
- **Found by**: manager, checking the spec 4 / spec 5 focus wire field by field.
- **Evidence**: `frontend/src/lib/api/ai.ts` declares
  `interface ActiveContextResponse { workflow_id: string | null }`. The server's
  `ActiveContextResponse` in `src/scistudio/api/routes/ai.py` returns
  `{workflow_id, focus}`, where `focus` is the **stored** record including the
  backend-stamped `reported_at`.
- **Why it is worth recording**: the request half of this wire is exact - the
  manager diffed `WorkspaceFocusPayload` against `WorkspaceFocusModel` and all
  seven fields match with nothing extra on either side. The response half is
  the one place the two descriptions differ, and it differs by omission rather
  than by disagreement, which is the benign direction. It is listed so that
  whoever first wants to read the echo back - to show a stale focus in the UI,
  say - finds the type already waiting rather than discovering the field by
  accident.
- **Suggested title**: `chore(frontend): ActiveContextResponse omits the focus the server returns`

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

**Final tally for this task**: 16 `python_tests` events in the ledger, **none
of them a pass** - 11 `fail`, each with a different set of 1 to 6 tests, and 5
`unknown / TimeoutExpired`. One run outside the gate, with the gate's exact
command and no 600-second cap, finished in 5m55s with `2 failed, 9310 passed`,
the two being `test_clean_block_save_triggers_reload_and_event` and
`test_generate_facts_write_and_check_round_trip` - two more that had passed in
every other run and pass in isolation.

So the honest statement about this branch is: **9310 of 9312 Python tests pass
on any given run, the failing two are different every time, none of them is in
this diff (which contains no `.py` file at all), and the gate ledger holds no
green Python run to point at.** CI, on a dedicated runner, is the first place
this suite can be judged.

The two "clean" pre-PR `check` runs this task produced were both discharged by
F-A1-009's timeout path rather than by a passing suite, which is why no PR was
opened on them.



### S4-A2

Owner: the notebook shell, the cell editors, the output renderer, the marks,
and the cell commands (ADR-054 spec 4, T-004 to T-007).

#### F-A2-001 — The session API has no delete-cell and no move-cell route, so FR-010 cannot be sent

- **Severity**: P2 — two of FR-010's five commands cannot reach the runtime.
- **Found by**: S4-A2, wiring the cell commands.
- **Evidence**: `src/scistudio/api/routes/explore.py` carries
  `POST /sessions/{id}/cells` (insert), `PUT .../cells/{cell_id}` (write) and
  `PUT .../cells/{cell_id}/enabled`, and no delete or move.
  `ExploreSession` (`src/scistudio/explore/session.py`) exposes `insert_cell`,
  `set_cell_source` and `set_cell_enabled` and neither a delete nor a move —
  although the document underneath it already has one
  (`NotebookDocument.remove_cell`, `src/scistudio/explore/notebook.py:587`).
- **What the shell does about it**: `NotebookShell.tsx` renders the three
  controls — delete, move up, move down — **disabled**, each carrying the reason
  in its `title`, and `NotebookShell.test.tsx` asserts that. Hiding them would
  make the shell look finished; sending a request to a route that does not exist
  would show the person a failure that is not theirs.
- **Deliberately not worked around**: a move expressed as "write the sources of
  two cells in swapped order" would change which cell id owns which source, and
  every mark, output and execution count the runtime holds is keyed by cell id.
  The notebook would look moved and the marks would be wrong.
- **Fix**: add `DELETE /api/explore/sessions/{id}/cells/{cell_id}` and a move
  route (or an `index` field on the write route) plus the session-service
  methods behind them, publishing `analysis_updated` as `insert_cell` does. That
  is a `src/scistudio/**` change, which no agent in this dispatch may make.
- **Suggested title**: `explore: the session API cannot delete or move a cell (ADR-054 FR-010)`

#### F-A2-002 — An unsaved draft does not survive a tab switch

- **Severity**: P3 — no typing is lost in the ordinary case; one edge case
  loses a conflicting draft.
- **Found by**: S4-A2, writing the reload reconciliation.
- **Evidence**: `NotebookShell.tsx` holds `drafts` in component state, and the
  workspace unmounts the centre and right columns when the active tab changes.
  The shell flushes every **non-conflicting** draft to
  `PUT /cells/{cell_id}` in its unmount cleanup, so ordinary typing is saved
  rather than dropped; a draft marked **conflicting** by a reload is deliberately
  not flushed — writing it would overwrite the edit that arrived from outside
  without anybody deciding to — and is therefore lost on a tab switch.
- **Why it is here and not fixed**: the durable home for a draft is
  `ExploreSessionState`, and `frontend/src/store/exploreSlice.ts` and
  `store/types.ts` are S4-A1's write set in this dispatch. The spec's own
  `CellView` entity does not carry a draft field either, so this is a small spec
  addition as much as a code one.
- **Fix**: add `draft` and `draftConflicting` to `CellView`, write them from the
  shell, and reconcile them in the slice's `applyExploreCells` instead of in the
  component. `reconcileDrafts` in `NotebookShell.tsx` is already a pure function
  and moves as it is.
- **Suggested title**: `explore: keep an unsaved cell draft in the session slice, not in the shell`

#### F-A2-003 — A script-driven HTML output renders inert, and its frame has a fixed height

- **Severity**: P3 — a deliberate trade, recorded so it is a decision and not a
  surprise.
- **Found by**: S4-A2, implementing FR-011's sandboxed frame.
- **Evidence**: `OutputRenderer.tsx` renders `text/html` and `image/svg+xml`
  into an `<iframe sandbox="" srcdoc=...>`: no scripts, no same-origin access,
  no forms, no popups, no navigation. The bundle carries no HTML sanitiser and
  none was added — the frame is the mechanism, and it is stronger than a filter
  list, which has to be right about every attribute and every future browser.
- **What it costs**: a Plotly, Bokeh or ipywidgets output — whose `text/html`
  is a script bundle — renders as its static markup rather than as a figure.
  Matplotlib, pandas `_repr_html_`, and every image output are unaffected, and a
  Plotly output that also carries `text/plain` falls back to it.
  The frame is also a fixed 240px tall, because a frame that is granted nothing
  cannot post its content height back out.
- **Fix, if the owner wants live figures**: grant `allow-scripts` (and *never*
  `allow-same-origin` beside it, which together defeat the sandbox), and add a
  small height handshake — which is the panel-contract spec's frame host, and
  the reason to consider routing rich outputs through that host instead.
- **Suggested title**: `explore: decide whether notebook HTML outputs may run scripts in their frame`

#### F-A2-004 — Two external edits in a row cause one re-read

- **Severity**: P3 — a narrow race; the notebook is stale on screen until the
  next event.
- **Found by**: S4-A2, wiring FR-017's reload.
- **Evidence**: `ExploreSession.reload_if_changed`
  (`src/scistudio/explore/session.py:605`) publishes
  `analysis_updated` with `reason: "external_edit"` and **no cells**, so the
  shell re-reads `GET /cells` when it sees that reason. The slice stores only
  `lastAnalysisReason` (`store/exploreSlice.ts`), a bare string with no
  timestamp or sequence, so a second `external_edit` in a row leaves the value
  unchanged, the shell's effect does not re-run, and the second reload is not
  read back until some other event arrives.
- **Fix**: give the slice the analysis event's timestamp beside its reason (the
  event already carries one), or have the slice apply the re-read itself. Both
  are in `exploreSlice.ts`, which is S4-A1's write set.
- **Suggested title**: `explore: the shell misses a second consecutive external edit`

#### F-A2-005 — The ANSI renderer is ours, and it renders no carriage returns

- **Severity**: P3 — a scope note about what "ANSI colour" was taken to mean.
- **Found by**: S4-A2, implementing FR-011.
- **Evidence**: the bundle carries no ANSI library and **none was added**.
  `parseAnsi` in `OutputRenderer.tsx` implements the SGR subset IPython emits —
  reset, bold/dim/italic/underline, the sixteen basic colours, the 256-colour
  cube, truecolor — and consumes and drops every other escape, including one
  that never terminates. `OutputRenderer.test.tsx` asserts all of that against a
  real IPython traceback.
- **What is not done**: it is a colouriser, not a terminal. A `tqdm` progress
  bar redraws itself with `\r` and cursor moves, and renders here as one line
  per redraw rather than as one bar. Jupyter's own notebook renderer has the
  same limitation for saved output; JupyterLab's console does not.
- **Fix, if it matters**: collapse `\r`-separated runs to their last segment
  before rendering — about ten lines in `AnsiText` — or, if real terminal
  semantics are ever wanted, note that the bundle already carries `@xterm/xterm`
  for the AI terminal.
- **Suggested title**: `explore: collapse carriage-return progress output in cell streams`

#### F-A2-006 — The toolbar's test evidence is split across files, and the spec names only one

- **Severity**: P3 — bookkeeping.
- **Found by**: S4-A2.
- **Evidence**: `docs/specs/adr-054-explore-frontend.md` frontmatter lists
  `frontend/src/explore/SessionToolbar.test.tsx`, but the toolbar is written by
  three agents in this assembly — run controls here, the kernel list and package
  in S4-A4, confirm and cancel in S4-A3. S4-A2's half is therefore in
  `SessionToolbar.runControls.test.tsx`, so that three agents editing one test
  file in parallel does not become a merge conflict in the evidence.
- **Fix**: either accept the split and correct the spec's test list, or have the
  integration agent fold the halves into `SessionToolbar.test.tsx` once all
  three have landed.
- **Suggested title**: N/A — for the integration agent to settle.

#### F-A2-007 — The gate's own working directories make three audit tests exceed the 60s per-test kill

- **Severity**: P2 — three tests fail in `gate_record check` on a worktree that
  has been prepared for `gate_record check`, and they are not the agent's.
- **Found by**: S4-A2, reading the gate check's pytest tail.
- **Evidence**: the run reported
  `tests/qa/test_audit_full_audit.py::test_full_audit_renders_human_readable_facts_summary`,
  `tests/qa/test_generate_facts_cli.py::test_generate_facts_write_and_check_round_trip`
  and `tests/ai/test_mcp_tools_disk_integration.py::test_concurrent_write_workflow_serialises`
  as failed, each on `pytest-timeout`'s 60s wall-clock kill
  (`pyproject.toml:306`), with the traceback inside
  `scistudio/qa/audit/governed.py:76` — `repo_root.glob(pattern)` plus a `stat`
  per match. Re-run with `--timeout=900` and no other change:

  ```
  3 passed in 117.15s
  ```

- **The cause is repo bulk, not the diff.** The governed-file globs of the
  landed specs include `frontend/**` and `.workflow/**`, and in a prepared
  worktree those two walk:

  | pattern | paths | time per call |
  |---|---:|---:|
  | `frontend/**` | 35,591 | 2.08s |
  | `.workflow/**` | 26,697 | 1.28s |

  Both directories are there **because the gate put them there**:
  `frontend/node_modules` is what the frontend checks need, and
  `.workflow/local/venv` is the CI-equivalent environment `check` builds. So
  the check's own preparation is what pushes the audit past its per-test kill,
  and it will do it to every agent on a fresh worktree.

- **This diff is frontend-only** — no `src/scistudio/**` or `tests/**` file is
  touched — so none of the three can be caused by it.
- **Fix**: have `governed_file_matches` skip ignored directories (it already
  has a `tracked_paths` set beside it in `governed.py` and could resolve a glob
  against that instead of against the filesystem), or exclude `node_modules`,
  `dist` and `.workflow/local` from the walk. Either is a `src/scistudio/**`
  change, out of every agent's write set in this dispatch.
- **Suggested title**: `qa: governed-file globs walk node_modules and the gate venv, timing out three audit tests`

#### F-A2-008 — The evaluator reconciles a check whose execution errored as satisfied

- **Severity**: P1 for the gate's own trustworthiness — a green
  "reconciliation passed" can stand on a check that never produced a result.
- **Found by**: S4-A2, reading its own ledger after the check went green.
- **Evidence**: `.workflow/records/2253-feat-2253-notebook-shell.json`. The
  `python_tests` check events for the final diff fingerprint read, in order:

  | at (UTC) | status | summary |
  |---|---|---|
  | 10:04:36 | `fail` | `exit 1` |
  | 10:18:22 | `unknown` | `execution error: TimeoutExpired` |
  | 10:33:28 | `unknown` | `execution error: TimeoutExpired` |

  and the reconcile event written 0.4s after the last one reads
  `{"result": "pass", "unsatisfied": []}`. `python_tests` never passed on this
  diff, and the obligation was reported satisfied anyway.
- **Why it matters**: `unknown` is the status for "the check did not run to a
  verdict". Treating it as satisfied means a check that times out — which is
  exactly what happens on a loaded machine, and this dispatch runs five agents'
  suites at once — is indistinguishable from a check that passed. An agent
  reading the banner would report a green gate in good faith.
- **Fix**: treat `unknown` as unsatisfied in the evaluator, with a repair hint
  that says the check errored rather than failed. `src/scistudio/qa/**`, out of
  every agent's write set in this dispatch.
- **Suggested title**: `gate: an errored (unknown) check reconciles as satisfied`

### S4-A3

Owner: the variable strip, the panel slots, the emission path, the pause tab,
and the retirement of the interactive modal (ADR-054 spec 4, T-008 to T-011).

#### F-A3-001 — A producing request for a type has no HTTP surface

- **Severity**: P1 — FR-019 is implemented against a listing rather than
  against the resolver spec 1 wrote for it.
- **Found by**: S4-A3, building the variable strip.
- **Evidence**: `src/scistudio/panels/router.py::PreviewRouter.resolve_request`
  is the capability-aware entry point FR-048 and FR-049 describe: it filters the
  candidates to those declaring at least the required capability, runs the
  FR-003 specificity ladder, applies the per-type **per-capability** user choice
  from `src/scistudio/panels/choices.py`, and falls back to the displaying
  resolution when nothing produces for the type. No route reaches it with a
  *type name*: `GET /api/panels?target_type=` returns the catalogue in tier
  order with no ladder and no choice, and `POST /api/previews/sessions` hardcodes
  `granted_capability=PanelCapability.DISPLAYING` in
  `src/scistudio/api/routes/panels.py::envelope_response`.
- **What was built instead**: `resolveProducingPanel` in
  `frontend/src/explore/PanelSlots.tsx` reads `GET /api/panels?target_type=<T>`
  and takes the first row whose declared capability satisfies `producing`, using
  the contract's own `capabilitySatisfies`; with no producing row it takes the
  first row, which is FR-049's display fallback with no outbound path. That is
  one line of selection over a backend-ordered list rather than a second
  resolver — but it is **not** the ladder, and it silently ignores a producing
  choice a person has recorded for the type.
- **Consequence today**: a person who chose a preferred producing panel for
  `DataFrame` gets whichever producing panel is highest in tier order instead.
  A type served by a specific-parent panel and a general one resolves by tier
  and priority rather than by specificity.
- **Fix**: add a capability parameter to the panel resolution surface — either
  `GET /api/panels/resolve?target_type=<T>&capability=producing` returning a
  `PanelDescriptorModel` plus `fell_back_to_display`, or a `capability` query on
  the existing listing that makes the backend order by `resolve_request` — then
  delete the selection in `resolveProducingPanel` and mount what it answers.
  That is a `src/scistudio/**` change, which no agent in this dispatch may make.
- **Cited by**: `frontend/src/explore/PanelSlots.tsx` (`resolveProducingPanel`,
  `TODO(#2253)`).
- **Suggested title**: `feat(panels): expose capability-aware panel resolution over HTTP so the Explore strip can make a producing request`

#### F-A3-002 — `PanelSpecSummary` is missing the `descriptor` the backend sends

- **Severity**: P2 — a wire field the frontend cannot see without a cast.
- **Found by**: S4-A3, resolving a panel for a variable's type.
- **Evidence**: `scistudio.api.schemas.PanelSpecModel` carries
  `descriptor: PanelDescriptorModel | None` and
  `src/scistudio/api/routes/panels.py::_list_entry` fills it for every panel
  with a directory. `PanelSpecSummary` in `frontend/src/types/api.ts` (line 787)
  declares every other field of that model and not this one.
- **Consequence**: `PanelSlots.tsx` declares the field structurally
  (`PanelCatalogueRow`) to read the descriptor it is being sent, so the type is
  described in two places and only one of them is checked.
- **Fix**: add `descriptor?: PanelDescriptorResponse | null` to
  `PanelSpecSummary` and drop `PanelCatalogueRow`. `frontend/src/types/api.ts`
  is S4-A1's file in this dispatch. This is one more instance of `#2237`
  (nothing checks the API wire between `schemas.py` and `types/api.ts`).
- **Suggested title**: `fix(frontend): PanelSpecSummary omits the descriptor GET /api/panels sends`

#### F-A3-003 — `interactive_prompt` carries no run id, so the escalation has to guess one

- **Severity**: P1 — FR-026 and FR-027 open a session over "the paused run" and
  nothing on the wire names that run.
- **Found by**: S4-A3, building the pause tab's notebook control.
- **Evidence**: the event's `data` is built in
  `src/scistudio/engine/scheduler/_dispatch.py` (`INTERACTIVE_PROMPT`) and
  carries `workflow_id`, `block_type`, `panel_manifest`, `panel_descriptor`,
  `panel_payload` and `input_signature` — no run id. `serialise_event` in
  `src/scistudio/api/ws.py` hoists `block_id` and `workflow_id` and nothing
  else. But `POST /api/explore/sessions` with `source: "paused_run"` requires
  **both** `block_id` and `run_id`
  (`src/scistudio/api/routes/explore.py`, and
  `SessionService.open_over_paused_run` -> `resolver.paused_run_inputs(run_id, block_id)`,
  which queries `block_executions` by `(run_id, block_id)`).
- **What was built instead**: `openPausedRunNotebook` in
  `frontend/src/explore/ExploreTab.tsx` reads `prompt.data.run_id` when it is
  there and otherwise takes the newest run of the prompt's own workflow from
  `GET /api/runs?workflow_id=...&limit=1`. The run that is paused is by
  construction the one that is running, so this is right in every ordinary case
  and wrong for two concurrent runs of the same workflow.
- **Fix**: put `run_id` on the `interactive_prompt` event's data beside
  `workflow_id`, and read it in
  `frontend/src/hooks/useWebSocket.parts/handleLifecycle.ts::handleInteractivePrompt`.
  Both halves are outside this agent's write set.
- **Cited by**: `frontend/src/explore/ExploreTab.tsx` (`openPausedRunNotebook`,
  `TODO(#2253)`).
- **Suggested title**: `fix(engine): the interactive_prompt event carries no run_id, so the Explore pause cannot open a session over the paused run`

#### F-A3-004 — A settled pause leaves its tab on screen, because closing it would lose the remembered decision

- **Severity**: P2 — clutter now, a data loss if it is "fixed" naively.
- **Found by**: S4-A3, writing the confirm path's interaction-memory test.
- **Evidence**: `createCloseTab` in
  `frontend/src/store/tabSlice.parts/workflowTabActions.ts` sets
  `EMPTY_TAB_STATE` when the closed tab was the last one, and otherwise calls
  `restoreTab(nextTab)`, which overwrites the live workflow slice with that
  tab's captured snapshot. `PauseControls.onConfirm` writes the remembered
  decision into the node's config through `updateNodeConfig`, which writes the
  **live** slice — so closing the pause tab immediately afterwards discards it.
  The retired modal never switched tabs and so never had the problem; the test
  that caught it is `records the emission as the remembered decision when the
  node opted in` in `frontend/src/explore/PauseTab.test.tsx`, which failed with
  `expected null` when confirm closed the tab.
- **What was built instead**: `settle()` clears the prompt and leaves the tab.
  `PausePanel` then renders "This block is no longer waiting for a decision."
  and the person closes the tab.
- **Fix**: make `closeTab` capture the live workflow slice into the tab that
  owns it before restoring the next one (which is what `syncActiveTab` already
  does for a preview or Explore tab), then have `settle()` close the tab.
  `tabSlice.parts/**` is S4-A1's in this dispatch.
- **Cited by**: `frontend/src/explore/PanelSlots.tsx` (`settle`, `TODO(#2253)`).
- **Suggested title**: `fix(frontend): closeTab restores the next tab's snapshot over unsaved live workflow state`

#### F-A3-005 — FR-020's declared outputs are only knowable after a packaging check

- **Severity**: P2 — the auto-pin is correct but usually has nothing to act on.
- **Found by**: S4-A3, implementing FR-020.
- **Evidence**: the only surface that reports which names a notebook declares as
  outputs is `POST /api/explore/sessions/{id}/packaging/check`, whose
  `outputs[].bound_name` names them (`PackagedPortModel`). Neither
  `BindingsResponse` nor `GraphResponse` carries a "declared" flag, and
  `explore.analysis_updated` carries only a reason.
- **What was built instead**: `declaredOutputNames` in
  `frontend/src/explore/VariableStrip.tsx` unions
  `session.lastReport.outputs[].bound_name` with the bound run's port names when
  the session was opened over a block's outputs. Until something requests a
  packaging check — S4-A4's package control, T-013 — the first source is empty,
  so a file-opened or notebook-opened session pins nothing.
- **Fix**: report the declared output names on `BindingsResponse` (the analysis
  already computes them for `slice_for_outputs`), or have the shell request a
  packaging check on open. The first is a `src/scistudio/**` change; the second
  writes on a surface the person did not ask to write on.
- **Suggested title**: `feat(explore): report a notebook's declared output names on the bindings response`

#### F-A3-006 — FR-023's shell-side freeze is dark until the graph is fetched

- **Severity**: P2 — the behaviour is still correct, just late.
- **Found by**: S4-A3, implementing the submission freeze.
- **Evidence**: `frozenNamesOf` in `frontend/src/explore/PanelSlots.tsx` reads
  the running cell's changed set from `session.graph.changedSets`, which is
  written only by `applyExploreGraph`. Nothing in the merged frontend calls
  `exploreApi.getExploreGraph` yet — `grep -rn "getExploreGraph" frontend/src`
  finds only the client and the slice. Until T-014's graph view lands and
  fetches it, the freeze falls back to the names the cell was last *observed* to
  change, and for a cell that has never run that set is empty.
- **Consequence**: the emission is then sent, and the backend refuses it with
  `409 panel_frozen`, whose message the slot renders as the same note. The
  person sees the same refusal one round trip later.
- **Fix**: fetch the graph when the analysis moves, as the strip now fetches the
  bindings. It belongs with T-014's graph view (S4-A4) rather than in a second
  place.
- **Suggested title**: `fix(explore): nothing fetches the dependency graph, so the shell-side submission freeze never fires`

#### F-A3-007 — Two partial mocks of `lib/api/explore` had to gain the methods the real components call

- **Severity**: P3 — the same fragility S4-A1 recorded as F-A1-007.
- **Found by**: S4-A3, replacing the region placeholders with real components.
- **Evidence**: `frontend/src/explore/ExploreTab.test.tsx` mocks
  `../lib/api/explore` with a hand-written object holding `openExploreSession`
  alone. Landing the real `PanelSlotRegion` and `VariableStripRegion` made
  `mounts one slot per open panel so two can be compared` fail with
  `TypeError: exploreApi.windowExploreVariable is not a function`; the strip's
  bindings read would have been the next one.
- **Fixed by**: adding `windowExploreVariable` and `getExploreBindings` to that
  mock. The underlying fragility is not fixed: the next method a region calls
  breaks it again.
- **Fix**: convert it to the `importOriginal` form
  (`store/__tests__/panelCatalogInvalidation.test.ts` is the repository's model).
- **Suggested title**: `test(frontend): explore suites hand-write partial API mocks that break on every new call`

#### F-A3-008 — A pause tab reports its kernel as "opening"

- **Severity**: P3 — cosmetic.
- **Found by**: S4-A3, rendering the pause tab.
- **Evidence**: `kernelLabel` in `frontend/src/explore/SessionToolbar.tsx`
  answers `"opening"` for `session === undefined`, which is right for a session
  tab whose open is in flight and wrong for a pause tab, which has no session at
  all until FR-026's escalation and is not waiting for one.
- **Fix**: one branch in `kernelLabel` on `tab.mode === "pause" &&
  tab.sessionId === null` — "no kernel", or no badge at all. Left alone because
  `kernelLabel` is the toolbar's shared rendering and S4-A4 owns the kernel half
  of that toolbar (T-012, T-013); two agents editing the same function in the
  same wave is the conflict this dispatch is arranged to avoid.
- **Suggested title**: `polish(explore): a pause tab shows its kernel as "opening" when it has no session`

#### F-A3-009 — `tutorialReviewPanel.test.ts` had to move out of the deleted modal's directory

- **Severity**: P3 — recorded so the move is not read as a deletion.
- **Found by**: S4-A3, deleting `App.parts/InteractiveModals.parts/**`.
- **Evidence**: the file tested the shipped `core.interactive.review_labels`
  panel *document* — it reads the asset off disk and drives the frame handshake
  — and had nothing to do with the modal beyond living under its directory.
  Deleting the directory would have deleted a test of a shipped tutorial asset.
- **Fixed by**: `git mv` to `frontend/src/panels/__tests__/`, beside the other
  panel-document suites. It uses `process.cwd()` rather than a path relative to
  itself, so nothing in it needed changing, and it passes there.
- **Suggested title**: N/A — done, recorded for the audit.


#### F-A3-010 — Deleting the modal forced a governance correction in three ADR-051 documents

- **Severity**: P2 — done, recorded because it left this agent's write set.
- **Found by**: S4-A3, from `gate_record check`'s `full_audit` failure.
- **Evidence**: `docs/adr/ADR-051.md`, `docs/adr/ADR-051-addendum1.md` and
  `docs/specs/adr-051-interactive-blocks.md` each list
  `frontend/src/App.parts/InteractiveModals.tsx` under `governs.files`. FR-024
  requires that file deleted, so the audit reported six errors —
  `doc-drift.phantom-file` and `closure.unresolved-file-claim`, one pair per
  document — and `full_audit` is a merge-blocking check, so the branch could not
  pass its gate and the failure would have followed the merge onto the track
  branch and every sibling.
- **What was done**: the one line was removed from each document's
  `governs.files`, and the spec's affected-files table row now says the file was
  deleted by ADR-054 spec 4 FR-024. No decision, requirement or prose in ADR-051
  changed, and its two sibling frontend files (`DataRouterModal.tsx`,
  `PairEditorModal.tsx`) still exist and are still governed.
- **Why it is here**: `docs/adr/**` and `docs/specs/**` are outside the S4-A3
  write set. The alternative was to stop with the branch un-gateable, leaving a
  correction the manager would have had to make anyway. Recorded with a
  `gate_record amend` naming the reason.
- **Worth an owner's eye**: whether a *retired* governed file should be
  expressible in the frontmatter (a `retired_governs`, or a note beside the
  path) rather than simply dropped, so the record still says the document once
  owned it.
- **Suggested title**: `chore(docs): ADR-051 governs a frontend file ADR-054 spec 4 deletes`

#### F-A3-011 — A timed-out check is recorded `unknown` and then satisfies its obligation

- **Severity**: P1 — the gate reports "reconciliation passed" over a check that
  never produced a result.
- **Found by**: S4-A3, on the second `gate_record check --mode pre-pr` run.
- **Evidence**: the ledger
  `.workflow/records/2253-feat-2253-panels-and-pause.json` holds

  ```json
  {"name": "python_tests", "status": "unknown", "exit_code": null,
   "summary": "execution error: TimeoutExpired", "raw_log_ref": null}
  ```

  and the reconcile event written 0.4s later is
  `{"result": "pass", "unsatisfied": []}`. The first run of the same check,
  which did complete, was recorded `fail` and correctly listed
  `checks.python_tests` as unsatisfied. So a check that *ran and failed* blocks
  and a check that *never finished* does not.
- **Why it happened here**: the machine is carrying several agents' test runs at
  once and the Python suite takes ~7 minutes of its own; the subprocess wrapper's
  deadline expired before pytest did.
- **Consequence**: an agent that does not read the ledger event by event would
  report a green gate on no evidence. The suite was re-run by hand for this
  branch rather than trusted.
- **Fix**: treat `unknown` as unsatisfied in the reconciler — a check with no
  exit code is not a check that passed — and say so in the repair hint
  ("python_tests timed out; re-run it") rather than printing "reconciliation
  passed".
- **Suggested title**: `fix(gate): a check that times out is recorded unknown and then counts as satisfied`

#### F-A3-012 — `PYTHONPATH=./src` is relative, and the explore kernel starts somewhere else

- **Severity**: P2 — one Python test fails for every agent that follows the
  dispatch preamble literally.
- **Found by**: S4-A3, re-running the Python suite by hand after F-A3-011.
- **Evidence**: with `export PYTHONPATH=./src` (the preamble's own line, and
  what `gate_record check` inherits),
  `tests/api/test_explore_branch_switch.py::test_a_branch_switch_kills_the_real_kernel_process`
  fails with

  ```
  BridgeProtocolError: The kernel bridge did not answer:
  ModuleNotFoundError: No module named 'scistudio'.
  ```

  The session's ipykernel is a real subprocess started under the temporary
  project directory, so the relative `./src` on the inherited `PYTHONPATH`
  resolves against *that* directory and finds nothing. With
  `PYTHONPATH=<repo>/src` spelled absolutely, the same file is `5 passed`.
- **Why it appeared now**: the test is new — ADR-054 spec 3 landed the real
  kernel — and it is the first test in the repository that spawns an interpreter
  which has to import `scistudio` for itself.
- **Fix**: say `PYTHONPATH=$(pwd)/src` in `docs/ai-developer/rules.md`, the
  dispatch preamble and the gate CLI reference, or have
  `scistudio.explore.kernel` absolutise the `PYTHONPATH` entries it passes to
  the kernel it launches. The second is the durable one: the kernel is launched
  with a cwd of the project, and a relative entry inherited from the server's
  environment can never mean what it meant there.
- **Also relevant to**: the whole Python suite otherwise passed on this branch
  (`9312 passed, 80 skipped, 8 xfailed`), and the two failures the first gate run
  reported — `test_system_vertical.py::test_execute_broadcasts_runtime_lifecycle_events_to_websocket`
  and `test_audit_full_audit.py::test_full_audit_renders_human_readable_facts_summary`
  — did not recur and pass in isolation. That is the contention S4-A1 recorded as
  F-A1-008, seen again.
- **Suggested title**: `fix(explore): the launched kernel inherits a relative PYTHONPATH and cannot import scistudio`

### S4-A4

Owner: packaging and its report, the packaged node's badge, the kernel list,
the dependency-graph view, and the palette's insert-call action
(ADR-054 spec 4, T-012 to T-015).

#### F-A4-001 - `GraphResponse` sends cell edges, so the frontend re-derives the version edges

`scistudio.explore.dependency_analysis` computes both graphs: `DependencyGraph`
carries `edges` (cell to cell, per name) **and** `version_edges` (version node
to version node), derived by `_version_edges` from `edges` plus `changed_sets`.
`GET /api/explore/sessions/{id}/graph` publishes `edges` and `changed_sets` but
not `version_edges`.

FR-032 asks for "one node per variable version". The only way to draw that from
what is on the wire is to run `_version_edges` again on the frontend, which is
what `buildVersionGraph` in `frontend/src/explore/GraphView.tsx` does. Every
input to it is the runtime's own fact, so no mark or dependency is invented -
but the same derivation now exists in two languages, and the sink case (a
reading cell that changes nothing keeps a node, with `target = None`) is
exactly the kind of rule that drifts.

**Fix**: add `version_edges` to `GraphResponse` and drop the frontend
derivation, or state in spec 4 that the frontend owns it. The route is
`src/scistudio/api/routes/explore.py`, which no agent in this dispatch may
write.

Cited by: `frontend/src/explore/GraphView.tsx` (`buildVersionGraph`),
`src/scistudio/explore/dependency_analysis.py` (`_version_edges`).

#### F-A4-002 - jsdom cannot prove a graph edge is drawn

`@xyflow/react` mounts a node from the node array, so `GraphView.test.tsx`
asserts version nodes, their highlight and the region selection against the
real component. It does **not** mount an edge without a measured viewport: the
edge renderer needs each endpoint's measured box and jsdom reports every box as
zero. Passing `width` / `height` / `measured` on the nodes does not help; that
was checked before the test was written this way.

The suite therefore asserts the edges where they are decided
(`buildVersionGraph`, origins included) and asserts that the view was handed
them, through the count it renders. What is not covered under the runner is
"an SVG path exists between these two boxes".

**Fix**: cover it in spec 4's end-to-end scenario (T-016), which runs a real
browser. No unit-level fix is available short of a headless-Chrome runner.

Cited by: `frontend/src/explore/GraphView.test.tsx`.

#### F-A4-003 - The notebook badge is a marker, and today it renders on nothing

Two separate limits, both deliberate.

The badge (FR-030) is `pointer-events-none`. The way back into the notebook is
the double-click FR-004 already wired in `useCanvasHandlers`; making the badge
itself a second entry point needs a callback threaded through
`WorkflowCanvas.parts/flowNodeBuilder.ts` into `BlockNodeData`, and neither
file is in this agent's write set. The badge's `title` says the double-click is
the way in, so it is not a dead end - but a person who clicks the badge gets
nothing.

And it renders on nothing at all right now, because it reads
`isPackagedNotebookBlock`, which reads `BlockSummary.notebook_filename`, which
the backend does not send (S4-A1's `F-A1-001`). The badge lights up the moment
that lands, with no frontend change.

**Fix**: land F-A1-001's backend change first; then decide whether the badge
should also be clickable, which is a `flowNodeBuilder` + `BlockNodeData`
change.

Cited by: `frontend/src/components/nodes/BlockNode.tsx`,
`frontend/src/explore/packagedBlock.ts`.

#### F-A4-004 - A retired kernel is invisible to `GET /api/explore/kernels`

`ExploreSessionService.kernels()` keeps only listings whose state is
`starting`, `idle` or `busy`, and `KernelListItem` carries no `needs_restart`
field. So the two things FR-015 and FR-016 ask the list for cannot both come
from that route: a kernel the runtime retired (a branch change) or that died
has already left the response, and the response could not have said "needs
restart" about it anyway.

`KernelList` therefore merges the response with the per-session kernel views
the `explore.kernel_state` events write, and a retired kernel's row comes from
the session view alone. That is FR-015's "from the kernel-state events" read
literally, and it works - but a session this browser has never opened has no
session view, so its retired kernel is in neither source.

**Fix**: either add `needs_restart` to `KernelListItem` and stop filtering the
listing by state, or say in spec 4 that a retired kernel is reported per
session rather than per project.

Cited by: `frontend/src/explore/KernelList.tsx` (`buildKernelRows`),
`src/scistudio/explore/session.py` (`ExploreSessionService.kernels`),
`src/scistudio/api/routes/explore.py` (`KernelListItem`).

#### F-A4-005 - The kernel list does not poll, so another session's new kernel is late

The list fetches when it is opened and on its Refresh control, and after that
it moves only from `explore.kernel_state` events. Those events are per session:
a session this browser has never opened has no row to move until the next
fetch, and memory readings do not update at all while the list is open.

Left as is on purpose: FR-015 says nothing about a refresh interval, and a poll
on an open popover is a request every few seconds for a surface most people
open for two of them.

**Fix**: decide with the owner whether the list should poll while open, and
whether the memory reading should tick.

Cited by: `frontend/src/explore/KernelList.tsx`.

#### F-A4-006 - The inserted block call is a template, not a runnable line

FR-031's inserted cell is `<name> = blocks.run("<type_name>", <port>=...)`,
with `...` for every input port. It parses - deliberately, because the
dependency analysis reads every cell with `ast.parse` and a half-typed line
would be flagged as broken - but it does not run until the person replaces each
`...`.

The palette could do better: it knows the block's accepted types, and the
session's bindings response knows which live names carry those types, so a port
with exactly one candidate could be filled in. It does not, because the palette
does not currently read the bindings and guessing wrong is worse than an
obvious blank.

Two smaller edges in the same place. A port whose name is not a Python
identifier is omitted from the call rather than written as something that would
not run. And the call is a single line however many ports the block has.

**Fix**: consider filling a port whose type has exactly one live binding, and
wrapping the call when it passes more than three ports.

Cited by: `frontend/src/components/BlockPalette.parts/exploreCall.ts`.

#### F-A4-007 - Spec 4 puts the kernel list and package control in `SessionToolbar.tsx`; the landed contract puts them in a region

Spec 4 section 4.2 lists `frontend/src/explore/SessionToolbar.tsx` as the file
carrying "run-stale, interrupt, restart, commit, package, notebook toggle,
kernel list, confirm and cancel". S4-A1's landed `SessionToolbar.tsx` carries
the frame and the notebook toggle only, and routes each group of controls to
one region component in `regions/ExploreRegions.tsx` so four agents could take
one region each without restructuring a shared file.

T-012 and T-013 therefore replaced `ToolbarKernelControls` in
`regions/ExploreRegions.tsx` and did not touch `SessionToolbar.tsx` at all.
That is what the dispatch's own instruction said to do, and it is the smaller
diff; it just does not match what the spec's affected-files table says.

**Fix**: a one-row correction to spec 4 section 4.2 naming
`regions/ExploreRegions.tsx` as the toolbar's control host. A `docs/specs/**`
change, out of every agent's write set here.

Cited by: `frontend/src/explore/regions/ExploreRegions.tsx`,
`docs/specs/adr-054-explore-frontend.md` section 4.2.

#### F-A4-008 - `frontend/vitest.setup.ts` gained a global no-op `ResizeObserver`

The graph view mounts `@xyflow/react`, which constructs a `ResizeObserver`
unconditionally. jsdom has none, so S4-A1's own `ExploreTab.test.tsx` graph
toggle threw on mount the moment the placeholder became a real flow - and that
is a sibling's file, which this agent may not edit.

The polyfill went into the shared setup beside the existing `matchMedia`,
`createObjectURL` and `localStorage` shims, guarded so the terminal harness's
own `vi.stubGlobal("ResizeObserver", ...)` still wins. The full frontend suite
was re-run after the change: 210 files, 2444 tests, all passing. Recorded as a
`gate_record amend` rather than slipped in, because it is outside the write set
the dispatch prompt named.

**Fix**: none needed; noted so the audit reads a deliberate scope expansion
rather than a stray edit.

Cited by: `frontend/vitest.setup.ts`.

#### F-A4-009 - The packaging report closes only through its own control

`PackagingControl` opens the report as an absolutely-positioned card and closes
it on its Close button, on a successful package, and on nothing else - not on a
click outside it and not on Escape. Every other popover in the palette closes
on pointer-leave, which is the wrong gesture for a card carrying a text field,
so neither existing pattern fits.

**Fix**: add outside-click and Escape dismissal, ideally through a shared
helper rather than a third hand-rolled one.

Cited by: `frontend/src/explore/PackagingReport.tsx`.

#### F-A4-010 - A check that times out is recorded `unknown` and then reconciled as satisfied

`gate_record.checks.run_check` runs every check with a hardcoded
`timeout=600` (`checks.py:640`). When that fires it returns

```python
CheckEvent(..., exit_code=None, status="unknown",
           summary=f"execution error: {type(exc).__name__}")
```

and `evaluator.py` then does this, immediately after a comment explaining that
a required check which cannot be proven must fail closed:

```python
if event.status == "skipped":
    ...            # FAIL CLOSED (section 7.5): unproven is not proven passing
    continue
if event.status != "fail":
    continue       # <- "unknown" lands here and satisfies the obligation
```

So a required check that **failed** blocks PR readiness and one that **never
finished** does not. Observed three times on this row: three `python_tests`
events with `"status": "unknown", "summary": "execution error:
TimeoutExpired"`, each followed by a reconciliation of
`{"result": "pass", "unsatisfied": []}`, while every `"status": "fail"` event
produced `"unsatisfied": ["checks.python_tests"]`.

This is the shape of defect that only appears on a loaded machine - which is
exactly when an agent is most tempted to take the pass and move on. This row
did not: every run is in the ledger, the failures were reproduced and
classified, and the state is reported rather than banked.

**Fix**: extend the fail-closed branch to every status that is not `pass`.
`unknown` deserves its own repair hint - "the check did not finish in 600s;
re-run, or reduce the local load" is a different instruction from "the tool is
missing". A required check with `raw_log_ref: null` is the same condition seen
from another angle. Consider making the 600s configurable, since the Python
suite legitimately takes 5-8 minutes on an idle machine and there is no margin.

Cited by: `src/scistudio/qa/governance/gate_record/checks.py` (`run_check`,
`timeout=600`), `src/scistudio/qa/governance/gate_record/evaluator.py`
(`if event.status != "fail": continue`),
`.workflow/records/2253-feat-2253-packaging-and-graph.json`.

#### F-A4-011 - `run_python_tests` pins `-n auto`, which is hostile on a shared machine

`src/scistudio/qa/testing/run_python_tests.py` hardcodes `-n auto` for its
parallel phase. On the dispatch machine - 32 logical CPUs, and several agents
each running their own full suite at once, 122 python processes counted during
this row's runs - `auto` asks for 32 workers per agent, and workers start dying:

- run 1: `3 failed`, all three `node down: Not properly terminated`, plus an
  xdist `INTERNALERROR` from a zero-byte `.coverage.*` file a dead worker left
  behind (`sqlite3.OperationalError: no such table: file`).
- run 2: `5 failed` - three more crashed workers, plus
  `tests/ai/test_mcp_tools_disk_integration.py::test_concurrent_write_workflow_serialises`
  (a path-resolution race, already S4-A1's F-A1-008) and
  `tests/api/test_reload_on_save.py::test_broken_block_save_does_not_reload_or_emit`
  (`assert 2 == 1` on `file.changed` events - a duplicate watchdog event).
- run 4, at 12 workers: `3 failed`, a different three again -
  `test_concurrent_write_workflow_serialises` once more,
  `tests/api/test_panel_document_events.py::test_the_file_route_accepts_a_panel_document`,
  and `tests/qa/test_generate_facts_cli.py::test_generate_facts_check_reports_stale_file`.

- run 5, back at `auto`: `3 failed`, again a different three -
  `test_concurrent_write_workflow_serialises`,
  `tests/workflow/test_serializer_property.py::test_relativify_inverts_absolutify`,
  and `tests/qa/test_generate_facts_cli.py::test_generate_facts_write_and_check_round_trip`.
- run 6, as the other agents ramped up: `10 failed`, now including three
  `tests/api/test_workflows.py` execute/cancel tests. Those spawn engine
  subprocesses, and the gate passes `--timeout=60`; a 60-second per-test
  deadline is not survivable when 122 python processes are resident on 32
  logical cores. That is the mechanism behind the whole class.

Across six runs: more than twenty distinct failing node ids, never the same
set twice, and every failing set passes in isolation:

```
python -m pytest -p no:xdist --no-cov <that run's node ids>   ->  all passed
```

Two runs also outlived the gate's own 600-second per-check timeout, which is
how F-A4-010 was found.

`PYTEST_XDIST_AUTO_NUM_WORKERS` is honoured by xdist and is the lever, but at 6
the suite outran the gate's own timeout (F-A4-010).

**Fix**: let `run_python_tests` take a worker count (or read the env var and
default sensibly) so an agent on a busy machine can trade minutes for
reliability, and make the gate's per-check timeout scale with it. Also worth
deleting a stale zero-byte `.coverage.*` before the run rather than letting a
dead worker's leftovers fail the next one.

Cited by: `src/scistudio/qa/testing/run_python_tests.py`,
`docs/planning/adr-054-assembly-followups.md` `F-A1-008`.


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

### fix-codeql

Triage of the CodeQL alerts the assembly branch adds over `main`. The first
pass (`fix/2229-panel-codeql-findings`, PR #2260, merged) took the delta from
**12 to 5**: the four `js/prototype-polluting-assignment` alerts and the three
`py/path-injection` alerts on `panels/assets.py` cleared. The second pass
(`fix/2229-codeql-barrier`) established why the remaining four cannot be
cleared in code and what this repository can and cannot do about them.

**Where it stands, measured on `eb8b3588` (check-run `101292090119`):** the
assembly carries 60 open alerts and `main` carries 55. The delta is five —
four on `core.plot.basic/index.html` (FC-004) and one on `api/routes/git.py`
(FC-003). Nothing else on the branch is new.

#### FC-001 — every `py/path-injection` alert on the assembly is also on `main`, at identical counts

- **Severity**: P3 — not new, not this branch's, and not a regression. Whether
  any of the 51 is a real vulnerability is unexamined; only their provenance
  is settled here.
- **Found by**: fix-codeql. Re-checked in the second pass because
  `api/routes/user_library.py` appeared in a second annotation set and looked
  new. It is not: GitHub caps a check run at ~30 annotations, so the 22 paths
  in the first sample and the 26 in the second are two different samples of
  one unchanged set.
- **Evidence** — group both refs by path and compare, rather than trusting a
  line-number match, because the assembly's diff moves lines:

  ```bash
  for ref in refs/heads/main refs/pull/2255/head; do
    echo "== $ref"
    gh api "repos/jiazhenz026/SciStudio/code-scanning/alerts?state=open&per_page=100&ref=$ref" \
      --jq '[.[]|select(.rule.id=="py/path-injection")|.most_recent_instance.location.path]
            |group_by(.)|map({(.[0]):length})|add'
  done
  ```

  Both refs return the same object, byte for byte — 51 alerts across 11 paths:

  ```text
  {"src/scistudio/api/routes/data.py":3,"src/scistudio/api/routes/projects.py":3,
   "src/scistudio/api/routes/user_library.py":16,"src/scistudio/api/routes/workflow_watcher.py":2,
   "src/scistudio/desktop/package_installer.py":1,"src/scistudio/desktop/package_manager.py":7,
   "src/scistudio/plot/_context.py":2,"src/scistudio/plot/scaffold.py":5,
   "src/scistudio/plot/targets.py":1,"src/scistudio/utils/atomic_io.py":5,
   "tests/desktop/test_package_manager.py":6}
  ```

  `src/scistudio/panels/assets.py` is absent from both, having been 3 on the
  assembly before PR #2260: the lexical pre-check added there registered as a
  barrier CodeQL can see.
- **Why it is here and not done**: fixing them would turn a scoped security fix
  into a repo-wide sweep across five subsystems the ADR-054 dispatch does not
  own, on a branch that has to merge. The set is now bounded and reproducible,
  which is what a triage pass owes the next person.
- **Suggested title**: `Triage the 51 inherited py/path-injection alerts CodeQL reports on main`

#### FC-002 — the `scaffold_panel` skeleton and the agent-facing panel contract do not exist on this base, so the safe URL pattern is not in them yet

- **Severity**: P2 — the next authored panel reintroduces the finding this PR
  fixed in `core.plot.basic`.
- **Found by**: fix-codeql.
- **Evidence**: `src/scistudio/ai/agent/mcp/tools_panels/` and
  `src/scistudio/_agent_reference/panel-contract.md` are both absent from
  `track/adr-054-integration`; they are S5-B2's work on PR #2257, which targets
  `track/adr-054-spec5-agent-enablement`. The pattern this PR establishes is
  `safeAssetUrl` in
  `src/scistudio/panels/builtin/core.plot.basic/index.html` (an allowlist of
  `data:` media types per element plus a root-relative path, with TAB/LF/CR
  stripped before the check) and `idMap()` in
  `src/scistudio/tutorials/core/what-is-a-type/assets/panels/review_labels/index.html`
  (`Object.create(null)` for any map keyed by something out of the payload).
- **Why it is here and not done**: editing files that do not exist on this
  branch is not possible, and creating them here would collide with #2257.
- **Suggested title**: `Carry the panel URL allowlist and null-prototype map pattern into the scaffold_panel skeleton and the agent panel contract`

#### FC-003 — one `py/stack-trace-exposure` alert in `api/routes/git.py` is new on the assembly branch and outside the panel dispatch's scope

- **Severity**: P3 — medium severity, not among the 46 the PR check calls high,
  and untriaged.
- **Found by**: fix-codeql.
- **Evidence**: alert 270, `src/scistudio/api/routes/git.py:685`, present on
  `refs/pull/2255/head` and absent from `refs/heads/main`;
  `git diff --stat origin/main HEAD -- src/scistudio/api/routes/git.py` shows
  `+52` lines on this branch. It was not in the annotation set the dispatch
  named, and `api/routes/git.py` is in no agent's write set.
- **Why it is here and not done**: out of scope for this fix, and whichever
  spec added those 52 lines should own it.
- **Suggested title**: `Triage the py/stack-trace-exposure alert the assembly adds at api/routes/git.py:685`

#### FC-004 — the four `core.plot.basic` alerts cannot be cleared in code, and this repository honours no suppression mechanism except dismissal

- **Severity**: P2 — the code is correct and tested; what is unresolved is the
  alert, and it needs an owner decision rather than more engineering.
- **Found by**: fix-codeql, after PR #2260 failed to clear them.
- **The alerts**, on `refs/pull/2255/head` at `eb8b3588`:

  | # | Rule | Location | Severity |
  |---|---|---|---|
  | 260 | `js/xss` | `core.plot.basic/index.html:445` | high |
  | 258 | `js/client-side-unvalidated-url-redirection` | `core.plot.basic/index.html:445` | medium |
  | 272 | `js/xss` | `core.plot.basic/index.html:452` | high |
  | 271 | `js/client-side-unvalidated-url-redirection` | `core.plot.basic/index.html:452` | medium |

  They moved from 379/386 to 445/452 when `safeAssetUrl` was inserted above
  them; they are the same two sinks.
- **Why the code cannot clear them**: an allowlist validator returns the string
  it validated, so `payload.src` -> `url` -> `return url` -> `setAttribute` is
  an intact dataflow whatever the checks in between decided. Two ways to break
  it were considered and both rejected as contortions, with the reasoning
  written out beside `safeAssetUrl` in the document itself: re-encoding the
  base64 payload character by character through a constant alphabet is an
  identity function written as a loop over a megabyte-scale payload on the
  render path; decoding to a `Blob` for `URL.createObjectURL` buys the panel
  choosing the media type — which the element already constrains — in exchange
  for an object URL the panel must revoke on every zoom click or leak.
- **Why neither named suppression mechanism is available here**:
  - `.github/codeql/codeql-config.yml` query filters require **advanced
    setup**. This repository is on **default setup** —
    `gh api repos/jiazhenz026/SciStudio/code-scanning/default-setup` returns
    `{"state":"configured","query_suite":"default",...}`, and every alert
    instance carries
    `analysis_key: dynamic/github-code-scanning/codeql:analyze`. A config file
    would be inert.
  - Inline `// codeql[...]` / `# lgtm[...]` comments are not acted on by
    GitHub Code Scanning; they only populate a `suppressions` property in
    SARIF, which something else then has to consume. See FC-005 for the proof
    already sitting in this tree.
- **What is actually available**: dismissal, via the UI or the API. That is a
  repository security-state change with no diff for a reviewer to see, on
  exactly the class of thing that ends up hiding a real vulnerability, so it is
  the owner's to make rather than an agent's. If the owner agrees the four are
  false positives:

  ```bash
  for n in 258 260 271 272; do
    gh api -X PATCH "repos/jiazhenz026/SciStudio/code-scanning/alerts/$n" \
      -f state=dismissed -f dismissed_reason='false positive' \
      -f dismissed_comment='core.plot.basic gates every src through safeAssetUrl: an allowlist of data: media types per element plus a root-relative path. CodeQL follows the flow, not the condition, because the validator returns the string it validated. Pinned by frontend/src/panels/__tests__/panelHostilePayload.test.ts (23 cases fail without the gate).'
  done
  ```

- **The fact that should shape the decision**: `CodeQL` is **not** a required
  status check for merging to `main`. The active ruleset "Rules for Agents"
  (id 14656629) requires exactly five — `Lint & Format`,
  `Test (Python 3.11)`, `Test (Python 3.13)`, `Type Check`,
  `Import Contracts`:

  ```bash
  gh api repos/jiazhenz026/SciStudio/rules/branches/main \
    --jq '.[]|select(.type=="required_status_checks")|.parameters.required_status_checks[].context'
  ```

  So a red `CodeQL` check does not block the merge; it is a standing red mark
  on the PR. FK-005's `Test (Python 3.13)` timeout is the one that does block.
- **Suggested title**: `Decide whether to dismiss the four core.plot.basic CodeQL alerts that the allowlist cannot clear`

#### FC-005 — two `# lgtm[py/path-injection]` comments in the tree read like controls and are not

- **Severity**: P2 — not a vulnerability, but a comment that looks like a
  suppression and silently is not is worse than no comment: the next reader
  believes the alert was handled.
- **Found by**: fix-codeql, looking for a suppression idiom to follow.
- **Evidence**: `src/scistudio/api/routes/user_library.py:404` and
  `src/scistudio/api/routes/projects.py:358` each carry a
  `# lgtm[py/path-injection]` above a call the author judged safe. Both alerts
  are still open on `main`: alert **#247** at `user_library.py:408`, four lines
  below its comment and on the `tempfile.mkstemp(dir=str(resolved.parent))`
  call it was written to cover, and alert **#236** at `projects.py:370`.

  ```bash
  gh api "repos/jiazhenz026/SciStudio/code-scanning/alerts?state=open&per_page=100&ref=refs/heads/main" \
    --jq '.[]|select(.most_recent_instance.location.path|test("user_library|projects"))
          |"#\(.number) \(.most_recent_instance.location.path):\(.most_recent_instance.location.start_line)"'
  ```

- **What to do**: keep the prose — the containment reasoning in both is
  genuine and worth reading — and drop the `lgtm[...]` line, or replace it
  with a dismissal (FC-004's mechanism) so the claim and the alert state
  agree.
- **Why it is here and not done**: `api/routes/**` is outside this fix's write
  set, and editing those two files perturbs 19 open path-injection alerts for
  a comment change.
- **Suggested title**: `Remove or honour the two lgtm[py/path-injection] comments that suppress nothing`

#### FC-006 — `core.plot.basic`'s `payload.path` branch builds a URL that can never resolve

- **Severity**: P2 — a real dead path, found while tracing what
  `safeAssetUrl` actually has to accept. Not a security issue.
- **Found by**: fix-codeql.
- **Evidence**: when the payload carries no inline `src`, `bulkSource` builds
  `context.asset_base_url + "/" + encodeURIComponent(name)`.
  `asset_base_url` is `/api/panels/assets/core.plot.basic/`
  (`panels/descriptor.py:panel_asset_base_url`), and that route confines to
  `panel.directory` — the built-in panel's own folder
  (`api/routes/panels.py:218`). That folder holds `index.html` and
  `panel.json` and nothing else, which
  `tests/panels/test_builtin_panels.py::test_panel_directory_holds_nothing_but_its_own_two_files`
  asserts. A plot artifact is never in it, so the request is a guaranteed 404
  and the panel renders "No renderable plot artifact."
- **What it means in practice**: the only figure source that works today is
  the inline `data:` URI, which the provider produces only for artifacts at or
  under `PreviewLimits.max_bytes`. A plot above that bound shows nothing, and
  the panel reports it as an absent artifact rather than as one too large to
  inline.
- **Why it is here and not done**: fixing it means either a route that serves
  run artifacts to a panel or a spec decision about how a panel reaches bulk
  bytes — ADR-054 spec 1's question, not a security fix's.
- **Suggested title**: `A plot too large to inline renders as "no artifact" because the panel asset route cannot serve run artifacts`

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

#### FK-004 — the app-block file watcher reads liveness the same untrustworthy way

- **Severity**: P3 — different subsystem, and its failure mode is bounded.
- **Found by**: fix-kernel, sweeping for the same pattern after #2240.
- **Evidence**: `src/scistudio/blocks/app/watcher.py:191` `_handle_is_alive()`
  answers `poll() is None` for a plain `Popen`, which is exactly the reading
  that reported a dead explore kernel as healthy — on Linux `waitpid`
  withholds a killed multi-threaded process while its sibling threads exit,
  so `poll()` returns `None` about a corpse.
- **Why it is here and not done**: `src/scistudio/blocks/**` is outside this
  fix's write set, and the consequence there is milder — the docstring says a
  handle whose liveness is unknown is treated as alive "so the watcher relies
  on its timeout instead", so a false "alive" costs a delay rather than a
  wrong answer to the person. Worth aligning on the same pid-aware reading if
  the watcher ever grows a tighter deadline.
- **Suggested title**: `Give the app-block watcher the same pid-aware liveness
  reading as the explore kernel`

#### FK-005 — `Test (Python 3.13)` stalls out its whole 600 s parallel phase on the track branch

- **Severity**: P1 — it fails every CI run on `track/adr-054-integration` and
  on every branch cut from it, so no sub-PR of this assembly can go green.
- **Found by**: fix-kernel, while proving #2240's fix in CI.
- **Evidence**: it is **not** caused by the #2240 fix — the same job fails
  identically on the branch point. On `track/adr-054-integration` at
  `fa678c7ff` (run 33957302816, the exact base of PR #2262): 3.13's parallel
  phase printed 31 dots and was killed by `timeout 600` with exit 124, while
  3.11 finished the same phase with `9308 passed ... in 443.05s`. On PR
  #2262 at `151738a87` (run 33957753781): 3.13 printed 16 dots and was killed
  at exactly 600 s; 3.11 passed both phases in 11m48s. Runs 33955810545 and
  33957302816 on the track branch both fail 3.13 the same way.
- **The one asymmetry worth starting from**: `ci.yml` runs 3.13 **with
  coverage** and 3.11 with `--no-cov`. The same test set that completes in
  443 s uncovered does not get past a few dozen tests in 600 s covered, which
  looks like a stall rather than slowness. Nothing diagnosable survives,
  because the shell-level `timeout 600` hard-kills the phase before
  pytest-timeout's per-test 60 s kill can print a traceback — so the first
  step is probably to let pytest-timeout win (raise the shell timeout, or
  lower the per-test one) and get a stack out of it.
- **Why it is here and not done**: it is a CI-wide defect on the integration
  branch, not part of #2240's cluster, and fixing it would mean editing
  `.github/workflows/ci.yml`, which is outside this fix's write set.
- **Suggested title**: `Test (Python 3.13) stalls its parallel phase under
  coverage and is killed at the 600 s shell timeout`
- **Resolved by**: the `fix-citime` entries below, on
  `fix/2253-ci-test-budget`. Two corrections to the reading above, both from
  the raw job logs rather than the web log view: it is **not a stall** -- the
  killed runs print progress all the way to 96-97% (126 progress lines in run
  33952874542; the "31 dots" and "16 dots" counts are what the collapsed web
  log shows, not what the job printed) -- and the asymmetry called out here is
  exactly right: coverage is ~1.5x, and it is what pushed an honest 662 s
  parallel phase past a 600 s guard. The instinct to raise the shell timeout
  to get a diagnosis was also right, and is what produced the numbers in
  FT-001.

### fix-citime

Entries are prefixed `FT-` because `FC-` is already taken by `fix-codeql`.

#### FT-001 — `tests/qa/test_audit_full_audit.py` runs the whole ADR-042 audit against the real repository, twice, inside the unit suite

- **Severity**: P3 — cleanup with a real price, not a defect.
- **Found by**: fix-citime, measuring where the 3.13 parallel phase goes.
- **Evidence**: CI run 33960011315, `Test (Python 3.13 sysmon)`,
  `--durations=40` over 9313 tests:
  `test_full_audit_renders_human_readable_facts_summary` 11.63 s (3rd
  slowest) and `test_full_audit_reports_stale_generated_facts` 8.21 s (6th).
  Both call `full_audit.run(REPO_ROOT, ...)`, which is the same repository-wide
  work the dedicated `Full Audit` CI job already does in its own parallel job
  — frontmatter lint, fact drift, doc drift, developer docs, closure,
  signature drift, architecture drift and vulture, over the whole tree.
- **Why it is here and not done**: every cheap reduction costs coverage. The
  markdown test asserts that *every* child report appears in the rendered
  summary, so the children cannot be disabled; pointing `run()` at a
  synthetic tree would keep the assertions but stop them being about this
  repository. Which of those is acceptable is an owner call, not a fix
  agent's.
- **Suggested title**: `tests/qa/test_audit_full_audit.py duplicates the Full Audit job inside the unit suite`

#### FT-002 — `generate_facts` has no cache, so every caller pays a full griffe walk of the package

- **Severity**: P3.
- **Found by**: fix-citime.
- **Evidence**: before this fix, `tests/qa/test_generate_facts_cli.py` was the
  1st and 2nd slowest tests in the whole parallel phase — 30.52 s and 22.57 s
  on CI (run 33960011315) — because two tests made **four** CLI invocations
  and each one walks `src/scistudio` with griffe from scratch. Locally a
  single `--write` is 13 s and a single `--check` 17-19 s. This PR shares one
  `--write` across the module and takes it to three invocations; the
  remaining three are irreducible from the test side because `--check`
  regenerates by definition.
- **Why it is here and not done**: the cache would belong in
  `src/scistudio/qa/audit/facts.py`, keyed on source file hashes, and
  `src/scistudio/**` is outside this fix's write set. It would also speed up
  the `Full Audit` job and every local `gate_record check`.
- **Suggested title**: `cache generate_facts so the griffe walk is paid once per source state`

#### FT-003 — raising the xdist worker count nearly halves the parallel phase, and crashed a worker once out of two tries

- **Severity**: P2 — a real, large speedup that is not safe to take on the
  evidence available.
- **Found by**: fix-citime, CI run 33960875235 (three legs, same commit, same
  runner class, coverage on, `COVERAGE_CORE=sysmon`).
- **Evidence**:

  | workers | parallel phase | result |
  |---|---|---|
  | `-n auto` (4 on ubuntu-latest) | 534.33 s | clean, coverage 88% |
  | `-n 6` | 383.99 s | **`[gw0] node down: Not properly terminated`** while running `tests/qa/test_generate_facts_cli.py::test_generate_facts_write_and_check_round_trip`; coverage collapsed to 55% because the dead worker returned no data |
  | `-n 8` | 310.65 s | clean, coverage 88% |

  A 42% cut in wall clock for a one-token change is the largest single lever
  found anywhere in this investigation — the suite is I/O-bound enough that
  4 workers leave the runner idle. But a crashed worker is worse than a slow
  job: it fails a random PR for no reason a reader can act on, and it
  silently destroys that worker's coverage data, which on the serial phase
  would trip `--cov-fail-under=70` and blame the wrong change.
- **Why it is here and not done**: one crash in two oversubscribed runs is
  not enough to characterise. Taking it needs a handful of repeat runs at
  `-n 8` to see whether the crash recurs, and a look at whether it is memory
  (the griffe walk under N workers) or something in that test. Worth doing —
  it would take the whole `Test` job under five minutes — but it is a
  deliberate reliability trade the owner should make, not one to land while
  he is asleep.
- **Suggested title**: `measure -n 8 for the CI parallel phase: 42% faster, one unexplained worker crash`

#### FT-004 — the `Test` matrix legs run different workloads and nothing said so

- **Severity**: P3 — fixed by this PR's comment, recorded because it cost
  three agents a diagnosis.
- **Found by**: fix-citime; independently by fix-kernel (FK-005).
- **Evidence**: `Test (Python 3.11)` runs `--no-cov`; `Test (Python 3.13)`
  measures coverage. On run 33960011315 that is 435.70 s versus 662.34 s for
  the identical test set. Every reading of the failure started from "3.13 is
  broken" because the workflow's comment described the two-phase split and
  the coverage split, but not that the 3.13 leg therefore carries ~1.5x the
  runtime of the leg people compare it against.
- **Why it matters beyond the comment**: the same asymmetry means the 3.11
  leg is not a usable early-warning signal for the 3.13 leg's budget. If the
  owner wants one, the cheapest version is to keep printing `--durations`
  (this PR does) and watch the 3.13 parallel total.
- **Suggested title**: `document, or remove, the coverage asymmetry between the two Test matrix legs`

### fix-gate

The repair of M-005's link 3 — the gate counting a timed-out check as a passing
one — on `fix/2253-gate-timeout-not-satisfied`. **F-B4-8** and **F-A1-009** are
the same defect found twice and are fixed by this branch; the entries are marked
in place so neither becomes an issue.

#### FG-000 — What the fix changed, for the record

Not a follow-up. Written down so a later reader can tell what this branch did
from what it deliberately left alone.

- A `subprocess.TimeoutExpired` is now `status="timeout"` with the budget in its
  summary, not `status="unknown"` / `"execution error: TimeoutExpired"`. The
  `unknown` branch keeps its own meaning for a check that could not be launched.
- Only a `pass` discharges a check obligation. `skipped`, `timeout` and
  `unknown` are unsatisfied in `pre-pr` / `ci`, recorded-not-blocking in the WIP
  modes — the posture `skipped` already had.
- `SCISTUDIO_GATE_CHECK_TIMEOUT` (seconds, default `600`, unusable values
  ignored) makes the budget configurable. Named after `SCISTUDIO_GATE_BASE`.
- `check` and `finalize` now call one predicate,
  `checks.event_discharges_obligation`. They diverged because each carried its
  own idea of what counted: the executing path treated everything that was not
  `fail` as satisfied, the evidence-reuse path required `pass`.
- **Nothing was made easier to satisfy.** No command was shortened, no test
  skipped, no scope narrowed. A run that legitimately passed before still
  passes; runs that falsely passed now correctly fail.
- **No existing ledger event was rewritten or re-evaluated.** The change applies
  to events recorded from here on.

#### FG-001 — `run_python_tests` skips the serial phase when the parallel phase fails

- **Severity**: P2 — a red test in the serial phase goes unexecuted and
  unreported, which is worse than a red test.
- **Found by**: fix-gate, reading M-005's chain. S5-B4 named it first, in a
  closing line of its own entry, and it was never registered on its own.
- **Evidence**: `src/scistudio/qa/testing/run_python_tests.py:67-69` —
  `rc = _run(parallel)` then `if rc not in (0, _NO_TESTS_COLLECTED): return rc`.
  The serial phase at line 71 is never reached. There is no dependency between
  the phases; they are split so PTY/subprocess tests cannot crash an xdist
  worker. Link 2 of M-005's chain is entirely this, and it is what hid
  `test_a_branch_switch_kills_the_real_kernel_process`.
- **Why it is not fixed here**: `src/scistudio/qa/testing/**` is outside this
  branch's write set, and the change wants its own reasoning about exit-code
  aggregation across two phases rather than a drive-by edit inside a governance
  fix.
- **Suggested title**: `run_python_tests must run the serial phase even when the
  parallel phase failed`

#### FG-002 — The gate's timeout and CI's `timeout 600` are two different walls with one number

- **Severity**: P3 — documentation and diagnosis, not behaviour.
- **Found by**: fix-gate, and the confusion is already in this file: FK-005 and
  the first draft of M-005's link 3 both say "`timeout 600`" for what are two
  unrelated mechanisms.
- **The two**: the gate CLI's `subprocess.run(timeout=...)` around a whole check
  (now `SCISTUDIO_GATE_CHECK_TIMEOUT`, this branch's), and `ci.yml`'s shell
  `timeout 600` around each pytest phase inside the CI job (FK-005's, a
  different agent's). They fire in different processes, produce different
  evidence, and want different fixes. Raising one does nothing for the other.
- **Why it is worth recording**: FK-005's diagnosis depends on the distinction —
  its point is that the shell wall hard-kills the phase before pytest-timeout
  can print a traceback, which is a property of the CI wall specifically. The
  gate CLI's docs now say which wall they mean; `ci.yml` says nothing about
  either.
- **Suggested title**: `chore(ci): name the pytest phase timeout so it is not
  confused with the gate CLI's per-check budget`

#### FG-003 — The `timeout` status is a ledger vocabulary addition, and old readers do not know it

- **Severity**: P3 — no known break; recorded because it is a schema change to
  the file ADR-042 Addendum 6 makes the single source of truth.
- **Found by**: fix-gate, making the change.
- **Evidence**: `CheckEvent.status` gains `"timeout"`. Ledgers written by this
  code and read by an older checkout would fail pydantic validation on that
  member. Nothing outside `gate_record` reads the field — the whole vocabulary
  is confined to `checks.py` and `evaluator.py`, and the frontend and CI never
  see it — so the blast radius is one repository at two different commits.
- **Why it is not a problem in practice**: CI runs the branch's own code against
  the branch's own ledger. It would only bite someone checking out an older
  commit to read a newer record.
- **Suggested title**: `chore(qa): gate ledger readers should tolerate an
  unknown CheckEvent status rather than refuse the record`

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
