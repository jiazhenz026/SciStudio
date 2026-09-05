---
spec_id: adr-054-agent-enablement
title: "ADR-054 Agent Enablement — Workspace Focus, The Panel Skill, And Session Tools"
status: Draft
feature_branch: docs/adr-054-agent-enablement-spec
created: 2026-09-02
input: "Owner-directed live session (guided): author the agent-enablement spec for ADR-054 section 8. The owner's one hard requirement: the agent must always know whether the person is on the canvas or in an explore session, delivered by extending the existing active-workflow channel into a workspace focus with a mode that the context tool reports, with session tools refusing when no session is active. The skill, the reference documents, the panel and session tools, the stub harness a scaffolded panel ships with, and the count assertions and catalogs every tool change moves are the author's to draft."
owners:
  - "@jiazhenz026"
related_adrs:
  - 33
  - 40
  - 42
  - 48
  - 53
  - 54
related_specs:
  - adr-054-panel-contract
  - adr-054-notebook-dependency-analysis
  - adr-054-explore-session
  - adr-054-explore-frontend
  - adr-054-documentation
  - embedded-coding-agent-spec
scope:
  in:
    - Workspace focus - the frontend reports the active mode (canvas, explore, pause) with its identifiers along the existing active-workflow channel, the backend persists it beside the active workflow id, and the context tool reports it; session tools refuse when no session is active.
    - The scistudio-write-panel skill, the panel-contract reference document, the rewrite of the panel section of block-contract.md to the framed-document form, the packaged-notebook shape in scistudio-write-block, and the base skill's routing.
    - Panel tools - scaffold a panel into a tier with its stub harness, read a panel's source, list panel examples, and rebuild the panel registry.
    - Session tools - open a session over a block's outputs, read the notebook with its marks and graph, append and run cells, list bindings, run the packaging check, and package.
    - The stub harness a scaffolded panel ships with, and how the agent opens it.
    - The examples corpus gaining a panel and a packaged notebook.
    - The count assertions, the provisioning skill count, and the catalog documents every tool and skill change moves.
  out:
    - The panel contract, the frame host, the tiers, and the asset route (adr-054-panel-contract).
    - The session runtime, its API, and its events (adr-054-explore-session). The session tools call that API.
    - The dependency analysis (adr-054-notebook-dependency-analysis).
    - The frontend (adr-054-explore-frontend), except the single report of the active mode this spec requires of it.
    - Human documentation revision (adr-054-documentation).
    - The agent runtime itself, its terminal, and its provisioning mechanism (ADR-033, ADR-040), which are unchanged.
