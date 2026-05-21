---
spec_id: adr-044-subworkflow-block
title: "ADR-044 SubWorkflowBlock Authoring-Only Container Implementation Specification"
status: Draft
feature_branch: docs/issue-1357/adr-044-subworkflow-spec
created: 2026-05-21
input: "Owner directive 2026-05-21 to make SubWorkflowBlock an authoring/UI-only concept with engine-side inline flattening at load, eliminating the nested-execution surface tracked by issue #890."
owners:
  - "@jiazhenz026"
related_adrs:
  - 44
  - 17
  - 18
  - 22
  - 28
  - 38
  - 42
related_specs: []
scope:
  in:
    - Disk-format contract for SubWorkflowBlock references (config.ref.path) and subworkflow files (top-level exposed_ports section).
    - Engine-side inline flattening of subworkflow references at workflow load time (editor open and run start).
    - Dynamic port adaptation for SubWorkflowBlock derived from referenced subworkflow's exposed_ports.
    - Cycle detection via canonical-path DFS during inline flattening.
    - Lineage snapshot semantics — workflow_yaml_snapshot must contain the flattened YAML.
    - External-file load behaviour — copy into project/subworkflows/ on import.
    - Removal of the existing SubWorkflowBlock stub (sequential executor, _scheduler_factory, _cleanup_callback) and closure of issue #890 by the implementation PR.
    - Frontend UI behaviour for SubWorkflowBlock nodes — dynamic port rendering, double-click tab switch, dangling edge surfacing, SubWorkflowBroken placeholder.
    - MCP / AI agent integration — no new tools; reuse write_workflow.
  out:
    - Reproducibility freeze or version pinning of referenced subworkflows. Reproducibility is provided by the per-run flattened lineage snapshot and user-managed git branches/tags.
    - Cross-project subworkflow catalog or shared library.
    - Subworkflow template parameters distinct from ports. Future spec if needed.
    - Streaming intermediate states of inlined inner blocks back to a "subworkflow node" view in the UI.
    - Automatic rename refactoring of subworkflow files with reference rewriting.
governs:
  modules:
    - scistudio.workflow
    - scistudio.blocks.subworkflow
    - scistudio.api.runtime
    - scistudio.core.lineage
    - frontend.src.components.nodes
  contracts:
    - scistudio.blocks.subworkflow.subworkflow_block.SubWorkflowBlock
    - scistudio.workflow.definition.WorkflowDefinition.flatten_subworkflows
    - scistudio.workflow.schema
    - scistudio.api.runtime.ApiRuntime.load_workflow
    - scistudio.api.runtime.ApiRuntime.start_workflow
  files:
    - src/scistudio/blocks/subworkflow/subworkflow_block.py
    - src/scistudio/workflow/definition.py
    - src/scistudio/workflow/schema.py
    - src/scistudio/workflow/validator.py
    - src/scistudio/workflow/serializer.py
    - src/scistudio/api/runtime.py
    - src/scistudio/core/lineage/recorder.py
    - tests/blocks/test_subworkflow.py
    - tests/workflow/test_flatten_subworkflows.py
    - tests/integration/test_subworkflow_lineage.py
    - frontend/src/components/nodes/SubWorkflowNode.tsx
    - frontend/src/components/nodes/BlockNode.tsx
    - docs/architecture/ARCHITECTURE.md
tests:
  - tests/blocks/test_subworkflow.py
  - tests/workflow/test_flatten_subworkflows.py
  - tests/integration/test_subworkflow_lineage.py
acceptance_source: adr
language_source: en
---

# ADR-044 SubWorkflowBlock Authoring-Only Container Implementation Specification

## 1. Change Summary

This spec translates ADR-044 into implementation requirements. The change is
to make `SubWorkflowBlock` an authoring-only concept and have the engine
inline-flatten subworkflow references at workflow load time. The scheduler,
runners, validator, and lineage recorder always see a flat DAG.

The core requirements are:

- A pure `WorkflowDefinition.flatten_subworkflows` function replaces every
  `SubWorkflowBlock` node with its referenced subworkflow's inner blocks
  and edges, using `<sw_id>__` id prefixes.
