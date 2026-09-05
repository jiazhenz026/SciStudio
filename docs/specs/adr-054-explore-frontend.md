---
spec_id: adr-054-explore-frontend
title: "ADR-054 Explore Frontend — The Explore Tab, The Notebook Shell, And One Surface For Every Interaction"
status: Draft
feature_branch: docs/adr-054-explore-frontend-spec
created: 2026-09-02
input: "Owner-directed live session (guided): author the explore-frontend spec for ADR-054 sections 2, 4.2, 4.4, 6.1, and 6.3. The owner settled the design in discussion — one Explore tab hosts every interaction; the left pane is unchanged, the centre is the panel host with a variable strip and the session toolbar, the right pane is the notebook replacing the data preview while the tab is active, the bottom panel is unchanged; the notebook shell is SciStudio's own with one Monaco editor per visible cell and no notebook library, rendering the .ipynb output format natively; the variable strip lists every binding the analysis reports and declared outputs are pinned; nothing runs on open and a name that does not yet exist is shown greyed; sessions open from a block's context menu, a file's context menu, a packaged block's node, or an interactive block's pause; the kernel list is a collapsible list on the toolbar; packaging is a toolbar button; the interactive-block modal is retired; the dependency graph is drawn with the graph library already in the bundle; events arrive over the existing WebSocket."
owners:
  - "@jiazhenz026"
related_adrs:
  - 36
  - 42
  - 44
  - 50
  - 51
  - 53
  - 54
related_specs:
  - adr-054-panel-contract
  - adr-054-notebook-dependency-analysis
  - adr-054-explore-session
  - adr-054-documentation
  - adr-051-interactive-blocks
