---
spec_id: adr-055-agent-context-workspace
title: "ADR-055 Spec 2 — Agent Context, Workspace Access, And Managed Execution Tools"
status: Draft
feature_branch: docs/2263-adr-055-specs
created: 2026-09-05
input: "Owner-directed live session: author the ADR-055 implementation spec set under umbrella issue #2263. Spec 2 merges ADR-055 sections 5.1, 5.2, and 5.3 (owner decision: one spec). get_agent_context exposes the existing provisioned project assets with real paths; workspace tools reuse existing services rather than duplicating domain logic; run_command executes arbitrary code as an intended capability via asyncio subprocess registered in the ProcessRegistry for process-tree cancellation, with explicit project context and the bundled Python environment. All new tools register in the shared FastMCP registry with the external-audience tag per adr-055-webmcp-bridge; none are router-internal. Amended by the owner decisions of 2026-09-10 recorded on issue #2279: transfer moves to adr-055-lab-deployment; inspect tools read anything the backend OS user can read; author tools enforce a server-side blacklist mirroring the provisioned hooks; hook parity is surfaced in tool results; the shared write helper gains an optional expected state_version; managed command state is kept in memory and cleared on restart."
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
    - "Workspace author tools: create, write, patch, rename/move, delete, confined to the active project, with explicit conflict handling, reusing the editor's atomic-write / UI-sync / block-reload path, and a server-side blacklist for `workflows/*.yaml|*.yml` and `data/` (#2279 decision 3)."
    - "Hook parity for hosts that run no provisioned hooks, surfaced in tool results: list_blocks before block writes, concrete port type warnings, scistudio CLI denial, and the run_workflow poll reminder (#2279 decision 4)."
    - "The `run_command` execution tool: asyncio subprocess registered in the backend's ProcessRegistry, explicit project context, bundled-Python environment contract, managed job lifecycle with separate status and cancellation, bounded output capture, and in-memory job state (#2279 decision 6)."
    - Bounded operation logging for all new tools (identifiers and outcomes, never full payloads).
    - Registration of all new tools in the shared FastMCP registry with the external-audience visibility tag from adr-055-webmcp-bridge.
  out:
    - The webmcp router, registration module, and session middleware (adr-055-webmcp-bridge).
    - "Transfer: the user-picked upload, the streaming download endpoint, inline transfer caps, and TransferRecord moved to adr-055-lab-deployment (#2279 decision 1). The only transfer use case is a lab-server backend with a laptop browser; local mode registers no upload/download tools."
    - "Worker and grandchild process cleanup when the backend stops (tracked separately in #2281)."
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
    - src/scistudio/api/routes/projects.py
    - src/scistudio/api/runtime/_file_writes.py
    - src/scistudio/api/runtime/__init__.py
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
decisions of 2026-09-10, recorded on issue #2279, amend it; this text reflects
them.

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
   helper; execution reuses the asyncio spawn + ProcessRegistry pattern and the
   desktop terminal's Python environment; the port-type check reuses the
   provisioned hook's own scanner.
3. **Bounded by construction.** Reads and command output are capped while
   streaming, not after collection; logs carry identifiers and outcomes, never
   payloads.
4. **The provisioned hooks hold for hosts that run none.** A WebMCP host does
   not execute the project's hook scripts, so the rules they enforce locally
   are enforced by the server and reported in tool results.

The #2279 decisions that shape this text:

| # | Decision |
|---|---|
| 1 | Transfer (user-picked upload, streaming download endpoint, inline caps, TransferRecord) moves to `adr-055-lab-deployment`; local mode registers no upload/download tools. |
| 2 | Inspect tools read anything the backend's OS user can read; absolute paths are accepted and project-relative paths resolve against the active project. Reads stay bounded while streaming. |
| 3 | Author tools stay project-confined and refuse any mutation whose source or target is `workflows/*.yaml\|*.yml` (use `write_workflow` / `update_block_config`) or under `data/` (use `run_workflow`). Backend runtime writes into `data/` are unaffected. |
| 4 | Hook parity in tool results: list_blocks-before-block-write (once per backend lifetime, and for `scaffold_block` through the bridge), concrete port type warnings, scistudio CLI denial in `run_command`, and an additive `run_workflow` poll hint. |
| 5 | The shared write helper gains an optional expected `state_version`; the editor PUT route's observable behavior is unchanged. |
| 6 | Managed command status, exit state, and bounded output tail live in memory and are cleared on backend restart; `run_command` processes register in the app ProcessRegistry so backend shutdown (`terminate_all`) covers them. |

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
   states their execution location explicitly, never claims the host executed
   them, and names the server-side equivalent of each.

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
through the shared helper, and a write based on a state version the file has
moved past is rejected with an explicit conflict result.

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
assert the explanatory refusal; then satisfy the precondition and assert the
operation succeeds; assert the local transport's behavior for `scaffold_block`
is unchanged.

