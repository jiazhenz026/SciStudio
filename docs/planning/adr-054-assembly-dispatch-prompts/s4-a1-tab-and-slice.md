---
title: "ADR-054 Assembly Dispatch — S4-A1 Explore Tab, Slice, And Layout"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S4-A1 — The Explore Tab, The Store Slice, And The Layout

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 4's foundation — the Explore tab as a
  member of the centre-area tab union, the store slice written from session
  events, the API types, the event routing, the layout swap, and the two
  context menus that open a session.
- Task kind: feature
- Persona: implementer
- Issue: #2253
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2253
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec4-explore-frontend
- Agent branch: feat/2253-explore-tab-shell
- Agent worktree: .worktrees/s4-a1
- Gate record: .workflow/records/2253-feat-2253-explore-tab-shell.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first; it carries the rules, the coordination, the gate workflow,
  the follow-up register rule, and the description of the base you build on.

## Required Rules

Everything in the shared preamble, plus:

- `docs/specs/adr-054-explore-frontend.md` — your spec. You implement
  **T-001, T-002 and T-003** of its §4.3, covering FR-001 to FR-007 and
  FR-033 to FR-035.
- `docs/specs/adr-054-explore-session.md` §3 — the API and the event set your
  slice is written from. Read the **landed** implementation at
  `src/scistudio/api/routes/explore.py` and `src/scistudio/api/ws.py`, which
  is the fact; where it disagrees with the spec, report the disagreement.
- ADR-050 for the canvas node rendering you add a context menu to.

## Scope

You own only:

- `frontend/src/store/types.ts` — the Explore tab union member.
- `frontend/src/store/exploreSlice.ts` — new.
- `frontend/src/types/api.ts` — session request/response and event payloads.
- `frontend/src/types/ui.ts` — pause-mode and shell-state enumerations.
- `frontend/src/App.parts/ProjectWorkspace.tsx` — the centre branch and the
  right-column condition.
- `frontend/src/explore/ExploreTab.tsx` — new; the layout skeleton only:
  toolbar region, strip region, panel-slot region, notebook-pane region, and
  the pause-mode arrangement. Leave each region's contents to its owner and
  land them as clearly-named placeholder components the other agents replace.
- `frontend/src/explore/SessionToolbar.tsx` — new; the toolbar frame and the
  notebook toggle only. The kernel list is S4-A4's, the run/interrupt/restart
  controls are S4-A2's, package is S4-A4's, confirm/cancel are S4-A3's.
- `frontend/src/hooks/useWebSocket.parts/dispatchEvent.ts` — route every
  session event to the slice.
- `frontend/src/components/WorkflowCanvas.tsx` and
  `frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.ts` — the
  node context menu and the packaged-node double-click.
- `frontend/src/components/ProjectTree.tsx` and
  `frontend/src/components/ProjectTree.parts/**` — the file context menu.
- `frontend/src/components/DataPreview.tsx` — not rendered while an Explore
  tab is active.
- Tests for each of the above.

You must not touch:

- `frontend/src/explore/NotebookShell.tsx`, `CellEditor.tsx`,
  `OutputRenderer.tsx`, `CellMarks.tsx` — S4-A2.
- `frontend/src/explore/VariableStrip.tsx`, `PanelSlots.tsx`,
  `frontend/src/App.parts/InteractiveModals*` — S4-A3.
- `frontend/src/explore/PackagingReport.tsx`, `GraphView.tsx`,
  `frontend/src/components/nodes/BlockNode.tsx`,
  `frontend/src/components/BlockPalette*` — S4-A4.
- Every `src/scistudio/**` path.
- `docs/specs/**`, `docs/architecture/**`.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

Everything in the shared preamble. In addition: **three agents build on your
work.** The slice shape, the API types, and the region contract in
`ExploreTab.tsx` are the interface they code against, so:

- Name the slice's state and actions after the spec's Key Entities —
  `ExploreSliceState`, `CellView`, `VariableEntry`, `PanelSlot` — and export
  every type another component would need.
- Give each region in `ExploreTab.tsx` a placeholder component in its own
  file with the props the real component will take, so the others replace a
  file rather than restructure your layout.
- Push early and often. The others branch from your branch, not from the
  track branch.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S4-A1`.

## Work To Do

1. **T-001 — the member, the slice, the types, the routing.**
   Add the Explore member to the centre-area tab union keyed by the session's
   notebook path (FR-001), with the tab persisting across a reload like a file
   tab and re-fetching its session state on restore. Write
   `exploreSlice.ts` holding sessions by path: cells, marks, kernel state,
   bindings, open panels, pinned names, the graph, the last report. Route
   every session event through `dispatchEvent.ts` into it: session opened and
   closed, kernel state, cell state with marks, cell output, changed names,
   analysis updated, commit recorded, packaged (FR-033).
   **FR-034 is the hard rule of this task**: the slice is written from events
   and responses only. Never derive a mark, a kernel state or a binding in the
   frontend, and reflect a command only when its event arrives. FR-035: open
   no connection to a kernel.
   Events may arrive before the response to the command that caused them —
   apply them idempotently by cell id and state so order does not matter.
2. **T-002 — the layout.**
   One branch in the centre switch and one condition on the right column: when
   the active tab is an Explore tab the right column renders the notebook
   shell instead of the data preview (FR-005). The left pane and the bottom
   panel are untouched — that is what keeps the palette, the tree and the
   block cards available while exploring. The right pane stays collapsible as
   the preview is today, and the centre and toolbar stay usable collapsed
   (FR-006). The centre must host more than one panel at once, arranged so two
   can be compared (FR-007) — you build the arrangement, S4-A3 fills the slots.
3. **T-003 — the two context menus and the packaged-node double-click.**
   The canvas has a double-click handler and no context menu; the data tree
   has a double-click that opens a preview. Both gain a context menu carrying
   the explore action alone (FR-002, FR-003), with the block node's action
   **disabled with a reason** when the runtime reports no outputs. Extend the
   existing double-click handler to recognise a packaged block's node beside
   the subworkflow node it already recognises, opening its notebook bound to
   the node's most recent run (FR-004).

## Required Tests And Checks

- `frontend/src/store/exploreSlice.test.ts` — every session event type reaches
  the slice and updates it; events applied idempotently and out of order reach
  the same state; no mark or binding is ever computed locally.
- A dispatch test proving every session event routes to the slice.
- `frontend/src/explore/ExploreTab.test.tsx` — the layout renders the four
  regions; the right pane collapses; the centre stays usable collapsed.
- `ProjectWorkspace` test — the preview is replaced while an Explore tab is
  active and restored when it is not; the left pane and bottom panel do not
  change.
- Canvas and tree tests — the menu appears, the action opens a tab, the action
  is disabled with a reason when there are no outputs, a packaged node's
  double-click opens its notebook.
- `npm run test`, `npm run lint`, `npm run build` in `frontend/`. The build
  must succeed.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec4-explore-frontend --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, then `python scripts/scistudio_pr_create.py`, then
  post-PR `finalize`. Base your PR on `track/adr-054-spec4-explore-frontend`.
- Docs: `--docs-na "user-docs:the human documentation revision is ADR-054
  spec 6, issue #2236"`.
- Sentrux: recorded automatically as a guard event inside `check`.

## Output Required

Per the shared preamble. Additionally: state the exported slice type names and
the region-component props, because three agents code against them.

## Stop Conditions

Per the shared preamble.
```
