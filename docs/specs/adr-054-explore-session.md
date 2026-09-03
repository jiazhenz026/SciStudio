---
spec_id: adr-054-explore-session
title: "ADR-054 Explore Session — Notebook, Kernel, Queue, And Packaging"
status: Draft
feature_branch: docs/adr-054-explore-session-spec
created: 2026-09-02
input: "Owner-directed live session (guided): author the explore-session runtime spec for ADR-054 sections 4, 5, 6.3 to 6.7, and 7. The owner settled the design in discussion — a session is a notebook in the project plus an optional ipykernel driven through jupyter_client as the only client; execution semantics are Jupyter's and nothing is rebound or re-run on the graph's account; a re-run is marked stale or out of order and never triggered automatically, with one control to run the stale set and one to run a cell with its upstream; every cell run is committed to a dedicated ref off the execution path; a notebook worth keeping is packaged into a Code Block whose ports come from its declarations and which runs the declared-output slice; a packaged block replays on new data by default and can be set to ask, in which case it pauses and opens its notebook in the Explore tab; the session exposes an API and events the frontend builds against."
owners:
  - "@jiazhenz026"
related_adrs:
  - 38
  - 41
  - 42
  - 44
  - 51
  - 53
  - 54
related_specs:
  - adr-054-panel-contract
  - adr-054-notebook-dependency-analysis
  - adr-054-documentation
  - adr-051-interactive-blocks
scope:
  in:
    - The session service - opening a session over a block's outputs, over a file, or over a paused interactive block's inputs; listing, closing, and committing sessions; the notebook file's location and its generated first cell; reload on external edits.
    - The kernel - an ipykernel launched from the bundled Python and driven through jupyter_client as the only client; ownership by the session service; a kernel-side bridge for namespace fingerprints, variable windows, bindings, and memory; the in-notebook helpers scistudio.input, scistudio.output, and scistudio.load in session mode and in packaged mode; installs through the kernel with environment re-snapshot; interrupt, restart, stop, and retirement on branch switch.
    - The execution queue - one queue, admission of panel-emitted code through the statement whitelist, coalescing of queued duplicates, the observation call around each run, the stale and out-of-order marks, the run-stale and run-with-upstream controls, and the shallow freeze bound.
    - Storage and history - the .ipynb on disk with outputs, outputs stripped into a dedicated ref namespace on every cell run off the execution path, packing, and an explicit commit to the branch.
    - Packaging - a Code Block generated from the notebook under the project's blocks directory, ports from the notebook's declarations, the slice materialised for the existing notebook backend, the refusal conditions, reopening from the node, and repackaging.
    - The remember setting on_new_input with the values replay and ask, for a packaged notebook block and for an authored interactive block, including the pause and the Explore-tab prompt a packaged block raises when it asks.
    - Calling a block from a cell inside the kernel, and the case of an interactive block called from a cell.
    - The explore_sessions lineage anchor, per-cell-run records, block-call records, environment snapshots by reference, and retention.
    - The session API and the events the explore-frontend spec builds against.
  out:
    - The dependency analysis, the fingerprint, and the graph queries (adr-054-notebook-dependency-analysis). This spec calls them and never re-implements them.
    - The panel contract, the frame host, and the windowed read the host performs (adr-054-panel-contract). This spec supplies the kernel-side window a panel bound to a notebook variable reads.
    - The Explore tab, the notebook shell, the marks as drawn, the kernel list as drawn, and every other rendering concern (the explore-frontend spec).
    - The agent-facing skill, reference documents, and MCP tools (the agent-enablement spec).
    - Human documentation revision (adr-054-documentation).
    - A general-purpose notebook IDE, importing external notebooks with their own execution history, and lifting block calls out of a notebook onto the canvas as nodes, all excluded by ADR-054 section 10.2.
