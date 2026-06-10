# Investigation: async-loop blocking & WS-driven run-state lifecycle

**Date:** 2026-06-10
**Author:** AI implementer (agent A2, P1-P2 API bug-fix session)
**Scope:** INVESTIGATION ONLY — no code refactor in this PR. Findings +
recommendation + proposed follow-up issues for #1528 (DSN-4) and #1532 (DSN-8).
**Source:** comprehensive audit #1513 / PR #1514 (DSN-4, DSN-8).

This document accompanies the same PR that fixes #1521, #1551, and #1461. The
two issues below are deliberately left unimplemented because each needs an
explicit design decision (and #1528 likely an ADR) that exceeds a scoped
bug-fix.

---

## #1528 (DSN-4, P2) — Synchronous git/SQLite/snapshot work blocks the asyncio loop; single-active-project global

### Current behavior

`ApiRuntime` runs inside a single FastAPI/uvicorn event loop. Several
request paths perform **blocking, CPU/IO-synchronous** work directly on that
loop thread:

- **Pre-run git auto-commit** (`api/runtime/_runs.py:229-279`,
  `start_workflow`): constructs a `GitEngine`, calls `head_state()`, and on a
  dirty tree runs `engine.commit(...)`. Each `GitEngine` call shells out to the
  bundled `git` binary via `subprocess.run` (`core/versioning/git_binary.py`).
  This is synchronous and can take tens to hundreds of ms (or block on a
  signing server — see the sandbox signing failure in this very session).
- **Lineage recorder / SQLite writes** (`_runs.py:_build_lineage_recorder`,
  `_finalize_lineage_run`): `LineageRecorder.begin_run` / `finalize_run` write
  to a project-scoped SQLite store synchronously.
- **Git REST endpoints** (`api/routes/git.py`): every endpoint
  (`commit`, `restore`, `merge`, `branch_switch`, …) calls `GitEngine`
  methods (subprocess) directly inside the `async def` handler. The
  ADR-045 §5.1 #5 change in this PR adds two more `git diff` subprocess calls
  per tree-mutating op (committed-range + working-tree) — still synchronous.
- **Workflow / file snapshots**: workflow YAML reads and (pre-this-PR) the
  SHA-256 hash snapshot of every workflow ran on the loop thread.

Because these run on the loop thread, a single slow git/SQLite call **stalls
every other in-flight WS message, SSE log push, and HTTP request** for the
duration. Under a flaky or slow git binary (or a remote signing server) the
whole backend appears to hang.

Separately, the runtime is **single-active-project**: `self.active_project`,
`self.lineage_store`, `self.data_catalog`, `self.workflow_runs`, and the
version-vector maps are all keyed to one open project. Opening a second project
clears them (`_projects.open_project` → `self.data_catalog = {}`,
`reset_version_state_for_project`). There is no concurrency model for two
projects, and `workflow_runs` is keyed by `workflow_id` (not `run_id`), so the
global is also a single-run-per-workflow constraint (see #1517).

### Root cause

The API layer was built request-synchronous against a synchronous core
(`GitEngine` is subprocess-based; `LineageStore` is SQLite). FastAPI handlers
are `async def`, so any synchronous call inside them executes on the loop
thread with no `run_in_executor` / threadpool offload. The single-active-project
global is an early-stage simplification that was never revisited.

### Options

1. **Offload blocking calls to a threadpool** (`asyncio.to_thread` /
   `loop.run_in_executor`). Wrap the `GitEngine` and `LineageRecorder` calls in
   `start_workflow` and the git endpoints. Lowest-risk, localized; keeps the
   single-project model. Risk: git operations on the same repo are not safe to
   run concurrently — needs a per-project async lock so two offloaded git ops
   don't interleave (`index.lock` contention).
2. **Async git/lineage facade**: introduce an async wrapper service that owns a
   dedicated worker (thread or process) per project and serializes git/SQLite
   access behind a queue. Cleaner isolation; larger surface; touches protected
   `core.versioning` / `core.lineage` paths.
3. **Multi-project runtime**: key all session state by `project_id` (and runs
   by `run_id`, folding in #1517). Removes the single-active-project global.
   Largest change; cross-cutting; almost certainly needs an ADR.

### Recommendation

Stage it:

- **Short term (own issue, no ADR):** Option 1 — offload the known blocking
  calls (`GitEngine.*`, `LineageRecorder.*`) via `asyncio.to_thread`, guarded by
  a **per-project async git lock**, so the loop stops stalling. This is a
  contained, test-coverable change to `api/routes/git.py` and
  `api/runtime/_runs.py`.
- **Long term (ADR required):** the single-active-project → multi-project /
  run-identity model (Option 3), coordinated with #1517 (run-identity refactor).
  This changes the runtime state contract, storage scoping, and the WS/MCP
  run-lookup surface, so it meets the ADR bar (cross-module, hard to reverse,
  long-term tradeoff).

### ADR needed?

- Option 1: **No** — implementation detail (threadpool offload + lock).
- Option 3: **Yes** — runtime state-scoping contract change.

### Proposed follow-up issues

- `fix(api): offload blocking git/lineage calls off the event loop (per-project
  async lock)` — implements Option 1. References #1528.
- `design(adr): multi-project / run-identity runtime state scoping` — ADR +
  spec, coordinated with #1517. References #1528, #1517.

---

## #1532 (DSN-8, P2) — No authoritative read path for live run state; WS-disconnect cancels all runs 2s after the last client drops

### Current behavior

There are **two** ways to learn a run's state, and neither is the single
authoritative source:

1. **WebSocket event stream** (`api/ws.py`): the only push channel. Clients
   subscribe to engine events (`block_running`, `block_done`, `workflow_completed`,
   …) and reconstruct run state client-side from the event sequence. There is
   no "give me the current state of run X" pull endpoint over WS.
2. **MCP tool `read_run` / `get_run_status`**
   (`ai/agent/mcp/tools_workflow/read.py:243-270`): derives state on demand by
   reading `runtime.workflow_runs[run_id].task` (`done`/`cancelled`/`exception`)
   and the scheduler's private `_block_states`. This is the closest thing to an
   authoritative read, but it reaches into `scheduler._block_states` (a private
   attribute) and is only reachable via the MCP/agent surface, not the GUI.

The GUI has no REST/WS endpoint that returns the authoritative current run
state; it depends entirely on having observed the full event stream from the
moment the run started. A client that connects mid-run, or reconnects after a
drop, cannot resynchronize — it sees only events emitted after it reconnects.

**WS-disconnect cancellation:** `api/ws.py:207-220, 344-355`. When the last GUI
WS client disconnects, the handler's `finally` schedules
`_cancel_after_gui_disconnect_grace`, which sleeps
`_GUI_DISCONNECT_GRACE_SEC = 2.0` (ws.py:40) and then, if no client reconnected,
calls `_cancel_running_workflows_for_gui_disconnect` — which cancels **every**
active workflow run. So a transient network blip or a browser tab refresh that
exceeds the 2-second grace **kills all in-flight runs**. The grace debounces
fast reconnects but is fragile: 2s is short for mobile/VPN/laptop-sleep, and
the policy ("browser owns the runs") is implicit, not a documented contract.

### Root cause

- Run state was modeled as a **stream-only** projection: the engine emits
  events, and the canonical state lives implicitly in (a) the scheduler's
  in-memory `_block_states` and (b) the asyncio task status. There is no
  serialized, pull-able run-state resource.
- The disconnect-cancellation policy treats the GUI WS connection as the
  **owner** of run lifetime (a run exists only while a browser watches it),
  which is reasonable for ephemeral local sessions but wrong for long-running
  scientific workflows the user expects to survive a disconnect.

### Options

1. **Authoritative run-state read endpoint:** add `GET /api/runs/{run_id}`
   (and/or a WS `get_run_state` request) that returns the serialized current
   state (run status + per-block states) from the runtime, reusing the
   derivation already in `read_run`. Promote the `scheduler._block_states`
   read into a public `block_states()` accessor (the runtime already calls
   `scheduler.block_states()` in `_runs._derive_lineage_run_status`, so a
   public method exists — `read.py` should use it instead of the private attr).
   Lets any client (GUI or agent) resync without replaying the stream.
2. **Reconnect resync handshake:** on WS connect, the server sends a snapshot
   of all active runs' current state before resuming the live stream. Builds on
   Option 1's serialization.
3. **Decouple run lifetime from WS presence:** make disconnect cancellation
   **opt-in / policy-driven** (e.g. a per-run "cancel on disconnect" flag, or a
   much longer / configurable grace, or never-cancel with an explicit
   user-cancel). Removes the "transient blip kills my run" failure.

### Recommendation

- **Option 1 is the foundational fix** and should land first: a single
  authoritative serialized run-state read path. While doing it, fix the private
  `scheduler._block_states` access in `read.py:267` to use the public
  `block_states()` accessor (low-risk cleanup).
- **Option 2** (reconnect resync) layers on top once Option 1 exists.
- **Option 3** (disconnect policy) should be decided explicitly: at minimum
  make the grace configurable and document the "WS owns the run" contract; the
  preferred end state is that a disconnect does **not** cancel long-running
  runs by default.

### ADR needed?

- Option 1 (+ public `block_states()`): **No** — additive read endpoint +
  accessor; reuses existing derivation.
- Option 3 (run-lifetime-vs-WS-presence policy): **Yes (lightweight)** — it
  changes a user-visible behavioral contract (when runs get cancelled) and is
  the kind of decision that will be questioned later. An ADR addendum or a short
  ADR is warranted; coordinate with #1528 Option 3 and #1517 since run identity
  is shared.

### Proposed follow-up issues

- `feat(api): authoritative GET /api/runs/{run_id} run-state endpoint; use
  public scheduler.block_states()` — Option 1. References #1532.
- `feat(api): WS reconnect resync snapshot of active runs` — Option 2.
  References #1532.
- `adr: run lifetime vs WS-client presence (disconnect cancellation policy)` —
  Option 3, ADR addendum. References #1532, #1528, #1517.

---

## Cross-cutting note

#1528 and #1532 both intersect #1517 (run-identity refactor: key runs by
`run_id` with an explicit concurrency policy). The multi-project/run-identity
ADR proposed under #1528 Option 3 and the run-lifetime ADR under #1532 Option 3
should be planned together so the runtime state contract changes once, not
three times.
