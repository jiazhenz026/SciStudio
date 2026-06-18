---
title: "No-Context Audit — ADR-050 Workflow Canvas Node Readability"
audit_date: 2026-06-18
auditor: "audit_reviewer (no-context)"
branch: audit/1698-no-context
issue: 1698
governing_docs:
  - docs/adr/ADR-050.md
  - docs/specs/adr-050-canvas-node-readability.md
  - docs/architecture/ARCHITECTURE.md
recommendation: pass-with-fixes
language_source: en
---

# No-Context Audit — ADR-050 Canvas Node Readability

This is an independent, no-context audit. It verifies the workflow-canvas node
implementation against ADR-050 and `docs/specs/adr-050-canvas-node-readability.md`
only, with no knowledge of the task plan, gate record, PR, or commit history.

## 0. Method And Evidence

- Read governing oracle: `docs/adr/ADR-050.md`, the spec, and the relevant
  `ARCHITECTURE.md` section.
- Traced every cross-module connection end-to-end in `frontend/src/**`.
- Ran static analysis (grep for deferral markers and deleted-module references).
- Ran checks myself in the audit worktree
  (`/Users/jiazhenz/SciStudio/.worktrees/feat-1698-audit-no-context`):
  - `npm ci` — OK.
  - `npm run typecheck` — **PASS** (exit 0).
  - `npm run build` — **PASS** (exit 0, built in 37.5s).
  - Targeted vitest suites (ADR-050 node/status/ports/focus/autoLayout/
    layoutConstants/ConfigPanel/PortEditorTable/computeEffectivePorts/
    CapabilityDropdown): **121/121 PASS**.
  - In-scope backend contract tests (`tests/api/test_blocks.py`,
    `tests/blocks/test_registry.py`, `tests/blocks/test_dynamic_ports.py`,
    `tests/blocks/test_registry_package_layout.py`,
    `tests/packaging/test_adr043_package_capabilities.py`): **163/163 PASS**.

### Tooling note (path-resolution hazard, not a code defect)

The audit worktree shares a checkout root with the main repo. Reads with a
bare `frontend/...` path can resolve against the **main** working tree (which
still has the OLD card `BlockNode.tsx`). Every finding below was re-verified by
reading the **absolute worktree path**
(`/Users/jiazhenz/SciStudio/.worktrees/feat-1698-audit-no-context/...`). The
real, rewritten implementation is the square-node model; the old card only
appears under the main checkout and is NOT what this branch ships.

## 1. Findings (ordered by severity)

There are **no P1 (blocking)** findings. The implementation faithfully and
completely realizes ADR-050 + spec. The findings below are P2/P3 quality and
coverage items.

### [P2-1] Focus-mode canvas integration (dim/hide application) is not unit-tested

- Evidence: `frontend/src/components/WorkflowCanvas.tsx:234-259`
  (`applyFocusToNodes` / `applyFocusToEdges`) and `:325-344` (focus derivation
  + `focusActive` gating). The pure focus-set computation is fully tested
  (`WorkflowCanvas.parts/__tests__/focusMode.test.ts`, 12 tests), but the
  WorkflowCanvas-level wrappers that translate `FocusResult` into ReactFlow
  `className`/`opacity`/`pointerEvents` props have no test.
- Why it matters: ADR-050 §5 lists "focus mode computes the expected focus set
  from selection and exits cleanly" and "nodes/edges outside the focus set may
  be hidden or strongly dimmed" as verification targets. The set computation is
  covered; the rendering application (dimming opacity `0.18`, edge opacity
  `0.12`, `pointerEvents: none` on dimmed nodes) is asserted only by manual
  verification, not automatically.
- Severity rationale: P2 not P1 — the logic is small, deterministic, and the
  underlying pure function is covered; the risk is regression drift, not a
  current defect.
- Fix recommendation: add a component test (or a thin extracted-pure test of
  `applyFocusToNodes`/`applyFocusToEdges`) asserting that dimmed nodes get the
  `scistudio-focus-dimmed` class + reduced opacity and that boundary edges are
  dimmed, plus an "exit restores all visibility" assertion at the canvas level.

