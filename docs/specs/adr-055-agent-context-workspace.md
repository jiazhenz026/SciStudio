---
spec_id: adr-055-agent-context-workspace
title: "ADR-055 Spec 2 — Agent Context, Workspace Access, And Managed Execution Tools"
status: Draft
feature_branch: feat/2279-agent-context-workspace
created: 2026-09-05
input: "Owner-directed live session: author the ADR-055 implementation spec set under umbrella issue #2263. Spec 2 merges ADR-055 sections 5.1, 5.2, and 5.3 (owner decision: one spec). get_agent_context exposes the existing provisioned project assets with real paths; workspace tools reuse existing services rather than duplicating domain logic; run_command executes arbitrary code as an intended capability via asyncio subprocess registered in the ProcessRegistry for process-tree cancellation, with explicit project context and the bundled Python environment. All new tools register in the shared FastMCP registry with the external-audience tag per adr-055-webmcp-bridge; none are router-internal. Amended by the owner decisions of 2026-09-10 recorded on issue #2279: transfer moves to adr-055-lab-deployment; inspect tools read anything the backend OS user can read; author tools enforce a server-side blacklist mirroring the provisioned hooks; hook parity is surfaced in tool results; the shared write helper gains an optional expected state_version; managed command state is kept in memory and cleared on restart. Amended again on 2026-09-11 after the with-context (AU3) and no-context (AU4) audits: delete and move act on links as links; a command owns its whole job (Windows Job Object, POSIX process group) for cancel and shutdown; exit is detected apart from pipe EOF with a bounded drain; reads never advance a state version; searches are bounded by entries visited; and, by owner decision, failure outcomes carry isError: true."
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
  - adr-055-lab-deployment
scope:
  in:
    - "The `get_agent_context` tool over existing provisioned assets: project identity, effective guidance, an index of documentation and skills with real readable paths, the instance's execution environment and capabilities, and hook guidance with execution location made explicit."
    - "Workspace inspect tools: directory listing, metadata, file search, and bounded streaming reads. They accept absolute paths and read anything the backend's OS user can read; project-relative paths resolve against the active project (#2279 decision 2)."
    - "Workspace author tools: create, write, patch, rename/move, delete, confined to the active project, with explicit conflict handling, reusing the editor's atomic-write / UI-sync / block-reload path, and a server-side blacklist for `workflows/*.yaml|*.yml` and `data/` (#2279 decision 3). Delete and move act on a symlink or junction itself, never on what it points to."
    - "Hook parity for hosts that run no provisioned hooks, surfaced in tool results: list_blocks before block writes, concrete port type warnings, scistudio CLI denial, and the run_workflow poll reminder (#2279 decision 4)."
    - "The `run_command` execution tool: asyncio subprocess owning its whole job (Windows Job Object, POSIX process group) and registered in the backend's ProcessRegistry, explicit project context, bundled-Python environment contract, managed job lifecycle with separate status and cancellation, bounded output capture, and in-memory job state (#2279 decision 6)."
    - "Failure outcomes (refusals, conflicts, a command that exited non-zero, a cancel that did not stop the command) are tool results carrying `isError: true` (owner decision 2026-09-11)."
    - Bounded operation logging for all new tools (identifiers and outcomes, never full payloads).
    - Registration of all new tools in the shared FastMCP registry with the external-audience visibility tag from adr-055-webmcp-bridge.
  out:
    - The webmcp router, registration module, and session middleware (adr-055-webmcp-bridge).
    - "Transfer: the user-picked upload, the streaming download endpoint, inline transfer caps, and TransferRecord moved to adr-055-lab-deployment (#2279 decision 1). The only transfer use case is a lab-server backend with a laptop browser; local mode registers no upload/download tools."
    - "Workflow worker and grandchild process cleanup when the backend stops (tracked separately in #2281)."
    - "Provisioning changes: instructions, skills, hooks, and agent-reference assets already exist (ADR-040); this spec consumes them, it does not redesign them."
    - Automatic host-native hook execution or system-prompt installation (excluded by ADR-055 section 10).
    - "A new sandbox around arbitrary code (excluded by ADR-055 section 5.3: code runs with the user's ordinary permissions)."
    - Per-project Python environments (excluded by ADR-055 section 8).
    - AI-host presentation (deferred by the owner).
governs:
  modules:
    - scistudio.ai.agent.mcp.tools_qa
    - scistudio.ai.agent.mcp.tools_workspace
    - scistudio.ai.agent.mcp.tools_execution
    - scistudio.api.routes.projects
    - scistudio.api.runtime._file_writes
  contracts:
    - scistudio.ai.agent.mcp._context.get_context
  entry_points: []
  files:
    - docs/specs/adr-055-agent-context-workspace.md
    - src/scistudio/ai/agent/mcp/tools_qa.py
    - src/scistudio/ai/agent/mcp/tools_workspace.py
    - src/scistudio/ai/agent/mcp/tools_execution.py
    - src/scistudio/ai/agent/mcp/__init__.py
    - src/scistudio/ai/agent/mcp/_context.py
    - src/scistudio/ai/agent/mcp/tools_authoring.py
    - src/scistudio/ai/agent/mcp/tools_workflow/read.py
    - src/scistudio/ai/agent/mcp/tools_workflow/write.py
    - src/scistudio/api/app.py
    - src/scistudio/api/routes/projects.py
    - src/scistudio/api/routes/webmcp.py
    - src/scistudio/api/runtime/_file_writes.py
    - src/scistudio/api/runtime/__init__.py
    - src/scistudio/engine/runners/platform.py
    - src/scistudio/engine/runners/process_handle.py
  excludes: []
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - tests/ai/test_mcp_agent_context.py
  - tests/ai/test_mcp_workspace_tools.py
  - tests/ai/test_mcp_execution_tools.py
  - tests/ai/test_mcp_tools_workflow.py
  - tests/api/test_projects.py
