---
title: "No-Context Audit — Serious Code Bugs / Correctness Defects"
issue: 1589
branch: audit/2026-06-11-codebase-no-context
author: audit_reviewer agent (AUD-3, no-context) + manager verification
date: 2026-06-11
status: committed
lens: serious code bugs / correctness defects
overall_recommendation: pass-with-fixes
---

# No-Context Audit — Serious Code Bugs / Correctness Defects (2026-06-11)

## 1. Scope and method

One lens of a three-lens **no-context** repository audit (issue #1589). The agent
read only ADRs/specs/docs/code/tests (no issues, gate records, PRs, or manager
summaries) and hunted concrete, runtime-relevant defects in the execution path:
`engine/runners/**`, `engine/scheduler/**`, `engine/resources.py`,
`api/runtime/**`, `api/routes/**`, `api/ws.py`, `api/sse.py`,
`core/lineage/recorder.py`, `blocks/io/**`, and the governing ADRs (esp.
ADR-022 resource model). Each finding is grounded in code read at HEAD
`cd370810` with a concrete failure scenario.

The manager independently re-verified the core claim of the top findings (see
**Manager verification**).

> Context: the execution surface is in **markedly better shape** than the prior
> 2026-06-10 audit — atomic checkpoint/SaveData/YAML, browse sanitiser, streamed
> upload cap, provenance_degraded, EventBus snapshot iteration, start-time
> validation, double-start guard, and bounded registries are all verifiably
> fixed. The defects below are new or residual; none blocks single-workflow local
> use. Recommendation: **pass-with-fixes**.

## 2. Findings (severity-ordered)

### BUG-RM-01 — ADR-022 GPU/CPU dispatch gating is dead code (scheduler never acquires/releases resources) (P2)

- **Category:** bug · **Confidence:** high
- **Locations:** `src/scistudio/engine/scheduler/_dispatch.py:86`,
  `src/scistudio/engine/resources.py:204-227,229-256`, `docs/adr/ADR-022.md:93-96,116-121`
- **Evidence:** The only dispatch-time check is `_dispatch.py:86`:
  `if not self._resource_manager.can_dispatch(ResourceRequest(),
  active_count=len(self._active_tasks)):` — it passes a **default**
  `ResourceRequest()` (`requires_gpu=False, cpu_cores=1`), never the block's
  declared request, and never calls `acquire()`. `ResourceManager.acquire()` has
  **zero call sites** in `src/` (it is the sole mutator of
  `_gpu_in_use`/`_cpu_in_use`/`_allocations`), so those counters stay 0 forever:
  the GPU check (`resources.py:204`) and CPU check (`resources.py:216`) can never
  fire, and `_on_block_terminal` releases from an always-empty `_allocations`.
  ADR-022 §4 states Layer-1 ResourceManager "blocks new work when discrete
  resources are exhausted."
- **Impact:** Discrete GPU/CPU dispatch gating is silently inoperative. N blocks
  declaring `requires_gpu=True` on a host with `gpu_slots=1` dispatch
  concurrently and oversubscribe the GPU (VRAM OOM / device contention); CPU-core
  throttling never limits concurrency. Only the psutil system-memory watermark
  and the active-task-count watermark still gate. The existing concurrency test
  uses a mock that simulates acquire/release in its own `can_dispatch` stub, so
  it passes while the real wiring gap is uncovered.
- **Recommendation:** Plumb the block's real `ResourceRequest` into `_dispatch`
  and call `resource_manager.acquire(request, block_id)` before creating the task
  (gating on its return); rely on the already-wired `_on_block_terminal → release`
  to free on terminal events. Add a scheduler test asserting the **real**
  counters increment on dispatch and decrement on completion (not a mock).

### BUG-WSCANCEL-02 — WebSocket cancel ignores `workflow_id` and cancels every concurrent workflow (P2)

- **Category:** bug · **Confidence:** high
- **Locations:** `src/scistudio/api/ws.py:272-295`,
  `src/scistudio/engine/scheduler/_events.py:198-211`,
  `src/scistudio/engine/scheduler/__init__.py:168-173`,
  `src/scistudio/api/runtime/_runs.py:51-60`
- **Evidence:** The WS handler emits onto the **shared** bus:
  `event_bus.emit(EngineEvent(CANCEL_WORKFLOW_REQUEST, data={'workflow_id': …}))`
  (ws.py:290-295). Every `DAGScheduler.__init__` subscribes
  `CANCEL_WORKFLOW_REQUEST → self._on_cancel_workflow` (scheduler/__init__.py:171)
  and **never unsubscribes** (`rg 'unsubscribe|dispose'
  engine/scheduler` → no matches). `_on_cancel_workflow` computes
  `cancelable_blocks` from `self._block_states` and **never reads**
  `event.data['workflow_id']`, so each subscribed scheduler cancels its own
  RUNNING/PAUSED blocks. The #1525 double-start guard only rejects a second run
  of the *same* `workflow_id`; two different workflow_ids coexist on one bus. The
  same blindness applies to `cancel_block`.
- **Impact:** With ≥2 concurrent workflows, a WS cancel for workflow A also
  cancels every RUNNING/PAUSED block of B, C, … — silent loss of unrelated
  in-flight computation. (The REST cancel route is correctly scoped; only the WS
  broadcast path — which the frontend uses — is affected.)
- **Recommendation:** Filter `_on_cancel_workflow`/`_on_cancel_block` by
  `event.data.get('workflow_id') == self._workflow.id` (early-return on
  mismatch), or give each run a per-run bus, or have the WS handler resolve the
  run and call `run.scheduler.cancel_workflow()` directly like REST.

### BUG-LINEAGE-03 — LineageRecorder cross-attributes blocks across concurrent runs (P2)

- **Category:** bug · **Confidence:** high
- **Locations:** `src/scistudio/core/lineage/recorder.py:104-108,188-231`,
  `src/scistudio/api/runtime/_runs.py:127-128`
- **Evidence:** `_build_lineage_recorder` creates one `LineageRecorder(
  self.event_bus, …)` per `start_workflow` (subscribes `_on_terminal` to
  BLOCK_DONE/ERROR/CANCELLED/SKIPPED on the **shared** bus). `_on_terminal`
  early-returns only on `_store is None`, `block_id is None`, or per-recorder
  dedup — it **never checks** `event.data.get('workflow_id')` against the run it
  belongs to, yet writes a `block_executions` row with `run_id=self._run_id` for
  **any** block terminal event on the bus.
- **Impact:** With two concurrent workflows, every BLOCK_DONE fans out to BOTH
  recorders; each writes a `block_executions` (and derived data_objects/block_io)
  row attributing the other workflow's block to its own `run_id`. Lineage /
  provenance — the core guarantee of a scientific data runtime — is silently
  cross-contaminated. (Recorders are disposed at run end, so the sequential-run
  duplicate-write bug from #926 is fixed; concurrent cross-attribution is not.)
- **Recommendation:** Filter `_on_terminal` by `event.data.get('workflow_id') ==
  self._workflow_id` (record the workflow_id at construction), or move to a
  per-run event bus. Same root cause as BUG-WSCANCEL-02.

### BUG-PTYLEAK-04 — Engine-initiated PTY tab leaks a subprocess + slot if never joined (P3)

- **Category:** bug · **Confidence:** medium
- **Locations:** `src/scistudio/api/routes/ai_pty/engine.py:132-149,164-168`,
  `src/scistudio/api/routes/ai_pty/websocket.py:184-211`
- **Evidence:** `open_engine_initiated_tab` spawns the agent PTY and registers it
  in `_active_ptys`/`_engine_tab_to_run`/`_engine_run_to_run_dir` (engine.py:146-149)
  before a best-effort WS broadcast (engine.py:164-168, swallows RuntimeError when
  no loop). The only cleanup is `pty_endpoint`'s `finally`
  (websocket.py:196-211), which runs only after a frontend WS client actually
  connects. There is no timeout/reaper for an opened-but-never-joined tab.
- **Impact:** If the broadcast is lost or the user never opens the tab, the
  spawned claude/codex subprocess runs forever, the registry entries leak, and
  the slot counts permanently against `MAX_ACTIVE_PTYS` (16). Enough orphaned
  opens reach the cap and all new PTY tabs are refused. Requires a specific
  failure, so P3.
- **Recommendation:** Reap engine-initiated tabs not joined within a grace window
  (background timer kills the PTY + clears the maps), or spawn the PTY only on
  first WS join. At minimum log/expose the orphan count.

### BUG-PIDLEAK-05 — LocalRunner never deregisters the ProcessHandle; dead PIDs can be re-killed at shutdown (P3)

- **Category:** bug · **Confidence:** high
- **Locations:** `src/scistudio/engine/runners/local.py:276-283`,
  `src/scistudio/engine/runners/process_handle.py:129-144`
- **Evidence:** `LocalRunner.run` calls `register_async_process(pid=proc.pid, …)`
  (local.py:276-281) but after `await proc.communicate()` (local.py:283) never
  calls `registry.deregister(block_id)`. `rg deregister` shows the only callers
  are `ProcessMonitor` (unexpected exits) and tests — the normal-completion path
  leaves the handle registered with a now-dead PID. `ProcessRegistry.terminate_all`
  (process_handle.py:129-144) signals every retained handle's PID at engine
  shutdown.
- **Impact:** Over a long session the shared registry accumulates handles for
  completed blocks; at shutdown `terminate_all` signals each stored PID — if the
  OS recycled a completed worker's PID, an unrelated process receives
  SIGTERM/SIGKILL (or a psutil tree-kill on Windows). Same-named blocks across
  runs also overwrite the keyed entry. Low per-event likelihood but a real
  safety hazard (matches BUG-7 in the prior audit, still unfixed).
- **Recommendation:** Deregister in a `finally` in `LocalRunner.run` (or on BLOCK
  terminal in the scheduler), and key the registry by `(run_id, block_id)` so
  terminate operations cannot target a reused PID from a finished run.

## 3. Manager verification

Independently confirmed against HEAD `cd370810`:

- **BUG-RM-01:** `grep -rn "\.acquire(" src/scistudio/engine src/scistudio/blocks`
  returns **no callers**; `acquire` is defined at `resources.py:229`. Dead gating
  **confirmed**.
- **BUG-WSCANCEL-02:** `_on_cancel_workflow` in `_events.py` contains **no**
  `workflow_id` reference. **Confirmed.**
- **BUG-LINEAGE-03:** `recorder._on_terminal` (`recorder.py:188`) contains **no**
  `workflow_id` filter. **Confirmed.**
- BUG-PTYLEAK-04 / BUG-PIDLEAK-05: high-quality agent verification with cited
  lines; accepted at the agent's stated confidence (medium / high).

## 4. Recommendation

**pass-with-fixes.** Nothing here blocks day-to-day single-workflow local use.
BUG-RM-01 should be addressed before any feature leans on resource gating; the
two concurrency P2s (cross-workflow cancel, lineage cross-attribution) are the
still-live concurrent-different-workflow half of the documented DSN-1 root cause
and should be fixed before multi-workflow concurrency is relied upon. The two P3
leaks warrant tracked follow-ups. See the consolidated index for the follow-up
issue plan.
