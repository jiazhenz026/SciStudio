---
title: "ADR-050 Canvas Node Readability Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: [50]
language_source: en
---

# ADR-050 Canvas Node Readability Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Deliver the full ADR-050 frontend refactor (square canvas
  nodes, unified status surface, focus mode, tidy layout); integrate into one
  umbrella PR; run a real browser e2e; flip `[DO NOT MERGE]` to
  `[READY TO REVIEW]`. Owner is asleep; manager works autonomously.
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1698` (implementation). ADR/spec decision issue `#1687` is closed.
- Gate record: `.workflow/records/1698-canvas-node-readability.json`
- Branch/worktree plan:
  - Manager umbrella: `feat/1698-canvas-node-readability` @
    `.worktrees/feat-1698-canvas-node-readability`
  - Agents branch FROM the umbrella branch HEAD into dedicated worktrees and
    merge back into the umbrella branch via the manager.
- Protected branch: `main`
- Umbrella branch: `feat/1698-canvas-node-readability`
- Umbrella PR: `#<pending>`
- Umbrella PR title: `[DO NOT MERGE] ADR-050 canvas node readability refactor`
- Final PR target: `main` (final readiness = flip title to
  `[READY TO REVIEW]`; manager does NOT merge — no merge authorization).
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
- Dispatch prompt files (committed):
  - FE-1: `docs/planning/adr-050-canvas-node-readability-dispatch/FE-1-square-node.md`
  - FE-2: `docs/planning/adr-050-canvas-node-readability-dispatch/FE-2-focus-tidy-store.md`
  - FE-3: `docs/planning/adr-050-canvas-node-readability-dispatch/FE-3-bottompanel-config.md`
  - BE: `docs/planning/adr-050-canvas-node-readability-dispatch/BE-contract-tests.md`

## 2. Scope

- In scope (union; observed umbrella diff):
  - `frontend/src/components/nodes/**`
  - `frontend/src/components/WorkflowCanvas.tsx`,
    `frontend/src/components/WorkflowCanvas.parts/**`
  - `frontend/src/components/BottomPanel.tsx`,
    `frontend/src/components/BottomPanel.parts/**`
  - `frontend/src/components/Toolbar.tsx`,
    `frontend/src/components/Toolbar.parts/WorkflowGroups.tsx`
  - `frontend/src/components/{TypeLegend.tsx,PortEditorTable.tsx,
    PortEditor/CapabilityDropdown.tsx,WorkflowEditor/LossySaveWarning.tsx}`
  - `frontend/src/store/**`, `frontend/src/types/ui.ts`,
    `frontend/src/config/typeColorMap.ts`,
    `frontend/src/utils/computeEffectivePorts.ts`,
    `frontend/src/api/capabilities.ts`
  - `frontend/src/App.tsx`, `frontend/src/App.parts/{ProjectWorkspace.tsx,
    useBottomPanelControls.ts}`
  - `frontend/package.json`, `frontend/package-lock.json`
  - `tests/api/test_blocks.py`, `tests/blocks/**`,
    `tests/packaging/test_adr043_package_capabilities.py`
  - `docs/architecture/ARCHITECTURE.md`, `docs/planning/**` (this checklist +
    dispatch prompts)
- Out of scope:
  - Workflow YAML node/edge/config schema (only `node.layout` may be written).
  - Backend scheduler / validation / lineage / runtime execution / data object
    contracts.
  - Package block classes, entry points, assets, runtime behavior; no
    package-specific old-node / square-node hint fields.
  - Replacing ReactFlow or SubWorkflowBlock; persisted focus presets; Problems
    tab; legacy/compat node mode (FR-026).
- Protected paths: `src/scistudio/api/**`, `src/scistudio/blocks/**` are
  verify-only (BE agent). Any required production change there is a STOP +
  manager scope amendment.
- Deferred work: none planned. Any deferral requires `TODO(#NNNN)` citing an
  issue/ADR/spec.

## 3. Conventions