**Acceptance Scenarios**:

1. **Given** any author tool, **When** the source or target of the mutation is
   `workflows/*.yaml|*.yml` or anything under `data/` (including a rename or
   move into or out of `data/`, and a directory operation containing such a
   file), **Then** the call is refused with a pointer to `write_workflow` /
   `update_block_config` or `run_workflow`, and nothing changes.
2. **Given** a backend on which `list_blocks` has not run, **When** an author
   tool would write a `blocks/*.py` file, or `scaffold_block` is called through
   the bridge, **Then** the result is an explanatory refusal; **after**
   `list_blocks` runs once — through any transport — the same call succeeds;
   **after** a backend restart the requirement applies again. `scaffold_block`
   through the local transport behaves as before.
3. **Given** an author-tool write to `blocks/*.py` whose `InputPort`/`OutputPort`
   constructors use a generic `DataObject` or empty `accepted_types`, **When**
   the write succeeds, **Then** the result carries a non-blocking warning.
4. **Given** a command that invokes the `scistudio` CLI, **When** it is passed
   to `run_command`, **Then** it is refused and the result names the MCP
   alternatives.
5. **Given** a `run_workflow` call, **When** it returns, **Then** the result
   carries an additive hint to poll `get_run_status` until the run is
   terminal, and every existing field is unchanged.

### User Story 4 - Arbitrary code runs managed, cancellable, and in the right environment (Priority: P1)

`run_command` executes user-authorized arbitrary code with the instance's
ordinary permissions: asyncio-spawned, registered in the backend's
ProcessRegistry for process-tree cancellation, bound to an explicit project
context, and resolving the bundled Python and user dependency locations so a
package the agent installs is the package SciStudio later uses.

**Why this priority**: ADR-055 section 5.3 declares arbitrary code an intended
capability; the demo's synchronous `subprocess.run` blocked the event loop,
ignored cancellation, and could run with `cwd=None` — all three are
correctness failures for a shared async server.

**Independent Test**: Start a long-running command that spawns children; while
it runs, verify the event loop stays responsive (a sibling task keeps its
schedule); cancel it and assert the whole process tree terminates and the
registry no longer tracks it; run `python -c "import sys; print(sys.executable)"`
and assert the bundled interpreter; install a package through `run_command`
and assert a subsequent SciStudio-side import resolves it.

**Acceptance Scenarios**:

1. **Given** a command that sleeps with child processes, **When** cancellation
   is requested, **Then** the process tree is terminated, the tool reports the
   terminal state, and the ProcessRegistry shows no residue.
2. **Given** a long-running command, **When** a sibling request arrives,
   **Then** it completes without waiting for the command (no event-loop
   blocking).
3. **Given** no active project, **When** `run_command` is invoked, **Then** it
   fails with an explicit absent-context result instead of running with an
   undefined working directory.
4. **Given** a pip install through `run_command`, **When** SciStudio code later
   imports the package, **Then** both resolve the same user dependency
   location (environment is explicit and shared).
5. **Given** a running command, **When** the backend shuts down, **Then** the
   lifespan's `terminate_all` stops it, because it is registered in that
   registry.

### User Story 5 - Job lifecycle outlives the browser request (Priority: P2)

A long operation started through a tool survives the originating HTTP request
ending: request cancellation and job cancellation are distinct, and job status,
output, and cancellation remain reachable through managed lifecycle behavior.

**Why this priority**: ADR-055 section 5.3: "a browser request timeout is
distinct from terminating a job and its child processes" — collapsing the two
either kills long analyses on disconnect or leaves orphans.