### [P3-1] `GROUP_PADDING` layout constant is declared but never consumed by the layout adapter

- Evidence: `frontend/src/components/WorkflowCanvas.parts/layoutConstants.ts:42`
  exports `GROUP_PADDING = 24`; `autoLayout.ts` imports only `LAYER_GAP`,
  `SIBLING_GAP`, `HIGH_DEGREE_CLEARANCE`, `NODE_SIZE` (line 26). `GROUP_PADDING`
  is referenced solely by `layoutConstants.test.ts` (positivity assertion).
- Why it matters: ADR-050 §3.2 lists "optional group/subworkflow spacing" as a
  layout spacing constant. It is correctly documented in-source as "Reserved
  for future compound layout," so this is a documented reservation, not an
  untracked "later"/MVP deferral. It is flagged only as a tidiness/dead-export
  observation.
- Fix recommendation: either wire it into a future compound/group ELK pass or
  add a `TODO(#NNN)` citing a follow-up issue so the reservation is tracked per
  the repo deferred-work rule. (Currently it is justified by ADR-050 §3.2 text,
  which is an acceptable citation, so this is borderline informational.)

### [P3-2] `Node<any>` typing in canvas node builders (pre-existing pattern, not new debt)

- Evidence: `flowNodeBuilder.ts:80,107,219` and `WorkflowCanvas.tsx:234`,
  `useFlowNodes.ts:65` use `Node<any>` with a paired
  `eslint-disable-next-line @typescript-eslint/no-explicit-any`.
- Why it matters: the audit brief asks to flag `any`. These are the standard
  ReactFlow heterogeneous-node-data idiom (block/annotation/group nodes share
  one array) and predate this change; they are localized and disable-annotated.
  Not a regression introduced by ADR-050 work.
- Fix recommendation: none required for this PR. Optionally migrate to a
  discriminated `Node<BlockNodeData | AnnotationNodeData | GroupNodeData>` union
  in a separate typing-cleanup task.

## 2. Wiring Verification (接线) — end-to-end traces

All cross-module connections traced are **live and connected** (no
dead-wired/declared-but-unconnected paths found):

| Wire | Path | Status |
|---|---|---|
| Runtime/problem state → square node status surface | `flowNodeBuilder.computeProblemSeverity` → `buildBlockNode.data.problemSeverity` → `BlockNode.tsx:127` → `NodeStatusSurface` | Connected |
| Error click → Logs | `NodeStatusSurface.onErrorClick` → `data.onErrorClick` → `useFlowCallbacks.makeOnErrorClick` → canvas `onErrorClick` → `ProjectWorkspace` → `App.tsx:428 handleErrorClick` → `useBottomPanelControls` sets tab `logs` + expands | Connected (FR-012) |
| Warning click → BottomPanel Config | `NodeStatusSurface.onWarningClick` → `data.onWarningClick` → `useFlowCallbacks.makeOnWarningClick` → canvas `onWarningClick` → `ProjectWorkspace` ← `useCanvasReadability(handleNodeSelect)` (opens `config` tab + expands) | Connected (FR-013) |
| Focus mode controls → store → canvas → (not persisted) | `CanvasReadabilityControls` → `onEnterFocusMode/onExitFocusMode` → `uiSlice.enterFocusMode/exitFocusMode` → `WorkflowCanvas.computeFocusSet` → `applyFocusToNodes/Edges` | Connected; FR-018 honored (no workflow mutation, no dirty flag) |
| Tidy → store batch → layout persistence | `CanvasReadabilityControls.onTidy/onTidyWhole` → `runTidy` → `computeAutoLayout` → `onTidyLayout` → `updateNodeLayoutBatch` (writes only `node.layout`) → existing save/version path | Connected (FR-020..FR-024) |
| BottomPanel Config receives config + lossy-save detail | `ConfigPanel` gets `selectedNode`/`schema`/`blockOutputs`/`edges`; renders schema fields (ordered by `ui_priority`), capability selector, port editor, CodeBlock editor, and `config-lossy-save-detail` | Connected (FR-014, SC-003) |
| Variadic +/- still wired | `BlockNode` → `PortHandles` `AddPortButton`/remove `×` → `handleAddPortConfirmed`/`handleRemovePort` → `onUpdateConfig({input_ports/output_ports})`; min/max via `canAdd*/canRemove*` | Connected (FR-009, SC-004); ADR-029 confirm-on-disconnect preserved |
| Dynamic port colour driven by config | `resolveDrivingConfigValue` → `computeEffectivePorts` → `PortHandles` colour; edges mirror via `useFlowEdges` | Connected |

