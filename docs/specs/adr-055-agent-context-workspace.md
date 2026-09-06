---
spec_id: adr-055-agent-context-workspace
title: "ADR-055 Spec 2 — Agent Context, Workspace Access, And Managed Execution Tools"
status: Draft
feature_branch: docs/2263-adr-055-specs
created: 2026-09-05
input: "Owner-directed live session: author the ADR-055 implementation spec set under umbrella issue #2263. Spec 2 merges ADR-055 sections 5.1, 5.2, and 5.3 (owner decision: one spec). get_agent_context exposes the existing provisioned project assets with real paths; workspace tools (inspect/author/upload/download) reuse existing services rather than duplicating domain logic; file export uses browser download / host native file capability (owner decision; the new download endpoint doubles as the future web-UI manual transfer entry; base64 inline only for small files); run_command executes arbitrary code as an intended capability via asyncio subprocess registered in the ProcessRegistry for process-tree cancellation, with explicit project context and the bundled Python environment. All new tools register in the shared FastMCP registry with the external-audience tag per adr-055-webmcp-bridge; none are router-internal."
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 40
  - 36
  - 17
  - 19
related_specs:
  - adr-055-webmcp-bridge
  - adr-055-prefix-independence
scope:
  in:
    - "The `get_agent_context` tool over existing provisioned assets: project identity, effective guidance, an index of documentation and skills with real readable paths, the instance's execution environment and capabilities, and hook guidance with execution location made explicit."
    - "Workspace inspect tools: directory listing, metadata, file search, and bounded streaming text reads."
    - "Workspace author tools: create, write, patch, rename, move, delete with explicit conflict handling, reusing the existing atomic-write / UI-sync / block-reload path."
    - "Transfer: streaming upload reuse, a new streaming download endpoint (shared with the future web-UI manual transfer entry), in-place reference to authorized server datasets, and bounded inline fallback for small files only."
    - "The `run_command` execution tool: asyncio subprocess registered in the existing ProcessRegistry, explicit project context, bundled-Python environment contract, managed lifecycle for long operations, bounded output capture, and request-vs-job cancellation semantics."
    - Bounded operation logging for all new tools (identifiers and outcomes, never full payloads).
    - Registration of all new tools in the shared FastMCP registry with the external-audience visibility tag from adr-055-webmcp-bridge.
  out:
    - The webmcp router, registration module, and session middleware (adr-055-webmcp-bridge).
    - "Provisioning changes: instructions, skills, hooks, and agent-reference assets already exist (ADR-040); this spec consumes them, it does not redesign them."
    - Automatic host-native hook execution or system-prompt installation (excluded by ADR-055 section 10).
    - "A new sandbox around arbitrary code (excluded by ADR-055 section 5.3: code runs with the user's ordinary permissions)."
    - Per-project Python environments (excluded by ADR-055 section 8).
    - The web UI's manual upload/download entry points (future work; this spec delivers only the shared endpoint they will use).
governs:
  modules:
    - scistudio.ai.agent.mcp.tools_qa
    - scistudio.api.routes.projects
    - scistudio.api.routes.data
  contracts:
    - scistudio.ai.agent.mcp._context.get_context
  entry_points: []
  files:
    - docs/specs/adr-055-agent-context-workspace.md
    - src/scistudio/ai/agent/mcp/tools_qa.py
    - src/scistudio/ai/agent/mcp/__init__.py
    - src/scistudio/ai/agent/mcp/_context.py
    - src/scistudio/api/routes/projects.py
    - src/scistudio/api/routes/data.py
    - src/scistudio/api/runtime/_workflows.py
    - src/scistudio/engine/runners/process_handle.py
  excludes: []
planned_governs:
  modules:
    - scistudio.ai.agent.mcp.tools_workspace
    - scistudio.ai.agent.mcp.tools_execution
  contracts: []
  entry_points: []
  files:
    - src/scistudio/ai/agent/mcp/tools_workspace.py
    - src/scistudio/ai/agent/mcp/tools_execution.py
  excludes: []
tests:
  - tests/ai/test_mcp_agent_context.py
  - tests/ai/test_mcp_workspace_tools.py
  - tests/ai/test_mcp_execution_tools.py
  - tests/api/test_projects.py
acceptance_source: adr
language_source: en
---

# ADR-055 Spec 2 — Agent Context, Workspace Access, And Managed Execution Tools

## 1. Change Summary

This spec comes from ADR-055 (section 5) and umbrella issue #2263; the owner
merged the context, workspace, and execution surfaces into one spec.