governs:
  modules:
    - scistudio.blocks.base.interactive
    - scistudio.blocks.code.backends.notebook
    - scistudio.core.lineage
    - scistudio.core.versioning
    - scistudio.api.ws
  contracts:
    - scistudio.blocks.base.interactive.InteractiveMixin
    - scistudio.core.lineage.record.RunRecord
    - scistudio.core.lineage.record.BlockExecutionRecord
  entry_points: []
  files:
    - docs/specs/adr-054-explore-session.md
    - src/scistudio/__init__.py
    - src/scistudio/blocks/base/interactive.py
    - src/scistudio/blocks/code/backends/notebook.py
    - src/scistudio/core/lineage/record.py
    - src/scistudio/core/lineage/store.py
    - src/scistudio/core/lineage/environment.py
    - src/scistudio/core/versioning/_commit_ops.py
    - src/scistudio/engine/scheduler/_dispatch.py
    - src/scistudio/api/ws.py
    - src/scistudio/api/project_layout.py
    - pyproject.toml
    - tests/architecture/test_layer_deps.py
  excludes:
    - docs/architecture/**
    - docs/user/**
    - src/scistudio/_skills/**
    - src/scistudio/_agent_reference/**
planned_governs:
  modules:
    - scistudio.explore.session
    - scistudio.explore.kernel
    - scistudio.explore.kernel_bridge
    - scistudio.explore.notebook
    - scistudio.explore.notebook_api
    - scistudio.explore.queue
    - scistudio.explore.packaging
    - scistudio.explore.lineage
    - scistudio.api.routes.explore
  contracts:
    - scistudio.explore.session.ExploreSession
    - scistudio.explore.session.SessionService
    - scistudio.explore.queue.ExecutionRequest
    - scistudio.explore.packaging.PackagingReport
    - scistudio.explore.lineage.ExploreSessionRecord
  entry_points: []
  files:
    - src/scistudio/explore/session.py
    - src/scistudio/explore/kernel.py
    - src/scistudio/explore/kernel_bridge.py
    - src/scistudio/explore/notebook.py
    - src/scistudio/explore/notebook_api.py
    - src/scistudio/explore/queue.py
    - src/scistudio/explore/packaging.py
    - src/scistudio/explore/lineage.py
    - src/scistudio/api/routes/explore.py
    - tests/explore/test_kernel_session.py
    - tests/explore/test_execution_queue.py
    - tests/explore/test_marks.py
    - tests/explore/test_notebook_store.py
    - tests/explore/test_explore_commits.py
    - tests/explore/test_packaging.py
    - tests/explore/test_block_call_adapter.py
    - tests/explore/test_explore_lineage.py
    - tests/explore/test_notebook_api.py
    - tests/api/test_explore_routes.py
    - tests/blocks/base/test_interaction_policy.py
  excludes: []
tests:
  - tests/explore/test_kernel_session.py
  - tests/explore/test_execution_queue.py
  - tests/explore/test_marks.py
  - tests/explore/test_notebook_store.py
  - tests/explore/test_explore_commits.py
  - tests/explore/test_packaging.py
  - tests/explore/test_block_call_adapter.py
  - tests/explore/test_explore_lineage.py
  - tests/explore/test_notebook_api.py
  - tests/api/test_explore_routes.py
  - tests/blocks/base/test_interaction_policy.py
  - tests/architecture/test_layer_deps.py
acceptance_source: adr
language_source: en
---

# ADR-054 Explore Session — Notebook, Kernel, Queue, And Packaging

## 1. Change Summary

A scientist has run three blocks and does not know what the fourth should be.
ADR-054 gives them a place to find out: an **Explore Session**, a notebook and
a live kernel opened over the outputs of a block or over a file. It is not a
node, it does not touch the engine, and nothing pauses while they explore.
This spec defines the runtime behind that session.

From the person's side, the session is a Jupyter notebook that behaves like
one. The kernel is ipykernel, launched from SciStudio's bundled interpreter;
magics work, `%pip` installs into the environment the kernel runs in, a cell
reads whatever the namespace holds when it runs. What SciStudio adds sits
around the kernel and never inside its semantics: the notebook's first cell
loads the data the session was opened on; every cell run is committed to the
project's history without anyone asking; the dependency analysis marks what a
re-run makes stale and what a re-run read out of written order, and never runs
anything on its own; a panel bound to a variable refreshes when that variable
changes, and an edit made in a panel becomes a line of code in the notebook.

When the notebook is worth keeping, the person packages it. Packaging produces
a Code Block: its ports are the notebook's `scistudio.input` and
`scistudio.output` declarations, its implementation is a copy of the notebook,
and its run executes the backward slice of the declared outputs through the
notebook backend Code Blocks already have. On new data the block replays; set
to ask, it pauses like an interactive block and opens its notebook in the
Explore tab over the run's inputs, and the notebook version the person confirms
is the decision it remembers.

The session service owns the kernel. It sits beside the engine, is driven
through `jupyter_client` as the kernel's only client, and is the one place
every execution passes through, which is what lets it admit, mark, observe,
record, and commit. `jupyter_server` is not used, because it would let the
frontend talk to the kernel directly and take every one of those steps out of
SciStudio's hands.

This spec consumes the dependency analysis and the panel contract as they are
specified, defines the session API and events the explore-frontend spec builds
against, and leaves rendering entirely to that spec.

## 2. User Scenarios & Testing

### User Story 1 - A notebook over a block's outputs that behaves like Jupyter (Priority: P1)

A person right-clicks a block that has run and chooses to explore its outputs.
A notebook opens whose first cell loads each output port into a variable named
after the port. They run it, add a cell, type `%pip install scikit-image`, run
that, import the package, and keep going. Everything behaves as it does in
Jupyter.

**Why this priority**: This is the surface everything else attaches to. If
the kernel does not behave like Jupyter the target users will not use it, and
if the first cell is not the load the notebook cannot replay, cannot be
packaged, and cannot recover from a kernel restart.

**Independent Test**: Open a session over a fixture run's outputs, confirm the
generated first cell names every output port, run it and confirm the variables
exist in the kernel with the expected types, run a `%pip` cell against a local
index and confirm the package imports, and confirm the environment snapshot
recorded after that cell differs from the one before.

**Acceptance Scenarios**:

1. **Given** a block whose outputs exist, **When** the person opens a session
   over it, **Then** a notebook is created in the project's explore directory
   whose first cell loads each output port into a variable named after the
   port, and no kernel is started.
2. **Given** a block whose outputs have never been produced, **When** the
   session action is requested, **Then** it is refused with a message saying
   there is nothing to explore.
3. **Given** an open session, **When** the person runs the first cell,
   **Then** a kernel starts from the bundled interpreter, the cell executes,
   and the variables exist in the kernel namespace.
4. **Given** a running kernel, **When** a cell containing `%pip install` runs,
   **Then** the package installs into the kernel's environment and a new
   environment snapshot is recorded by reference.
5. **Given** a session opened from a file in the data tree, **When** the
   notebook is created, **Then** its first cell loads the file by path.

### User Story 2 - Marks tell the truth and never run anything (Priority: P2)

Cells A, B, and C each bind `df`. The person runs all three, edits B, and runs
B again. B reads C's `df`, as it would in Jupyter. B is marked out of order and
C is marked stale. Nothing else runs. The person clicks the control on B to
run it with its upstream; A runs, then B, and the marks clear. They click the
control to run the stale set; C runs.

**Why this priority**: This is the correctness problem ADR-054 §6.1 exists
for, delivered without changing Jupyter's semantics. It ranks below Story 1
because it presupposes a working kernel and queue.

**Independent Test**: Run the A, B, C fixture, edit and re-run B, and confirm
the marks on B and C. Trigger run-with-upstream on B and confirm the queue
runs A then B and only those. Trigger run-stale and confirm C runs. Confirm
that at no point did the service enqueue a cell the person did not ask for.

**Acceptance Scenarios**:

1. **Given** A, B, and C have run and B is re-run, **When** B is submitted,
   **Then** B is marked out of order because the graph's definer of `df` for
   B is A while the kernel's last binder is C, and B still runs.
2. **Given** B has re-run, **When** the run completes, **Then** C is marked
   stale, B's stale mark is cleared, and no cell is enqueued automatically.
3. **Given** B is out of order, **When** run-with-upstream is requested on B,
   **Then** the queue runs A and then B, skipping any cell in B's backward
   slice that is neither stale nor out of order and whose every changed name
   is still last bound by it in the kernel.
4. **Given** C is stale, **When** run-stale is requested, **Then** the stale
   cells run in written order and nothing else.
5. **Given** a cell is queued and the person submits the same cell again,
   **When** the second submission arrives, **Then** it is coalesced with the
   first and the cell runs once.
6. **Given** a cell is running, **When** the person interrupts, **Then** the
   interrupt reaches the kernel and the cell ends with an interrupt error
   rather than the session ending.

### User Story 3 - A panel edit becomes a line of code (Priority: P3)

A panel bound to `df` shows a table. The person deletes two rows in it. A new
cell appears after the current one containing `df = df.drop(index=[3, 7])`,
runs, and the next cell the person writes sees the smaller frame.

**Why this priority**: This is the loop ADR-054 §3.1 promises, and the reason
a producing panel exists. It ranks below Story 2 because it is one more
submission on the same queue.

**Independent Test**: Submit an emitted snippet through the session API and
confirm it is inserted as a cell after the current cell, admitted, run, and
that the namespace reflects it. Submit a snippet containing a bare method call
and confirm it is refused with a message naming the panel and the statement.

**Acceptance Scenarios**:

1. **Given** a panel bound to `df` emits an assignment, **When** the session
   receives it, **Then** a cell is inserted after the current cell with that
   code and is enqueued.
2. **Given** an emitted snippet contains a statement outside the whitelist,
   **When** it is received, **Then** it is refused before it is queued, with
   an error naming the panel and the statement, and no cell is inserted.
3. **Given** the emitted cell has run, **When** the observation completes,
   **Then** the changed names are reported so the panel bound to `df`
   refreshes, and cells below reading `df` are marked stale.
4. **Given** a cell is running and it may change `df`, **When** the panel
   bound to `df` tries to emit, **Then** the submission is refused until the
   run ends, while the panel keeps reading.

### User Story 4 - The notebook becomes a block and runs in a workflow (Priority: P4)

The person packages the notebook. A block appears in the project palette with
an input port per `scistudio.input` and an output port per
`scistudio.output`. They drop it into a workflow after the block they explored
and run the workflow. The node runs the notebook's declared-output slice with
no interface and writes its output ports. On a new batch it replays.

**Why this priority**: Packaging is where exploration turns into a workflow
step, which is the origin of the feature. It ranks below Story 3 because the
session must work before it is worth keeping.

**Independent Test**: Package a fixture notebook and confirm the generated
block declaration and notebook copy exist under the project's blocks
directory, the block registers with the declared ports, and a workflow run
through it produces outputs equal to the session's. Package again after an
edit and confirm the copy is replaced. Attempt to package notebooks with a
stale cell, an out-of-order cell, a never-run cell, an unresolved read, an
interactive block call, and no output declaration, and confirm each is refused
with the cells named.

**Acceptance Scenarios**:

1. **Given** a notebook whose slice is clean, **When** it is packaged,
   **Then** a block declaration and a notebook copy are written under the
   project's blocks directory, the block registers with ports named by the
   declarations and typed by the objects bound at packaging, and it appears
   in the palette.
2. **Given** a packaged block in a workflow, **When** the workflow runs,
   **Then** the node executes only the backward slice of the declared outputs
   through the notebook backend and writes its output ports.
3. **Given** the same node on a different branch wired to a new batch,
   **When** the workflow runs, **Then** the node replays without pausing.
4. **Given** a notebook whose slice contains a stale, out-of-order, or
   never-run cell, an unresolved read, or a call to an interactive block, or
   that declares no output, **When** packaging is requested, **Then** it is
   refused with the offending cells or reads named.
5. **Given** a packaged block's node, **When** the person double-clicks it,
   **Then** its notebook opens in a session bound to the node's most recent
   run inputs, and packaging again replaces the copy.

### User Story 5 - A packaged block asks on new data (Priority: P5)

The person sets a packaged block to ask. On the next run with changed inputs
the node pauses, the Explore tab opens the block's notebook over this run's
inputs, they adjust a threshold, and confirm. The node runs the notebook they
confirmed. With unchanged inputs the block does not pause.

**Why this priority**: ADR-054 §4.7 makes remembering one setting for every
block with an interaction, and a packaged block is one. It ranks below Story 4
because it is the pause added to the run Story 4 defines.

**Independent Test**: Set a fixture packaged block to ask, run its workflow
with inputs whose fingerprint differs from the remembered one, confirm the
engine pauses the node and emits an interactive prompt naming the notebook and
the run inputs, confirm through the session API with a notebook commit, and
confirm the compute phase runs that commit's slice. Run again with unchanged
inputs and confirm no pause.

**Acceptance Scenarios**:

1. **Given** a packaged block set to ask and inputs whose fingerprint differs
   from the remembered one, **When** the node runs, **Then** the engine pauses
   it exactly as it pauses an interactive block, and the prompt names the
   notebook and the run's inputs.
2. **Given** the pause, **When** the person confirms a notebook version,
   **Then** the compute phase runs that version's slice and the decision
   remembered is that commit.
3. **Given** a packaged block set to ask and unchanged inputs, **When** the
   node runs, **Then** it replays the remembered commit without pausing.
4. **Given** an authored interactive block set to replay, **When** its inputs
   change, **Then** it replays its remembered decision without pausing.
5. **Given** the pause, **When** the person cancels, **Then** the node is
   cancelled and the session opened for it is closed.

### User Story 6 - Every cell run is in the history and in lineage (Priority: P6)

The person runs thirty cells over an afternoon. Each run is a commit on the
session's ref, with outputs stripped; the branch's own log shows none of them.
They ask for a commit on the branch and get one. A colleague later follows an
object produced in the session into a workflow run and back.

**Why this priority**: ADR-054 §6.6 and §7 make history and provenance
non-optional. It ranks below the interactive stories because it is invisible
while it works.

**Independent Test**: Run cells and confirm one commit per run on the
session's ref with outputs stripped and the content captured at execution
time. Confirm the branch log is unchanged until an explicit commit. Confirm an
`explore_sessions` row exists, each cell run has a record, a block call from a
cell has a `BlockExecutionRecord` pointing at the session, and an object
produced in the session resolves from a workflow run's input.

**Acceptance Scenarios**:

1. **Given** a cell run completes, **When** the result has been returned,
   **Then** a commit containing the notebook as captured at execution time,
   with outputs stripped, is written to the session's ref, and the working
   tree and the branch index are untouched.
2. **Given** thirty cell runs, **When** the branch log is read, **Then** it
   contains no explore commits.
3. **Given** an open session, **When** the person requests a commit to the
   branch or closes the session with changes, **Then** one commit is written
   to the branch.
4. **Given** a session, **When** it opens, **Then** an `explore_sessions`
   record exists with the notebook path, its content, the environment
   snapshot by reference, and a status.
5. **Given** a block call from a cell, **When** it completes, **Then** a
   `BlockExecutionRecord` is written whose foreign key is the session.

### User Story 7 - A kernel never becomes an untracked process (Priority: P7)

Three sessions are open. The person opens the kernel list, sees each session's
memory, and ends one. They switch branches and the remaining kernels retire.
They reopen a session and the notebook replays from its first cell.

**Why this priority**: ADR-054 §5.3 lists the obligations of owning a process
for an unbounded period. It ranks last because it is verified by the absence
of leaks rather than by a feature.

**Independent Test**: Open three sessions, confirm the kernel list reports
each with its memory, end one and confirm its process is gone, switch the
branch and confirm every kernel is gone, and confirm a kernel that dies
mid-cell is reported as dead and restartable.

**Acceptance Scenarios**:

1. **Given** open sessions, **When** the kernel list is requested,
   **Then** every live kernel is listed with its session, its memory, and a
   way to end it.
2. **Given** a kernel, **When** its session is closed or it is ended from the
   list, **Then** the process is terminated.
3. **Given** open sessions, **When** the branch changes, **Then** every kernel
   is retired and the sessions report that they need a restart.
4. **Given** a kernel that dies during a cell, **When** the death is detected,
   **Then** the cell ends with an error, the session reports the kernel dead,
   and restart is offered.

### Edge Cases

- **The kernel dies mid-cell.** The cell ends with an error naming the death,
  the session's marks reset to never-run, and the notebook is intact on disk
  because the file is written before execution.
- **Two sessions are opened on the same notebook.** The second open returns
  the first session; a notebook has at most one kernel.
- **The notebook file is edited outside the session while a kernel is alive.**
  The cells reload from disk, the analysis re-runs, marks are kept by cell id
  where the id survives, and the kernel namespace is untouched.
- **The person interrupts during an install.** The interrupt reaches the
  kernel; the environment may be half-installed, and the next snapshot records
  whatever it finds.
- **Packaging is requested while a cell is queued or running.** Packaging
  waits for the queue to drain, because the slice's marks are not final until
  it has.
- **An output declaration sits in a disabled cell.** It is not an output; the
  analysis builds over enabled cells only.
- **The same name is declared as output twice.** The later declaration in
  written order wins, and packaging reports the duplicate.
- **A block call from a cell raises.** The exception propagates into the cell
  as an ordinary Python exception, and the block-call record is written with
  the failure.
- **The file a session was opened from no longer exists.** The first cell
  fails with the loader's error; the session opens regardless, because the
  notebook is the person's.
- **A commit fails because git is busy or the repository is locked.** The
  commit is retried off the execution path and never blocks a cell; a run
  whose commit could not be written is reported once.
- **The branch changes with unsaved cell edits.** The notebook is written to
  disk before the kernel retires, so nothing typed is lost.
- **A packaged block's notebook and the exploration it came from diverge.**
  Expected: the block owns its copy and the session continues. Reopening the
  block opens the block's copy.

## 3. Requirements

### Functional Requirements

**The session**

- **FR-001**: A session MUST be a notebook file in the project's explore
  directory, `{project}/explore/`, plus an optional kernel. The session's
  identity MUST be the notebook's project-relative path. A notebook MUST have
  at most one kernel at a time, and opening a session on a notebook that
  already has one MUST return the existing session.
- **FR-002**: A session MUST be openable over the outputs of a block whose
  outputs exist, over a file in the project's data tree, and over the inputs
  of a run paused at an interactive block. A block whose outputs have never
  been produced MUST NOT offer the action, and the API MUST refuse it with a
  message saying there is nothing to explore.
- **FR-003**: A session opened over a block's outputs MUST bind to the most
  recent completed run of that block, or to the paused run when opened from a
  pause, and MUST record which run it is bound to.
- **FR-004**: When a session is created, the service MUST write a notebook
  whose first cell loads each input: one `scistudio.load(scistudio.input(...))`
  line per output port of the block, with the variable named after the port,
  or one `scistudio.load("<path>")` line for a file. The first cell MUST NOT
  run automatically.
- **FR-005**: The service MUST persist cell edits received through the API to
  the notebook file and re-run the analysis, and MUST reload the cells when
  the file changes on disk from outside the session, keeping marks by cell id
  where the id survives and leaving the kernel namespace untouched.
- **FR-006**: Closing a session MUST end its kernel, write the notebook, and,
  if the notebook changed since the last branch commit, write one commit to
  the branch (FR-036). Listing sessions MUST report every notebook in the
  explore directory with whether it has a kernel.

**The kernel**

- **FR-007**: The kernel MUST be an ipykernel process launched from
  SciStudio's bundled interpreter, driven through `jupyter_client`. The
  session service MUST be the kernel's only client; the frontend MUST NOT
  hold a connection to the kernel.
- **FR-008**: The kernel MUST be owned by the session service, which sits
  beside the engine. The explore subsystem MUST NOT import the API, AI, or
  engine layers, and the engine MUST NOT import the explore subsystem.
- **FR-009**: At kernel start the service MUST inject a kernel-side bridge
  that provides, on request: a fingerprint of every top-level name in the
  namespace using the fingerprint function of the dependency-analysis spec; a
  windowed read of one named variable, produced by wrapping the native object
  into its SciStudio type and running the existing preview provider for that
  type; the list of top-level bindings with their type names; and the
  process's memory. Requests MUST travel over the kernel's own execute channel
  and MUST NOT appear as cells.
- **FR-010**: The helpers `scistudio.input`, `scistudio.output`, and
  `scistudio.load` MUST be importable from the top-level package inside the
  kernel. In session mode `scistudio.input(name)` MUST return the reference of
  the bound run's port artefact, `scistudio.load` MUST resolve a reference or
  a path to a `DataObject` through the storage layer, and
  `scistudio.output(**names)` MUST register the names as the session's
  declared outputs without writing anything. The mode MUST be selected by an
  environment variable the launcher sets.
- **FR-011**: In packaged mode the same helpers MUST read from and write to
  the Code Block's exchange folders: `scistudio.input(name)` MUST return the
  materialised input file for that port, and `scistudio.output(**names)` MUST
  write each object into the output folder for that port through the existing
  adapters.
- **FR-012**: A cell whose source contains a `%pip`, `!pip`, or `%conda` line
  MUST cause a new environment snapshot to be captured after it runs and
  stored by reference; the session MUST NOT duplicate a snapshot per record.
- **FR-013**: The service MUST support interrupt, restart, and stop.
  Interrupt MUST reach the kernel process and end the running cell without
  ending the session. Restart MUST start a fresh kernel and reset every mark
  to never-run. Stop MUST terminate the process.
- **FR-014**: Switching the project's branch MUST retire every kernel after
  writing every open notebook to disk, and each session MUST report that it
  needs a restart.
- **FR-015**: The service MUST detect a kernel that dies and MUST end the
  running cell with an error, report the kernel dead, and offer restart.
- **FR-016**: The service MUST list every live kernel in the project with its
  session, its memory, and a way to end it.

**The execution queue and the marks**

- **FR-017**: Each session MUST have one execution queue that runs one request
  at a time in submission order. A request is a cell or a snippet emitted by a
  panel. A submission of a cell already queued and not yet started MUST be
  coalesced with it. A running request MUST NOT be cancelled except by an
  explicit interrupt.
- **FR-018**: A snippet emitted by a panel MUST be parsed before it is queued
  and admitted only if every statement is an assignment, an import, or a call
  to `scistudio.output`. Any other statement MUST cause the emission to be
  refused with an error naming the panel and the statement, and no cell MUST
  be inserted. An admitted snippet MUST be inserted as a new cell after the
  session's current cell and queued.
- **FR-019**: Before a cell runs, the service MUST compare, for each name the
  cell reads, the cell the graph says defines it with the cell that last bound
  it in the kernel, and MUST mark the cell out of order when they differ. The
  cell MUST run regardless.
- **FR-020**: The service MUST keep, per session, which cell last bound each
  name in the kernel, updated from each run's observed changed set.
- **FR-021**: Around each run the service MUST take a namespace fingerprint
  before and after through the bridge, hand both to the comparison of the
  dependency-analysis spec, record the observation on the cell, and re-run
  the analysis.
- **FR-022**: After a run, the service MUST mark every cell in the run cell's
  downstream set stale, MUST clear the run cell's stale and out-of-order marks
  when its reads resolved in order, and MUST NOT enqueue any cell on its own
  account.
- **FR-023**: The marks MUST be never-run, stale, and out-of-order. They are
  session state: a kernel restart MUST reset every cell to never-run.
- **FR-024**: The service MUST offer run-stale, which enqueues the stale cells
  in written order, and run-with-upstream for a cell, which enqueues the
  cell's backward slice in written order, skipping every cell that is neither
  stale nor out of order and whose every changed name is still last bound by
  that cell in the kernel.
- **FR-025**: While a request runs, submissions from panels bound to any name
  in the request cell's changed set (the union the analysis reports) MUST be
  refused until the run ends; reads MUST continue. Submissions from other
  panels MUST be accepted.
- **FR-026**: After a run, the service MUST report the observed changed names
  so that panels bound to them refresh, and MUST report the updated marks.

**Storage and history**

- **FR-027**: The notebook on disk MUST keep its cell outputs. The service
  MUST write the notebook before each run so that a kernel death loses
  nothing typed.
- **FR-028**: Every cell run MUST produce one commit to the session's ref
  under a dedicated namespace, `refs/scistudio/explore/<session>`, containing
  the notebook as captured at execution time with outputs stripped, written
  after the result has been returned to the caller.
- **FR-029**: Explore commits MUST be written with plumbing commands against a
  temporary index so that the working tree and the branch's index are never
  touched, and MUST NOT appear on the branch.
- **FR-030**: A commit that fails MUST be retried off the execution path and
  MUST never block a run; a run whose commit could not be written MUST be
  reported once.
- **FR-031**: The service MUST ensure packing after a bounded number of
  explore commits rather than relying on git's automatic threshold.
- **FR-032**: The record the dependency analysis keeps in cell metadata MUST
  be preserved by every write of the notebook.
- **FR-033**: Cell metadata MUST carry the enabled flag the analysis reads,
  and the service MUST write it when the flag is toggled through the API.
- **FR-034**: The session's environment snapshot MUST be stored once per
  distinct environment and referenced from records.
- **FR-035**: A session MUST report its current notebook commit so that
  packaging and the interaction memory of FR-046 can name it.
- **FR-036**: The service MUST write a commit to the branch containing the
  notebook with outputs stripped when the person requests it, and on close
  when the notebook changed since the last branch commit.

**Packaging**

- **FR-037**: Packaging MUST produce a Code Block: a generated block
  declaration at `{project}/blocks/<name>.py` that the existing tier-1 scan
  discovers, and a copy of the notebook at `{project}/blocks/<name>.ipynb`
  that the declaration names as its script.
- **FR-038**: The generated block's input ports MUST be the notebook's
  `scistudio.input` declarations and its output ports the
  `scistudio.output` declarations, as the analysis reports them; each port's
  type MUST be the SciStudio type of the object bound to that name at
  packaging, and its file extension the default the materialisation layer
  assigns to that type. A session opened from a file MUST have its load line
  rewritten to a port read at packaging.
- **FR-039**: Packaging MUST refuse, naming the offending cells or reads, a
  notebook whose declared-output slice contains a never-run, stale, or
  out-of-order cell; whose slice has an unresolved read; whose slice calls an
  interactive block; or that declares no output. Packaging MUST wait for the
  queue to drain before checking.
- **FR-040**: A packaged block's run MUST execute the backward slice of the
  declared outputs and nothing else. The notebook backend MUST accept a cell
  selection and MUST materialise a temporary notebook containing only the
  selected cells, in written order, for execution in packaged mode.
- **FR-041**: The generated block's version MUST be the notebook commit it
  was packaged from, and packaging MUST record that commit.
- **FR-042**: Double-clicking a packaged block's node MUST open a session on
  the block's notebook copy bound to the node's most recent run inputs, and
  packaging again from that session MUST replace the copy and the declaration
  in place.
- **FR-043**: Packaging MUST leave the exploration notebook it came from
  untouched.

**What a block remembers**

- **FR-044**: Every block with an interaction MUST carry a setting
  `on_new_input` with the values `replay` and `ask`, declared on the block
  with a default and overridable on the node. A packaged notebook block MUST
  default to `replay`; an authored interactive block MUST default to `ask`.
- **FR-045**: For an authored interactive block, `ask` MUST be the existing
  behaviour: the remembered decision replays when the input signature matches
  and the block pauses otherwise. `replay` MUST replay the remembered decision
  regardless of the signature.
- **FR-046**: For a packaged notebook block, the remembered decision MUST be
  the notebook commit it was packaged from. With `replay`, a run MUST execute
  that commit's slice without pausing. With `ask` and a changed input
  signature, the engine MUST pause the node exactly as it pauses an
  interactive block, and the prompt MUST name the notebook, the commit, and
  the run's inputs so that the Explore tab can open a session over them.
- **FR-047**: Confirming the pause of FR-046 MUST carry a notebook commit,
  which becomes the remembered decision, and the compute phase MUST execute
  that commit's slice. Cancelling MUST cancel the node and close the session
  opened for it.
- **FR-048**: The pause of FR-046 MUST hold nothing resident and MUST reuse
  the engine's existing interactive pause; the session opened for it is the
  session service's and the engine MUST NOT wait on it.

**Calling a block from a cell**

- **FR-049**: A cell MUST be able to call a block by identifier through an
  adapter that runs inside the kernel: it resolves the block from the
  registry, validates ports, wraps native objects into typed data objects on
  the way in, runs the block in-process, and unwraps on the way out. It MUST
  NOT go through the workflow runner.
- **FR-050**: An interactive block called from a cell MUST open its panel
  through the session service in the Explore tab and MUST block the cell until
  the value arrives or the cell is interrupted. A notebook containing such a
  call MUST be refused at packaging (FR-039).
- **FR-051**: A block call from a cell MUST write a `BlockExecutionRecord`
  with its foreign key pointing at the session, and its inputs and outputs
  MUST be recorded as `block_io` edges with data objects as they are for a
  workflow run.

**Lineage**

- **FR-052**: An `explore_sessions` table MUST be added that parallels `runs`
  field for field: the notebook's path, its captured content, the commit of
  FR-028, an environment snapshot reference, a start time, and a status.
- **FR-053**: Every cell run MUST write a record carrying the session, the
  notebook commit, the cell id, and the environment reference.
- **FR-054**: A packaged block's run MUST be an ordinary workflow run whose
  block version is the notebook commit (FR-041), so that the session the step
  came from is reachable from the run.
- **FR-055**: Objects named in `scistudio.output` MUST be durable; every
  other object a session produces MUST be a reclaim candidate for the existing
  retention planner.

**The API and events**

- **FR-056**: The session API MUST offer: open (over a block's outputs, a
  file, or a paused run), list, close, and commit-to-branch; read and write
  cells, run one cell, run the stale set, run with upstream, toggle enabled,
  interrupt, restart; the graph, the marks, and the bindings with their type
  names and whether each exists in the kernel; a windowed read of a variable
  and the emission of a snippet from a panel; the kernel list and ending a
  kernel; a packaging check and packaging.
- **FR-057**: The service MUST publish, over the existing WebSocket hub:
  session opened and closed; kernel state with memory; cell state with its
  marks; cell output as it streams; the changed names after a run; analysis
  updated; commit recorded; and packaged. A client MUST NOT need any other
  channel.
- **FR-058**: The API MUST expose nothing that reaches the kernel except
  through the service's queue and bridge.

**Boundaries and dependencies**

- **FR-059**: `ipykernel` and `jupyter_client` MUST be added to the core
  dependencies, and the bundled runtime MUST be rebuilt before a release that
  ships the session, because the runtime cannot receive dependencies through
  an over-the-air update.
- **FR-060**: The architecture layer test MUST enumerate the explore subsystem
  with the forbidden imports of FR-008.

### Key Entities

- **ExploreSession** — a notebook and its optional kernel. Attributes:
  notebook path, bound run, kernel state, current cell, marks per cell,
  last-bound-by map, declared outputs, current notebook commit.
  Relationships: owned by SessionService; has one ExecutionQueue; recorded as
  one ExploreSessionRecord.
- **SessionService** — the owner of every session and kernel in a project.
  Attributes: sessions by path. Relationships: the only client of every
  kernel; publishes SessionEvents; called by the API layer and by the
  interactive pause of FR-046.
- **KernelHandle** — one ipykernel process and its `jupyter_client` manager.
  Attributes: process id, state, memory, environment reference.
  Relationships: owned by one ExploreSession; hosts one KernelBridge.
- **KernelBridge** — the code injected into the kernel. Attributes: none
  persisted. Relationships: answers fingerprint, window, bindings, and memory
  requests; hosts the notebook helpers and the block-call adapter.
- **ExecutionRequest** — one unit of work on the queue. Attributes: session,
  cell id or emitted snippet with its panel, submission time, state.
  Relationships: coalesced by cell id while queued; produces an observation
  and a commit.
- **CellMark** — never-run, stale, or out-of-order. Attributes: cell id, mark,
  reason (the names and definers that produced it). Relationships: session
  state; reset on restart; reported in SessionEvents.
- **ExploreCommit** — one commit on the session's ref. Attributes: sha,
  notebook content with outputs stripped, cell id that produced it.
  Relationships: referenced by cell-run records and by packaging.
- **PackagedNotebookBlock** — the Code Block packaging produces. Attributes:
  declaration path, notebook copy path, ports, notebook commit,
  `on_new_input`. Relationships: discovered by the tier-1 scan; executed by
  the notebook backend over its slice; reopened into an ExploreSession.
- **InteractionPolicy** — the `on_new_input` setting. Attributes: `replay` or
  `ask`, declared default, node override. Relationships: read by the engine's
  interactive dispatch for both block kinds.
- **PackagingReport** — the result of a packaging check. Attributes: slice
  cells, refusals with the cells or reads named, ports inferred.
  Relationships: returned by the API before and by packaging itself.
- **ExploreSessionRecord** — the lineage row. Attributes: those of FR-052.
  Relationships: the anchor for cell-run records and block-call records.
- **SessionEvent** — a message on the WebSocket hub. Attributes: event type
  from FR-057, session, payload. Relationships: consumed by the frontend.

## 4. Implementation Plan

### 4.1 Technical Approach

**The kernel is Jupyter's; the service is SciStudio's.** ipykernel is launched
from the bundled interpreter and driven through `jupyter_client`'s
`KernelManager` and client, which already provide launch, interrupt, restart,
shutdown, and the message channels. ipykernel executes one request at a time,
so the single queue ADR-054 §6.3 requires is the kernel's own; what the
service adds is admission, marking, observation, recording, and committing,
each of which needs something only SciStudio knows. `jupyter_server` is not
used because it exists to let a frontend talk to a kernel directly, and every
one of those additions must sit between the person and the kernel.

**Where the service lives.** `scistudio.explore` is a subsystem beside the
engine at the layer of `previewers` and `plot`. It imports `core` for
storage, lineage, and versioning, and `blocks` for the registry and the Code
Block; it never imports the API, AI, or engine layers, and the engine never
imports it. The interactive pause of FR-046 is the one point where the engine
and the session meet, and it meets the session the way it meets every
interactive block: through a prompt event and a decision, never through a
reference to the session.

**The bridge, and why panels read through the kernel.** A panel bound to a
notebook variable needs a window of a live object, and that object exists
only in the kernel process. The bridge is a small module the service injects
at kernel start; a window request executes a bridge call on the kernel's
execute channel with the output suppressed, so nothing appears as a cell. The
bridge wraps the native object into its SciStudio type by construction from
data and runs the existing preview provider for that type, so a table window
in a session is produced by the same code that produces it in the workflow
preview. Namespace fingerprints use the fingerprint function of the
dependency-analysis spec, imported inside the kernel. Memory is read from the
process itself.

**Two modes for three helpers.** `scistudio.input`, `scistudio.output`, and
`scistudio.load` are the only SciStudio-specific lines a notebook contains,
and the same lines must work in a session and in a packaged run. The launcher
sets an environment variable naming the mode. In session mode the helpers
speak to the bridge: `input` returns the bound run's port artefact reference,
`load` resolves it through the storage layer, and `output` registers names.
In packaged mode they speak to the Code Block's exchange folders, which is
how a Code Block already passes data to a script. Nothing in the notebook
changes between the two.

**Marks are bookkeeping, not execution.** The service keeps which cell last
bound each name, updated from each run's observed changed set. Before a run
it asks the graph for the definer of each read and compares; after a run it
asks the graph for the downstream set and marks it stale. Neither step
enqueues anything. Run-with-upstream is the one place the service chooses
cells to run on the person's behalf, and its skip rule is exact: a cell in the
slice is skipped only if nothing about it is questionable and every name it
changes is still bound by it, so the A, B, C case re-runs A and an
undisturbed chain re-runs nothing.

**Commits without touching the working tree.** ADR-054 §6.6 measured the cost
of add-and-commit; the same cost is available through plumbing —
`hash-object`, `update-index` against a temporary index file, `write-tree`,
`commit-tree`, `update-ref` — and plumbing is what keeps thirty commits an hour
from disturbing the branch's index or the working tree the person is editing.
The commit is queued after the result returns and carries the notebook as
captured at execution time, so a second run during the interval cannot change
what the first commit records. Packing is forced after a bounded number of
commits, because the project ships its own git and the default threshold is
a week of heavy use away.

**Packaging produces a Code Block, because that is what it is.** A Code Block
already runs a `.ipynb` through `nbconvert` from the project root with
exchange folders for its ports. Packaging generates a block declaration the
tier-1 scan discovers — a Python file in the project's blocks directory
defining a `CodeBlock` subclass with the ports and the notebook as its script
— and copies the notebook beside it. The one addition to the backend is the
cell selection: the slice is materialised as a temporary notebook so that
`nbconvert` runs exactly the cells the graph selected and nothing else. The
scan is not recursive, which is why the declaration sits directly in the
blocks directory rather than in a subdirectory.

**Asking reuses the pause that exists.** A packaged block set to ask is an
interactive block whose decision is a notebook commit and whose panel is the
Explore tab. The engine's interactive dispatch already runs a prompt phase,
holds a future, and runs a compute phase from the decision; the packaged
block's prompt names the notebook and the run's inputs, the frontend opens a
session over them, and confirming returns a commit. Interaction memory
already remaps a remembered decision by input signature; `on_new_input`
becomes the policy that decides whether the remap check is consulted at all.
For an authored interactive block the same setting changes nothing by default
and lets a block replay across changed inputs when a person wants it to.

**Lineage adds a table and reuses three.** `explore_sessions` parallels `runs`
so that everything downstream — block executions, data objects, io edges —
is the same code with a different foreign key. A packaged block's run is an
ordinary run whose block version is a commit sha, which is how the step points
back at the session.

**The API is the only door.** The route module exposes the operations of
FR-056 and nothing that reaches the kernel; the events of FR-057 go through
the WebSocket hub the workflow already uses, with new event types, so the
frontend keeps one connection.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `docs/specs/adr-054-explore-session.md` | create | This spec. |
| `src/scistudio/explore/session.py` | create | ExploreSession, SessionService, open and close, marks, last-bound-by (FR-001 to FR-006, FR-019 to FR-026). |
| `src/scistudio/explore/kernel.py` | create | KernelHandle over `jupyter_client`; launch, interrupt, restart, stop, death detection, memory (FR-007, FR-013 to FR-016). |
| `src/scistudio/explore/kernel_bridge.py` | create | Injected into the kernel: fingerprints, windows, bindings, memory, the helpers' session-mode backend, the block-call adapter (FR-009, FR-010, FR-049, FR-050). |
| `src/scistudio/explore/notebook_api.py` | create | `input`, `output`, `load` with mode selection (FR-010, FR-011). |
| `src/scistudio/__init__.py` | modify | Exposes the three helpers lazily at the top level. |
| `src/scistudio/explore/notebook.py` | create | `.ipynb` read and write, output stripping, cell metadata preservation, external-change reload (FR-005, FR-027, FR-032, FR-033). |
| `src/scistudio/explore/queue.py` | create | The queue, admission whitelist, coalescing, observation around runs, freeze bound (FR-017, FR-018, FR-021, FR-025). |
| `src/scistudio/explore/packaging.py` | create | Checks, declaration generation, notebook copy, port inference, repackaging (FR-037 to FR-043). |
| `src/scistudio/explore/lineage.py` | create | ExploreSessionRecord, cell-run records, retention hooks (FR-052 to FR-055). |
| `src/scistudio/core/versioning/_commit_ops.py` | modify | Plumbing commit to a ref with a temporary index; forced packing (FR-028 to FR-031, FR-036). |
| `src/scistudio/core/lineage/record.py`, `store.py` | modify | The `explore_sessions` table and cell-run records; block executions keyed to a session (FR-051, FR-052). |
| `src/scistudio/core/lineage/environment.py` | modify | Snapshot by reference (FR-034). |
| `src/scistudio/blocks/code/backends/notebook.py` | modify | Cell selection and packaged-mode environment (FR-040). |
| `src/scistudio/blocks/base/interactive.py` | modify | `on_new_input` and its defaults (FR-044, FR-045). |
| `src/scistudio/engine/scheduler/_dispatch.py` | modify | Consults `on_new_input` before the remap check; the packaged block's prompt and decision (FR-045 to FR-048). |
| `src/scistudio/api/routes/explore.py` | create | The session API (FR-056, FR-058). |
| `src/scistudio/api/ws.py` | modify | Session event types on the hub (FR-057). |
| `src/scistudio/api/project_layout.py` | modify | The explore directory joins the project layout (FR-001). |
| `pyproject.toml` | modify | `ipykernel` and `jupyter_client` (FR-059). |
| `tests/explore/**` | create | The tests listed in the frontmatter. |
| `tests/api/test_explore_routes.py` | create | API and event coverage. |
| `tests/blocks/base/test_interaction_policy.py` | create | `on_new_input` for both block kinds. |
| `tests/architecture/test_layer_deps.py` | modify | The explore subsystem's forbidden imports (FR-060). |

### 4.3 Implementation Sequence

| Task | Title | Story | Depends on | Verification |
|---|---|---|---|---|
| T-001 | Add the dependencies and the layer rule; rebuild the bundled runtime | Foundation | — | Layer test enumerates `explore`; the runtime carries ipykernel |
| T-002 | Kernel handle over `jupyter_client` with launch, interrupt, restart, stop, and death detection | US1, US7 | T-001 | A cell runs; interrupt ends a hung cell; a killed process is reported dead |
| T-003 | Kernel bridge: fingerprints, bindings, memory | US1, US3 | T-002 | Bridge calls answer without producing cells; fingerprints match the analysis spec's |
| T-004 | Notebook helpers in session mode and packaged mode | US1, US4 | T-003 | Same notebook runs in both modes against fixtures |
| T-005 | Notebook store: write with outputs, strip on commit, metadata preserved, external reload | US1, US6 | T-001 | Round trip keeps analysis records; external edit reloads cells |
| T-006 | Session open over block outputs, file, and paused run; first cell; list; close | US1 | T-002, T-005 | Generated first cell names ports; refusal when outputs absent |
| T-007 | Queue with coalescing, admission whitelist, observation around runs, freeze bound | US2, US3 | T-003, T-006 | Duplicate submissions run once; a bad emission is refused; panels bound to changed names are told |
| T-008 | Marks: last-bound-by, out-of-order check, stale propagation, run-stale, run-with-upstream | US2 | T-007 | The A, B, C fixture behaves as Story 2 states; nothing runs unasked |
| T-009 | Explore commits through plumbing to the session ref, off the path, with packing; branch commit | US6 | T-005 | One commit per run; working tree untouched; branch log clean |
| T-010 | Variable windows through the bridge for panels | US3 | T-003 | A window equals the preview provider's output for the same object |
| T-011 | `%pip` detection and environment snapshot by reference | US1 | T-004 | Snapshot changes after an install and is stored once |
| T-012 | Block-call adapter in the kernel, including the interactive-block call | US6 | T-003 | A block runs in-process with typed wrapping; an interactive call blocks until a value arrives |
| T-013 | Lineage: `explore_sessions`, cell-run records, block-call records, retention | US6 | T-009, T-012 | Records written; object resolves across the boundary |
| T-014 | Packaging: checks, declaration and copy, port inference, backend cell selection, reopen | US4 | T-008, T-009 | Refusals name cells; the packaged block runs the slice; reopen binds to the last run |
| T-015 | `on_new_input` for both block kinds; the packaged block's ask pause | US5 | T-014 | Replay never pauses; ask pauses on a changed signature; confirm carries a commit |
| T-016 | Kernel list and branch-switch retirement | US7 | T-002, T-006 | Every kernel listed with memory; branch change retires all |
| T-017 | Session API routes and WebSocket events | US1 to US7 | T-006 to T-016 | Every operation of FR-056 has a route; every event of FR-057 is emitted |

### 4.4 Verification Plan

Kernel lifecycle is tested against a real ipykernel process, because a mocked
kernel would pass a test that a real interrupt fails: launch, a hung cell
interrupted, restart resetting marks, stop terminating the process, and a
process killed from outside reported as dead. These tests spawn processes and
carry the serial marker.

The queue and the marks are tested on the A, B, C fixture and on the six-cell
fixture the dependency-analysis spec uses, asserting the exact set of cells
enqueued for each control and that no control enqueues a cell the person did
not name. The admission whitelist is tested with an accepted assignment and
with each refused statement form.

Storage and history are tested by running cells and reading the session's ref
with git: one commit per run, outputs absent, working tree and branch index
unchanged, and the branch log empty of explore commits until an explicit
commit.

Packaging is tested end to end: a fixture notebook is packaged, the generated
block is discovered by the registry, a workflow runs it, and its outputs are
compared to the session's. Each refusal condition has a fixture. The ask
setting is tested through the engine's interactive dispatch with a changed and
an unchanged signature.

Lineage is tested by following an object from a session into a workflow run
and back, and by checking that a packaged block's run record carries the
notebook commit.

The API is tested route by route, and the events by subscribing to the hub
during a scripted session and comparing the sequence.

Lint, type, and format checks run as usual. The layer test is expected to fail
until T-001.

### 4.5 Risks And Rollback

**The bundled runtime.** ipykernel and jupyter_client are new core
dependencies, and the runtime cannot receive them over the air. A release
that ships the session without a rebuilt runtime ships a session that cannot
start. T-001 rebuilds the runtime first, and the release checklist must
carry it.

**Protected paths.** Lineage, versioning, the block base, and the engine's
dispatch are protected core, so the implementation PRs that touch them need
the core-change label and escalate to the strict gate tier. The sequence
groups those touches into T-009, T-013, and T-015 so that the label is
needed on few PRs.

**A real kernel in tests.** Process-spawning tests are slow and can leak. They
carry the serial marker, run outside the parallel batch, and each test kills
what it started.

**Windows through the execute channel.** A bridge request that runs while a
long cell is executing waits behind it, because the kernel executes one
request at a time. This is the shallow freeze ADR-054 §6.3 accepts: the panel
keeps its last window and the read completes when the cell does. If it proves
too slow in practice, a control-channel path is the escape, and it is not
built until it is needed.

**Fingerprinting on every run.** The cost is bounded by the analysis spec's
constant and measured there; a session with a very large namespace pays it on
every run. The observation is what makes the marks true, so it is not
optional, and the bound is the mitigation.

**Rollback.** The explore subsystem and its route can be removed as a unit.
The modifications to protected paths are additive — a table, a setting with a
default that preserves current behaviour, a cell selection the backend
ignores when absent, a plumbing commit path nothing else calls — so reverting
them leaves existing behaviour intact.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: A session opened over a block's outputs produces a first cell
  naming every output port, and opening one over a block with no outputs is
  refused. Measured by test.
- **SC-002**: A cell containing `%pip install` installs into the kernel's
  environment and a new snapshot is recorded by reference. Measured by test
  against a local index.
- **SC-003**: On the A, B, C fixture, re-running B marks B out of order and C
  stale, runs nothing else, run-with-upstream runs A then B, and run-stale
  runs C. Measured by test.
- **SC-004**: An emitted snippet outside the whitelist is refused before it
  is queued and no cell is inserted; an admitted one is inserted after the
  current cell and runs. Measured by test.
- **SC-005**: An interrupt during a hung cell ends the cell within the
  kernel's interrupt timeout and the session survives. Measured by test
  against a real kernel.
- **SC-006**: Every cell run produces exactly one commit on the session's ref
  with outputs stripped, and the working tree, the branch index, and the
  branch log are unchanged. Measured by test.
- **SC-007**: A packaged fixture notebook registers as a block with the
  declared ports, runs in a workflow, and produces outputs equal to the
  session's. Measured by test.
- **SC-008**: Each packaging refusal condition is refused with the cells or
  reads named. Measured by one test per condition.
- **SC-009**: A packaged block set to replay never pauses; set to ask, it
  pauses on a changed signature and not on an unchanged one, and confirming
  runs the confirmed commit's slice. Measured by test through the engine's
  dispatch.
- **SC-010**: An authored interactive block set to replay runs across changed
  inputs without pausing; set to ask it behaves as today. Measured by test.
- **SC-011**: An object produced in a session and consumed by a workflow run
  resolves in both directions, and a packaged block's run record carries the
  notebook commit. Measured by test.
- **SC-012**: Every live kernel is listed with its memory; ending one
  terminates its process; a branch switch retires all. Measured by test.
- **SC-013**: Every operation in FR-056 has a route and every event in FR-057
  is emitted during a scripted session. Measured by test.
- **SC-014**: The explore subsystem imports neither the API, AI, nor engine
  layers, and the engine does not import it. Measured by the layer test.
- **SC-015**: The bundled runtime built for the release carries ipykernel and
  jupyter_client. Measured by starting a session from the packaged
  application.

## 6. Assumptions

- **A-001**: Execution semantics are Jupyter's and the graph never rebinds or
  re-runs. The owner rejected version retention with rebinding on 2026-09-02.
  _Source: owner._
- **A-002**: The session is not a node and involves no pause while exploring;
  ADR-054 §4.1 and §5.3 as revised. _Source: adr._
- **A-003**: Notebooks live in `{project}/explore/` and a packaged block's
  declaration and copy live directly in `{project}/blocks/`, because the
  tier-1 scan is not recursive. _Source: owner, existing-system._
- **A-004**: Run-with-upstream skips a cell in the slice only if it is neither
  stale nor out of order and every name it changes is still last bound by it.
  _Source: owner._
- **A-005**: `jupyter_client` is the kernel's only client and `jupyter_server`
  is not used. _Source: owner._
- **A-006**: The three notebook helpers are exposed at the top-level package.
  The top-level package is not one of ADR-052's canonical roots, so the frozen
  surface inventory is unchanged; the helpers carry stability markers.
  _Source: inferred._
- **A-007**: A packaged block set to ask is in scope. The owner reversed a
  deferral of it on 2026-09-02, and issue 2221 was closed. _Source: owner._
- **A-008**: The packaged block reuses the engine's existing interactive
  pause; its prompt phase needs no worker because the prompt is the notebook
  and the run's inputs, both already known. _Source: inferred._
- **A-009**: Explore commits are written with plumbing rather than the
  add-and-commit path ADR-054 §6.6 measured; the cost is the same order and
  the working tree is untouched. _Source: inferred._
- **A-010**: Variable windows are served over the kernel's execute channel and
  wait behind a running cell, which ADR-054 §6.3's shallow freeze accepts.
  _Source: inferred._
- **A-011**: The reference-to-object load a session's `scistudio.load`
  performs exists in the storage layer today for the engine's use; if it
  proves to be engine-bound, moving it into `core` is a task of T-004 and
  touches a protected path. _Source: inferred._
- **A-012**: The file watcher that suppresses product-written files must not
  suppress notebook writes the session needs to observe from outside, and
  must not reload the session on its own writes. T-005 verifies both.
  _Source: inferred._
