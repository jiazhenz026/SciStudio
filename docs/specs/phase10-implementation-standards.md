---
spec_id: phase10-implementation-standards
title: "Phase 10 Implementation Standards"
status: Deprecated
feature_branch: legacy/phase10-implementation-standards
created: 2026-04-06
input: "Historical Phase 10 task decomposition for core type system, scheduler, and worker subprocess refinements."
owners:
  - "@jiazhenz026"
related_adrs:
  - 18
  - 27
related_specs: []
scope:
  in:
    - Historical Phase 10 task contracts retained for reference.
  out:
    - Active implementation planning.
governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests: []
acceptance_source: issue
language_source: en
---
# Phase 10 Implementation Standards

## 1. Change Summary

This deprecated spec is retained as historical reference. Its original body is preserved below, but it is not an active implementation spec under ADR-042.

## 2. Existing Historical Body

# Phase 10 Implementation Standards

**Status**: accepted
**Date**: 2026-04-06
**Issue**: #261 (foundation), follow-up tickets T-001 through T-014
**Authoritative ADRs**: ADR-018 Addendum 1, ADR-027, ADR-027 Addendum 1

## Purpose

This document is the **single source of truth** for the 14 Phase 10
implementation tickets that follow PR #261 (Phase 10 skeleton). Each
ticket below has a complete contract specifying which files to create,
which to modify, which tests to add or update, the acceptance criteria,
the dependencies on other tickets, and explicit out-of-scope notes.

A subsequent implementation agent picking up any single ticket should
**not need to re-read the ADRs**. This document quotes the ADR
pseudocode where the implementation contract is load-bearing, and cites
the specific Decision letter (D1, D2, ...) from ADR-027 for traceability.

## Scope

In scope: contracts for T-001 .. T-014 (Phase 10 core type system,
scheduler concurrency, and worker subprocess refinements). One PR per
ticket. Linear chained sequence per the dependency graph below.

