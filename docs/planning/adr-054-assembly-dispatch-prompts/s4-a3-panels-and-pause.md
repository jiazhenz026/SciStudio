---
title: "ADR-054 Assembly Dispatch — S4-A3 The Panels And The Pause Tab"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 51
  - 54
language_source: en
---

# S4-A3 — The Variable Strip, The Panel Slots, And The Retirement Of The Modal

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Build ADR-054 spec 4's panel half — the variable strip, the
  panel slots on the panel-contract host, the emission path, and the pause tab
  that replaces the interactive modal.
- Task kind: feature
- Persona: implementer
- Issue: #2253
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2253
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec4-explore-frontend
- Agent branch: feat/2253-panels-and-pause
- Agent worktree: .worktrees/s4-a3
- Gate record: .workflow/records/2253-feat-2253-panels-and-pause.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first.

## Required Rules

Everything in the shared preamble, plus:

- `docs/specs/adr-054-explore-frontend.md` — your spec. You implement
  **T-008 to T-011** of its §4.3, covering FR-018 to FR-027.
- `docs/specs/adr-054-panel-contract.md` and the **landed** panel host it
  produced. Your job is to *place and bind* the host, not to build one. Find
  it before writing anything.
- ADR-051 — the interactive blocks whose modal you retire.
- Agent S4-A1's slice and region contract, merged into your base.

## Scope

You own only:

- `frontend/src/explore/VariableStrip.tsx` — new.
- `frontend/src/explore/PanelSlots.tsx` — new.
- `frontend/src/explore/SessionToolbar.tsx` — the confirm and cancel controls
  of pause mode, and the open-a-notebook control, only.
- `frontend/src/explore/ExploreTab.tsx` — the pause-mode arrangement only,
  inside the region S4-A1 left for it.
- `frontend/src/App.parts/InteractiveModals.tsx` — **delete**.
- `frontend/src/App.parts/InteractiveModals.parts/**` — **delete**.
- `frontend/src/App.tsx` — stop mounting the modal.
- `frontend/src/hooks/useWebSocket.parts/dispatchEvent.ts` — the interactive
  prompt event's route only: it now opens a pause tab instead of a modal.
  S4-A1 owns the session-event routes in the same file; keep your edit
  surgical.
- Tests for each of the above.

You must not touch:

- `frontend/src/explore/NotebookShell.tsx`, `CellEditor.tsx`,
  `OutputRenderer.tsx`, `CellMarks.tsx` — S4-A2.
- `frontend/src/explore/PackagingReport.tsx`, `GraphView.tsx`,
  `BlockNode.tsx`, `BlockPalette*` — S4-A4.
- `frontend/src/store/exploreSlice.ts`, `types/api.ts`,
  `ProjectWorkspace.tsx` — S4-A1.
- Every `src/scistudio/**` path. **The backend's interactive path must be
  unchanged** — that is the point of FR-025.

If you need an out-of-scope path, stop and report back. Do not edit it.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S4-A3`.

## Work To Do

1. **T-008 — the strip and the slots.**
   The strip lists **every** binding the analysis reports with its type name,
   pinned outputs first, and shows a name that does not exist in the kernel as
   greyed and not openable (FR-018). It is populated from the analysis event,
   so a name appears as soon as the cell that binds it exists, and greys until
   the bindings response says it exists in the kernel.
   Clicking a live name mounts a panel in the centre **through the panel
   host**, requesting the **producing** capability for the variable's type and
   binding the panel to the name (FR-019) — that is the panel-contract spec's
   capability-aware resolution at work, not a second resolver of your own.
   Names declared as outputs open and pin automatically when they become live,
   and a pinned panel does not close on a strip click (FR-020).
2. **T-009 — emission, refusal, refresh, freeze.**
   Code a panel emits is sent to the session API as an emission **naming the
   panel**; on acceptance insert the cell after the current cell in the queued
   state; on refusal show the refusal naming the panel and the statement, and
   insert nothing (FR-021).
   On a changed-names event, panels bound to those names refresh and **other
   panels do not** (FR-022).
   While a cell runs, submissions from panels bound to a name in the cell's
   changed set are refused by the shell with a note, and **reading continues**
   (FR-023). The changed set comes from the cell-state event; do not compute it.
3. **T-010 — the pause tab, and the modal deleted.**
   An interactive prompt event opens an Explore tab with the block's panel
   mounted over the run's inputs, **the notebook pane absent**, and confirm
   and cancel on the toolbar (FR-024). Confirm sends the completion message
   the modal sends today and cancel sends the cancellation, **so the backend's
   interactive path is unchanged** (FR-025) — read the modal's messages before
   deleting it and assert them in a test.
   Delete the modal and its registry. The panel is resolved by the **backend**,
   by block name, as the panel-contract spec specifies; there is no frontend
   registry any more. The frontend build succeeding with the modal gone is
   what proves nothing else imported it.
4. **T-011 — escalation and the packaged ask.**
   A control on the pause toolbar opens a notebook over the paused run's
   inputs and shows the notebook pane, **while the paused block goes on
   waiting** (FR-026). That is a session open like any other.
   A prompt from a packaged block set to `ask` opens the block's notebook over
   the run's inputs in the same tab, and confirm sends the notebook commit the
   person chose (FR-027).

## Required Tests And Checks

- `VariableStrip.test.tsx` — greyed until live; pinned outputs first; a click
  requests the producing capability for the variable's type.
- `PanelSlots.test.tsx` — an accepted emission inserts a queued cell after the
  current one; a refusal names the panel and the statement and inserts
  nothing; **only bound panels refresh** on a changed-names event; the freeze
  refuses submission while reading continues.
- A pause-tab test driven by a real interactive prompt event, asserting that
  **confirm and cancel send exactly the messages the modal sent**. Cover both
  built-in interactive panels — `data_router` and `pair_editor` — because
  every existing interactive block is presented through this tab after your
  change and presentation is where the risk now sits.
- A test that the escalation control opens a session over the paused inputs
  and that the pause does not resolve.
- The dispatch test must prove the interactive prompt **no longer reaches a
  modal**.
- `npm run test`, `npm run lint`, `npm run build` in `frontend/`. **The build
  must succeed with the modal deleted.**
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec4-explore-frontend --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, `python scripts/scistudio_pr_create.py`, post-PR
  `finalize`. Base your PR on `track/adr-054-spec4-explore-frontend`.
- Docs: `--docs-na "user-docs:the human documentation revision is ADR-054
  spec 6, issue #2236"`.

## Output Required

Per the shared preamble. Additionally: list every file you deleted and state
what proved nothing still imported it.

## Stop Conditions

Per the shared preamble.
```