scope:
  in:
    - An Explore tab as a new member of the centre-area tab union, its identity, its deduplication, and its persistence across a reload.
    - The four ways a session opens into the tab - a block's context menu, a file's context menu, a packaged block's node, and an interactive block's pause - and the two context menus, which are new to the canvas and the tree.
    - The layout while the tab is active - left pane unchanged, centre panel host with a variable strip and the session toolbar, right pane notebook in place of the data preview, bottom panel unchanged.
    - The notebook shell - cell list, one Monaco editor per visible cell, code and markdown cells, add, delete, move, enable toggle, run, outputs from the .ipynb MIME bundle, marks, run-stale and run-with-upstream, interrupt and restart, kernel list, commit to branch, package with its report.
    - The variable strip, panel opening from it, pinned declared outputs, panel refresh on changed names, and the shallow freeze as presented.
    - The interactive-block pause opening the Explore tab with no notebook pane, confirm and cancel on the toolbar, escalation to a notebook, and the retirement of the modal.
    - The packaged block's node badge and double-click, and the block-palette card that inserts a block call into the notebook.
    - The dependency-graph secondary view.
    - Handling of the session events over the existing WebSocket, and the frontend store slice that holds session state.
    - Unit tests with the existing toolchain and one end-to-end scenario.
  out:
    - The session service, the kernel, the queue, the marks as computed, packaging as performed, and the API and events as emitted (adr-054-explore-session). This spec consumes them.
    - The dependency analysis and the graph queries (adr-054-notebook-dependency-analysis).
    - The panel contract, the frame host, the message contract, and panel editing (adr-054-panel-contract). This spec places the host and binds it.
    - The agent-facing skill, reference, and tools (the agent-enablement spec).
    - Human documentation revision (adr-054-documentation).
    - A general-purpose notebook IDE, a separate application layout for sessions, and any change to the workflow canvas beyond the context menu and the packaged node's badge.
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-054-explore-frontend.md
    - frontend/src/store/types.ts
    - frontend/src/types/api.ts
    - frontend/src/types/ui.ts
    - frontend/src/App.tsx
    - frontend/src/App.parts/ProjectWorkspace.tsx
    - frontend/src/App.parts/InteractiveModals.tsx
    - frontend/src/App.parts/InteractiveModals.parts/**
    - frontend/src/components/WorkflowCanvas.tsx
    - frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.ts
    - frontend/src/components/nodes/BlockNode.tsx
    - frontend/src/components/nodes/BlockNode.parts/**
    - frontend/src/components/ProjectTree.tsx
    - frontend/src/components/ProjectTree.parts/**
    - frontend/src/components/BlockPalette.tsx
    - frontend/src/components/BlockPalette.parts/**
    - frontend/src/components/DataPreview.tsx
    - frontend/src/hooks/useWebSocket.parts/dispatchEvent.ts
    - frontend/src/explore/**
    - frontend/src/store/exploreSlice.ts
    - frontend/src/types/explore.ts
    - frontend/e2e/specs/**
  excludes:
    - frontend/src/components/DataPreview.parts/**
    - frontend/src/panels/**
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - frontend/src/explore/ExploreTab.test.tsx
  - frontend/src/explore/NotebookShell.test.tsx
  - frontend/src/explore/CellEditor.test.tsx
  - frontend/src/explore/OutputRenderer.test.tsx
  - frontend/src/explore/VariableStrip.test.tsx
  - frontend/src/explore/SessionToolbar.test.tsx
  - frontend/src/explore/GraphView.test.tsx
  - frontend/src/store/exploreSlice.test.ts
  - frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.test.ts
  - frontend/src/hooks/useWebSocket.parts/dispatchEvent.test.ts
  - frontend/e2e/specs/adr054-explore.spec.ts
acceptance_source: adr
language_source: en
---

# ADR-054 Explore Frontend — The Explore Tab, The Notebook Shell, And One Surface For Every Interaction

## 1. Change Summary

ADR-054 §4.4 says where a session appears: the centre area is already a
discriminated union of tabs, and an Explore tab joins it. This spec is the
whole of that sentence. It adds the tab, the four ways into it, the layout
while it is active, the notebook shell the right pane renders, the variable
strip and the panels the centre hosts, the marks and the controls the session
runtime exposes, and the handling of the session's events. It also retires the
interactive-block modal, because ADR-054 §4.2 makes the Explore tab the one
surface for every interaction: an interactive block's pause opens the same
tab with its panels and no notebook.

From the person's side the result is a Jupyter notebook in the right pane
that behaves like one, with three things beside it that Jupyter does not have.
The centre shows live panels over the variables the notebook binds, and an
edit made in a panel becomes a cell. Two marks, stale and out of order, say
where the screen disagrees with written order, and two controls act on them
only when asked. And a button packages the notebook into a block that appears
in the palette.

The shell is SciStudio's own. The kernel, the queue, the marks, the commits,
and packaging are the session runtime's, and the frontend renders their state
and sends their commands; nothing here talks to a kernel. The cell editor is
the Monaco editor the bundle already carries, one instance per visible cell.
No notebook library is introduced: the only one worth considering carries its
own widget system and its own kernel client, and the kernel client is the one
part this design cannot use, because every execution must pass through the
session service. What is reused from Jupyter is its file format, whose output
MIME bundle the shell renders natively.

## 2. User Scenarios & Testing

### User Story 1 - A block's outputs open in an Explore tab (Priority: P1)

A person right-clicks a block that has run and chooses to explore its outputs.
An Explore tab opens in the centre area. The left pane is what it was. The
centre shows an empty panel host with a variable strip listing the port
variables, greyed because nothing has run. The right pane shows the notebook
with its generated first cell. The bottom panel is unchanged. They run the
first cell; the strip's names turn live.

**Why this priority**: This is the entry and the layout. Every other story
happens inside this tab, and if the layout separated the session from the
palette, the project tree, and the block cards, ADR-054 §4.4's reason for
choosing a tab over a separate application would be lost.

**Independent Test**: Right-click a block node with outputs, choose explore,
and confirm an Explore tab is active, the right pane renders the notebook,
the data preview is not rendered, the centre renders the variable strip with
greyed names, and the left and bottom panes are unchanged. Run the first cell
through the shell and confirm the names become openable. Right-click a block
without outputs and confirm the action is disabled with a reason.

**Acceptance Scenarios**:

1. **Given** a block node whose outputs exist, **When** the person opens its
   context menu, **Then** it offers to explore the outputs, and choosing it
   opens an Explore tab bound to that session.
2. **Given** a block node whose outputs have never been produced, **When** the
   person opens its context menu, **Then** the explore action is disabled and
   says there is nothing to explore.
3. **Given** an Explore tab is active, **When** the workspace renders,
   **Then** the right pane shows the notebook in place of the data preview,
   the centre shows the panel host with the variable strip and the toolbar,
   and the left and bottom panes are unchanged.
4. **Given** a session just opened, **When** the strip renders, **Then** every
   binding the analysis reports is listed with its type, and a name that does
   not exist in the kernel is shown greyed and cannot be opened.
5. **Given** a file in the data tree, **When** the person opens its context
   menu and chooses explore, **Then** an Explore tab opens on a session whose
   first cell loads the file.
6. **Given** an Explore tab, **When** the person switches to another tab and
   back, **Then** the session, its marks, and its open panels are as they
   were.

### User Story 2 - The notebook behaves like Jupyter and shows the marks (Priority: P2)

The person adds cells, edits them, runs them one at a time, sees outputs,
tracebacks, and inline images beneath them, and types magics. When they edit
a middle cell and re-run it, the cell shows an out-of-order mark with a
control to run it with its upstream, and the cells below show a stale mark.
Nothing runs on its own. They click the run-stale control.

**Why this priority**: The notebook is the surface the target users already
know, and the marks are the one addition ADR-054 §6.1 makes to it. It ranks
below Story 1 because it lives inside the tab.

**Independent Test**: Drive the shell against a scripted session: add, edit,
move, delete, and run cells; confirm each command reaches the API and each
state event updates the shell; render fixture outputs of every MIME type the
shell supports; apply mark events and confirm the marks and their controls
render; confirm the controls send run-stale and run-with-upstream and
nothing is sent unasked.

**Acceptance Scenarios**:

1. **Given** a notebook of many cells, **When** it renders, **Then** only the
   visible cells carry an editor and the rest render as static highlighted
   text, and scrolling swaps them without losing edits.
2. **Given** a cell with outputs of text, error, and image types, **When** it
   renders, **Then** each output renders from the notebook's MIME bundle and
   an error shows its traceback with colour.
3. **Given** a cell marked out of order, **When** it renders, **Then** it
   shows the mark, the names and cells that caused it, and a control that
   sends run-with-upstream for that cell.
4. **Given** cells marked stale, **When** the toolbar renders, **Then** it
   shows the count and a control that sends run-stale, and the marked cells
   show the mark.
5. **Given** a cell's enable toggle, **When** the person disables it,
   **Then** the cell renders as disabled, the toggle is sent to the API, and
   the marks update from the next analysis event.
6. **Given** a running cell, **When** the person interrupts, **Then** the
   interrupt is sent and the cell shows the interrupted state when the event
   arrives.

### User Story 3 - A panel edit becomes a cell and the panels stay live (Priority: P3)

The person clicks `df` in the strip; a table panel opens in the centre. They
delete two rows in it. A new cell appears after the current cell with the
emitted code and runs; the panel refreshes; the cells below show stale marks.
While a long cell runs, the panel still scrolls and sorts, and an attempt to
submit from it is refused with a note until the cell ends.

**Why this priority**: This is the loop that makes the centre worth having
and the reason a producing panel exists. It ranks below Story 2 because it is
the notebook plus one binding.

**Independent Test**: Open a panel from the strip and confirm the host is
mounted with a producing request for the variable's type. Emit code from a
stub panel and confirm the shell inserts the cell after the current cell
when the API accepts it, and shows the refusal naming the panel when the API
refuses. Deliver a changed-names event and confirm only panels bound to those
names refresh. Deliver a running state for a cell whose changed set includes
`df` and confirm the panel's emission is refused while reads continue.

**Acceptance Scenarios**:

1. **Given** a live name in the strip, **When** the person clicks it,
   **Then** a panel resolved for the variable's type with the producing
   capability is mounted in the centre bound to that name.
2. **Given** a name declared as output, **When** the strip renders,
   **Then** its panel is opened and pinned automatically.
3. **Given** a mounted panel emits code, **When** the API accepts it,
   **Then** a cell appears after the current cell with that code and shows
   the queued state.
4. **Given** a mounted panel emits code the API refuses, **When** the refusal
   arrives, **Then** the shell shows it naming the panel and the statement,
   and no cell is inserted.
5. **Given** a changed-names event after a run, **When** it arrives,
   **Then** panels bound to those names refresh and other panels do not.
6. **Given** a cell is running whose changed set includes a bound name,
   **When** that panel tries to submit, **Then** the shell refuses the
   submission with a note and the panel keeps reading.

### User Story 4 - An interactive block's pause opens the same tab (Priority: P4)

A workflow reaches an interactive block and pauses. Instead of a modal, an
Explore tab opens with the block's panel in the centre bound to the run's
inputs and no notebook pane. The person makes their choice and clicks
confirm on the toolbar; the workflow continues. On another occasion they
click the notebook control instead, a notebook pane appears over the same
inputs, and they explore.

**Why this priority**: ADR-054 §4.2 makes one surface for every interaction
and retires the modal. It ranks below Story 3 because it is the same host and
toolbar with the notebook pane absent.

**Independent Test**: Deliver an interactive prompt event and confirm an
Explore tab opens with the panel mounted, no notebook pane, and confirm and
cancel on the toolbar; confirm that confirm sends the same completion message
the modal sent and cancel sends the same cancellation; confirm the modal
component no longer exists. Click the notebook control and confirm a session
is opened over the paused run's inputs and the notebook pane appears.

**Acceptance Scenarios**:

1. **Given** an interactive prompt event, **When** it arrives, **Then** an
   Explore tab opens with the block's panel mounted over the run's inputs and
   the notebook pane absent.
2. **Given** the tab of scenario 1, **When** the person confirms,
   **Then** the completion is sent exactly as the modal sent it and the tab
   shows the block continuing.
3. **Given** the tab of scenario 1, **When** the person cancels, **Then** the
   cancellation is sent and the tab closes.
4. **Given** the tab of scenario 1, **When** the person opens the notebook
   pane, **Then** a session is opened over the paused run's inputs and the
   pane renders its notebook, while the paused block still awaits its
   decision.
5. **Given** a packaged block set to ask pauses, **When** the prompt arrives,
   **Then** the tab opens the block's notebook over the run's inputs, and
   confirming sends the notebook commit the person chose.

### User Story 5 - The notebook becomes a block from the toolbar (Priority: P5)

The person clicks package on the toolbar. A report shows the cells the block
will run and the ports it will have, or the cells and reads that prevent
packaging. They confirm; the block appears in the palette. Its node on the
canvas carries a notebook badge, and double-clicking it opens the notebook.

**Why this priority**: Packaging is where the session becomes a workflow
step. It ranks below the interactive stories because it is one dialog and one
badge.

**Independent Test**: Request the packaging check through the toolbar and
render the report for a clean notebook and for each refusal; confirm the
package command is sent only from a clean report; deliver a packaged event
and confirm the palette refreshes; render a packaged block's node and confirm
the badge; double-click it and confirm the session opens.

**Acceptance Scenarios**:

1. **Given** a clean notebook, **When** the person clicks package,
   **Then** the report lists the slice cells and the inferred ports, and
   confirming sends the package command.
2. **Given** a notebook with a refusal, **When** the person clicks package,
   **Then** the report names the offending cells or reads and the confirm
   control is disabled.
3. **Given** a packaged event, **When** it arrives, **Then** the block palette
   refreshes and the new block appears.
4. **Given** a packaged block's node, **When** it renders, **Then** it carries
   a notebook badge, and double-clicking it opens the block's notebook in an
   Explore tab bound to the node's most recent run.

### User Story 6 - Kernels are visible and the graph is drawable (Priority: P6)

The person opens the kernel list on the toolbar and sees every live kernel in
the project with its session and memory, and ends one. They open the graph
view and see one node per variable version with the edges the analysis
reports, and the stale cells highlighted.

**Why this priority**: The kernel list discharges ADR-054 §5.3's obligation
that a resident process be attributable without a dedicated surface; the
graph view is ADR-054 §4.4's secondary view. Both are verified by rendering
rather than by use, which is why they rank last.

**Independent Test**: Deliver kernel-state events for three sessions and
confirm the list renders each with memory and an end control that sends the
end command. Deliver an analysis event and confirm the graph view renders
the version nodes and edges with the graph library, highlights stale cells,
and lets a connected region be selected.

**Acceptance Scenarios**:

1. **Given** kernel-state events for several sessions, **When** the list
   opens, **Then** each is shown with its session and memory and an end
   control, and ending one sends the command.
2. **Given** a branch change retires the kernels, **When** the events
   arrive, **Then** the tab shows that the kernel needs a restart and offers
   it.
3. **Given** an analysis event, **When** the graph view is open, **Then** it
   renders one node per variable version and the edges, highlights cells
   marked stale or out of order, and lets a connected region be selected.
4. **Given** the block palette while an Explore tab is active, **When** the
   person uses a block's card to insert a call, **Then** a cell with the
   block call is inserted after the current cell.

### Edge Cases

- **Two entries point at the same notebook.** The tab is keyed by the
  session's notebook path, so a second open activates the existing tab.
- **The Explore tab is active and the person runs the workflow.** The tab
  stays; workflow events update the canvas behind it as they do today, and a
  pause at an interactive block opens its own Explore tab beside this one.
- **The page reloads with an Explore tab open.** The tab is persisted by its
  session path like a file tab; on reload the session state is fetched and
  the kernel state is whatever the runtime reports.
- **The session's kernel dies.** The tab shows the kernel dead, offers
  restart, and renders every cell as never-run when the event arrives.
- **A panel fails to load.** The panel host's own failure behaviour applies:
  the host's error surface and the fallback panel the backend names render in
  the centre slot, and the strip entry stays.
- **The notebook is edited outside SciStudio.** The reload event replaces the
  cells; an editor with unsaved edits for a cell whose id survived keeps its
  draft and is marked as conflicting until saved or discarded.
- **A very long output.** Text outputs above a bound are truncated with a
  control to show all; image outputs render at their size within the pane.
- **The right pane is collapsed.** The notebook can be collapsed like the data
  preview today; the centre and the toolbar remain, so a person can work with
  panels alone.
- **The variable strip overflows.** Names scroll horizontally; pinned outputs
  stay first.

## 3. Requirements

### Functional Requirements

**The tab**

- **FR-001**: The centre-area tab union MUST gain an Explore member keyed by
  the session's notebook path. Opening a session whose tab exists MUST
  activate that tab. The tab MUST persist across a reload like a file tab and
  re-fetch its session state on restore.
- **FR-002**: An Explore tab MUST open from four entries: the context menu of
  a block node whose outputs exist; the context menu of a file in the data
  tree; double-clicking a packaged block's node; and an interactive prompt
  event. A block node without outputs MUST show the explore action disabled
  with a reason.
- **FR-003**: A context menu MUST be added to block nodes on the canvas and to
  files in the data tree. The canvas has no context menu today, and the menu
  MUST carry only the explore action until other actions are specified.
- **FR-004**: Double-click on a packaged block's node MUST open its notebook
  in an Explore tab bound to the node's most recent run, extending the
  existing double-click handler that opens a subworkflow.

**The layout**

- **FR-005**: While an Explore tab is active, the right pane MUST render the
  notebook shell in place of the data preview, the centre MUST render the
  panel host with the variable strip above it and the session toolbar, and
  the left pane and the bottom panel MUST be unchanged.
- **FR-006**: The right pane MUST be collapsible as the data preview is
  today, and the centre and toolbar MUST remain usable with it collapsed.
- **FR-007**: The centre MUST host more than one panel at a time, each bound
  to one name, arranged so that a person can compare two.

**The notebook shell**

- **FR-008**: The shell MUST render the notebook's cells in order with a
  Monaco editor for each visible code cell and static highlighted text for
  cells outside the viewport, preserving unsaved edits when an editor is
  swapped out.
- **FR-009**: The shell MUST support code and markdown cells; markdown cells
  MUST render with the markdown renderer already in the bundle and edit in
  place.
- **FR-010**: The shell MUST offer add, delete, and move for cells, a per-cell
  run control, and a per-cell enable toggle, each sent to the session API,
  and MUST reflect the resulting cell-state events.
- **FR-011**: The shell MUST render cell outputs from the notebook's MIME
  bundle: plain text, stream output, errors with their traceback rendered
  with ANSI colour, images, and HTML in a sandboxed frame. Unknown MIME types
  MUST fall back to plain text where available and otherwise to a note.
- **FR-012**: The shell MUST render the three marks the runtime reports —
  never-run, stale, and out-of-order — on the cell, and an out-of-order mark
  MUST show the names and cells that caused it.
- **FR-013**: The shell MUST offer run-stale on the toolbar with the stale
  count, and run-with-upstream on an out-of-order cell, and MUST send nothing
  the person did not ask for.
- **FR-014**: The toolbar MUST offer interrupt, restart, commit to branch,
  package, the notebook toggle, and a collapsible kernel list.
- **FR-015**: The kernel list MUST show every live kernel in the project with
  its session and memory and an end control, from the kernel-state events.
- **FR-016**: The shell MUST show the kernel's state — none, starting, idle,
  busy, dead, needs restart — and MUST offer restart when the runtime reports
  the kernel dead or retired.
- **FR-017**: Cell edits MUST be sent to the session API on a debounce and on
  run, and the shell MUST reconcile a reload event with unsaved edits by cell
  id, keeping the draft and marking it as conflicting.

**The variable strip and the panels**

- **FR-018**: The strip MUST list every binding the analysis reports with its
  type name, ordered with pinned outputs first, and MUST show a name that does
  not exist in the kernel as greyed and not openable.
- **FR-019**: Clicking a live name MUST mount a panel in the centre through
  the panel host, requesting the producing capability for the variable's type
  and binding the panel to the name.
- **FR-020**: Names declared as outputs MUST be opened and pinned
  automatically when they become live, and pinned panels MUST NOT close on a
  strip click.
- **FR-021**: Code a panel emits MUST be sent to the session API as an
  emission naming the panel; on acceptance the shell MUST insert the cell
  after the current cell in the queued state; on refusal the shell MUST show
  the refusal naming the panel and the statement and insert nothing.
- **FR-022**: On a changed-names event, panels bound to those names MUST
  refresh and other panels MUST NOT.
- **FR-023**: While a cell runs, submissions from panels bound to a name in
  the cell's changed set MUST be refused by the shell with a note, and
  reading MUST continue; the set comes from the cell-state event.

**One surface for every interaction**

- **FR-024**: An interactive prompt event MUST open an Explore tab with the
  block's panel mounted over the run's inputs, the notebook pane absent, and
  confirm and cancel on the toolbar. The modal and its registry MUST be
  deleted.
- **FR-025**: Confirm MUST send the completion message the modal sends today,
  and cancel MUST send the cancellation, so that the backend's interactive
  path is unchanged.
- **FR-026**: The toolbar of a pause tab MUST offer opening a notebook, which
  opens a session over the paused run's inputs and shows the notebook pane,
  while the paused block continues to await its decision.
- **FR-027**: A prompt from a packaged block set to ask MUST open the block's
  notebook over the run's inputs in the same tab, and confirm MUST send the
  notebook commit the person chose.

**Packaging and the packaged node**

- **FR-028**: The package control MUST first request the packaging check and
  render its report: the slice cells and inferred ports for a clean notebook,
  or the offending cells and reads with the confirm control disabled.
- **FR-029**: On a packaged event the block palette MUST refresh and the new
  block MUST appear.
- **FR-030**: A packaged block's node MUST carry a notebook badge.
- **FR-031**: While an Explore tab is active, a block's card in the palette
  MUST offer inserting a call to that block into the notebook after the
  current cell.

**The graph view**

- **FR-032**: The tab MUST offer a secondary graph view rendered with the
  graph library already in the bundle: one node per variable version, edges
  from the analysis event with their origin, cells marked stale or out of
  order highlighted, and a connected region selectable.

**Events and state**

- **FR-033**: The frontend MUST handle the session events over the existing
  WebSocket dispatch — session opened and closed, kernel state, cell state
  with marks, cell output, changed names, analysis updated, commit recorded,
  and packaged — and MUST hold session state in one store slice.
- **FR-034**: The frontend MUST NOT hold runtime truth: every mark, kernel
  state, and binding it shows MUST come from the runtime's events or
  responses, and a command MUST be reflected only when its event arrives.
- **FR-035**: The frontend MUST open no connection to a kernel.

**Tests**

- **FR-036**: Every component listed in the frontmatter MUST have unit
  coverage with the existing toolchain, and one end-to-end scenario MUST open
  a session from a block, run a cell, open a panel, emit a cell from it, see
  a stale mark, run the stale set, and package.

### Key Entities

- **ExploreTab** — the union member. Attributes: kind, id, session path,
  mode (session or pause), bound run, the pause's node when in pause mode.
  Relationships: one per session or pause; keyed by session path; persisted
  like a file tab.
- **ExploreSliceState** — the store slice. Attributes: sessions by path with
  cells, marks, kernel state, bindings, open panels, pinned names, the graph,
  the last report. Relationships: written only from events and responses;
  read by every component of this spec.
- **CellView** — one cell as rendered. Attributes: id, kind, source, outputs,
  enabled, mark with its reason, run state, editor mounted or static.
  Relationships: one per notebook cell; draft edits reconciled by id.
- **VariableEntry** — one strip item. Attributes: name, type name, live,
  pinned, open panel id. Relationships: derived from the bindings response
  and the analysis event.
- **PanelSlot** — one mounted panel in the centre. Attributes: panel id,
  bound name, pinned, frozen for submission. Relationships: mounted through
  the panel host; refreshed on changed names.
- **ContextMenu** — the new menu on block nodes and data-tree files.
  Attributes: target, actions. Relationships: opens an ExploreTab.
- **PackagingReportView** — the rendered report. Attributes: slice cells,
  ports, refusals, confirm enabled. Relationships: rendered from the check
  response; sends the package command.
- **GraphView** — the secondary view. Attributes: version nodes, edges with
  origins, highlighted cells, selection. Relationships: rendered from the
  analysis event.

## 4. Implementation Plan

### 4.1 Technical Approach

**One more member of a union that exists.** The workspace already renders the
centre by the active tab's kind and mounts the data preview in the right
column unconditionally. The Explore member adds one branch to the centre
switch and one condition to the right column: when the active tab is an
Explore tab, the right column renders the notebook shell instead of the data
preview. The left pane and the bottom panel are not touched, which is what
keeps the palette, the project tree, and the block cards available while
exploring. The tab is keyed by the session's notebook path so that the
existing deduplication by id serves it.

**Two context menus that do not exist yet.** The canvas has a double-click
handler and no context menu, and the data tree has a double-click that opens
a preview. Both gain a context menu carrying the explore action alone, with
the block node's action disabled when the runtime reports no outputs. The
double-click handler is extended to recognise a packaged block's node beside
the subworkflow node it already recognises.

**A shell of our own, on Monaco.** The notebook shell is a cell list. Each
visible code cell mounts the Monaco editor the bundle already carries; cells
outside the viewport render as static highlighted text, because a hundred
editor instances would not be acceptable and a hundred static blocks are.
Outputs render from the `.ipynb` MIME bundle — text, streams, errors with
ANSI colour, images, and sandboxed HTML — which is what makes the notebook
look the same here and in Jupyter. Markdown cells use the markdown renderer
already in the bundle. No notebook library is introduced: JupyterLab's
components carry a widget system foreign to this application and a kernel
client that would bypass the session service, and the React wrappers over
them still need a Jupyter server behind them.

**The centre is the panel host, placed.** The panel-contract spec defines the
frame host and the message contract; this spec places it in the centre,
mounts one host per open panel, and binds each to a name. The variable strip
above it is populated from the analysis event, so it lists a name as soon as
the cell that binds it exists and greys it until the bindings response says
it exists in the kernel. A click requests the producing capability for the
variable's type, which is the panel-contract spec's capability-aware
resolution at work. Declared outputs pin themselves when they become live.

**Marks are drawn, never computed.** The runtime computes stale and
out-of-order and sends them on cell-state events; the shell draws them and
offers the two controls. The frontend never derives a mark from the graph on
its own, because a mark computed in two places would disagree in exactly the
cases that matter. The same rule holds for kernel state and bindings: the
store slice is written from events and responses only, and a command is shown
as taken effect when its event arrives.

**The pause opens the tab.** The interactive prompt event today opens a
modal that looks up a panel in a frontend registry and hands it confirm and
cancel. The event now opens an Explore tab in pause mode: the same host mounts
the block's panel over the run's inputs, the toolbar carries confirm and
cancel, and the notebook pane is absent. Confirm and cancel send the messages
the modal sent, so the backend's interactive path is unchanged. The modal and
its registry are deleted, and the resolution of the panel is the backend's,
by block name, as the panel-contract spec specifies. A control on the pause
toolbar opens a notebook over the same inputs, which is a session open like
any other; the paused block goes on waiting.

**Packaging is a report and a button.** The check request returns the slice
and the ports or the refusals; the shell renders it and enables confirm only
when there are none. The packaged event refreshes the palette, and the
packaged node's badge and double-click are what let the person come back.

**The graph view is a second consumer of one event.** The analysis event
carries version nodes and edges with origins; the view renders them with the
graph library the canvas already uses, highlights the marked cells, and lets
a region be selected. Selection has no consumer in this spec beyond
highlighting; ADR-054 §4.5's subgraph operation is a later spec's.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `docs/specs/adr-054-explore-frontend.md` | create | This spec. |
| `frontend/src/store/types.ts` | modify | The Explore tab member and its slice types (FR-001, FR-033). |
| `frontend/src/store/exploreSlice.ts` | create | Session state written from events and responses (FR-033, FR-034). |
| `frontend/src/types/api.ts` | modify | Session API request and response shapes; session event payloads. |
| `frontend/src/types/ui.ts` | modify | Pause-mode and shell state enumerations. |
| `frontend/src/App.parts/ProjectWorkspace.tsx` | modify | The centre branch and the right-column condition for an Explore tab (FR-005, FR-006). |
| `frontend/src/explore/ExploreTab.tsx` | create | The tab's layout: toolbar, strip, panel slots, notebook pane, pause mode (FR-005 to FR-007, FR-024 to FR-027). |
| `frontend/src/explore/NotebookShell.tsx` | create | The cell list with virtualised editors (FR-008 to FR-010, FR-017). |
| `frontend/src/explore/CellEditor.tsx` | create | One Monaco editor per visible cell; static fallback (FR-008). |
| `frontend/src/explore/OutputRenderer.tsx` | create | MIME bundle rendering (FR-011). |
| `frontend/src/explore/CellMarks.tsx` | create | The three marks and the run-with-upstream control (FR-012, FR-013). |
| `frontend/src/explore/SessionToolbar.tsx` | create | Run-stale, interrupt, restart, commit, package, notebook toggle, kernel list, confirm and cancel in pause mode (FR-013 to FR-016, FR-024 to FR-028). |
| `frontend/src/explore/VariableStrip.tsx` | create | Bindings with type, greyed and live states, pinning (FR-018 to FR-020). |
| `frontend/src/explore/PanelSlots.tsx` | create | Mounted panel hosts, refresh on changed names, submission freeze (FR-019, FR-021 to FR-023). |
| `frontend/src/explore/PackagingReport.tsx` | create | The check report and confirm (FR-028). |
| `frontend/src/explore/GraphView.tsx` | create | The secondary view (FR-032). |
| `frontend/src/hooks/useWebSocket.parts/dispatchEvent.ts` | modify | Session event types routed to the slice; interactive prompt routed to the Explore tab (FR-024, FR-033). |
| `frontend/src/App.parts/InteractiveModals.tsx` | delete | Retired by FR-024. |
| `frontend/src/App.parts/InteractiveModals.parts/**` | delete | Retired by FR-024; the loader is already superseded by the panel-contract spec. |
| `frontend/src/App.tsx` | modify | Stops mounting the modal. |
| `frontend/src/components/WorkflowCanvas.tsx` | modify | Node context menu (FR-003). |
| `frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.ts` | modify | Context-menu handler; double-click recognises a packaged node (FR-002 to FR-004). |
| `frontend/src/components/nodes/BlockNode.tsx` | modify | The notebook badge (FR-030). |
| `frontend/src/components/ProjectTree.tsx`, `ProjectTree.parts/**` | modify | File context menu with the explore action (FR-002, FR-003). |
| `frontend/src/components/BlockPalette.tsx`, `BlockPalette.parts/**` | modify | The insert-call action on a card while an Explore tab is active; refresh on the packaged event (FR-029, FR-031). |
| `frontend/src/components/DataPreview.tsx` | modify | Not rendered while an Explore tab is active (FR-005). |
| `frontend/e2e/specs/adr054-explore.spec.ts` | create | The end-to-end scenario (FR-036). |

### 4.3 Implementation Sequence

| Task | Title | Story | Depends on | Verification |
|---|---|---|---|---|
| T-001 | Add the Explore tab member, the slice, the API types, and the event routing | US1 | — | Slice updates from every event type; tab persists and restores |
| T-002 | Render the layout: centre branch, right-column swap, toolbar skeleton | US1 | T-001 | Right pane shows the shell and hides the preview; left and bottom unchanged |
| T-003 | Add the node and file context menus and the packaged-node double-click | US1, US5 | T-001 | Actions open the tab; disabled with a reason when no outputs |
| T-004 | Build the notebook shell with virtualised Monaco cells and markdown cells | US2 | T-002 | Only visible cells carry editors; drafts survive swaps |
| T-005 | Build the output renderer for the MIME bundle | US2 | T-004 | Each supported type renders from fixtures; unknown falls back |
| T-006 | Render the marks and wire run-stale and run-with-upstream | US2 | T-004 | Marks and reasons render; controls send exactly their command |
| T-007 | Wire cell commands, enable toggle, interrupt, restart, and the reload reconciliation | US2 | T-004 | Each command reaches the API; conflicting drafts are marked |
| T-008 | Build the variable strip and panel slots on the panel host | US3 | T-002 | Greyed until live; pinned outputs; producing request by type |
| T-009 | Wire emission, refusal, changed-names refresh, and the submission freeze | US3 | T-008 | Accepted emission inserts a queued cell; refusal names the panel; only bound panels refresh |
| T-010 | Route the interactive prompt to a pause-mode tab; delete the modal | US4 | T-008 | Same messages as the modal; the modal files are gone |
| T-011 | Add the notebook control on a pause tab and the packaged-ask prompt | US4 | T-010 | A session opens over the paused inputs; confirm sends a commit |
| T-012 | Build the packaging report, the packaged event handling, and the node badge | US5 | T-006 | Clean report enables confirm; refusals disable it; palette refreshes; badge renders |
| T-013 | Build the kernel list and the kernel-state presentation | US6 | T-002 | Every kernel listed with memory; end sends the command; retirement offers restart |
| T-014 | Build the graph view | US6 | T-006 | Version nodes and edges render; marked cells highlighted; region selectable |
| T-015 | Add the palette card's insert-call action | US6 | T-004 | A call cell is inserted after the current cell |
| T-016 | Write the end-to-end scenario | US1 to US5 | T-012 | The scenario of FR-036 passes against a running backend |

### 4.4 Verification Plan

Unit tests use the existing toolchain and render each component against a
scripted slice: the shell against notebooks of various sizes to prove editor
virtualisation and draft preservation; the output renderer against a fixture
of every supported MIME type; the marks against cell-state events; the strip
and the slots against bindings and changed-names events; the toolbar against
kernel states; the pause tab against an interactive prompt event, asserting
that confirm and cancel send the messages the modal sent. The dispatch test
proves every session event reaches the slice and that the interactive prompt
no longer reaches a modal.

The end-to-end scenario runs against a real backend with a fixture project:
open a session from a block, run the first cell, open a panel from the strip,
emit a cell from a stub panel, observe the stale mark, run the stale set, and
package; then reopen the packaged block by double-click. It exists because the
pieces this spec assembles are proven individually elsewhere and the failure
this spec can introduce is between them.

Lint, type, and format checks run as usual. The frontend build must succeed
with the modal deleted, which is what proves nothing else imported it.

### 4.5 Risks And Rollback

**Editor cost.** A Monaco instance per cell without virtualisation would make
a long notebook unusable. Virtualisation is in the first shell task and the
unit test proves that only visible cells carry editors.

**Two sources of truth for marks.** A frontend that recomputed marks from the
graph would disagree with the runtime in exactly the ambiguous cases. FR-034
forbids it, and the slice is written only from events and responses.

**The modal's retirement.** Every existing interactive block is presented
through the pause tab after this change. Its confirm and cancel send the
messages the modal sent, so the backend path is untouched; the risk is
confined to presentation, and the pause-tab tests cover both built-in
interactive panels.

**Events out of order.** A cell-state event may arrive before the response to
the command that caused it. The slice applies events idempotently by cell id
and state, so order does not matter.

**Rollback.** The explore directory, the slice, and the route changes can be
removed as a unit; the modal deletion is the one change that cannot be
reverted by removal alone and is restored from history if the pause tab has
to be withdrawn.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: Right-clicking a block with outputs opens an Explore tab whose
  right pane renders the notebook, whose centre renders the strip and the
  toolbar, and whose left and bottom panes are unchanged. Measured by unit
  test and by the end-to-end scenario.
- **SC-002**: A notebook of two hundred cells mounts editors only for visible
  cells and preserves a draft through a scroll that unmounts its editor.
  Measured by unit test.
- **SC-003**: Every supported output MIME type renders from a fixture, and an
  error renders its traceback with colour. Measured by unit test.
- **SC-004**: Stale and out-of-order marks render with their reasons, and
  the two controls send exactly run-stale and run-with-upstream. Measured by
  unit test.
- **SC-005**: A greyed name cannot be opened; a live name opens a panel with
  the producing request; a declared output pins itself. Measured by unit
  test.
- **SC-006**: An accepted emission inserts a queued cell after the current
  cell; a refused one inserts nothing and names the panel. Measured by unit
  test.
- **SC-007**: Only panels bound to changed names refresh. Measured by unit
  test.
- **SC-008**: An interactive prompt opens a pause-mode Explore tab, confirm
  and cancel send the modal's messages, and the modal component does not
  exist. Measured by unit test and by the build.
- **SC-009**: A packaged block set to ask opens its notebook in the pause
  tab and confirm sends a commit. Measured by unit test.
- **SC-010**: The packaging report enables confirm only for a clean notebook,
  the palette refreshes on the packaged event, and the packaged node carries
  the badge and opens by double-click. Measured by unit test.
- **SC-011**: The kernel list shows every kernel with memory and ends one on
  request. Measured by unit test.
- **SC-012**: The graph view renders version nodes and edges and highlights
  marked cells. Measured by unit test.
- **SC-013**: No frontend code opens a WebSocket or HTTP connection to a
  kernel. Measured by inspection of the network layer and by the absence of
  any kernel URL in the frontend.
- **SC-014**: The end-to-end scenario of FR-036 passes. Measured by the
  scenario.

## 6. Assumptions

- **A-001**: The layout is left unchanged, centre panels, right notebook,
  bottom unchanged, with the data preview absent while the tab is active.
  _Source: owner._
- **A-002**: The cell editor is Monaco, one instance per visible cell, and no
  notebook library is introduced. _Source: owner._
- **A-003**: Variables reach panels through the strip, and declared outputs
  pin themselves. _Source: owner._
- **A-004**: Nothing runs on open; a name whose object does not exist is
  greyed. _Source: owner._
- **A-005**: The kernel list is a collapsible list on the toolbar rather than
  a bottom-panel tab. _Source: owner._
- **A-006**: The interactive-block modal is retired and every interaction
  opens the Explore tab. _Source: owner._
- **A-007**: The session API and events are as the explore-session spec
  defines them, and the panel host and capability-aware resolution are as
  the panel-contract spec defines them; this spec introduces no backend
  behaviour. _Source: spec._
- **A-008**: The graph library already in the bundle draws the graph view.
  _Source: owner._
- **A-009**: The subgraph operation of ADR-054 §4.5 is not built here; the
  graph view lets a region be selected and does nothing with the selection
  yet. _Source: inferred._
- **A-010**: The end-to-end toolchain is the one the repository already uses,
  with its spec directory. _Source: existing-system._
