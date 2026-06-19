[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity
- Repository: SciStudio
- Owner request: Implement ADR-050 — replace the canvas card BlockNode with a fixed square topology glyph + unified status surface; remove node-body config.
- Task kind: feature
- Persona: implementer
- Issue: #1698 — https://github.com/zjzcpj/SciStudio/issues/1698
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: feat/1698-canvas-node-readability
- Agent branch: feat/1698-fe1-square-node
- Agent worktree: /Users/jiazhenz/SciStudio/.worktrees/feat-1698-fe1-square-node
- Gate record: .workflow/records/1698-canvas-node-readability.json
- Checklist: docs/planning/adr-050-canvas-node-readability-checklist.md
- Governing docs: docs/adr/ADR-050.md, docs/specs/adr-050-canvas-node-readability.md

## Required Rules
Read and follow: the issue #1698; AGENTS.md; docs/ai-developer/rules.md; docs/ai-developer/personas/implementer.md; docs/specs/adr-050-canvas-node-readability.md; docs/adr/ADR-050.md. Read §4 "Shared Interface Contract" of the checklist — it is binding.

## Scope — you own ONLY:
- frontend/src/components/nodes/** (incl. BlockNode.tsx, BlockNode.parts/**, __tests__/**)
- frontend/src/components/WorkflowCanvas.parts/flowNodeBuilder.ts
- frontend/src/components/WorkflowCanvas.parts/useFlowNodes.ts
- frontend/src/types/ui.ts

You must NOT touch: WorkflowCanvas.tsx, WorkflowCanvas.parts/{useCanvasHandlers,useFlowCallbacks,WorkflowMiniMap,focusMode,autoLayout,layoutConstants}.*, store/**, BottomPanel/**, Toolbar/**, App.tsx, App.parts/**, package.json, any src/** or tests/**. You may IMPORT (read-only) from frontend/src/api/capabilities.ts and frontend/src/components/WorkflowEditor/LossySaveWarning.tsx but must NOT edit them. If you need an out-of-scope file, STOP and report.

## Work To Do (ADR-050 §2, spec FR-001..FR-016)
1. Create `nodes/BlockNode.parts/nodeGeometry.ts`: `NODE_SIZE = 104`, `NODE_BORDER_RADIUS = 8`, and port-rail Y-offset helpers for N ports on a 104px rail. (Do NOT cross-import layoutConstants.ts.)
2. Rewrite `nodes/BlockNode.tsx` as a fixed 104×104 square glyph: body shows ONLY block-kind mark (category icon from data.category), block label (capped to 2 visual lines, truncate+title tooltip on overflow, no geometry change), and the unified status surface. NO config fields, NO data-type/role subtitle, NO status footer, NO inline error text, NO warning chip, NO paused toast inside the body. Body must not grow for any reason.
3. Create `nodes/BlockNode.parts/NodeStatusSurface.tsx`: single fixed-geometry surface for runtime state (idle/ready/running/paused/done/error/cancelled/skipped) + problem severity (none/warning/error) per ADR-050 §2.5 priority table. Error has highest priority → on activate calls `data.onErrorClick` (selects node + opens Logs). Warning → on activate calls `data.onWarningClick` (selects node + opens Config). Render as corner dot/ring/badge; never a text row; never changes width/height.
4. Create `nodes/BlockNode.parts/NodeActionToolbar.tsx`: floating run/restart/delete (+ optional menu) shown on hover/selected, positioned OUTSIDE the square; must not consume body space or change measured geometry.
5. Update `BlockNode.parts/PortHandles.tsx`: keep input ports on the left rail, output ports on the right rail, colored by accepted type; keep ADR-029 variadic `+/-` (min/max limits, per-port `-` on hover/selected, `+` at rail end). Align rails to the square via nodeGeometry; rails MAY extend beyond the square for many ports but the body stays fixed. Port labels stay OUTSIDE the body (hover/selected/zoom/accessibility). Keep AddPortDialog working from the rail.
6. In `types/ui.ts`: extend `BlockNodeData` per checklist §4.2 — add `problemSeverity?: "none"|"warning"|"error"` and `onWarningClick?: () => void`. Keep status/errorMessage/errorSummary fields (rendered ONLY via NodeStatusSurface). Keep onUpdateConfig in the type but the node body must not render config editors.
7. In `flowNodeBuilder.ts`: set `initialWidth = initialHeight = NODE_SIZE` (was 280×180); compute `problemSeverity` (error if status==="error"; else warning if `lossyOmeFields(upstreamOmeFields, selectedCapability.metadata_fidelity)` non-empty for a save-direction IO node with a selected capability; else "none") importing `lossyOmeFields` from `../../api/capabilities`; pass `onWarningClick` through. Add OPTIONAL `onWarningClick` to `BlockNodeCallbacks`.
8. In `useFlowNodes.ts`: add OPTIONAL `makeOnWarningClick?: (nodeId: string) => () => void` to `UseFlowNodesOpts` and thread it into buildBlockNode (default undefined so FE-2 call sites still compile).
9. DELETE (remove file + all imports) the inline-config/legacy node path: `InlineConfigField.tsx`, `InlineTextInputField.tsx`, `InlineCapabilitySelector.tsx`, `inlineConfigHelpers.ts`, `ErrorMessage.tsx`, `StatusBadge.tsx`, `PausedToast.tsx`. Split/replace `badgeStyles.ts` so only the category-icon table the square node needs remains. No `legacyBlockNode`, `CardBlockNode`, `compact=false`, or feature flag (FR-026).
10. Tests under `nodes/__tests__/**`: DELETE or rewrite tests asserting inline node config (e.g. inlineConfigHelpers.test.ts, capabilities.test.tsx inline expectations). ADD tests proving: fixed square geometry stable across idle/running/warning/error/paused (SC-001); body renders no config controls; long label truncates to 2 lines without geometry change; status/warning/error render through one surface; error-activate calls onErrorClick, warning-activate calls onWarningClick; `+/-` present and obey min/max (SC-004); port type colors/hover titles preserved. Match the spec's target test files (compactNode/statusSurface/ports).

## Coordination
You are not alone in the codebase. Work ONLY in your worktree/branch. Do NOT use `pip install -e .`. New callback opts MUST be OPTIONAL. Do not revert/overwrite other agents' work. Commit to your branch with AI trailers; do NOT open a PR (the manager integrates). Do NOT merge anything.

## TODO And Deferral Rule
Deferred work must be tracked: `TODO(#1698): <reason>`. No hidden V1/MVP/later.

## Required Tests And Checks (run in your worktree)
- `npm --prefix frontend test -- BlockNode`
- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run build` (note: build runs the whole app; if it fails ONLY due to FE-2/FE-3-owned files you don't own, report it but don't fix out-of-scope files — your slice must typecheck for the files you own)
- Stage your changes and commit on `feat/1698-fe1-square-node` with trailers:
  `Gate-Record: .workflow/records/1698-canvas-node-readability.json`,
  `Task-Kind: feature`, `Issue: #1698`, `Assisted-by: claude-code:opus-4.8`.

## Output Required
Report: changed/created/deleted file paths; test+typecheck results; the final commit SHA on your branch; any blocker/scope issue; confirmation the node body renders no config and geometry is fixed 104×104.

## Stop Conditions
Stop and report if: you need an out-of-scope file; the task conflicts with ADR-050/spec/checklist §4; you cannot add/update required tests; another agent's contract blocks you.