acceptance_source: adr
language_source: en
---

# ADR-055 Spec 2 — Agent Context, Workspace Access, And Managed Execution Tools

## 1. Change Summary

This spec comes from ADR-055 (section 5) and umbrella issue #2263; the owner
merged the context, workspace, and execution surfaces into one spec. The owner
decisions of 2026-09-10, recorded on issue #2279, amend it, as do the fixes and
the owner decision that followed the with-context (AU3) and no-context (AU4)
audits of 2026-09-11. This text reflects them.

An external AI agent driving SciStudio through the webmcp bridge needs three
things a local CLI agent gets natively: the project's provisioned context
(instructions, docs, skills, hooks), access to the filesystem beside the
backend, and a way to run code. ADR-055 section 5 defines all three, and
section 9.2 records why the hackathon demo's versions are not production-ready:
reads collect fully before truncating, shell execution blocks the event loop
and ignores the process registry, shell calls can run with `cwd=None`, and
cancellation is half-wired.

This spec defines the production versions, with four structural rules:

1. **Real registry tools, tagged external.** Every new tool is a normal
   `@mcp.tool` in the shared registry carrying the `audience:external`
   visibility tag from `adr-055-webmcp-bridge`, so local agents (who have
   native file/shell capability) never see them and the router never grows
   if-chain dispatch.
2. **Reuse, not duplication.** Authoring runs the editor's atomic-write +
   UI-sync + block-reload path, extracted from the HTTP route into a shared
   helper; execution reuses the asyncio spawn + ProcessRegistry pattern, the
   platform Job Object support, and the desktop terminal's Python environment;
   the port-type check reuses the provisioned hook's own scanner.
3. **Bounded by construction.** Reads, searches, and command output are capped
   while they run, not after collection; logs carry identifiers and outcomes,
   never payloads.
4. **The provisioned hooks hold for hosts that run none.** A WebMCP host does
   not execute the project's hook scripts, so the rules they enforce locally
   are enforced by the server for the external tools and reported in tool
   results — as failures (`isError: true`) when they refuse.

The decisions that shape this text:

| # | Decision |
|---|---|
| 1 | Transfer (user-picked upload, streaming download endpoint, inline caps, TransferRecord) moves to `adr-055-lab-deployment`; local mode registers no upload/download tools. |
| 2 | Inspect tools read anything the backend's OS user can read; absolute paths are accepted and project-relative paths resolve against the active project. Reads stay bounded while streaming. |
| 3 | Author tools stay project-confined and refuse any mutation whose source or target is `workflows/*.yaml\|*.yml` (use `write_workflow` / `update_block_config`) or under `data/` (use `run_workflow`). Backend runtime writes into `data/` are unaffected. |
| 4 | Hook parity in tool results: list_blocks-before-block-write (once per backend lifetime, and for `scaffold_block` through the bridge), concrete port type warnings, scistudio CLI denial in `run_command`, and an additive `run_workflow` poll hint. |
| 5 | The shared write helper gains an optional expected `state_version`; the editor PUT route's observable behavior is unchanged. |
| 6 | Managed command status, exit state, and bounded output tail live in memory and are cleared on backend restart; `run_command` processes register in the app ProcessRegistry so backend shutdown (`terminate_all`) covers them. |
| 7 | Failure outcomes — refusals (blacklist, list_blocks-first, CLI denial, and every other policy refusal), write conflicts, a command that ended with a non-zero exit, and a cancel that did not stop the command — are returned as tool results with `isError: true`, keeping status, refusal code, message, and alternatives in the structured content (owner decision 2026-09-11, audits AU3 P2-3 / AU4 P3-5). |

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
`.scistudio/agent-reference/`, skills directories, hook scripts) with paths
that resolve; the docs index matches the real `docs/` tree; every retrieval
instruction works with the tool it names; hook guidance states where hooks
execute and where the server does and does not enforce them. Then delete one
asset class and assert the response reports its absence accurately instead of
fabricating an index.

**Acceptance Scenarios**:

1. **Given** a newly created project, **When** `get_agent_context` is called,
   **Then** the response includes project identity, the effective guidance
   summary, and an index whose entries point to paths that exist on disk.
2. **Given** a project whose `.scistudio/agent-reference/` is missing, **When**
   the tool is called, **Then** the response reports that asset class as
   unavailable with an accurate diagnostic, and the rest of the index is
   unaffected.
3. **Given** any project, **When** the response describes hooks, **Then** it
   states their execution location explicitly, never claims the host executed
   them, and names the server-side equivalent of each — including where there
   is none (`run_command` does not re-check command text; the `scaffold_block`
   rule applies to bridge calls only).
4. **Given** no open project, **When** the tool is called, **Then** it returns
   a refusal (`no_active_project`) flagged as an error, never a default index.

### User Story 2 - The agent inspects anything it may read and authors project files with UI sync (Priority: P1)

The external agent lists directories, reads files in bounded ranges — inside
the project or anywhere else the backend's user can read, such as a shared
dataset directory used in place — and creates or modifies project files. Every
write lands through the same atomic-write and file-change-notification path the
editor uses, so the open UI reflects the change.

