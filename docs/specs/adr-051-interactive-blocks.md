---
spec_id: adr-051-interactive-blocks
title: "ADR-051 Interactive Data-Processing Blocks Implementation Specification"
status: Planned
feature_branch: docs/adr-051-interactive-blocks
created: 2026-06-25
input: "Owner-approved ADR-051 direction: interactive data-processing blocks that pause mid-workflow, open a block-owned window onto real data, take a data-dependent decision, and compute from it — as a block capability, under ADR-017 subprocess isolation, with the decision recorded in lineage."
owners:
  - "@jiazhenz026"
related_adrs:
  - 51
related_specs: []
scope:
  in:
    - The interaction capability (`InteractiveMixin`), the `InteractivePrompt` contract, and the `SupportsInteraction` protocol used for validation.
    - Registry scan-time validation binding the capability to `execution_mode = INTERACTIVE`.
    - Two-phase subprocess orchestration replacing the in-process `_run_interactive` scheduler path, including the `PAUSED` pause, the engine-held intermediate-reference channel, and cancellation cleanup.
    - The block-owned panel window and manifest-based frontend component injection reusing the ADR-048 asset-serving mechanism.
    - Recording the user decision in lineage through the existing `block_config_resolved` field and excluding intermediate scratch from lineage.
    - Migration of `Data Router` and `Pair Editor` to the capability, including their panel components.
  out:
    - Any domain package interactive block, including an LCMS blank-subtraction block.
    - A live re-computation loop or backend reads while the window is open.
    - A generic runtime-rendered declarative widget schema in place of injected windows.
    - The subprocess-to-engine `RUNNING`/`PAUSED`/progress status channel (issue #56).
    - The re-run policy for a recorded decision (deterministic replay versus re-prompt).
    - Any change to the read-only previewer subsystem beyond reusing its injection mechanism.
governs:
  modules:
    - scistudio.engine.scheduler
    - scistudio.engine.runners
    - scistudio.blocks.base
    - scistudio.blocks.base.interactive
    - scistudio.blocks.process.builtins
  contracts:
    - scistudio.blocks.base.state.ExecutionMode
    - scistudio.blocks.base.interactive.InteractiveMixin
    - scistudio.blocks.base.interactive.InteractivePrompt
    - scistudio.blocks.base.interactive.PanelManifest
    - scistudio.engine.runners.local.LocalRunner
    - scistudio.engine.runners.worker.main
  entry_points: []
  files:
    - docs/specs/adr-051-interactive-blocks.md
    - src/scistudio/blocks/base/block.py
    - src/scistudio/blocks/base/interactive.py
    - src/scistudio/blocks/base/state.py
    - src/scistudio/blocks/process/builtins/data_router.py
    - src/scistudio/blocks/process/builtins/pair_editor.py
    - src/scistudio/engine/scheduler/_dispatch.py
    - src/scistudio/engine/scheduler/_events.py
    - src/scistudio/engine/runners/local.py
    - src/scistudio/engine/runners/worker.py
    - src/scistudio/engine/events.py
    - src/scistudio/api/ws.py
    - frontend/src/App.parts/InteractiveModals.tsx
    - frontend/src/components/DataRouterModal.tsx
    - frontend/src/components/PairEditorModal.tsx
    - docs/architecture/ARCHITECTURE.md
    - docs/block-development/block-contract.md
    - docs/block-development/architecture-for-block-devs.md
    - docs/block-development/quickstart.md
  excludes:
    - docs/user/reference/**
    - docs/user/llms.txt
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - tests/blocks/test_interactive_mixin.py
  - tests/blocks/test_interactive_registry_validation.py
  - tests/engine/test_interactive_two_phase.py
  - tests/engine/test_interactive_lineage.py
  - tests/engine/test_interactive_cancellation.py
  - tests/blocks/test_data_router.py
  - tests/blocks/test_pair_editor.py
acceptance_source: adr
language_source: en
---

# ADR-051 Interactive Data-Processing Blocks Implementation Specification

## 1. Change Summary

This spec implements ADR-051. It adds interactive data-processing blocks: blocks
that pause mid-workflow, open a block-owned window onto their real input data, take
a data-dependent decision from the user, and compute their outputs from it. The
decision is recorded in lineage, and execution stays under the ADR-017 subprocess
isolation contract throughout.

The change has three parts. First, interaction becomes a block capability —
`InteractiveMixin` plus `execution_mode = INTERACTIVE` — validated at registry
scan time. Second, the runtime executes an interactive block as two worker-
subprocess phases around an engine-managed pause, replacing the current in-process
`_run_interactive` path. Third, the panel window is owned by the block and injected
through the ADR-048 manifest/asset-serving mechanism instead of being hardcoded per
block type in the frontend. The existing `Data Router` and `Pair Editor` blocks are
migrated onto this model as the reference implementations.

This spec is derived from ADR-051 (owner-approved). It closes #1781.

## 2. User Scenarios & Testing

### User Story 1 - Decide on real data inside a running workflow (Priority: P1)

A scientist runs a workflow containing an interactive data-processing block. When
the block is reached, the workflow pauses and a window opens showing the block's
real input data. The scientist makes a data-dependent decision (for example
selecting which run is the blank and which region to subtract), confirms, and the
block computes its outputs from that decision. The decision is saved with the run.

**Why this priority**: This is the core capability ADR-051 exists to deliver. It is
the minimum that makes interactive data processing usable end-to-end.

**Independent Test**: Define a minimal test interactive block (a `ProcessBlock`
with `InteractiveMixin`) whose decision selects an item; run a workflow over a
multi-item collection; assert the block pauses, the prompt is built in a
subprocess, the panel payload is delivered, the injected response drives a fresh
subprocess that produces the expected outputs, and the decision appears in the
lineage record.

**Acceptance Scenarios**:

1. **Given** a workflow with an interactive block whose inputs are ready, **When**
   the scheduler reaches the block, **Then** the block transitions to `PAUSED`, its
   `prepare_prompt` runs in a worker subprocess, and the JSON-safe panel payload is
   emitted to the frontend.
2. **Given** a paused interactive block, **When** the scientist confirms a
   decision, **Then** the block transitions to `RUNNING`, `run` executes in a fresh
   worker subprocess with the decision injected, and the block transitions to
   `DONE` with outputs.
3. **Given** a completed interactive block, **When** the run's lineage is read,
   **Then** the decision is present in the block's `block_config_resolved` record
   and no intermediate scratch reference is present.
4. **Given** an input collection with many items, **When** the block is reached,
   **Then** the workflow pauses exactly once and the decision covers all items.

### User Story 2 - Existing interactive blocks keep working (Priority: P2)

A scientist already using `Data Router` or `Pair Editor` continues to use them with
unchanged behaviour after the runtime change. Their windows still open, their item
routing and pair reordering still work, and their results are identical, now under
subprocess isolation.

**Why this priority**: Removing the in-process path would break the only interactive
blocks in core if they are not migrated in the same change. Behaviour preservation
protects existing workflows.

**Independent Test**: Run representative workflows that use `Data Router` and
`Pair Editor`; assert the produced routing/reordering outputs match the pre-change
behaviour and that both blocks now execute through the two-phase subprocess path.

**Acceptance Scenarios**:

1. **Given** a workflow using `Data Router`, **When** it runs and the user assigns
   items to outputs, **Then** the output collections match the pre-migration
   behaviour.
2. **Given** a workflow using `Pair Editor`, **When** the user reorders items,
   **Then** the reordered collections match the pre-migration behaviour.
3. **Given** either migrated block, **When** it executes, **Then** neither
   `prepare_prompt` nor `run` runs in the scheduler process, and the panel is
   resolved from the block's manifest rather than a hardcoded branch.

### User Story 3 - Safe failure and clean cancellation (Priority: P3)

A block author who declares an interactive block incorrectly is told at load time,
not at runtime. A scientist who closes the window instead of deciding cancels the
step cleanly, with no leftover scratch and no computation performed.

**Why this priority**: These guardrails make the feature robust but are not required
for the primary happy path to deliver value.

**Independent Test**: Attempt to register malformed interactive blocks and assert
each is rejected at scan time; cancel a paused interaction and assert the block is
`CANCELLED`, no compute phase ran, and any intermediate scratch is removed.

**Acceptance Scenarios**:

1. **Given** a block with `execution_mode = INTERACTIVE` but no `InteractiveMixin`,
   missing `prepare_prompt`, or no valid panel manifest, **When** the registry
   scans it, **Then** registration fails with a clear error.
2. **Given** a block that mixes in `InteractiveMixin` but is not `INTERACTIVE`,
   **When** the registry scans it, **Then** registration fails with a clear error.
3. **Given** a paused interactive block whose `prepare_prompt` persisted
   intermediate scratch, **When** the scientist cancels, **Then** the block is
   `CANCELLED`, no compute-phase subprocess is spawned, and the scratch is removed.

### Edge Cases

- A non-JSON-safe `panel_payload` or `interactive_response` is rejected by the
  runtime rather than pickled or truncated.
- An interactive block produces no intermediate references; the compute phase
  rebuilds entirely from inputs, config, and the decision.
- `prepare_prompt` or `run` crashes in its subprocess; the failure is isolated as a
  block error and the engine is unaffected.
- The workflow run is cancelled at engine level while a block is paused; the paused
  interaction is torn down and its scratch removed.
- An interactive block sits paused indefinitely; because nothing is resident, the
  pause has no resource cost and there is no timeout.

## 3. Requirements

### Functional Requirements

- **FR-001**: A block is interactive if and only if its `execution_mode` is
  `ExecutionMode.INTERACTIVE` and it inherits `InteractiveMixin`.
- **FR-002**: The block registry MUST reject at scan time any block that sets
  `execution_mode = INTERACTIVE` without inheriting `InteractiveMixin`, without
  defining `prepare_prompt`, or without declaring a valid panel manifest, and MUST
  reject any block that inherits `InteractiveMixin` without `execution_mode = INTERACTIVE`.
- **FR-003**: `prepare_prompt` MUST run in an isolated worker subprocess, receive
  the block's full input collections and resolved config, and return an
  `InteractivePrompt` carrying a `panel_payload` and optional intermediate storage
  references.
- **FR-004**: `panel_payload` and `interactive_response` MUST be JSON-safe; the
  runtime MUST reject values that are not.
- **FR-005**: One interaction MUST cover the whole input. The runtime MUST NOT
  iterate the collection into per-item pauses.
- **FR-006**: On reaching an interactive block the engine MUST transition it to
  `PAUSED`, deliver the `panel_payload` to the frontend, and hold the pause with no
  block process resident.
- **FR-007**: The panel component MUST be resolved from the block's panel
  manifest, and the frontend MUST NOT select panels by hardcoded `blockType`
  branching. Core panels resolve from the manifest's `panel_id` against a
  built-in panel registry (they are bundled with the app, not wheel-served, so
  their `module_url` is empty); a package-provided panel loads its module from
  the manifest's `module_url` through the ADR-048 same-origin asset-serving
  mechanism. Both paths are manifest-driven; only the load mechanism differs.
- **FR-008**: The interaction MUST be a single round; the runtime MUST NOT
  re-invoke block computation to refresh the window while it is open.
- **FR-009**: On confirmation the engine MUST transition the block to `RUNNING` and
  execute `run` in a fresh worker subprocess with `interactive_response` (and any
  intermediate references) merged into the resolved config.
- **FR-010**: Intermediate results that cross the pause MUST be carried as storage
  references held engine-side, MUST NOT be sent to the browser or routed through the
  user response, and MAY be loaded by reference in the compute phase.
- **FR-011**: The `interactive_response` MUST be recorded in lineage through the
  existing `block_config_resolved` field (ADR-038); intermediate references MUST NOT
  be recorded in lineage.
- **FR-012**: Cancelling an interaction MUST transition the block to `CANCELLED`
  under ADR-019 semantics, release any intermediate scratch, and spawn no compute
  phase.
- **FR-013**: The in-process `_run_interactive` scheduler path MUST be removed;
  interactive blocks MUST NOT execute in the scheduler process.
- **FR-014**: `Data Router` and `Pair Editor` MUST be migrated to inherit
  `InteractiveMixin`, keep `execution_mode = INTERACTIVE` and their ADR-029 variadic
  ports, execute through the two-phase path, resolve their panels via manifest, and
  preserve their existing user-visible behaviour.
- **FR-015**: The interactive prompt delivered to the frontend MUST carry the block
  identity needed to resolve the panel manifest, independent of whether other
  lifecycle events carry `block_type` (the known #1452/#1454 drift).

### Key Entities

- **InteractiveMixin**: The capability mixed into a block to make it interactive.
  Declares `interactive_panel` (a panel manifest), `prepare_prompt`, and relies on
  the category base's `run`. Relationship: layered onto a category base such as
  `ProcessBlock`; paired with `execution_mode = INTERACTIVE`.
- **InteractivePrompt**: The return of `prepare_prompt`. Attributes:
  `panel_payload` (JSON-safe, window-sized view of the data) and `intermediate`
  (tuple of storage references for reuse by the compute phase). Relationship:
  produced in the prompt phase; `panel_payload` flows to the browser, `intermediate`
  flows engine-side to the compute phase.
- **PanelManifest**: The declaration of a block's window frontend component
  (module URL, export name, optional CSS, version), following the ADR-048
  `FrontendManifest` shape, extended only as the panel requires (for example a
  declared response shape). Relationship: served and validated by the backend;
  resolved by the frontend to load the panel.
- **interactive_response**: The JSON-safe decision returned by the panel.
  Relationship: merged into the resolved config for the compute phase and recorded
  in lineage.
- **interactive_intermediate**: The engine-held storage references threaded into
  the compute phase config. Relationship: derived from `InteractivePrompt.intermediate`;
  excluded from lineage; cleaned up on completion or cancellation.

## 4. Implementation Plan

### 4.1 Technical Approach

A new module `scistudio.blocks.base.interactive` defines `InteractiveMixin`, the
`SupportsInteraction` protocol, `InteractivePrompt`, and `PanelManifest`. The block
registry gains a scan-time check that binds `execution_mode = INTERACTIVE` and the
mixin together and validates the panel manifest, in the same import-time style as
existing dynamic-port validation.

The worker entry point gains a phase marker in its invocation payload so a single
worker program can dispatch either `prepare_prompt` (prompt phase) or `run`
(compute phase); both reconstruct typed inputs exactly as today (ADR-017/ADR-027).
The prompt phase returns the `InteractivePrompt` as a JSON result envelope and
exits; the compute phase returns outputs and exits.

The scheduler's interactive handling replaces `_run_interactive` with a two-phase
orchestration: spawn the prompt-phase worker, transition the block to `PAUSED`,
hold the returned `panel_payload` and intermediate references engine-side, emit the
panel payload over the existing event/WebSocket surface, await the
`interactive_response`, then spawn a fresh compute-phase worker with the response
and intermediate references merged into config, and finalize as for any block. The
engine owns the intermediate scratch lifecycle and releases it on completion or
cancellation. The decision reaches lineage automatically because it is part of the
resolved config the compute phase runs with (ADR-038 `block_config_resolved`),
while intermediate references are stripped from the recorded config.

The frontend replaces the hardcoded `InteractiveModals` `blockType` branching with
a panel host that resolves the component from the block's manifest `panel_id`.
Core panels resolve against a built-in panel registry (the bundled
`DataRouterModal` / `PairEditorModal` keyed by `panel_id`); a package panel loads
its module from the manifest's `module_url` by dynamically importing it
(same-origin, reusing the ADR-048 `@vite-ignore` import + version/CSS handling)
and mounting it with a panel host API (`panelPayload`, `confirm`, `cancel`).
The backend serves those package panel assets from a path-confined,
suffix-allowlisted route (`GET /api/blocks/panels/{panel_id}/{asset_path}`,
mirroring the ADR-048 previewer asset route) keyed by the block's
`PanelManifest.asset_root`. No core block ships a wheel-served panel, so the
dynamic-import / asset-serving path is exercised only by packages.

The panel manifest is also surfaced as block metadata for registry/API/palette
consumption: `BlockSpec`, the `BlockSummary` palette DTO, and the
`get_block_schema` response carry `execution_mode` and the serialized
`panel_manifest` (the server-only `asset_root` stays off the wire, used by the
asset route for path confinement). The two core blocks declare manifests, and
their `prepare_prompt` implementations are aligned to return `InteractivePrompt`.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/blocks/base/interactive.py` | create | New `InteractiveMixin`, `SupportsInteraction`, `InteractivePrompt`, `PanelManifest`. |
| `src/scistudio/blocks/base/state.py` | modify | Document `INTERACTIVE` as the capability-gated mode; no enum value change. |
| `src/scistudio/blocks/base/block.py` | modify | Surface the panel manifest on block metadata for API/registry consumption. |
| `src/scistudio/blocks/registry/**` | modify | Scan-time validation pairing capability and execution mode and validating the manifest. |
| `src/scistudio/engine/scheduler/_dispatch.py` | modify | Replace `_run_interactive` with two-phase prompt/compute orchestration. |
| `src/scistudio/engine/scheduler/_events.py` | modify | Wire response handling and cancellation to the two-phase flow. |
| `src/scistudio/engine/scheduler/_lineage.py` | modify | Ensure the decision is recorded and intermediate references are excluded. |
| `src/scistudio/engine/runners/worker.py` | modify | Phase marker dispatching `prepare_prompt` vs `run`. |
| `src/scistudio/engine/runners/local.py` | modify | Spawn prompt and compute phases; thread intermediate references. |
| `src/scistudio/engine/runners/process_handle.py` | modify | Carry the phase marker in the worker payload. |
| `src/scistudio/engine/events.py` | modify | Reuse/adjust interactive prompt/response events for the two-phase flow. |
| `src/scistudio/api/ws.py` | modify | Deliver panel payload and receive the decision under the new flow. |
| `src/scistudio/blocks/process/builtins/data_router.py` | modify | Migrate to `InteractiveMixin`; return `InteractivePrompt`; declare manifest. |
| `src/scistudio/blocks/process/builtins/pair_editor.py` | modify | Same migration. |
| `frontend/src/App.parts/InteractiveModals.tsx` | modify | Replace `blockType` branching with manifest-driven panel host. |
| `frontend/src/components/DataRouterModal.tsx` | modify | Repackage as a manifest-served panel component. |
| `frontend/src/components/PairEditorModal.tsx` | modify | Repackage as a manifest-served panel component. |
| `docs/architecture/ARCHITECTURE.md` | modify | Rewrite §5.2.4 (PAUSED), §5.3 (subprocess isolation), and §5.3.1 ("Interactive blocks run in-process") so interactive blocks are described as two-phase subprocess execution, not an in-process exception. |
| `docs/block-development/block-contract.md` | modify | Document `execution_mode = INTERACTIVE` together with the `InteractiveMixin` capability and the prompt/response/manifest contract. |
| `docs/block-development/architecture-for-block-devs.md` | modify | Correct the statement that interactive blocks run outside subprocess isolation. |
| `docs/block-development/quickstart.md` | modify | Remove the claim that interactive blocks are the in-process exception. |
| `tests/blocks/test_interactive_mixin.py` | create | Capability contract tests. |
| `tests/blocks/test_interactive_registry_validation.py` | create | Scan-time validation tests. |
| `tests/engine/test_interactive_two_phase.py` | create | Two-phase subprocess round-trip tests. |
| `tests/engine/test_interactive_lineage.py` | create | Decision recorded, scratch excluded. |
| `tests/engine/test_interactive_cancellation.py` | create | Clean cancellation tests. |
| `tests/blocks/test_data_router.py` | modify | Behaviour preserved under migration. |
| `tests/blocks/test_pair_editor.py` | modify | Behaviour preserved under migration. |

### 4.3 Implementation Sequence

1. **T-001**: Add `scistudio.blocks.base.interactive` (`InteractiveMixin`,
   `SupportsInteraction`, `InteractivePrompt`, `PanelManifest`). (US1, foundation)
2. **T-002**: Add registry scan-time validation pairing capability and mode and
   validating the manifest; surface the manifest in block metadata. (US3, US1)
3. **T-003**: Add the worker phase marker and dispatch for `prepare_prompt` vs
   `run`. (US1, foundation)
4. **T-004**: Replace `_run_interactive` with the two-phase scheduler
   orchestration, including PAUSED handling, engine-held intermediate references,
   and finalize. (US1)
5. **T-005**: Wire lineage to record the decision and exclude intermediate
   references. (US1)
6. **T-006**: Add cancellation teardown that releases scratch and spawns no compute
   phase. (US3)
7. **T-007**: Replace frontend `blockType` branching with a manifest-driven panel
   host reusing ADR-048 asset serving. (US1)
8. **T-008**: Migrate `Data Router` and `Pair Editor` blocks and repackage their
   panel components as manifest-served. (US2)
9. **T-009**: Update architecture documentation. (cross-cutting)

### 4.4 Verification Plan

Backend unit tests cover the capability contract and registry validation
(`test_interactive_mixin`, `test_interactive_registry_validation`). Engine tests
cover the two-phase subprocess round-trip with response injection and no in-memory
carryover, intermediate-reference threading that never reaches the browser, lineage
recording of the decision with scratch excluded, and clean cancellation
(`test_interactive_two_phase`, `test_interactive_lineage`,
`test_interactive_cancellation`). Migration is verified by the existing
`test_data_router` and `test_pair_editor` suites updated to run under the new model
with unchanged behaviour. Frontend tests cover manifest-driven panel resolution and
the migrated panels. Lint, type, full audit, and the tier-selected check surface
run through `gate_record check`.

### 4.5 Risks And Rollback

The largest risk is that removing `_run_interactive` and migrating the two blocks
must land together, since the blocks break if the in-process path is removed
without migration; the sequence keeps them in one change and the migration tests
gate it. The worker phase marker touches the ADR-017 worker payload, so its tests
must confirm the existing single-phase path is unchanged. Repackaging core panels
as manifest-served components is new frontend wiring; reusing the ADR-048 serving
path limits new surface. Rollback is reverting the branch: there is no persisted
data migration, and lineage gains a field value within the existing
`block_config_resolved`, not a schema change.

The interactive event flow this change reworks is the same EventBus lifecycle
surface as the known #1452/#1454 drift, where `BLOCK_READY`/`BLOCK_RUNNING` do not
carry `block_type`. That drift does not block this work: the panel is resolved from
the prompt event and the block manifest, not from those events. The implementation
must keep block identity on the prompt event (FR-015) so manifest resolution holds
regardless of when #1452/#1454 is addressed, and must avoid regressing the passing
scheduler state-machine cancellation contract that ADR-051's cancellation relies
on.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: An interactive block completes the pause-decide-compute loop end to
  end, with `prepare_prompt` and `run` each observed running in a worker subprocess
  and neither in the scheduler process.
- **SC-002**: 100% of malformed interactive declarations in the validation test
  matrix are rejected at registry scan time rather than at runtime.
- **SC-003**: The user decision is present in the run's `block_config_resolved`
  lineage record, and no intermediate scratch reference appears in lineage, in the
  lineage test.
- **SC-004**: Cancelling a paused interaction results in `CANCELLED`, zero
  compute-phase subprocess spawns, and zero residual intermediate scratch files.
- **SC-005**: `Data Router` and `Pair Editor` produce outputs identical to their
  pre-migration behaviour across the migration test suites.
- **SC-006**: Panel components are resolved from manifests with no remaining
  `blockType`-branching panel selection in the frontend.

## 6. Assumptions

- The ADR-048 asset-serving route and `FrontendManifest` validator are reusable for
  interactive panel components; interactive panels extend that shape only where the
  interaction requires (source: adr).
- The existing worker payload can carry a phase marker without changing the
  single-phase AUTO execution behaviour (source: existing-system).
- Recording the decision needs no lineage schema change because it already travels
  inside the resolved config captured by `block_config_resolved` (source:
  existing-system).
- An indefinite pause is acceptable because the engine holds it with nothing
  resident, so no interaction timeout is required (source: adr).
- The migration of `Data Router` and `Pair Editor` and the runtime change ship in
  the same PR (source: owner).
- The architecture and block-development docs that currently describe interactive
  blocks as running in-process (`docs/architecture/ARCHITECTURE.md` §5.2.4/§5.3/§5.3.1,
  `docs/block-development/block-contract.md`, `architecture-for-block-devs.md`,
  `quickstart.md`) are updated in the implementation PR, not the planning-doc PR,
  because their in-process description is still accurate until the runtime changes
  (source: existing-system).
- The known EventBus lifecycle drift #1452/#1454 (`BLOCK_READY`/`BLOCK_RUNNING`
  missing `block_type`) is not a prerequisite; ADR-051 resolves panels from the
  prompt event and the manifest (source: existing-system).