- `ApiRuntime.start_workflow` is the single call site for this function;
  it runs the flattener immediately before scheduler dispatch and writes
  the result to `RunRecord.workflow_yaml_snapshot`.
- `ApiRuntime.load_workflow` returns the authored graph unchanged.
  Flattening is run-time-only so that saving from the editor preserves
  every `SubWorkflowBlock` container in the on-disk YAML. The editor
  resolves each `SubWorkflowBlock` node's port surface via the dynamic-
  ports mechanism (FR-004) — a per-node lookup into the referenced
  subworkflow's `exposed_ports`, not whole-graph flattening (rationale:
  Codex P1 on PR #1359).
- `SubWorkflowBlock` retains only dynamic-port derivation from the referenced
  subworkflow's `exposed_ports`. The existing scheduler-injection scaffold
  (`_scheduler_factory`, `_cleanup_callback`, `_sequential_execute`) is
  deleted.
- Cycle detection during flattening uses canonical-path DFS; symbolic links,
  `..` segments, and case-insensitive filesystems all canonicalise.
- The implementation PR closes issue #890 because nested execution is
  rejected by ADR-044.

This spec comes from owner directive 2026-05-21 and is acceptance-sourced
from ADR-044.

## 2. User Scenarios & Testing

### User Story 1 - Collapse a sub-pipeline for canvas readability (Priority: P1)

As a workflow author with a long pipeline, I need to factor a logical sub-section
into a separate subworkflow file and reference it as a single node on the main
canvas.

Why this priority: ADR-044 §3 — the core user-visible problem the ADR
addresses.

Independent Test: Create a main workflow file and a subworkflow file with an
`exposed_ports` section; drop a `SubWorkflowBlock` in the main file with
`config.ref.path` pointing at the subworkflow; verify the canvas shows one
node with the exposed ports.

Acceptance Scenarios:

1. Given a subworkflow file with `exposed_ports` declaring `raw_in` and
   `report`, when the user drops a `SubWorkflowBlock` and sets
   `config.ref.path`, then the node renders with `raw_in` as an input handle
   and `report` as an output handle.
2. Given two referenced subworkflows, when the user connects them on the main
   canvas via their exposed port names, then the edges persist in the parent
   workflow YAML using the `<sw_id>.<exposed_port>` form.
3. Given the user double-clicks a `SubWorkflowBlock` node, when the action
   fires, then the editor opens the referenced subworkflow file in a new tab
   (or switches focus to its existing tab).

### User Story 2 - Engine runs the flattened DAG (Priority: P1)

As a workflow runtime, I need subworkflow references inlined at load time so
the scheduler always sees a flat DAG.

Why this priority: ADR-044 §4 — the architectural decision that eliminates
the #890 surface.

Independent Test: Submit a workflow containing one `SubWorkflowBlock` to
`start_workflow`; assert that the dispatched DAG contains the inner blocks
with prefixed ids and that the `SubWorkflowBlock` node is absent.

Acceptance Scenarios:

1. Given a workflow with one `SubWorkflowBlock` `sw1` containing inner blocks
   `load`, `peak_pick`, `qc_report`, when `start_workflow` is invoked, then
   the dispatched DAG contains exactly `sw1__load`, `sw1__peak_pick`, and
   `sw1__qc_report` (plus other top-level blocks) and no `SubWorkflowBlock`
   nodes.
2. Given nested subworkflows (`sw1` contains `sw2` which contains `load`),
   when flattening runs, then the resulting flat block id is
   `sw1__sw2__load` and the DAG is flat.
3. Given a workflow run completes, when the `RunRecord` row is examined,
   then `workflow_yaml_snapshot` equals the flattened YAML and
   `block_executions` contains rows with the prefixed ids; no
   `parent_run_id` is set.

### User Story 3 - Edits to a referenced subworkflow propagate on next load (Priority: P1)

As a workflow author, I need changes to a subworkflow file to take effect in
every workflow that references it on next load, similar to Python `import`.

Why this priority: ADR-044 §5 — establishes the explicit ref-only semantic
and rejects the freeze-and-refresh UI.

