---
title: "ADR-054 Assembly Dispatch — S4-A4 Packaging, Kernels, Graph, Palette"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 50
  - 54
language_source: en
---

# S4-A4 — Packaging, The Kernel List, The Graph View, And The Palette

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Build ADR-054 spec 4's remaining surfaces — packaging as a
  toolbar button with its report, the packaged node's badge, the kernel list,
  the dependency-graph secondary view, and the palette's insert-call action.
- Task kind: feature
- Persona: implementer
- Issue: #2253
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2253
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec4-explore-frontend
- Agent branch: feat/2253-packaging-and-graph
- Agent worktree: .worktrees/s4-a4
- Gate record: .workflow/records/2253-feat-2253-packaging-and-graph.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first.

## Required Rules

Everything in the shared preamble, plus:

- `docs/specs/adr-054-explore-frontend.md` — your spec. You implement
  **T-012 to T-015** of its §4.3, covering FR-014's kernel share, FR-015,
  FR-028 to FR-032.
- `docs/specs/adr-054-explore-session.md` — the packaging check and its
  report, and the kernel-state events, as **landed** in
  `src/scistudio/explore/packaging.py` and `session.py`.
- ADR-050 for the canvas node rendering your badge joins.
- Agent S4-A1's slice and region contract, merged into your base.

## Scope

You own only:

- `frontend/src/explore/PackagingReport.tsx` — new.
- `frontend/src/explore/GraphView.tsx` — new.
- `frontend/src/explore/SessionToolbar.tsx` — the package control and the
  collapsible kernel list only. **S4-A1 owns the frame and the notebook
  toggle; S4-A2 owns run-stale, interrupt, restart, commit; S4-A3 owns confirm
  and cancel.** Add your controls; do not restructure the file.
- `frontend/src/components/nodes/BlockNode.tsx` — the notebook badge.
- `frontend/src/components/BlockPalette.tsx` and
  `frontend/src/components/BlockPalette.parts/**` — the insert-call action and
  the refresh on the packaged event.
- Tests for each of the above.

You must not touch:

- `frontend/src/explore/NotebookShell.tsx`, `CellEditor.tsx`,
  `OutputRenderer.tsx`, `CellMarks.tsx` — S4-A2.
- `frontend/src/explore/VariableStrip.tsx`, `PanelSlots.tsx`,
  `InteractiveModals*` — S4-A3.
- `frontend/src/store/exploreSlice.ts`, `types/api.ts`,
  `ProjectWorkspace.tsx`, `ExploreTab.tsx`, the context menus — S4-A1.
- Every `src/scistudio/**` path.

If you need an out-of-scope path, stop and report back. Do not edit it.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S4-A4`.

## Work To Do

1. **T-012 — packaging, the packaged event, the badge.**
   The package control **first requests the packaging check** and renders its
   report: the slice cells and inferred ports for a clean notebook, or the
   offending cells and reads with the confirm control **disabled** (FR-028).
   Confirm is enabled only when there are no refusals.
   On a packaged event the block palette refreshes and the new block appears
   (FR-029). A packaged block's node carries a notebook badge (FR-030) — that
   badge and its double-click are what let the person come back to the
   notebook.
2. **T-013 — the kernel list.**
   The toolbar carries a collapsible kernel list (FR-014's share). It shows
   **every live kernel in the project** with its session and memory and an end
   control, from the kernel-state events (FR-015). The end control sends the
   command; the list reflects the resulting event, never an optimistic guess.
   When the runtime reports a kernel retired, offer restart.
3. **T-014 — the graph view.**
   A secondary view on the tab, rendered with **the graph library already in
   the bundle** — the one the canvas uses; introduce none (FR-032). One node
   per variable version, edges from the analysis event with their origin,
   cells marked stale or out of order highlighted, and a connected region
   selectable.
   Selection has **no consumer** in this spec beyond highlighting. ADR-054
   §4.5's subgraph operation is a later spec's; do not build toward it, and do
   not leave an untracked hook for it.
4. **T-015 — the palette's insert-call action.**
   While an Explore tab is active, a block's card in the palette offers
   inserting a call to that block into the notebook **after the current cell**
   (FR-031). While no Explore tab is active the card behaves exactly as today.

## Required Tests And Checks

- `PackagingReport.test.tsx` — a clean report enables confirm and lists the
  slice cells and inferred ports; a report with refusals disables confirm and
  names the offending cells and reads.
- A packaged-event test — the palette refreshes and the block appears.
- `BlockNode` test — the badge renders on a packaged block and not on others.
- Kernel-list tests — every kernel listed with its session and memory; end
  sends the command and the list moves only on the event; a retired kernel
  offers restart.
- `GraphView.test.tsx` — version nodes and edges render with their origins;
  cells marked stale or out of order are highlighted; a connected region is
  selectable.
- Palette test — a call cell is inserted after the current cell while an
  Explore tab is active, and the card is unchanged when none is.
- `npm run test`, `npm run lint`, `npm run build` in `frontend/`.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec4-explore-frontend --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, `python scripts/scistudio_pr_create.py`, post-PR
  `finalize`. Base your PR on `track/adr-054-spec4-explore-frontend`.
- Docs: `--docs-na "user-docs:the human documentation revision is ADR-054
  spec 6, issue #2236"`.

## Output Required

Per the shared preamble. Additionally: name the graph library you used and
where it was already in the bundle.

## Stop Conditions

Per the shared preamble.
```