**Independent Test**: Start a managed long command, abort the originating
request, and assert the job keeps running and remains observable (it can be
found with `list_commands`) and cancellable; then cancel the job and assert
terminal state and process-tree cleanup.

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
- Writes to `blocks/`, `types/` follow the existing drop-in semantics (a
  lint-clean save rebuilds the registries) — the reuse rule makes this
  automatic.
- Delete/rename of a path the UI has open: a `deleted` file-changed event fires
  at the old path (and `created` at the new one for a move); the result lists
  the affected paths; UI reaction is out of scope here.
- A directory delete or move touching more than 2000 files is refused; bulk
  reorganization belongs to `run_command`.
- Output exactly at the cap: the marker is unambiguous about whether
  truncation occurred (a one-byte probe for reads; total byte counts for
  command output).
- Concurrent `run_command` invocations: each is an independent registry entry;
  no shared mutable execution state.
- A command whose background child keeps its output pipes open after the
  command exits: the job is reported exited and output capture stops at exit,
  with a note.
- Windows: the command string runs in the command processor, and Python
  children write UTF-8 to their pipes (`PYTHONIOENCODING`), so tails show
  non-ASCII text.
- `get_agent_context` on an instance with no active project: explicit
  absent-context response (never a project-less "default" index).

## 3. Requirements

### Functional Requirements

- **FR-001**: `get_agent_context` MUST return a bounded initial response
  covering: project identity and active context; effective SciStudio/project
  guidance; an index of documentation and skills with real readable paths
  (project `docs/`, `.scistudio/agent-reference/`, host-specific skills
  directories, hook scripts); the instance's execution environment and access
  capabilities; and hook guidance with execution location explicit. Detailed
  content stays in its files and is fetched through the appropriate existing
  tool.
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
  hosts; unexpected failures follow the existing raise-and-adapt convention.
- **FR-004**: Inspect tools (list/metadata/search/read) MUST accept absolute
  paths and read anything the backend's OS user can read, resolve
  project-relative paths against the active project (refusing a relative path
  when no project is open), and bound every read while streaming with an
  accurate truncation marker carrying total size.
- **FR-005**: Author tools (create/write/patch/rename-move/delete) MUST be
  confined to the active project and MUST reuse the editor's write path —
  atomic write, `FILE_CHANGED` event emission, and post-save block reload —
  extracted from `api/routes/projects.py` into a shared helper both the route
  and the tools call. The helper MUST accept an optional expected
  `state_version` and reject a stale write explicitly (stale-version,
  missing-file, and already-exists conditions named in the result); the editor
  PUT route MUST keep its observable behavior when the field is absent.
- **FR-006**: Author tools MUST refuse any mutation whose source or target is
  `workflows/*.yaml|*.yml` (pointing to `write_workflow` / `update_block_config`)
  or anything under `data/` (pointing to `run_workflow`), checking both the
  lexical and the symlink-resolved path and every file a directory operation
  touches. Backend runtime writes into `data/` are unaffected.
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
  `deny_scistudio_cli` pattern, applied per shell segment), naming the MCP
  alternatives; (d) the `run_workflow` result MUST carry an additive hint to
  poll `get_run_status` until terminal, with every existing field unchanged.
- **FR-008**: Authorized shared datasets MUST be usable in place through
  filesystem permissions; tools MUST NOT copy them into the project.
- **FR-009**: `run_command` MUST spawn through asyncio subprocesses (never
  synchronous `subprocess.run` in the request path) in a new process group,
  register every process in the backend ProcessRegistry that the lifespan's
  shutdown `terminate_all` runs on, support process-tree cancellation, and fail
  with an explicit absent-context result when no project is active.
- **FR-010**: The execution environment MUST be explicit: working directory
  and `SCISTUDIO_PROJECT_DIR` bound to the active project (as worker processes
  receive it), and the desktop Python terminal's environment — SciStudio's
  `python`/`pip` wrappers first on `PATH`, `PIP_TARGET` at the shared user
  dependency site that SciStudio's registries and workers import from — so
  install-then-use resolves to the intended runtime. Credentials the backend
  exports for its own workers (`SCISTUDIO_ENGINE_IPC_TOKEN`) MUST NOT be passed
  to commands.