Independent Test: Edit the `exposed_ports` of a subworkflow file; reopen a
parent that references it; verify the parent shows the new port surface and
flags dangling edges where prior connections no longer match.

Acceptance Scenarios:

1. Given a subworkflow with output port `report`, when the parent references
   it and then the subworkflow renames `report` to `summary`, then reopening
   the parent shows the parent's edge to `report` as dangling and the
   `SubWorkflowBlock` node exposes `summary` instead.
2. Given a subworkflow is edited to add a new exposed port, when the parent
   is reopened, then the `SubWorkflowBlock` node shows the new port available
   for connection.
3. Given a run completed before the subworkflow edit, when the lineage
   snapshot for that run is read, then it contains the pre-edit flattened
   YAML and the run can be reconstructed without depending on the current
   state of the subworkflow file.

### User Story 4 - Cycle detection catches reference loops (Priority: P1)

As a workflow loader, I need to detect cyclic subworkflow references and fail
with a clear error chain.

Why this priority: ADR-044 §7 — without cycle detection, recursion can hang
the editor or overflow the stack.

Independent Test: Construct files `a.wf.yaml` and `b.swf.yaml` that reference
each other; assert load raises `CyclicSubworkflowError` with the chain.

Acceptance Scenarios:

1. Given `a.wf.yaml` references `b.swf.yaml` and `b.swf.yaml` references back
   to `a.wf.yaml`, when either is opened, then load raises
   `CyclicSubworkflowError` with chain
   `a.wf.yaml → b.swf.yaml → a.wf.yaml`.
2. Given a symbolic link `alias.swf.yaml` points at `a.wf.yaml` and `a.wf.yaml`
   references `alias.swf.yaml`, when load runs, then cycle detection fires
   because both paths canonicalise to the same inode.
3. Given a user copies `main.wf.yaml` to `external.swf.yaml`, manually
   rewrites the copy to remove its back-references, and references
   `external.swf.yaml` from `main.wf.yaml`, when load runs, then no cycle is
   detected and load succeeds with the inlined content.

### User Story 5 - External subworkflow files import into the project (Priority: P2)

As an author with a subworkflow file outside the current project, I need the
file copied into `<project>/subworkflows/` on import so the resulting
workflow is portable.

Why this priority: ADR-044 §2.1 — convenience and portability. Users could
manually copy files; the auto-import removes the friction.

Independent Test: Open a `SubWorkflowBlock`, pick an external `.swf.yaml`;
verify the file appears in `<project>/subworkflows/` with a project-relative
`config.ref.path` recorded in the parent.

Acceptance Scenarios:

1. Given the user selects an external `.swf.yaml` via the file picker, when
   the picker confirms, then the file is copied into
   `<project>/subworkflows/` with the original filename (or a numeric suffix
   on collision) and `config.ref.path` is set to the project-relative path.
2. Given the same external file is picked twice in two `SubWorkflowBlock`
   nodes, when both imports complete, then the project contains two copies
   with distinct names and each parent reference points to its own copy.
3. Given the project directory is copied to another machine, when the parent
   workflow is opened there, then references resolve against the copied
   subworkflow files in the project (no dependency on the original external
   path).

### User Story 6 - Broken refs surface as red placeholder nodes (Priority: P2)

As an author whose referenced subworkflow file was deleted or moved, I need
the main workflow to still open with a clearly marked broken node so I can
repair it without losing the rest of the workflow.

Why this priority: ADR-044 §10 — graceful degradation; a hard-fail on missing
ref would punish users for filesystem-level events.

Independent Test: Delete the file at `config.ref.path`; reopen the parent;
observe a `SubWorkflowBroken` placeholder node and the rest of the canvas
renders normally.

Acceptance Scenarios:

1. Given a `SubWorkflowBlock` whose `config.ref.path` does not resolve to a
   readable file, when the workflow opens in the editor, then the canvas
   shows a `SubWorkflowBroken` placeholder node (red style) and all other
   blocks render normally.
2. Given the user clicks the broken placeholder, when the action fires, then
   a "locate file…" dialog appears allowing the user to repoint
   `config.ref.path`.
3. Given a workflow run is attempted with an unresolved ref, when
   `start_workflow` runs, then the validator rejects the workflow before
   dispatch with a clear missing-file error.

