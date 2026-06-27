---
title: "No-Context Audit: ADR-044 SubWorkflowBlock Authoring-Only + Inline Flattening"
status: Draft
owners:
  - "@jiazhenz026"
date: 2026-06-21
recommendation: pass-with-must-fix
related_adrs:
  - 44
related_specs:
  - adr-044-subworkflow-block
language_source: en
---

# No-Context Audit: ADR-044 SubWorkflowBlock Authoring-Only + Inline Flattening

## 0. Audit Frame

- Persona: `audit_reviewer`, no-context mode. Judged the branch diff only
  against `docs/adr/ADR-044.md` and `docs/specs/adr-044-subworkflow-block.md`.
- Did not read the issue, manager plan, checklist, dispatch prompts, PR text,
  commit messages, or other audit reports.
- Branch under review: `audit/adr-044-no-context-20260621` (worktree), diff vs
  `origin/main...HEAD`. Implementation commits in range:
  - `66627c30` (backend + flattening)
  - `82fbcfb9` (frontend node)
- Representation note applied per instruction: real code uses
  `WorkflowDefinition.nodes`, colon edge refs `"node_id:port_name"`,
  `exposed_ports.internal` dot form `"block_id.port"`, `api/runtime` package
  (`_runs.py`/`_workflows.py`), and ref key `config.ref.path`. The drift from
  ADR/spec prose is NOT itself flagged.

## 1. Verdict

`pass-with-must-fix`.

The backend (flattening, cycle detection, lineage snapshot, validator
rejection, stub removal) is faithful and well-tested; SC-001, SC-002, SC-003,
SC-005, FR-001..FR-003, FR-005..FR-008, FR-010, FR-011, FR-012 all verified
correct by probe and by the committed tests (36 passed). However the
**frontend block-type contract is wrong** (P0): the real authored node type is
`subworkflow_block`, but the frontend routes/renders only on the literal
`"subworkflow"`, so a real `SubWorkflowBlock` will never reach the new
`SubWorkflowNode` (no dynamic ports, no double-click, no broken UI). A second
correctness defect (P1) makes the double-click open the wrong file for the
FR-011 import path. These must be fixed before merge; the unit tests pass only
because they hardcode the wrong type string, so CI does not catch either.

## 2. Findings (ordered by severity)

### P0-1 — Frontend renders/routes on `"subworkflow"`, but the real block type is `"subworkflow_block"` (FR-004, US1, US6, SC-007)

Evidence (the persisted/API block type is `subworkflow_block`):
- `src/scistudio/workflow/flatten.py:36` — `SUBWORKFLOW_TYPE = "subworkflow_block"`.
- Probe: `_type_name_for_class(SubWorkflowBlock) == "subworkflow_block"`;
  registry alias key is `subworkflow_block` (category `subworkflow` is a
  separate field, not the `block_type`).
- `tests/api/test_runtime_subworkflow_flatten.py:79,137,151` assert
  `block_type == "subworkflow_block"`; `tests/workflow/test_subworkflow_yaml_roundtrip.py:85`
  asserts the same on reload. So a node authored through the real backend
  carries `block_type="subworkflow_block"`.

Evidence (the frontend keys off `"subworkflow"`):
- `frontend/src/components/WorkflowCanvas.parts/useFlowNodes.ts:27` —
  `const SUBWORKFLOW_BLOCK_TYPES = new Set(["subworkflow", "subworkflow_broken"]);`
  → `useFlowNodes.ts:145` routes to `buildSubWorkflowNode` only when this set
  matches.
- `frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.ts:204` —
  double-click guard `authored.block_type !== "subworkflow"` (returns early).
- `frontend/src/components/WorkflowCanvas.parts/flowNodeBuilder.ts:307` —
  `broken = node.block_type === "subworkflow_broken" || ...` (the healthy
  branch expects `"subworkflow"`).
- `frontend/src/types/ui.ts:93` comment is factually wrong: it claims the
  backend block type is `"subworkflow"`.
- Confirmed no normalization exists: `grep -rn "subworkflow_block" frontend/src/`
  returns nothing.

Impact: a real `SubWorkflowBlock` node (`block_type="subworkflow_block"`) fails
the `SUBWORKFLOW_BLOCK_TYPES.has(...)` check and falls through to the generic
`buildBlockNode` path — no dynamic port handles, no double-click open, no
broken-state styling. Breaks FR-004 frontend rendering, US1 AS1/AS3, and
SC-007 (the Chrome smoke acceptance). The `subworkflow_broken` placeholder
routes correctly on both sides; only the healthy `subworkflow_block` path is
broken. The frontend unit test
(`frontend/src/components/nodes/__tests__/SubWorkflowNode.test.tsx:35,41`)
passes only because it hardcodes `blockType: "subworkflow"`, so it gives false
confidence.