Out of scope: the ADR text itself (already merged in PRs #255 and #259);
the architecture / project-tree / block-sdk doc updates (already merged
in PR #257 and #258); the imaging plugin package itself (lives in
`scieasy-blocks-imaging` repo, not this one).

## One-sentence summary

Fourteen surgical implementation tickets land Phase 10's core type
system (instance-level axes, stratified Pydantic metadata,
PhysicalQuantity, setup/teardown hooks), the scheduler concurrency fix,
the GPU auto-detect, and the worker subprocess typed reconstruction —
in a stacked-PR sequence that always leaves `main` green.

---

## 1. Cross-reference table

| Ticket | Title                                                        | Source ADR section(s)                              |
|--------|--------------------------------------------------------------|----------------------------------------------------|
| T-001  | Scheduler concurrency fix                                    | ADR-018 Addendum 1 (whole)                         |
| T-002  | ResourceManager GPU auto-detect                              | ADR-027 D10                                        |
| T-003  | PhysicalQuantity                                             | ADR-027 D6 + Addendum 1 §4 (PhysicalQuantity Pydantic integration) |
| T-004  | FrameworkMeta + scieasy.core.meta module                     | ADR-027 D5 (framework slot)                        |
| T-005  | DataObject three-slot metadata                               | ADR-027 D5 (whole)                                 |
| T-006  | Array 6D instance-level axes + sel/iter\_over                | ADR-027 D1, D4                                     |
| T-007  | Other base classes (Series/DataFrame/Composite/Text/Artifact) audit | ADR-027 D2                                  |
| T-008  | Test migration — replace `Image()` with `Array(axes=...)`    | ADR-027 D2 consequence (modified files table)      |
| T-009  | ProcessBlock setup/teardown hooks                            | ADR-027 D7                                         |
| T-010  | scieasy.utils.constraints                                    | ADR-027 D4 companion (port constraint helpers)     |
| T-011  | scieasy.utils.axis\_iter.iterate\_over\_axes                 | ADR-027 D3                                         |
| T-012  | TypeRegistry.resolve + Meta validation                       | ADR-027 D11 + Addendum 1 §3 (Meta constraints)     |
| T-013  | Six base-class `_reconstruct_extra_kwargs` / `_serialise_extra_metadata` hooks | ADR-027 Addendum 1 §2 + Addendum 1 §"Rewritten files" |
| T-014  | Worker subprocess typed reconstruction                       | ADR-027 D11 + Addendum 1 §1 (`_reconstruct_one` / `_serialise_one`) |

---

## 2. Dependency graph

```
                        T-001 (scheduler concurrency)
                        T-002 (gpu auto-detect)
                          │
                          ▼
                        T-003 (PhysicalQuantity)
                          │
                          ▼
                        T-004 (FrameworkMeta + core.meta)
                          │
                          ▼
                        T-005 (DataObject three slots)
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
            T-006       T-007       T-009
            (Array     (Series/    (ProcessBlock
            axes +     DataFrame/   setup/teardown)
            sel/iter)  Composite/
                       Text/Artifact)
              │           │
              ▼           │
            T-010         │
            (constraints) │
              │           │
              ▼           │
            T-011         │
            (iterate_     │
             over_axes)   │
              │           │
              ▼           │
            T-008 ────────┘
            (test migration)
              │
              ▼
            T-012 (TypeRegistry.resolve + Meta validation)
              │
              ▼
            T-013 (six pairs of base-class round-trip hooks)
              │
              ▼
            T-014 (worker.reconstruct/serialise + worker scan)
```

T-001 and T-002 are independent of every other ticket and can be merged
first in any order. T-003 unlocks T-004 (because `FrameworkMeta`
indirectly references `PhysicalQuantity` via the `ChannelInfo` example
in the SDK, and T-003 is small/safe). T-004 unlocks T-005 (DataObject
needs `FrameworkMeta` as its `framework` field type). T-005 unlocks
T-006 / T-007 / T-009 (all three modify base / subclass structure).
T-006 unlocks T-010 / T-011 (constraint and iter helpers depend on the
new `axes` instance attribute). T-008 (test migration) waits until
T-006 + T-007 are merged so `Array(axes=[...])` exists. T-012 / T-013 /
T-014 are the final stack (worker reconstruction).

## 3. Recommended chained PR order

The recommended linear order, where each PR's base is the previous PR's
branch (stacked PRs):

1. **T-001** — scheduler concurrency fix (independent, large)
2. **T-002** — GPU auto-detect (independent, small)
3. **T-003** — PhysicalQuantity (independent, small)
4. **T-004** — FrameworkMeta + `scieasy.core.meta` package
5. **T-005** — DataObject three-slot metadata
6. **T-006** — Array 6D axes + `sel` / `iter_over`
7. **T-007** — other base classes audit
8. **T-009** — ProcessBlock setup / teardown hooks
9. **T-010** — `scieasy.utils.constraints`
10. **T-011** — `scieasy.utils.axis_iter.iterate_over_axes`
11. **T-008** — test migration (Image → Array)
12. **T-012** — `TypeRegistry.resolve` + Meta validation
13. **T-013** — six base-class `_reconstruct_extra_kwargs` /
    `_serialise_extra_metadata` hook pairs
14. **T-014** — worker subprocess typed reconstruction

If parallel work is desired: T-001, T-002, T-003 can be opened
simultaneously off `main`. T-009 can also be opened in parallel with
T-006/T-007 (it touches a different file).

---

## 4. Universal rules for all 14 implementation agents

These rules apply to **every** ticket in this document. Failure to
follow them is a workflow gate violation.

1. **Workflow gate is mandatory** — every ticket follows the full
   6-stage workflow gate per `CLAUDE.md` Appendix A. No exceptions for
   "small" tickets. Each stage must show `[DONE]` in
   `python .workflow/gate.py status <task_id>` before the next stage
   begins.
2. **Branch naming**: `feat/issue-N/T-NNN-short-name` (replace `feat`
   with `fix` for bug-fix tickets). Example for T-001:
   `feat/issue-262/T-001-scheduler-concurrency`.
3. **Stacked PR base** — each PR's base branch is the previous merged
   PR's branch (so the diffs compose cleanly). If the previous PR has
   already merged into `main`, base off `main` directly. Mark stacked
   PRs with the previous PR number in the description.
4. **Out-of-scope changes are forbidden** — the PR's diff must contain
   only the files listed in the ticket's "Files to be created", "Files
   to be modified", "New tests", and "Existing tests to update"
   sections. Any other modified file is a scope violation per
   `CLAUDE.md` §6.7.
5. **Every check must be green before review**:
   - `pytest -x --no-cov` passes locally (use `--no-cov` to bypass the
     project-wide 85% gate during incremental work; CI will run with
     coverage).
   - `ruff check src/ tests/` clean.
   - `ruff format --check src/ tests/` clean.
   - `mypy src/scieasy --ignore-missing-imports` clean.
   - `python -m importlinter --config pyproject.toml` clean (the
     `Core must not depend on blocks/engine/api/ai/workflow` contract is
     load-bearing for several of these tickets).
6. **CHANGELOG.md** must be updated under `[Unreleased]` in the
   appropriate section (`Added` / `Changed` / `Fixed`) with full
   attribution per `CLAUDE.md` Appendix A Stage 6:
   `[#N] Description (@claude, YYYY-MM-DD, branch: ..., session: ...)`.
7. **PR body must reference**:
   - The ADR section the PR implements (e.g. "Implements ADR-027 D6").
   - The ticket ID from this standards doc (e.g. "Per
     `docs/specs/phase10-implementation-standards.md` T-003").
   - The previous PR in the stack (if any).
   - A reproduction of the ticket's acceptance criteria as a checklist
     with each box ticked when satisfied.
8. **No silent scope expansion** — if implementing a ticket reveals a
   pre-existing bug or design ambiguity, open a *new issue* describing
   it. Do not fix it inline. Per `CLAUDE.md` §9.2 ("Claude must not
   silently broaden scope") and Appendix C Step 3 ("If fixing the issue
   reveals a DIFFERENT bug, open a new issue — do not fix it here").

---

## 5. Universal acceptance criteria (apply to ALL 14 tickets)

In addition to each ticket's own acceptance criteria, every ticket must
satisfy these:

1. The PR's diff includes ONLY files listed in "Files to be created",
   "Files to be modified", "New tests", and "Existing tests to update"
   for that ticket. Any other modified file is a scope violation.
2. `pytest -x --no-cov` passes locally before push.
3. `ruff check src/ tests/` clean.
4. `ruff format --check src/ tests/` clean.
5. `mypy src/scieasy --ignore-missing-imports` clean.
6. `CHANGELOG.md` has an entry under `[Unreleased]` in the appropriate
   section with full attribution per `CLAUDE.md` Appendix A Stage 6.
7. Workflow gate has all 6 stages `[DONE]`.
8. PR body explicitly references which ADR section it implements and
   links to this standards doc by ticket ID.
9. PR body reproduces the ticket's per-ticket acceptance criteria as a
   checklist with each item ticked.
10. CI is green on the PR before requesting review.

---

## 6. Open questions resolved by this document

These are decisions made in this document that go *beyond* the ADR text.
The ADRs deferred them to the implementation phase; this section
records the resolution so subsequent agents do not have to re-litigate.

### Question 1: Where do `_reconstruct_one` and `_serialise_one` live?

ADR-027 Addendum 1 §1 leaves this open in the "Rewritten files"
sub-table for `composite.py`, noting: "The recursive delegation needs
an import of `worker._reconstruct_one`, which is acceptable because
composite reconstruction is intrinsically tied to the worker
reconstruction protocol. Alternative: move the helpers into a new
module `scieasy.core.types.serialization` to avoid `core` importing
`engine.runners`."

**Decision: create `src/scieasy/core/types/serialization.py`** as a NEW
module owned by T-014. The two helpers (`_reconstruct_one`,
`_serialise_one`) live there. `worker.py` imports them from
`scieasy.core.types.serialization` instead of defining them locally.
`composite.py`'s `_reconstruct_extra_kwargs` and
`_serialise_extra_metadata` (added by T-013) do
`from scieasy.core.types.serialization import _reconstruct_one,
_serialise_one` *inside the classmethod body* to avoid an import cycle
at module load time.

**Rationale**:
- Keeps the importlinter `Core must not depend on blocks/engine/api/ai/
  workflow` contract clean (verified in `pyproject.toml`).
- Makes the reconstruction logic unit-testable without standing up a
  full subprocess worker harness.
- Co-locates the helpers next to the registry that resolves the type
  chains they consume.

**Impact**: T-014's "Files to be created" list adds
`src/scieasy/core/types/serialization.py`. T-013's `composite.py` patch
uses the inside-the-method import.

### Question 2: How does T-008 handle `tests/integration/test_multimodal_workflow.py`?

ADR-027's "modified files" table for tests says: "Update ~7
instantiations OR move this test into `scieasy-blocks-imaging` as an
integration test that requires all three plugin packages installed.
Phase 10 decision: keep in core repo but mark with a pytest marker
`@pytest.mark.requires_imaging` that is skipped when the plugin is not
installed."

**Decision: skip-via-marker.** T-008 (test migration) does both:

1. Adds a new pytest marker `requires_imaging` registered in
   `pyproject.toml` under `[tool.pytest.ini_options].markers`.
2. Adds a top-of-module fixture / skip directive in
   `tests/integration/test_multimodal_workflow.py` that checks for
   `scieasy_blocks_imaging` importability and skips the whole module if
   absent.
3. Rewrites every `Image(...)` call in that file to
   `Array(axes=[...], ...)` so that, when the plugin lands, the test
   still runs as a generic Array-based smoke test.

**Rationale**: keeps the core repo's CI fully self-contained (no
external plugin dependency) while preserving the test's value once
`scieasy-blocks-imaging` ships. The `requires_imaging` marker becomes a
pattern for other Phase 10+ plugin-dependent tests.

### Question 3: What goes in `scieasy.core.meta` vs. directly under each base class?

ADR-027 D5 lists `core/meta/__init__.py` and `core/meta/framework.py`
as new files in the impact scope but does not enumerate the public
surface beyond `FrameworkMeta`.

**Decision** (already reflected in the PR #261 skeleton):
- `scieasy.core.meta.framework` exports `FrameworkMeta`.
- `scieasy.core.meta.__init__` re-exports `FrameworkMeta`, the
  `with_meta` free-function helper, and `ChannelInfo` (a small frozen
  Pydantic BaseModel used by imaging plugin `Meta` classes).
- `ChannelInfo` lives in core (not in any plugin) so multiple imaging
  plugins can compose it without forcing a plugin → plugin import.
- The `with_meta(obj, **changes)` free function is a thin wrapper
  around `obj.with_meta(**changes)`; both forms are supported.

### Question 4: How is `Array.iter_over` implemented when the source is filesystem-backed (non-Zarr)?

ADR-027 D4 says: "If self.storage_ref is Zarr-backed and supports
partial reads, only the requested chunk(s) are materialised. For other
backends, falls back to self.view().to_memory() then numpy indexing."

**Decision**: T-006 implements the fallback path **first**
(materialise once, slice with numpy). The Zarr-aware partial-read path
is a secondary optimisation inside the same ticket; if Zarr-aware
slicing is non-trivial to land within the T-006 PR size budget, split
it into a follow-up T-006a ticket and document the deferral in the
T-006 PR body. The functional contract is identical (lazy iteration in
the iteration sense, not in the I/O sense), so the deferral does not
break any other ticket.

### Question 5: How does T-009's `ProcessBlock.setup` interact with the existing two-arg `process_item(self, item, config)` signature?

ADR-027 D7 says: "Existing blocks that override `process_item(self,
item, config)` (two-argument form) remain source-compatible because the
new third argument has a default of `None`."

**Decision**: T-009 changes the abstract signature to
`process_item(self, item, config, state=None)` and updates the default
`run()` to call `self.process_item(item, config, state)`. Existing
2-arg overrides continue to work because Python's positional argument
passing tolerates extra trailing positional args only when the override
is keyword-aware. **To be safe**, T-009 also walks every existing
`process_item` override (in `tests/` and in
`src/scieasy/blocks/process/contrib/`) and explicitly accepts `state`
in the signature, even when ignored. This is a one-line change per
override and is in scope for T-009.

---

## 7. Per-ticket sections

Each section uses the same 12 subsections:

a. Ticket ID and name
b. Source ADR sections
c. Files to be created
d. Files to be modified
e. New tests
f. Existing tests to update
g. Implementation details
h. Acceptance criteria
i. Out of scope
j. Dependencies on other tickets
k. Estimated diff size
l. Suggested workflow gate ticket title

---

### T-001 — Scheduler concurrency fix

**a. Ticket ID and name**: T-001 — Scheduler concurrency fix
(`asyncio.create_task` per block).

**b. Source ADR sections**:
- ADR-018 Addendum 1, "Decision" section (whole).
- ADR-018 Addendum 1, "Detailed impact scope → Rewritten files" table
  for `src/scieasy/engine/scheduler.py`.
- ARCHITECTURE.md §6.1 (already updated in PR #257 to describe the
  target behaviour).

**c. Files to be created**: none.

**d. Files to be modified**:
- `src/scieasy/engine/scheduler.py`

**e. New tests**:
- `tests/engine/test_scheduler_concurrency.py` (new file) containing:
  - `test_independent_branches_run_concurrently`
  - `test_resource_throttling_retries_dispatch`
  - `test_scheduler_shutdown_cleanup_on_exception`
  - `test_cancel_block_before_subprocess_starts` (edge case:
    `task.cancel()` path)
  - `test_cancel_block_during_subprocess_run` (normal case:
    `ProcessHandle.terminate()` path)
  - `test_cancel_workflow_with_mix_of_running_and_ready_blocks`

**f. Existing tests to update**:
- `tests/engine/test_scheduler.py` — audit each test for assertions
  that depend on strict serial ordering between *independent* DAG
  branches. Update or rewrite per the rationale recorded in ADR-018
  Addendum 1 discussion row 8 ("Tests that asserted strict sequential
  ordering between independent blocks will fail and must be updated").
- `tests/integration/test_cancel_scenario.py` — audit. Should be
  unaffected because cancellation goes through the same
  `ProcessHandle.terminate()` path.
- `tests/integration/test_multimodal_workflow.py` — audit; if it checks
  output values only, no change. If it checks event ordering between
  independent branches, update.

**g. Implementation details**: split `DAGScheduler._dispatch` into a
synchronous prelude (`_dispatch`) and an async task body
(`_run_and_finalize`) per the ADR-018 Addendum 1 "Decision" section
pseudocode (quoted in full below). Add `self._active_tasks: dict[str,
asyncio.Task[None]] = {}` to `__init__`. Add
`_dispatch_newly_ready()`, called from `_on_block_done` and
`_on_process_exited`. Add `_cancel_active_tasks_on_shutdown()`. Wrap
`execute()` body in `try / finally`. Update `_check_completion()` to
also require `not self._active_tasks`. Update `_on_cancel_block` to
branch on "handle present → terminate" vs "handle absent →
task.cancel()".

Pseudocode quoted from ADR-018 Addendum 1:

```python
async def _dispatch(self, block_id: str) -> None:
    """Synchronous prelude. Does NOT await the runner."""
    if self._paused:
        return
    if not self._resource_manager.can_dispatch(block.resource_request):
        return  # stay READY; retried on next resource release
    self.set_state(block_id, BlockState.RUNNING)
    await self._event_bus.emit(...)
    block = self._instantiate_block(block_id)
    inputs = self._gather_inputs(block_id)
    node = self._dag.nodes[block_id]
    task = asyncio.create_task(
        self._run_and_finalize(block_id, block, inputs, node.config),
        name=f"dispatch:{block_id}",
    )
    self._active_tasks[block_id] = task

async def _run_and_finalize(self, block_id, block, inputs, config) -> None:
    """Long-running task body."""
    try:
        result = await self._runner.run(block, inputs, config)
        self._block_outputs[block_id] = result
        self.set_state(block_id, BlockState.DONE)
        await self._event_bus.emit(EngineEvent(BLOCK_DONE, ...))
    except Exception as exc:
        if self._block_states.get(block_id) == BlockState.CANCELLED:
            return
        self.set_state(block_id, BlockState.ERROR)
        await self._event_bus.emit(EngineEvent(BLOCK_ERROR, ...))
    finally:
        self._active_tasks.pop(block_id, None)

async def _dispatch_newly_ready(self) -> None:
    for node_id in self._order:
        state = self._block_states[node_id]
        if state == BlockState.IDLE and self._check_readiness(node_id):
            self._block_states[node_id] = BlockState.READY
            await self._dispatch(node_id)
        elif state == BlockState.READY and node_id not in self._active_tasks:
            await self._dispatch(node_id)

def _check_completion(self) -> None:
    terminal = {BlockState.DONE, BlockState.ERROR,
                BlockState.CANCELLED, BlockState.SKIPPED}
    if all(s in terminal for s in self._block_states.values()) \
            and not self._active_tasks:
        self._completed_event.set()

async def execute(self) -> None:
    await self._event_bus.emit(EngineEvent(WORKFLOW_STARTED, ...))
    if not self._dag.nodes:
        self._completed_event.set()
        await self._event_bus.emit(EngineEvent(WORKFLOW_COMPLETED, ...))
        return
    try:
        for node_id in self._order:
            if self._block_states[node_id] == BlockState.IDLE \
                    and self._check_readiness(node_id):
                self._block_states[node_id] = BlockState.READY
                await self._dispatch(node_id)
        await self._completed_event.wait()
    finally:
        await self._cancel_active_tasks_on_shutdown()
    await self._event_bus.emit(EngineEvent(WORKFLOW_COMPLETED, ...))

async def _cancel_active_tasks_on_shutdown(self) -> None:
    for block_id, task in list(self._active_tasks.items()):
        handle = self._process_registry.get_handle(block_id) \
            if self._process_registry else None
        if handle is not None:
            try:
                handle.terminate()
            except Exception:
                logger.exception("Shutdown: failed to terminate %s", block_id)
        if not task.done():
            task.cancel()
            try:
                await task
            except BaseException:
                pass
```

**h. Acceptance criteria**:
- [ ] `DAGScheduler.__init__` declares `self._active_tasks: dict[str,
      asyncio.Task[None]] = {}` (ADR-018 Addendum 1 Decision §"New
      scheduler field").
- [ ] `DAGScheduler._dispatch` does NOT await `self._runner.run` —
      it creates an `asyncio.Task` and returns (ADR-018 Addendum 1
      Decision item 1).
- [ ] `DAGScheduler._run_and_finalize` exists and is the body that
      awaits `self._runner.run`, transitions to DONE / ERROR, emits the
      terminal event, and pops from `_active_tasks` in `finally`
      (ADR-018 Addendum 1 Decision item 2).
- [ ] `DAGScheduler._check_completion` requires both "all terminal"
      AND "no active tasks" (ADR-018 Addendum 1 Decision §`_check_completion`).
- [ ] `DAGScheduler.execute` body wraps in `try / finally` calling
      `_cancel_active_tasks_on_shutdown` (ADR-018 Addendum 1 Decision
      §`execute`).
- [ ] `_dispatch_newly_ready` is called from `_on_block_done` and
      `_on_process_exited` (ADR-018 Addendum 1 Decision §`_on_block_done`).
- [ ] `_on_cancel_block` branches on `process_registry.get_handle()`
      result: terminate the subprocess if a handle exists, otherwise
      `task.cancel()` (ADR-018 Addendum 1 Decision §`_on_cancel_block`).
- [ ] `test_independent_branches_run_concurrently` asserts wall-clock
      time of two `sleep(N)` independent blocks is `≈ N`, not `≈ 2N`.
- [ ] `test_resource_throttling_retries_dispatch` asserts that with
      `gpu_slots=1` and two GPU blocks, the second enters RUNNING only
      after the first completes (ADR-018 Addendum 1 Decision item 5).
- [ ] `test_scheduler_shutdown_cleanup_on_exception` asserts
      `_active_tasks` is empty and all subprocesses are terminated
      after `execute()` returns under an exception path.

**i. Out of scope**:
- No new `BlockState` values, no new event types, no changes to the
  EventBus subscription matrix.
- No changes to `ProcessHandle` / `ProcessRegistry` /
  `spawn_block_process` (ADR-019 remains authoritative).
- No changes to `BlockRunner` / `LocalRunner` (ADR-017 remains
  authoritative). The `await asyncio.to_thread(popen.communicate, ...)`
  inside `LocalRunner` already does the right thing; the bug is in
  `DAGScheduler` not in `LocalRunner`.
- No changes to `Collection`, `ViewProxy`, or storage backends.
- No "deterministic mode" / `sequential: bool` flag (deferred per
  ADR-018 Addendum 1 Alternatives Considered).

**j. Dependencies on other tickets**: none. Independent of every other
Phase 10 ticket and can land first.

**k. Estimated diff size**: ~150 source lines changed in
`scheduler.py`. ~250 lines of new tests in
`test_scheduler_concurrency.py`. ~30 lines of audit-driven changes in
`test_scheduler.py`. Total ~430 lines.

**l. Suggested workflow gate ticket title**:
`Scheduler concurrency fix per ADR-018 Addendum 1 (T-001)`

---

### T-002 — ResourceManager GPU auto-detect

**a. Ticket ID and name**: T-002 — ResourceManager GPU auto-detect.

**b. Source ADR sections**:
- ADR-027 D10 (whole subsection).
- ADR-027 discussion row 15.
- ARCHITECTURE.md §6.4 (already updated in PR #257).

**c. Files to be created**: none.

**d. Files to be modified**:
- `src/scieasy/engine/resources.py`

**e. New tests**:
- `tests/engine/test_resource_manager_gpu_autodetect.py` (new file)
  containing:
  - `test_gpu_slots_none_triggers_auto_detect`
  - `test_auto_detect_uses_torch_when_available`
  - `test_auto_detect_falls_back_to_nvidia_smi`
  - `test_auto_detect_returns_zero_when_no_gpu`
  - `test_explicit_integer_overrides_auto_detect`
  - `test_warning_logged_when_zero_slots_but_gpu_block_dispatched`

**f. Existing tests to update**:
- `tests/engine/test_resources.py` — audit any test that constructs
  `ResourceManager()` with the implicit `gpu_slots=0`. Update to pass
  `gpu_slots=0` explicitly so the auto-detect path is not exercised
  when not under test.

**g. Implementation details**:

```python
class ResourceManager:
    def __init__(
        self,
        gpu_slots: int | None = None,         # was: int = 0
        cpu_workers: int = 4,
        memory_high_watermark: float = 0.80,
        memory_critical: float = 0.95,
        event_bus: Any | None = None,
    ) -> None:
        if gpu_slots is None:
            gpu_slots = _auto_detect_gpu_slots()
        self.gpu_slots = gpu_slots
        ...

def _auto_detect_gpu_slots() -> int:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.device_count()
    except ImportError:
        pass
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "-L"], capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return sum(1 for line in result.stdout.splitlines()
                       if line.startswith("GPU "))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return 0
```

When `gpu_slots == 0` after auto-detect AND a block declaring
`requires_gpu=True` is encountered, log one WARNING explaining the
override path. Use a module-level "warned-once" flag so the warning is
not spammed.

**h. Acceptance criteria**:
- [ ] `ResourceManager.__init__` signature changes the default of
      `gpu_slots` from `0` to `None` (ADR-027 D10).
- [ ] `_auto_detect_gpu_slots` function exists at module level
      (ADR-027 D10 pseudocode).
- [ ] `_auto_detect_gpu_slots` tries `torch.cuda.device_count()` first
      (ADR-027 D10 §"Best-effort GPU count detection").
- [ ] `_auto_detect_gpu_slots` falls back to `nvidia-smi -L` parsing
      (ADR-027 D10).
- [ ] `_auto_detect_gpu_slots` returns `0` if neither is available
      (ADR-027 D10).
- [ ] Explicit integer values passed to `__init__` are respected
      unchanged (ADR-027 D10).
- [ ] One-time WARNING is logged when `gpu_slots == 0` after
      auto-detect AND a `requires_gpu=True` block dispatch is attempted
      (ADR-027 D10).
- [ ] `test_explicit_integer_overrides_auto_detect` asserts that
      `ResourceManager(gpu_slots=2)` does NOT call
      `_auto_detect_gpu_slots`.

**i. Out of scope**:
- No VRAM-aware slot calculation. Physical GPU count only (ADR-027 D10
  caveat).
- No `pynvml` dependency.
- No per-GPU slot tracking (the `gpu_slots` field remains an integer
  count, not a list of GPU indices).

**j. Dependencies on other tickets**: none.

**k. Estimated diff size**: ~30 source lines added in `resources.py`.
~120 lines of new tests. Total ~150 lines.

**l. Suggested workflow gate ticket title**:
`ResourceManager GPU auto-detect per ADR-027 D10 (T-002)`

---

### T-003 — PhysicalQuantity

**a. Ticket ID and name**: T-003 — PhysicalQuantity dataclass + Pydantic
v2 integration.

**b. Source ADR sections**:
- ADR-027 D6 (PhysicalQuantity definition + unit tables).
- ADR-027 Addendum 1 §4 ("PhysicalQuantity Pydantic integration").

**c. Files to be created**: none. (`src/scieasy/core/units.py` was
created as a skeleton in PR #261.)

**d. Files to be modified**:
- `src/scieasy/core/units.py` — fill in the skeleton.

**e. New tests**:
- `tests/core/test_units.py` (new file) containing:
  - `test_construction_with_known_unit_succeeds`
  - `test_construction_with_unknown_unit_raises_value_error`
  - `test_to_within_kind_converts_correctly` (e.g.
    `Q(1.0, "m").to("mm") == Q(1000.0, "mm")`)
  - `test_to_cross_kind_raises_value_error`
  - `test_lt_compares_after_normalising`
  - `test_lt_cross_kind_raises_type_error`
  - `test_eq_within_kind_with_epsilon`
  - `test_eq_cross_kind_returns_false`
  - `test_eq_with_non_pq_returns_not_implemented`
  - `test_hash_consistent_with_eq`
  - `test_physical_quantity_pydantic_round_trip` (per Addendum 1 §4 +
    "Tests" sub-table).
  - `test_physical_quantity_inside_basemodel_serialises_as_dict`

**f. Existing tests to update**: none.

**g. Implementation details**: replace the `NotImplementedError`
placeholders in `src/scieasy/core/units.py` with the implementation
quoted in ADR-027 D6:

```python
_LENGTH   = {"m": 1.0, "mm": 1e-3, "um": 1e-6, "nm": 1e-9, "pm": 1e-12, "A": 1e-10}
_TIME     = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "min": 60.0, "hr": 3600.0}
_FREQ     = {"Hz": 1.0, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}
_WAVENUM  = {"cm-1": 100.0, "m-1": 1.0}