### Edge Cases

- A `SubWorkflowBlock` whose `config.ref.path` points at a file with no
  `exposed_ports` section (or an empty section) resolves to a node with
  zero ports. Legal but no edges can connect; the validator does not fail
  unless edges reference non-existent ports.
- A subworkflow file referenced by multiple `SubWorkflowBlock` nodes in the
  same parent produces independent prefixed copies in the flat DAG; runtime
  state is independent between copies.
- A subworkflow may reference more subworkflows; flattening handles
  arbitrary nesting depth in one pass. Prefix chains compose
  (`sw1__sw2__load`).
- A subworkflow file may be opened in its own editor tab and executed
  standalone via the normal run path. The `exposed_ports` section is
  ignored during standalone execution; the blocks list runs as a normal DAG
  with user-supplied initial inputs.
- An edge in the parent references `sw.<port>` for a port that is not in
  the referenced subworkflow's `exposed_ports` becomes a dangling edge
  after flattening. The validator rejects it at run start.

## 3. Requirements

### Functional Requirements

- **FR-001:** `WorkflowDefinition.flatten_subworkflows(self) -> WorkflowDefinition`
  exists as a pure function that returns a new definition whose blocks/edges
  contain no `SubWorkflowBlock` nodes.
- **FR-002:** `ApiRuntime.load_workflow` returns the authored workflow
  definition with every `SubWorkflowBlock` node intact. It does **not**
  invoke `flatten_subworkflows`; the editor consumes the authored graph
  so that subsequent saves preserve each `SubWorkflowBlock` container
  byte-for-byte in the on-disk YAML. The editor obtains each node's port
  surface via FR-004 (dynamic ports), not by flattening.
- **FR-003:** `ApiRuntime.start_workflow` calls `flatten_subworkflows`
  before scheduler dispatch and writes the flattened YAML to
  `RunRecord.workflow_yaml_snapshot`. This is the sole call site for the
  flattener.
- **FR-004:** `SubWorkflowBlock.get_effective_input_ports` and
  `get_effective_output_ports` derive the port set from the referenced
  subworkflow's `exposed_ports`, with port `accepted_types` inherited from
  the inner block port at `exposed_ports.<direction>[].internal`.
- **FR-005:** Inline flattening prefixes inner block ids with `<sw_id>__`
  and rewrites all inner edges to use prefixed ids.
- **FR-006:** Inline flattening rewrites parent edges that reference
  `<sw_id>.<exposed_port>` to the prefixed
  `<sw_id>__<internal_block>.<internal_port>`.
- **FR-007:** Inline flattening detects reference cycles via canonical-path
  DFS (paths canonicalised by `Path.resolve(strict=True)`) and raises
  `CyclicSubworkflowError` with the full reference chain.
- **FR-008:** A workflow file with no `exposed_ports` section is legal and
  referenceable; it exposes zero ports to the parent.
- **FR-009:** A workflow file with `exposed_ports` may also be executed
  standalone via the normal run path; `exposed_ports` is ignored at
  standalone run time.
- **FR-010:** Broken refs produce `SubWorkflowBroken` placeholder nodes
  during editor load; other blocks load normally; the validator fails at
  `start_workflow` if any broken-ref placeholder remains.
- **FR-011:** External-file load copies the chosen file into
  `<project>/subworkflows/` (numeric suffix on filename collision) and
  records `config.ref.path` as a project-relative path.
- **FR-012:** The existing `SubWorkflowBlock` stub is deleted:
  `_scheduler_factory`, `_cleanup_callback`, `_run_with_scheduler`,
  `_sequential_execute`, `input_mapping` and `output_mapping` ClassVars,
  and all engine-side injection of these symbols.
- **FR-013:** The implementation PR closes issue #890 with the rationale
  that ADR-044 rejects nested execution.

### Key Entities

- **SubWorkflowBlock** — Authoring-time container class in
  `scistudio.blocks.subworkflow.subworkflow_block`. Carries
  `config.ref.path` and derives ports dynamically from the referenced
  subworkflow's `exposed_ports`. Has no `run()`-time behaviour after
  flattening removes it. Relationships: referenced by zero or more parent
  workflow YAML files; references exactly one subworkflow file via
  `config.ref.path`.