- `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked
- Every completed row MUST include an artifact (commit, test command, path).
- Agents edit only their own rows. Scope changes require gate-record amendment.

## 4. Shared Interface Contract (manager-defined — all agents MUST obey)

This contract keeps the four worktrees independently compilable. Seams across
agents use OPTIONAL props and duplicated literal constants so each branch type-
checks alone; the manager fixes integration seams on merge.

### 4.1 Node geometry (ADR-050 §2.1, FR-001/FR-002)
- Square body is `104 x 104` CSS px; border-radius ≤ `8px`; width === height;
  body never grows for config/ports/status/errors/actions.
- FE-1 owns `nodes/BlockNode.parts/nodeGeometry.ts`: exports `NODE_SIZE = 104`,
  `NODE_BORDER_RADIUS = 8`, and port-rail offset helpers.
- FE-2 owns `WorkflowCanvas.parts/layoutConstants.ts`: declares its OWN
  `NODE_SIZE = 104` (+ layer/sibling/clearance gaps) with a comment
  "MUST equal nodeGeometry.NODE_SIZE (ADR-050 §2.1)" and a unit test asserting
  `104`. Decoupled on purpose — do NOT cross-import between these two files.
- FE-1 `flowNodeBuilder.buildBlockNode` sets `initialWidth = initialHeight =
  NODE_SIZE` (replacing 280×180).

### 4.2 `BlockNodeData` (frontend/src/types/ui.ts — FE-1 owns)
- KEEP existing fields. The node BODY must not render config controls, status
  footers, inline error text, warning chips, or paused toasts.
- ADD (FE-1):
  - `problemSeverity?: "none" | "warning" | "error"` — highest-priority problem
    signal. FE-1 computes it in `flowNodeBuilder` from runtime `status`
    (`error` ⇒ error) and lossy-save check (warning) using
    `lossyOmeFields(upstreamOmeFields, selectedCapability.metadata_fidelity)`
    imported from `frontend/src/api/capabilities.ts` (read-only import; FE-1
    must NOT modify capabilities.ts).
  - `onWarningClick?: () => void` — OPTIONAL. Selects the node and opens
    BottomPanel Config detail. Wired by FE-2 through `useFlowCallbacks` +
    `makeOnWarningClick`; emitted by the `NodeStatusSurface` warning affordance.
  - `onErrorClick?` already exists — error status MUST select node + open Logs
    (FR-012); FE-2 owns the App-level handler, FE-1 emits via NodeStatusSurface.
- New callback opts added to `UseFlowNodesOpts` / `BlockNodeCallbacks` MUST be
  OPTIONAL so FE-2's existing call sites compile before integration.

### 4.3 Focus dimming seam (FR-017/FR-018/FR-019 — FE-2 only)
- Focus mode is implemented ENTIRELY in FE-2 by post-processing the array
  returned by `useFlowNodes` inside `WorkflowCanvas.tsx`: set ReactFlow
  node-level `hidden` and/or `style`/`className` (opacity dim) on out-of-focus
  nodes/edges. It MUST NOT mutate workflow state and MUST NOT require any change
  to `BlockNodeData` or FE-1 files. FE-1 does not implement focus.

### 4.4 Config ownership seam (FR-003/FR-013/FR-014 — FE-3)
- ConfigPanel already renders all config (enum/scalar/file-browser/format
  capability/port editor/codeblock). FE-3 ADDS the selected-node lossy-save
  warning + validation detail to `ConfigPanel` using the `LossySaveWarning`
  component (compute source fields via `collectUpstreamOmeFields` over
  `blockOutputs`+`edges`, both passed down to ConfigPanel by FE-2's wiring).
- Warning-status click target: FE-2 routes `onWarningClick` → select node +
  `setActiveBottomTab("config")`. FE-3 renders the detail there. No new
  Problems tab (FR-013).

### 4.5 Store seam (FR-022/FR-024 — FE-2)
- FE-2 adds `updateNodeLayoutBatch(positions: Record<string, {x:number;y:number}>)`
  to `WorkflowSlice` (one history entry, marks dirty, writes ONLY `node.layout`)
  and focus-mode UI state to `UISlice` if stored centrally.

### 4.6 elkjs (FR-021 — FE-2 only)
- Only FE-2 edits `frontend/package.json` / `package-lock.json` (adds `elkjs`).
  `autoLayout.ts` wraps it behind a deterministic adapter returning
  `{ [nodeId]: {x,y} }`.

## 5. Manager Preflight

- [x] Dedicated manager branch and worktree created.
- [x] Implementation issue `#1698` created (decision issue `#1687` was closed).
- [x] Gate record started (`gate_record init`, manager/Tier 3).
- [~] Scope include/exclude recorded in the gate record (`plan`).
- [x] Umbrella branch created.
- [ ] Umbrella PR opened.
- [ ] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist
      (PR number pending creation).