_KIND = {
    **{u: "length"     for u in _LENGTH},
    **{u: "time"       for u in _TIME},
    **{u: "freq"       for u in _FREQ},
    **{u: "wavenumber" for u in _WAVENUM},
}
_SCALE = {**_LENGTH, **_TIME, **_FREQ, **_WAVENUM}

@dataclass(frozen=True)
class PhysicalQuantity:
    value: float
    unit: str

    def __post_init__(self) -> None:
        if self.unit not in _SCALE:
            raise ValueError(f"Unknown unit: {self.unit!r}")

    def to(self, target_unit: str) -> "PhysicalQuantity":
        if _KIND[self.unit] != _KIND[target_unit]:
            raise ValueError(f"Cannot convert {_KIND[self.unit]} to {_KIND[target_unit]}")
        return PhysicalQuantity(
            self.value * _SCALE[self.unit] / _SCALE[target_unit],
            target_unit,
        )

    def __lt__(self, other: "PhysicalQuantity") -> bool:
        if _KIND[self.unit] != _KIND[other.unit]:
            raise TypeError("Incompatible kinds")
        return self.value * _SCALE[self.unit] < other.value * _SCALE[other.unit]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PhysicalQuantity):
            return NotImplemented
        if _KIND[self.unit] != _KIND[other.unit]:
            return False
        return abs(self.value * _SCALE[self.unit] - other.value * _SCALE[other.unit]) < 1e-12
```

The Pydantic v2 integration (Addendum 1 §4):

```python
from pydantic_core import core_schema
from pydantic import GetCoreSchemaHandler

class PhysicalQuantity:
    ...

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        def _validate(v: Any) -> "PhysicalQuantity":
            if isinstance(v, PhysicalQuantity):
                return v
            if isinstance(v, dict) and "value" in v and "unit" in v:
                return cls(value=float(v["value"]), unit=str(v["unit"]))
            raise ValueError(
                f"PhysicalQuantity expects {{value, unit}} dict or "
                f"PhysicalQuantity, got {type(v).__name__}"
            )

        return core_schema.no_info_plain_validator_function(
            _validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda obj: {"value": obj.value, "unit": obj.unit},
                return_schema=core_schema.dict_schema(),
            ),
        )
```

`__hash__` must be consistent with the custom `__eq__`. Implement as
`hash((self.value * _SCALE[self.unit], _KIND[self.unit]))` so that
`Q(1.0, "m") == Q(1000.0, "mm")` implies they hash equal.

**h. Acceptance criteria**:
- [ ] `_LENGTH`, `_TIME`, `_FREQ`, `_WAVENUM`, `_KIND`, `_SCALE`
      module-level dicts populated per ADR-027 D6 §"unit tables".
- [ ] `PhysicalQuantity.__post_init__` raises
      `ValueError("Unknown unit: ...")` for unknown units (ADR-027 D6).
- [ ] `PhysicalQuantity.to(target_unit)` returns a new
      `PhysicalQuantity` of the same kind, raises `ValueError` for
      cross-kind (ADR-027 D6).
- [ ] `PhysicalQuantity.__lt__` raises `TypeError` for cross-kind
      comparison (ADR-027 D6).
- [ ] `PhysicalQuantity.__eq__` returns `False` (not raise) for
      cross-kind, returns `NotImplemented` for non-PQ inputs (ADR-027 D6).
- [ ] `PhysicalQuantity.__hash__` is consistent with `__eq__`
      (`Q(1.0, "m")` and `Q(1000.0, "mm")` hash equal).
- [ ] `PhysicalQuantity.__get_pydantic_core_schema__` returns a Pydantic
      v2 core schema accepting either an instance or a `{"value", "unit"}`
      dict (ADR-027 Addendum 1 §4 pseudocode).
- [ ] `BaseModel(field=Q(0.108, "um")).model_dump_json()` produces
      `{"field": {"value": 0.108, "unit": "um"}}` (ADR-027 Addendum 1
      §4 — `test_physical_quantity_pydantic_round_trip`).
- [ ] `BaseModel.model_validate({"field": {"value": 0.108, "unit":
      "um"}})` returns a model whose `field` is a `PhysicalQuantity`
      instance.

**i. Out of scope**:
- No `pint` integration (ADR-027 D6 explicitly rejects this for
  Phase 10).
- No dimensional algebra (`Q(2.0, "m") + Q(3.0, "mm")`).
- No new units beyond the four kinds in ADR-027 D6.

**j. Dependencies on other tickets**: none directly. T-004 references
`ChannelInfo` which itself references `PhysicalQuantity` indirectly via
the imaging plugin examples in the SDK doc, but the `core.meta` module
itself does not import `PhysicalQuantity`.

**k. Estimated diff size**: ~120 source lines in `units.py` (including
the Pydantic integration and docstrings). ~200 lines of tests. Total
~320 lines.

**l. Suggested workflow gate ticket title**:
`PhysicalQuantity per ADR-027 D6 + Addendum 1 §4 (T-003)`

---

### T-004 — FrameworkMeta + scieasy.core.meta module

**a. Ticket ID and name**: T-004 — `FrameworkMeta` + `scieasy.core.meta`
public surface.

**b. Source ADR sections**:
- ADR-027 D5 (FrameworkMeta definition).
- ADR-027 "Detailed impact scope → New files" rows for
  `core/meta/__init__.py` and `core/meta/framework.py`.

**c. Files to be created**: none. (`src/scieasy/core/meta/framework.py`
and `src/scieasy/core/meta/__init__.py` were created as skeletons in
PR #261.)

**d. Files to be modified**:
- `src/scieasy/core/meta/framework.py` — fill in the skeleton.
- `src/scieasy/core/meta/__init__.py` — fill in `ChannelInfo` and
  `with_meta` (the latter remains a thin wrapper since the bulk of the
  logic lives on `DataObject` after T-005).

**e. New tests**:
- `tests/core/test_framework_meta.py` (new file) containing:
  - `test_framework_meta_default_factory_object_id_unique`
  - `test_framework_meta_default_factory_created_at_recent`
  - `test_framework_meta_frozen_raises_on_assignment`
  - `test_framework_meta_derive_returns_new_instance_with_derived_from`
  - `test_framework_meta_derive_overrides_via_kwargs`
  - `test_framework_meta_json_round_trip`
  - `test_channel_info_construction_and_round_trip`
  - `test_with_meta_helper_calls_dataobject_method` (uses a mock —
    DataObject side is implemented in T-005)

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
# scieasy/core/meta/framework.py

from datetime import datetime
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field

class FrameworkMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    object_id: str        = Field(default_factory=lambda: uuid4().hex)
    source: str           = ""
    lineage_id: str | None = None
    derived_from: str | None = None

    def derive(self, **changes: Any) -> "FrameworkMeta":
        """Per ADR-027 D5 propagation rule: fresh object_id, fresh
        created_at, derived_from set to the parent's object_id, other
        fields inherited unless overridden."""
        return type(self)(
            created_at=changes.pop("created_at", datetime.utcnow()),
            object_id=changes.pop("object_id", uuid4().hex),
            source=changes.pop("source", self.source),
            lineage_id=changes.pop("lineage_id", self.lineage_id),
            derived_from=changes.pop("derived_from", self.object_id),
            **changes,
        )
```

