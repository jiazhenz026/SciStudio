---
title: "Audit — ADR-055 Spec 4 track O3, run lifetime without the GUI-disconnect cancel (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 38
  - 42
related_specs:
  - adr-055-enterprise-support
  - adr-055-local-background-runtime
language_source: en
---

# Audit — ADR-055 Spec 4 Track O3, Run Lifetime Without The GUI-Disconnect Cancel (with-context)

Audit mode: **with-context** (`audit_reviewer` persona, task kind `docs`).
Subject: PR #2334, branch `fix/2327-run-lifetime` @ `cf2cffa83` (implementation
commit `6ee4b109a`), base `main` @ `e9dcd01aa`. 11 files, +1784/-118.
Issue: #2327 (owner decision 2026-09-11: option 1, with the constraint that the
#1500 stuck-`running` problem must not regress). Umbrella PR: #2323
`[DO NOT MERGE]`. Checklist: `docs/planning/adr-055-spec4-checklist.md` §9 on
`track/adr-055-spec4`. Dispatch prompt: §A3 of
`docs/planning/adr-055-spec4-dispatch-prompts.md`.
Gate ledger under audit: `.workflow/records/2327-fix-2327-run-lifetime.json`.
Audit gate ledger: `.workflow/records/2327-audit-2327-o3-with-context.json`.

**Verdict: block until P1-1 is fixed.** The disconnect cancel is gone. The
three guarantees the owner named hold as built:
- Graceful shutdown ends every run.
- A hard kill is reconciled at the next open. A real backend was killed
  mid-run and reopened to prove it.
- A worker death ends the run `failed`.

The concurrent-finish ordering held in 270 forced races. The defect is in the
path #2327 makes common. After a page reload the frontend reopens the project.
Reopening closes the lineage store the in-flight run writes to, so a run that
completes afterwards keeps a `running` row and loses all of its block lineage.
The next open then records it `failed`. That is the #1500 symptom, reached
through the ordinary reconnect flow, and no test asserts the row after it.

## 1. Findings

### P1 — blocks merge

**P1-1. Reopening the project mid-run strands the run's lineage in `running`,
then records a completed run as `failed`.**

- **Mechanism.**
  - `_init_lineage_store` closes the previous `LineageStore` on every
    `open_project`, including a reopen of the same project
    (`src/scistudio/api/runtime/_projects.py:185-191`).
  - The run's `LineageRecorder` keeps the store object it was built with
    (`src/scistudio/api/runtime/_runs.py:133`).
  - A closed store raises `ProgrammingError("LineageStore is closed")` on
    every call (`src/scistudio/core/lineage/store.py:395`).
  - Every `block_executions` write after the reopen fails, and so does
    `finalize_run`. Both failures are swallowed.
  - `_on_done` then calls `release_run` (`_runs.py:562-568`), which removes
    the owner marker and the live entry.
  - The next open finds a `running` row with no marker and finalises it
    `failed`.
- **Why #2327 makes it the normal path.**
  - The frontend does not persist `currentProject`: the `partialize` whitelist
    in `frontend/src/store/index.ts:92-113` says canvas state "re-derives from
    project open + workflow load".
  - So a user who closes the tab and comes back must open the project again.
    That goes `useProjectActions.openProject` → `GET /api/projects/{id}`
    (`src/scistudio/api/routes/projects.py:385-389`) → `runtime.open_project`.
  - On `main` the disconnect cancel had already ended the run with its store
    open, so this flow ended `cancelled`.
  - With this PR the run survives, the reopen closes its store, and the row
    stays `running`.
- **Evidence (probe C, section 4).** Execute, reopen the project over HTTP
  while the run is in flight, release, let the run finish:
  - Blocks: `load=done, transform=done, final=done`.
  - Row: `status='running'`, `finished_at=None`. `/api/runs` reports
    `['running']`. Marker gone, live entry gone.
  - `block_executions` rows for the 3-block run: `0`.
  - The next open changes the row to `status='failed'`.
- **Project switch (probe C2).** Switching to another project mid-run gives
  the same result: the row is left `running`.
- **Test gap.** The PR's own
  `test_a_started_run_is_claimed_before_its_row_is_visible`
  (`tests/api/test_runtime_run_lifetime.py:406-423`) reopens the project
  mid-run. It stops at `wait_for_workflow_completion` and never reads the row.
