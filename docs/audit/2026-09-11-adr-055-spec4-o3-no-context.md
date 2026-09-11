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
