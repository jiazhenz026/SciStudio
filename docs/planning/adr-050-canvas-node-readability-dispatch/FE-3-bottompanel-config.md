[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity
- Repository: SciStudio
- Owner request: Implement ADR-050 config-ownership layer — BottomPanel Config is the SOLE computational-config surface; add selected-node lossy-save + validation detail; verify port editor / capability / type semantics survive node simplification.
- Task kind: feature
- Persona: implementer
- Issue: #1698 — https://github.com/zjzcpj/SciStudio/issues/1698
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: feat/1698-canvas-node-readability
- Agent branch: feat/1698-fe3-bottompanel-config
- Agent worktree: /Users/jiazhenz/SciStudio/.worktrees/feat-1698-fe3-bottompanel-config
- Gate record: .workflow/records/1698-canvas-node-readability.json
- Checklist: docs/planning/adr-050-canvas-node-readability-checklist.md
- Governing docs: docs/adr/ADR-050.md, docs/specs/adr-050-canvas-node-readability.md

## Required Rules
Read and follow: the issue #1698; AGENTS.md; docs/ai-developer/rules.md; docs/ai-developer/personas/implementer.md; docs/specs/adr-050-canvas-node-readability.md (esp. FR-003/FR-010/FR-013/FR-014/FR-027..FR-032, SC-002/SC-003); docs/adr/ADR-050.md §2.3. Read checklist §4.4 — binding.

## Scope — you own ONLY:
- frontend/src/components/BottomPanel.tsx
- frontend/src/components/BottomPanel.parts/{ConfigPanel.tsx, FormatCapabilityConfig.tsx, TabBar.tsx} (+ ConfigPanel.test.tsx and any new tests in BottomPanel.parts/)
- frontend/src/components/WorkflowEditor/LossySaveWarning.tsx
- frontend/src/components/PortEditorTable.tsx (+ PortEditorTable.test.tsx)
- frontend/src/components/PortEditor/CapabilityDropdown.tsx
- frontend/src/components/TypeLegend.tsx
- frontend/src/config/typeColorMap.ts
- frontend/src/api/capabilities.ts
- frontend/src/utils/computeEffectivePorts.ts (+ its __tests__)
- frontend/src/__tests__/CapabilityDropdown.test.tsx
- frontend/src/App.parts/useBottomPanelControls.ts (verify; avoid signature changes — coordinate via STOP if a change is unavoidable)

You must NOT touch: frontend/src/components/nodes/**, WorkflowCanvas* (incl. WorkflowCanvas.parts/**), frontend/src/store/**, frontend/src/types/ui.ts, App.tsx, App.parts/ProjectWorkspace.tsx, package.json, any src/** or tests/**. If you need one, STOP and report.

## Work To Do (ADR-050 §2.3, spec FR-003/FR-013/FR-014)
1. Verify ConfigPanel already renders EVERY computational config control needed after inline node config is deleted: core_type/enum, scalar/number/boolean, file & directory browsers, format capability selector (FormatCapabilityConfig + CapabilityDropdown), CodeBlock editor, and full variadic port editing (PortEditorTable: naming + type selection, min/max). Fill any gap so nothing that used to be inline-on-node is lost (FR-003, SC-003). The canvas node will render NO config — BottomPanel is authoritative.
2. Lossy-save warning detail (FR-014): in `ConfigPanel`, render `<LossySaveWarning>` for the SELECTED save-direction IO node when its selected capability would drop upstream OME fields. Compute the source field list from the selected node's upstream block outputs using `collectUpstreamOmeFields` (exported from LossySaveWarning) over `blockOutputs` + `edges`. Accept `blockOutputs` and `edges` as new props on ConfigPanel/BottomPanel (FE-2's wiring will pass them; define them OPTIONAL so this compiles standalone and degrades gracefully when absent). The detail must live in Config detail, NOT on the canvas node, NOT in a new Problems tab (FR-013).
3. Keep `LossySaveWarning.tsx` as the presentational component + helpers (`collectUpstreamOmeFields`, `flattenOmeFields`). It is no longer imported by the node body; it is imported by ConfigPanel. Keep `lossyOmeFields` in api/capabilities.ts intact and exported (FE-1 imports it read-only — do NOT change its signature).
4. `TabBar.tsx`: do NOT add a Problems tab. Logs (errors) and Config (warnings/validation) remain the destinations.
5. Verify TypeLegend + typeColorMap continue to carry data-type semantics (port/edge color, hover, hash fallback for unknown plugin types). No data-type subtitle anywhere in node body (that's FE-1's concern; just keep type semantics intact here).
6. Verify computeEffectivePorts + CapabilityDropdown behavior unchanged for dynamic ports + capability selection.
7. Tests: rewrite/extend `ConfigPanel.test.tsx` to prove BottomPanel owns core_type, capability, file path, CodeBlock, and variadic port editing (SC-003) AND renders the lossy-save warning detail for a selected node (FR-014). Keep/extend PortEditorTable.test.tsx, CapabilityDropdown.test.tsx, computeEffectivePorts tests. Assert no production import path references InlineConfigField/InlineTextInputField/InlineCapabilitySelector/inlineConfigHelpers from your owned files (SC-002).

## Coordination
You are not alone. Work ONLY in your worktree/branch. Do NOT `pip install -e .`. New props you add MUST be OPTIONAL. Do not revert/overwrite others' work. Commit to your branch with AI trailers; do NOT open a PR; do NOT merge. Note: FE-1 deletes the inline-config components and their node imports — you do NOT delete node files; you only ensure BottomPanel covers their former function.

## TODO And Deferral Rule
`TODO(#1698): <reason>` for any deferral.

## Required Tests And Checks (run in your worktree)
- `npm --prefix frontend test -- ConfigPanel` and `-- CapabilityDropdown` and `-- computeEffectivePorts`
- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run build` (if it fails only due to nodes/** or WorkflowCanvas* you don't own, report but don't fix)
- Commit on `feat/1698-fe3-bottompanel-config` with trailers `Gate-Record: .workflow/records/1698-canvas-node-readability.json`, `Task-Kind: feature`, `Issue: #1698`, `Assisted-by: claude-code:opus-4.8`.

## Output Required
Report: changed/created file paths; what config controls were already covered vs. newly added; test+typecheck results; final commit SHA; confirmation BottomPanel is the sole config surface and lossy detail renders in Config; any blocker.

## Stop Conditions
Stop and report if: you need an out-of-scope file; useBottomPanelControls needs a signature change; you find config functionality that cannot move to BottomPanel; you cannot add/update required tests.
