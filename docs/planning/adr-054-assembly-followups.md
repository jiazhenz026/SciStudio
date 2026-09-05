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