## 3. Deferral / Leftover Scan

- `TODO`/`FIXME`/`HACK`/`XXX`/`not implemented`/`throw new Error("not implemented")`
  /"for now"/"MVP"/"V1"/commented-out code/empty handlers in the changed canvas,
  node, status, focus, autoLayout, store, and ConfigPanel surfaces: **none found.**
- `@ts-ignore` / `@ts-expect-error`: **none.**
- `eslint-disable`: only the pre-existing `no-explicit-any` on ReactFlow node
  builders (see [P3-2]); annotated and localized.
- Deleted inline-config modules (`InlineConfigField`, `InlineTextInputField`,
  `InlineCapabilitySelector`, `inlineConfigHelpers`, `ErrorMessage`,
  `StatusBadge`, `PausedToast`): **all physically deleted**; no production import
  references remain (remaining `*StatusBadge` matches are unrelated Git/AI
  components). Satisfies FR-015 / SC-002.

## 4. Bug / Edge-Case Review

All ADR-listed edge cases handled correctly:

- **Cyclic graph in tidy**: `autoLayout` passes back-edges to ELK
  (`cycleBreaking.strategy: GREEDY`); test "handles cycles without throwing".
- **Zero-port nodes**: `portRailOffset(index, 0)` returns `NODE_SIZE/2`; body
  renders without empty rails (covered by `nodeGeometry` + compactNode tests).
- **Unknown plugin/category type**: `categoryIcons[...] ?? categoryIcons.custom`
  (🧩) tested; unknown data type keeps deterministic hash colour via
  `resolveTypeColor` (preserved, unchanged).
- **Focus with no selection**: `computeFocusSet` returns `active:false`,
  everything visible; control disabled when `!selectedNodeId`
  (`CanvasReadabilityControls` `disabled={!canFocus}`). Tested.
- **Lossless vs lossy capability**: `computeProblemSeverity` raises `warning`
  only when `lossyOmeFields(...).length > 0`; ConfigPanel omits detail for
  lossless. Both directions tested.
- **Long-label truncation**: `line-clamp-2` + fixed body height; full text in
  `title`; geometry asserted stable. Tested (FR-005).
- **Geometry that can grow**: body uses fixed `NODE_SIZE` inline width/height;
  status/actions/ports are absolute overlays. compactNode test asserts stability
  across idle/running/paused/done/error/skipped/warning (SC-001).
- **Determinism (auto-layout)**: inputs sorted by id, ELK pinned to
  `NETWORK_SIMPLEX` + `LAYER_SWEEP`, results rounded; "identical across runs"
  and "stable regardless of input order" tests pass (SC-006).
- **State-mutation discipline**: focus mutates nothing
  (`focusMode.test.ts` purity test + `uiSlice` actions never touch workflow);
  tidy writes only `node.layout` and is a no-op when nothing matches
  (`workflowSlice.layoutBatch.test.ts`, SC-007). Focus-scoped tidy leaves hidden
  nodes untouched (scope filtering in `autoLayout` + batch only-matching write).

One pre-existing, out-of-scope test failure was observed and cleared (see §6).

## 5. FR / SC Coverage Table