governs:
  modules:
    - scistudio.ai.agent.mcp
    - scistudio.ai.agent.mcp.tools_panels
    - scistudio.agent_provisioning
  contracts:
    - scistudio.ai.agent.mcp.tools_workflow.read.get_active_workflow_context
  entry_points: []
  files:
    - docs/specs/adr-054-agent-enablement.md
    - src/scistudio/ai/agent/mcp/_context.py
    - src/scistudio/ai/agent/mcp/runtime.py
    - src/scistudio/ai/agent/mcp/server.py
    - src/scistudio/ai/agent/mcp/tools_workflow/read.py
    - src/scistudio/ai/agent/mcp/tools_authoring.py
    - src/scistudio/api/routes/ai.py
    - src/scistudio/api/runtime/_projects.py
    - src/scistudio/agent_provisioning/_orchestrate.py
    - src/scistudio/agent_provisioning/skills.py
    - src/scistudio/agent_provisioning/templates/claude_agents_md.md
    - src/scistudio/_skills/scistudio/SKILL.md
    - src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md
    - src/scistudio/ai/agent/mcp/tools_panels/**
    - src/scistudio/_agent_reference/README.md
    - src/scistudio/_agent_reference/block-contract.md
    - src/scistudio/_agent_reference/panel-contract.md
    - src/scistudio/_agent_reference/public-api.md
    - src/scistudio/_agent_reference/data-types.md
    - docs/specs/embedded-coding-agent-spec.md
    - tests/ai/test_mcp_tools_panels.py
    - tests/ai/test_mcp_fastmcp.py
    - tests/ai/test_mcp_server_skeleton.py
    - tests/ai/test_finish_ai_block_skeleton.py
    - tests/agent_provisioning/test_skills.py
  excludes:
    - docs/architecture/**
    - docs/user/**
planned_governs:
  modules:
    - scistudio.ai.agent.mcp.tools_explore
  contracts: []
  entry_points: []
  files:
    - src/scistudio/ai/agent/mcp/tools_explore/**
    - src/scistudio/_skills/scistudio/scistudio-write-panel/**
    - frontend/src/explore/**
    - tests/ai/test_mcp_tools_explore.py
    - tests/ai/test_workspace_focus.py
  excludes: []
tests:
  - tests/ai/test_workspace_focus.py
  - tests/ai/test_mcp_tools_panels.py
  - tests/ai/test_mcp_tools_explore.py
  - tests/ai/test_mcp_fastmcp.py
  - tests/ai/test_mcp_server_skeleton.py
  - tests/ai/test_finish_ai_block_skeleton.py
  - tests/agent_provisioning/test_skills.py
acceptance_source: adr
language_source: en
---

# ADR-054 Agent Enablement — Workspace Focus, The Panel Skill, And Session Tools

## 1. Change Summary

ADR-054 §8 says that the agent is the intended author of most of what the ADR
introduces — panels, blocks, and cells — and that a design whose authoring
path runs through an agent that has never heard of it is not delivered until
the agent has been taught. This spec is that teaching, plus one thing the
owner asked for that the ADR does not state: **the agent must always know
whether the person is on the canvas or in an explore session.**

The agent runs in a terminal inside the application and learns about the
workspace only through its tools. Today one of those tools reports the active
workflow, fed by the frontend and persisted beside the project. This spec
widens that channel into a **workspace focus**: the frontend reports the mode
— canvas, explore, or pause — with what identifies it, the backend persists
it as it persists the active workflow, and the context tool reports it. The
session tools refuse to act when no session is active, and the skills tell
the agent to ask before acting, because an agent that edits a workflow while
the person is in a notebook, or appends a cell while they are on the canvas,
is doing the wrong thing confidently.

The rest follows ADR-054 §8 as written. A new skill, `scistudio-write-panel`,
carries the task flow for authoring a panel; a new reference document,
`panel-contract.md`, carries the contract; the panel section of
`block-contract.md`, which today teaches the ES-module form the panel
contract retires, is rewritten; and `scistudio-write-block` gains the shape
in which a block is a packaged notebook and routes to the panel skill when
what the person wants is a window. Panel tools let the agent scaffold a
panel into a tier with the stub harness that makes it openable on its own,
read one, and rebuild the registry. Session tools let the agent open a
session, read the notebook with its marks and graph, append and run cells,
list bindings, and run the packaging check. Every tool and skill change moves
count assertions and catalog documents, and this spec lists them so that the
work plans for them rather than discovering them.

## 2. User Scenarios & Testing

### User Story 1 - The agent knows where the person is (Priority: P1)

A person in an explore session asks the agent to drop the rows with missing
intensity. The agent calls the context tool, sees that the mode is explore
with a session on a notebook, appends a cell that drops the rows, and runs
it. The same request made from the canvas leads the agent to propose a block
or a workflow edit instead.

**Why this priority**: This is the owner's one hard requirement for this
spec. Without it every other tool here can be used in the wrong place, and
an agent that is wrong about where the person is does damage rather than
work.

**Independent Test**: Set the focus to canvas with a workflow, call the
context tool, and confirm the mode and the workflow are reported. Set it to
explore with a session path, a bound run, and a current cell, and confirm
each is reported. Set it to pause with a node and a run and confirm the same.
Call a session tool with the focus on canvas and confirm it refuses with a
message saying no session is active.

**Acceptance Scenarios**:

1. **Given** the frontend has reported an Explore tab as active, **When** the
   agent calls the context tool, **Then** the result carries mode explore,
   the session's notebook path, its bound run, and the current cell.
2. **Given** the frontend has reported a workflow tab as active, **When** the
   agent calls the context tool, **Then** the result carries mode canvas and
   the workflow id, exactly as the tool reports today.
3. **Given** the frontend has reported a pause tab as active, **When** the
   agent calls the context tool, **Then** the result carries mode pause with
   the paused node and its run.
4. **Given** the focus is canvas, **When** the agent calls any session tool
   without naming a session, **Then** the tool refuses with a message saying
   no explore session is active and how to open one.
5. **Given** the backend restarts, **When** the agent calls the context
   tool, **Then** the last reported focus is restored from disk.

### User Story 2 - The agent authors a panel and sees it work (Priority: P2)

A person asks for a picker that lets them drag a baseline region on a
spectrum. The agent scaffolds a panel into the project, opens the generated
harness in a browser, sees the panel render over stub data and emit a line of
code when a region is dragged, edits the document, rebuilds the registry, and
the panel is available for the spectrum type.

**Why this priority**: ADR-054 §3.2 chose the panel's authoring form so that
an agent can see whether its output works, and §8.5 says that argument is
sound only if the harness delivers the loop. This story is the loop.

**Independent Test**: Call the scaffold tool for a target type into the
project tier and confirm the panel directory, the declaration, the document,
and the harness exist; open the harness and confirm it renders the document
over the stub data and captures an emission; call the reload tool and confirm
the registry lists the panel; call the read tool and confirm it returns the
source.

**Acceptance Scenarios**:

1. **Given** a target type and a tier, **When** the agent calls the scaffold
   tool, **Then** a panel directory with a declaration, a self-contained
   document, and a harness is written into that tier.
2. **Given** the harness, **When** it is opened in a browser, **Then** the
   document renders over representative data for the declared types, the
   host side of the message contract is stood in for, and an emission is
   captured and shown.
3. **Given** a scaffolded panel, **When** the agent calls the reload tool,
   **Then** the registry lists the panel with its capability and tier.
4. **Given** a registered panel, **When** the agent calls the read tool,
   **Then** it returns the declaration and the document.
5. **Given** the panel skill, **When** the agent follows it, **Then** it
   decides the capability, chooses the tier, writes the document, checks it
   in the harness, and registers it, in that order.

### User Story 3 - The agent works inside the person's session (Priority: P3)

A person in a session asks the agent to find the peaks. The agent reads the
notebook, sees which cells are stale, which names are bound and live, appends
a cell calling the peak-finding block, runs it, and reports the binding it
produced. The person sees the cell appear and run in their notebook.

**Why this priority**: ADR-054 §8.1 says someone who does not want to write
pandas will ask the agent to write the cells. It ranks below Story 2 because
it depends on the session API rather than on anything this spec builds
itself.

**Independent Test**: Against a scripted session, call the read tool and
confirm cells, marks, bindings, and the graph are returned; call the append
tool and confirm a cell is inserted after the current cell through the
session API; call the run tool and confirm the queue receives it; call the
bindings tool and confirm live and greyed names are distinguished; call the
packaging check and confirm the report is returned.

**Acceptance Scenarios**:

1. **Given** an active session, **When** the agent calls the read tool,
   **Then** it returns the cells with their marks, the bindings with whether
   each is live, the declared outputs, and the graph.
2. **Given** an active session, **When** the agent appends a cell, **Then** the
   cell is inserted after the person's current cell through the session API
   and appears in their notebook.
3. **Given** an appended cell, **When** the agent runs it, **Then** it goes
   through the session's queue like any cell, and the tool returns the
   outputs and the changed names when the run completes.
4. **Given** an active session, **When** the agent calls the packaging check,
   **Then** the report is returned with the slice and the ports or the
   refusals.
5. **Given** an active session, **When** the agent calls the open tool for a
   different block, **Then** a second session opens and the focus is
   unchanged until the person switches to it.

### User Story 4 - The agent chooses the packaged-notebook shape (Priority: P4)

A person asks for a step whose computation nobody knows yet. The agent,
following the block skill, opens a session over the data, works it out in
cells, runs the packaging check, and packages. A block appears in the palette.

**Why this priority**: ADR-054 §8.1 names this as a judgement the agent
should be able to make and explain rather than default into. It ranks below
Story 3 because it is that story followed by packaging.

**Independent Test**: Read the block skill and confirm it presents the
packaged-notebook shape beside the existing shapes with the condition for
choosing it, and routes to the panel skill when the request is a window.
Call the package tool on a clean fixture session and confirm the block is
written and registered.

**Acceptance Scenarios**:

1. **Given** the block skill, **When** the agent reads it, **Then** it names
   the packaged-notebook shape, says to choose it when the computation is not
   yet understood, and routes to the panel skill when the request is a
   window.
2. **Given** a clean session, **When** the agent calls the package tool,
   **Then** the block is written under the project's blocks directory and
   registers with the declared ports.
3. **Given** a session with a refusal, **When** the agent calls the package
   tool, **Then** it is refused with the same report the check returns.

### User Story 5 - A tool change moves everything it must (Priority: P5)

A maintainer adds a session tool. The suite fails in the places that count
tools and the catalogs that list them, and the spec tells them which places
those are, so the change lands in one pass.

**Why this priority**: ADR-054 §8.4 calls this cost easy to miss and easy to
state. It ranks last because it is a maintenance property.

**Independent Test**: Add the tools this spec names and confirm the count
assertions, the provisioning skill count, and the catalog documents are
updated together, and the suite passes.

**Acceptance Scenarios**:

1. **Given** the tools and the skill this spec adds, **When** the suite runs,
   **Then** every count assertion this spec lists matches.
2. **Given** the tools this spec adds, **When** the catalogs this spec lists
   are read, **Then** each lists them.

### Edge Cases

- **The frontend has never reported a focus.** The context tool reports mode
  canvas with whatever active workflow is persisted, which is today's
  behaviour.
- **The focus names a session whose notebook no longer exists.** The context
  tool reports the focus as stale and the session tools refuse until a new
  focus is reported.
- **The agent names a session explicitly while the focus is elsewhere.** The
  session tools accept an explicit session path, so an agent can work in a
  session the person is not looking at; the skill says to prefer the focus.
- **The agent appends a cell while a cell is running.** The append is queued
  by the session like any submission; the tool returns when the run completes
  or when the queue refuses.
- **A scaffolded panel's harness is opened without a browser available.** The
  tool reports the harness path and the URL the existing GUI tool exposes, and
  the agent is told to use its own browser path.
- **The provisioning template's skill count.** The template states the number
  of task skills in prose; it changes from six to seven, and the provisioning
  test that counts written files moves with it.

## 3. Requirements

### Functional Requirements

**Workspace focus**

- **FR-001**: The frontend MUST report the workspace focus whenever the active
  tab changes: mode `canvas` with the workflow id; mode `explore` with the
  session's notebook path, its bound run, and the current cell id; or mode
  `pause` with the paused node and its run. The report MUST travel along the
  existing active-workflow channel.
- **FR-002**: The backend MUST persist the focus beside the active workflow
  id, in the same per-project file, and MUST restore it on project open and
  on backend restart exactly as it restores the active workflow id.
- **FR-003**: The context tool the agent already has for the active workflow
  MUST report the focus: its existing fields unchanged, plus the mode and the
  mode's identifiers. A focus that has never been reported MUST read as mode
  canvas with the persisted workflow.
- **FR-004**: A focus naming a session whose notebook no longer exists MUST be
  reported as stale, and session tools MUST refuse until a new focus is
  reported.
- **FR-005**: Every session tool MUST act on the focused session by default,
  MUST accept an explicit session path instead, and MUST refuse with a
  message saying no explore session is active and how to open one when
  neither is available.

**Skills**

- **FR-006**: A task skill `scistudio-write-panel` MUST be added to the bundle
  with the flow: decide the capability, choose the tier, write the document,
  check it in the harness, register it. It MUST be short, carry no inline
  code, and point at the panel-contract reference and the panel examples.
- **FR-007**: `scistudio-write-block` MUST present the packaged-notebook shape
  beside the shapes it presents today, state that it is chosen when the
  computation is not yet understood, and route to `scistudio-write-panel`
  when what the person wants is a window.
- **FR-008**: The base skill MUST route to the panel skill and MUST tell the
  agent to confirm the workspace focus before acting on a request that could
  be a cell or a workflow edit.
- **FR-009**: The provisioning orchestration, the skill list, the
  provisioning template's statement of the task-skill count, and the
  provisioning test that counts written files MUST be updated for the added
  skill.

**Reference documents**

- **FR-010**: A reference document `panel-contract.md` MUST be added and MUST
  be the single description of the capability declaration, the message
  contract, the on-disk layout, the tier a panel is written into, the
  registration per tier, and the statement whitelist for emitted code, as the
  panel-contract spec defines them.
- **FR-011**: The panel section of `block-contract.md` MUST be rewritten to
  the framed-document form and MUST NOT describe the ES-module form or the
  retired asset route.
- **FR-012**: `public-api.md` MUST name the three notebook helpers at the
  top-level package and the explore subsystem's public symbols, and
  `data-types.md` MUST state that a notebook holds native objects and how the
  helpers convert at the boundary.
- **FR-013**: The reference README MUST index the added document.

**Panel tools**

- **FR-014**: A `scaffold_panel` tool MUST write a panel directory into a
  named tier for named target types and a capability: the declaration, a
  self-contained document with a working skeleton, and a harness.
- **FR-015**: The harness MUST be a document that opens on its own in a
  browser: it MUST load the panel document, supply representative data for
  the declared target types, stand in for the host side of the message
  contract, and show any emission the panel makes. The tool MUST return the
  harness path and the URL the existing GUI tool exposes.
- **FR-016**: A `read_panel_source` tool MUST return a registered panel's
  declaration and document by id, from whichever tier it resolved from.
- **FR-017**: A `list_panel_examples` tool MUST return the panel examples in
  the corpus, which MUST gain at least one displaying and one producing
  panel.
- **FR-018**: A `reload_panels` tool MUST rebuild the panel registry and
  return the discovered panels with their tiers, capabilities, and any
  discovery diagnostics.

**Session tools**

- **FR-019**: An `open_explore_session` tool MUST open a session over a named
  block's outputs or a named file through the session API and return the
  session path. It MUST NOT change the focus.
- **FR-020**: A `read_notebook` tool MUST return the session's cells with
  their source, enabled flag, marks, and outputs; the bindings with their
  type names and whether each is live; the declared outputs; and the graph.
- **FR-021**: An `append_cell` tool MUST insert a cell after the session's
  current cell through the session API and return its id, and a `run_cell`
  tool MUST submit a cell to the session's queue and return its outputs and
  changed names when the run completes, or the queue's refusal.
- **FR-022**: A `get_bindings` tool MUST return the bindings alone, for the
  common case where the agent needs to know what exists before writing.
- **FR-023**: A `check_packaging` tool MUST return the packaging report, and a
  `package_notebook` tool MUST package and return the block id, or the report
  when packaging is refused.
- **FR-024**: Every session tool MUST go through the session API and MUST NOT
  reach the kernel, the notebook file, or the queue directly.

**Counts and catalogs**

- **FR-025**: The tool-count assertions in the MCP tests MUST be updated for
  the eleven tools this spec adds, and the per-group assertions MUST gain the
  two new groups.
- **FR-026**: The catalogs that list tools — the base skill, the embedded
  coding agent spec, and the architecture document's tool table — MUST list
  the added tools. The architecture document is a guarded path and its
  update follows the documentation spec's batch.
- **FR-027**: The examples corpus MUST gain a panel and a packaged notebook,
  reachable through the existing example-listing tools.

### Key Entities

- **WorkspaceFocus** — what the person is looking at. Attributes: mode,
  workflow id, session path, bound run, current cell, paused node, paused
  run, reported-at. Relationships: reported by the frontend; persisted with
  the active workflow id; read by the context tool and by every session tool.
- **PanelScaffold** — what the scaffold tool writes. Attributes: tier,
  panel id, target types, capability, declaration, document, harness.
  Relationships: registered by the reload tool; read by the read tool.
- **PanelHarness** — the standalone document. Attributes: stub data per
  target type, host stand-in, captured emissions. Relationships: written by
  PanelScaffold; opened through the GUI tool's URL or a file path.
- **SessionToolContext** — the session a tool acts on. Attributes: session
  path, resolved from the focus or from an explicit argument.
  Relationships: refused when neither resolves.
- **ToolCatalog** — the places that enumerate tools. Attributes: the count
  assertions, the base skill, the agent spec, the architecture table.
  Relationships: every tool change moves all of them.

## 4. Implementation Plan

### 4.1 Technical Approach

**The focus rides the channel that exists.** ADR-040 Addendum 5 gave the
agent the active workflow: the frontend posts it, the runtime keeps it and
mirrors it to a per-project file so it survives restarts, and a tool reads
it. The focus is the same shape with more fields. The frontend's report is
one call on tab change, which the explore-frontend spec's tab already has a
place for; the runtime's field becomes a small record; the file gains keys;
the tool gains fields. Nothing new is invented, and the agent that already
calls the context tool keeps working.

**Refusal is the enforcement.** A skill can tell the agent to check the mode
first, and it does, but the session tools refusing to act without a session
is what makes the rule hold when the agent forgets. The refusal names the way
to open a session, so the agent can recover in one step.

**The harness is what makes the authoring form honest.** ADR-054 §8.5 says
the argument for a plain HTML panel is sound only if the agent can actually
open its work and look at it. The scaffold writes, beside the panel document,
a harness page that loads it, stands in for the host, feeds it data shaped
like the declared types, and prints whatever it emits. The agent's existing
browser-driven path — the GUI tool returns a URL, the agent uses its own
browser — is the mechanism; what is new is that a panel is born with a page
that path can open.

**Session tools are thin.** Each is a call to the session API the
explore-session spec defines, with the focus resolved first. They do not
touch the kernel, the notebook file, or the queue, because the whole point of
the session service is that every execution passes through it, and an agent
tool that bypassed it would be a second door. An appended cell appears in the
person's notebook through the same events the person's own edits produce.

**Two new tool groups, and the arithmetic that follows.** The panel tools and
the session tools are two modules beside the existing groups. The MCP tests
assert the total and the per-group counts; the base skill, the agent spec,
and the architecture document list every tool. The architecture document is
a guarded path, so its row lands in the documentation spec's batch, and the
count assertions land with the tools. The provisioning side counts skills the
same way: the orchestration list, the skills index, the template's prose
count, and the provisioning test all name the number, and all move by one.

**The reference documents carry the shapes; the skills carry the flow.**
This follows the layering ADR-054 §8.2 records: a skill stays short with no
inline code, the reference documents carry contracts, and worked patterns are
fetched through the example-listing tools. The panel section of
`block-contract.md` is rewritten rather than appended to, because it
currently teaches the form the panel contract retires, and a document that
teaches both is worse than one that teaches neither.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `docs/specs/adr-054-agent-enablement.md` | create | This spec. |
| `src/scistudio/api/routes/ai.py` | modify | The focus report on the active-workflow route (FR-001). |
| `src/scistudio/api/runtime/_projects.py` | modify | Focus persistence beside the active workflow id (FR-002). |
| `src/scistudio/ai/agent/mcp/runtime.py`, `_context.py` | modify | The focus record reaches the tools (FR-003). |
| `src/scistudio/ai/agent/mcp/tools_workflow/read.py` | modify | The context tool reports the focus (FR-003, FR-004). |
| `src/scistudio/ai/agent/mcp/tools_panels/**` | create | scaffold, read, examples, reload (FR-014 to FR-018). |
| `src/scistudio/ai/agent/mcp/tools_explore/**` | create | open, read, append, run, bindings, check, package (FR-019 to FR-024). |
| `src/scistudio/ai/agent/mcp/server.py` | modify | Registers the two groups. |
| `src/scistudio/ai/agent/mcp/tools_authoring.py` | modify | Example listing gains the panel and the packaged notebook (FR-027). |
| `src/scistudio/_skills/scistudio/scistudio-write-panel/**` | create | The panel skill (FR-006). |
| `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md` | modify | The packaged-notebook shape and the routing (FR-007). |
| `src/scistudio/_skills/scistudio/SKILL.md` | modify | Routing and the focus rule; the tool catalog (FR-008, FR-026). |
| `src/scistudio/agent_provisioning/_orchestrate.py`, `skills.py`, `templates/claude_agents_md.md` | modify | The seventh task skill (FR-009). |
| `src/scistudio/_agent_reference/panel-contract.md` | create | The panel reference (FR-010). |
| `src/scistudio/_agent_reference/block-contract.md` | modify | The panel section rewritten (FR-011). |
| `src/scistudio/_agent_reference/public-api.md`, `data-types.md`, `README.md` | modify | Helpers, explore symbols, boundary conversion, index (FR-012, FR-013). |
| `docs/specs/embedded-coding-agent-spec.md` | modify | The tool catalog (FR-026). |
| `tests/ai/test_workspace_focus.py` | create | Focus report, persistence, context tool, refusal (FR-001 to FR-005). |
| `tests/ai/test_mcp_tools_panels.py` | create | Scaffold, harness, read, reload. |
| `tests/ai/test_mcp_tools_explore.py` | create | Session tools against a scripted session API. |
| `tests/ai/test_mcp_fastmcp.py`, `test_mcp_server_skeleton.py`, `test_finish_ai_block_skeleton.py` | modify | Count assertions (FR-025). |
| `tests/agent_provisioning/test_skills.py` | modify | The written-file count (FR-009). |
| `frontend/src/explore/**` | modify | The focus report on tab change, owned by the explore-frontend spec (FR-001). |

### 4.3 Implementation Sequence

| Task | Title | Story | Depends on | Verification |
|---|---|---|---|---|
| T-001 | Widen the active-workflow channel into the workspace focus: route, persistence, runtime record | US1 | — | Focus round-trips through the file and restart |
| T-002 | Report the focus from the context tool and refuse session tools without a session | US1 | T-001 | Each mode reported; refusal message names the way to open a session |
| T-003 | Write the panel-contract reference and rewrite the panel section of the block contract | US2 | — | No mention of the ES-module form remains |
| T-004 | Add the panel tools with the scaffold's harness | US2 | T-003 | Harness renders over stub data and captures an emission |
| T-005 | Add the panel skill and update provisioning counts | US2 | T-003 | Provisioning writes the seventh skill; counts pass |
| T-006 | Add the session tools over the session API | US3, US4 | T-002 | Each tool reaches the API; appended cell appears through events |
| T-007 | Update the block skill and the base skill | US4 | T-005 | Routing and the focus rule present |
| T-008 | Add the examples: a panel and a packaged notebook | US2, US4 | T-004 | Example listing returns both |
| T-009 | Update count assertions and catalogs | US5 | T-004, T-006 | Suite passes; catalogs list every tool |

### 4.4 Verification Plan

The focus is tested end to end on the backend: post each mode on the route,
read it back from the runtime and from the file, restart the runtime object,
and call the context tool. The refusal is tested by calling every session
tool with the focus on canvas and with a stale session.

The panel tools are tested against the panel registry with a temporary tier:
scaffold, confirm the three files, open the harness in the test browser the
end-to-end toolchain provides and confirm it renders and captures an
emission, reload, and read.

The session tools are tested against a scripted session API, asserting the
request each tool makes and the shape of what it returns; the real session
is covered by the explore-session spec.

Provisioning is tested by the existing provisioning test with its count
moved, and the skills by the existing skill tests extended to the added one.
The count assertions are the test; the catalogs are checked by a test that
reads each and asserts every registered tool name appears.

### 4.5 Risks And Rollback

**The architecture document's tool table.** It is a guarded path, and the
count assertions cannot wait for its batch. The mitigation is that the
assertions and the other catalogs land with the tools, and the guarded table
lands in the documentation spec's batch with its label; the test that reads
catalogs excludes the guarded document until then.

**An agent that ignores the mode.** The skill's rule is advice; the tools'
refusal is the guarantee. A session tool cannot act on the canvas, and a
workflow edit while a session is focused is not refused, because the person
may want it; the skill tells the agent to ask.

**The harness drifts from the host.** A harness that stands in for the host
can fall behind the real message contract. The harness is generated from the
same contract module the host uses, and the panel-contract spec's contract
test runs the built-in panels through it.

**Rollback.** The two tool groups, the skill, and the reference document can
be removed as a unit with the counts moved back; the focus fields are
additive and default to today's behaviour when absent.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: The context tool reports mode canvas, explore, and pause with
  the identifiers of each, and restores the last focus after a restart.
  Measured by test.
- **SC-002**: Every session tool refuses with the recovery message when no
  session is focused or named. Measured by test.
- **SC-003**: A scaffolded panel's harness renders the document over stub
  data and captures an emission in a browser. Measured by the end-to-end
  toolchain.
- **SC-004**: A scaffolded panel registers on reload with its tier and
  capability, and reads back. Measured by test.
- **SC-005**: Each session tool makes the session API call this spec names
  and returns the stated shape. Measured by test against a scripted API.
- **SC-006**: Provisioning writes seven task skills and the base skill, and
  the provisioning test's count matches. Measured by test.
- **SC-007**: The block skill names the packaged-notebook shape and routes to
  the panel skill; the base skill states the focus rule. Measured by reading
  them in a test.
- **SC-008**: No reference document describes the ES-module panel form or the
  retired asset route. Measured by a search.
- **SC-009**: Every count assertion matches and every unguarded catalog lists
  every registered tool. Measured by the suite.
- **SC-010**: The example listing returns a panel and a packaged notebook.
  Measured by test.

## 6. Assumptions

- **A-001**: The agent must always know whether the person is on the canvas
  or in an explore session, and the mechanism is the active-workflow channel
  widened into a focus. _Source: owner._
- **A-002**: The frontend's report of the focus is one call on tab change and
  is owned by the explore-frontend spec's tab; this spec states the
  requirement and the shape. _Source: spec._
- **A-003**: Session tools call the session API the explore-session spec
  defines and never reach the kernel. _Source: adr._
- **A-004**: The tool set is the author's: four panel tools and seven session
  tools. The owner delegated the list. _Source: owner._
- **A-005**: The harness is generated from the same contract module the frame
  host uses, so that it cannot drift silently. _Source: inferred._
- **A-006**: The architecture document's tool table is updated in the
  documentation spec's batch because the document is guarded, and the
  catalog test excludes it until then. _Source: existing-system._
- **A-007**: Authoring cells inside an open session is not a skill; the
  conventions live in the reference the session tools point at, as ADR-054
  §8.3 decides. _Source: adr._
- **A-008**: The agent's browser-driven path through the GUI tool is the way
  it opens a harness; no new browser mechanism is added. _Source: adr._