- [x] No `pip install -e .` environment pollution found.
- [x] Dispatch checklist copied from the template and committed.
- [~] Dispatch prompts created from the work prompt template and linked.
- [ ] Sentrux baseline: Sentrux MCP unavailable this session; recorded via
      `gate_record check` guard event at integration (CLI fallback `sentrux
      scan/check` if available).

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| FE-1 | implementer | N/A | dispatch/FE-1-square-node.md | Square `BlockNode` + `NodeStatusSurface` + floating actions + node-data flow; delete inline-config/footers | `feat/1698-fe1-square-node` | `.worktrees/feat-1698-fe1-square-node` | `frontend/src/components/nodes/**`, `WorkflowCanvas.parts/flowNodeBuilder.ts`, `WorkflowCanvas.parts/useFlowNodes.ts`, `frontend/src/types/ui.ts` | everything else; `api/capabilities.ts` import-only | #1698 | `[ ]` |
| FE-2 | implementer | N/A | dispatch/FE-2-focus-tidy-store.md | Focus mode + tidy (elkjs) + batch layout store + canvas/toolbar/App wiring | `feat/1698-fe2-focus-tidy-store` | `.worktrees/feat-1698-fe2-focus-tidy-store` | `WorkflowCanvas.tsx`, `WorkflowCanvas.parts/{focusMode,autoLayout,layoutConstants,CanvasReadabilityControls,useCanvasHandlers,useFlowCallbacks,WorkflowMiniMap}`, `store/**`, `Toolbar.tsx`, `Toolbar.parts/WorkflowGroups.tsx`, `App.tsx`, `App.parts/ProjectWorkspace.tsx`, `frontend/package.json`, `frontend/package-lock.json` | `nodes/**`, `BottomPanel/**`, `types/ui.ts`, `flowNodeBuilder.ts`, `useFlowNodes.ts` | #1698 | `[ ]` |
| FE-3 | implementer | N/A | dispatch/FE-3-bottompanel-config.md | BottomPanel owns ALL config + lossy/validation detail; verify port editor + capability + type legend | `feat/1698-fe3-bottompanel-config` | `.worktrees/feat-1698-fe3-bottompanel-config` | `BottomPanel.tsx`, `BottomPanel.parts/{ConfigPanel,FormatCapabilityConfig,TabBar}.tsx`, `WorkflowEditor/LossySaveWarning.tsx`, `PortEditorTable.tsx`, `PortEditor/CapabilityDropdown.tsx`, `TypeLegend.tsx`, `config/typeColorMap.ts`, `api/capabilities.ts`, `utils/computeEffectivePorts.ts`, `App.parts/useBottomPanelControls.ts` + their tests | `nodes/**`, `WorkflowCanvas*`, `store/**`, `App.tsx` | #1698 | `[ ]` |
| BE | test_engineer | N/A | dispatch/BE-contract-tests.md | Verify + strengthen package→registry→API block-schema contract tests | `feat/1698-be-contract-tests` | `.worktrees/feat-1698-be-contract-tests` | `tests/api/test_blocks.py`, `tests/blocks/**`, `tests/packaging/test_adr043_package_capabilities.py` | all `src/**` (verify-only), all `frontend/**` | #1698 | `[ ]` |

## 7. Tracks

### 7.1 FE-1 Square Node — Integration
- [ ] Output reviewed · [ ] Scope compliance · [ ] Merged into umbrella

### 7.2 FE-2 Focus/Tidy/Store — Integration
- [ ] Output reviewed · [ ] Scope compliance · [ ] Merged into umbrella

### 7.3 FE-3 BottomPanel Config — Integration
- [ ] Output reviewed · [ ] Scope compliance · [ ] Merged into umbrella

### 7.4 BE Contract Tests — Integration
- [ ] Output reviewed · [ ] Scope compliance · [ ] Merged into umbrella

### 7.5 Manager-owned
- [ ] `docs/architecture/ARCHITECTURE.md` §9.5 updated (no inline-config card /
      status-footer description).
- [ ] Doc search for stale node-card / inline-config descriptions.
- [ ] Integration seam fixes (node-data callbacks, ConfigPanel props wiring).
- [ ] Browser e2e per spec §4.4 manual verification.

## 8. Verification Evidence

| Check | Command | Status | Evidence |
|---|---|---|---|
| Frontend tests | `npm --prefix frontend test` | `[ ]` | |
| Typecheck | `npm --prefix frontend run typecheck` | `[ ]` | |
| Build | `npm --prefix frontend run build` | `[ ]` | |
| Backend contract tests | `PYTHONPATH=src pytest tests/api/test_blocks.py tests/blocks/ tests/packaging/test_adr043_package_capabilities.py` | `[ ]` | |
| Full audit | `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output .workflow/local/full-audit.json` | `[ ]` | |
| Gate check (pre-PR) | `gate_record check --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md` | `[ ]` | |
| Browser e2e | manual (spec §4.4) | `[ ]` | |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-06-18 | manager | — | dispatch baseline | — |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, commit.
- [ ] PR body closes `#1698`.
- [ ] CI passed.
- [ ] Umbrella PR title flipped to `[READY TO REVIEW]`.