**Why this priority**: Authoring is the core external-agent capability;
writes that bypass the notification path silently desynchronize the user's UI
(ADR-055 section 5.2: "the browser remains a view of backend state").

**Independent Test**: Through the registry, list a project directory, read a
file with an offset/limit that crosses the read cap, read a file outside the
project by absolute path, then write a new file and patch an existing one;
assert the read never pulled more than the cap from disk, the writes are atomic
(no partial states observable), a file-changed event reaches the event bus
through the shared helper, a write based on a state version the file has moved
past is rejected with an explicit conflict result, and a read never stops the
watcher from delivering an external edit to the UI.

**Acceptance Scenarios**:

1. **Given** a project with nested directories, **When** the inspect tools run
   with project-relative paths, **Then** listing, metadata, and search results
   are project-relative; **and when** they run with an absolute path outside
   the project, **Then** they read it in place under the backend user's
   filesystem permissions, reporting absolute paths.
2. **Given** a 5 MB text file, **When** it is read with default bounds,
   **Then** the response contains at most the capped byte range plus an
   accurate truncation marker with total size, and the implementation never
   reads the rest of the file to produce it.
3. **Given** a file the agent read at state version N, **When** the file
   changed on disk and the agent writes based on version N, **Then** the write
   is rejected with an explicit conflict result naming the condition, and the
   file keeps the other writer's content.
4. **Given** any author tool, **When** its path escapes the project (absolute
   path elsewhere, `..` traversal, a symlink out), **Then** it is refused and
   nothing changes on disk.
5. **Given** a symlink or junction in the project, **When** it is deleted or
   moved, **Then** the link itself is deleted or moved and what it points to —
   inside the project, under `data/`, or outside the project — is untouched.
6. **Given** an external edit not yet delivered by the watcher, **When** the
   agent reads the file, **Then** the watcher still delivers the edit to the
   UI afterwards.

### User Story 3 - The provisioned hooks hold for a host that runs none (Priority: P1)

A WebMCP host does not execute `.claude/hooks/*.py`. The rules those hooks
enforce for local CLI agents are enforced by the server for the external
tools, and every refusal or advisory comes back in the tool result with the
tool to use instead.

**Why this priority**: Without parity an external agent can hand-edit
workflow YAML past schema validation, rewrite scientific data, skip the
block-reuse check, or drive the CLI past the GUI and lineage — the exact
failures the hooks exist to prevent (ADR-040 §3.6).

**Independent Test**: Through the bridge, attempt each guarded operation and
assert the explanatory refusal flagged as an error; then satisfy the
precondition and assert the operation succeeds; assert the local transport's
behavior for `scaffold_block` is unchanged.

**Acceptance Scenarios**:

1. **Given** any author tool, **When** the path being mutated — or, for a
   directory operation, any file inside it — is `workflows/*.yaml|*.yml` or
   under `data/` (including a rename or move into or out of `data/`), **Then**
   the call is refused with a pointer to `write_workflow` / `update_block_config`
   or `run_workflow`, and nothing changes. A write through a link is checked
   against the file it changes; a delete or move of a link is checked against
   the link.
2. **Given** a backend on which `list_blocks` has not run, **When** an author
   tool would write a `blocks/*.py` file, or `scaffold_block` is called through
   the bridge, **Then** the result is an explanatory refusal; **after**
   `list_blocks` runs once — through any transport — the same call succeeds;
   **after** a backend restart the requirement applies again. `scaffold_block`
   through the local transport behaves as before.
3. **Given** an author-tool write to `blocks/*.py` whose `InputPort`/`OutputPort`
   constructors use a generic `DataObject` or empty `accepted_types`, **When**
   the write succeeds, **Then** the result carries a non-blocking warning.
4. **Given** a command that invokes the `scistudio` CLI — directly, quoted,
   through a launcher (`nohup`, `nice`, `timeout`, `start /b`, `env -i`,
   `xargs`), a shell wrapper (`sh -c`, `bash -c`, `cmd /c`), or the Python
   module forms — **When** it is passed to `run_command`, **Then** it is
   refused and the result names the MCP alternatives.
5. **Given** a `run_workflow` call, **When** it returns, **Then** the result
   carries an additive hint to poll `get_run_status` until the run is
   terminal, and every existing field is unchanged.

### User Story 4 - Arbitrary code runs managed, cancellable, and in the right environment (Priority: P1)

`run_command` executes user-authorized arbitrary code with the instance's
ordinary permissions: asyncio-spawned, owning every process it starts,
registered in the backend's ProcessRegistry, bound to an explicit project
context, and resolving the bundled Python and user dependency locations so a
package the agent installs is the package SciStudio later uses.

**Why this priority**: ADR-055 section 5.3 declares arbitrary code an intended
capability; the demo's synchronous `subprocess.run` blocked the event loop,
ignored cancellation, and could run with `cwd=None` — all three are
correctness failures for a shared async server.

**Independent Test**: Start a long-running command that spawns children;
while it runs, verify the event loop stays responsive (a sibling task keeps
its schedule); cancel it and assert the whole process tree terminates and the
registry no longer tracks it — also when an intermediate process has already
exited and when a background process holds the output pipes; run
`python -c "import sys; print(sys.executable)"` and assert the bundled
interpreter; install a package through `run_command` and assert a subsequent
SciStudio-side import resolves it.