| Req | Status | Evidence |
|---|---|---|
| FR-001 square fixed body | Implemented | `BlockNode.tsx:97-107`; compactNode test |
| FR-002 104×104 default density | Implemented | `nodeGeometry.NODE_SIZE=104`; `flowNodeBuilder.initialWidth/Height` |
| FR-003 no config in body | Implemented | `BlockNode.tsx` (no config render); compactNode "no input/select/textarea" |
| FR-004 no footer/inline error/warning chip | Implemented | compactNode "no inline error / no paused toast"; status via surface only |
| FR-005 2-line label cap | Implemented | `line-clamp-2` + `title`; compactNode label test |
| FR-006 category mark from `data.category` | Implemented | `categoryIcons`; compactNode each-category test |
| FR-007 type semantics on ports/edges/legend | Implemented | `PortHandles` colours + `title`; `TypeLegend` retained |
| FR-008 input-left / output-right rails | Implemented | `PortHandles` Position.Left/Right |
| FR-009 variadic +/- obey min/max | Implemented | ports test (add/remove + min/max hide) |
| FR-010 full port edit in BottomPanel | Implemented | `ConfigPanel` `PortEditorTable`; ConfigPanel SC-003 test |
| FR-011 one fixed-geometry status surface | Implemented | `NodeStatusSurface`; statusSurface "exactly one surface" |
| FR-012 error → select + Logs | Implemented | `onErrorClick` chain → `handleErrorClick` (logs) |
| FR-013 warning → select + Config, no Problems tab | Implemented | `onWarningClick` → `handleNodeSelect` (config); TabBar has no Problems |
| FR-014 lossy-save detail outside body (in Config) | Implemented | `ConfigPanel` `config-lossy-save-detail`; 3 FR-014 tests |
| FR-015 inline components deleted from import graph | Implemented | files deleted; SC-002 grep + ConfigPanel guard test |
| FR-016 inline-config tests removed/rewritten | Implemented | new geometry/status/ports/ConfigPanel suites replace them |
| FR-017 focus control + exit affordance + hidden count | Implemented | `CanvasReadabilityControls` exit button + "N nodes, M edges hidden" |
| FR-018 focus is view state, no mutation | Implemented | `uiSlice` actions + focusMode purity test |
| FR-019 deterministic focus set | Implemented | `computeFocusSet`; focusMode tests |
| FR-020 tidy action | Implemented | `CanvasReadabilityControls` Tidy/Tidy all |
| FR-021 deterministic adapter (elkjs) | Implemented | `autoLayout.ts` (elkjs `^0.11.1`); determinism tests |
| FR-022 tidy writes only `node.layout` | Implemented | `updateNodeLayoutBatch`; layoutBatch test |
| FR-023 tidy explicit only | Implemented | only invoked from control onClick; no auto-layout effect |
| FR-024 batch layout action | Implemented | `updateNodeLayoutBatch` single history entry; test |
| FR-025 ARCHITECTURE updated | Implemented | `ARCHITECTURE.md:1700-1722` (square glyphs, no inline/footer) |
| FR-026 no legacy/flag/fallback | Implemented | no `legacyBlockNode`/`compact=false`/mode switch found |
| FR-027 package→registry→API contract preserved | Implemented | in-scope backend contract tests 163/163 pass |
| FR-028 base_category/subcategory drive marks | Implemented | `buildBlockNode` category from `base_category`; registry tests |
| FR-029 config_schema ui_priority/ui_widget active | Implemented | `ConfigPanel.orderedConfigEntries` sorts by `ui_priority`, `ui_widget` browse |
| FR-030 ports/dynamic/variadic/capabilities active | Implemented | `computeEffectivePorts`, PortHandles, capability selectors; tests |
| FR-031 no package class edits | Implemented | branch diff touches no package block source |
| FR-032 no package-specific node-hint fields | Implemented | no such fields in schemas/diff |
| FR-033 imaging/spectroscopy/LCMS/SRS verified | Implemented | `test_registry_package_layout.py` / `test_adr043_package_capabilities.py` pass |
| SC-001 stable dims across states | Implemented | compactNode each-status geometry test |
| SC-002 no inline-config import path | Implemented | grep + ConfigPanel guard test |
| SC-003 Config owns core/cap/path/code/ports | Implemented | ConfigPanel SC-003 tests |
| SC-004 +/- mutate input_ports/output_ports + limits | Implemented | ports test |
| SC-005 focus set + exit without mutation | Implemented | focusMode tests |
| SC-006 deterministic auto-layout | Implemented | autoLayout determinism tests |
| SC-007 tidy changes only layout + dirty/history | Implemented | layoutBatch test |
| SC-008 ARCHITECTURE no longer inline-card | Implemented | `ARCHITECTURE.md` §ADR-050 block |
| SC-009 typecheck + build pass | Implemented | both exit 0 (ran by auditor) |
| SC-010 backend contract metadata | Implemented | in-scope backend tests pass |
| SC-011 package blocks render w/o source edits | Implemented | package layout/capability tests pass |
| SC-012 no package-facing field removed | Implemented | contract tests pass; no schema field removals in diff |
| SC-013 gate_record check passes | Not verified (out of context boundary) | gate ledger excluded from no-context scope; CI/gate to confirm separately |

