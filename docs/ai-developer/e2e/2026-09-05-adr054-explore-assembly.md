---
session_id: "2026-09-05-adr054-explore-assembly"
title: "ADR-054 assembled: an Explore session opened, explored, and packaged into a block"
created: "2026-09-05"
owner: "@jiazhenz026"
trigger:
  kind: "pr-readiness"
  ref: "PR #2255 (ADR-054 specs 1-5 assembly)"
related_adrs:
  - 48
  - 51
  - 54
status: "draft"
language_source: en
---

# E2E Session — ADR-054 Explore Assembly

> Filled by the manager before the `scistudio-e2e-test` skill runs. Section 7
> is left empty; the skill writes it.

## 1. Goal And Out-Of-Scope

- **Goal**: prove that the five ADR-054 specs assemble into one working
  feature — that a scientist can open an Explore session over a block's
  outputs, run a cell, open a panel from the variable strip, have that panel
  emit code back into the notebook, watch the runtime mark the affected cells
  stale, run the stale set, and package the notebook into a block that appears
  on the canvas and reopens by double-click. This is the loop ADR-054 §1
  describes, and no unit test proves it, because every piece of it was built
  by a different agent against a different spec.

  It also proves the two retirements ADR-054 makes: the interactive-block
  modal is gone and its pause opens the same Explore tab, and a previewer
  resolves through the unified panel contract rather than the ADR-048
  ES-module one.