Fix: make the frontend match the real type. Change `SUBWORKFLOW_BLOCK_TYPES`
to `new Set(["subworkflow_block", "subworkflow_broken"])`, change the
double-click guard to `!== "subworkflow_block" && !== "subworkflow_broken"`,
change the `flowNodeBuilder.ts` broken check's healthy branch accordingly, fix
the `ui.ts:93` comment, and update the unit test to use
`blockType: "subworkflow_block"` (so CI guards the contract). Keep the
ReactFlow `nodeTypes` registration key (`subworkflow` in
`WorkflowCanvas.tsx:26`) as-is — that is the React Flow node-type map key set
by `buildSubWorkflowNode`'s `type: "subworkflow"`, which is internally
consistent and separate from `block_type`.

### P1-1 — Double-click `openSubworkflow` resolves the ref to the wrong directory for imported subworkflows (US1 AS3, FR-011)

Evidence:
- `import_subworkflow_file` copies imports to `<project>/subworkflows/` and
  returns a project-relative ref like `subworkflows/child.yaml`
  (`src/scistudio/api/runtime/_workflows.py:113-143`;
  `tests/api/test_runtime_subworkflow_flatten.py:163`).
- The flattener resolves `config.ref.path` against the **project root**
  (`flatten.py` `(base / ref).resolve(...)`), so backend resolution correctly
  finds `<project>/subworkflows/child.yaml`.
- The frontend double-click does NOT use the project-root convention. It
  strips the directory: `subworkflowRefToWorkflowId("subworkflows/child.swf.yaml")`
  returns `"child"` (`frontend/src/App.parts/useProjectActions.ts:71-76`),
  then `openSubworkflow` calls `loadWorkflowById("child", "child")`
  (`useProjectActions.ts:379-385`).
- `workflow_path` maps an id to `<project>/workflows/<id>.yaml`
  (`src/scistudio/api/runtime/_workflows.py:25-27`) — i.e. the `workflows/`
  directory, not `subworkflows/`.

Impact: double-clicking a healthy subworkflow node whose ref lives under
`subworkflows/` (the FR-011 default) opens/loads `<project>/workflows/child.yaml`,
which is the wrong file or none. US1 AS3 ("opens the referenced subworkflow
file") fails for the import path. (This bug is currently masked by P0-1, which
prevents double-click from firing at all; fixing P0-1 exposes it.)

Fix: resolve the open action by the project-relative ref path directly rather
than reducing it to a stem-only id, or extend the loader to honor a
`subworkflows/`-relative path. Add a frontend test that drives a ref under
`subworkflows/` through `openSubworkflow` and asserts the resolved target.

### P2-1 — `exposed_ports.internal` port existence is not validated (ADR §9.1 item 3)

Evidence:
- ADR §9.1 requires the validator to check that each referenced file's
  `exposed_ports.internal` references resolve to blocks **and ports** that
  exist in that file.
- `flatten._resolve_own_exposed` validates the **block id** (raises
  `ValueError "references unknown block"`) but never checks the port name on
  that block.
- Probe: a child with `exposed_ports.outputs: [{name: cout, internal:
  load.NO_SUCH_PORT}]` flattens successfully and emits an edge
  `sw1__load:NO_SUCH_PORT -> sink:in` with no flatten-time error.

Impact: an exposed port whose internal port name is wrong is only caught at
run start by the post-flatten validator Check 5/6 **if** a parent edge wires
that exposed port. An unwired bad exposed port survives silently. Net safety is
preserved for the wired/dispatch case (no bad graph reaches the scheduler), so
this is a completeness gap, not a correctness hole.

Fix: in `_resolve_own_exposed` (or a dedicated validator pass), verify the
inner port exists on the referenced block (registry-effective ports), raising
on a missing port. Add a test mirroring
`test_flatten_exposed_internal_unknown_block_raises` for the missing-port case.

### P2-2 — FR-004 `accepted_types` inheritance is implemented but untested

Evidence:
- FR-004 specifies port `accepted_types` are "inherited from the inner block
  port at `exposed_ports.<direction>[].internal`".
- Implemented in `src/scistudio/workflow/subworkflow_ports.py:_accepted_types`
  (registry-based, returns `[t.__name__ ...]`).
- `tests/blocks/test_subworkflow.py:55` (`test_effective_ports_derived_from_exposed_ports`)
  asserts only the port **names**; `_block(...)`/block-local resolution passes
  `registry=None`, so `accepted_types` is always `[]` there. No test exercises
  the registry-backed inheritance path. The API-route path (the authoritative
  typed surface, `routes/workflows.py:_resolved_ports_for_node`) is tested for
  names/broken only (`test_runtime_subworkflow_flatten.py:139-141`), not for
  inherited types.

Impact: a documented contract (type inheritance / port colour correctness in
the editor) has no regression guard.