- **FR-011**: Command output collection MUST be bounded during capture (not
  clipped after the fact) with accurate totals and truncation flags; every
  command MUST be a managed job whose status and cancellation are separate
  tools, independent of the originating request, with a way to find jobs whose
  starting request ended. Job state (status, exit state, bounded output tails)
  MUST live in memory and be cleared on backend restart.
- **FR-012**: Tool logging MUST record operation identifiers and outcomes only;
  file contents, command bodies, and full arguments MUST NOT be logged.

### Key Entities

- **WriteConflict**: the condition (`stale_version`, `missing_file`,
  `already_exists`, `missing_parent`, `is_directory`, `directory_not_empty`,
  `too_many_entries`), the entity, and the expected and current state
  versions; returned by the shared helper and surfaced as a `conflict` result
  (or a 409 from the editor route when it supplied an expected version).
- **ManagedCommand**: job identifier, project binding, process id, state
  (`running`, `exited`, `cancelled`), exit code, bounded stdout/stderr tails
  with total byte counts and truncation flags; backed by the ProcessRegistry
  entry while it runs; in memory only.
- **ToolRefusal**: machine-readable code, message, and the tools to use
  instead; the result shape for every policy refusal and conflict.

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
tools refuse rather than write around the path. The conflict check applies the
watcher's ADR-045 §3.3 rule at read time — a disk mtime newer than the cached
disk version advances the state version once — so an external edit the watcher
has not delivered yet still conflicts.

**Context tool.** `get_agent_context` lives in `tools_qa.py` beside
`get_project_info`, `get_doc`, and `search_docs`, reading the provisioning
outputs of `agent_provisioning` via `get_context().project_dir`; it assembles a
bounded index (capped entries per asset class) and marks each entry with its
retrieval tool.

**Workspace tools** live in `tools_workspace.py`. Reads use a buffer sized to
the window, filled in chunks, plus a one-byte probe; searches bound results,
scanned files, and bytes per file; filesystem work runs in threads so the event
loop stays free. The author tools confine paths with the same realpath +
commonpath rule as the editor route, apply the blacklist, then call the shared
path.

**Hook parity.** `list_blocks` sets a backend-lifetime flag in
`tools_workflow/read.py`; author tools consult it, and `scaffold_block`
consults it only when the WebMCP route has marked the dispatch as a bridge call
(a context variable set around `mcp.call_tool`). The port-type warning loads
the provisioned `hook_enforce_concrete_port_types.py` template through the
provisioning loader and runs its scanner. `run_workflow` returns a subclass of
its result model adding `poll_hint`.

