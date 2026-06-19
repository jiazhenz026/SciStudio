[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity
- Repository: SciStudio
- Owner request: Implement ADR-050 §3 — focus mode (frontend-only view state) + tidy layout (deterministic, elkjs, writes only node.layout) + canvas/toolbar/App wiring + batch layout store action.
- Task kind: feature
- Persona: implementer
- Issue: #1698 — https://github.com/zjzcpj/SciStudio/issues/1698
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: feat/1698-canvas-node-readability
- Agent branch: feat/1698-fe2-focus-tidy-store
- Agent worktree: /Users/jiazhenz/SciStudio/.worktrees/feat-1698-fe2-focus-tidy-store
- Gate record: .workflow/records/1698-canvas-node-readability.json
- Checklist: docs/planning/adr-050-canvas-node-readability-checklist.md
- Governing docs: docs/adr/ADR-050.md, docs/specs/adr-050-canvas-node-readability.md

## Required Rules
Read and follow: the issue #1698; AGENTS.md; docs/ai-developer/rules.md; docs/ai-developer/personas/implementer.md; docs/specs/adr-050-canvas-node-readability.md (esp. FR-017..FR-026, SC-005..SC-007); docs/adr/ADR-050.md §3. Read checklist §4 (Shared Interface Contract) — binding.

## Scope — you own ONLY:
- frontend/src/components/WorkflowCanvas.tsx
- frontend/src/components/WorkflowCanvas.parts/{focusMode.ts, autoLayout.ts, layoutConstants.ts, CanvasReadabilityControls.tsx, useCanvasHandlers.ts, useFlowCallbacks.ts, WorkflowMiniMap.tsx} (+ __tests__/**)
- frontend/src/store/** (uiSlice.ts, workflowSlice.ts, workflowSlice.parts/workflowEditActions.ts, types.ts, store/__tests__/**)
- frontend/src/components/Toolbar.tsx, Toolbar.parts/WorkflowGroups.tsx
- frontend/src/App.tsx, frontend/src/App.parts/ProjectWorkspace.tsx
- frontend/package.json, frontend/package-lock.json

You must NOT touch: frontend/src/components/nodes/**, WorkflowCanvas.parts/{flowNodeBuilder.ts,useFlowNodes.ts}, frontend/src/types/ui.ts, BottomPanel/**, App.parts/useBottomPanelControls.ts, any src/** or tests/**. If you need one, STOP and report.

## Work To Do (ADR-050 §3, spec FR-017..FR-026)
1. `WorkflowCanvas.parts/layoutConstants.ts` (create): `NODE_SIZE = 104` (comment: "MUST equal nodeGeometry.NODE_SIZE, ADR-050 §2.1") + deterministic spacing constants (min horizontal layer gap, min vertical sibling gap, high-degree clearance). Add a unit test asserting NODE_SIZE === 104.
2. `WorkflowCanvas.parts/focusMode.ts` (create): PURE function computing the focus set from selected node id(s) + workflow edges — selected nodes + directly connected edges + immediate upstream/downstream neighbors (FR-019). Return visible/dimmed/hidden id sets + counts. No workflow mutation. Unit tests: single selection, multi-selection induced subgraph, edge inclusion, empty-selection disabled, exit restores (FR-018, SC-005).
3. `autoLayout.ts` (create): deterministic adapter around `elkjs` layered layout (left-to-right by data flow). Input: nodes, edges, node dims (NODE_SIZE), scope (whole | focus set). Output: `{ [nodeId]: {x:number;y:number} }`. Must be deterministic & stable across repeated runs on the same input (SC-006). Handle cycles/disconnected components without throwing. Unit tests on representative DAGs.
4. Add `elkjs` to frontend/package.json + lockfile (`npm --prefix frontend install elkjs`). It is the only dependency change allowed.
5. Store (`workflowSlice` + `workflowEditActions.ts` + `types.ts`): add `updateNodeLayoutBatch(positions: Record<string,{x:number;y:number}>)` — ONE history entry, marks dirty, writes ONLY `node.layout` (never id/type/config/ports/edges/state). Mirror existing `createUpdateNodeLayout`. Store test `store/__tests__/workflowSlice.layoutBatch.test.ts`: only layout fields change; one undo entry (SC-007).
6. Focus UI state: store in `uiSlice` (e.g. `focusMode: { enabled, selectedIds, depth }`) with toggle/exit actions, OR keep local to WorkflowCanvas — your choice; if in store, add to `UISlice` in types.ts.
7. `CanvasReadabilityControls.tsx` (create) and/or `Toolbar.parts/WorkflowGroups.tsx`: add a Focus toggle (with visible exit affordance + hidden-count when focus active) and a Tidy action. Tidy = explicit user action only (FR-023). When focus is active, Tidy defaults to the focus scope and ALSO offer whole-workflow tidy (ADR-050 §3.2). Wire Tidy → autoLayout → `updateNodeLayoutBatch` → existing save/version flow.
8. `WorkflowCanvas.tsx`: apply focus dimming/hiding by POST-PROCESSING the array from `useFlowNodes` (set ReactFlow node-level `hidden`/`style`/`className`); do NOT change BlockNodeData or FE-1 files (checklist §4.3). Provide `makeOnWarningClick` via `useFlowCallbacks` → `() => { onSelectNode(id); setActiveBottomTab("config"); }` and pass it into `useFlowNodes` (the opt is optional on FE-1's side). Keep `onErrorClick` routing to Logs. Ensure MiniMap remains useful with square nodes + focus.
9. App wiring (App.tsx / ProjectWorkspace.tsx): pass focus/tidy callbacks and the warning-click → Config-tab handler into the canvas/toolbar. Do not duplicate config editing anywhere.

## Coordination
You are not alone. Work ONLY in your worktree/branch. Do NOT `pip install -e .`. Focus must add/remove/rewrite NOTHING in workflow YAML; tidy writes only `node.layout`. Commit to your branch with AI trailers; do NOT open a PR; do NOT merge.

## TODO And Deferral Rule
`TODO(#1698): <reason>` for any deferral; no hidden later work.

## Required Tests And Checks (run in your worktree)
- `npm --prefix frontend test -- WorkflowCanvas` and `-- workflowSlice`
- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run build` (if it fails only due to nodes/** or BottomPanel/** you don't own, report but don't fix; your owned files must typecheck)
- Commit on `feat/1698-fe2-focus-tidy-store` with trailers `Gate-Record: .workflow/records/1698-canvas-node-readability.json`, `Task-Kind: feature`, `Issue: #1698`, `Assisted-by: claude-code:opus-4.8`.

## Output Required
Report: changed/created file paths; the elkjs version added; test+typecheck results; final commit SHA; confirmation tidy writes only layout + focus mutates no workflow state; any blocker.

## Stop Conditions
Stop and report if: you need an out-of-scope file (esp. nodes/** or types/ui.ts); elkjs proves unsuitable (then propose an equivalent deterministic lib per FR-021 and ask); you cannot add/update required tests.