**Acceptance Scenarios**:

1. **Given** a command that sleeps with child processes, **When** cancellation
   is requested, **Then** the process tree is terminated, the tool reports the
   terminal state, and the ProcessRegistry shows no residue.
2. **Given** a command whose child starts a long-lived grandchild and then
   exits, **When** cancellation is requested, **Then** the grandchild is
   terminated too (Windows does not reparent orphans; the Job Object holds
   them).
3. **Given** a long-running command, **When** a sibling request arrives,
   **Then** it completes without waiting for the command (no event-loop
   blocking).
4. **Given** no active project, **When** `run_command` is invoked, **Then** it
   fails with an explicit absent-context result instead of running with an
   undefined working directory.
5. **Given** a pip install through `run_command`, **When** SciStudio code later
   imports the package, **Then** both resolve the same user dependency
   location (environment is explicit and shared).
6. **Given** a running command — or an exited command whose background process
   still runs — **When** the backend shuts down, **Then** the lifespan's
   `terminate_all` stops it, because the command stays registered while any of
   its processes lives.
7. **Given** a command that exits while a background process it started holds
   stdout/stderr, **When** it exits, **Then** the job is reported exited
   promptly, with a note that output may be incomplete and a flag that
   background processes are still running.

### User Story 5 - Job lifecycle outlives the browser request (Priority: P2)

A long operation started through a tool survives the originating HTTP request
ending: request cancellation and job cancellation are distinct, and job status,
output, and cancellation remain reachable through managed lifecycle behavior.

**Why this priority**: ADR-055 section 5.3: "a browser request timeout is
distinct from terminating a job and its child processes" — collapsing the two
either kills long analyses on disconnect or leaves orphans.

**Independent Test**: Start a managed long command through the bridge, let the
HTTP client give up mid-request, and assert the job keeps running and remains
observable (it can be found with `list_commands`, by label) and cancellable;
then cancel the job and assert terminal state and process-tree cleanup.

**Acceptance Scenarios**:

1. **Given** a running managed command, **When** the originating request is
   aborted, **Then** the job continues and a later status call reports it
   accurately.
2. **Given** the same job, **When** job cancellation is issued, **Then** the
   process tree terminates and the final status is terminal and accurate.
3. **Given** a backend restart, **When** the agent asks for an earlier job,
   **Then** the result says job state is kept in memory only and was cleared.

### Edge Cases

- Read bounds exceeding file size: return what exists with an accurate
  truncation marker; never error solely for a large limit (limits above the
  maximum window are clamped and the applied limit is reported).
- A read window that starts or ends inside a multi-byte UTF-8 character:
  leading continuation bytes are skipped (the reported offset moves), an
  incomplete trailing sequence is held back, and `next_offset` resumes on a
  character boundary.
- Binary files through text-read tools: declared detection (NUL bytes or
  invalid UTF-8) and refusal with code `binary_content`; a bounded raw slice is
  available with `encoding='base64'`. No mojibake-as-success.
- Special files (FIFOs, sockets, devices): `read_file` refuses them
  (`special_file`) instead of blocking a worker thread; searches skip them.
- A search rooted at a huge tree (`/`, a network share): the walk stops after
  a fixed number of directory entries visited — matching or not — or a time
  budget, reports which bound applied, never follows links, and stops when its
  request ends. The budget and the request's end are checked between the lines
  of a file as well as between entries, so one slow file cannot outlive them.
- A content regular expression is matched in a separate, stdlib-only Python
  process: a backtracking match (`(a+)+$`, or `.*.*.*x`, which nests nothing)
  can run for hours on one line and cannot be interrupted in-process, so no
  bound on the pattern or the line holds. The search kills that process when
  the time budget runs out or the request ends and reports the time budget
  (or the request's end) as the bound that applied. If the process cannot
  start, the search is refused (`regex_unavailable`).
- The version a read reports is taken before its content, so a write based on
  it conflicts rather than overwriting content the reader never saw.
- Writes to `blocks/`, `types/` follow the existing drop-in semantics (a
  lint-clean save rebuilds the registries) — the reuse rule makes this
  automatic.
- Delete/rename of a path the UI has open: a `deleted` file-changed event fires
  at the old path (and `created` at the new one for a move); the result lists
  the affected paths; UI reaction is out of scope here.
- Links: deleting or moving a symlink or junction acts on the link; a tree
  delete or move never descends through a link inside the tree.
- A directory delete or move touching more than 2000 files is refused; bulk
  reorganization belongs to `run_command`.
- A refused write or move leaves nothing behind: preconditions are checked
  before any parent directory is created.
- Two writes based on the same state version: exactly one succeeds; the other
  is a `stale_version` conflict. The check, the disk change, and the version
  advance run under one per-project lock.
- Output exactly at the cap: the marker is unambiguous about whether
  truncation occurred (a one-byte probe for reads; total byte counts for
  command output).
- Concurrent `run_command` invocations: each is an independent registry entry;
  no shared mutable execution state.
- A command whose background process keeps its output pipes open after the
  command exits: the job is reported exited after a bounded drain, with a note
  that output may be incomplete; the background process stays under the job
  until it ends, `cancel_command` stops it, or the backend shuts down.
- Windows: the command string runs in the command processor, Python children
  write UTF-8 to their pipes (`PYTHONIOENCODING`), and every command runs in a
  Job Object. The command processor is created suspended, placed in the Job
  Object, then resumed, so no process escapes the job. If the Job Object cannot
  be created or the command cannot be placed in it or resumed, the command is
  refused (`job_object_unavailable`, flagged as an error) and nothing runs.
- POSIX: a descendant that leaves the command's process group (`setsid`,
  daemonizing) is outside the job, as with any process group.
