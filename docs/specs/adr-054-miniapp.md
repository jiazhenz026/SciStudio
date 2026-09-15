---
spec_id: adr-054-miniapp
title: "ADR-054 Spec — Panel Python And MiniApps"
status: Draft
feature_branch: docs/2341-adr-054-miniapp
created: 2026-09-11
input: "Owner request (issue #2341, 2026-09-11 design session): specify ADR-054 §10 and §11 — a panel may carry its own Python (`panel.py`), started as a resident subprocess only where a context provides the `call` operation, and the `miniapp` context built on it: MiniApps, small exploration apps the agent writes on request. Owner decisions: hand-written HTML plus Python, no app framework; preview and interactive contexts keep today's limits; a MiniApp leaves only itself; it declares one data type and the user picks the data when opening it; four entries (a MiniApps tab replacing the Previewers tab, whose list moves behind an All Previewers button in the preview column; New MiniApp in the toolbar New menu; a block context menu; the AI chat with a skill and tools); submitting the create dialog opens a template page at once while the agent fills it in; a MiniApp opens as a centre tab and the preview column collapses; four tiers with Promote to My Library in a hover popover; Convert to interactive block is done by an agent; the introduction lives in the tips card; the name is MiniApp."
owners:
  - "@jiazhenz026"
related_adrs:
  - 54
  - 17
  - 22
  - 39
  - 41
  - 51
  - 53
  - 55
related_specs:
  - adr-054-panels
  - adr-051-interactive-blocks
  - adr-053-personal-tool-library
  - adr-055-enterprise-support
scope:
  in:
    - "Panel Python: `panel.py` detection, the `call` operation, the resident subprocess (launch, protocol, registry handle, lifecycle, crash handling, memory display), and the call route."
    - "The `miniapp` context: descriptor rule, context opening from a panel id and a target, and the SDK `call`."
    - "The MiniApp tab kind, the collapsing preview column, the tab toolbar, and reload on file change."
    - "Creating a MiniApp: the create dialog, the create route, the template, the brief, and the agent session."
    - "The MiniApp skill, the `validate_panel` and `open_miniapp` agent tools, and the realtime event that opens a MiniApp tab."
    - "The MiniApps sidebar tab replacing the Previewers tab, its cards and hover popover, and the All Previewers button in the preview column."
    - "Opening a MiniApp on data: the target picker, the block context menu on the canvas, and New MiniApp in the toolbar New menu."
    - "Promoting a project MiniApp directory to the user library."
    - "Convert to interactive block: its dialog and agent session."
    - "MiniApp tips in the tips card."
    - "The two tutorial steps that route to the Previewers tab: their route follows the list to the All Previewers button, and one sentence of copy changes."
  out:
    - "Python for preview and interactive panels (ADR-054 §10; tracked in #2288)."
    - "Any change to the ADR-051 runtime, the pause, or interaction memory."
    - "Lineage records or typed data objects for what a MiniApp computes (ADR-054 §11.1)."
    - "Reserving memory for MiniApp processes; ADR-022's resource manager reserves memory for no process today (ADR-054 §12; tracked in #2288)."
    - "App frameworks such as Streamlit or Gradio (ADR-054 §16)."
    - "Editing a MiniApp's source inside the application other than through the agent (tracked in #2288)."
    - "Mechanical conversion of a MiniApp into a block (ADR-054 §11.5)."
    - "Directory promotion through the agent's `promote_to_user_library` tool, and ADR-053's canvas promotion entry on the new block context menu (tracked in #2288)."