```python
# scieasy/core/meta/__init__.py — ChannelInfo

from pydantic import BaseModel, ConfigDict

class ChannelInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    excitation_nm: float | None = None
    emission_nm:   float | None = None
    color:         str | None = None
```

`with_meta(obj, **changes)` remains a thin wrapper:

```python
def with_meta(obj: "DataObject", **changes: Any) -> "DataObject":
    return obj.with_meta(**changes)
```

The actual immutable-update logic on `DataObject` is implemented in
T-005.

**h. Acceptance criteria**:
- [ ] `FrameworkMeta` is a `pydantic.BaseModel` with
      `model_config = ConfigDict(frozen=True)` (ADR-027 D5).
- [ ] `FrameworkMeta` declares all five fields (`created_at`,
      `object_id`, `source`, `lineage_id`, `derived_from`) per ADR-027
      D5 spec.
- [ ] `created_at` and `object_id` use `Field(default_factory=...)` so
      every instance gets a fresh value.
- [ ] `FrameworkMeta.derive(**changes)` returns a new instance with
      `derived_from = self.object_id`, fresh `created_at` and
      `object_id`, inherited `source` and `lineage_id` unless
      overridden (ADR-027 D5 propagation rule).
- [ ] `FrameworkMeta` round-trips through `model_dump_json()` /
      `model_validate_json()`.
- [ ] `ChannelInfo` is a frozen Pydantic BaseModel with the four
      fields (`name`, `excitation_nm`, `emission_nm`, `color`).
- [ ] `with_meta(obj, **changes)` free function delegates to
      `obj.with_meta(**changes)`.

**i. Out of scope**:
- The `DataObject` side of the three-slot model (lives in T-005).
- Any plugin-specific `Meta` classes (live in plugin packages).
- Migrating existing `metadata` callers to `user` (out of scope here;
  the deprecation shim is part of T-005).

**j. Dependencies on other tickets**:
- T-003 (PhysicalQuantity) is recommended to merge first so the
  ChannelInfo docs can reference it, though there is no hard import
  dependency from `scieasy.core.meta` to `scieasy.core.units`.

**k. Estimated diff size**: ~80 source lines (40 in `framework.py`, 40
in `__init__.py`). ~150 lines of tests. Total ~230 lines.

**l. Suggested workflow gate ticket title**:
`FrameworkMeta and scieasy.core.meta per ADR-027 D5 (T-004)`

---

### T-005 — DataObject three-slot metadata

**a. Ticket ID and name**: T-005 — DataObject three-slot metadata
(framework / meta / user).

**b. Source ADR sections**:
- ADR-027 D5 (whole subsection).
- ADR-027 "Detailed impact scope → Rewritten files" row for
  `src/scieasy/core/types/base.py`.

**c. Files to be created**: none.

**d. Files to be modified**:
- `src/scieasy/core/types/base.py`

**e. New tests**:
- `tests/core/test_stratified_metadata.py` (new file) containing:
  - `test_dataobject_init_accepts_framework_meta_user`
  - `test_dataobject_framework_default_auto_populated`
  - `test_dataobject_meta_default_is_empty_basemodel`
  - `test_dataobject_user_default_is_empty_dict`
  - `test_with_meta_returns_new_instance_with_changed_meta`
  - `test_with_meta_preserves_framework_user_storage_ref`
  - `test_metadata_property_returns_user_with_deprecation_warning`
  - `test_dataobject_json_round_trip_three_slots`

**f. Existing tests to update**:
- `tests/core/test_dataobject_extended.py` — audit any test that uses
  the legacy `metadata=` kwarg. Add coverage for the new
  three-slot constructor while keeping the deprecation-shim test as a
  regression guard.
- `tests/core/test_data_object_persistence.py` — same audit.

**g. Implementation details**:

```python
# scieasy/core/types/base.py

from pydantic import BaseModel
from scieasy.core.meta import FrameworkMeta

class DataObject:
    def __init__(
        self,
        *,
        framework: FrameworkMeta | None = None,
        meta: BaseModel | None = None,
        user: dict[str, Any] | None = None,
        storage_ref: "StorageReference | None" = None,
        # legacy kwarg, deprecated:
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if metadata is not None:
            warnings.warn(
                "DataObject(metadata=...) is deprecated since Phase 10. "
                "Use the typed three-slot model: framework=, meta=, user=.",
                DeprecationWarning,
                stacklevel=2,
            )
            if user is None:
                user = dict(metadata)
        self.framework = framework or FrameworkMeta()
        self.meta = meta or BaseModel()
        self.user = dict(user or {})
        self.storage_ref = storage_ref

    def with_meta(self, **changes: Any) -> "Self":
        new_meta = self.meta.model_copy(update=changes)
        return type(self)(
            framework=self.framework,
            meta=new_meta,
            user=dict(self.user),
            storage_ref=self.storage_ref,
        )

    @property
    def metadata(self) -> dict[str, Any]:
        warnings.warn(
            "DataObject.metadata is deprecated since Phase 10; "
            "use .user (free dict) or .meta (typed Pydantic model).",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.user
```

The `TypeSignature.from_type` update is also part of T-005: ensure the
signature carries `required_axes` when the class declares them. (For
the base `DataObject` this is a no-op; the actual `required_axes`
attribute is added on `Array` in T-006.)

**h. Acceptance criteria**:
- [ ] `DataObject.__init__` accepts `framework`, `meta`, `user`,
      `storage_ref` as keyword arguments (ADR-027 D5).
- [ ] When `framework=None`, a fresh `FrameworkMeta()` is created
      (ADR-027 D5).
- [ ] When `meta=None`, a default `BaseModel()` instance is used
      (ADR-027 D5).
- [ ] When `user=None`, an empty dict is used.
- [ ] `DataObject.with_meta(**changes)` returns a new instance with
      `meta = self.meta.model_copy(update=changes)` and other slots
      preserved (ADR-027 D5 §`with_meta`).
- [ ] Legacy `DataObject(metadata=...)` kwarg accepted with a
      `DeprecationWarning` and copied into `user`.