An external AI agent driving SciStudio through the webmcp bridge needs three
things a local CLI agent gets natively: the project's provisioned context
(instructions, docs, skills, hooks), access to the project filesystem beside
the backend, and a way to run code. ADR-055 section 5 defines all three, and
section 9.2 records why the hackathon demo's versions are not production-ready:
reads collect fully before truncating, shell execution blocks the event loop
and ignores the process registry, shell calls can run with `cwd=None`, and
cancellation is half-wired.

This spec defines the production versions, with three structural rules:

1. **Real registry tools, tagged external.** Every new tool is a normal
   `@mcp.tool` in the shared registry carrying the `audience:external`
   visibility tag from `adr-055-webmcp-bridge`, so local agents (who have
   native file/shell capability) never see them and the router never grows
   if-chain dispatch.
2. **Reuse, not duplication.** Authoring reuses the existing atomic-write +
   UI-sync + block-reload path; upload reuses the staged chunked upload;
   execution reuses the asyncio spawn + ProcessRegistry pattern. The spec
   extracts shared helpers where the current logic is trapped inside an HTTP
   route.
3. **Bounded by construction.** Reads and outputs are capped while streaming,
   not after collection; large payloads move through a transfer path with
   status reporting; logs carry identifiers and outcomes, never payloads.

## 2. User Scenarios & Testing

### User Story 1 - An external agent receives the project's real context (Priority: P1)

A freshly provisioned project exposes its existing instructions, documentation
index, skills index, execution environment, and hook guidance through
`get_agent_context`, with real readable paths and honest statements about what
the host does and does not execute.

**Why this priority**: ADR-055 section 5.1 makes this the only new context
tool and the entry point that keeps external agents aligned with the project's
existing provisioning; without it every other tool is used blind.

**Independent Test**: Create a project through the normal provisioning path,
call `get_agent_context` through the registry (no browser needed), and assert:
the response names the project's actual provisioned assets (instructions,
`.scistudio/agent-reference/`, skills directories) with paths that resolve;
the docs index matches the real `docs/` tree; hook guidance states where hooks
execute. Then delete one asset class and assert the response reports its
absence accurately instead of fabricating an index.

**Acceptance Scenarios**:

1. **Given** a newly created project, **When** `get_agent_context` is called,
   **Then** the response includes project identity, the effective guidance
   summary, and an index whose entries point to paths that exist on disk.
2. **Given** a project whose `.scistudio/agent-reference/` is missing, **When**
   the tool is called, **Then** the response reports that asset class as
   unavailable with an accurate diagnostic, and the rest of the index is
   unaffected.
3. **Given** any project, **When** the response describes hooks, **Then** it
   states their execution location explicitly and never claims the host
   executed them.

### User Story 2 - The agent inspects and authors project files with UI sync (Priority: P1)

The external agent lists directories, reads files in bounded ranges, and
creates or modifies files — and every write lands through the same atomic-write
and file-change-notification path the editor uses, so the open UI reflects the
change.

**Why this priority**: Authoring is the core external-agent capability;
writes that bypass the notification path silently desynchronize the user's UI
(ADR-055 section 5.2: "the browser remains a view of backend state").

**Independent Test**: Through the registry, list a project directory, read a
file with an offset/limit that crosses the read cap, then write a new file and
patch an existing one; assert the read never buffered more than the cap, the
writes are atomic (no partial states observable), a file-changed event reaches
the event bus, and a conflicting write to a file changed since the read is
rejected with an explicit conflict response.

**Acceptance Scenarios**:

1. **Given** a project with nested directories, **When** the inspect tools run,
   **Then** listing, metadata, and search results are project-relative and
   cannot escape the project root (traversal attempts rejected).
2. **Given** a 5 MB text file, **When** it is read with default bounds,
   **Then** the response contains at most the capped byte range plus an
   accurate truncation marker with total size, and the implementation never
   materializes the whole file to produce it.
3. **Given** a file the agent read at version N, **When** the file changed on
   disk and the agent writes based on version N, **Then** the write is
   rejected with an explicit conflict response naming the condition.

### User Story 3 - Large files move through a real transfer path (Priority: P2)

Uploads stream through the existing staged chunked path; downloads use a new
streaming endpoint that the future web-UI manual entry will also call; small
payloads may travel inline (base64) only under a declared cap; server-resident
datasets are referenced in place, never re-uploaded.