governs:
  modules:
    - scistudio.panels
  contracts: []
  entry_points: []
  files:
    - src/scistudio/ai/agent/mcp/tools_panels.py
    - src/scistudio/_skills/scistudio/scistudio-write-miniapp/SKILL.md
    - frontend/src/miniapps/**
    - src/scistudio/panels/**
    - src/scistudio/api/routes/panels.py
    - frontend/src/panels/**
    - docs/specs/adr-054-miniapp.md
    - src/scistudio/engine/runners/process_handle.py
    - src/scistudio/api/ws.py
    - src/scistudio/api/routes/user_library.py
    - src/scistudio/agent_provisioning/skills.py
    - frontend/src/App.parts/ProjectWorkspace.tsx
    - frontend/src/store/types.ts
    - frontend/src/components/ActivityBar.tsx
    - frontend/src/components/PreviewerPalette.tsx
    - frontend/src/components/DataPreview.tsx
    - frontend/src/components/Toolbar.parts/FileOperationsGroup.tsx
    - frontend/src/components/WorkflowCanvas.tsx
    - frontend/src/components/palette/tips/tipPool.ts
    - frontend/src/components/promotion/promotable.ts
    - frontend/src/hooks/useWebSocket.parts/dispatchEvent.ts
    - frontend/src/components/LearningCenter.parts/targets.ts
    - src/scistudio/tutorials/core/welcome-to-scistudio/tutorial.yaml
    - src/scistudio/tutorials/core/what-is-a-type/tutorial.yaml
    - docs/specs/adr-053-learning-center.md
    - frontend/src/types/api.ts
    - src/scistudio/api/schemas.py
    - src/scistudio/api/routes/projects.py
    - src/scistudio/ai/agent/mcp/__init__.py
  excludes: []
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - tests/panels/test_panel_python_detection.py
  - tests/panels/test_panel_process.py
  - tests/panels/test_miniapp_context.py
  - tests/api/test_panel_call_route.py
  - tests/api/test_miniapp_create.py
  - tests/api/test_user_library_panel_promotion.py
  - tests/ai/test_mcp_panels_tools.py
  - tests/agent_provisioning/test_skills.py
  - frontend/src/miniapps/MiniAppTab.test.tsx
  - frontend/src/miniapps/MiniAppPalette.test.tsx
  - frontend/src/miniapps/CreateMiniAppDialog.test.tsx
  - frontend/src/components/WorkflowCanvas.test.tsx
acceptance_source: adr
language_source: en
---

# ADR-054 Spec — Panel Python And MiniApps

## 1. Change Summary

This spec implements ADR-054 §10 and §11. It came from a manual owner request
tracked as issue #2341, and it is the second specification of ADR-054, beside
`adr-054-panels`, which specifies the panel mechanism, the core migration, and the
authoring docs as Phases A, B, and C. This spec is **Phase D**, coordinated with
the other phases under #2296 and tracked with them in #2288. It depends on
Phase A — the panel descriptor and discovery, the context service, the sandboxed
frame and its channel, the SDK, and the token-scoped file routes — and on nothing
in Phases B and C.

It delivers two things. The first is a capability of every panel: a panel may
carry `panel.py`, which the host starts as a resident subprocess only in a
context that provides the `call` operation, and which the page calls by function
name through the host. The `preview` and `interactive` contexts do not provide
`call`; their behaviour does not change. The second is the `miniapp` context and
the feature built on it: **MiniApps**, small exploration apps the agent writes for
a user on request, opened on a block's output in a centre tab.

| Part | Delivers |
|---|---|
| Panel Python | `panel.py`, the `call` operation, the resident process and its lifecycle, the call route |
| The `miniapp` context | Descriptor rule, context opening, SDK `call` |
| Workspace | MiniApp tab kind, collapsing preview column, reload on change, target picker |
| Entries | MiniApps tab (replacing the Previewers tab), All Previewers button, New MiniApp in the New menu, the block context menu, the create dialog and template, the agent skill and tools, tips |
| Library and workflow | Directory promotion; Convert to interactive block |

What does not change: the ADR-051 runtime, its pause, and its window; the
`preview` and `interactive` contexts; the routing ladder; and the previewer list,
which moves behind a button but keeps its content and controls.

## 2. User Scenarios & Testing

### User Story 1 - A user creates a MiniApp from a block and watches it appear (Priority: P1)

A scientist right-clicks a segmentation block whose output is an `Image`, chooses
New MiniApp, types "let me drag a threshold across the stack and see the mask",
and submits. A tab opens at once with a page explaining that a MiniApp is being
built; the agent works in the AI tab below, and the tab reloads as files appear
until the threshold explorer is there.

**Why this priority**: This is the feature's main path and the answer to users not
knowing the agent can build a tool.

**Independent Test**: With a fake agent provider that writes a fixed MiniApp
directory after a delay, submit the dialog from a block's context menu and assert
the template tab mounts before the agent writes, the directory exists with the
template files, the session opens in the AI tab, and the tab reloads to the final
page.

**Acceptance Scenarios**:

1. **Given** a block whose latest successful run produced an `Image`, **When** the
   user right-clicks it and chooses New MiniApp, **Then** the dialog opens with
   that block's output pre-filled.
2. **Given** the dialog is submitted, **When** the route returns, **Then**
   `<project>/panels/<id>/` exists with the template `panel.json`, `index.html`,
   and `panel.py`, and a MiniApp tab shows the template page on the chosen output.
3. **Given** the template tab is open, **When** the agent rewrites `index.html`,
   **Then** the tab reloads within two seconds.
4. **Given** no working agent is configured, **When** the user submits, **Then** no
   directory is created and the dialog shows the graded availability reason of
   ADR-053 §5.2.

### User Story 2 - A MiniApp page calls its own Python (Priority: P1)

The threshold explorer's page calls `scistudio.call("threshold", {z: 12, t: 0.4})`
whenever a slider moves, and its `panel.py` answers from the stack it loaded once.

**Why this priority**: `call` and the resident process are what make a MiniApp more
than a preview.

**Independent Test**: Open a fixture MiniApp whose `panel.py` counts `setup` calls
and returns arrays; call it repeatedly and assert `setup` ran once, results arrive
as JSON and as binary arrays, and closing the tab ends the process.

**Acceptance Scenarios**:

1. **Given** a MiniApp with `panel.py`, **When** its tab opens, **Then** one process
   starts, is registered in the process registry, and receives the target through
   `setup(data)`.
2. **Given** a call to a function that returns a NumPy array, **When** it
   completes, **Then** the page receives an `ArrayBuffer` with dtype and shape.
3. **Given** a function that raises, **When** it is called, **Then** the page
   receives an error with the exception type and message, and the process keeps
   running.
4. **Given** the tab is closed, **When** ten seconds have passed, **Then** no
   process from the MiniApp's process tree is alive.

### User Story 3 - Preview and interactive panels never run Python (Priority: P1)

A package ships a panel that declares `preview` and `miniapp` and carries
`panel.py`.

**Why this priority**: ADR-054 §10 keeps previewers read-only and interactive
windows self-contained; this is the guarantee.

**Independent Test**: Mount the fixture as a preview and as a MiniApp; assert the
preview starts no process and has no `call`, and the MiniApp starts one.

**Acceptance Scenarios**:

1. **Given** the panel is mounted as a preview, **When** the page looks for
   `scistudio.call`, **Then** it is undefined, a raw `call` message is answered
   `unsupported`, and no process is started.
2. **Given** an interactive panel with `panel.py`, **When** its block pauses,
   **Then** no process is started.

### User Story 4 - The user asks in chat and the agent builds and opens a MiniApp (Priority: P2)

A user who has never opened the MiniApps tab asks the agent: "can I compare the
peak tables of these two runs side by side and click through the differences?"
The agent, following the MiniApp skill, offers a MiniApp, writes it, validates it,
and opens it.

**Why this priority**: The chat reaches users who never find the tab.

**Independent Test**: Call `validate_panel` and `open_miniapp` from an MCP test
client against a running backend with a connected frontend test harness; assert
the diagnostics and that the frontend opens a MiniApp tab on the named output.

**Acceptance Scenarios**:

1. **Given** a valid MiniApp directory, **When** the agent calls
   `validate_panel`, **Then** it receives no error diagnostics.
2. **Given** a connected frontend, **When** the agent calls `open_miniapp`,
   **Then** a `panel.open_miniapp` event is broadcast and the frontend opens or
   focuses the MiniApp tab.
3. **Given** no frontend is connected, **When** the agent calls `open_miniapp`,
   **Then** the tool reports that no workspace is open.

### User Story 5 - The MiniApps tab lists, opens, and promotes MiniApps (Priority: P2)

The left sidebar shows MiniApps where it showed Previewers. The previewer list is
one click away in the preview column.

**Why this priority**: The tab is the permanent entry; the previewer list must not
be lost in the move.

**Independent Test**: With MiniApps at the project, user, and package tiers, open
the tab; assert the grouping, the popover, Promote to My Library on project cards
only, and that All Previewers opens today's previewer list.

**Acceptance Scenarios**:

1. **Given** the MiniApps tab, **When** the user hovers a card, **Then** the popover
   shows the description, declared type, and tier, and Promote to My Library only
   for a project MiniApp.
2. **Given** a project MiniApp, **When** the user promotes it, **Then** its
   directory is in the user library, it is gone from the project, and it is still
   listed and opens.
3. **Given** the preview column, **When** the user clicks All Previewers, **Then**
   the list the Previewers tab showed replaces the preview inside the column, with
   its reload action, diagnostics, and per-type choice controls, and a control
   returns to the preview.

### User Story 6 - A MiniApp opens on data of its type (Priority: P2)

The user clicks the threshold explorer's card, or right-clicks a block.

**Why this priority**: Declaring one type is how a MiniApp is reused on other data.

**Independent Test**: With two workflows producing `Image` and one producing a
`DataFrame`, open an `Image` MiniApp from its card and from each block's context
menu; assert the picker offers only `Image` outputs and the menu lists the MiniApp
only on `Image` blocks.

**Acceptance Scenarios**:

1. **Given** a MiniApp declaring `Image`, **When** the user opens it from its card,
   **Then** a picker lists the `Image` outputs of the project's latest successful
   runs, and the MiniApp opens on the chosen one.
2. **Given** a block producing a `DataFrame`, **When** the user right-clicks it,
   **Then** the menu offers New MiniApp and no `Image` MiniApp.
3. **Given** a MiniApp tab is active, **When** the user switches to a workflow tab,
   **Then** the MiniApp tab stays open, its process keeps running, and the preview
   column returns to its width.

### User Story 7 - A faulty panel.py cannot take the application down (Priority: P2)

An agent's first attempt at `panel.py` loops forever in `setup`, or crashes.

**Why this priority**: Most `panel.py` files are written by agents (ADR-054 §10).

**Independent Test**: Open fixtures whose `panel.py` hangs, crashes, spawns a child
process, and prints to stdout; assert the API stays responsive, the tab shows each
state, Restart works, and closing kills the child.

**Acceptance Scenarios**:

1. **Given** `setup` never returns, **When** the startup limit passes, **Then** the
   tab shows that the MiniApp did not start, with Restart and Stop.
2. **Given** the process crashes, **When** the page calls, **Then** the call fails
   with `process_exited` and the tab shows the exit code and the last lines of the
   log.
3. **Given** `panel.py` prints to stdout, **When** it is called, **Then** the output
   goes to the MiniApp's log and the call protocol is unaffected.
4. **Given** a MiniApp is open, **When** the browser is reloaded or closed,
   **Then** its context closes and its process ends after the grace period.

### User Story 8 - A MiniApp becomes an interactive block (Priority: P3)

The scientist settled on a threshold and wants the workflow to ask for it every
run. They choose Convert to interactive block in the MiniApp tab.

**Why this priority**: The path from exploration to a workflow step; it depends on
everything above.

**Independent Test**: With a fake agent provider, submit the conversion dialog and
assert a session starts with a brief naming the MiniApp directory, the requested
outputs, and the ADR-051 contract, and that the MiniApp directory is unchanged.

**Acceptance Scenarios**:

1. **Given** a MiniApp tab, **When** the user chooses Convert to interactive block
   and names one `Mask` output, **Then** an agent session opens whose brief names
   that output and instructs `prepare_prompt`, one decision, and `run`.

### Edge Cases

- The chosen output was produced by a run that artifact retention has since
  reclaimed (#1983): the target no longer resolves; the tab shows that the data is
  gone and offers the picker.
- The same MiniApp is opened twice on the same output: the existing tab is
  focused. On different outputs: two tabs and two processes.
- The project closes or switches while MiniApp tabs are open: every MiniApp
  context closes and every process ends.
- The agent session fails to start after the directory was created: the template
  remains, the tab says the agent did not start, and the error is shown.
- The agent changes `contexts` or `types` in `panel.json`: validation reports it,
  and a MiniApp whose `types` no longer matches its open target is closed with a
  message.
- A MiniApp's `panel.py` imports a package that is not installed: `setup` fails,
  and the tab shows the import error and suggests installing it as for a block.
- A MiniApp id already exists at the project tier: the create route picks the next
  free id.
- A project MiniApp is promoted while its tab is open: the tab closes its context
  and reopens from the user tier.
- A package MiniApp shadows nothing and cannot be promoted; a project MiniApp with
  the id of a user MiniApp shadows it, as any panel does.
- The preview column had been collapsed by the user before a MiniApp tab opened:
  it stays collapsed after the MiniApp tab is left.
- `panel.py` exists in a panel that declares no context providing `call`: an
  informational diagnostic; nothing runs.
- A browser deployment has no native dialog: `save` downloads, as for every panel.

## 3. Requirements

### Functional Requirements

**Descriptor and context**

- **FR-001**: `panel.json` `contexts` MUST accept `miniapp`, extending
  `adr-054-panels` FR-002. A panel declaring `miniapp` MUST declare `types` with
  exactly one entry, a registered type name or `Collection[<type>]`. Preview
  routing MUST ignore `types` for the `miniapp` context.
- **FR-002**: A panel MAY contain `panel.py` at its root. Discovery MUST record
  whether it is present, and MUST add an informational diagnostic when it is
  present in a panel that declares no context providing `call`. Its presence MUST
  NOT change the operations any context provides.
- **FR-003**: The `preview` and `interactive` contexts MUST NOT provide `call` and
  MUST NOT start `panel.py`. The SDK MUST NOT define `call` there, and the host and
  the backend MUST answer a `call` on such a context with `unsupported`.
- **FR-004**: `POST /api/panels/contexts` MUST open a `miniapp` context from
  `{panel_id, source}`, where `source` is `{workflow_id, block_id, port}`. The
  backend MUST resolve it to the output reference of that block's latest
  successful run — a preview target as in `adr-054-panels` FR-009 — and MUST
  refuse a source with no such output, or whose type is neither the MiniApp's
  declared type nor a subtype of it. Context ids MUST be random, with at least 128
  bits. The context
  MUST authorize the target and its slots or items as a preview context does, and
  MUST provide `read`, `call`, and `save`, and neither `writeBack` nor `open`.
- **FR-005**: The `init` message of a `miniapp` context MUST carry the target
  reference, its type, and the MiniApp's id and name.

**The panel process**

- **FR-006**: Opening a context that provides `call` for a panel with `panel.py`
  MUST start one subprocess, off the API event loop, using the interpreter the
  local runner uses for block workers, with the project directory as its working
  directory, the runtime import roots blocks receive, the panel directory on its
  import path, and `PYTHONDONTWRITEBYTECODE=1`, so that importing `panel.py` writes
  nothing into the panel directory.
- **FR-007**: The subprocess MUST import `panel.py`, then call `setup(data)` if the
  module defines it, where `data` is the target reconstructed as a SciStudio data
  object by the engine's own reconstruction from its storage reference. Callable
  functions are the functions defined in `panel.py` itself — whose `__module__` is
  `panel.py`'s module — with names not starting with `_`, other than `setup` and
  `teardown`. A name `panel.py` only imports MUST NOT be callable.
- **FR-008**: The subprocess MUST be registered in the application's process
  registry — the instance the agent's `run_command` registers in and whose
  `terminate_all` runs at shutdown (`app.state.registry`), not the block runtime's
  own registry — under the namespace `panel-context` with the key `context-<context_id>`,
  through a handle that ends the whole process tree — a process group on POSIX and
  a Job Object on Windows, as the agent's `run_command` does — and MUST be
  deregistered when it exits.
- **FR-009**: The backend and the subprocess MUST exchange length-prefixed messages
  over a dedicated pipe that user code's `print` cannot write to; the subprocess
  MUST NOT listen on a network port. Its stdout and stderr MUST go to a per-context
  log under `<project>/.scistudio/panels/logs/`. The subprocess MUST exit when the
  pipe from the backend closes, so it cannot outlive a backend that died.
- **FR-010**: `POST /api/panels/contexts/{context_id}/call` MUST accept
  `{fn, args}` with `args` a JSON object, MUST refuse an unknown or closed context
  or one that does not provide `call`, and MUST forward the call to the process.
  It MUST return `{result}` as JSON, or `application/octet-stream` with dtype and
  shape headers when the function returns a NumPy array, as `adr-054-panels`
  FR-012 does for reads. The route MUST authenticate as the read route does and is
  subject to the opaque-origin refusal of `adr-054-panels` FR-030 and the
  application's CORS rules.
- **FR-011**: Calls on one context MUST run one at a time, in order, with at most
  16 waiting; a call beyond that MUST fail at once with `busy`. A call MUST fail
  with `timeout` after a configurable limit (60 seconds by default); the process is
  then marked `unresponsive`, later calls fail with `busy` until the running call
  returns, and the tab offers Restart. A result larger than a configurable limit
  (64 MiB by default) MUST fail with `too_large`. An exception in a function MUST
  return `{error: {type, message, traceback}}` and MUST NOT end the process.
- **FR-012**: `setup` MUST complete within a configurable startup limit (120
  seconds by default); otherwise the context MUST report `start_failed` and offer
  Restart and Stop.
- **FR-013**: The process MUST end when its context closes — its tab closes, its
  project closes or switches, SciStudio shuts down, or the workspace connection
  that opened it is gone — by calling `teardown()`
  when defined, then terminating with a five-second grace period, then killing the
  process tree. Shutdown MUST include MiniApp processes in the registry's
  `terminate_all`. A `miniapp` context MUST be bound to the realtime (`/ws`) client
  of the workspace that opened it and MUST close once that client has been
  disconnected for a grace period (30 seconds by default), debounced as the
  cancellation of browser-owned runs is in `src/scistudio/api/ws.py`.
- **FR-014**: If the process exits unexpectedly, pending and later calls MUST fail
  with `process_exited`, and the host MUST show the exit code and the last lines of
  the log with Restart. Restart MUST start a new process for the same context and
  target.
- **FR-015**: The host MUST show the process state — starting, running,
  unresponsive, stopped, crashed — refreshed at least every five seconds. The
  normal MiniApp interface MUST NOT display resident-memory figures or binary
  memory units. Runtime memory measurements remain available for diagnostics
  through the process API. This presentation requirement follows the owner
  directive in the guided #2354 session.
- **FR-016**: The SDK MUST expose `call(fn, args)`, returning a promise, only where
  the context provides `call`; the panel-to-host message types of `adr-054-panels`
  FR-016 gain `call`.
- **FR-017**: `.py` files MUST NOT be served by the token-scoped asset route, so a
  page cannot read `panel.py` or any other panel's Python.

**The MiniApp tab**

- **FR-018**: The store's tab union MUST gain a `miniapp` tab kind carrying the
  panel id, the source `{workflow_id, block_id, port}`, and a display name, with
  the id `miniapp:<panel_id>:<workflow_id>:<block_id>:<port>`; opening an existing
  id MUST focus it.
- **FR-019**: A MiniApp tab MUST stay open when another tab becomes active, MUST
  NOT be persisted across restarts, and closing it MUST close its context.
- **FR-020**: When a MiniApp tab becomes active the right preview column MUST
  collapse, and when a tab of another kind becomes active the column MUST return to
  the size it had before; a column the user had already collapsed stays collapsed.
  The user MAY drag the column open while the MiniApp is active. The AI-host
  presentation, which has no right column and shows the preview as a sidebar
  card, collapses nothing.
- **FR-021**: The tab toolbar MUST carry the process state and memory, Restart,
  Stop, and Convert to interactive block (FR-036).
- **FR-022**: For MiniApps at the project and user tiers, the backend MUST watch
  the panel directory of each open `miniapp` context — separately from the
  project file watcher, which reports neither page file types nor the user tier —
  and emit a `panel.files_changed` event with the panel id, added to the outbound
  events of `src/scistudio/api/ws.py`; the host MUST then reload the MiniApp — a
  new frame, context, and process on the same source — debounced by 500
  milliseconds.
  Only `panel.json`, `panel.py`, and files of the page types the token route
  serves count; `__pycache__/` and every other file are ignored, so what
  `panel.py` writes into its own directory never triggers a reload.

**Creating a MiniApp**

- **FR-023**: New MiniApp — from the MiniApps tab, the toolbar New menu, and a
  block's context menu — MUST open one dialog that asks for the data (a block
  output in the open project, pre-filled from the context menu) and for what the
  user wants to see or do, and offers the agent provider and permission mode as
  "Bring in my work" does.
- **FR-024**: `POST /api/panels/miniapps` MUST first check the chosen provider with
  the graded availability of `GET /api/ai/availability` — which the dialog SHOULD
  fetch when it opens, so that a slow first check does not delay the submit — and
  MUST create nothing when it reports that a session cannot start. It MUST then create `<project>/panels/<id>/` from the
  MiniApp template — `panel.json` with `contexts: ["miniapp"]`, `types` set to the
  chosen output's type, a name, and the request as `description`; the template
  `index.html`; and a `panel.py` whose `setup` does nothing — choosing the next free
  id when one exists. It MUST write a brief to
  `<project>/.scistudio/miniapps/<timestamp>-<hex>.md`, open the agent session
  through the pre-spawned session path "Bring in my work" uses, and return the panel
  id, the target, and the session's tab id.
- **FR-025**: The frontend MUST open the MiniApp tab on the chosen target as soon as
  the create route returns, before the agent has written anything, and MUST show
  the agent session in the bottom AI tab.
- **FR-026**: The template page MUST say in plain words what a MiniApp is, repeat
  the user's request, and say that the agent is writing it in the AI tab; it MUST
  render when `panel.py` does nothing. Its copy is reviewed by the owner.
- **FR-027**: The brief MUST tell the agent to follow the MiniApp skill, to write
  only inside the created directory unless the user asks otherwise, to keep the
  `id`, `contexts`, and `types` it was given, and to run `validate_panel` before
  finishing.

**The agent's skill and tools**

- **FR-028**: A new skill `src/scistudio/_skills/scistudio/scistudio-write-miniapp/SKILL.md`
  MUST be added to the provisioned skill names in
  `src/scistudio/agent_provisioning/skills.py`. It MUST teach the MiniApp form —
  `panel.json`, the page, the SDK's `read`, `call`, and `save`, and `panel.py` with
  `setup` and its functions — the frame's limits, the local library set and the CDN
  allowlist, validation, and opening; and it MUST tell the agent to offer a MiniApp
  when a user wants to look at, compare, or tune something interactively on
  project data rather than get a single answer or a workflow step.
- **FR-029**: `src/scistudio/ai/agent/mcp/tools_panels.py` MUST add two tools:
  `validate_panel(path)`, a read tool returning the discovery diagnostics for a
  panel directory, and `open_miniapp(panel_id, workflow_id, block_id, port)`, a
  write tool that asks the workspace to open a MiniApp tab on that output.
- **FR-030**: `open_miniapp` MUST emit a `panel.open_miniapp` event carrying the
  panel id and target, added to the outbound events of `src/scistudio/api/ws.py`;
  the frontend dispatcher MUST open or focus the MiniApp tab. With no frontend
  connected the tool MUST say so instead of reporting success.

**Sidebar, previewer list, and entries**

- **FR-031**: The activity bar's Previewers entry MUST be replaced by a MiniApps
  entry. The MiniApps tab MUST list every panel declaring `miniapp`, grouped by
  tier as the Previewers tab groups previewers, with a search box and a plus-icon New
  button; a card shows the name and declared type, and a single click opens the
  MiniApp (FR-034).
- **FR-032**: Each MiniApp card MUST show the shared hover popover
  (`frontend/src/components/palette/DetailPopover.tsx`) with the description,
  declared type, tier, and directory, and, for a project-tier MiniApp only, Promote
  to My Library (ADR-053 FR-019).
- **FR-033**: The preview column MUST gain an All Previewers button that opens the
  Previewers list unchanged — the same component, with its reload action,
  diagnostics, and per-type choice controls — inside the preview column itself, in
  place of the current preview, with a control that returns to the preview. No
  dialog is opened. Opening the list while the column is collapsed, as the
  tutorial route of FR-040 can, MUST expand the column first. The list keeps the
  Previewers tab's content — legacy previewers and panels declaring `preview`,
  with the discovery diagnostics — while MiniApps are listed in the MiniApps tab
  and panels declaring only `interactive` in neither, as today. In the AI-host
  presentation the button sits in the sidebar's Preview card.
- **FR-034**: Opening a MiniApp from its card MUST ask for a target, listing the
  outputs of the project's workflows whose latest successful run produced data of
  the declared type or a subtype, by workflow, block, and port, as returned by
  `GET /api/panels/miniapps/{panel_id}/sources`. Opening from a
  block's context menu MUST use that block's output, asking only when several ports
  match.
- **FR-035**: Canvas block nodes MUST gain a context menu. For a block with outputs
  from its latest successful run it MUST list the MiniApps whose declared type
  matches an output and New MiniApp; for a block without outputs the entries MUST
  be disabled with the reason. The hover toolbar is unchanged.
- **FR-036**: Convert to interactive block MUST open a dialog asking for the
  block's outputs (a name and type per port), with an optional note for the agent,
  and then start an agent session, which writes the block to the project, whose
  brief names the MiniApp directory, the `scistudio-write-block` skill, the ADR-051
  contract (`prepare_prompt` builds a self-contained view, one decision is written
  back, `run` computes the outputs), and the requested outputs. The MiniApp MUST be
  left unchanged.
- **FR-037**: The toolbar New menu (`frontend/src/components/Toolbar.parts/FileOperationsGroup.tsx`)
  MUST gain New MiniApp, disabled when no project is open.
- **FR-038**: `frontend/src/components/palette/tips/tipPool.ts` MUST gain at least
  one MiniApp tip; its copy is supplied or approved by the owner.

**Promotion**

- **FR-039**: The user-library route MUST accept a panel directory as a promotion
  source and target, moving `<project>/panels/<id>/` to the user tier's
  `panels/<id>/` under ADR-053 FR-017: write the library copy, then remove the
  project copy, degrading to a copy when removal fails. It MUST confine every file
  to both roots, refuse an existing library id unless the user confirms overwrite,
  and share the frontend promotion implementation (ADR-053 FR-025) through a panel
  source in `frontend/src/components/promotion/promotable.ts`.

**Tutorials**

- **FR-040**: The tutorial route target `previewers` MUST open the Previewers list
  in the preview column (FR-033) instead of switching the left sidebar, and the
  highlight target `previewer_palette` MUST resolve to that list, so the
  `where-previewers-live` step of `welcome-to-scistudio` and the
  `save-the-previewer` step of `what-is-a-type` keep their `route_to` and
  `highlight` values and the tutorial vocabulary is unchanged. The
  `welcome-to-scistudio` step keeps its copy. The second line of the
  `save-the-previewer` step MUST change from "In the Previewers tab, find
  **Image** and choose **All projects**." to "In **All Previewers**, find **Image**
  and choose **All projects**." — a light change the owner asked for, in wording
  proposed here for the owner's review. The owner's design comments in both YAML
  files MUST be kept; English comments in them, and the passages of
  `docs/specs/adr-053-learning-center.md` that describe the Previewers tab, MUST be
  updated to the new location. The list stays in the preview column until the user
  returns to the preview and covers no other pane, so later steps that route
  elsewhere are unaffected. This amends the `previewers` route target defined in
  `docs/specs/adr-053-learning-center.md`.

### Key Entities

- **PanelDescriptor** — gains `has_python` (whether `panel.py` is present) and the
  `miniapp` context value.
- **MiniAppContext** — a panel context of kind `miniapp`: context id, panel id,
  source, resolved target, authorized references, operations (`read`, `call`,
  `save`), owning realtime client, process.
- **PanelProcess** — the resident subprocess of one context: context id, pid, state
  (starting, running, unresponsive, stopped, crashed, start_failed), started at, resident memory,
  log path, exit code.
- **CallRequest / CallResult** — `{fn, args}` and `{result}` or
  `{error: {type, message, traceback}}`, or a binary array with dtype and shape.
- **MiniAppTab** — tab kind `miniapp`: id, panel id, source, display name.
- **MiniAppCreateRequest** — project, target (workflow, block, port), request text,
  provider, permission mode.
- **MiniAppBrief** — the file under `<project>/.scistudio/miniapps/` handed to the
  agent session.

## 4. Implementation Plan

### 4.1 Technical Approach

**Backend.** `scistudio.panels` gains a process host: a launcher that starts a
panel's subprocess with the block runtime's interpreter and import roots, a small
bootstrap module that imports `panel.py`, calls `setup`, and serves calls over the
pipe, and a `ProcessHandle` subclass registered in the process registry, modelled
on the agent's command handle. The context service opens `miniapp` contexts
from a block output, starts and stops their processes, watches their panel
directories, and closes them with their tabs, their projects, or the workspace
connection that opened them. The
panels router gains the call route and the create route; the create route reuses
the brief-writing and pre-spawned session path of "Bring in my work". A new MCP
module adds `validate_panel` and `open_miniapp`; `open_miniapp` emits an event on
the event bus, which `api/ws.py` forwards. The user-library route gains a panel
directory target.

**Frontend.** `frontend/src/miniapps/` holds the MiniApps sidebar tab, the create
and target-picker dialogs, the MiniApp tab view with its toolbar, and the
conversion dialog. The tab mounts `PanelFrame` from Phase A with the `miniapp`
context. The workspace gains the new tab kind, the preview column's collapse
behaviour (the right `ResizablePanel` gains a panel ref), and the All Previewers
button; the canvas gains a node context menu; the New menu, the activity bar, the
tips pool, and the promotion model gain their entries.

**Data flow.**

```text
page ══port══▶ host ──POST /api/panels/contexts/{id}/call (session)──▶ backend
                                                                         │ pipe
page ◀══ result ══ host ◀────────── JSON or binary ◀──────────── panel.py process
```

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/panels/**` | create or modify | Descriptor rule, process host and bootstrap, `miniapp` contexts, template |
| `src/scistudio/api/routes/panels.py` | create or modify | Call and create routes |
| `src/scistudio/engine/runners/process_handle.py` | modify | Registry support for panel handles, if the command handle's pattern needs a shared base |
| `src/scistudio/api/ws.py` | modify | `panel.open_miniapp` outbound event |
| `src/scistudio/api/routes/user_library.py` | modify | Panel directory promotion |
| `src/scistudio/ai/agent/mcp/tools_panels.py` | create | `validate_panel`, `open_miniapp` |
| `src/scistudio/ai/agent/mcp/__init__.py` | modify | Register the new tool module |
| `src/scistudio/api/schemas.py`, `frontend/src/types/api.ts` | modify | `UserLibraryTarget` gains panels; MiniApp source and create models |
| `src/scistudio/api/routes/projects.py` | modify | Project path resolution for panel directories |
| `src/scistudio/api/routes/work_import.py`, `src/scistudio/api/routes/ai_pty/engine.py` | modify if shared | Reuse the brief writer and the pre-spawned session path |
| `docs/specs/adr-053-learning-center.md` | modify | Passages that describe the Previewers tab (FR-040) |
| `src/scistudio/_skills/scistudio/scistudio-write-miniapp/SKILL.md` | create | MiniApp skill |
| `src/scistudio/agent_provisioning/skills.py` | modify | Provision the new skill |
| `frontend/src/miniapps/**` | create | Tab, dialogs, sidebar list, conversion |
| `frontend/src/store/types.ts` | modify | `miniapp` tab kind |
| `frontend/src/App.parts/ProjectWorkspace.tsx` | modify | MiniApps tab, preview column collapse |
| `frontend/src/components/ActivityBar.tsx` | modify | MiniApps replaces Previewers |
| `frontend/src/components/PreviewerPalette.tsx`, `frontend/src/components/DataPreview.tsx` | modify | All Previewers button; the list shown inside the preview column |
| `frontend/src/components/WorkflowCanvas.tsx` | modify | Node context menu |
| `frontend/src/components/Toolbar.parts/FileOperationsGroup.tsx` | modify | New MiniApp |
| `frontend/src/components/palette/tips/tipPool.ts` | modify | MiniApp tip |
| `frontend/src/components/promotion/promotable.ts` | modify | Panel promotion source |
| `frontend/src/hooks/useWebSocket.parts/dispatchEvent.ts` | modify | Handle `panel.open_miniapp` |
| `frontend/src/components/LearningCenter.parts/targets.ts` | modify | `previewers` route opens All Previewers |
| `src/scistudio/tutorials/core/what-is-a-type/tutorial.yaml` | modify | One sentence of copy (FR-040) |
| `src/scistudio/tutorials/core/welcome-to-scistudio/tutorial.yaml` | verify | Route and highlight keep working unchanged |
| tests listed in the frontmatter | create or modify | Coverage |

### 4.3 Implementation Sequence

| Task | Title | Story | Files | Depends on | Verification |
|---|---|---|---|---|---|
| T-001 | Descriptor: `miniapp`, one-type rule, `panel.py` detection | US3 | `panels/` | Phase A T-001 | `test_panel_python_detection.py` |
| T-002 | Process host: launcher, bootstrap, pipe protocol, log, registry handle | US2, US7 | `panels/`, `process_handle.py` | T-001 | `test_panel_process.py` |
| T-003 | `miniapp` context, call route, lifecycle and crash handling | US2, US3, US7 | `panels/`, `routes/panels.py` | T-002, Phase A T-005 | `test_miniapp_context.py`, `test_panel_call_route.py` |
| T-004 | SDK `call` and `init` fields | US2 | `panels/sdk/` | T-003, Phase A T-010 | SDK tests |
| T-005 | MiniApp tab kind, toolbar, preview column collapse, reload on change | US1, US2, US6 | `frontend/src/miniapps/`, `store/types.ts`, `ProjectWorkspace.tsx` | T-004, Phase A T-011 | `MiniAppTab.test.tsx` |
| T-006 | Create route, template, brief, session; create dialog | US1 | `routes/panels.py`, `panels/`, `frontend/src/miniapps/` | T-005 | `test_miniapp_create.py`, `CreateMiniAppDialog.test.tsx` |
| T-007 | MiniApp skill and provisioning | US4 | `_skills/`, `agent_provisioning/skills.py` | T-006 | `test_skills.py`; e2e scenario |
| T-008 | `validate_panel`, `open_miniapp`, realtime event and dispatcher | US4 | `tools_panels.py`, `api/ws.py`, `dispatchEvent.ts` | T-005 | `test_mcp_panels_tools.py` |
| T-009 | MiniApps tab, popover, All Previewers button | US5 | `frontend/src/miniapps/`, `ActivityBar.tsx`, `PreviewerPalette.tsx`, `DataPreview.tsx` | T-005 | `MiniAppPalette.test.tsx` |
| T-010 | Target picker, canvas context menu, New menu | US6 | `frontend/src/miniapps/`, `WorkflowCanvas.tsx`, `FileOperationsGroup.tsx` | T-006 | `WorkflowCanvas.test.tsx` |
| T-011 | Panel directory promotion | US5 | `user_library.py`, `promotable.ts` | T-009 | `test_user_library_panel_promotion.py` |
| T-012 | Convert to interactive block | US8 | `frontend/src/miniapps/`, `routes/panels.py` | T-006 | conversion tests |
| T-013 | MiniApp tips | US5 | `tipPool.ts` | T-009 | tip pool tests |
| T-014 | Tutorial route to All Previewers; `save-the-previewer` copy | US5 | `targets.ts`, tutorial YAML | T-009 | tutorial target tests; both tutorials run through |

Phase D lands as one PR, like each of Phases A to C, after Phase A has merged.

### 4.4 Verification Plan

- Backend unit and API tests in the frontmatter, run through `gate_record check`,
  including the process lifecycle on Windows and POSIX runners: startup, calls,
  binary results, errors, timeouts, crash, Restart, Stop, tab close, project
  switch, shutdown, and a `panel.py` that spawns a child.
- A test that the preview and interactive contexts never start a process and never
  expose `call` (US3).
- An API responsiveness test while a `panel.py` hangs and while one crashes (US8).
- Frontend tests for the tab kind, the collapse and restore rule, reload on change,
  the create dialog, the MiniApps tab, the popover, All Previewers, the target
  picker, and the canvas context menu.
- An MCP test for `validate_panel` and `open_miniapp`, with and without a connected
  frontend.
- The tutorial target tests for the `previewers` route and the
  `previewer_palette` highlight, and a run through the two tutorial steps of
  FR-040.
- An e2e scenario under `docs/ai-developer/e2e/` in which a user creates a MiniApp
  from a block with a real agent, watches the template turn into the app, moves a
  control that calls `panel.py`, promotes it, and converts it.

### 4.5 Risks And Rollback

- **Runaway processes.** Each process is registered, killed as a tree, ended with
  its context and at shutdown, and exits when its pipe to the backend closes.
- **Memory.** An open MiniApp holds its data until it is closed and nothing
  reserves memory for it. Memory measurements are available for diagnostics;
  the normal tab shows process state and Stop/Restart controls, without memory figures.
- **Untrusted Python.** `panel.py` runs as the user, like a block (ADR-054 §10);
  the contexts that must stay read-only never start it.
- **Agent dependence.** Nothing is created without a working agent; graded
  availability explains why.
- **Moving the previewer list.** Users who knew the Previewers tab find the list
  behind All Previewers; the tips card and the MiniApps tab's first appearance
  point to it.
- **Rollback.** Phase D is additive apart from the activity-bar swap; reverting it
  restores the Previewers tab and removes the MiniApp surfaces without touching
  Phases A to C.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: After the create dialog is submitted, with the provider's
  availability already known (FR-024), the template tab is visible in under two
  seconds on the supported desktop build.
- **SC-002**: A call returning a small JSON result completes in under 50
  milliseconds at the median after the process has started, measured locally.
- **SC-003**: In 100% of preview and interactive context tests, no process is
  started and `call` is unavailable.
- **SC-004**: Ten seconds after a MiniApp tab closes — or after the grace period
  once its browser has disconnected — no process of its tree is alive, in 100% of lifecycle tests on Windows and POSIX, including a `panel.py`
  that starts a child process.
- **SC-005**: While a `panel.py` hangs or crashes, the API answers a health request
  within one second in 100% of the responsiveness tests.
- **SC-006**: In the e2e scenario, an agent with the MiniApp skill produces a
  MiniApp that passes `validate_panel` and opens through `open_miniapp`.
- **SC-007**: Each of the four entries reaches the create dialog or a MiniApp in
  the frontend tests.

## 6. Assumptions

- Phase A of `adr-054-panels` has merged before Phase D starts: discovery, the
  context service, `PanelFrame`, the SDK, and the token routes exist. (source: spec)
- The agent's `run_command` handle already ends a whole process tree and releases
  its registry entry, so a panel handle can follow its pattern. SciStudio holds two
  registry instances — the block runtime's and the application's — and shutdown
  terminates the application's, which is why FR-008 names it. (source:
  existing-system)
- ADR-022's resource manager reserves no memory for any process, so MiniApp memory
  can be shown but not admitted. (source: existing-system)
- "Bring in my work" already writes a brief and opens a pre-spawned agent session,
  and its availability check gives graded reasons, so the create route can reuse
  both. (source: existing-system)
- No tool today opens a tab of the agent's choosing; the frontend opens a workflow
  tab on `workflow_started` and on a created `workflow.changed`, and an AI block's
  terminal tab on `block_pty_opened`
  (`frontend/src/hooks/useWebSocket.parts/handleLifecycle.ts`), so `open_miniapp`
  follows that event-to-dispatcher pattern with a new event. (source:
  existing-system)
- ADR-053's promotion moves single files only, so panel directories need a new
  target. (source: existing-system)
- The startup and call limits, the debounce, the log location, the brief location,
  and the success-criteria targets are spec decisions open to owner revision.
  (source: spec)
- The template page's copy and the tip copy are reviewed by the owner. (source:
  owner)
- The owner chose to move the tutorials' `previewers` route with the list and to
  change one sentence of copy lightly; the sentence in FR-040 is proposed for their
  review. (source: owner)


## Guided audit repair validation (2026-09-13)

Workspace reconnects reuse their assigned client identity; MiniApp mounts wait
for that identity. Historical file-change counters do not reload a newly opened
tab. Create and Convert reveal the spawned AI session immediately. New MiniApp
source discovery enumerates available outputs across the project.

Context revocation does not join teardown on the store lock or event loop.
Shutdown grants up to five seconds for cooperative teardown and at most one
second for termination before killing remaining processes. POSIX cleanup also
finds detached descendants carrying the launch identity. Windows launches must
join a Job Object while suspended before any panel code executes. Native Windows
process-lifecycle validation remains unclaimed until a Windows runner supplies
evidence (tracked under #2354); local validation is on macOS.

Static assets reject hardlink aliases of panel.py. A MiniApp without Python
advertises read only, and process controls reject contexts without a process.

MiniApp bootstrap uses the block worker's import ordering: load runtime core
dependencies first, then add project and installed-package roots. This prevents
a plugin's incompatible native dependency from replacing the runtime's copy.
Setup/import exceptions appear in the process status and log. Create and Convert
responses include the actual session provider and permission mode for UI adoption.


### Guided project-isolation clarification (#2354)

MiniApp sources MUST belong to the active project. A retained workflow run from
another project, or a run without a recorded launch project, cannot supply a
candidate, create request, or MiniApp context. The runtime retains live workflow
runs for lifecycle management; MiniApp discovery must check scheduler ownership
before registering any raw output into the active catalogue.

The create and open pickers reset on project change and ignore superseded
responses. Creation waits for current backend discovery; cached canvas outputs
and unvalidated context-menu presets cannot substitute for it. Candidate labels
identify the node instance, with a display name when available. The MiniApps
sidebar uses a single-line plus-icon New button, and a single click opens a card.
The create, open-on-data, and convert dialogs use an icon-only X in the upper
right corner with an accessible Close label. Clicking it or pressing Escape
dismisses the dialog without submitting.


The owner-approved create-dialog copy is **Data source** with “Select an output
from a completed block.” and **Instructions** with “Describe what to display and
which controls you need.” The example is “Show the image with a threshold slider.
Update the mask as I adjust the threshold.” Instructions continue to populate
the MiniApp description and agent brief.


MiniApp toolbar actions use icon-and-text controls: rotation arrow **Restart**,
square **Stop**, and blocks **Convert**. Convert retains “Convert to interactive
block” as its tooltip and accessible name. These controls keep neutral styling.


### Guided conversion-dialog simplification (#2354)

The conversion form uses the title **Convert to interactive block** and asks
for **Outputs** with persistent
**Name** and **Data type** labels. The type choice uses the current project
catalogue (native select with keyboard lookup), rather than arbitrary text.
There is no separate Port field: names normalize to lower-case ASCII identifiers,
leading digits receive an `output_` prefix, names without ASCII characters use
`output`, and generated collisions receive numeric suffixes. Duplicate display
names are rejected case-insensitively; every added row must be completed.

**Add output** uses a plus icon. **Instructions** is marked Optional and uses
“Use the current threshold as the default.” as its placeholder. Provider and Permission mode remain the existing shared
components with their original layout, copy and behavior. Conversion still
creates a separate block through the existing agent route and leaves the source
MiniApp unchanged; outputs are not inferred or prefilled.


The final owner-approved explanation is “Use **{MiniApp display name}** as an
interactive step in your workflow. Choose which results it should send to the
next blocks.” The dynamic MiniApp name is bold. A second short paragraph says
“Your MiniApp will remain available.” Submission says **Convert**. The type
control is the catalogue-backed native select with keyboard prefix lookup;
this does not claim a searchable combobox.


### Canvas hover actions (guided owner directive, #2354)

The node right-click menu described in FR-035 is replaced by the existing block
hover detail popover. Its New MiniApp and compatible Open in MiniApp actions
retain the same produced-output, type and multi-port selection contracts. The
popover remains open while the pointer is inside, with a 120ms transit grace.
Project/user block source opens through Edit block in the existing editor;
builtin/package/custom source uses the existing readonly View source action.
The authoritative canvas interaction details are in
[the block palette spec](frontend-block-palette.md#canvas-action-relocation-guided-owner-directive-2354).
