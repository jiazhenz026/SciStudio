---
title: "ADR-054 Assembly Dispatch — S4-A2 The Notebook Shell"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S4-A2 — The Notebook Shell, The Editors, The Outputs, And The Marks

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Build ADR-054 spec 4's notebook shell — SciStudio's own cell
  list on Monaco, with the `.ipynb` MIME bundle rendered natively, the
  runtime's marks drawn, and every cell command sent to the session API.
- Task kind: feature
- Persona: implementer
- Issue: #2253
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2253
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec4-explore-frontend
- Agent branch: feat/2253-notebook-shell
- Agent worktree: .worktrees/s4-a2
- Gate record: .workflow/records/2253-feat-2253-notebook-shell.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first.

## Required Rules

Everything in the shared preamble, plus:

- `docs/specs/adr-054-explore-frontend.md` — your spec. You implement
  **T-004 to T-007** of its §4.3, covering FR-008 to FR-014, FR-016 and FR-017.
- Agent S4-A1 landed the slice, the API types, and the `ExploreTab.tsx` region
  contract on `feat/2253-explore-tab-shell`, merged into your base. Read it
  before writing: your components are written against its exported types, and
  you replace its notebook-pane placeholder rather than restructuring its
  layout.

## Scope

You own only:

- `frontend/src/explore/NotebookShell.tsx` — new.
- `frontend/src/explore/CellEditor.tsx` — new.
- `frontend/src/explore/OutputRenderer.tsx` — new.
- `frontend/src/explore/CellMarks.tsx` — new.
- `frontend/src/explore/SessionToolbar.tsx` — the run-stale, interrupt,
  restart and commit controls only. **S4-A1 owns the frame and the notebook
  toggle; S4-A3 owns confirm and cancel; S4-A4 owns the kernel list and
  package.** Add your controls; do not restructure the file.
- Tests for each of the above.

You must not touch:

- `frontend/src/explore/ExploreTab.tsx`, `exploreSlice.ts`, `types/api.ts`,
  `ProjectWorkspace.tsx`, the context menus — S4-A1.
- `frontend/src/explore/VariableStrip.tsx`, `PanelSlots.tsx`,
  `frontend/src/App.parts/InteractiveModals*` — S4-A3.
- `frontend/src/explore/PackagingReport.tsx`, `GraphView.tsx`,
  `frontend/src/components/nodes/BlockNode.tsx`, `BlockPalette*` — S4-A4.
- Every `src/scistudio/**` path.

If you need an out-of-scope path, stop and report back. Do not edit it.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S4-A2`.

## Work To Do

1. **T-004 — the shell, virtualised.**
   Render the notebook's cells in order. **A Monaco editor for each *visible*
   code cell and static highlighted text for cells outside the viewport**
   (FR-008). This is not an optimisation to add later: a hundred editor
   instances would make a long notebook unusable, and §4.5 names editor cost
   as the first risk. Unsaved edits must survive an editor being swapped out —
   a draft lives in the shell's state, not in the Monaco model.
   Code and markdown cells both (FR-009); markdown renders with the markdown
   renderer **already in the bundle** and edits in place. Introduce no
   notebook library: JupyterLab's components carry a widget system foreign to
   this application and a kernel client that would bypass the session service.
2. **T-005 — the output renderer.**
   Render outputs from the notebook's MIME bundle (FR-011): plain text, stream
   output, errors with their traceback **rendered with ANSI colour**, images,
   and HTML **in a sandboxed frame**. An unknown MIME type falls back to plain
   text where the bundle carries it and otherwise to a note. Rendering from
   the `.ipynb` bundle is what makes the notebook look the same here and in
   Jupyter — do not invent a SciStudio output shape.
3. **T-006 — the marks.**
   Draw the three marks the runtime reports — never-run, stale, out-of-order —
   on the cell (FR-012). An out-of-order mark shows the names and cells that
   caused it. Offer run-stale on the toolbar **with the stale count**, and
   run-with-upstream on an out-of-order cell (FR-013).
   **FR-034 is absolute here**: never compute a mark. The runtime computes
   stale and out-of-order and sends them on cell-state events; you draw them.
   A mark computed in two places would disagree in exactly the cases that
   matter. Send nothing the person did not ask for.
4. **T-007 — the commands and the reconciliation.**
   Add, delete and move for cells, a per-cell run control, and a per-cell
   enable toggle, each sent to the session API, reflecting the resulting
   cell-state events (FR-010). Interrupt, restart and commit-to-branch on the
   toolbar (FR-014's share). Show the kernel's state — none, starting, idle,
   busy, dead, needs restart — and offer restart when the runtime reports the
   kernel dead or retired (FR-016).
   Cell edits go to the session API **on a debounce and on run**, and a reload
   event is reconciled with unsaved edits **by cell id, keeping the draft and
   marking it as conflicting** (FR-017). Do not silently drop a person's
   typing.

## Required Tests And Checks

- `NotebookShell.test.tsx` — against notebooks of several sizes, proving that
  **only visible cells carry editors** and that drafts survive a swap. This
  assertion is the whole reason virtualisation is in the first task.
- `OutputRenderer.test.tsx` — a fixture of every supported MIME type, plus an
  unknown type falling back. Assert the HTML frame is sandboxed and the ANSI
  traceback is coloured rather than escaped into noise.
- `CellMarks.test.tsx` — driven by cell-state events; assert the out-of-order
  reason names its causes; assert no mark is derived locally.
- Toolbar tests — each control sends exactly its command and nothing else.
- A reconciliation test — a reload event against an unsaved draft keeps the
  draft and marks it conflicting.
- `npm run test`, `npm run lint`, `npm run build` in `frontend/`.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec4-explore-frontend --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, `python scripts/scistudio_pr_create.py`, post-PR
  `finalize`. Base your PR on `track/adr-054-spec4-explore-frontend`.
- Docs: `--docs-na "user-docs:the human documentation revision is ADR-054
  spec 6, issue #2236"`.

## Output Required

Per the shared preamble.

## Stop Conditions

Per the shared preamble.
```