Fix: add a test that resolves a subworkflow surface with the runtime registry
and asserts the inner block's `accepted_types` propagate to the exposed port.

### P2-3 — FR-009 (standalone run ignores `exposed_ports`) has no dedicated test

Evidence:
- FR-009 / spec §2 edge case: a file with `exposed_ports` runs standalone with
  `exposed_ports` ignored. No subworkflow test asserts this; the FR-009 token
  does not appear in any new test (`grep` of the suite). Behaviour is plausibly
  correct because `start_workflow` only flattens when a `subworkflow_block`
  node is present and the validator/scheduler ignore the `exposed_ports`
  section, but it is unguarded.

Fix: add an integration assertion that a file carrying `exposed_ports` runs
through `start_workflow` normally and its `exposed_ports` does not affect
dispatch.

### P3-1 — "locate file…" affordance shows a dialog but does not persist (US6 AS2)

Evidence:
- `frontend/src/App.parts/useProjectActions.ts:386-397` — `locateSubworkflow`
  calls `promptInput(...)` and discards the result (`void promptInput`); a
  `TODO(#890)` defers persisting the repointed path and re-fetching
  `resolved_ports`.
- US6 AS2 says the dialog must allow the user to "repoint `config.ref.path`."
  The dialog appears, but repointing is a no-op.

Note: the deferral cites `#890`, which the implementation PR is closing
(FR-013/SC-004). Closing the issue the TODO points to leaves the deferral
without a live tracker, contrary to the "tracked TODO must cite an open
follow-up" rule. The repository must point this TODO at a separate open issue.

Fix: either implement persistence (PUT the node config + re-fetch), or retarget
the TODO to a new/open follow-up issue rather than the about-to-be-closed #890.

### P3-2 — Stale `SubWorkflowBlock` references remain in engine docstrings (FR-012 spirit)

Evidence:
- `src/scistudio/engine/runners/platform.py:5` and `:368` still reference
  "nested SubWorkflowBlock subprocess cleanup" in module/method docstrings.
- These are comments only; no live injection code. `git grep` confirms the
  engine never injected `_scheduler_factory`/`_cleanup_callback` even on
  `origin/main`, so FR-012's "all engine-side injection" had nothing to remove.
  SC-005 (symbol absence) is satisfied. This is documentation drift, not a code
  defect.

Fix (optional): scrub the stale `SubWorkflowBlock` mentions from
`platform.py` docstrings, or leave as-is (the Job Object utility is generic).

### P3-3 — No scheduler-side SC-001 assertion

Evidence:
- SC-001 says it is measured "by assertion in scheduler dispatch and by
  integration test." The integration test exists
  (`tests/integration/test_subworkflow_lineage.py:75,99`) and `run()` raises
  if a `SubWorkflowBlock` ever reaches it (`subworkflow_block.py` `run`). There
  is no explicit guard in the scheduler dispatch package
  (`grep` of `engine/scheduler/` for subworkflow returns nothing).

Impact: defense-in-depth gap only; the flattener guarantee + `run()` raise
already enforce SC-001 in practice.

Fix (optional): add a cheap assertion at dispatch that no node is a
`subworkflow_block`.

## 3. Items verified correct (no finding)

- **SC-001** — Probe: nested flatten yields zero subworkflow nodes; ids
  `src, sink, sw1__sw2__load`. `run()` raises `RuntimeError("authoring-only")`
  as a backstop (`subworkflow_block.py`).
- **SC-002** — `start_workflow` sets `prefer_inmemory=had_subworkflows`
  (`api/runtime/_runs.py`), and `_serialise_workflow_snapshot` serialises the
  in-memory flattened def via `dump_yaml_str` rather than re-reading the
  un-flattened on-disk YAML. The disk-read pitfall named in the audit brief is
  correctly avoided. Verified end-to-end by
  `test_lineage_recorder_persists_flattened_snapshot` (snapshot has no
  `subworkflow_block`, has `sw1__load`/`sw1__proc`).
- **SC-003** — Probe: direct `A→A` (chain `a → a`), 2-cycle `B→C→B`, 3-cycle
  `D→E→F→D` all raise `CyclicSubworkflowError` with the correct root-first
  chain. Parametrized test `test_flatten_detects_cycles`.
- **SC-005** — `grep` for `_scheduler_factory|_cleanup_callback|_run_with_scheduler|_sequential_execute`
  across `src/scistudio/` hits only the deletion-describing docstring in
  `subworkflow_block.py`; no live symbols. Tests `test_stub_symbols_removed`,
  `test_module_level_sequential_execute_removed`.
- **FR-002 / FR-003 separation** — `load_workflow`
  (`api/runtime/_workflows.py:99-108`) does not flatten; `start_workflow`
  (`api/runtime/_runs.py`) flattens before validate + dispatch, the sole call
  site. Verified.
