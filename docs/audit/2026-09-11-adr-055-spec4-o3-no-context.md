# Audit: Workflow Run Lifetime And Lineage Terminal State (no-context)

- Date: 2026-09-11
- Persona: `audit_reviewer`, **no-context** mode
- Branch / worktree: `audit/2327-no-context` @
  `C:/Users/jiazh/workspace/SciStudio/.worktrees/audit-2327-no-context`
- Code audited: `origin/fix/2327-run-lifetime` at
  `cf2cffa83f004b2b3b2dbb93bc34b4e921116d3a`, diffed against its merge base
  with `origin/main`, `e9dcd01aa2ef8dbdddfdadc0d5839a53a664a13d`
- Judged against: `docs/adr/ADR-055.md` (§7, §8.1), `docs/adr/ADR-038.md`
  (§3.1 `runs.status`, `governs`), `CHANGELOG.md` `[Unreleased]`, and the
  module docstrings of the audited code
- Code read: `src/scistudio/api/ws.py`, `src/scistudio/api/app.py` (lifespan),
  `src/scistudio/api/runtime/{__init__,_run_lifetime,_runs,_projects}.py`,
  `src/scistudio/core/lineage/{store,recorder,retention}.py`,
  `src/scistudio/engine/scheduler/{__init__,_dispatch}.py`,
  `src/scistudio/api/routes/projects.py`, the frontend project-open callers,
  and `desktop/main.js` `stopRuntime`

## 1. Change Summary

This report is the only file this change adds. It audits how a workflow run
ends and how its lineage `runs` row reaches a terminal status, on a branch
that removes the `/ws` last-disconnect cancel. It does not use the issue, PR,
checklist, dispatch, or commit messages. One `Grep` over the repository
returned a single line of the implementation's gate ledger
(`.workflow/records/2327-fix-2327-run-lifetime.json`). That line was not used
as evidence, and the ledger was not otherwise read.

**Recommendation: block.** The disconnect cancel is gone, and graceful
shutdown, start failure, and worker death work as documented. But one common
path, reopening the project while a run is live, leaves a finished run's row
`running` for the rest of the backend session. The next open then records
that completed run as `failed` (P1). The flow the CHANGELOG advertises,
"reopen the page and the run is still there", walks straight into it.

## 2. Findings

### P1-1. Reopening the active project mid-run strands the row as `running`, and the next open records a completed run as `failed`

Evidence, code:

- `GET /api/projects/{id}` always calls `runtime.open_project`
  (`src/scistudio/api/routes/projects.py:385-398`), which always calls
  `_init_lineage_store` (`_projects.py:455`). `_init_lineage_store` closes the
  prior `LineageStore` even when it is the same project (`_projects.py:185-191`).
- `LineageStore.close()` sets `_closed`, and every later call raises
  `ProgrammingError("LineageStore is closed")`
  (`core/lineage/store.py:395-399, 415-427`).
- The live run's `LineageRecorder` keeps the closed store. Its
  `finalize_run` swallows the error (`core/lineage/recorder.py:167-178`).
  `_on_done` then calls `release_run` in `finally` (`_runs.py:562-568`), which
  deletes the owner marker (`_run_lifetime.py:169-179`) even though the row was
  never finalised.
- Reconciliation runs only when a store is opened
  (`_projects.py:203-206`). A row that is `running`, not live, and has no
  marker is finalised as `failed` (`_run_lifetime.py:390-409`). The logged
  reason is "no process has claimed it (it has no owner marker)"
  (`_run_lifetime.py:309-310`), which is wrong for this case.

Evidence, frontend callers of that route (`frontend/src/lib/api/projects.ts:33-36`):
Open Recent and the open dialog (`App.tsx:413, 520, 536`,
`useProjectActions.ts:182, 235`), tutorial open (`useLearningCenter.ts:143`),
and the save retry after a 409 (`useWorkflowSync.ts:128`). After a browser is
closed and reopened, the user returns to a project through one of these.

Evidence, probe (throwaway, not committed): start a run with a gated runner,
call `GET /api/projects/{active id}` while it is in flight, release the run,
wait for completion:

```
PROBE1 block states: {'load': DONE, 'transform': DONE, 'final': DONE}
PROBE1 row after completion: running degraded= 0
PROBE1 marker exists: False live: False
PROBE1 runs_in_progress: ['6f362d25d39940b78bcdea752589b821']
PROBE1 /api/runs statuses: ['running']
PROBE1 row after the NEXT open: failed
```

Consequences:

- Run history shows `running` for a finished run for the rest of the session.
- `runs_in_progress()` is non-empty, so artifact retention refuses to sweep
  (`core/lineage/retention.py:189-195`) until the project is opened again.
- The terminal status finally written is `failed` for a run that completed.
  The row's `provenance_degraded` stays `0`, although every later
  `block_executions` write went to the closed store.
- Switching to another project mid-run has the same root cause, with the
  row stranded in the other project's database.

Test gap: `test_a_started_run_is_claimed_before_its_row_is_visible`
(`tests/api/test_runtime_run_lifetime.py:406-423`) reopens the project mid-run
and asserts the row is still `running`, but never checks the row after the run
completes. The `this_process_not_live` case (`:315-326`) says it models "a run
this process started whose store was closed under it". But it seeds a marker
that `release_run` always deletes in that situation, so the real case is only
covered as `no_marker`, and never for a run that completed.

Root-cause note: closing the store on reopen predates this branch. The branch
makes the scenario the normal path, because runs now outlive the browser, and
adds the step that turns the stranded row into `failed`.

Options, for the owner to choose: keep the same store object when the
reopened path equals the active project; have finalisation write through a
store reopened by path when the recorder's store is closed; or keep the owner
marker when finalisation did not succeed, and let reconciliation tell
"finished but unrecorded" apart from "interrupted".

### P2-1. The documented shutdown behavior does not hold on the desktop stop path

