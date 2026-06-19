---
spec_id: adr-050-canvas-node-readability
title: "ADR-050 Canvas Node Readability Implementation Specification"
status: Planned
feature_branch: docs/canvas-node-readability-adr
created: 2026-06-18
input: "Owner request: write the implementation spec for ADR-050, list all affected surfaces, and make clear that the implementation leaves no compatibility or legacy node mode."
owners:
  - "@jiazhenz026"
related_adrs:
  - 50
related_specs: []
scope:
  in:
    - Replace the current block-node card implementation with ADR-050 fixed square topology glyphs.
    - Remove node-body computational config and route all computational config editing through BottomPanel Config.
    - Preserve canvas port handles and variadic +/- topology controls.
    - Replace separate status footer, inline error text, and warning chips with one fixed-geometry node status surface.
    - Preserve existing package-to-registry-to-API block schema contracts that feed canvas nodes and BottomPanel config.
    - Verify package-provided blocks from every monorepo block package render through the new node model without package source changes.
    - Add focus mode as frontend-only canvas view state.
    - Add an explicit tidy layout command backed by deterministic graph layout and existing node.layout persistence.
    - Update toolbar/canvas wiring, store actions, frontend tests, and architecture documentation affected by the new canvas model.
    - Remove old inline-config/card code paths rather than preserving them as compatibility or legacy modes.
  out:
    - Changing workflow YAML schema beyond existing node.layout metadata.
    - Changing backend scheduler, validation, lineage, runtime execution, or data object contracts.
    - Changing package block classes, package entry points, package assets, or package runtime behavior for node rendering.
    - Adding package-specific UI fields, old-node compatibility flags, or square-node hints to block packages.
    - Replacing ReactFlow.
    - Replacing SubWorkflowBlock or changing ADR-044 flattening behavior.
    - Adding persisted focus presets or named canvas views.
    - Adding a new Problems bottom-panel tab in the first implementation.
    - Maintaining a feature flag, user preference, or fallback that restores the old long-card node UI.
