[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement the frontend half of ADR-044 SubWorkflowBlock authoring-only model.
- Task kind: feature
- Persona: implementer
- Issue: #890
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/890
- Umbrella PR: #1736 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-044-subworkflow-20260621
- Agent branch: feature/adr-044-frontend-20260621
- Agent worktree: /Users/jiazhenz/SciStudio-adr044-frontend-20260621
- Gate record: .workflow/records/890-adr-044-subworkflow.json (manager-owned; you do NOT run gate finalize/PR — you implement + report)
- Checklist: docs/planning/adr-044-subworkflow-checklist.md (Track B)

## Required Rules

Read and follow:
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/personas/implementer.md
- docs/adr/ADR-044.md and docs/specs/adr-044-subworkflow-block.md (the design you implement)

## Scope

You own ONLY (all under `frontend/`):
- `frontend/src/components/nodes/SubWorkflowNode.tsx` (NEW)
- `frontend/src/components/nodes/__tests__/SubWorkflowNode.test.tsx` (NEW)
- `frontend/src/components/WorkflowCanvas.tsx` (nodeTypes registry + onNodeDoubleClick wiring)
- `frontend/src/components/WorkflowCanvas.parts/useFlowNodes.ts` (dispatch branch for subworkflow nodes)
- `frontend/src/components/WorkflowCanvas.parts/flowNodeBuilder.ts` (add `buildSubWorkflowNode`)
- `frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.ts` (add `handleNodeDoubleClick`)
- `frontend/src/types/api.ts` (add the `resolved_ports` surface type on the workflow-node response type)
- Threading double-click → open-tab through `frontend/src/App.parts/*` / `ProjectWorkspace.tsx` as needed (open referenced file in a canvas tab).
- Any other `frontend/**` file strictly needed to wire the above — but if it is outside `frontend/`, STOP and report.

You MUST NOT touch:
- Anything under `src/` (Python backend) — the backend is implemented by the manager.
- `tests/` (python).
- Any `frontend/` file unrelated to subworkflow rendering/routing/double-click.

If you need an out-of-scope file, STOP and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. The manager is implementing the Python backend in parallel.
- MUST work only on branch `feature/adr-044-frontend-20260621` in worktree `/Users/jiazhenz/SciStudio-adr044-frontend-20260621`.
- MUST NOT use `pip install -e .` or `npm` global installs that pollute; use the worktree's own `frontend/node_modules` (run `npm install` inside `frontend/` of YOUR worktree if needed).
- Do NOT open a PR. Do NOT merge. Report changed files + test results back to the manager, who integrates.
- Edit only your Track B checklist rows (the manager maintains the checklist; just report row updates in your final message).

## LOCKED BACKEND CONTRACT (do not deviate; build against exactly this)

1. Two block types exist:
   - `subworkflow` — an authoring container node referencing an external workflow file.
   - `subworkflow_broken` — placeholder emitted when the referenced file cannot be resolved.
2. The workflow GET response (`GET /api/workflows/{id}`) returns each node with the usual fields
   (`id`, `block_type`, `config`, `execution_mode`, `layout`) PLUS, for subworkflow / subworkflow_broken
   nodes, an OPTIONAL field:
   ```ts
   resolved_ports?: {
     inputs: { name: string; accepted_types: string[] }[];
     outputs: { name: string; accepted_types: string[] }[];
     broken: boolean;
     ref_path: string | null;
   }
   ```
   This field is response-only (never persisted). For `subworkflow_broken` nodes, `broken: true` and
   `inputs`/`outputs` are empty.
3. The referenced file path is stored at `config.ref.path` (a project-relative string). Read it from the node's `config.ref?.path`.
4. Edges use COLON refs `"node_id:port_name"`. A subworkflow node's React Flow Handle `id` MUST equal the
   exposed port name so existing edge connect/persist logic (`useCanvasHandlers.handleConnect`) works unchanged.
5. Double-clicking a subworkflow node opens the referenced workflow file (`config.ref.path`) in a canvas tab
   (open existing tab if already open). Use the existing tab/open-workflow machinery
   (`useProjectActions` / `loadWorkflowById` pattern). For a `subworkflow_broken` node, double-click instead
   surfaces a "locate file…" affordance (a simple prompt/dialog is acceptable for this iteration; wire it so the
   user could repoint `config.ref.path` — if full repoint plumbing is large, render the affordance and leave a
   `TODO(#890)` for the repoint persistence and report it).

## Existing anchors (verified by manager investigation — use these, do NOT invent new patterns)

- `nodeTypes` map is in `WorkflowCanvas.tsx` (~lines 22-25). Add `subworkflow: SubWorkflowNode`. Render
  `subworkflow_broken` via the SAME `SubWorkflowNode` component using a `data.broken` flag (do not add a second component).
- Node-build dispatch is in `WorkflowCanvas.parts/useFlowNodes.ts` (~lines 87-138) — add a branch for
  `block_type === "subworkflow" || "subworkflow_broken"` BEFORE the generic `buildBlockNode`.
- Add `buildSubWorkflowNode` in `WorkflowCanvas.parts/flowNodeBuilder.ts` (model on `buildBlockNode`,
  ~lines 192-260): emit `type: "subworkflow"`, pack `inputPorts`/`outputPorts` from `node.resolved_ports`,
  plus `refPath` and `broken` into node `data`.
- `SubWorkflowNode.tsx`: reuse the existing `PortHandles` component with `isVariadicInputs/Outputs={false}`
  and `canAdd/canRemove={false}` (ports come from the referenced file, not user edits). Use
  `getCategoryVisual("subworkflow")` (already defined in `categoryVisuals.ts`, Package icon / pink) for styling.
  Broken state: red styling + a clear "broken reference" label showing the unresolved `ref_path`.
- Double-click: there is NO `onNodeDoubleClick` today — add `handleNodeDoubleClick` in
  `useCanvasHandlers.ts`, wire it onto `<ReactFlow>` in `WorkflowCanvas.tsx` (~lines 312-328), and thread the
  prop up to where workflow tabs are opened.
- `BlockNode.tsx` does NOT need editing — routing is in the nodeTypes map + useFlowNodes, not BlockNode.

## TODO And Deferral Rule

Deferred work must be tracked with `TODO(#890): <reason>` citing issue #890. No hidden later/MVP work.
Known acceptable deferral: full broken-ref repoint persistence may be a `TODO(#890)` if large — render the affordance now and report.

## Work To Do

1. Add the `resolved_ports` type to `frontend/src/types/api.ts` and the workflow-node response type.
2. Create `SubWorkflowNode.tsx` rendering dynamic port handles from `resolved_ports`, broken-ref red state, and the subworkflow category visual.
3. Register `subworkflow` in `nodeTypes`; route `subworkflow`/`subworkflow_broken` in `useFlowNodes.ts`; add `buildSubWorkflowNode`.
4. Add double-click → open referenced file tab (and broken → locate-file affordance).
5. Unit test `SubWorkflowNode.test.tsx`: renders input/output handles from `resolved_ports`; renders broken state; handle ids equal exposed port names.
6. Run frontend checks (below) and report.

## Required Tests And Checks (run inside `frontend/` of YOUR worktree)

- `npm test -- SubWorkflowNode` (or the repo's vitest/jest invocation) — your new test must pass.
- `npm run lint` (or `npx eslint`) on changed files — no new errors.
- `npm run typecheck` (or `npx tsc --noEmit`) — no new type errors.
- Report the exact commands you ran and their results.

## Output Required

Before reporting done, provide:
- Changed file paths (full list).
- Tests/checks run and their results (verbatim pass/fail summary).
- The exact `data` shape your `buildSubWorkflowNode` produces (so the manager can confirm contract alignment).
- Any blocker, scope issue, or TODO(#890) you left.
- A note on how double-click resolves `config.ref.path` to a tab (which existing function you reused).

## Stop Conditions

Stop and report back if:
- You need a file outside `frontend/`.
- The locked contract above is insufficient or contradicts the existing frontend data flow.
- `npm install` / lint / typecheck fails for unclear reasons.
- You cannot add the required test.