- **Out of scope**:
  - The agent-facing surface (spec 5). Its tools are exercised by
    `tests/ai/**`; a browser session does not reach them. The one exception
    is the workspace-focus report, which the frontend sends on tab change and
    which this session observes on the network, because that wire is the one
    seam between spec 4 and spec 5 that no unit test spans.
  - The documentation revision (spec 6, #2236). Not implemented.
  - The producing capability for the plot panel (#2212). Out of ADR-054's
    own scope per §10.2.
  - Multi-branch and merge behaviour. The session stays on one branch.

## 2. Preconditions

- **Repo state**: `track/adr-054-integration` at the head that PR #2255 shows,
  with specs 4 and 5 merged in. A run against a head missing either spec is
  not this session.
- **Working tree**: clean. `.workflow/local/**` and `.audit/**` may be dirty;
  nothing else.
- **Worktree to run from**: `.worktrees/mgr-054`
- **Backend port**: `8123` — deliberately not 8000, because the owner's own
  GUI may be on the default and this session must not fight it.
- **Frontend mode**: Vite dev server against `scistudio serve`.
  **The dev server must bind `127.0.0.1` explicitly**: `--host 127.0.0.1`.
  Without it the Electron window renders blank while `localhost` in a browser
  looks fine, and the failure is hard to attribute.
- **Required services / env vars**: none beyond a clean dev install.
  `PYTHONPATH=./src`; no `pip install -e .`.
- **Required data / fixtures**: a project containing a workflow with at least
  one block that has run and produced a tabular output, and at least one
  interactive block (`data_router` or `pair_editor`) wired into a workflow
  that can be run to its pause. Create it in the session if none exists —
  Step 1 does.
- **External accounts**: none. No step requires an AI provider.

## 3. Launch Plan

- **Backend start**:
  ```powershell
  $env:PYTHONPATH = "./src"; python -m scistudio serve --port 8123
  ```
- **Frontend start**:
  ```powershell
  cd frontend; npm run dev -- --port 5183 --host 127.0.0.1
  ```
- **Readiness probe**:
  ```powershell
  until curl -s http://127.0.0.1:8123/api/health | Select-String '"ok"'; do Start-Sleep 0.5; done
  ```
- **Cleanup commands** (run at end, even on failure):
  ```powershell
  Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match '5183|8123' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  ```
  Match on **this session's ports**, not on `vite` or `scistudio`. Several
  agents and the owner's own app run on this machine; a broad kill takes
  down work that is not this session's.

## 4. Affordances Under Test

- Workflow canvas — the new **node context menu** and its explore action,
  including the disabled state with a reason on a block with no outputs.
- Project tree — the new **file context menu** and its explore action.
- Centre area — the **Explore tab** as a tab-union member: opening,
  deduplication by notebook path, and survival of a page reload.
- Right column — the **notebook shell** replacing the data preview while an
  Explore tab is active, and the preview returning when it is not.
- Notebook shell — Monaco cell editing, run, the `.ipynb` output rendering,
  and the three marks as the runtime reports them.
- Variable strip — bindings listed with types, greyed until live, a click
  mounting a panel through the **unified panel host**.
- Panel host — a producing panel emitting code, and the emitted cell arriving
  in the notebook queued.
- Session toolbar — run-stale with its count, interrupt, restart, the kernel
  list, and package.
- Packaging — the check report, the confirm control's enablement, the block
  appearing in the palette, and the packaged node's badge and double-click.
- Interactive pause — an interactive block's prompt opening the **Explore tab
  in pause mode** rather than the retired modal, with confirm and cancel.
- Graph view — the secondary dependency-graph view.
- The workspace-focus report on tab change (`POST` on the active-workflow
  channel), observed on the network.

## 5. Steps

### Step 1 — Open a project with a run block

- **Action**: open the app at `http://127.0.0.1:5183`, open or create a
  project, build a minimal workflow with a data-loading block, and run it to
  completion so the block has outputs.
- **Expected**: the canvas shows the block in a completed state; the run
  finishes without an error toast.
- **Capture**: screenshot of the canvas; network requests to `/api/runs`.
- **On failure**: halt. Nothing downstream is meaningful without a run block.

### Step 2 — The node context menu, and its disabled state

- **Action**: right-click a block node that has **not** run. Then right-click
  the block from Step 1.
- **Expected**: a context menu appears on both — this menu is new; the canvas
  had none before. On the un-run block the explore action is **disabled and
  states a reason**. On the run block it is enabled.
- **Capture**: screenshot of each menu.
- **On failure**: halt.

### Step 3 — Open the Explore tab

- **Action**: choose the explore action on the run block.
- **Expected**: a new centre tab opens. The right column now shows the
  **notebook shell** and **not** the data preview. The left pane (palette,
  project tree) and the bottom panel are visibly unchanged. Nothing has run:
  the kernel state reads none or starting, and no cell has output.
- **Capture**: full-window screenshot; the `POST` carrying the workspace focus
  with mode `explore`, its notebook path and its bound run — record the exact
  body.
- **On failure**: halt.

### Step 4 — Tab identity and reload survival

- **Action**: choose the same explore action again. Then reload the page.
- **Expected**: the second invocation **activates the existing tab** rather
  than opening a second one. After the reload the Explore tab is still there
  and re-fetches its session state; the notebook shows the same cells.
- **Capture**: screenshot after reload.
- **On failure**: continue and mark the step failed — a duplicate tab is a
  real defect but does not stop the rest of the session.

### Step 5 — Run a cell

- **Action**: type a statement into the first cell that binds a name from the
  block's output, and run it.
- **Expected**: the kernel starts, the cell runs, output renders from the
  `.ipynb` MIME bundle, and the cell's never-run mark clears. The variable
  strip lists the bound name with its type name and shows it **live** rather
  than greyed.
- **Capture**: screenshot of the cell with its output and the strip;
  console messages matching `/error|warn/i`.
- **On failure**: halt.

### Step 6 — Open a panel from the strip

- **Action**: click the live name in the variable strip.
- **Expected**: a panel mounts in the centre through the panel host, bound to
  that name, showing the data. It is the **framed document** form of the
  unified contract, not an ES module — the network shows the panel descriptor
  and asset requests, not a module import.
- **Capture**: screenshot of the mounted panel; the panel descriptor response.
- **On failure**: halt.

### Step 7 — The panel emits a cell

- **Action**: perform an action in the panel that produces a value — a
  selection, a filter, a threshold, whatever the panel's producing capability
  offers.
- **Expected**: a new cell appears in the notebook **after the current cell**,
  in the queued state, carrying the code the panel emitted. The panel is
  named in whatever the shell shows about the emission.
- **Capture**: screenshot of the inserted cell; the emission request and its
  response.
- **On failure**: halt. This is the step no unit test can stand in for.

### Step 8 — The stale mark, drawn not computed

- **Action**: edit and re-run the **first** cell so that a name a later cell
  reads changes.
- **Expected**: the later cell carries a **stale** mark, and an out-of-order
  mark where the runtime reports one, with the names and cells that caused it
  named. The toolbar's run-stale control shows a **count**. Nothing ran that
  the person did not ask to run.
- **Capture**: screenshot of the marks and the run-stale count; the
  cell-state events on the WebSocket.
- **On failure**: continue and mark failed.

### Step 9 — Run the stale set

- **Action**: click run-stale.
- **Expected**: exactly the stale cells run, in order; their marks clear; no
  other cell runs.
- **Capture**: screenshot after; the run requests.
- **On failure**: continue and mark failed.

### Step 10 — The graph view

- **Action**: open the secondary graph view.
- **Expected**: one node per variable version, edges with their origins, and
  the cells marked stale or out of order highlighted. A connected region can
  be selected.
- **Capture**: screenshot.
- **On failure**: continue and mark failed.

### Step 11 — The kernel list

- **Action**: expand the kernel list on the toolbar.
- **Expected**: the live kernel is listed with its session and its memory, and
  an end control. Ending it moves the list only after the event arrives, and
  the shell then offers a restart.
- **Capture**: screenshot before and after ending.
- **On failure**: continue and mark failed. Restart the kernel before Step 12.

### Step 12 — Package the notebook

- **Action**: click package.
- **Expected**: the **check** runs first and its report renders — the slice
  cells and the inferred ports for a clean notebook, or the offending cells
  and reads with confirm **disabled**. If refusals are shown, fix the notebook
  until they are not, and record what they were.
- **Capture**: screenshot of the report.
- **On failure**: halt.

### Step 13 — Confirm packaging

- **Action**: confirm.
- **Expected**: the block palette refreshes and the new block appears in it.
  Dragging it onto the canvas produces a node carrying a **notebook badge**.
- **Capture**: screenshot of the palette and the badged node.
- **On failure**: halt.

### Step 14 — Reopen the packaged block

- **Action**: double-click the packaged block's node.
- **Expected**: its notebook opens in an Explore tab bound to the node's most
  recent run. This is the loop closing: the exploration became a block, and
  the block is still the exploration.
- **Capture**: screenshot.
- **On failure**: halt.

### Step 15 — The palette inserts a call

- **Action**: with the Explore tab active, use a block card in the palette to
  insert a call to that block.
- **Expected**: a call cell is inserted after the current cell.
- **Capture**: screenshot.
- **On failure**: continue and mark failed.

### Step 16 — The interactive pause opens the Explore tab, not a modal

- **Action**: run a workflow containing an interactive block (`data_router`
  or `pair_editor`) until it pauses.
- **Expected**: an **Explore tab in pause mode** opens — the block's panel
  over the run's inputs, **no notebook pane**, confirm and cancel on the
  toolbar. **No modal appears.** The workspace focus reported on the network
  reads mode `pause` with the paused node and its run.
- **Capture**: full-window screenshot; the focus `POST` body; the DOM checked
  for any dialog or modal container.
- **On failure**: halt. The modal's retirement is one of ADR-054's two
  headline unifications; a modal appearing here means it did not happen.

### Step 17 — Confirm the pause, and escalate one

- **Action**: use the pause tab's control to open a notebook over the paused
  inputs, observe that the block goes on waiting, then confirm the decision.
- **Expected**: the notebook pane appears over the same inputs while the pause
  is unresolved; confirm then resolves the run and the workflow continues to
  completion.
- **Capture**: screenshot at each stage; the completion message on the network.
- **On failure**: continue and mark failed.

### Step 18 — Leave the tab, and the preview returns

- **Action**: switch to a workflow tab, then open a data file's context menu
  in the project tree and use its explore action.
- **Expected**: leaving the Explore tab restores the data preview in the right
  column and the workspace focus reports mode `canvas` with the workflow id.
  The file context menu — also new — opens a session over the file.
- **Capture**: screenshot; the focus `POST` body for the canvas mode.
- **On failure**: continue and mark failed.

## 6. Regression Sentinels

Checked continuously; a hit fails the session even mid-step.

- **Console errors**: no uncaught React error, no unhandled promise
  rejection, and specifically nothing matching
  `/Cannot read propert|is not a function|Maximum update depth|Each child in a list/`.
  The last of those matters here: the notebook shell and the variable strip
  are both list renderers written by different agents.
- **Network errors**: no 5xx from any endpoint. No 404 on a panel asset —
  a 404 there means the unified contract's asset route is not serving what a
  descriptor points at, which would be invisible in a screenshot because the
  panel would simply render empty.
- **Native dialogs**: `alert`, `confirm` and `prompt` never fire. Beyond the
  usual reason, a native dialog would block the Chrome MCP session outright.
- **Modal container**: no interactive-block modal is mounted at any point.
  FR-024 deletes it; a screenshot that happens not to show it is not proof, so
  check the DOM.
- **Process health**: the backend process does not exit; the Vite dev server
  stays responsive. A dev-server death mid-session presents as a frontend bug
  and is not one.
- **Kernel processes**: no kernel process is left running after cleanup.

## 7. Results (skill fills in)

### 7.1 Verdict