**Why this priority**: ADR-055 section 5.2 makes the bounded streaming transfer
path a requirement and forbids treating a private server URL as proof the host
retrieved a file; the owner chose browser download / host native file
capability as the host handoff.

**Independent Test**: Upload a 200 MB file through the tool and assert memory
use stays bounded and the staged-upload service is what lands it; download a
project output through the new endpoint and assert streamed delivery with
correct length; attempt an inline transfer above the cap and assert it is
refused with a pointer to the transfer path; reference an authorized shared
dataset directory and assert no copy occurs.

**Acceptance Scenarios**:

1. **Given** a large user file, **When** the upload tool runs, **Then** the
   file lands via the staged chunked upload and the tool result identifies the
   transfer and its final status.
2. **Given** a large analysis output, **When** the download endpoint is used,
   **Then** the response streams with accurate size headers and survives a
   client disconnect without corrupting server state.
3. **Given** an authorized shared data directory, **When** the agent references
   it, **Then** tools operate on it in place under the existing filesystem
   permissions and no redundant upload is created.

### User Story 4 - Arbitrary code runs managed, cancellable, and in the right environment (Priority: P1)

`run_command` executes user-authorized arbitrary code with the instance's
ordinary permissions: asyncio-spawned, registered in the ProcessRegistry for
process-tree cancellation, bound to an explicit project context, and resolving
the bundled Python and user dependency locations so a package the agent
installs is the package SciStudio later uses.

**Why this priority**: ADR-055 section 5.3 declares arbitrary code an intended
capability; the demo's synchronous `subprocess.run` blocked the event loop,
ignored cancellation, and could run with `cwd=None` — all three are
correctness failures for a shared async server.

**Independent Test**: Start a long-running command that spawns children; while
it runs, verify the API stays responsive (a concurrent request completes);
cancel it and assert the whole process tree terminates and the registry no
longer tracks it; run `python -c "import sys; print(sys.executable)"` and
assert the bundled interpreter; pip-install a small package through
`run_command` and assert a subsequent SciStudio-side import resolves it.

**Acceptance Scenarios**:

1. **Given** a command that sleeps with child processes, **When** cancellation
   is requested, **Then** the process tree is terminated, the tool reports the
   terminal state, and the ProcessRegistry shows no residue.
2. **Given** a long-running command, **When** a sibling API request arrives,
   **Then** it completes without waiting for the command (no event-loop
   blocking).
3. **Given** no active project, **When** `run_command` is invoked, **Then** it
   fails with an explicit absent-context error instead of running with an
   undefined working directory.
4. **Given** a pip install through `run_command`, **When** SciStudio code later
   imports the package, **Then** both resolve the same user dependency
   location (environment is explicit and shared).

### User Story 5 - Job lifecycle outlives the browser request (Priority: P2)

A long operation started through a tool survives the originating HTTP request
ending: request cancellation and job cancellation are distinct, and job status,
output, and cancellation remain reachable through managed lifecycle behavior.

**Why this priority**: ADR-055 section 5.3: "a browser request timeout is
distinct from terminating a job and its child processes" — collapsing the two
either kills long analyses on disconnect or leaves orphans.

**Independent Test**: Start a managed long command, abort the HTTP request,
and assert the job keeps running and remains observable/cancellable; then
cancel the job and assert terminal state and process-tree cleanup.

**Acceptance Scenarios**:

1. **Given** a running managed command, **When** the originating request is
   aborted, **Then** the job continues and a later status call reports it
   accurately.
2. **Given** the same job, **When** job cancellation is issued, **Then** the
   process tree terminates and the final status is terminal and accurate.

### Edge Cases

- Read bounds exceeding file size: return what exists with an accurate
  truncation marker; never error solely for a large limit.
- Binary files through text-read tools: declared detection and refusal/fallback
  behavior; no mojibake-as-success.
- Writes to `blocks/`, `plots/`, `types/`, `workflows/`, `docs/` follow the
  existing drop-in semantics (block reload on save) — the reuse rule makes this
  automatic; tests pin it for one directory.
- Delete/rename of a path the UI has open: the file-changed event fires; the
  tool result notes the affected path; UI reaction is out of scope here.
- Output exactly at the cap: marker must be unambiguous about whether
  truncation occurred.
- Concurrent `run_command` invocations: each is an independent registry entry;
  no shared mutable execution state.
- `get_agent_context` on an instance with no active project: explicit
  absent-context response (never a project-less "default" index).

## 3. Requirements

### Functional Requirements