- `get_agent_context` on an instance with no active project: explicit
  absent-context refusal (never a project-less "default" index).

## 3. Requirements

### Functional Requirements

- **FR-001**: `get_agent_context` MUST return a bounded initial response
  covering: project identity and active context; effective SciStudio/project
  guidance; an index of documentation and skills with real readable paths
  (project `docs/`, `.scistudio/agent-reference/`, host-specific skills
  directories, hook scripts); the instance's execution environment and access
  capabilities; and hook guidance with execution location explicit and each
  hook's server-side equivalent stated accurately (including where there is
  none). Detailed content stays in its files and is fetched through the
  appropriate existing tool.
- **FR-002**: The context index MUST NOT redirect every resource to `get_doc`
  and MUST NOT depend on copied-into-`docs/` assets (demo anti-pattern); each
  entry names its retrieval path (existing documentation tool for `docs/`,
  workspace read for the rest). A missing asset class MUST be reported with a
  diagnostic, not fabricated.
- **FR-003**: All new tools MUST register in the shared FastMCP registry with
  the `audience:external` tag, `read`/`write` tags matching whether they
  mutate, and Pydantic result models. Policy refusals and conflicts MUST be
  results (a `status` and a `refusal` with a code, message, and the tools to
  use instead), because the bridge withholds exception text from external
  hosts. Failure outcomes — every refusal, every conflict, a command that ended
  with a non-zero exit, and a cancel that did not stop the command — MUST carry
  the MCP error flag (`isError: true`) with the structured content intact,
  through the Spec 1 bridge adapter and on native MCP transports (owner
  decision 2026-09-11). Unexpected failures follow the existing
  raise-and-adapt convention.
- **FR-004**: Inspect tools (list/metadata/search/read) MUST accept absolute
  paths and read anything the backend's OS user can read, resolve
  project-relative paths against the active project (refusing a relative path
  when no project is open), and bound every read while streaming with an
  accurate truncation marker carrying total size. Searches MUST be bounded by
  the number of directory entries visited (matching or not), a time budget,
  and bytes per file, MUST NOT follow links, MUST stop when their request ends,
  and MUST report which bound applied. The time budget and the request's end
  MUST be enforced while a file's content is scanned, including while a content
  regular expression is being matched: a match still running when either fires
  MUST be stopped. Special files MUST NOT be opened.
- **FR-005**: Author tools (create/write/patch/rename-move/delete) MUST be
  confined to the active project and MUST reuse the editor's write path —
  atomic write, `FILE_CHANGED` event emission, and post-save block reload —
  extracted from `api/routes/projects.py` into a shared helper both the route
  and the tools call. The helper MUST accept an optional expected
  `state_version` and reject a stale write explicitly (stale-version,
  missing-file, and already-exists conditions named in the result); the editor
  PUT route MUST keep its observable behavior when the field is absent. Only a
  real write MAY advance a state version: a read or a conflict check MUST NOT,
  because advancing records the new disk state as seen and the watcher would
  then drop the external edit's `file.changed` (ADR-045 §3.3). Preconditions
  MUST be checked before any parent directory is created. The expected-version
  check, the disk change, and the version advance MUST form one critical
  section, so two writes based on the same state version cannot both succeed.
- **FR-006**: Author tools MUST refuse any mutation whose path — or, for a
  directory operation, any file it touches — is `workflows/*.yaml|*.yml`
  (pointing to `write_workflow` / `update_block_config`) or under `data/`
  (pointing to `run_workflow`). Confinement and the blacklist MUST evaluate the
  path actually being mutated: for a write, the file a link points to; for a
  delete or move, the link itself (lstat semantics). Delete and move MUST NOT
  follow a link to delete or move what it points to, and a tree operation MUST
  NOT descend through a link inside the tree. Backend runtime writes into
  `data/` are unaffected.
- **FR-007**: Hook parity MUST be surfaced in tool results: (a) an author-tool
  write to `blocks/*.py`, and `scaffold_block` when invoked through the bridge,
  MUST return an explanatory refusal until `list_blocks` has been called at
  least once in the current backend lifetime (reset on restart; `list_blocks`
  marks it from any transport; local-transport `scaffold_block` unchanged);
  (b) a successful author-tool write to `blocks/*.py` MUST carry non-blocking
  warnings for `InputPort`/`OutputPort` constructors using a generic
  `DataObject` or empty `accepted_types`, using the provisioned
  `enforce_concrete_port_types` scanner rather than a copy; (c) `run_command`
  MUST refuse commands invoking the `scistudio` CLI (the provisioned
  `deny_scistudio_cli` pattern, applied per shell segment and through common
  launchers, shell wrappers, and the Python module forms), naming the MCP
  alternatives — parity with the hook, not containment; (d) the `run_workflow`
  result MUST carry an additive hint to poll `get_run_status` until terminal,
  with every existing field unchanged.
- **FR-008**: Authorized shared datasets MUST be usable in place through
  filesystem permissions; tools MUST NOT copy them into the project.