- **Contradicted claims.**
  - The PR table's first row: "run keeps going; a reconnecting client still
    sees it; it finishes normally with a terminal row".
  - The CHANGELOG entry (`CHANGELOG.md:627-643`): "Reopen the page and the run
    is still there, in Run history".
- **Options (owner's choice).**
  - (a) Do not close or replace the store when the active project is reopened.
  - (b) Keep a prior store open until the live runs that use it are released.
  - (c) Have the recorder write through the runtime's current store for its
    project rather than a captured handle.
  - (d) Define what a project switch does to the previous project's live runs.

  Whichever is chosen, a regression test must read the row after a mid-run
  reopen and after a mid-run switch.

### P2 — should fix before completion

**P2-1. A marker whose host differs is never reconciled by anyone, and it
disables artifact retention for the project permanently.**

- **Mechanism.**
  - `_owner_may_be_alive` returns `True` for any marker whose `host` is not
    `socket.gethostname()` (`_run_lifetime.py:285-287`).
  - No process ever finalises such a row. There is no staleness bound, no
    command and no log line that surfaces it.
  - Hostname is not a stable machine identity:
    - macOS `gethostname()` changes with the network.
    - A re-created container gets a new hostname by default.
    - A renamed machine gets one too.
- **Evidence (probe F).**
  - A dead-pid marker carrying the previous hostname stays `running` after
    three opens.
  - `plan_retention` then reports `is_blocked=True` with "1 run(s) still
    executing; retention will not sweep while a workflow is running."
  - #1983 retention is therefore off for that project from then on.
  - The same permanent state follows when `process_create_time` was recorded
    as `None` and the PID is later reused.
- **Options.**
  - A stable machine identifier instead of the hostname.
  - A staleness bound, for example a marker heartbeat or mtime.
  - A manual reconcile entry point.
  - At minimum, a warning at open that lists rows it cannot decide.

**P2-2. The new storage path is undocumented.**

- `docs/architecture/ARCHITECTURE.md` §11.2 enumerates the runtime paths
  under `.scistudio/`, with producer and purpose for `lineage.db`, `pause/`,
  `ai-block-runs/` and the rest (lines 1997-2008).
- `.scistudio/run-owners/<run_id>.json` is not added.
- AGENTS.md §3.4 requires docs when storage changes. The ledger records only
  `CHANGELOG.md` as a docs event.
- `docs/architecture/**` is outside the declared scope, so the fix needs a
  `gate_record amend`.

### P3 — improvements and follow-ups

**P3-1. An unreadable marker is treated as proof that its owner is dead.**
- `_read_marker` maps every `OSError` to `{}` (`_run_lifetime.py:269-270`).
  `_owner_may_be_alive({})` then returns `False`.
- A transient read failure is not proof of death. Examples: a Windows sharing
  violation, an antivirus scanner holding the file, a network filesystem
  error.
- Probe E: the owner process was alive, the marker read raised
  `PermissionError`, and the row was finalised `failed`.
- This contradicts the claim that "rows owned by a live process are
  untouched". It only matters when two backends share a project.
- Distinguishing `OSError` (skip or retry) from `ValueError` (corrupt content)
  would close it.

**P3-2. The marker sweep can delete a marker being claimed.**
- `claim_run` writes the marker before taking `_LOCK` to insert the live
  entry (`_run_lifetime.py:139-158`).
- A sweep that runs in between sees no live entry, no row and
  `pid == os.getpid()`. It removes the marker.
- Probe D, forcing that interleaving: `live=True marker_exists=False`.
- A second backend could then reconcile the live run.
- Not reachable today: `open_project` and `start_workflow` are both called
  from async routes on the event-loop thread.
- The module comment says reconciliation "runs on whichever thread opens the
  project", which invites a threaded caller.
- Inserting the live entry before writing the marker, or writing it under the
  lock, removes the window.

**P3-3. Shutdown straggler rows can be re-finalised.**
- `shutdown_workflow_runs` finalises a straggler `cancelled` while its task is
  still running (`_run_lifetime.py:236-252`).
- If the task finishes before the loop is torn down, `_on_done` finalises the
  row again with an unconditional `UPDATE`.
- The last writer wins. The outcome is still terminal.

**P3-4. Ledger evidence nits. No merge impact.**
- `test_events` and `docs_events` carry `verified_in_diff: null`.
- `pull_request.body_closes_issues` is `[]`, although the PR body says
  "Closes #2327" and `closes` is `[2327]`.
- One `python_tests` event failed and a later one passed with the identical
  input fingerprint, which suggests a flaky test.
- Three local reruns of the new and touched tests passed (23/23 each), and CI
  is green.
- Staging files `*.json.tmp` from a failed `os.replace` are never swept.

## 2. Claim Verification

| Claim | Verdict | Evidence |
|---|---|---|
| A GUI `/ws` disconnect no longer cancels any run | Verified | `ws.py` diff removes the grace constant, client set, cancel task and helpers. No reference remains in `src/`, `tests/`, `frontend/src/` or `docs/` (grep). `test_ws_module_no_longer_tracks_gui_clients_for_cancellation`. |
| A reconnecting client still sees the run | Partly | `test_gui_disconnect_keeps_run_going_and_reconnect_still_sees_it` waits 2.5 s past the old grace and sees live events and the `completed` row. That holds only if the client does not reopen the project; see P1-1. |
| Graceful shutdown: bounded wait, then stragglers written `cancelled` | Verified | `shutdown_workflow_runs` (`_run_lifetime.py:212-253`). Done-callbacks registered at start are scheduled before `asyncio.wait`'s own wake-up, and `sleep(0)` adds margin. Tests: `test_graceful_shutdown_mid_run_leaves_terminal_lineage` (real lifespan, row `cancelled`, marker removed) and `test_shutdown_finalises_a_run_that_ignores_cancellation`. See P3-3. |
| Kill or crash: dead-owner `running` rows reconciled `failed` at open | Verified | Probe A (real backend subprocess, hard kill mid-run): row `running` after the kill, `failed` with `finished_at` after the reopen, marker removed, reason in `run-<id>.log`. Tests cover a crashed pid, a reused pid, a missing marker, this process's untracked run and an unreadable marker. |
| Rows owned by a live process, including another host, are untouched | Verified with exceptions | `test_open_keeps_run_owned_by_a_live_process` and `..._another_host`. Exceptions: P3-1, a transient read error on a live owner's marker finalises its row; P2-1, "another host" also captures a renamed host forever. |
| PID reuse and create time handled | Verified | `_owner_may_be_alive` compares `create_time` within 2.0 s, matching #1542. `pid == os.getpid()` is correctly treated as dead after live runs are excluded. The `reused_pid` case is covered. AccessDenied is treated as alive (conservative). |
| Markers written before the row and cleaned up | Verified | `claim_run` precedes `begin_run` (`_runs.py:137-139`). The write is atomic (staging file + `os.replace`). Removal happens after finalisation (`_runs.py:562-568`), at shutdown, on abandon, at reconcile, and via the stale sweep. `test_open_removes_markers_of_runs_that_already_finished`. See P3-2. |
| No races with a run finishing concurrently | Verified | Probe B: 150 in-process thread races, 0 overwrites. Probe B2: 120 runs finished while a second process reconciled in a tight loop (3,158 passes), 0 overwrites. Cross-process ordering rests on finalise-before-unlink, not on `_LOCK`. |
| Worker death still ends the run `failed` | Verified | `test_worker_death_finalises_run_as_failed` kills a real worker process: `transform=ERROR`, `final=SKIPPED`, row `failed`. |
| Start failure after the row insert is finalised | Verified | Both windows after `_build_lineage_recorder` are wrapped: scheduler construction (`_runs.py:508-524`) and task creation (`:552-556`). No other statement sits between the insert and the scheduler. `test_start_failure_after_row_insert_finalises_the_row`. |
| No core or schema change; existing APIs and states | Verified | No `src/scistudio/core/**` path in the diff. Uses `runs_in_progress`, `get_run`, `finalize_run`, and the states `failed` and `cancelled`. The only `begin_run` caller is `_runs.py`, so no other writer creates marker-less `running` rows (MCP `run_workflow` and tutorials go through `start_workflow`). |
| Every #1500 scenario has a regression test | Partly | #1500's lineage scenarios were a GUI websocket disconnect and app shutdown (4ba26d2ff: `ws.py`, the `app.py` lifespan, `test_last_gui_disconnect_cancels_active_workflow`). Shutdown is covered. The disconnect test does not cover the reopen a real reconnect performs (P1-1). |

Other checks:
- `.scistudio/` is in the default project `.gitignore`
  (`src/scistudio/core/versioning/gitignore_template.py`), so the ADR-039
  pre-run auto-commit does not pick up markers.
- ADR-055 §7 ("Closing the connection window or browser does not stop an
  active analysis") and §8.1 ("Browser disconnection and idle-page detection
  do not terminate active analyses") are satisfied by the removal.

## 3. Tests And CI

- Required command:
  `PYTHONPATH=src .venv/Scripts/python -m pytest tests/api/test_runtime_run_lifetime.py tests/api/test_ws.py tests/api/test_runtime_import_surface.py -q`.
  - All tests pass, exit 0.
  - With the repository `addopts` a narrow run also trips the global 70%
    coverage floor. The run above used `--no-cov`.
  - Stability: `test_runtime_run_lifetime.py` plus `test_ws.py`, run three
    times, gave 23/23 passed each time.
- CI for PR #2334 at `cf2cffa83`: all 17 checks pass, including Test (Python
  3.11) 7m42s, Test (Python 3.13) 9m44s, E2E (headless), Import Contracts,
  Architecture Tests, Full Audit, Type Check and Verify Workflow Compliance.
- Gate reconciliation, read-only: `gate_record check --mode pre-pr --record
  .workflow/records/2327-fix-2327-run-lifetime.json --base origin/main --head
  origin/fix/2327-run-lifetime`.
  - Result: `tier=2 ... reconciliation passed`, exit 0.
  - The ledger change the check wrote was discarded, not committed.
- Ledger contents:
  - Task kind `bugfix`, persona `implementer`, issue #2327 `close_in_pr`.
  - The scope amend for `src/scistudio/api/app.py` is a recorded
    `scope_events` add-include.
  - Guards pass. Sentrux is advisory only.
  - The three commits carry `Gate-Record`, `Task-Kind`, `Issue`,
    `Assisted-by` and `Co-Authored-By` trailers.
- Sentrux: N/A (MCP not available in this runtime). Frontend or browser smoke:
  N/A (backend-only change).

## 4. Probes

Throwaway, uncommitted, run from the audit worktree against the audited code
with the `tests/api` fixtures:

- **A.** A real backend subprocess opens a project and starts a run whose
  middle block sleeps 120 s. Once the worker exists, the backend and its
  children are hard-killed (TerminateProcess). A fresh backend then reopens
  the project.
  - Result: `running` after the kill; `failed` after the reopen, with
    `finished_at` set, the marker removed, and the reason in the run log.
- **B.** 150 iterations of a claimed run finishing (`completed` + release)
  in one thread while another thread reconciles, with random offsets.
  - Result: 0 overwrites.
- **B2.** 120 runs claimed, finalised and released while a separate process
  reconciled the same project continuously.
  - Result: all `completed`, 0 reconciled.
- **C / C3.** A run is reopened mid-flight through `GET /api/projects/{path}`
  and then completes.
  - Result: row `running`, 0 `block_executions` rows, the next open records
    `failed` (P1-1).
- **C2.** A second project is created (and so opened) mid-run.
  - Result: row `running` after completion (P1-1).
- **D.** A sweep forced between `claim_run`'s marker write and its live
  insert.
  - Result: marker deleted while the run is live (P3-2).
- **E.** A `PermissionError` injected on a live owner's marker read.
  - Result: the row is finalised `failed` (P3-1).
- **F.** A marker with a dead pid and the previous hostname, then three opens.
  - Result: row still `running`, retention blocked (P2-1).

## 5. Checklist, Scope, And Documentation Drift

- Checklist §9.3 still shows placeholders (`<commit>`, `<test command>`),
  although PR #2334 and commit `6ee4b109a` exist. §9.4 is unchecked.
- The §9.1 required test "the #1500 scenario is reproduced as a regression
  test" is only partly met (P1-1).
- Scope: the diff stays inside the declared scope and its amend. `app.py` is
  a four-line lifespan hunk, as the A3 prompt allowed.
- Out-of-scope paths are untouched: no `seam.py`, `spa.py`, `routes/ai_pty/`,
  `routes/webmcp.py`, `cli/`, `frontend/`, `core/` or `docs/ai-developer/`.
- Docs: the CHANGELOG entry is present under `[Unreleased]` / Fixed but
  over-claims (P1-1). `ARCHITECTURE.md` §11.2 is missing (P2-2). No other doc
  described the removed disconnect cancel.

## 6. Recommendation

**Block.**
- P1-1 must be fixed and covered by a test that reads the lineage row after a
  mid-run reopen and after a mid-run switch.
- P2-1 and P2-2 should be resolved before completion. The owner decides
  P2-1's identity and staleness design.
- P3 items can be tracked as follow-ups.