- **FR-001**: `get_agent_context` MUST return a bounded initial response
  covering: project identity and active context; effective SciStudio/project
  guidance; an index of documentation and skills with real readable paths
  (project `docs/`, `.scistudio/agent-reference/`, host-specific skills
  directories); the instance's execution environment and access capabilities;
  and hook guidance with execution location explicit. Detailed content stays in
  its files and is fetched through the appropriate existing tool.
- **FR-002**: The context index MUST NOT redirect every resource to `get_doc`
  and MUST NOT depend on copied-into-`docs/` assets (demo anti-pattern); each
  entry names its retrieval path (existing documentation tool for `docs/`,
  workspace read for the rest).
- **FR-003**: All new tools MUST register in the shared FastMCP registry with
  the `audience:external` tag and Pydantic result models; errors follow the
  existing raise-and-adapt convention.
- **FR-004**: Inspect tools (list/metadata/search/read) MUST be
  project-relative, sandboxed to the project root (reusing the existing
  containment logic), and reads MUST be bounded while streaming with an
  accurate truncation marker carrying total size.
- **FR-005**: Author tools (create/write/patch/rename/move/delete) MUST reuse
  the existing write path — atomic write, `FILE_CHANGED` event emission, and
  post-save block reload — extracted from `api/routes/projects.py` into a
  shared helper both the route and the tools call; conflicting writes MUST be
  rejected explicitly (stale-version or missing-file conditions named in the
  result).
- **FR-006**: Upload MUST reuse the staged chunked upload service
  (`stage_upload_file`/`finish_staged_upload`); inline (base64) import is
  allowed only under a declared small-file cap with a clear pointer to the
  transfer path above it.
- **FR-007**: A new streaming download endpoint MUST serve project files and
  outputs with accurate length headers and disconnect-safe behavior; the
  endpoint is the contract the future web-UI manual entry reuses. Inline
  download exists only for small files under the same cap.
- **FR-008**: Authorized shared datasets MUST be usable in place through
  filesystem permissions; tools MUST NOT copy them into the project.
- **FR-009**: `run_command` MUST use `asyncio.create_subprocess_exec` (never
  synchronous `subprocess.run` in the request path), register every process in
  the existing ProcessRegistry, support process-tree cancellation, and fail
  with an explicit absent-context error when no project is active.
- **FR-010**: The execution environment MUST be explicit: bundled Python,
  existing user dependency locations, and `SCISTUDIO_PROJECT_DIR` propagation
  (following the existing worker environment construction), so install-then-use
  resolves to the intended runtime.
- **FR-011**: Command output collection MUST be bounded during capture (not
  clipped after the fact) with an accurate truncation marker; long operations
  MUST use the managed job lifecycle with status and cancellation separate
  from the originating request.
- **FR-012**: Tool logging MUST record operation identifiers and outcomes only;
  file contents, command bodies, and full arguments MUST NOT be logged.

### Key Entities

- **TransferRecord**: identifier, direction (upload/download), project-relative
  target, byte count, status, terminal state; surfaced in tool results so the
  host can report or retry. Persistence follows the existing staged-upload
  behavior; no new store.
- **ManagedCommand**: identifier, project binding, argv/environment summary,
  status, exit state, truncation flags; backed by the ProcessRegistry entry.

## 4. Implementation Plan

### 4.1 Technical Approach

`get_agent_context` lands in `tools_qa.py` beside `get_project_info`,
`get_doc`, and `search_docs`, reading the provisioning outputs of
`agent_provisioning` (instructions files, `.scistudio/agent-reference/`,
skills directories) via `get_context().project_dir`; it assembles the bounded
index and marks each entry with its retrieval path.

Workspace tools land in a new `tools_workspace.py`; execution in
`tools_execution.py`; both register on import through the existing
`mcp/__init__.py` import list. The write path: extract the atomic-write +
`_emit_file_changed` + block-reload trio from `api/routes/projects.py` into a
runtime-level helper used by both the HTTP route and the tools, eliminating the
demo's bare-write fork. Reads implement ranged streaming reads with cap
counters. Upload calls the staged-upload runtime functions directly. Download
is a new streaming route (FileResponse-style) under the projects/filesystem
surface, placed beside the existing file route, with the same sandbox
resolution and without the editor allowlist (which governs the editor UI, not
transfer).