- **FR-005 / FR-006** — Probe shows correct `<sw>__` prefixing, nested prefix
  composition (`sw1__sw2__load`), and parent-edge rewrite through nested
  exposed_ports to the deep leaf. Tests
  `test_flatten_rewrites_inner_and_parent_edges`,
  `test_flatten_nested_subworkflows_compose_prefixes`.
- **FR-006 dangling edge** — A parent edge to a removed exposed port is left
  pointing at the deleted `sw` node; validator Check 3 rejects "unknown node"
  at run start. Confirmed by reading `workflow/validator.py:262-282`.
- **FR-007** — `Path.resolve(strict=True)` canonicalisation in `flatten.py`;
  `self_path` seeds the DFS so a loop back to root is detected. Verified.
- **FR-008** — File without `exposed_ports` → zero ports, not broken
  (`subworkflow_ports.resolve_port_surface`); `test_flatten_no_exposed_ports_is_legal`.
- **FR-010** — Probe: missing ref → `subworkflow_broken` placeholder at load;
  strict-mode validator rejects ("could not be resolved"), draft-mode tolerates.
  `validator.py:240-256`; tests `test_flatten_broken_ref_emits_placeholder`,
  `test_flatten_missing_ref_path_is_broken`.
- **FR-011** — `import_subworkflow_file` copies into `<project>/subworkflows/`,
  numeric suffix on collision, returns POSIX project-relative ref. Route
  `POST /api/workflows/import-subworkflow`. Tests
  `test_import_subworkflow_copies_into_project` (incl. `_1` suffix on second
  import).
- **FR-012** — Stub deleted; `run()` raises; ports made dynamic. Verified by
  diff + grep + tests.
- **Serializer round-trip (Codex P1)** — `exposed_ports` defaults to `None`
  and `model_dump(exclude_none=True)` omits it; `dump_yaml_str` is the single
  serialisation source; `config.ref.path` survives save/load. Tests in
  `test_subworkflow_yaml_roundtrip.py`.
- **SC-006** — `docs/architecture/ARCHITECTURE.md` §5.4.7 updated to describe
  the authoring-only model + broken-ref placeholder + run-start rejection and
  cross-references ADR-044.

## 4. Check results (run by the auditor)

```
$ PYTHONPATH=$PWD/src python -m pytest --no-cov tests/workflow/test_flatten_subworkflows.py \
    tests/blocks/test_subworkflow.py tests/workflow/test_subworkflow_yaml_roundtrip.py \
    tests/api/test_runtime_subworkflow_flatten.py tests/integration/test_subworkflow_lineage.py
36 passed in 18.59s

$ PYTHONPATH=$PWD/src python -m ruff check src/scistudio/workflow/flatten.py src/scistudio/workflow/subworkflow_ports.py
All checks passed!

$ grep -rn "_scheduler_factory|_cleanup_callback|_run_with_scheduler|_sequential_execute" src/scistudio/
# only the deletion-describing docstring in blocks/subworkflow/subworkflow_block.py (lines 11-12); no live symbols
```

Probes (run with `PYTHONPATH=$PWD/src`):
- Nested flatten: zero subworkflow nodes; ids `src, sink, sw1__sw2__load`;
  edges `src:out -> sw1__sw2__load:in`, `sw1__sw2__load:out -> sink:in`.
- Cycles: direct / 2 / 3 all raise `CyclicSubworkflowError` with correct chain.
- Broken ref: placeholder emitted; strict-mode validator rejects, draft-mode
  tolerates.
- `exposed_ports.internal` with a nonexistent port: flatten succeeds (no
  port-existence check — see P2-1).
- Type-name probe: `block_type` is `subworkflow_block` (not `subworkflow`) —
  basis for P0-1.

## 5. Out-of-scope / unverifiable in no-context mode

- **FR-013 / SC-004** (PR closes #890 with the `Closes #890` keyword): a
  PR-body fact not visible from the diff; cannot verify here. Flagged only via
  P3-1's note that the deferral TODO points at #890.
- **SC-007** (Chrome smoke test): no runnable browser evidence in the diff. The
  frontend unit test exists but encodes the wrong block type (see P0-1), so it
  does not stand in for SC-007.

## 6. Required actions before merge (must-fix)

1. P0-1 — fix the frontend block-type contract (`subworkflow` →
   `subworkflow_block`) across `useFlowNodes.ts`, `useCanvasHandlers.ts`,
   `flowNodeBuilder.ts`, `ui.ts`, and the unit test.
2. P1-1 — fix double-click ref resolution for `subworkflows/`-relative refs and
   add a test.

Recommended (not blocking): P2-1, P2-2, P2-3 test/validation gaps; P3-1 retarget
the deferral off the closing #890.