Coverage summary: **33/33 FR Implemented; 12/13 SC Implemented, 1 SC
(SC-013, gate check) intentionally not verified** because the gate record is
outside the no-context audit boundary. No Partial or Missing FR/SC.

## 6. Out-Of-Scope Observation (not a finding)

`tests/blocks/io/test_load_data.py::test_load_data_multi_path_package_image`
fails under the full backend run with `assert <Image> is <Image>` (same class,
identity mismatch from duplicate module load paths). Confirmed it:
(a) reproduces on `origin/main`, (b) is not in ADR-050's test list, and
(c) this branch changed no `load_data`/imaging-types/io source. It is a
pre-existing test-isolation artifact, unrelated to ADR-050, and is not charged
against this implementation.

## 7. Recommendation

**pass-with-fixes.**

The implementation is a faithful, complete, no-legacy realization of ADR-050 and
its spec. All 33 FRs and 12 of 13 in-scope SCs are Implemented with code +
test evidence; typecheck, build, the ADR-050 frontend suites (121), and the
in-scope backend contract suites (163) all pass. The two recommended fixes are
non-blocking: add focus-mode canvas-integration tests [P2-1] and track/wire or
TODO-annotate the reserved `GROUP_PADDING` constant [P3-1]. SC-013 (gate check)
must be confirmed by the gate/CI run, which is outside this no-context audit's
boundary.

---

## 8. Manager Resolution (post-audit)

Per owner directive, **all** findings (P1–P3) were fixed before PR readiness.
This section is appended by the manager; the independent audit above is
unmodified.

| Finding | Resolution | Evidence |
|---|---|---|
| **[P2-1]** focus dim/hide not unit-tested | Extracted `applyFocusToNodes`/`applyFocusToEdges` from `WorkflowCanvas.tsx` into a pure module `WorkflowCanvas.parts/applyFocus.ts` and added `__tests__/applyFocus.test.ts` (6 tests: dim application, in-focus identity preservation, no input mutation per FR-018, edge dimming, exit-restores). | `applyFocus.ts`, `__tests__/applyFocus.test.ts`; suite 6/6 pass |
| **[P3-1]** unused `GROUP_PADDING` | Removed the dead export from `layoutConstants.ts` and its assertion from `layoutConstants.test.ts`. Group/subworkflow spacing is out of scope (no compound layout in this implementation); the constant can return with a future compound-layout change. | `layoutConstants.ts`, `__tests__/layoutConstants.test.ts` |
| **[P3-2]** `Node<any>` in node builders/handlers | Replaced every `Node<any>` + `eslint-disable @typescript-eslint/no-explicit-any` in `flowNodeBuilder.ts` (3 builders), `useFlowNodes.ts`, `useCanvasHandlers.ts` (4 handlers), and `applyFocus.ts` with ReactFlow's default `Node` type (`Node<Record<string, unknown>>`). Honest typing (the array is genuinely heterogeneous: block/annotation/group) that matches ReactFlow's default inference, removing the `any` without the `OnNodesChange` cascade a strict `Node<BlockNodeData> \| ...` union triggers. Zero `Node<any>`/`no-explicit-any` remain in these surfaces. | `flowNodeBuilder.ts`, `useFlowNodes.ts`, `useCanvasHandlers.ts`, `applyFocus.ts` |

Post-fix verification (integrated umbrella branch, Node-26 local harness for the
jsdom `localStorage`/Node-20 env gap): `npm run typecheck` clean, `npm run build`
OK, `eslint` clean on all touched files, frontend suite **783/783 pass**,
in-scope backend contract suites **163/163 pass**. SC-013 gate reconciliation is
run by the manager/gate workflow separately.