- **WorkflowDefinition** — Existing in-memory workflow representation in
  `scistudio.workflow.definition`. Gains `flatten_subworkflows()` and is
  the contract object passed to scheduler dispatch. Attributes: blocks,
  edges, exposed_ports (when the workflow is itself a subworkflow source).
- **exposed_ports** — Top-level YAML section in a referenceable subworkflow
  file. Has `inputs: [{name, internal}]` and `outputs: [{name, internal}]`
  arrays, where `internal` is `<block_id>.<port>` referencing a block and
  port that must exist in the same file's `blocks` list.
- **SubWorkflowBroken** — Placeholder block type emitted by the parser when
  `config.ref.path` does not resolve. Carries the unresolved path string
  for the editor to display.
- **CyclicSubworkflowError** — Exception type raised during inline
  flattening when canonical-path DFS detects a cycle. Carries the full
  reference chain as a list of `Path` objects.

## 4. Implementation Plan

### 4.1 Technical Approach

- A pure parser-layer flattener (`WorkflowDefinition.flatten_subworkflows`)
  is the single boundary between authoring-layer concepts and runtime
  concepts. It is invoked at exactly one site:
  `ApiRuntime.start_workflow`, immediately before scheduler dispatch.
  `ApiRuntime.load_workflow` returns the authored graph unchanged so the
  editor never sees the flattened form (preserves the save round-trip).
- The flattener is purely functional over on-disk YAML inputs (no
  randomness, no caller-supplied context). The same YAML inputs always
  produce the same flat DAG. This is required so the lineage snapshot
  taken at run start exactly matches the structure that runs.
- `SubWorkflowBlock` retains only its YAML schema identity, the
  `config.ref.path` config field, and `get_effective_*_ports` methods.
  The dynamic-ports mechanism is identical to `CodeBlock`'s existing
  pattern (ADR-028 Addendum 1 D5).
- Lineage schema (ADR-038) is unchanged. Only the input to
  `workflow_yaml_snapshot` changes: it is the flattened YAML rather than
  the on-disk YAML for runs that contain `SubWorkflowBlock` nodes.
- Validator is extended to recognise `SubWorkflowBroken` placeholders and
  fail on them at `start_workflow`. Other validation rules operate on the
  post-flatten DAG and are unchanged.