- [ ] `DataObject.metadata` is a property returning `self.user` and
      emitting a `DeprecationWarning` (ADR-027 D5 §"Backward-compat
      shim").
- [ ] The three slots round-trip through Pydantic
      `model_dump_json` / `model_validate_json` end-to-end.

**i. Out of scope**:
- Per-subclass `Meta` definitions (live in plugin packages).
- The `_reconstruct_extra_kwargs` / `_serialise_extra_metadata`
  classmethods (added in T-013).
- The worker subprocess reconstruction (T-014).
- Removing the deprecation shim (post-Phase 11; not now).

**j. Dependencies on other tickets**:
- T-004 (FrameworkMeta) must merge first.

**k. Estimated diff size**: ~80 source lines in `base.py`. ~200 lines
of tests. Total ~280 lines.

**l. Suggested workflow gate ticket title**:
`DataObject three-slot metadata per ADR-027 D5 (T-005)`

---

### T-006 — Array 6D instance-level axes + sel / iter\_over

**a. Ticket ID and name**: T-006 — Array 6D instance-level axes + `sel`
+ `iter_over`.

**b. Source ADR sections**:
- ADR-027 D1 (instance-level axes).
- ADR-027 D4 (`sel` and `iter_over`).
- ADR-027 "Detailed impact scope → Rewritten files" row for
  `src/scieasy/core/types/array.py`.
- ARCHITECTURE.md §4.1 (named axes on Array — already in PR #257).

**c. Files to be created**: none.

**d. Files to be modified**:
- `src/scieasy/core/types/array.py`

**e. New tests**:
- `tests/core/test_array_axes.py` (new file) containing:
  - `test_array_init_accepts_instance_axes`
  - `test_array_init_validates_required_axes`
  - `test_array_init_validates_allowed_axes`
  - `test_array_init_rejects_duplicate_axes`
  - `test_array_5d_instantiation`
  - `test_array_6d_instantiation_with_lambda_and_c`
  - `test_sel_single_index_removes_axis`
  - `test_sel_slice_keeps_axis`
  - `test_sel_metadata_propagation_per_d5`
  - `test_iter_over_yields_correct_count`
  - `test_iter_over_each_slice_has_axis_removed`
  - `test_iter_over_metadata_inheritance`

**f. Existing tests to update**:
- `tests/core/test_types.py` — add coverage for the new constructor
  shape but DO NOT remove existing `Image()`-using tests (those move to
  T-008).
- `tests/architecture/test_type_system.py` — audit for any `axes:
  ClassVar` assertion; update or remove.

**g. Implementation details**:

```python
# scieasy/core/types/array.py

class Array(DataObject):
    required_axes:   ClassVar[frozenset[str]] = frozenset()
    allowed_axes:    ClassVar[frozenset[str] | None] = None
    canonical_order: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        *,
        axes: list[str],
        shape: tuple[int, ...] | None = None,
        dtype: Any = None,
        chunk_shape: tuple[int, ...] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.axes = list(axes)
        self.shape = shape
        self.dtype = dtype
        self.chunk_shape = chunk_shape
        self._validate_axes()

    def _validate_axes(self) -> None:
        axes_set = set(self.axes)
        if not self.required_axes.issubset(axes_set):
            missing = self.required_axes - axes_set
            raise ValueError(
                f"{type(self).__name__} requires axes {sorted(self.required_axes)}, "
                f"missing: {sorted(missing)}"
            )
        if self.allowed_axes is not None and not axes_set.issubset(self.allowed_axes):
            extra = axes_set - self.allowed_axes
            raise ValueError(
                f"{type(self).__name__} accepts only {sorted(self.allowed_axes)}, "
                f"unexpected: {sorted(extra)}"
            )
        if len(set(self.axes)) != len(self.axes):
            raise ValueError(f"Duplicate axes in {self.axes}")

    def sel(self, **kwargs: int | slice) -> "Array":
        """ADR-027 D4: select sub-array along named axes."""
        # Build numpy index tuple in axis order, removing scalar-indexed axes
        # Construct new instance with reduced axes/shape and propagated meta
        ...

    def iter_over(self, axis: str) -> Iterator["Array"]:
        """ADR-027 D4: yield sub-arrays along one named axis."""
        if axis not in self.axes:
            raise ValueError(f"Axis {axis!r} not in {self.axes}")
        size = self.shape[self.axes.index(axis)]
        for k in range(size):
            yield self.sel(**{axis: k})
```

Metadata propagation in `sel`:

```python
new_framework = self.framework.derive()
new_meta      = self.meta              # shared by reference
new_user      = dict(self.user)        # shallow copy
new_axes      = [a for a in self.axes if isinstance(kwargs.get(a), slice)
                 or a not in kwargs]
```

Note that `_validate_axes` should not run on the *result* of `sel` if
the result removes a required axis — `sel`'s contract is "select a
sub-array", which is allowed to violate the source class's
`required_axes` invariant. **Decision**: `sel` returns an instance of
`type(self)` only when the resulting axes still satisfy
`required_axes`. Otherwise it returns a base `Array` instance with the
reduced axes. Document this in the `sel` docstring.

**h. Acceptance criteria**:
- [ ] `Array.required_axes`, `Array.allowed_axes`,
      `Array.canonical_order` exist as ClassVars (defaults: empty
      / `None` / `()`) per ADR-027 D1.
- [ ] `Array.__init__` requires `axes` as a keyword argument.
- [ ] `_validate_axes` raises `ValueError` for missing required,
      excess unallowed, or duplicate axes per ADR-027 D1 pseudocode.
- [ ] 5D instantiation `Array(axes=["t","z","c","y","x"], shape=(...))`
      succeeds.
- [ ] 6D instantiation with `lambda` and `c` coexisting succeeds
      (ADR-027 discussion #3).
- [ ] `Array.sel(z=15, c=0)` returns an instance with `z` and `c`
      removed from `axes`; `Array.sel(z=slice(10, 20))` keeps `z` in
      `axes`.
- [ ] `Array.iter_over("z")` yields `shape["z"]` sub-arrays, each
      missing `z` from its axes.
- [ ] Metadata propagation in `sel` and `iter_over` follows ADR-027 D5:
      framework derived, meta shared, user shallow-copied.
- [ ] `TypeSignature.from_type(Array)` includes `required_axes`
      (ADR-027 D1 §"Domain subtypes").

**i. Out of scope**:
- Defining any domain subclasses (`Image`, `FluorImage`, etc.) — they
  live in `scieasy-blocks-imaging`, not core (ADR-027 D2).
- Deleting any existing core domain subclasses — that audit is T-007.
- Test migration — that is T-008.
- Level 2 laziness (`SlicedStorageReference` carried through ViewProxy)
  — explicitly deferred to Phase 11+ (ADR-027 D4 discussion #6).
- Updating existing built-in blocks that reference `Image` — that
  audit is T-007.

**j. Dependencies on other tickets**:
- T-005 (DataObject three-slot metadata) must merge first.

**k. Estimated diff size**: ~150 source lines added/changed in
`array.py` (the existing class is ~84 lines; the new shape is ~200
lines including `sel`/`iter_over`/`_validate_axes`). ~300 lines of
tests. Total ~450 lines.

**l. Suggested workflow gate ticket title**:
`Array 6D instance-level axes + sel/iter_over per ADR-027 D1 D4 (T-006)`

---

### T-007 — Other base classes audit

**a. Ticket ID and name**: T-007 — audit `series.py`, `dataframe.py`,
`composite.py`, `text.py`, `artifact.py` for domain subtypes; remove
any that exist; ensure each base class is the only class in its module.

**b. Source ADR sections**:
- ADR-027 D2 (whole).
- ADR-027 "Detailed impact scope → Rewritten files" rows for
  `series.py`, `dataframe.py`, `composite.py`.

**c. Files to be created**: none.

**d. Files to be modified**:
- `src/scieasy/core/types/series.py`
- `src/scieasy/core/types/dataframe.py`
- `src/scieasy/core/types/composite.py`
- `src/scieasy/core/types/text.py`
- `src/scieasy/core/types/artifact.py`
- `src/scieasy/core/types/__init__.py` — update re-exports.

**e. New tests**:
- `tests/architecture/test_core_has_no_domain_types.py` (new file)
  containing:
  - `test_array_module_has_only_array_class`
  - `test_series_module_has_only_series_class`
  - `test_dataframe_module_has_only_dataframe_class`
  - `test_composite_module_has_only_compositedata_class`
  - `test_text_module_has_only_text_class`
  - `test_artifact_module_has_only_artifact_class`

  These use `inspect.getmembers` + a hard-coded allowlist per module.

**f. Existing tests to update**:
- `tests/architecture/test_type_system.py` — add the post-Phase 10
  invariant: "exactly seven public DataObject subclasses live in
  `scieasy.core.types`".

**g. Implementation details**: this is largely a deletion ticket. For
each module, audit for any domain subclass definition and remove. The
`array.py` file's `Image` / `MSImage` / `SRSImage` / `FluorImage`
deletion is part of T-006 (it ships with the new shape of `Array`),
but the other five files may also have legacy domain subclasses that
need to go.

After deletion, every module should contain exactly one public class:
the base class. Update `core/types/__init__.py` to re-export only the
seven base types.

**h. Acceptance criteria**:
- [ ] `src/scieasy/core/types/series.py` defines exactly one public
      class: `Series` (ADR-027 D2).
- [ ] `src/scieasy/core/types/dataframe.py` defines exactly one public
      class: `DataFrame` (ADR-027 D2).
- [ ] `src/scieasy/core/types/composite.py` defines exactly one public
      class: `CompositeData` (ADR-027 D2).
- [ ] `src/scieasy/core/types/text.py` defines exactly one public
      class: `Text` (ADR-027 D2).
- [ ] `src/scieasy/core/types/artifact.py` defines exactly one public
      class: `Artifact` (ADR-027 D2).
- [ ] `scieasy.core.types.__all__` lists exactly the seven base types
      plus `Collection` and `TypeRegistry` (no domain subclasses).
- [ ] `test_core_has_no_domain_types.py` passes.

**i. Out of scope**:
- Creating the plugin packages (`scieasy-blocks-imaging`,
  `scieasy-blocks-spectral`, etc.). They are separate repositories.
- Migrating existing tests that reference `Image` / `Spectrum` etc.
  That is T-008.
- Updating built-in blocks that have `accepted_types=[Image]`. That
  is part of T-008's audit (rename to `accepted_types=[Array]` with
  optional constraint helpers from `scieasy.utils.constraints`).

**j. Dependencies on other tickets**:
- T-006 must merge first (so `array.py` is in its final shape).

**k. Estimated diff size**: ~50 source lines deleted across five
modules. ~150 lines of new architecture tests. Total ~200 lines net.

**l. Suggested workflow gate ticket title**:
`Audit core base classes for domain subtypes per ADR-027 D2 (T-007)`

---

### T-008 — Test migration: replace `Image()` with `Array(axes=[...])`

**a. Ticket ID and name**: T-008 — Test migration: replace `Image()`
with `Array(axes=[...], ...)` across the test suite.

**b. Source ADR sections**:
- ADR-027 D2 (consequence — "tests under `tests/blocks/` that
  `from scieasy.core.types.array import Image` must either switch to
  `Array` or be marked as requiring `scieasy-blocks-imaging` installed").
- ADR-027 "Detailed impact scope → Modified files" tests sub-table.

**c. Files to be created**: none.

**d. Files to be modified**:
- `pyproject.toml` — register the `requires_imaging` pytest marker
  under `[tool.pytest.ini_options].markers`.

**e. New tests**: none. (T-008 is a migration ticket, not a new-test
ticket.)

**f. Existing tests to update** (counts come from ADR-027's tests
sub-table; the implementation agent must verify each count when
opening the PR):
- `tests/core/test_types.py` — ~3 instantiations.
- `tests/core/test_dataobject_extended.py` — ~1 instantiation.
- `tests/core/test_composite.py` — ~1 instantiation.
- `tests/core/test_proxy.py` — ~1 instantiation.
- `tests/core/test_collection.py` — ~21 instantiations (largest).
- `tests/blocks/test_block_base.py` — ~16 instantiations.
- `tests/blocks/test_collection_blocks.py` — ~1 instantiation.
- `tests/blocks/test_adapters.py` — ~1 instantiation. (May move
  entirely to imaging plugin tests in a future ticket.)
- `tests/blocks/test_ports.py` — ~3 instantiations.
- `tests/blocks/test_lazy_list.py` — ~3 instantiations.
- `tests/blocks/test_app_block.py` — ~2 instantiations.
- `tests/engine/test_checkpoint.py` — ~7 instantiations.
- `tests/integration/test_block_sdk_e2e.py` — ~1 instantiation.
- `tests/integration/test_multimodal_workflow.py` — ~7 instantiations
  AND add the `@pytest.mark.requires_imaging` skip-via-marker per
  Question 2 above.
- `tests/api/test_data.py` — ~1 instantiation.
- `tests/workflow/test_validator.py` — `from scieasy.core.types.array
  import Array, Image` → `Array` only.
- `tests/ai/test_validator.py` — ~4 instantiations. AI validator tests
  verify the "you cannot import Image from core" rule, which is now
  enforced by T-007 deletion.
- `tests/ai/test_type_generator.py` — ~2 instantiations.

**g. Implementation details**: each `Image(...)` call becomes
`Array(axes=["y", "x"], ...)` for the 2D case, or
`Array(axes=["t","z","c","y","x"], ...)` for higher-dim cases. Where
the original test passed `Image` to a port's `accepted_types=`, replace
with `accepted_types=[Array]` plus an optional
`constraint=has_axes("y","x")` from `scieasy.utils.constraints`.

`tests/integration/test_multimodal_workflow.py` gets the
`requires_imaging` skip directive at the top of the module:

```python
import pytest
pytest.importorskip("scieasy_blocks_imaging",
                    reason="requires scieasy-blocks-imaging plugin")

pytestmark = pytest.mark.requires_imaging
```

The marker registration in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "requires_imaging: marks tests that need scieasy-blocks-imaging installed",
]
```

**h. Acceptance criteria**:
- [ ] No file under `tests/` contains `from scieasy.core.types.array
      import Image` (or any other domain subclass from core).
- [ ] No file under `tests/` instantiates `Image(...)` from a core
      module.
- [ ] `tests/integration/test_multimodal_workflow.py` is marked with
      `@pytest.mark.requires_imaging` and skipped when the plugin is
      absent (per Question 2 above).
- [ ] `pyproject.toml` registers the `requires_imaging` marker.
- [ ] `pytest -x --no-cov` passes locally.
- [ ] No production source under `src/scieasy/` is modified by this
      PR (test-only migration).

**i. Out of scope**:
- Touching any `src/scieasy/blocks/` built-ins that hard-code
  `accepted_types=[Image]`. Those are also tracked by ADR-027's
  Modified Files table; if the audit reveals any built-ins still
  referencing core `Image`, **open a separate issue** rather than
  inline-fixing per Universal Rule §4.8.

**j. Dependencies on other tickets**:
- T-006 (Array 6D axes) — required so `Array(axes=[...])` works.
- T-007 (other base classes audit) — required so the `Image` import
  no longer succeeds, providing a fail-fast guard for missed sites.

**k. Estimated diff size**: ~80 sites updated across ~17 test files.
~250 net lines changed. Plus ~5 lines in `pyproject.toml`. Total ~255
lines.

**l. Suggested workflow gate ticket title**:
`Test migration: Image() to Array(axes=...) per ADR-027 D2 (T-008)`

---

### T-009 — ProcessBlock setup / teardown hooks

**a. Ticket ID and name**: T-009 — `ProcessBlock.setup()` and
`teardown()` hooks.

**b. Source ADR sections**:
- ADR-027 D7 (whole).
- ADR-027 discussion rows 10–11.
- ARCHITECTURE.md §5.1 (already updated in PR #257).

**c. Files to be created**: none.

**d. Files to be modified**:
- `src/scieasy/blocks/process/process_block.py`
- `src/scieasy/blocks/process/contrib/baseline_correction.py`
- `src/scieasy/blocks/process/contrib/cellpose_segment.py`
- `src/scieasy/blocks/process/contrib/spectral_pca.py`

  (each `process_item` override gets `state=None` added explicitly per
  Question 5 above)

**e. New tests**:
- `tests/blocks/test_process_block_lifecycle.py` (new file) containing:
  - `test_setup_called_once_before_iteration`
  - `test_teardown_called_once_after_iteration`
  - `test_state_passed_to_process_item`
  - `test_teardown_called_even_on_process_item_error`
  - `test_default_setup_returns_none`
  - `test_default_teardown_is_noop`
  - `test_existing_two_arg_process_item_still_works` (regression guard
    for backward compat)

**f. Existing tests to update**:
- `tests/blocks/test_process_block.py` — add coverage for the new
  3-arg signature; existing 2-arg tests stay green.

**g. Implementation details**: per ADR-027 D7 pseudocode (quoted in §7
of ADR-027):

```python
class ProcessBlock(Block):
    def setup(self, config: BlockConfig) -> Any:
        return None

    def teardown(self, state: Any) -> None:
        pass

    def process_item(
        self,
        item: DataObject,
        config: BlockConfig,
        state: Any = None,
    ) -> DataObject:
        raise NotImplementedError

    def run(self, inputs, config):
        from scieasy.core.types.collection import Collection
        primary = next(iter(inputs.values()))
        state = self.setup(config)
        try:
            if isinstance(primary, Collection):
                results = []
                for item in primary:
                    result = self.process_item(item, config, state)
                    result = self._auto_flush(result)
                    results.append(result)
                output_name = self.output_ports[0].name if self.output_ports else "output"
                return {output_name: Collection(results, item_type=primary.item_type)}
            else:
                result = self.process_item(primary, config, state)
                output_name = self.output_ports[0].name if self.output_ports else "output"
                return {output_name: result}
        finally:
            self.teardown(state)
```

**h. Acceptance criteria**:
- [ ] `ProcessBlock.setup(config)` exists with default returning
      `None` (ADR-027 D7).
- [ ] `ProcessBlock.teardown(state)` exists with default no-op
      (ADR-027 D7).
- [ ] `ProcessBlock.process_item` signature is
      `(self, item, config, state=None)` (ADR-027 D7).
- [ ] `ProcessBlock.run` calls `setup` once, iterates,
      calls `teardown` in `finally` (ADR-027 D7 pseudocode).
- [ ] `setup` is called BEFORE iteration starts and only ONCE per
      `run()` (`test_setup_called_once_before_iteration`).
- [ ] `teardown` is called AFTER iteration completes or fails, in a
      `finally` block (`test_teardown_called_even_on_process_item_error`).
- [ ] Pre-existing `process_item` overrides with the 2-arg signature
      continue to work (`test_existing_two_arg_process_item_still_works`).
- [ ] Each existing override under
      `src/scieasy/blocks/process/contrib/*.py` is updated to accept
      `state=None` even when ignored (per Question 5).

**i. Out of scope**:
- Cellpose-specific logic. The Cellpose block is a plugin
  responsibility (per ADR-027 D14); the contrib placeholder under
  `src/scieasy/blocks/process/contrib/cellpose_segment.py` only needs
  the signature update, not the full Tier-2 batched implementation.
- The `setup`-receives-inputs alternative (rejected in ADR-027
  discussion #11).
- A `StatefulBlock` base class (rejected in ADR-027 discussion #10).

**j. Dependencies on other tickets**:
- T-005 (DataObject three-slot metadata) is recommended but not
  strictly required (the lifecycle hooks do not touch metadata).
  Listing T-005 as a dependency keeps the merge order clean.

**k. Estimated diff size**: ~40 source lines in `process_block.py`.
~10 lines across the contrib overrides. ~200 lines of tests. Total
~250 lines.

**l. Suggested workflow gate ticket title**:
`ProcessBlock setup/teardown hooks per ADR-027 D7 (T-009)`

---

### T-010 — scieasy.utils.constraints

**a. Ticket ID and name**: T-010 — port constraint helper module.

**b. Source ADR sections**:
- ADR-027 "Detailed impact scope → New files" row for
  `src/scieasy/utils/constraints.py`.
- ADR-027 D4 (companion).
- ARCHITECTURE.md §4.1 + §4.5.1 (already in PR #257) — describe the
  `has_axes(...)` usage pattern.

**c. Files to be created**: none. (`src/scieasy/utils/constraints.py`
was created as a skeleton in PR #261.)

**d. Files to be modified**:
- `src/scieasy/utils/constraints.py` — fill in the skeleton.

**e. New tests**:
- `tests/utils/test_constraints.py` (new file; if `tests/utils/`
  doesn't exist, create it with an empty `__init__.py`) containing:
  - `test_has_axes_passes_when_required_present`
  - `test_has_axes_fails_when_required_missing`
  - `test_has_axes_allows_extra_axes`
  - `test_has_axes_iterates_collection_per_adr020`
  - `test_has_exact_axes_passes_on_set_equality`
  - `test_has_exact_axes_fails_on_extra_axis`
  - `test_has_exact_axes_fails_on_missing_axis`
  - `test_has_shape_passes_on_correct_ndim`
  - `test_has_shape_fails_on_wrong_ndim`
  - `test_has_axes_handles_items_without_axes_attribute`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
# scieasy/utils/constraints.py — implementations to fill in

def has_axes(*required: str) -> ConstraintFn:
    required_set = frozenset(required)
    def _check(collection: Any) -> bool:
        for item in collection:
            item_axes = getattr(item, "axes", None)
            if item_axes is None:
                return False
            if not required_set.issubset(set(item_axes)):
                return False
        return True
    _check.__doc__ = f"has_axes({', '.join(repr(a) for a in required)})"
    return _check

def has_exact_axes(*axes: str) -> ConstraintFn:
    expected_set = frozenset(axes)
    def _check(collection: Any) -> bool:
        for item in collection:
            item_axes = getattr(item, "axes", None)
            if item_axes is None or set(item_axes) != expected_set:
                return False
        return True
    _check.__doc__ = f"has_exact_axes({', '.join(repr(a) for a in axes)})"
    return _check

def has_shape(ndim: int) -> ConstraintFn:
    def _check(collection: Any) -> bool:
        for item in collection:
            item_axes = getattr(item, "axes", None)
            if item_axes is None or len(item_axes) != ndim:
                return False
        return True
    _check.__doc__ = f"has_shape({ndim!r})"
    return _check
```

The `collection` parameter is duck-typed because per ADR-020 the actual
type is `Collection`, but the constraint function is called from
`Block.validate(...)` which the test suite may invoke with plain lists
during unit tests. The implementation should accept any iterable.

**h. Acceptance criteria**:
- [ ] `has_axes(*required)` returns a callable that returns True iff
      every item's axes contain every name in `required`.
- [ ] `has_exact_axes(*axes)` returns a callable enforcing set
      equality.
- [ ] `has_shape(ndim)` returns a callable enforcing
      `len(item.axes) == ndim`.
- [ ] All three handle items missing the `axes` attribute gracefully
      (return False rather than raising AttributeError).
- [ ] Each returned callable's `__doc__` is set to a useful repr like
      `"has_axes('y', 'x')"`.
- [ ] All three iterate the `collection` argument once (no double
      iteration), short-circuit on first failure.

**i. Out of scope**:
- Adding constraint helpers for non-axis concerns (dtype, shape values,
  metadata predicates). Future tickets, not Phase 10.
- Integrating these into the port system internals — that is the
  block author's responsibility via the `constraint=` kwarg per ADR-020.

**j. Dependencies on other tickets**:
- T-006 (Array instance-level axes) — required so `item.axes` is an
  instance attribute, not a ClassVar.

**k. Estimated diff size**: ~80 source lines in `constraints.py`. ~150
lines of tests. Total ~230 lines.

**l. Suggested workflow gate ticket title**:
`scieasy.utils.constraints per ADR-027 D4 companion (T-010)`

---

### T-011 — scieasy.utils.axis\_iter.iterate\_over\_axes

**a. Ticket ID and name**: T-011 — `iterate_over_axes` utility.

**b. Source ADR sections**:
- ADR-027 D3 (whole).
- ADR-027 "Detailed impact scope → New files" row for
  `src/scieasy/utils/axis_iter.py`.
- ARCHITECTURE.md §4.5.1 (already in PR #257).

**c. Files to be created**: none. (`src/scieasy/utils/axis_iter.py` was
created as a skeleton in PR #261.)

**d. Files to be modified**:
- `src/scieasy/utils/axis_iter.py` — fill in the skeleton.

**e. New tests**:
- `tests/utils/test_axis_iter.py` (new file) containing:
  - `test_iterate_over_axes_3d_iterate_z`
  - `test_iterate_over_axes_5d_iterate_t_z_c`
  - `test_iterate_over_axes_operates_on_must_be_subset`
  - `test_iterate_over_axes_inconsistent_shapes_raises_broadcast_error`
  - `test_iterate_over_axes_metadata_propagation_per_d5`
  - `test_iterate_over_axes_returns_same_class_as_source`
  - `test_iterate_over_axes_axes_preserved`

**f. Existing tests to update**: none.

**g. Implementation details**:

```python
# scieasy/utils/axis_iter.py

import numpy as np
from itertools import product
from scieasy.core.exceptions import BroadcastError

def iterate_over_axes(source, operates_on, func):
    if not operates_on.issubset(set(source.axes)):
        missing = operates_on - set(source.axes)
        raise BroadcastError(
            f"operates_on {sorted(operates_on)} is not a subset of "
            f"source axes {source.axes} (missing: {sorted(missing)})"
        )

    extra_axes  = [a for a in source.axes if a not in operates_on]
    extra_shape = [source.shape[source.axes.index(a)] for a in extra_axes]

    raw = source.to_memory()  # Phase 10 Level 1: full materialise
    out_chunks = {}
    out_shape_op_dims = None

    for combo in product(*(range(s) for s in extra_shape)):
        coord = dict(zip(extra_axes, combo))
        index = tuple(
            coord[a] if a in coord else slice(None) for a in source.axes
        )
        slice_data = raw[index]
        result = func(slice_data, coord)

        if out_shape_op_dims is None:
            out_shape_op_dims = result.shape
        elif result.shape != out_shape_op_dims:
            raise BroadcastError(
                f"Inconsistent slice output shape {result.shape}, "
                f"expected {out_shape_op_dims}"
            )
        out_chunks[combo] = result

    # Stack back
    out_array = np.empty(extra_shape + list(out_shape_op_dims), dtype=raw.dtype)
    for combo, result in out_chunks.items():
        out_array[combo] = result

    return type(source)(
        axes=list(source.axes),
        shape=out_array.shape,
        dtype=out_array.dtype,
        framework=source.framework.derive(),
        meta=source.meta,
        user=dict(source.user),
    )
```

The exact construction call may vary depending on whether the source's
type registers extra-kwargs that are not present on a freshly-materialised
result; defer that detail to the implementer.

**h. Acceptance criteria**:
- [ ] `iterate_over_axes(source, operates_on, func)` calls `func` once
      per combination of non-`operates_on` axis indices.
- [ ] The output is a new instance of `type(source)` with `axes`,
      `shape`, `dtype` consistent with the iteration result (ADR-027
      D3).
- [ ] Metadata propagation follows ADR-027 D5: framework derived
      (with `derived_from=source.framework.object_id`), meta shared by
      reference, user shallow-copied.
- [ ] Raises `BroadcastError` if `operates_on` is not a subset of
      `source.axes`.
- [ ] Raises `BroadcastError` if slice outputs have inconsistent
      shapes.
- [ ] Errors raised inside the user-provided `func` propagate
      unchanged (NOT wrapped).
- [ ] Function is serial — no threads, asyncio, or multiprocessing
      (ADR-027 D3 §"Memory" paragraph).

**i. Out of scope**:
- Block-internal parallelism (forbidden inside the utility per
  ADR-027 D3).
- Level 2 laziness via `SlicedStorageReference` (deferred per ADR-027
  D4 discussion #6).
- Integration with `Array.iter_over` chains for memory-bounded streaming
  — Phase 11 if profiling justifies.

**j. Dependencies on other tickets**:
- T-006 (Array `sel` / `iter_over` and instance-level axes).
- T-005 (FrameworkMeta `derive()` and DataObject `with_meta`).

**k. Estimated diff size**: ~120 source lines in `axis_iter.py`. ~200
lines of tests. Total ~320 lines.

**l. Suggested workflow gate ticket title**:
`scieasy.utils.axis_iter.iterate_over_axes per ADR-027 D3 (T-011)`

---

### T-012 — TypeRegistry.resolve + Meta validation

**a. Ticket ID and name**: T-012 — `TypeRegistry.resolve` helper +
`Meta` Pydantic constraint validation.

**b. Source ADR sections**:
- ADR-027 D11 (TypeRegistry.scan + .resolve helper).
- ADR-027 Addendum 1 §3 ("Meta Pydantic constraints").
- ADR-027 Addendum 1 "Detailed impact scope → Rewritten files" row
  for `src/scieasy/core/types/registry.py`.

**c. Files to be created**: none.

**d. Files to be modified**:
- `src/scieasy/core/types/registry.py`

**e. New tests**:
- `tests/core/test_type_registry_resolve.py` (new file) containing:
  - `test_resolve_returns_most_specific_class`
  - `test_resolve_returns_none_for_unknown_chain`
  - `test_resolve_walks_chain_in_order`
  - `test_register_validates_meta_is_basemodel`
  - `test_register_rejects_meta_with_private_attr`
  - `test_register_rejects_meta_with_non_serialisable_field`
  - `test_register_accepts_well_formed_meta`
  - `test_scan_is_idempotent`

**f. Existing tests to update**:
- `tests/architecture/test_registries.py` — audit; should be unaffected
  by additive changes.

**g. Implementation details**:

```python
# scieasy/core/types/registry.py

from pydantic import BaseModel
from pydantic.fields import PrivateAttr

class TypeRegistry:
    @classmethod
    def resolve(cls, type_chain: list[str]) -> type | None:
        """Walk the chain from most-specific to least-specific and
        return the first matching registered class. Returns None if no
        entry matches."""
        for name in type_chain:
            if name in cls._registered_by_name:
                return cls._registered_by_name[name]
        return None

    @classmethod
    def register(cls, klass: type) -> None:
        cls._validate_meta_class(klass)
        cls._registered_by_name[klass.__name__] = klass

    @classmethod
    def _validate_meta_class(cls, klass: type) -> None:
        meta_cls = getattr(klass, "Meta", None)
        if meta_cls is None:
            return  # no Meta declared — OK
        if not (isinstance(meta_cls, type) and issubclass(meta_cls, BaseModel)):
            raise TypeError(
                f"{klass.__name__}.Meta must be a pydantic.BaseModel subclass; "
                f"got {meta_cls!r}"
            )
        # Reject PrivateAttr fields
        for field_name, field in meta_cls.model_fields.items():
            # PrivateAttr fields appear in __private_attributes__, not model_fields,
            # but check explicitly anyway
            pass
        for attr_name in getattr(meta_cls, "__private_attributes__", {}):
            raise TypeError(
                f"{klass.__name__}.Meta.{attr_name}: PrivateAttr is not "
                f"allowed (per ADR-027 Addendum 1 §3 — Meta must round-trip "
                f"through JSON)"
            )
        # Smoke test JSON round-trip with default values
        try:
            instance = meta_cls()
            json_str = instance.model_dump_json()
            meta_cls.model_validate_json(json_str)
        except Exception as exc:
            raise TypeError(
                f"{klass.__name__}.Meta does not round-trip through JSON: {exc}"
            ) from exc
```

The "smoke test with default values" only catches Meta classes whose
default-constructible form fails. Plugin authors with required fields
should write their own round-trip test in their plugin's test suite.

**h. Acceptance criteria**:
- [ ] `TypeRegistry.resolve(type_chain)` returns the most-specific
      registered class or `None` (ADR-027 D11).
- [ ] `TypeRegistry.register` runs `_validate_meta_class` and rejects
      with a clear error message (ADR-027 Addendum 1 §3).
- [ ] `_validate_meta_class` requires `Meta` (if present) to be a
      `pydantic.BaseModel` subclass.
- [ ] `_validate_meta_class` rejects `Meta` classes that declare
      `PrivateAttr` fields.
- [ ] `_validate_meta_class` rejects `Meta` classes whose default
      instance does not round-trip through `model_dump_json` /
      `model_validate_json`.
- [ ] `TypeRegistry.scan()` is idempotent — calling it twice does not
      raise or duplicate-register (ADR-027 D11 §"Ensure scan is
      idempotent").

**i. Out of scope**:
- Adding the worker subprocess `TypeRegistry.scan()` call. That is in
  T-014.
- Plugin packaging concerns (entry-point parsing, etc.) — ADR-025 is
  authoritative.
- Validating non-`Meta` plugin attributes.

**j. Dependencies on other tickets**:
- T-005 (DataObject three-slot metadata) — needed so the Meta class
  registration story makes sense.

**k. Estimated diff size**: ~80 source lines in `registry.py`. ~200
lines of tests. Total ~280 lines.

**l. Suggested workflow gate ticket title**:
`TypeRegistry.resolve and Meta validation per ADR-027 D11 + Addendum 1 §3 (T-012)`

---

### T-013 — Six base-class `_reconstruct_extra_kwargs` / `_serialise_extra_metadata` hook pairs

**a. Ticket ID and name**: T-013 — six pairs of round-trip hooks on the
core base classes.

**b. Source ADR sections**:
- ADR-027 Addendum 1 §2 ("Where lives the per-base-class knowledge of
  how to reconstruct from a metadata sidecar").
- ADR-027 Addendum 1 §"D11′ companion. `_reconstruct_extra_kwargs`
  classmethod hook" — full pseudocode for all six base classes.
- ADR-027 Addendum 1 §"Rewritten files" sub-table.

**c. Files to be created**: none.

**d. Files to be modified**:
- `src/scieasy/core/types/base.py` — add default no-op hook pair on
  `DataObject`.
- `src/scieasy/core/types/array.py` — add `axes` / `shape` / `dtype`
  / `chunk_shape` hook pair on `Array`.
- `src/scieasy/core/types/series.py` — add `index_name` / `value_name`
  / `length` hook pair on `Series`.
- `src/scieasy/core/types/dataframe.py` — add `columns` / `row_count`
  / `schema` hook pair on `DataFrame`.
- `src/scieasy/core/types/text.py` — add `format` / `encoding` hook
  pair on `Text`.
- `src/scieasy/core/types/artifact.py` — add `mime_type` / `description`
  hook pair on `Artifact`.
- `src/scieasy/core/types/composite.py` — add slot-recursive hook pair
  on `CompositeData` (delegates to `_reconstruct_one` / `_serialise_one`
  via inside-the-method import per Question 1 above).

**e. New tests**:
- `tests/core/test_base_class_round_trip.py` (new file) containing:
  - `test_dataobject_default_hooks_return_empty_dict`
  - `test_array_reconstruct_extra_kwargs`
  - `test_array_serialise_extra_metadata`
  - `test_series_reconstruct_round_trip`
  - `test_dataframe_reconstruct_round_trip`
  - `test_text_reconstruct_round_trip`
  - `test_artifact_reconstruct_round_trip`
  - `test_composite_reconstruct_recursive_slots`
  - `test_plugin_subclass_can_override_and_super`

**f. Existing tests to update**:
- `tests/core/test_types.py` — add coverage for the new classmethods
  on each base class.

**g. Implementation details**: full pseudocode quoted from ADR-027
Addendum 1 §"D11′ companion. `_reconstruct_extra_kwargs` classmethod
hook":

```python
# scieasy/core/types/base.py
class DataObject:
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {}

    @classmethod
    def _serialise_extra_metadata(cls, obj: "DataObject") -> dict:
        return {}


# scieasy/core/types/array.py
class Array(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "axes":        list(metadata.get("axes", [])),
            "shape":       tuple(metadata["shape"]) if metadata.get("shape") else None,
            "dtype":       metadata.get("dtype"),
            "chunk_shape": tuple(metadata["chunk_shape"]) if metadata.get("chunk_shape") else None,
        }

    @classmethod
    def _serialise_extra_metadata(cls, obj: "Array") -> dict:
        return {
            "axes":        list(obj.axes),
            "shape":       list(obj.shape) if obj.shape is not None else None,
            "dtype":       str(obj.dtype) if obj.dtype is not None else None,
            "chunk_shape": list(obj.chunk_shape) if obj.chunk_shape is not None else None,
        }


# scieasy/core/types/series.py
class Series(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "index_name": metadata.get("index_name"),
            "value_name": metadata.get("value_name"),
            "length":     metadata.get("length"),
        }

    @classmethod
    def _serialise_extra_metadata(cls, obj: "Series") -> dict:
        return {
            "index_name": obj.index_name,
            "value_name": obj.value_name,
            "length":     obj.length,
        }


# scieasy/core/types/dataframe.py
class DataFrame(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "columns":   list(metadata.get("columns", [])),
            "row_count": metadata.get("row_count"),
            "schema":    dict(metadata.get("schema", {})),
        }

    @classmethod
    def _serialise_extra_metadata(cls, obj: "DataFrame") -> dict:
        return {
            "columns":   list(obj.columns),
            "row_count": obj.row_count,
            "schema":    dict(obj.schema or {}),
        }


# scieasy/core/types/text.py
class Text(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "format":   metadata.get("format", "plain"),
            "encoding": metadata.get("encoding", "utf-8"),
        }

    @classmethod
    def _serialise_extra_metadata(cls, obj: "Text") -> dict:
        return {
            "format":   obj.format,
            "encoding": obj.encoding,
        }


# scieasy/core/types/artifact.py
class Artifact(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        return {
            "mime_type":   metadata.get("mime_type"),
            "description": metadata.get("description", ""),
        }

    @classmethod
    def _serialise_extra_metadata(cls, obj: "Artifact") -> dict:
        return {
            "mime_type":   obj.mime_type,
            "description": obj.description,
        }


# scieasy/core/types/composite.py
class CompositeData(DataObject):
    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict) -> dict:
        # Inside-the-method import to avoid load-time cycle (Question 1).
        from scieasy.core.types.serialization import _reconstruct_one
        slot_payloads = metadata.get("slots", {}) or {}
        slots = {
            slot_name: _reconstruct_one(slot_payload)
            for slot_name, slot_payload in slot_payloads.items()
        }
        return {"slots": slots}

    @classmethod
    def _serialise_extra_metadata(cls, obj: "CompositeData") -> dict:
        from scieasy.core.types.serialization import _serialise_one
        return {
            "slots": {
                slot_name: _serialise_one(slot_obj)
                for slot_name, slot_obj in obj._slots.items()
            }
        }
```

**h. Acceptance criteria**:
- [ ] `DataObject._reconstruct_extra_kwargs` and
      `_serialise_extra_metadata` exist with empty-dict defaults
      (ADR-027 Addendum 1 §"D11′ companion").
- [ ] `Array` overrides both, covering `axes`, `shape`, `dtype`,
      `chunk_shape`.
- [ ] `Series` overrides both, covering `index_name`, `value_name`,
      `length`.
- [ ] `DataFrame` overrides both, covering `columns`, `row_count`,
      `schema`.
- [ ] `Text` overrides both, covering `format`, `encoding`.
- [ ] `Artifact` overrides both, covering `mime_type`, `description`.
- [ ] `CompositeData` overrides both with slot-recursive delegation
      via `from scieasy.core.types.serialization import ...` *inside*
      the classmethod body (per Question 1 above).
- [ ] `test_plugin_subclass_can_override_and_super` exercises the
      `super()._reconstruct_extra_kwargs(metadata)` chain that plugin
      subclasses use (per ADR-027 Addendum 1 §"D11′ companion" final
      paragraph).
- [ ] No `import scieasy.core.types.serialization` at module load time
      in `composite.py` (verified by importlinter contract — composite
      currently has no such import; the inside-the-method import keeps
      the load-time graph clean).

**i. Out of scope**:
- The `_reconstruct_one` / `_serialise_one` helpers themselves —
  those live in T-014's new `serialization.py` module.
- The worker `reconstruct_inputs` / `serialise_outputs` rewrite — also
  T-014.
- Plugin subclass overrides (out of scope; example only).

**j. Dependencies on other tickets**:
- T-005 (DataObject three-slot metadata) — needed so the hook context
  makes sense.
- T-006 (Array axes / shape / dtype / chunk_shape instance fields) —
  needed for the Array hook implementation.
- T-007 (other base classes audit) — needed so the modules contain
  exactly one base class each.
- T-014 will land *after* T-013 because T-014 provides the
  `serialization.py` module that `composite.py` imports inside its
  classmethod. **Important**: the import is inside the method body, so
  T-013 can be merged before T-014 is opened — the import error only
  fires when the classmethod is called, which the T-013 tests for
  composite skip (or use a stub `serialization` module fixture that
  injects no-op `_reconstruct_one` / `_serialise_one`).
  Alternatively, T-013 ships alongside a stub
  `src/scieasy/core/types/serialization.py` that exposes no-op
  versions of the two helpers, which T-014 then replaces with the
  full implementation. **Decision**: ship the stub in T-013 to remove
  the conditional. Add it to T-013's "Files to be created" list:
  `src/scieasy/core/types/serialization.py` (stub).

**k. Estimated diff size**: ~150 source lines across the seven
modules. ~250 lines of tests. ~30 lines of stub. Total ~430 lines.

**l. Suggested workflow gate ticket title**:
`Six base-class _reconstruct_extra_kwargs / _serialise_extra_metadata per ADR-027 Addendum 1 §2 (T-013)`

---

### T-014 — Worker subprocess typed reconstruction

**a. Ticket ID and name**: T-014 — `worker.reconstruct_inputs` /
`worker.serialise_outputs` rewrite via `_reconstruct_one` /
`_serialise_one`, plus the `TypeRegistry.scan()` call at worker
startup.

**b. Source ADR sections**:
- ADR-027 D11 (TypeRegistry.scan in worker.main).
- ADR-027 Addendum 1 §1 (whole — `_reconstruct_one`, `_serialise_one`).
- ADR-027 Addendum 1 "Detailed impact scope → Rewritten files" row
  for `src/scieasy/engine/runners/worker.py`.

**c. Files to be created**:
- (None new — `src/scieasy/core/types/serialization.py` was already
  created in T-013 as a stub. T-014 replaces the stub body with the
  full `_reconstruct_one` / `_serialise_one` implementations.)

**d. Files to be modified**:
- `src/scieasy/engine/runners/worker.py`
- `src/scieasy/core/types/serialization.py` (T-013 stub → full impl)

**e. New tests**:
- `tests/engine/test_worker_type_reconstruction.py` (new file)
  containing:
  - `test_reconstruct_one_array_round_trip`
  - `test_reconstruct_one_series_round_trip`
  - `test_reconstruct_one_dataframe_round_trip`
  - `test_reconstruct_one_text_round_trip`
  - `test_reconstruct_one_artifact_round_trip`
  - `test_reconstruct_one_composite_round_trip`
  - `test_reconstruct_inputs_collection_dispatch`
  - `test_reconstruct_inputs_scalar_pass_through`
  - `test_reconstruct_inputs_returns_typed_not_viewproxy`
- `tests/engine/test_worker_serialise_outputs.py` (new file or extend
  existing) containing:
  - `test_serialise_one_writes_full_metadata_sidecar`
  - `test_serialise_outputs_collection_format`
  - `test_round_trip_serialise_then_reconstruct`
- `tests/engine/test_worker_typeregistry_scan.py` (new file) containing:
  - `test_worker_main_calls_typeregistry_scan_before_reconstruct`
  - `test_worker_resolves_plugin_type_when_registered`

**f. Existing tests to update**:
- `tests/engine/test_worker.py` — audit; the existing tests assert
  `ViewProxy` return types. Update to assert typed `DataObject`
  instances per ADR-027 Addendum 1 §"Consequences": "Tests that
  asserted `inputs['x']` is a `ViewProxy` will fail. ... The
  implementation ticket for D11 must update these to assert
  `isinstance(inputs['x'], FluorImage)` (or `Array`, depending on the
  test's domain) instead."
- `tests/blocks/test_block_base.py` — same audit per the Addendum.
- `tests/core/test_proxy.py` — same audit. ViewProxy itself is
  unchanged, so tests that exercise `ViewProxy.slice` /
  `ViewProxy.to_memory` directly still pass; only tests that asserted
  "the input the worker delivers is a ViewProxy" need to change.

**g. Implementation details**:

```python
# scieasy/core/types/serialization.py — full implementation

from typing import Any
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.core.types.registry import TypeRegistry
from scieasy.core.storage.ref import StorageReference
from scieasy.core.meta import FrameworkMeta


def _reconstruct_one(payload_item: dict) -> "DataObject":
    """ADR-027 Addendum 1 §1 — see standards doc T-014."""
    ref = StorageReference(
        backend=payload_item["backend"],
        path=payload_item["path"],
        format=payload_item.get("format"),
        metadata=payload_item.get("metadata", {}),
    )
    md = payload_item.get("metadata", {})

    type_chain = md.get("type_chain", ["DataObject"])
    cls = TypeRegistry.resolve(type_chain) or DataObject

    framework = FrameworkMeta.model_validate(md.get("framework", {}))

    meta_cls = getattr(cls, "Meta", None)
    if meta_cls is not None:
        meta = meta_cls.model_validate(md.get("meta", {}))
    else:
        meta = None

    user = dict(md.get("user", {}) or {})

    if hasattr(cls, "_reconstruct_extra_kwargs"):
        extra_kwargs = cls._reconstruct_extra_kwargs(md)
    else:
        extra_kwargs = {}

    return cls(
        storage_ref=ref,
        framework=framework,
        meta=meta,
        user=user,
        **extra_kwargs,
    )


def _serialise_one(obj: "DataObject") -> dict:
    """ADR-027 Addendum 1 §1 — see standards doc T-014."""
    if obj.storage_ref is None:
        raise RuntimeError(
            f"Cannot serialise {type(obj).__name__} without storage_ref"
        )

    md: dict[str, Any] = {}
    md["type_chain"] = obj.dtype_info.type_chain
    md["framework"]  = obj.framework.model_dump(mode="json")
    if obj.meta is not None:
        md["meta"] = obj.meta.model_dump(mode="json")
    md["user"] = dict(obj.user or {})
    if hasattr(type(obj), "_serialise_extra_metadata"):
        md.update(type(obj)._serialise_extra_metadata(obj))

    ref = obj.storage_ref
    return {
        "backend":  ref.backend,
        "path":     ref.path,
        "format":   ref.format,
        "metadata": md,
    }
```

```python
# scieasy/engine/runners/worker.py

def main() -> None:
    try:
        from scieasy.core.types.registry import TypeRegistry
        TypeRegistry.scan()  # ADR-027 D11

        raw = sys.stdin.read()
        payload = json.loads(raw)
        # ... reconstruct_inputs(payload), call block, serialise_outputs ...


def reconstruct_inputs(payload: dict[str, Any]) -> dict[str, Any]:
    from scieasy.core.types.collection import Collection
    from scieasy.core.types.registry import TypeRegistry
    from scieasy.core.types.base import DataObject
    from scieasy.core.types.serialization import _reconstruct_one

    raw_inputs = payload.get("inputs", {})
    result: dict[str, Any] = {}

    for key, value in raw_inputs.items():
        if isinstance(value, dict) and value.get("_collection"):
            items = [_reconstruct_one(item) for item in value["items"]]
            item_type_name = value.get("item_type", "DataObject")
            item_type = TypeRegistry.resolve([item_type_name]) or DataObject
            result[key] = Collection(items, item_type=item_type)
        elif isinstance(value, dict) and "backend" in value and "path" in value:
            result[key] = _reconstruct_one(value)
        else:
            result[key] = value

    return result


def serialise_outputs(outputs: dict[str, Any], output_dir: str) -> dict[str, Any]:
    from scieasy.blocks.base.block import Block
    from scieasy.core.types.base import DataObject
    from scieasy.core.types.collection import Collection
    from scieasy.core.types.serialization import _serialise_one

    result: dict[str, Any] = {}
    for key, value in outputs.items():
        if isinstance(value, Collection):
            item_payloads = [_serialise_one(Block._auto_flush(item)) for item in value]
            result[key] = {
                "_collection": True,
                "item_type":   value.item_type.__name__ if value.item_type else "DataObject",
                "items":       item_payloads,
            }
        elif isinstance(value, DataObject):
            result[key] = _serialise_one(Block._auto_flush(value))
        elif isinstance(value, (str, int, float, bool, type(None), list, dict)):
            result[key] = value
        else:
            result[key] = str(value)
    return result
```

**Important**: the `from scieasy.core.types.serialization import ...`
lines stay outside the function body in `worker.py` because `worker.py`
lives in `scieasy.engine`, not `scieasy.core`, so the import is in the
"normal" direction (engine → core). The inside-the-method imports are
required only inside `composite.py` to avoid the load-time cycle when
core imports core (per Question 1).

The `ViewProxy` import in `worker.py` is removed (per ADR-027
Addendum 1 §"ViewProxy role after this Addendum" — `worker.py` no
longer constructs `ViewProxy` instances).

**h. Acceptance criteria**:
- [ ] `worker.main()` calls `TypeRegistry.scan()` before
      `reconstruct_inputs` (ADR-027 D11).
- [ ] `worker.reconstruct_inputs` returns typed `DataObject` instances,
      not `ViewProxy` (ADR-027 Addendum 1 §1 + Discussion #1).
- [ ] `worker.reconstruct_inputs` handles three cases: Collection,
      single DataObject, scalar pass-through (ADR-027 Addendum 1 §1
      pseudocode).
- [ ] `worker.serialise_outputs` writes the full metadata sidecar
      (`type_chain` + `framework` + `meta` + `user` + base-class extras)
      via `_serialise_one` (ADR-027 Addendum 1 §1).
- [ ] `_reconstruct_one` and `_serialise_one` live in
      `src/scieasy/core/types/serialization.py` (Question 1).
- [ ] Round-trip test: serialise an instance via `_serialise_one`,
      reconstruct via `_reconstruct_one`, assert deep equality of
      `framework`, `meta`, `user`, `axes`, `shape`, `dtype`,
      `chunk_shape` (Array case) and analogous fields for the other
      base classes.
- [ ] `worker.py` no longer imports `ViewProxy` (ADR-027 Addendum 1
      §"ViewProxy role after this Addendum").
- [ ] Existing tests in `tests/engine/test_worker.py` and
      `tests/blocks/test_block_base.py` are updated where they
      asserted `ViewProxy` return types.

**i. Out of scope**:
- Removing `ViewProxy` itself (deferred — `Array.view()` continues to
  return `ViewProxy` per ADR-027 Addendum 1 §"ViewProxy role after this
  Addendum").
- Wire-format renames (no top-level key changes per ADR-027 Addendum 1
  §"Out of scope" → "Changing the wire format JSON keys").
- Migrating any plugin packages (Phase 11 / plugin repos own that).

**j. Dependencies on other tickets**:
- T-005 (DataObject three slots).
- T-006 (Array axes/shape/dtype/chunk_shape).
- T-007 (only base classes in core).
- T-009 (ProcessBlock signature change is needed for end-to-end
  worker tests but not for the reconstruction layer itself; loosely
  ordered).
- T-012 (`TypeRegistry.resolve` and Meta validation).
- T-013 (six base-class hook pairs).

T-014 is the *capstone* — every previous ticket must be merged for it
to pass its acceptance criteria.

**k. Estimated diff size**: ~120 source lines in
`serialization.py` (replacing the T-013 stub). ~80 source lines
modified in `worker.py`. ~400 lines of tests. Total ~600 lines.

**l. Suggested workflow gate ticket title**:
`Worker subprocess typed reconstruction per ADR-027 D11 + Addendum 1 §1 (T-014)`

---

## 8. Summary table

| Ticket | Title (short)                           | Depends on             | Est. lines |
|--------|-----------------------------------------|------------------------|------------|
| T-001  | Scheduler concurrency fix               | —                      | ~430       |
| T-002  | ResourceManager GPU auto-detect         | —                      | ~150       |
| T-003  | PhysicalQuantity                        | —                      | ~320       |
| T-004  | FrameworkMeta + scieasy.core.meta       | T-003 (soft)           | ~230       |
| T-005  | DataObject three slots                  | T-004                  | ~280       |
| T-006  | Array 6D axes + sel/iter\_over          | T-005                  | ~450       |
| T-007  | Other base classes audit                | T-006                  | ~200       |
| T-009  | ProcessBlock setup/teardown             | T-005                  | ~250       |
| T-010  | scieasy.utils.constraints               | T-006                  | ~230       |
| T-011  | iterate\_over\_axes                     | T-006, T-005           | ~320       |
| T-008  | Test migration Image → Array            | T-006, T-007           | ~255       |
| T-012  | TypeRegistry.resolve + Meta validation  | T-005                  | ~280       |
| T-013  | Six base-class hook pairs               | T-005, T-006, T-007    | ~430       |
| T-014  | Worker typed reconstruction (capstone)  | T-005..T-013           | ~600       |

Total estimated diff across all 14 tickets: ~4,425 lines.

---

## 9. References

- `docs/adr/ADR.md` — ADR-018 Addendum 1, ADR-027, ADR-027 Addendum 1.
- `docs/architecture/ARCHITECTURE.md` — §4.1, §4.5, §5.1, §5.4, §6.1, §6.4.
- `CLAUDE.md` Appendix A — Mandatory Workflow Gate Protocol.
- `CLAUDE.md` Appendix C — Bug Fix and Issue Resolution Workflow.
- PR #261 (this PR) — Phase 10 skeleton + standards.

---

**End of phase10-implementation-standards.md**