- **FR-009**: `run_command` MUST spawn through asyncio subprocesses (never
  synchronous `subprocess.run` in the request path) in a new process group,
  own every process the command starts — a Windows Job Object the command
  joins before it runs anything (a command that cannot join one is refused and
  never runs); on POSIX the command's process group, which still names every
  descendant after the shell is reaped, stopped without reaping the shell that
  asyncio owns — register the command in the backend ProcessRegistry that the
  lifespan's shutdown `terminate_all` runs on for as long as any of its
  processes lives, support whole-job cancellation (including descendants whose
  parent already exited), and fail with an explicit absent-context result when
  no project is active.
- **FR-010**: The execution environment MUST be explicit: working directory
  and `SCISTUDIO_PROJECT_DIR` bound to the active project (as worker processes
  receive it), and the desktop Python terminal's environment — SciStudio's
  `python`/`pip` wrappers first on `PATH`, `PIP_TARGET` at the shared user
  dependency site that SciStudio's registries and workers import from — so
  install-then-use resolves to the intended runtime. Credentials the backend
  exports for its own workers (`SCISTUDIO_ENGINE_IPC_TOKEN`) MUST NOT be passed
  to commands.
- **FR-011**: Command output collection MUST be bounded during capture (not
  clipped after the fact) with accurate totals and truncation flags. A
  command's exit MUST be detected from the process, not from pipe EOF; output
  then drains for a bounded grace period, after which the job is reported
  exited, with a note and flags when output may be incomplete or background
  processes still run. Every command MUST be a managed job whose status and
  cancellation are separate tools, independent of the originating request, with
  a way to find jobs whose starting request ended (a listing with labels and
  command previews). Job state (status, exit state, bounded output tails) MUST
  live in memory and be cleared on backend restart.
- **FR-012**: Tool logging MUST record operation identifiers and outcomes only;
  file contents, command bodies, file names, and full arguments MUST NOT be
  logged by the tools or the shared write path.

### Key Entities

- **WriteConflict**: the condition (`stale_version`, `missing_file`,
  `already_exists`, `missing_parent`, `is_directory`, `directory_not_empty`,
  `too_many_entries`), the entity, and the expected and current state
  versions; returned by the shared helper and surfaced as a `conflict` result
  flagged as an error (or a 409 from the editor route when it supplied an
  expected version).
- **ManagedCommand**: job identifier, optional label, command preview, project
  binding, process id, the job's process ownership (Job Object or process
  group), state (`running`, `exited`, `cancelled`), exit code, bounded
  stdout/stderr tails with total byte counts and truncation flags, and whether
  output is incomplete or background processes still run; backed by the
  ProcessRegistry entry while any of its processes lives; in memory only.
- **ToolRefusal**: machine-readable code, message, and the tools to use
  instead; the result shape for every policy refusal and conflict, carried
  with `isError: true`.

## 4. Implementation Plan

### 4.1 Technical Approach

**Shared write path.** The atomic-write + `file.changed` + lint-gated block
reload trio moves from `api/routes/projects.py` into
`src/scistudio/api/runtime/_file_writes.py` (`write_project_file`), with
`delete_project_path` and `move_project_path` built from the same pieces. The
editor route calls `write_project_file` and keeps its names importable. The
`ai` layer may not import `api` (import-linter "AI must not depend on api"), so
the tools reach the path through the MCP context: `ApiRuntime.project_files` is
a `ProjectFileService` bound to the runtime, and the lifespan's MCP context
adapter exposes it as `MCPContext.project_files`. The `ai` side declares only a
structural `ProjectFileWriter` Protocol and a `get_project_files(ctx)` accessor;
a context without it (the standalone bridge, a unit-test stub) makes author
tools refuse rather than write around the path. Version lookups are
compare-only: an external edit the watcher has not delivered yet (disk mtime
newer than the cached disk version) is projected as current + 1 — the version
the watcher will assign — so a conflict check still sees it while the watcher
still delivers it. A real write first absorbs such a pending edit, then emits
its own event. Disk work — the atomic write, tree walks and removal, and the
ruff lint subprocess — runs in worker threads; registry rebuilds stay on the
event loop, as in the editor route. Each write, delete, and move holds a
per-project `asyncio.Lock` (`project_mutation_lock`) from its precondition
check through its version advance. Confinement — the editor route's
`_resolve_project_file` and `confine_to_project` alike — resolves the path and
requires it to start with the project root plus a separator before any
filesystem call uses it, the guard CodeQL's `py/path-injection` query models.

**Links.** Author tools and the service resolve only the parent directories of
a delete or move target, so the path they confine, check, and change is the
link itself; `is_link` recognizes symlinks and Windows junctions (reparse
points tagged mount point or symlink) without following them, `remove_link`
removes a link (unlink, or rmdir for a Windows directory link), and tree walks
treat a link as one entry. Writes follow links to the file they change and
check that file.

**Context tool.** `get_agent_context` lives in `tools_qa.py` beside
`get_project_info`, `get_doc`, and `search_docs`, reading the provisioning
outputs of `agent_provisioning` via `get_context().project_dir`; it assembles a
bounded index (capped entries per asset class) and marks each entry with its
retrieval tool.

**Workspace tools** live in `tools_workspace.py`. Reads use a buffer sized to
the window, filled in chunks, plus a one-byte probe, and take the state version
before the content; searches walk with their own scanner bounded by entries
visited and a time budget and honor a stop flag the tool sets when its request
ends, checking both between entries and between the lines of a file; a regular
expression is matched in one stdlib-only child interpreter per search
(`python -I -S -c`), fed one file's lines per request, which the search thread
kills when the deadline passes or the stop flag is set (a kill-on-close Job
Object on Windows and `SIGALRM` on POSIX end it if the backend dies first);
filesystem work runs in threads so the event loop stays free.