**Execution.** `run_command` in `tools_execution.py` follows the
`LocalRunner._spawn_worker` pattern: POSIX spawns `/bin/sh -c` through
`asyncio.create_subprocess_exec` with a new session; Windows runs the command
processor through `asyncio.create_subprocess_shell` with a new process group
and no console window (CreateProcess quoting would corrupt a command string
passed to `create_subprocess_exec("cmd.exe", "/c", ...)`). The process
registers in the backend ProcessRegistry the context exposes as
`MCPContext.process_registry` (the lifespan's `app.state.registry`). A
supervisor task, not the request, owns each job: it pumps output into bounded
tails and records the terminal state; cancellation runs `terminate_tree` in a
thread. The environment is `desktop/paths.py`'s `user_python_terminal_env` plus
the project binding.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/api/runtime/_file_writes.py` | create | Shared write path + `ProjectFileService` |
| `src/scistudio/api/runtime/__init__.py` | modify | `ApiRuntime.project_files` |
| `src/scistudio/api/routes/projects.py` | modify | PUT route uses the shared helper; optional `expected_state_version` |
| `src/scistudio/api/app.py` | modify | Context adapter exposes `project_files` and `process_registry` (two members) |
| `src/scistudio/api/routes/webmcp.py` | modify | Bridge-call marker around dispatch |
| `src/scistudio/ai/agent/mcp/_context.py` | modify | Optional capability Protocols/accessors; bridge-call marker |
| `src/scistudio/ai/agent/mcp/tools_qa.py` | modify | `get_agent_context` |
| `src/scistudio/ai/agent/mcp/tools_workspace.py` | create | Inspect and author tools |
| `src/scistudio/ai/agent/mcp/tools_execution.py` | create | `run_command` + managed job tools |
| `src/scistudio/ai/agent/mcp/tools_workflow/read.py` | modify | `list_blocks` backend-lifetime flag |
| `src/scistudio/ai/agent/mcp/tools_workflow/write.py` | modify | Additive `run_workflow` poll hint |
| `src/scistudio/ai/agent/mcp/tools_authoring.py` | modify | `scaffold_block` bridge check |
| `src/scistudio/ai/agent/mcp/__init__.py` | modify | Import new tool modules (registration) |
| `tests/ai/test_mcp_agent_context.py` | create | Context tool over provisioned fixtures |
| `tests/ai/test_mcp_workspace_tools.py` | create | Inspect/author behavior, bounds, blacklist, hook parity |
| `tests/ai/test_mcp_execution_tools.py` | create | Execution, cancellation, environment, job lifecycle |
| `tests/ai/test_mcp_tools_workflow.py` | modify | `run_workflow` poll hint |
| `tests/ai/test_mcp_fastmcp.py` | modify | Registry tool set |
| `tests/api/test_projects.py` | modify | Route/helper parity, expected state version |

### 4.3 Implementation Sequence

1. **T-001** (foundation): extract the shared write helper from
   `projects.py`; route + helper parity tests; optional expected
   `state_version`.
2. **T-002** (US1): `get_agent_context` + provisioning-fixture tests.
3. **T-003** (US2/US3): `tools_workspace.py` inspect/author tools, blacklist,
   and block hook parity + bounds, conflict, and parity tests.
4. **T-004** (US4/US5): `tools_execution.py` + registry integration + CLI
   denial + cancellation/responsiveness/environment tests.
5. **T-005** (US3): additive `run_workflow` poll hint.
6. **T-006** (cross-cutting): bounded logging, audience tags verified through
   both catalogues, spec text (this spec amended; transfer moved to
   `adr-055-lab-deployment`).

### 4.4 Verification Plan

- Registry-level tests for every new tool (no browser required), covering the
  acceptance scenarios above; author tools run through the real bridge route so
  the production context adapter and event emission are exercised.
- Boundedness checks on fixtures at least four times the cap: a read pulls at
  most the window plus a one-byte probe from disk; command output keeps at
  most the tail cap.
- Concurrency tests: a long `run_command` while a sibling task keeps schedule;
  two concurrent commands as independent registry entries.
- Process-tree cancellation (a command with a child and grandchild) with zero
  registry residue; request abort leaves the job running; a command started
  through the bridge sits in `app.state.registry` and is stopped by the
  lifespan shutdown.
- Install-then-import parity: always via the stdlib check (a module written to
  the command's `PIP_TARGET` imports on both sides); additionally via an
  offline wheel `pip install` when the interpreter ships pip (CI's
  setup-python interpreter does; uv-managed venvs do not, and the test says so
  when it skips).
- Existing suites (`tests/api/test_projects.py`, `tests/api/test_file_endpoints.py`,
  `tests/api/test_reload_on_save.py`, the webmcp bridge suite) pass unchanged.
- `gate_record check` tier-selected checks for the diff.

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
- Rollback: new modules are additive; the extracted helper is
  behavior-preserving; revert restores current behavior with no migration.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: `get_agent_context` on a freshly provisioned project returns an
  index whose every listed path resolves on disk; missing-asset diagnostics are
  accurate in 100% of fixture cases.
- **SC-002**: No read or command-output path holds more than the configured cap
  plus one chunk in memory, measured on fixtures ≥ 4× the cap.
- **SC-003**: 100% of tool-authored writes emit the file-changed event and pass
  through the atomic write path (asserted via the shared helper, not
  re-implemented).
- **SC-004**: A cancelled managed command leaves zero live descendant processes
  and zero registry residue in 100% of test runs on all supported platforms.
- **SC-005**: A package installed through `run_command` is importable by the
  SciStudio runtime in the same instance, in the verification environment.
- **SC-006**: 100% of blacklisted author mutations (`workflows/*.yaml|*.yml`,
  `data/`, as source or target) are refused with nothing changed on disk.

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