governs:
  modules:
    - scistudio.api.routes.blocks
    - scistudio.api.schemas
    - scistudio.blocks.registry
  contracts:
    - scistudio.workflow.definition.NodeDef
    - scistudio.workflow.schema.NodeModel
    - scistudio.api.schemas.WorkflowNode
    - scistudio.blocks.registry.BlockSpec
    - scistudio.api.schemas.BlockSummary
    - scistudio.api.schemas.BlockSchemaResponse
    - scistudio.api.routes.blocks.list_blocks
    - scistudio.api.routes.blocks.get_block_schema
  entry_points:
    - scistudio.blocks
    - scistudio.types
  files:
    - docs/**
    - src/scistudio/blocks/base/block.py
    - src/scistudio/blocks/registry/__init__.py
    - src/scistudio/blocks/registry/_spec.py
    - src/scistudio/blocks/registry/_scan.py
    - src/scistudio/api/schemas.py
    - src/scistudio/api/routes/blocks.py
    - packages/scistudio-blocks-*/pyproject.toml
    - packages/scistudio-blocks-*/src/scistudio_blocks_*/__init__.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/interactive/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/math/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/measurement/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/morphology/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/preprocess/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/projection/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/registration/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/segmentation/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/tracking/**/*.py
    - packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/visualization/**/*.py
    - packages/scistudio-blocks-lcms/src/scistudio_blocks_lcms/analysis/**/*.py
    - packages/scistudio-blocks-lcms/src/scistudio_blocks_lcms/external/**/*.py
    - packages/scistudio-blocks-lcms/src/scistudio_blocks_lcms/io/**/*.py
    - packages/scistudio-blocks-lcms/src/scistudio_blocks_lcms/isotope_tracing/**/*.py
    - packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/blocks/**/*.py
    - packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/**/*.py
    - packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/**/*.py
    - packages/scistudio-blocks-srs/src/scistudio_blocks_srs/spectral_extraction/**/*.py
    - frontend/package.json
    - frontend/package-lock.json
    - frontend/src/types/api.ts
    - frontend/src/App.tsx
    - frontend/src/App.parts/ProjectWorkspace.tsx
    - frontend/src/App.parts/useBottomPanelControls.ts
    - frontend/src/api/capabilities.ts
    - frontend/src/utils/computeEffectivePorts.ts
    - frontend/src/components/Toolbar.tsx
    - frontend/src/components/Toolbar.parts/WorkflowGroups.tsx
    - frontend/src/components/WorkflowCanvas.tsx
    - frontend/src/components/WorkflowCanvas.parts/WorkflowMiniMap.tsx
    - frontend/src/components/WorkflowCanvas.parts/flowNodeBuilder.ts
    - frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.ts
    - frontend/src/components/WorkflowCanvas.parts/useFlowCallbacks.ts
    - frontend/src/components/WorkflowCanvas.parts/useFlowNodes.ts
    - frontend/src/components/nodes/BlockNode.tsx
    # ADR-050 implementation deletes the inline-config / status-footer parts
    # (InlineConfigField, InlineTextInputField, InlineCapabilitySelector,
    # inlineConfigHelpers, ErrorMessage, StatusBadge, PausedToast) and adds the
    # square-node parts (NodeStatusSurface, NodeActionToolbar, nodeGeometry).
    # Governed via a glob so the manifest tracks the directory, not a frozen
    # file list that drifts when parts are added/removed.
    - frontend/src/components/nodes/BlockNode.parts/**
    - frontend/src/components/BottomPanel.tsx
    - frontend/src/components/BottomPanel.parts/ConfigPanel.tsx
    - frontend/src/components/BottomPanel.parts/FormatCapabilityConfig.tsx
    - frontend/src/components/BottomPanel.parts/TabBar.tsx
    - frontend/src/components/PortEditorTable.tsx
    - frontend/src/components/TypeLegend.tsx
    - frontend/src/components/WorkflowEditor/LossySaveWarning.tsx
    - frontend/src/components/PortEditor/CapabilityDropdown.tsx
    - frontend/src/config/typeColorMap.ts
    - frontend/src/store/types.ts
    - frontend/src/store/uiSlice.ts
    - frontend/src/store/workflowSlice.ts
    - frontend/src/store/workflowSlice.parts/workflowEditActions.ts
    - frontend/src/types/ui.ts
  excludes:
    - docs/user/reference/**
    - docs/user/llms.txt
tests:
  - frontend/src/utils/__tests__/computeEffectivePorts.test.ts
  - frontend/src/__tests__/CapabilityDropdown.test.tsx
  - frontend/src/components/nodes/__tests__/BlockNode/compactNode.test.tsx
  - frontend/src/components/nodes/__tests__/BlockNode/statusSurface.test.tsx
  - frontend/src/components/nodes/__tests__/BlockNode/ports.test.tsx
  - frontend/src/components/WorkflowCanvas.parts/__tests__/autoLayout.test.ts
  - frontend/src/components/WorkflowCanvas.parts/__tests__/focusMode.test.ts
  - frontend/src/components/BottomPanel.parts/ConfigPanel.test.tsx
  - frontend/src/components/PortEditorTable.test.tsx
  - frontend/src/store/__tests__/workflowSlice.layoutBatch.test.ts
acceptance_source: adr
language_source: en
---

# ADR-050 Canvas Node Readability Implementation Specification

## 1. Change Summary

This spec turns ADR-050 into an executable implementation plan. The workflow
canvas must move from the current long card node shape to a fixed square node
shape that shows block identity, port topology, and a single status surface.
Computational config must leave the node body and live in BottomPanel Config.

The implementation also adds two canvas readability controls:

- **Focus mode** narrows or dims the graph around the selected node or selected
  subgraph without changing workflow YAML.
- **Tidy layout** computes deterministic node positions and writes only the
  existing `node.layout` metadata.

This is a replacement, not an additive compatibility layer. The old node card,
inline config strip, status footer, inline error message, and warning chip
inside the node body must be removed from the active implementation. Existing
workflow YAML remains valid because the persistent schema is unchanged.

## 2. User Scenarios & Testing

### User Story 1 - Read A Complex Canvas Quickly (Priority: P1)

As a workflow author, I can scan a complex workflow as topology instead of as a
collection of mini forms.

Why this priority: the owner problem is canvas spaghetti caused by large,
content-heavy nodes and tangled graph structure.

Independent Test: render representative block nodes and assert fixed square
geometry, no inline config fields, stable port rails, and no geometry change
when status or warning data is present.

Acceptance Scenarios:

- Given a block with several config fields, when it renders on the canvas, then
  the node body contains the block label, block-kind mark, ports, actions, and
  status only.
- Given a long block name, when it renders, then the node remains square and
  the label is truncated to two visual lines.
- Given an error message, lossy-save warning, or paused state, when it renders,
  then the node status surface changes but the node body does not grow.

### User Story 2 - Configure Blocks In One Place (Priority: P1)

As a workflow author, I can select a node and edit all computational config in
BottomPanel Config without also seeing config duplicated in the node body.

Why this priority: ADR-050 separates topology from computational configuration.

Independent Test: select LoadData, SaveData, CodeBlock, and a generic process
block; assert ConfigPanel renders the editable controls and BlockNode renders
none of those controls.

Acceptance Scenarios:

- Given a LoadData node with `core_type` and `capability_id`, when the node is
  selected, then BottomPanel Config shows the core type and format capability
  controls and the canvas node body does not show either control.
- Given a CodeBlock node, when it is selected, then CodeBlock config remains in
  BottomPanel and the canvas node remains the square topology glyph.
- Given a SaveData warning, when the warning status is clicked, then the
  selected node opens the relevant BottomPanel detail instead of expanding the
  canvas node.

### User Story 3 - Edit Port Topology On Canvas (Priority: P1)

As a workflow author, I can still quickly add or remove variadic ports from the
canvas, because port count is topology rather than computational config.

Why this priority: the owner explicitly requested that `+/-` remain on the
canvas.

Independent Test: render variadic blocks with min/max limits and assert `+/-`
controls appear on rails, mutate port config correctly, and do not reintroduce
node-body config rows.

Acceptance Scenarios:

- Given a variadic input block below its max input count, when the user clicks
  the input rail `+`, then the add-port dialog opens and the confirmed port is
  persisted through existing `input_ports` config.
- Given a removable connected port, when the user clicks `-`, then existing
  disconnect confirmation behavior still protects affected edges.
- Given a block at its min or max port count, when it renders, then disabled
  add/remove behavior matches ADR-029.

### User Story 4 - Focus A Subgraph Without Changing The Workflow (Priority: P2)

As a workflow author, I can focus the selected node or selected subgraph so
unrelated graph regions stop competing for attention.

Why this priority: subworkflows already exist but do not solve temporary graph
inspection.

Independent Test: run pure focus-set tests against graph fixtures and assert
selection, one-hop neighbors, edge inclusion, exit behavior, and no workflow
mutation.

Acceptance Scenarios:

- Given one selected node, when focus mode is enabled, then that node, its
  directly connected edges, and immediate neighbors are visible or emphasized.
- Given multiple selected nodes, when focus mode is enabled, then the induced
  selected subgraph and immediate boundary neighbors are visible or emphasized.
- Given focus mode is active, when the user exits it, then all nodes and edges
  return to normal visibility and the workflow dirty flag is unchanged.

### User Story 5 - Tidy A Messy Graph Deterministically (Priority: P2)

As a workflow author, I can click a tidy action to arrange the graph by data
flow without manually dragging every node.

Why this priority: large workflows need an explicit mechanical cleanup tool.

Independent Test: run auto-layout tests on representative DAGs and assert
deterministic left-to-right positions, layout-only mutations, and stable output
across repeated runs.

Acceptance Scenarios:

- Given a workflow without useful layout, when the user clicks Tidy, then nodes
  receive deterministic `layout` positions ordered by data flow.
- Given a workflow with config and edges, when Tidy runs, then only node layout
  metadata changes.
- Given focus mode is active, when Tidy is invoked for the focus scope, then
  only focused nodes move unless the user chooses whole-workflow tidy.

### Edge Cases

- A node has more ports than fit beside the square body: rail layout may extend
  beyond the square, but the square body remains fixed-size.
- A block has no schema yet: render the square node with known label/status and
  available summary ports, without inline config fallback.
- A block has zero ports: render the square body without empty rails; selection
  and status still work.
- A plugin data type is unknown to the static type-color map: keep the existing
  deterministic hash color behavior.
- A cyclic or invalid workflow graph reaches tidy: auto-layout must not change
  validation semantics; layout may still position connected components.
- Focus mode with no selected node: the action is disabled or prompts the user
  to select a node; it must not enter an ambiguous state.
- BottomPanel is collapsed when a node is selected: selection expands Config as
  current behavior already does.

## 3. Requirements

### Functional Requirements

- FR-001: BlockNode MUST render block nodes as fixed square node bodies with
  equal width and height.
- FR-002: The default node body size MUST be `104 x 104` CSS pixels unless the
  implementation centralizes density constants that still obey ADR-050.
- FR-003: BlockNode MUST NOT render computational config controls in the node
  body.
- FR-004: BlockNode MUST NOT render a status footer, inline error text row, or
  warning chip inside the node body.
- FR-005: BlockNode MUST render a block label capped to two visual lines with
  overflow handled without geometry changes.
- FR-006: BlockNode MUST render the existing block-kind category as a compact
  mark or icon, sourced from `data.category`.
- FR-007: BlockNode MUST keep data type semantics on ports, edges, hover text,
  and TypeLegend, not inside the node body.
- FR-008: PortHandles MUST keep input ports on the left rail and output ports
  on the right rail.
- FR-009: Variadic `+/-` controls MUST remain available on canvas rails and
  obey ADR-029 min/max constraints.
- FR-010: Full variadic port editing, including naming and type selection, MUST
  remain in BottomPanel Config / PortEditorTable.
- FR-011: Runtime state, errors, warnings, and problem severity MUST be
  represented through one fixed-geometry node status surface.
- FR-012: Error status activation MUST select the node, open BottomPanel Logs,
  and expose the full error detail through existing log rows.
- FR-013: Warning status activation MUST select the node and open BottomPanel
  Config or an equivalent in-scope detail area; the first implementation MUST
  NOT add a new Problems tab.
- FR-014: Lossy-save warning details MUST be available outside the node body,
  preferably in the selected node's ConfigPanel.
- FR-015: Existing inline config components MUST be deleted or removed from the
  active import graph; they must not remain as a legacy path.
- FR-016: Existing tests that assert inline node config MUST be deleted or
  rewritten to assert BottomPanel config behavior.
- FR-017: WorkflowCanvas MUST expose a focus mode control and visible exit
  affordance when focus mode is active.
- FR-018: Focus mode MUST be frontend view state and MUST NOT mutate workflow
  nodes, edges, config, layout, or runtime state.
- FR-019: Focus mode MUST compute a deterministic focus set from selection and
  graph adjacency.
- FR-020: WorkflowCanvas MUST expose a tidy layout action.
- FR-021: Tidy layout MUST use a deterministic graph layout adapter and SHOULD
  use `elkjs` layered layout unless implementation research finds a blocker.
- FR-022: Tidy layout MUST write only existing `node.layout` metadata.
- FR-023: Tidy layout MUST be explicit user action; it MUST NOT run
  automatically on every graph edit.
- FR-024: The workflow store MUST provide a batch layout update action or an
  equivalent non-jitter implementation so tidy can update many nodes together.
- FR-025: Architecture docs MUST be updated in the implementation PR so
  `ARCHITECTURE.md` no longer describes inline-config card nodes.
- FR-026: The implementation MUST NOT provide a feature flag, preference,
  fallback component, or code path that restores the old long-card node UI.
- FR-027: The implementation MUST preserve the package-to-registry-to-API
  contract that carries block metadata into the frontend:
  `Block` class metadata, `BlockSpec`, `BlockSummary`, and
  `BlockSchemaResponse`.
- FR-028: Package-provided `base_category` / `subcategory` metadata MUST
  remain the source for block-kind marks, palette grouping, and API summaries;
  the square node design MUST NOT require new package UI metadata.
- FR-029: Package and API `config_schema` metadata, including `ui_priority`
  and `ui_widget`, MUST remain active for BottomPanel Config field ordering
  and widget selection. Removing node-body config MUST NOT remove those
  schema fields or reinterpret them as legacy node UI.
- FR-030: Package-provided ports, `dynamic_ports`, variadic flags, min/max
  port limits, allowed variadic types, and `format_capabilities` MUST remain
  active contracts for canvas ports, `+/-` topology controls, effective port
  computation, and BottomPanel capability selection.
- FR-031: The implementation MUST NOT require edits to package block classes,
  package entry points, package assets, or package runtime behavior for the
  square node UI.
- FR-032: The implementation MUST NOT add package-specific old-node,
  legacy-renderer, compact-card, or square-node hint fields.
- FR-033: The square node model MUST be package-agnostic: it MUST render any
  block purely from its `BlockSpec` / `BlockSchemaResponse` metadata
  (block-kind, ports, dynamic ports, variadic flags, config schema,
  capabilities) with no package-specific code path (see FR-032). Because
  package-provided blocks carry the same metadata shape as core blocks, the
  frontend node/config tests that exercise that metadata cover package blocks by
  construction; this frontend ADR adds no backend or package contract tests.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `SquareBlockNode` | The replacement canvas rendering model for block nodes | fixed size, label, block-kind mark, ports, status surface, hover actions | Replaces current BlockNode card rendering |
| `NodeStatusSurface` | Single visual surface for runtime state and problem severity | runtime state, warning flag, error flag, click target | Opens Logs for errors and Config detail for warnings |
| `FocusModeState` | Frontend-only view state for focused graph rendering | enabled, selected ids, visible ids, hidden/dimmed ids, depth | Derived from workflow nodes and edges; not persisted |
| `TidyLayoutAction` | Explicit layout computation command | scope, algorithm, spacing constants, generated positions | Writes `WorkflowNode.layout` only |
| `LayoutBatchUpdate` | Store-level mutation for applying many node positions | node id to position map | Marks workflow dirty and preserves history semantics chosen by implementation |
| `PackageProvidedBlockSchema` | Existing block metadata produced by core and package block classes through registry/API | base category, subcategory, ports, dynamic ports, variadic flags, config schema, format capabilities | Consumed by canvas node rendering, BottomPanel Config, port editor, TypeLegend, and capability selectors |

### No Compatibility Or Legacy Mode

The implementation MUST be a clean replacement.

Required removals:

- Remove inline config rendering from BlockNode.
- Remove active imports and usage of `InlineConfigField`,
  `InlineTextInputField`, `InlineCapabilitySelector`, and
  `inlineConfigHelpers`.
- Remove or replace `StatusBadge` and `ErrorMessage` so the active node path
  uses `NodeStatusSurface`.
- Remove node-body use of `LossySaveWarning`; warning detail must move to
  BottomPanel or a non-geometry-changing detail surface.
- Remove tests whose only purpose is preserving inline node config behavior,
  or rewrite them to assert the new BottomPanel-owned config contract.

Prohibited compatibility mechanisms:

- No `legacyBlockNode`, `CardBlockNode`, `compact=false`, or old/new node mode
  switch.
- No user preference or localStorage flag to restore inline config nodes.
- No temporary feature flag that ships the old card in production.
- No duplicate config editing on canvas and BottomPanel.
- No status footer kept for "old workflows".

Workflow file compatibility is different: existing workflow YAML remains valid
because this implementation does not change node, edge, config, or layout
schema. There is no workflow migration and no legacy workflow renderer.

Package/API schema compatibility is also different from legacy node UI. The
fields that packages and the backend currently expose through `BlockSpec`,
`BlockSummary`, and `BlockSchemaResponse` remain active contracts. Do not
delete `base_category`, `subcategory`, port declarations, `dynamic_ports`,
variadic flags, min/max port limits, allowed variadic type lists,
`format_capabilities`, or `config_schema` metadata such as `ui_priority` and
`ui_widget` as part of removing inline node config. Those fields still drive
BottomPanel Config, file/directory pickers, capability selection, effective
ports, port rails, and palette grouping. If implementation discovers a truly
obsolete frontend-only field used only by the old node card, delete that
frontend path; do not delete package-facing block schema contracts without a
new ADR/spec amendment.

## 4. Implementation Plan

### 4.1 Technical Approach

Implement the change in six layers.

1. **Node geometry and status layer**
   Replace BlockNode's card layout with a square shell. Move actions into a
   floating toolbar and status into a `NodeStatusSurface`. Keep port handles
   attached to left/right rails.

2. **Config ownership layer**
   Delete node-body config rendering. Ensure BottomPanel Config exposes every
   config field, capability selector, CodeBlock editor, port editor, and
   warning detail needed after node simplification.

3. **Package/API contract layer**
   Treat package-provided block metadata as an existing contract surface.
   Verify that the registry and block API continue to expose the metadata the
   frontend needs, but do not add package-specific UI hints or edit package
   runtime logic for the square node model.

4. **Focus mode layer**
   Add a pure `focusMode.ts` helper that computes visible/emphasized nodes and
   edges from selected ids and workflow edges. Wire view state in
   WorkflowCanvas or UI slice without persisting it to workflow YAML.

5. **Tidy layout layer**
   Add an `autoLayout.ts` adapter around a deterministic graph layout engine.
   The adapter accepts workflow nodes, edges, node dimensions, and scope; it
   returns `{nodeId: {x, y}}`. WorkflowCanvas applies the result through a
   batch layout update.

6. **Documentation and test layer**
   Search current documentation for old inline-card node descriptions, update
   affected current docs, and replace old node tests with geometry, status,
   focus, tidy, package-backed contract, and BottomPanel ownership tests.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `docs/**` | verify/modify affected current docs | Governance/documentation impact surface; search all docs for old node-card, inline-config, status-footer, and canvas-control descriptions. Generated references remain excluded. |
| `docs/adr/ADR-050.md` | modify if needed | Governing ADR for design decisions and constraints. |
| `docs/specs/adr-050-canvas-node-readability.md` | create | This implementation specification. |
| `docs/architecture/ARCHITECTURE.md` | modify | Replace §9.5 old card/inline-config/status-footer description. |
| `src/scistudio/blocks/base/block.py` | verify only | Package block class metadata is an active producer contract; no ADR-050 code change expected. |
| `src/scistudio/blocks/registry/__init__.py` | verify only | `BlockSpec` carries metadata consumed by API and frontend nodes. |
| `src/scistudio/blocks/registry/_spec.py` | verify only | Registry scan maps block class metadata into `BlockSpec`; no square-node-specific fields should be added. |
| `src/scistudio/blocks/registry/_scan.py` | verify only | Package entry point and monorepo scan behavior feed available package blocks. |
| `src/scistudio/api/schemas.py` | verify/modify only if contract tests expose a gap | `BlockSummary` and `BlockSchemaResponse` carry the metadata consumed by BlockNode, BottomPanel, and port editors. |
| `src/scistudio/api/routes/blocks.py` | verify/modify only if contract tests expose a gap | `/api/blocks` and `/api/blocks/{type}/schema` are the package-to-frontend schema bridge. |
| `packages/scistudio-blocks-*/pyproject.toml` | verify only | Existing `scistudio.blocks` and `scistudio.types` entry points define package discovery; no edit expected. |
| `packages/scistudio-blocks-*/src/scistudio_blocks_*/__init__.py` | verify only | `get_block_package()` metadata feeds registry scan; no edit expected. |
| `packages/scistudio-blocks-*/src/scistudio_blocks_*/<block-source-dirs>/**/*.py` | verify only | Representative block metadata, ports, config schemas, and capabilities must render through new node UI without package code changes. |
| `frontend/package.json` | modify | Add graph layout dependency, expected `elkjs`, if implementation confirms choice. |
| `frontend/package-lock.json` | modify | Lock dependency changes. |
| `frontend/src/types/api.ts` | verify/modify only if API contract tests expose a gap | Frontend `BlockSummary` and `BlockSchemaResponse` mirror backend block schema. |
| `frontend/src/types/ui.ts` | modify | Add status-surface fields if BlockNodeData needs explicit warning/problem metadata; keep BottomTab unchanged unless owner approves Problems tab. |
| `frontend/src/store/types.ts` | modify | Add focus mode state and batch layout action signatures if implemented in store. |
| `frontend/src/store/uiSlice.ts` | modify | Store focus mode UI state if not kept local to WorkflowCanvas. |
| `frontend/src/store/workflowSlice.ts` | modify | Wire batch layout update action if added. |
| `frontend/src/store/workflowSlice.parts/workflowEditActions.ts` | modify | Implement batch layout updates for tidy. |
| `frontend/src/App.tsx` | modify | Wire new toolbar/canvas props and bottom-panel handlers. |
| `frontend/src/App.parts/ProjectWorkspace.tsx` | modify | Pass focus/tidy callbacks and layout update callbacks to canvas and toolbar. |
| `frontend/src/App.parts/useBottomPanelControls.ts` | modify | Add warning-status click handler opening Config detail if needed. |
| `frontend/src/api/capabilities.ts` | verify/modify only if contract tests expose a gap | Capability lookup remains backed by API/package `format_capabilities`. |
| `frontend/src/utils/computeEffectivePorts.ts` | verify/modify only if contract tests expose a gap | Dynamic accepted types remain driven by `BlockSchemaResponse.dynamic_ports`. |
| `frontend/src/components/Toolbar.tsx` | modify | Pass Tidy and Focus controls into workflow toolbar or delegate to canvas controls. |
| `frontend/src/components/Toolbar.parts/WorkflowGroups.tsx` | modify | Add Focus and Tidy buttons if toolbar placement is chosen. |
| `frontend/src/components/WorkflowCanvas.tsx` | modify | Apply focus filtering/dimming, expose tidy control, call auto-layout adapter. |
| `frontend/src/components/WorkflowCanvas.parts/CanvasReadabilityControls.tsx` | create | Optional focused controls component for Focus/Tidy if not placed in main toolbar. |
| `frontend/src/components/WorkflowCanvas.parts/focusMode.ts` | create | Pure focus-set computation. |
| `frontend/src/components/WorkflowCanvas.parts/autoLayout.ts` | create | Pure layout adapter around graph layout library. |
| `frontend/src/components/WorkflowCanvas.parts/layoutConstants.ts` | create | Shared square-node dimensions and layout spacing constants. |
| `frontend/src/components/WorkflowCanvas.parts/flowNodeBuilder.ts` | modify | Change initial node dimensions from card values to square geometry. |
| `frontend/src/components/WorkflowCanvas.parts/useFlowNodes.ts` | modify | Pass warning/status metadata and selected/focus state needed by BlockNode. |
| `frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.ts` | modify | Keep drag behavior compatible with focus/tidy state and batch layout writes. |
| `frontend/src/components/WorkflowCanvas.parts/WorkflowMiniMap.tsx` | modify | Ensure minimap remains useful with square nodes and focus mode. |
| `frontend/src/components/nodes/BlockNode.tsx` | rewrite | Replace card UI with square topology glyph. |
| `frontend/src/components/nodes/BlockNode.parts/NodeStatusSurface.tsx` | create | Unified runtime/problem status surface. |
| `frontend/src/components/nodes/BlockNode.parts/NodeActionToolbar.tsx` | create | Floating run/restart/delete/action controls. |
| `frontend/src/components/nodes/BlockNode.parts/nodeGeometry.ts` | create | Shared constants/helpers for node body and port rail positions. |
| `frontend/src/components/nodes/BlockNode.parts/PortHandles.tsx` | modify | Align rails to square geometry while preserving add/remove behavior. |
| `frontend/src/components/nodes/BlockNode.parts/AddPortDialog.tsx` | modify as needed | Ensure dialog still opens from rail controls with square nodes. |
| `frontend/src/components/nodes/BlockNode.parts/PausedToast.tsx` | delete or move | Paused detail cannot render in node body. |
| `frontend/src/components/nodes/BlockNode.parts/StatusBadge.tsx` | delete or replace | Superseded by `NodeStatusSurface`. |
| `frontend/src/components/nodes/BlockNode.parts/ErrorMessage.tsx` | delete | Inline error text is prohibited by ADR-050. |
| `frontend/src/components/nodes/BlockNode.parts/InlineConfigField.tsx` | delete | Old inline node config path. |
| `frontend/src/components/nodes/BlockNode.parts/InlineTextInputField.tsx` | delete | Old inline node config path. |
| `frontend/src/components/nodes/BlockNode.parts/InlineCapabilitySelector.tsx` | delete | Capability config belongs in BottomPanel. |
| `frontend/src/components/nodes/BlockNode.parts/inlineConfigHelpers.ts` | delete | Old inline config priority helper. |
| `frontend/src/components/nodes/BlockNode.parts/badgeStyles.ts` | modify or delete | Category icon/status style tables should be split or replaced. |
| `frontend/src/components/WorkflowEditor/LossySaveWarning.tsx` | modify | Keep warning computation but move node-body chip use into BottomPanel detail. |
| `frontend/src/components/BottomPanel.tsx` | modify | Pass selected-node warning/problem detail to ConfigPanel if needed. |
| `frontend/src/components/BottomPanel.parts/ConfigPanel.tsx` | modify | Render lossy-save and validation/problem detail for selected node. |
| `frontend/src/components/BottomPanel.parts/FormatCapabilityConfig.tsx` | verify/modify | Ensure capability config remains complete after inline selector deletion. |
| `frontend/src/components/BottomPanel.parts/TabBar.tsx` | verify/modify | Do not add Problems tab in first implementation; logs/config remain destinations. |
| `frontend/src/components/PortEditor/CapabilityDropdown.tsx` | verify/modify | Capability dropdown remains the BottomPanel/PortEditor path for package/API capabilities. |
| `frontend/src/components/PortEditorTable.tsx` | verify/modify | Ensure full variadic port edit behavior remains after canvas rails simplify. |
| `frontend/src/components/TypeLegend.tsx` | verify/modify | Continue serving type semantics; no type subtitle in node body. |
| `frontend/src/config/typeColorMap.ts` | verify/modify | Existing port color behavior must remain stable. |
| `frontend/src/utils/__tests__/computeEffectivePorts.test.ts` | verify/modify | Frontend dynamic-port computation coverage. |
| `frontend/src/__tests__/CapabilityDropdown.test.tsx` | verify/modify | Capability selector coverage after inline selector deletion. |
| `frontend/src/components/nodes/__tests__/BlockNode/**` | modify/delete/create | Replace inline config expectations with square geometry/status/ports tests. |
| `frontend/src/components/WorkflowCanvas.parts/__tests__/**` | create | Focus and tidy pure-function coverage. |
| `frontend/src/components/BottomPanel.parts/ConfigPanel.test.tsx` | modify | Prove BottomPanel owns config and warning detail. |
| `frontend/src/store/__tests__/workflowSlice.layoutBatch.test.ts` | create | Prove batch layout writes only layout metadata. |

### 4.3 Implementation Sequence

1. Add layout constants and BlockNode square shell.
2. Replace header/footer/action layout with square body, floating action
   toolbar, and port rails.
3. Add `NodeStatusSurface`; route error click to Logs and warning click to
   Config detail.
4. Move lossy-save warning detail into BottomPanel Config.
5. Confirm package/registry/API contract payloads still expose block-kind,
   port, dynamic-port, variadic, config-schema, and capability metadata.
6. Delete inline config components and rewrite affected tests.
7. Add focus-mode pure helper and unit tests.
8. Wire focus mode into WorkflowCanvas rendering and controls.
9. Add auto-layout adapter and unit tests.
10. Add workflow store batch layout update and tests.
11. Wire Tidy action into canvas/toolbar and persist positions through
    existing layout save path.
12. Update architecture documentation.
13. Run frontend tests, frontend typecheck/build, full audit, and gate check.

### 4.4 Verification Plan

Required local checks for implementation PR:

- `npm --prefix frontend test -- BlockNode`
- `npm --prefix frontend test -- WorkflowCanvas`
- `npm --prefix frontend test -- ConfigPanel`
- `npm --prefix frontend test -- workflowSlice`
- `npm --prefix frontend test -- computeEffectivePorts`
- `npm --prefix frontend test -- CapabilityDropdown`
- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run build`
- `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output .workflow/local/full-audit.json`
- `PYTHONPATH=src python -m scistudio.qa.governance.gate_record check --base origin/main --head HEAD`

Manual verification before merge:

- Open a workflow with several block categories and verify all nodes are square.
- Select LoadData, SaveData, CodeBlock, and process blocks; verify config is
  available only in BottomPanel.
- Select representative package-provided blocks from imaging, spectroscopy,
  LCMS, and SRS; verify block-kind mark, ports, capability controls, and
  config fields render without package source edits.
- Trigger or mock error/warning/paused/running states; verify node geometry is
  unchanged.
- Add and remove variadic ports from canvas rails and from BottomPanel.
- Enable and exit focus mode.
- Run Tidy on whole graph and focus scope; save and reload to verify layout
  persistence.

### 4.5 Risks And Rollback

Risks:

- Removing inline config can feel slower for simple workflows.
  Mitigation: selecting a node already opens Config; keep that path fast.
- Square nodes may make port-heavy blocks visually dense.
  Mitigation: rails may extend outside the square and full editing remains in
  BottomPanel.
- Layout dependency output may be unstable across versions.
  Mitigation: lock dependency and test representative fixtures.
- Batch layout update may interact badly with undo/redo.
  Mitigation: define one history entry per tidy action and add store tests.
- "No legacy" may be misread as permission to remove active package/API
  metadata. Mitigation: this spec distinguishes old frontend node UI paths
  from active block schema contracts and requires package-backed verification.

Rollback:

- Reverting the implementation PR restores the previous node UI because no
  workflow schema migration is performed.
- Do not keep a runtime toggle for rollback. Rollback is by git revert, not by
  shipping a legacy UI path.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: BlockNode tests prove node body dimensions remain equal and stable
  across idle, running, warning, error, and paused states.
- SC-002: No production import path references `InlineConfigField`,
  `InlineTextInputField`, `InlineCapabilitySelector`, or `inlineConfigHelpers`.
- SC-003: ConfigPanel tests prove core type, capability, file path, CodeBlock,
  and variadic port editing remain accessible after inline config removal.
- SC-004: Variadic port tests prove `+/-` canvas controls still mutate
  `input_ports` / `output_ports` and enforce min/max limits.
- SC-005: Focus-mode tests prove the selected focus set and exit behavior
  without mutating workflow state.
- SC-006: Auto-layout tests prove deterministic output for the same graph input.
- SC-007: Store tests prove tidy changes only `layout` fields and creates the
  intended dirty/history behavior.
- SC-008: Architecture docs no longer describe block nodes as inline-config
  cards with status footers.
- SC-009: `npm --prefix frontend run typecheck` and `npm --prefix frontend run
  build` pass.
- SC-010: The package-to-registry-to-API backend contract (`BlockSpec`,
  `BlockSummary`, `BlockSchemaResponse`) is unchanged by this frontend-only
  work — no backend or package source is edited — so the metadata the frontend
  consumes is preserved by construction and remains covered by the existing
  backend test suite on `main`. This ADR adds no backend contract tests.
- SC-011: The square node model and BottomPanel config render block metadata
  generically (FR-033), so package-provided blocks — whose metadata shares the
  same shape as core blocks — render through the same frontend path with no
  package source edits, covered by the frontend node/config component tests and
  the canvas e2e.
- SC-012: No package-facing API or block schema field is removed solely because
  the old node body no longer renders inline config.
- SC-013: `gate_record check` passes for the implementation PR.

## 6. Assumptions

- The implementation is ADR-050-governed and may remove ADR-023 inline node
  config behavior without a compatibility period. Source: owner.
- Existing workflow YAML must continue to load because node, edge, config, and
  layout schema are unchanged. Source: existing-system.
- `elkjs` is the preferred layout dependency but may be replaced by an
  equivalent deterministic graph-layout library if implementation research
  finds a blocker. Source: ADR-050.
- The first implementation routes warnings to Config and errors to Logs; it
  does not add a Problems tab. Source: inferred from current BottomPanel.
- Focus mode is local UI state, not persisted workflow state. Source: ADR-050.
- Package block metadata and API schema fields remain active contracts for the
  BottomPanel, ports, capability selectors, palette grouping, and TypeLegend;
  ADR-050 removes only old frontend node-body rendering paths. Source:
  existing-system.