`CHANGELOG.md` (the #2327 entry) says that on shutdown the backend "cancels
live runs and waits up to 10 seconds ... It writes `cancelled` itself for any
run that has not stopped by then." The lifespan does this
(`app.py:233-237`, `_run_lifetime.py:212-253`). A graceful shutdown with a real
sleeping worker finished in 0.14 s, with the row `cancelled` and the worker
gone (probe PROBE2).

But `desktop/main.js` `stopRuntime` (`:1565-1598`, called from `before-quit`
at `:2402-2406`) does this:

- On Windows it runs `taskkill /pid <pid> /T /F` at once, so the lifespan never
  runs.
- On POSIX it sends SIGTERM, then SIGKILL after `STOP_ESCALATION_MS = 5000`
  (`:65-67`), which is shorter than the 10 s bound plus the 5 s
  `terminate_all` grace.

A desktop quit mid-run is therefore repaired only at the next project open,
as `failed`. The logged reason, "most likely a crash or forced kill"
(`_run_lifetime.py:316`), describes a normal quit as a crash. The row does not
stay `running` forever, but the documented status and wording are wrong for
the most common way the packaged app stops. Either the CHANGELOG and the
docstring should say shutdown is best-effort and bounded by the host's kill
policy, or the stop path and the bound should be aligned.

### P2-2. The new run-lifetime contract has no governing ADR or spec update

- ADR-038 `governs` `src/scistudio/api/runtime/`,
  `scistudio.api.runtime`, and `ApiRuntime.start_workflow`
  (`docs/adr/ADR-038.md:14-33`). §3.1 defines
  `status ∈ running | completed | failed | cancelled` but says nothing about
  who writes a terminal status when a process ends, gets killed, or crashes.
- ADR-055 `governs` `src/scistudio/api/app.py` and
  `src/scistudio/api/runtime/_projects.py`, both changed here. Its §7 and §8.1
  state the browser rule ("Closing the connection window or browser does not
  stop an active analysis"; "Browser disconnection ... do[es] not terminate
  active analyses"), but not the lineage consequence.
- The branch adds new per-project storage
  (`<project>/.scistudio/run-owners/<run_id>.json`), a status policy
  (interrupted gives `failed`, shutdown straggler gives `cancelled`,
  `finished_at` = detection time), a cross-process ownership rule (pid,
  create time, host), and a new `ApiRuntime.shutdown_workflow_runs` member.
  These are recorded only in the CHANGELOG and the module docstring.
  `AGENTS.md` §3.4 asks for a spec update when runtime behavior or storage
  changes.

ADR-038 is `agent_editable: false`, so the fix is an owner-authored addendum or
spec, or an explicit N/A decision.

### P3-1. Wording drift

- `ws.py:170-172` and the test module say "startup reconciliation", but
  reconciliation runs when a project's lineage store opens
  (`_projects.py:203-206`), not at backend startup. The module docstring and
  the CHANGELOG say "when a project is opened", which is correct.
- The CHANGELOG says the backend "waits up to 10 seconds for each run's
  history". The code applies one 10 s bound to all runs together
  (`asyncio.wait(pending, timeout=bound)`, `_run_lifetime.py:230`).

### P3-2. The "still there on the canvas" claim is not verified

The CHANGELOG says a reopened page shows the run "in Run history and on the
canvas". The `/ws` handler sends no state snapshot on connect (`ws.py:180-195`),
and no workflow run-state GET route exists (`routes/workflows.py` exposes
cancel POSTs only). The new test checks `/api/runs` and later events, not the
canvas state of the reconnected client
(`test_gui_disconnect_keeps_run_going_and_reconnect_still_sees_it`). The claim
is either unimplemented or implemented in the frontend without a test here.

### P3-3. A shutdown straggler's `cancelled` can be overwritten

`shutdown_workflow_runs` finalises a straggler as `cancelled` and releases it
(`_run_lifetime.py:237-252`). The task's `_on_done` stays attached, and
`LineageStore.finalize_run` has no `WHERE status = 'running'` guard
(`store.py:486-495`). If the task ends before the loop closes (for example
after `terminate_all` kills its worker), the derived status overwrites
`cancelled`. The row stays terminal, so this matters only for
reproducibility of the recorded reason.

### P3-4. Ownership edge cases

- If the marker cannot be written (`OSError`), the run proceeds without one
  (`_run_lifetime.py:149-156`). Another backend that opens the project would
  then finalise the live run as `failed`, and the owner's own finalisation
  later overwrites that. Only the docstring records this.
- Liveness is keyed on `socket.gethostname()` (`_run_lifetime.py:285-287`).
  Two hosts with the same hostname sharing a project directory (for example
  containers with a default hostname on network storage) would judge each
  other's PIDs locally.
- A crashed backend left as an unreaped zombie still answers
  `psutil.Process(pid).create_time()`, so its runs stay `running` until it
  is reaped.

### P3-5. Headless runs blocked on user interaction now wait indefinitely

Before this branch, the disconnect cancel also ended runs parked on an
interactive block (ADR-051) or an engine-opened AI Block PTY tab
(`ws.py` docstring, ADR-035 §3.10) once the browser left. Now such a run holds
its row `running` and blocks retention until a client returns or someone
cancels it. That is consistent with ADR-055 §7, but no document states it.

### P3-6. A pre-existing path to a released-but-running row

In `_finalize_lineage_run` (`_runs.py:227-249`), `status` is assigned inside a
`try`. If `_derive_lineage_run_status` raises, the later
`if status == "completed"` raises `UnboundLocalError`. `_on_done`'s `finally`
then releases the run with its row still `running` until the next open. This
is unlikely, and it predates the branch.

## 3. What Holds

- **Browser disconnect.** The cancel machinery is removed, not disabled
  (`ws.py` diff; `test_ws_module_no_longer_tracks_gui_clients_for_cancellation`).
  A run outlives the old 2 s grace against the real endpoint. This matches
  ADR-055 §7 and §8.1.
- **Graceful lifespan shutdown.** Mid-run shutdown writes `cancelled`, removes
  the marker, and kills the worker. A run that ignores cancellation is forced
  to `cancelled` after the bound (tests plus PROBE2).
- **Kill or crash, then the next open.** Dead-PID, reused-PID (create time),
  missing, and unreadable markers reconcile to `failed`, with the reason in the
  backend log and in `run-<id>.log`. Live-elsewhere, other-host, and
  live-in-this-process runs are left alone.
- **Worker death.** A killed worker gives the block `ERROR` and the run
  `failed` (test).
- **Failure between row insert and task start.** `abandon_run` covers scheduler
  construction and `create_task` (`_runs.py:508-556`; test).
- **Ordering.** The marker is written before the row
  (`_runs.py:134-139`), so a just-started run is never seen as orphaned. The
  in-process `_LOCK` orders release against reconciliation's check-then-write.
- **Other surfaces.** `.scistudio/` is git-ignored by the default template
  (`core/versioning/gitignore_template.py:30`) and ignored by the workflow
  watcher (`routes/workflow_watcher.py:103`), so markers do not dirty
  pre-run auto-commits or raise file events. No generated API reference
  covers `ApiRuntime`, so nothing generated was hand-edited.

## 4. Checks Run

| Check | Result |
|---|---|
| `pytest tests/api/test_runtime_run_lifetime.py tests/api/test_ws.py tests/api/test_runtime_import_surface.py -q --no-cov` | 26 passed |
| 14 further test files touching these modules (`test_runtime_lineage_finalize_status`, `test_runtime_bounded_registries`, `test_open_project_degraded_modes`, `test_app`, `test_identity_seam`, MCP tool and bridge suites, ...) | 383 passed, 6 skipped (platform), exit 0 |
| `ruff check` on the changed Python files | pass |
| Throwaway probe PROBE1: reopen the active project mid-run | reproduces P1-1 |
| Throwaway probe PROBE2: graceful shutdown with a real 120 s worker | 0.14 s, `cancelled`, worker gone, marker removed |
| Sentrux | N/A (MCP not available in this runtime) |

The coverage gate reports 33% when only the three required files run. That is
the repository-wide threshold applied to a narrow selection, not a finding.

## 5. Re-audit (head 4d02f0423)

- Code re-audited: `origin/fix/2327-run-lifetime` at
  `4d02f042337a9d8b857f62509fbdc83b864c02ae`, compared file by file with the
  first audit's head `cf2cffa83`. The audit branch was fast-forwarded to it.
- Same no-context rules. The branch now also contains a with-context audit
  report and the implementation ledger; neither was read.
- Surface added for this round: `desktop/main.js` (backend stop sequence) and
  `desktop/test/**`, together with the new `src/scistudio/api/runtime/_stop_request.py`
  and `docs/specs/adr-055-local-background-runtime.md` §4.6, FR-015 and FR-016.

**Updated recommendation: block.** Every earlier finding is fixed or
documented, and P1-1 is fixed and verified. But the new Windows stop request
(N1, P1) makes every git subprocess of the Windows desktop backend hang until
the app quits, which freezes project creation, project open, and run start. A
second new finding (N2, P2) is that the graceful stop never reaches the
lifespan while a page is connected, so the desktop's graceful path does not
deliver what the CHANGELOG and Spec 3 FR-015 claim.

### 5.1 Verdicts On The First Audit's Findings

| Finding | Verdict | Evidence |
|---|---|---|
| P1-1: reopen or switch mid-run strands the row, then records `failed` | **Fixed** | `_init_lineage_store` keeps the store when the database path is unchanged and retires it on a switch (`_projects.py:186-213`, `_run_lifetime.py:463-477`). `release_run` removes the marker only once the row is terminal, retries through a store opened by path, and otherwise annotates the marker (`_run_lifetime.py:357-460`). PROBE1 rerun: row `completed`, `runs_in_progress()` empty, still `completed` after the next open. New probe PROBE3 (switch A to B mid-run): A's row `completed` with all three `block_executions` rows, nothing written to B, A's retired store closed after the run, marker removed. Branch tests: `test_reopening_the_project_mid_run_keeps_its_history`, `test_switching_projects_mid_run_keeps_the_run_and_its_history`, `test_release_rewrites_the_outcome_through_a_reopened_store`, `test_an_unrecordable_outcome_waits_in_the_marker_for_the_next_open`. |
| P2-1: the documented shutdown does not hold on the desktop stop path | **Partially fixed** | `stopRuntime` now requests a graceful stop (SIGTERM on POSIX, closing stdin on Windows) and force-kills only after `STOP_ESCALATION_MS = 15000`. Quitting waits up to `RELAUNCH_STOP_TIMEOUT_MS = 20000` (`desktop/main.js:65-77, 1599-1639, 2461-2493`). On a real idle Windows backend, closing stdin reached "Application shutdown complete" in under 1 s. But on Windows the request causes N1, and on every platform N2 stops it from reaching the lifespan in the common case. |
| P2-2: no governing ADR or spec update | **Fixed** | Spec 3 §4.6 documents the store lifetime, owner markers, statuses, reconciliation rules, machine id, known limits, and runs waiting on a person. FR-015 and FR-016 were added and the new files and tests are listed. Residual P3: ADR-038, which `governs` `src/scistudio/api/runtime/`, does not point to §4.6. |
| P3-1: wording drift | **Fixed** | `ws.py:167-172` and the `test_ws.py` docstring say "reconciliation when a project is opened". The CHANGELOG says "up to 10 seconds in total". The phrase "startup reconciliation" now occurs only in this report. |
| P3-2: the "still there on the canvas" claim | **Fixed** | Claim withdrawn. The CHANGELOG and §4.6 now say a reconnecting page is not sent the states it missed. |
| P3-3: a shutdown straggler's `cancelled` can be overwritten | **Fixed** | `_FORCED_RUN_IDS` and `consume_forced` stop the late done-callback from writing again (`_run_lifetime.py:497-505, 551-557`; `_runs.py:262-274`). Test: `test_shutdown_finalises_a_run_that_ignores_cancellation_and_keeps_that_outcome`. |
| P3-4: ownership edge cases | **Fixed / documented** | A marker write failure now runs the workflow without a lineage row (`_runs.py:138-156`; test `test_a_run_whose_marker_cannot_be_written_runs_without_lineage`). A machine id replaces the hostname (`_run_lifetime.py:175-218`). Zombies count as dead (`test_open_reconciles_a_run_whose_owner_is_a_zombie`). Containers sharing a machine id are a documented known limit. A foreign-owned row older than 24 h is logged. By design, rows owned by another machine, or whose marker is unreadable, stay `running`, with a warning. |
| P3-5: headless runs waiting on user input | **Fixed (documented)** | Spec 3 §4.6 "Runs waiting on a person". |
| P3-6: `UnboundLocalError` in `_finalize_lineage_run` | **Fixed** | `status` defaults to `failed` (`_runs.py:253-261`). Test: `test_lineage_finalization_records_failed_when_the_status_cannot_be_derived`. |

### 5.2 New Findings

#### N1 (P1). The Windows stop-request watcher hangs every subprocess that inherits stdin, including git

On Windows the desktop spawns the backend with a stdin pipe and
`SCISTUDIO_STOP_ON_STDIN_EOF=1` (`desktop/main.js:978-982, 1127-1141`). The
backend then starts a daemon thread that blocks in `sys.stdin.buffer.read`
(`_stop_request.py:50-79`, started from the lifespan at `app.py:76-80`). While
that read is pending, starting any child process that inherits the backend's
stdin blocks until the read returns, which happens only when the shell closes
stdin.

The git wrapper passes no `stdin` (`core/versioning/git_binary.py:190-200`), so
every git call inherits it. That includes `is_repository`
(`git_engine.py:198-215`) on project create and open, and `start_workflow`'s
pre-run auto-commit.

Evidence, all throwaway probes:

- Controlled real-uvicorn probe, same redirected home, timing
  `POST /api/projects/`:

  | Backend stdin | Result |
  |---|---|
  | null device (old `ignore`) | 200 in 0.38 s |
  | open pipe, variable unset | 200 in 0.35 s |
  | open pipe plus `SCISTUDIO_STOP_ON_STDIN_EOF=1` | still pending after 60 s |

- Backend log of a stalled creation: "Using system git" at 09:06:54, nothing
  for 240 s, then "the launching process closed stdin", then the git repo
  initialised and the request completed (`POST /api/projects/ 200 240414.1ms`).
  `create_project` and `get_project` are `async def`, so the event loop, and
  with it `/ws`, froze for the whole wait.
- Minimal repro, with the child spawned exactly as `spawnRuntimeCandidate`
  does (Node, `stdio: ["pipe","pipe","pipe"]`) and also from Python:

  ```
  none     stdin=DEVNULL    git --version returned in 0.01s
  watcher  inherited-stdin  git --version HUNG >15s (killed by timeout)
  watcher  stdin=DEVNULL    git --version returned in 0.01s
  ```

- The same repro shows a second effect. A process that exits while the
  watcher is still blocked aborts with `Fatal Python error:
  _enter_buffered_busy: could not acquire lock for <_io.BufferedReader
  name='<stdin>'> at interpreter shutdown`.

Why the tests miss it: `tests/api/test_runtime_stop_request.py` exercises the
watcher only in processes that start no children. The desktop harness uses a
Node fake backend (`desktop/test/harness/fake-backend.js`), which never runs
the Python watcher.

Options, for the owner to choose:

- Spawn every backend child with an explicit `stdin=subprocess.DEVNULL`
  (git, pip, `EnvironmentSnapshot`, command tools). This is broad, and new
  call sites can regress.
- Carry the stop request on a channel that is not the standard input handle,
  for example a non-inheritable pipe handle passed by number, a named event,
  or an authenticated loopback request.
- Keep stdin but have the watcher wait on it in a way that does not hold a
  synchronous read on the inherited handle.

#### N2 (P2). The graceful stop never reaches the lifespan while a page is connected

uvicorn 0.48 runs with `timeout_graceful_shutdown=None` (`cli/main.py:425,
547`). Before it sends the lifespan shutdown, it waits without a bound for open
connections and handler tasks (`uvicorn/server.py:271-309`). Two connections
never end on their own:

- The log SSE stream (`api/sse.py:21-43`) sends keepalives until the client
  disconnects.
- The `/ws` handler (`ws.py:286-293`) runs `gather(_inbound_loop(),
  _outbound_loop())`. After the client disconnects, the inbound loop returns,
  but the outbound loop keeps waiting on `queue.get()`.

The frontend holds `/ws` open whenever a project is open, and the SSE stream
whenever a workflow is open (`App.tsx:238-244`, `hooks/useSSE.ts:36-87`).
`hideWindowsForQuit` only hides the windows, so both connections stay open.

Evidence: a real-uvicorn probe, mid-run, triggering the same graceful shutdown
through uvicorn's CTRL_BREAK handler, because N1 blocks the stdin trigger:

| Clients | Result |
|---|---|
| none | exited in 0.24 s, "Application shutdown complete" |
| log SSE stream open | "Waiting for connections to close", still running after 25 s |
| `/ws` client open | "Waiting for background tasks to complete", still running after 25 s |

In those runs CTRL_BREAK also reached the block worker in the same process
group, so their `failed` statuses are artifacts of the trigger and are not
cited.

Consequence: in the common desktop case the backend is force-killed at 15 s,
`shutdown_workflow_runs` never runs, and live runs are recorded `failed` at
the next open, which is the P2-1 outcome. Every quit and every relaunch with a
project open also waits the full 15 s.

This contradicts the CHANGELOG ("The desktop app now asks the backend to shut
down this way when it quits") and Spec 3 §4.6 ("The desktop stop sequence ...
leaves room for this before it force-kills"). The desktop tests do not cover
it: the fake backend exits by itself on SIGTERM or EOF.

#### N3 (P3). Deleting the active project mid-run resurrects it

`delete_project` closes the store directly (`_projects.py:683-693`), without
`retire_store`, and does not stop the project's runs. The run keeps writing
into the deleted directory, and the new `_ensure_terminal_row` fallback
creates a fresh `.scistudio/lineage.db` there.

Probe PROBE4: `DELETE` returned 204, yet after the run ended the directory held
`.scistudio/lineage.db`, `logs/run-<id>.log`, a pause checkpoint, and
`data/zarr/...`. The run outputs are pre-existing behavior; the recreated
lineage database is new.

#### N4 (P3). An unrelated change rides on this branch

The MCP pointer hardening is unrelated to run lifetime:
`_write_private_pointer` (`_projects.py:527-563`),
`tests/api/test_runtime_mcp_pointer.py`, and a second CHANGELOG entry tagged
`[#2327]` that says "Found by the no-context audit of #2329". `AGENTS.md` §3.2
asks for focused PRs. Owner approval, if any, is not visible in no-context
mode.

#### N5 (P3). stdin is now a never-closed pipe on every platform

`spawnRuntimeCandidate` sets `stdio: ["pipe", ...]` unconditionally, while the
stop-request variable is set only on Windows. On macOS and Linux, a backend
child that inherits stdin and reads it now blocks instead of seeing
end-of-file. Git runs with `GIT_TERMINAL_PROMPT=0`, and block workers get their
own pipe (`engine/runners/local.py:317-325`), so no concrete case was found.

### 5.3 Checks Run

| Check | Result |
|---|---|
| `pytest` on the lifetime, ws, import-surface, stop-request, finalize-status, MCP-pointer, bounded-registry, degraded-open, app, identity-seam and known-project suites (`--no-cov`) | 175 passed, 2 skipped, exit 0 |
| `node --test desktop/test/bootstrap.test.js desktop/test/main-orchestration.test.js` (Node 24.14, Windows) | exit 0, including the three #2327 cases |
| PROBE1 rerun (reopen mid-run) | fixed: `completed`, stays `completed` after the next open |
| PROBE2 rerun (in-process graceful shutdown, real worker) | 0.11 s, `cancelled`, worker gone, marker removed |
| PROBE3 (switch A to B mid-run) | A `completed` with all block rows; B untouched; retired store closed |
| PROBE4 (delete mid-run) | N3 |
| Real-uvicorn stdin probes (null device, open pipe, open pipe plus variable) | N1 |
| Node- and Python-spawned watcher repro | N1 |
| Real-uvicorn mid-run shutdown with no client, SSE, `/ws` | N2 |
| Sentrux | N/A (MCP not available in this runtime) |

## 6. Final Re-audit (head de11b2848)

- Code: `origin/fix/2327-run-lifetime` at
  `de11b2848a5641b5ae5e0b108d4ef30d326733b1`. The audit branch was
  fast-forwarded to it. The head now contains `origin/main`, which brings a
  repository-wide docstring rewrite (332 files). Only the run-lifetime and
  backend-stop surfaces were audited.
- Same no-context rules. Neither the with-context report nor the
  implementation ledger was read.

**Final recommendation: pass.** The P1 (N1) and the P2 (N2) are fixed and
verified against a real Windows backend. P1-1 and every first-round finding
remain fixed. The open items are all P3: N3 partial, N4 bundled scope, and the
ADR-038 pointer. `AGENTS.md` §3.6 requires any of them that is deferred to be
tracked.

| Finding | Verdict | Evidence |
|---|---|---|
| N1 (P1): the stop watcher hangs children that inherit stdin | **Fixed** | `detach_standard_input` moves the pipe to a private, non-inheritable descriptor, and points descriptor 0 and the Win32 `STD_INPUT_HANDLE` at the null device. The watcher reads the private descriptor with `os.read` (`_stop_request.py:61-166`). My repro, spawned from Node as the desktop does and also from Python: under the watcher, `git --version` returns in 0.01 s and a grandchild reading stdin gets end-of-file in 0.03-0.04 s. No "Fatal Python error" at exit. Branch tests: `test_children_do_not_inherit_the_stop_request_pipe_and_the_backend_exits_cleanly`, and `test_runtime_backend_stop.py`, which runs the real `gui --bundled` backend with a git pre-run commit. Both pass on this Windows host. |
| N2 (P2): the graceful stop never reaches the lifespan while a page is connected | **Fixed** | `arm_stop_notice` chains onto uvicorn's SIGTERM, SIGINT and SIGBREAK handlers. Each stop signal first calls `begin_shutdown`, which closes the log broadcaster (`sse.py` breaks on `END`) and kills AI terminal sessions (`app.py:80-87`). The `/ws` handler now returns when either loop ends (`ws.py:290-306`). Real-uvicorn probe, triggered by the desktop's own stdin-EOF request mid-run: no client 0.30 s, log stream open 0.35 s, `/ws` open 0.31 s. All rows are `cancelled` and all markers removed. The force-kill is now 25 s and the wait 30 s, covering a shutdown budget of at most 20 s. After a requested stop the backend exits with code 3 (Windows' default SIGTERM action). `trackRuntime` classifies that exit by `stopRequested` and `isQuitting`, not by the code (`desktop/main.js:1986-2012`). |
| N3 (P3): deleting the active project mid-run resurrects it | **Partially fixed** | The lifetime retry no longer recreates the database (`_run_lifetime.py:375-383`, `_write_marker(create_parent=False)`; test `test_a_run_whose_project_was_deleted_does_not_recreate_it`). But probe PROBE5 (delete, then the run completes) still finds a fresh, empty `lineage.db` (zero `runs` rows) in the deleted project. The artifact-retention sweep creates it: this branch now points `_schedule_artifact_retention` at the run's own project, and `_reclaim_artifacts_blocking` opens `LineageStore` on that path. Before, it used the active project, which is `None` after the delete. With `SCISTUDIO_ARTIFACT_RETENTION=0`, no database appears. Retention refuses to sweep an empty database, so no data is lost. The branch test calls `release_run` directly and does not reach this path. The run's own writes into the deleted project (logs, checkpoint, `data/zarr`) predate the branch. |
| N4 (P3): an unrelated change rides on the branch | **Documented, still bundled** | The CHANGELOG entry is now tagged `[#2333]` and says it ships with #2327 because both touch `_projects.py`. Whether that is acceptable is an owner decision. |
| N5 (P3): stdin is a never-closed pipe on every platform | **Fixed** | `stdio: [process.platform === "win32" ? "pipe" : "ignore", "pipe", "pipe"]` (`desktop/main.js:1134-1136`), asserted in `desktop/test/bootstrap.test.js`. POSIX runtime behavior was not exercised on this Windows host; source and test only. |

**AI terminal sessions on a graceful stop: they end.** The stop signal's
`begin_shutdown`, and the lifespan's `terminate_ai_terminal_sessions(timeout_sec=3.0)`,
pop every session, including engine-started ones with no socket, from
`_active_ptys` and kill its tree. The PTY socket handler returns once
`pty.is_alive()` turns false or the client disconnects
(`ai_pty/websocket.py:160-258`), so it cannot hold the connection drain open.
Branch tests `test_ai_terminal_sessions_are_killed_and_deregistered` and
`test_a_graceful_stop_kills_an_ai_terminal_session_with_no_socket` pass. They
use a stand-in session; no real provider CLI was run.

**`tests/api/test_runtime_backend_stop.py`.** It starts the real desktop
command (`gui --port 0 --bundled`) with a stdin pipe and the stop variable, a
project-local slow block, and an open `/ws` plus log stream. It starts a run,
whose pre-run auto-commit runs git with an inherited stdin, then closes stdin.
It asserts that the process exits within 25 s, that the log stream ends, that
no fatal stdin-lock error appears, and that the row is `cancelled`. It passed
here. It covers N1 and N2 together on whatever platform runs it. On POSIX it
still sets the Windows-only variable, so it exercises the stdin path there
too, not SIGTERM.

| Check | Result |
|---|---|
| `pytest` on `test_runtime_backend_stop`, `test_runtime_backend_streams`, `test_runtime_stop_request`, `test_runtime_run_lifetime`, `test_ws`, `test_runtime_import_surface`, `test_runtime_lineage_finalize_status`, `test_runtime_mcp_pointer` and `test_app` (`--no-cov`) | 73 passed, 2 skipped (POSIX-only pointer cases), exit 0 |
| `node --test desktop/test/bootstrap.test.js desktop/test/main-orchestration.test.js` | exit 0, including the three #2327 cases |
| PROBE1 to PROBE3 reruns | unchanged: reopen and switch keep `completed`; in-process shutdown gives `cancelled` in 0.09 s |
| PROBE5 (delete mid-run, with retention on and off) | N3 partial, source confirmed |
| Node- and Python-spawned watcher repro | N1 fixed |
| Real-uvicorn stdin-EOF stop mid-run with no client, SSE, `/ws` | N2 fixed |
| Sentrux | N/A (MCP not available in this runtime) |