`run_command` follows the `LocalRunner._spawn_worker` pattern: asyncio
subprocess, `register_async_process`, bounded incremental output collection,
explicit environment from the worker-env construction, and a managed-job
wrapper for long operations with status/cancel surfaced as tools. Project
binding comes from `get_context()` and fails closed when absent.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/ai/agent/mcp/tools_qa.py` | modify | Add `get_agent_context` |
| `src/scistudio/ai/agent/mcp/tools_workspace.py` | create | Inspect/author/transfer tools |
| `src/scistudio/ai/agent/mcp/tools_execution.py` | create | `run_command` + managed job tools |
| `src/scistudio/ai/agent/mcp/__init__.py` | modify | Import new tool modules (registration) |
| `src/scistudio/api/routes/projects.py` | modify | Extract shared write helper; add streaming download route |
| `src/scistudio/api/routes/data.py` | modify | Wire download surface if placed there; reuse upload staging |
| `src/scistudio/api/runtime/_workflows.py` | modify | Expose staged-upload helpers at the level tools consume |
| `src/scistudio/engine/runners/process_handle.py` | modify | Any ProcessRegistry accessor needed by the tool layer |
| `tests/ai/test_mcp_agent_context.py` | create | Context tool over provisioned fixtures |
| `tests/ai/test_mcp_workspace_tools.py` | create | Inspect/author/transfer behavior and bounds |
| `tests/ai/test_mcp_execution_tools.py` | create | Execution, cancellation, environment, job lifecycle |
| `tests/api/test_projects.py` | modify | Download route + shared write-helper parity |

### 4.3 Implementation Sequence

1. **T-001** (foundation): extract the shared write helper from
   `projects.py`; route + helper parity tests.
2. **T-002** (US1): `get_agent_context` + provisioning-fixture tests.
3. **T-003** (US2): `tools_workspace.py` inspect/author tools + bounds and
   conflict tests.
4. **T-004** (US3): streaming download endpoint + upload reuse + inline caps.
5. **T-005** (US4/US5): `tools_execution.py` + registry integration +
   cancellation/responsiveness/environment tests.
6. **T-006** (cross-cutting): bounded logging, audience tags verified through
   both catalogues, ADR-055 section 11 Workspace/Execution/Existing-context
   rows.

### 4.4 Verification Plan

- Registry-level tests for every new tool (no browser required), covering the
  acceptance scenarios above.
- Memory-boundedness check for large read/upload/download paths (fixture size
  several times the cap).
- Concurrency test: long `run_command` + sibling API request responsiveness.
- Existing suites (`tests/api/test_projects.py`, provisioning lifecycle tests)
  pass unchanged.
- `gate_record check` tier-selected checks for the diff.

### 4.5 Risks And Rollback

- Risk: extracting the write helper changes editor save behavior. Mitigation:
  parity tests on the existing route before tools consume it; the route's
  observable behavior is pinned by current tests.
- Risk: arbitrary-code capability is abused through a compromised host.
  Mitigation: this is an ADR-decided intended capability with the user's
  ordinary permissions; the bridge session substrate (spec 1) is the boundary;
  logging policy preserves auditability.
- Risk: download endpoint broadens file exposure beyond the editor allowlist.
  Mitigation: same project sandbox; session-required; path resolution shared
  with the existing file route.
- Rollback: new modules and routes are additive; the extracted helper is
  behavior-preserving; revert restores current behavior with no migration.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: `get_agent_context` on a freshly provisioned project returns an
  index whose every listed path resolves on disk; missing-asset diagnostics are
  accurate in 100% of fixture cases.
- **SC-002**: No read or command-output path materializes more than the
  configured cap plus one chunk in memory, measured on fixtures ≥ 4× the cap.
- **SC-003**: 100% of tool-authored writes emit the file-changed event and pass
  through the atomic write path (asserted via the shared helper, not
  re-implemented).
- **SC-004**: A cancelled managed command leaves zero live descendant processes
  and zero registry residue in 100% of test runs on all supported platforms.
- **SC-005**: A pip install performed through `run_command` is importable by
  the SciStudio runtime in the same instance, in the verification environment.

## 6. Assumptions

- External agents have no filesystem access except these tools; local agents
  keep using their native capabilities and never see the external-tagged tools
  (source: owner session, 2026-09-05).
- Browser download / host native file capability is the supported host handoff
  for exports; a private server URL alone is not a supported handoff (source:
  owner session; ADR-055 section 5.2).
- Arbitrary code executes with the user's ordinary OS permissions and no
  additional sandbox (source: ADR-055 section 5.3).
- One environment per user, shared by that user's projects; no per-project
  environments (source: ADR-055 section 8, owner-confirmed).