- Frontend renders `SubWorkflowBlock` nodes with handles derived from the
  effective ports endpoint. Double-click invokes the existing tab-open
  action. `SubWorkflowBroken` placeholders render in the broken-ref style
  with a "locate file…" affordance.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/blocks/subworkflow/subworkflow_block.py` | modify | Delete stub; add `get_effective_input_ports` / `get_effective_output_ports`; keep `config.ref.path` schema. |
| `src/scistudio/workflow/definition.py` | modify | Add `flatten_subworkflows`, cycle detection, prefix logic, edge rewriting. |
| `src/scistudio/workflow/schema.py` | modify | Add optional top-level `exposed_ports` field for workflow YAML schema. |
| `src/scistudio/workflow/validator.py` | modify | Validate `SubWorkflowBroken` placeholders fail at run start; validate post-flatten DAG. |
| `src/scistudio/workflow/serializer.py` | modify | Ensure `exposed_ports` round-trips through serialise/deserialise. |
| `src/scistudio/api/runtime.py` | modify | Call `flatten_subworkflows` in `start_workflow` only. `load_workflow` returns the authored graph unchanged. |
| `src/scistudio/core/lineage/recorder.py` | modify | Ensure the flattened YAML is what reaches `workflow_yaml_snapshot`. |
| `src/scistudio/engine/runners/**` | modify | Remove `_scheduler_factory` injection of `SubWorkflowBlock`. |
| `src/scistudio/engine/scheduler.py` | modify | Remove any path that recognises `SubWorkflowBlock` (none should remain after flattening). |
| `tests/blocks/test_subworkflow.py` | modify | Rewrite: drop stub-behavior tests; add port-derivation tests. |
| `tests/workflow/test_flatten_subworkflows.py` | create | Cycle detection, id prefixing, nested flattening, broken ref placeholder. |
| `tests/integration/test_subworkflow_lineage.py` | create | End-to-end run with `SubWorkflowBlock`; verify snapshot contains flattened YAML and `block_executions` rows. |
| `frontend/src/components/nodes/SubWorkflowNode.tsx` | create | Render `SubWorkflowBlock` with dynamic port handles, double-click tab open, broken-ref state. |
| `frontend/src/components/nodes/BlockNode.tsx` | modify | Route `SubWorkflowBlock` and `SubWorkflowBroken` types to the new component. |
| `docs/architecture/ARCHITECTURE.md` | modify | Update §5.4.7 to describe the authoring-only model; cross-reference ADR-044. |

### 4.3 Implementation Sequence

| ID | Title | Story | Files | Depends on | Verification |
|---|---|---|---|---|---|
| T-001 | Implement `flatten_subworkflows` with cycle detection | US 2, US 4 | `workflow/definition.py`, `workflow/schema.py` | — | `tests/workflow/test_flatten_subworkflows.py` |
| T-002 | Confirm `ApiRuntime.load_workflow` returns the authored graph unchanged; wire per-`SubWorkflowBlock` dynamic-ports resolution + dangling-edge detection via FR-004 | US 1, US 3, US 6 | `api/runtime.py`, `blocks/subworkflow/subworkflow_block.py` | T-001 | unit + manual editor open |
| T-003 | Wire flatten into `ApiRuntime.start_workflow` + lineage snapshot | US 2, US 3 | `api/runtime.py`, `core/lineage/recorder.py` | T-001 | `tests/integration/test_subworkflow_lineage.py` |
| T-004 | Rewrite `SubWorkflowBlock` as authoring-only with dynamic ports | US 1 | `blocks/subworkflow/subworkflow_block.py`, `tests/blocks/test_subworkflow.py` | T-001 | unit |
| T-005 | Validator updates for broken-ref placeholders | US 6 | `workflow/validator.py` | T-001 | unit |
| T-006 | External-file load → copy-to-project | US 5 | `api/runtime.py`, frontend file picker | T-002 | manual + unit |
| T-007 | Frontend `SubWorkflowNode` + dynamic ports + double-click + broken placeholder | US 1, US 6 | `frontend/src/components/nodes/SubWorkflowNode.tsx`, `BlockNode.tsx` | T-002 | Chrome smoke test |
| T-008 | Delete stub: `_scheduler_factory`, `_cleanup_callback`, sequential executor, engine-side injection | FR-012 | `blocks/subworkflow/**`, `engine/runners/**`, `engine/scheduler.py` | T-004 | full audit |
| T-009 | Update ARCHITECTURE.md §5.4.7 | docs | `docs/architecture/ARCHITECTURE.md` | T-008 | frontmatter lint + doc drift |
| T-010 | Close #890 in implementation PR | FR-013 | PR body only | T-008 | PR closing keyword |

### 4.4 Verification Plan

- Unit tests under `tests/workflow/test_flatten_subworkflows.py` and
  `tests/blocks/test_subworkflow.py` cover cycle detection, id prefixing,
  port derivation, broken-ref handling.
- Integration test `tests/integration/test_subworkflow_lineage.py` covers
  end-to-end run + lineage snapshot equality with the flattened YAML.
- Frontend Chrome smoke test (per memory rule "Mandatory Chrome smoke test
  for all UI agents") covers `SubWorkflowNode` rendering, double-click tab
  open, dynamic port handle rendering, broken-ref placeholder.
- `ruff check .`, `ruff format --check .`, `pytest` on relevant directories.
- ADR-042 QA full audit on the implementation PR.
- Frontmatter lint on this spec and ADR-044.
- Sentrux applicability check on the touched source paths.

### 4.5 Risks And Rollback

- **Risk:** A subworkflow edit silently breaks parent edges. **Mitigation:**
  Editor surfaces dangling edges on next load; validator rejects them at
  run start. **Rollback:** None required; the rejection mechanism is the
  rollback signal.
- **Risk:** The flattener performance for deeply nested subworkflows is
  poor. **Mitigation:** Each file read is cached within a single flatten
  invocation (mtime+hash); typical workflows have ≤ 100 inner blocks and
  ≤ 3 nesting levels per Assumption A-004. **Rollback:** Add caching
  across invocations if profiling shows hotspots; the public contract is
  unchanged.
- **Risk:** Symbolic-link or `..`-segment edge cases on Windows cause
  cycle detection to miss a cycle. **Mitigation:** Test fixtures exercise
  symlinks (where the platform supports them), `..` segments, and
  case-insensitive paths; `Path.resolve(strict=True)` is the canonical
  form. **Rollback:** None; the test fixtures guard the implementation.
- **Risk:** Deleting `_scheduler_factory` / `_cleanup_callback` breaks
  some other downstream consumer outside `subworkflow/`. **Mitigation:**
  Grep for both symbol names across the codebase during T-008; engine
  reviewers verify no remaining consumers. **Rollback:** Revert T-008
  alone; the rest of the cascade does not require deletion.
- **Risk:** External-file load misses an edge case where the chosen file
  has the same name as an existing project subworkflow but different
  content. **Mitigation:** Numeric suffix on name collision and a visible
  confirmation in the file picker that the new name was chosen.
  **Rollback:** None; users can rename manually.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001:** Zero `SubWorkflowBlock` nodes reach the scheduler. Measured
  by assertion in scheduler dispatch and by integration test inspecting
  the dispatched DAG.
- **SC-002:** For 100% of runs of workflows that contain `SubWorkflowBlock`
  nodes pre-flatten, `RunRecord.workflow_yaml_snapshot` equals the
  flattened YAML. Measured by integration test.
- **SC-003:** Direct cycles (A→A), 2-cycles (A→B→A), and 3-cycles
  (A→B→C→A) are all detected and produce `CyclicSubworkflowError` with
  the correct chain. Measured by parametrized test fixtures.
- **SC-004:** Issue #890 closed by the implementation PR with the
  `Closes #890` keyword in the PR body. Measured by GitHub state.
- **SC-005:** `_scheduler_factory`, `_cleanup_callback`,
  `_run_with_scheduler`, `_sequential_execute`, `input_mapping`, and
  `output_mapping` symbols are absent from
  `src/scistudio/blocks/subworkflow/**` and from any engine-side injection
  site. Measured by `grep` in CI.
- **SC-006:** `docs/architecture/ARCHITECTURE.md` §5.4.7 describes the
  authoring-only model and cross-references ADR-044. Measured by manual
  review and doc-drift audit.
- **SC-007:** Dropping a `SubWorkflowBlock` on the canvas, setting
  `config.ref.path`, and connecting an edge to/from one of its exposed
  ports persists correctly in the parent workflow YAML and renders
  correctly on reload. Measured by Chrome smoke test.

## 6. Assumptions

- **A-001 (existing-system):** The dynamic-ports mechanism established by
  `CodeBlock` (ADR-028 Addendum 1 D5) — specifically
  `get_effective_input_ports` and `get_effective_output_ports` — covers
  `SubWorkflowBlock`'s port-adaptation needs without further base-class
  changes.
- **A-002 (existing-system):** ADR-038 lineage schema is unchanged by this
  work; only the content of `workflow_yaml_snapshot` changes for runs
  containing `SubWorkflowBlock` nodes pre-flatten.
- **A-003 (owner):** The frontend tab system can open any workflow YAML
  file in its own tab (user confirmed 2026-05-21: "tab 系统早就有了").
- **A-004 (inferred):** Realistic workflows have ≤ 100 inner blocks across
  all nesting levels and ≤ 3 levels of nesting. The flattener is expected
  to complete in tens of milliseconds for such workflows; if profiling
  later shows hotspots, caching across invocations is the planned
  mitigation (§4.5).
- **A-005 (existing-system):** No production workflow YAML files in the
  repository currently contain `SubWorkflowBlock` nodes; the implementation
  PR re-verifies this before deleting the stub.
- **A-006 (adr):** Per ADR-044 §6, no `kind: workflow | subworkflow`
  discriminator is introduced. Any workflow file may be referenced and any
  may be run standalone.