**Failure flag.** A FastMCP call-tool middleware registered with the shared
registry sets the MCP error flag on the results of tools that registered a
failure rule: refusals and conflicts for the workspace tools,
`get_agent_context`, and `scaffold_block`; additionally a non-zero exit for
`run_command` / `get_command_status` and a cancel that left processes running
for `cancel_command`. The result stays a result — a `ToolResult` subclass
carrying `is_error`, which the Spec 1 adapter already propagates as `isError`
and which native MCP transports receive in `CallToolResult.isError` — so the
structured reason survives the bridge.

**Hook parity.** `list_blocks` sets a backend-lifetime flag in
`tools_workflow/read.py`; author tools consult it, and `scaffold_block`
consults it only when the WebMCP route has marked the dispatch as a bridge call
(a context variable set around `mcp.call_tool`; background tasks a dispatch
spawns run in a copy of the context with the marker cleared). The port-type
warning loads the provisioned `hook_enforce_concrete_port_types.py` template
through the provisioning loader and runs its scanner. `run_workflow` returns a
subclass of its result model adding `poll_hint`.

**Execution.** `run_command` in `tools_execution.py` follows the
`LocalRunner._spawn_worker` pattern: POSIX spawns `/bin/sh -c` through
`asyncio.create_subprocess_exec` with a new session; Windows runs the command
processor through `asyncio.create_subprocess_shell` with a new process group
and no console window (CreateProcess quoting would corrupt a command string
passed to `create_subprocess_exec("cmd.exe", "/c", ...)`), created suspended,
assigned to a Job Object with kill-on-close, then resumed
(`PlatformOps.create_job_object` / `assign_to_job`, plus the new
`resume_process`, `terminate_job_object`, `job_active_process_count`, and
`close_job_object`); a failed step kills the suspended process and refuses the
call. The POSIX process group is stopped by polling its members without
waiting on them, so the shell stays asyncio's to reap. The command registers a
`ProcessHandle` subclass in the ProcessRegistry the context exposes as
`MCPContext.process_registry` (the lifespan's `app.state.registry`): its
`terminate` stops the whole job (Job Object, or the POSIX process group with
members verified by start time), and it overrides the new
`ProcessHandle.owns_live_process` hook so `terminate_all` still reaches it
after the shell has exited. A supervisor task, not the request, owns each job:
it detects exit from `returncode` (asyncio's `Process.wait()` resolves only
after every pipe closes), drains output for a bounded grace period, records the
terminal state, and keeps the job registered until none of its processes is
alive. Cancellation runs in a thread. The environment is `desktop/paths.py`'s
`user_python_terminal_env` plus the project binding.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/api/runtime/_file_writes.py` | create | Shared write path, link-safe delete/move, compare-only versions, `ProjectFileService` |
| `src/scistudio/api/runtime/__init__.py` | modify | `ApiRuntime.project_files` |
| `src/scistudio/api/routes/projects.py` | modify | PUT route uses the shared helper; optional `expected_state_version` |
| `src/scistudio/api/app.py` | modify | Context adapter exposes `project_files` and `process_registry` (two members) |
| `src/scistudio/api/routes/webmcp.py` | modify | Bridge-call marker around dispatch |
| `src/scistudio/engine/runners/platform.py` | modify | Job Object terminate / count / close (POSIX no-ops) |
| `src/scistudio/engine/runners/process_handle.py` | modify | `ProcessHandle.owns_live_process` hook used by `terminate_all` |
| `src/scistudio/ai/agent/mcp/_context.py` | modify | Optional capability Protocols/accessors; bridge-call marker and its detached copy |
| `src/scistudio/ai/agent/mcp/tools_qa.py` | modify | `get_agent_context` |
| `src/scistudio/ai/agent/mcp/tools_workspace.py` | create | Inspect and author tools; failure-flag middleware |
| `src/scistudio/ai/agent/mcp/tools_execution.py` | create | `run_command` + managed job tools |
| `src/scistudio/ai/agent/mcp/tools_workflow/read.py` | modify | `list_blocks` backend-lifetime flag |
| `src/scistudio/ai/agent/mcp/tools_workflow/write.py` | modify | Additive `run_workflow` poll hint |
| `src/scistudio/ai/agent/mcp/tools_authoring.py` | modify | `scaffold_block` bridge check |
| `src/scistudio/ai/agent/mcp/__init__.py` | modify | Import new tool modules (registration) |
| `tests/ai/test_mcp_agent_context.py` | create | Context tool over provisioned fixtures |
| `tests/ai/test_mcp_workspace_tools.py` | create | Inspect/author behavior, bounds, links, blacklist, hook parity, failure flag |
| `tests/ai/test_mcp_execution_tools.py` | create | Execution, whole-job cancellation, shutdown, HTTP abort, environment, failure flag |
| `tests/ai/test_mcp_tools_workflow.py` | modify | `run_workflow` poll hint |
| `tests/ai/test_mcp_fastmcp.py`, `tests/ai/test_finish_ai_block_skeleton.py`, `tests/contracts/test_runtime_import_contract.py` | modify | Registry tool set |
| `tests/api/test_projects.py` | modify | Route/helper parity, expected state version, compare-only versions |

### 4.3 Implementation Sequence

1. **T-001** (foundation): extract the shared write helper from
   `projects.py`; route + helper parity tests; optional expected
   `state_version`.
2. **T-002** (US1): `get_agent_context` + provisioning-fixture tests.
3. **T-003** (US2/US3): `tools_workspace.py` inspect/author tools, blacklist,
   link semantics, and block hook parity + bounds, conflict, and parity tests.
4. **T-004** (US4/US5): `tools_execution.py` + Job Object / process-group
   ownership + registry integration + CLI denial + cancellation,
   responsiveness, shutdown, HTTP-abort, and environment tests.
5. **T-005** (US3): additive `run_workflow` poll hint.
6. **T-006** (cross-cutting): failure flag, bounded logging, audience tags
   verified through both catalogues, spec text (this spec amended; transfer
   moved to `adr-055-lab-deployment`).

### 4.4 Verification Plan

- Registry-level tests for every new tool (no browser required), covering the
  acceptance scenarios above; author tools run through the real bridge route so
  the production context adapter, event emission, and the failure flag through
  the Spec 1 adapter are exercised.
- Boundedness checks on fixtures at least four times the cap: a read pulls at
  most the window plus a one-byte probe from disk; command output keeps at
  most the tail cap; a search over non-matching files stops at the visit cap.
- Link tests with directory and file links, and links into `data/`,
  `workflows/`, and outside the project: POSIX symlinks on CI's Linux runner;
  on Windows, junctions (no privilege needed), with file symlinks skipped when
  the host lacks the privilege.
- Watcher interplay: the real `_ProjectFileHandler` still emits after a read,
  in both orders.
- Concurrency tests: a long `run_command` while a sibling task keeps schedule;
  two concurrent commands as independent registry entries.
- Whole-job cancellation with an all-alive chain, with an exited intermediate
  (orphaned grandchild), and with a background process holding the pipes; zero
  registry residue; a real HTTP client aborting mid-call through a live server;
  lifespan shutdown stopping a background process of an exited command.
- Install-then-import parity: always via the stdlib check (a module written to
  the command's `PIP_TARGET` imports on both sides); additionally via an
  offline wheel `pip install` when the interpreter ships pip (CI's
  setup-python interpreter does; uv-managed venvs do not, and the test says so
  when it skips).
- Existing suites (`tests/api/test_projects.py`, `tests/api/test_file_endpoints.py`,
  `tests/api/test_reload_on_save.py`, `tests/engine/test_process_handle.py`,
  the webmcp bridge suite) pass unchanged.
- `gate_record check` tier-selected checks on the committed diff.

### 4.5 Risks And Rollback

- Risk: extracting the write helper changes editor save behavior. Mitigation:
  the route keeps its checks and error details; the existing route suites pass
  unchanged; parity tests pin that the route runs the helper.
- Risk: arbitrary-code capability is abused through a compromised host.
  Mitigation: this is an ADR-decided intended capability with the user's
  ordinary permissions; the bridge session substrate (spec 1) is the boundary;
  logging policy preserves auditability. The author-tool blacklist mirrors the
  hooks for the file tools; it is parity, not a sandbox — `run_command` can
  still change any file the user can, by design.
- Risk: the OS-user read scope exposes files outside the project to the host.
  Mitigation: owner decision 2 accepts it (reads are what the user's own shell
  could do); the bridge session substrate authenticates every call.
- Risk: a process escapes its job (POSIX `setsid`). Mitigation: documented
  edge case; on Windows the suspended start leaves no window before Job Object
  assignment; workflow-worker orphan cleanup is tracked in #2281.
- Rollback: new modules are additive; the extracted helper is
  behavior-preserving; the platform and registry additions are opt-in hooks
  whose defaults keep existing behavior; revert restores current behavior with
  no migration.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: `get_agent_context` on a freshly provisioned project returns an
  index whose every listed path resolves on disk; missing-asset diagnostics are
  accurate in 100% of fixture cases.
- **SC-002**: No read, search, or command-output path holds more than the
  configured cap plus one chunk in memory, measured on fixtures ≥ 4× the cap.
- **SC-003**: 100% of tool-authored writes emit the file-changed event and pass
  through the atomic write path (asserted via the shared helper, not
  re-implemented).
- **SC-004**: A cancelled managed command leaves zero live descendant processes
  and zero registry residue in 100% of test runs on all supported platforms,
  including descendants whose parent exited and background processes holding
  the pipes.
- **SC-005**: A package installed through `run_command` is importable by the
  SciStudio runtime in the same instance, in the verification environment.
- **SC-006**: 100% of blacklisted author mutations (`workflows/*.yaml|*.yml`,
  `data/`, as source or target) are refused with nothing changed on disk, and
  100% of link deletes and moves leave the link's target untouched.
- **SC-007**: 100% of failure outcomes reach the host as `isError: true` with
  their structured reason intact.

## 6. Assumptions

- External agents have no filesystem access except these tools; local agents
  keep using their native capabilities and never see the external-tagged tools
  (source: owner session, 2026-09-05).
- Reading anywhere the backend's OS user can read is the intended inspect scope
  (source: #2279 decision 2).
- Arbitrary code executes with the user's ordinary OS permissions and no
  additional sandbox (source: ADR-055 section 5.3).
- One environment per user, shared by that user's projects; no per-project
  environments (source: ADR-055 section 8, owner-confirmed).
- File transfer between a laptop browser and a lab-server backend is specified
  in `adr-055-lab-deployment` (source: #2279 decision 1).
- Failure outcomes are errors for the host (source: owner decision 2026-09-11).
