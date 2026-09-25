---
spec_id: adr-056-user-code-import
title: "Importing And Reloading User Code Through Python's Import System"
status: Draft
spec_standard: 2
created: 2026-09-17
input: "Implement ADR-056: replace SciStudio's by-path user-code importing, per-kind discovery and five reload drivers with one user import path, one discovery step, one precedence rule, one reset entry point and one failure record."
owners:
  - "@jiazhenz026"
related_adrs:
  - 56
  - 53
  - 54
  - 27
  - 17
related_specs:
  - adr-053-personal-tool-library
  - adr-054-panels
scope:
  in:
    - "Data types, blocks and their helper files, panel.py, plot render scripts"
    - "Legacy previewers until their removal in 0.3.6"
    - "The project tier, the library tier and the tutorial-scoped library"
    - "The backend, the worker, the panel process, the plot harness and the standalone MCP bridge"
  out:
    - "Code Block scripts, which run as programs in a user-chosen interpreter (ADR-041)"
    - "Installed plugin packages, which are imported through entry points (ADR-052)"
    - "Running user code outside the backend process (issue #1531)"
    - "Which tiers a tutorial project composes (ADR-053 Learning Center spec)"
    - "Panel pages served as HTML and JavaScript (ADR-054 Section 4)"
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-053-personal-tool-library.md
    - docs/specs/adr-054-panels.md
    - docs/specs/adr-056-user-code-import.md
    - src/scistudio/ai/agent/mcp/_reload.py
    - src/scistudio/ai/agent/mcp/runtime.py
    - src/scistudio/ai/agent/mcp/tools_authoring.py
    - src/scistudio/ai/agent/mcp/tools_library.py
    - src/scistudio/ai/agent/mcp/tools_workflow/_models.py
    - src/scistudio/api/routes/blocks.py
    - src/scistudio/api/routes/git.py
    - src/scistudio/api/routes/packages.py
    - src/scistudio/api/routes/panels.py
    - src/scistudio/api/routes/tutorials.py
    - src/scistudio/api/routes/types.py
    - src/scistudio/api/routes/user_library.py
    - src/scistudio/api/runtime/_file_writes.py
    - src/scistudio/api/runtime/_projects.py
    - src/scistudio/api/schemas.py
    - src/scistudio/api/ws.py
    - src/scistudio/blocks/base/ports.py
    - src/scistudio/blocks/io/_unified_dispatch.py
    - src/scistudio/blocks/io/savers/_capability.py
    - src/scistudio/blocks/io/savers/_helpers.py
    - src/scistudio/blocks/io/simple_io.py
    - src/scistudio/blocks/registry/__init__.py
    - src/scistudio/blocks/registry/_capability.py
    - src/scistudio/blocks/registry/_scan.py
    - src/scistudio/core/dropins.py
    - src/scistudio/core/entry_points.py
    - src/scistudio/core/types/base.py
    - src/scistudio/core/types/collection.py
    - src/scistudio/core/types/composite.py
    - src/scistudio/core/types/registry.py
    - src/scistudio/desktop/paths.py
    - src/scistudio/engine/runners/local.py
    - src/scistudio/engine/runners/process_handle.py
    - src/scistudio/engine/runners/worker.py
    - src/scistudio/panels/bootstrap.py
    - src/scistudio/panels/process.py
    - src/scistudio/panels/registry.py
    - src/scistudio/panels/service.py
    - src/scistudio/panels/validation.py
    - src/scistudio/panels/watcher.py
    - src/scistudio/plot/_harness.py
    - src/scistudio/plot/runtime.py
    - src/scistudio/tutorials/discovery.py
    - tests/ai/test_mcp_execution_tools.py
    - tests/ai/test_mcp_tools_library.py
    - tests/api/test_block_origin_tiers.py
    - tests/api/test_blocks.py
    - tests/api/test_registry_reload_symmetry.py
    - tests/blocks/test_desktop_package_discovery.py
    - tests/blocks/test_dropin_type_import.py
    - tests/blocks/test_registry_version_strict.py
    - tests/blocks/test_tier1_dropin_subprocess.py
    - tests/engine/test_local_runner.py
    - tests/panels/test_miniapp_context.py
    - tests/tutorials/test_core_tutorial_what_is_a_type.py
    - tests/tutorials/test_scoped_library.py
  excludes: []
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/user/user-code.md
    - src/scistudio/core/user_code/__init__.py
    - src/scistudio/core/user_code/discovery.py
    - src/scistudio/core/user_code/events.py
    - src/scistudio/core/user_code/failures.py
    - src/scistudio/core/user_code/identity.py
    - src/scistudio/core/user_code/import_path.py
    - src/scistudio/core/user_code/loader.py
    - src/scistudio/core/user_code/names.py
    - src/scistudio/core/user_code/precedence.py
    - src/scistudio/core/user_code/reset.py
    - tests/core/user_code/__init__.py
    - tests/core/user_code/test_discovery_precedence.py
    - tests/core/user_code/test_failures_and_events.py
    - tests/core/user_code/test_import_path.py
    - tests/core/user_code/test_names.py
    - tests/core/user_code/test_reset.py
    - tests/integration/test_user_code_identity.py
  excludes: []
tests:
  - tests/blocks/test_dropin_type_import.py
  - tests/api/test_registry_reload_symmetry.py
  - tests/api/test_blocks.py
  - tests/ai/test_mcp_tools_library.py
language_source: en
---

# Spec: Importing And Reloading User Code Through Python's Import System

## 1. Change Summary

SciStudio imports user files by file path, under module names it makes up, and
treats `sys.path` as something to open and close around each import. More than
ten call sites do this, each with its own rules for what is importable, when to
forget it, and how to report a failure. ADR-056 replaces that with Python's own
import system, the way a Jupyter kernel treats the files beside a notebook.

This spec implements ADR-056. It defines one ordered user import path that
every process carrying user code keeps on `sys.path`, one discovery step that
finds every kind of user extension, one precedence rule that settles same-named
items, one name check that runs before anything is imported, one reset entry
point that all refresh triggers call, and one failure record that every listing
and reload response returns. It removes the generated module names, the
`sys.path` window, the refusing `sys.meta_path` finder and the per-kind
scanners and reload drivers they support.

The request came from the owner, who accepted ADR-056 as the governing
decision. The spec decides the nine items ADR-056 Section 7 leaves open.

## 2. User Stories

### User Story 1 - A user type is one class everywhere (Priority: P1)

A scientist writes `types/scverse_omics.py` defining `AnnData`, and a block
that declares an `AnnData` port. The block runs, saves and previews without the
type failing its own check.

**Why this priority**: This is the failure users hit most often and cannot work
around. "SaveAnnData expected AnnData, got AnnData" (#2480) stops a workflow
with a message that reads as nonsense. Nothing else in this spec matters if a
type still exists twice in a process.

**Independent Test**: Load a project whose `types/` defines a type and whose
`blocks/` imports it by name. Assert the class object registered by the type
registry, the class the block module holds, and the class the worker resolves
are the same object within each process.

**Acceptance Scenarios**:

- **Given** a project type `types/scverse_omics.py` defining `AnnData` and a block importing it with `from scverse_omics import AnnData`, **When** the block runs and its output is saved with `SimpleSaver`, **Then** the save succeeds and no type check compares two distinct classes of the same name.
- **Given** the same project, **When** the block's output port is checked against a downstream block's input port, **Then** the check passes by `isinstance` without a name-based fallback.
- **Given** an object of a user type produced in the backend, **When** it is pickled and read in a worker process, **Then** it unpickles to that process's single class for the type.

### User Story 2 - An edit takes effect, whatever triggered it (Priority: P1)

A scientist edits a block, a type or a panel — in the app, in an external
editor, through the agent, or by switching a git branch — and the next thing
they do uses the edited code.

**Why this priority**: Stale code runs silently and produces wrong results with
no sign that anything is wrong. Today five reload drivers each rebuild a
different subset of registries, so whether an edit takes effect depends on
which surface the user touches next.

**Independent Test**: Change a user file through each trigger in turn and
assert that a subsequent listing, run and preview all use the new code, without
restarting the backend.

**Acceptance Scenarios**:

- **Given** a registered block, **When** its file is edited and saved through the app, **Then** the next listing and the next run use the edited code.
- **Given** a project on a git branch, **When** the branch is switched so that a type file differs, **Then** no module from the previous branch's file resolves afterwards.
- **Given** a package-shaped type `types/<name>/__init__.py` with submodules, **When** a submodule is edited, **Then** the change takes effect with the package.
- **Given** no user file has changed, **When** a trigger fires, **Then** the reset does nothing.

### User Story 3 - A block imports the file beside it (Priority: P2)

A scientist splits shared code into a helper file and imports it from several
blocks, the way they would beside a notebook.

**Why this priority**: Today this fails, and it fails by making every block in
the importing file disappear with no message. It blocks the natural way to
organize a growing personal library, but it does not corrupt results.

**Independent Test**: Place a helper beside two block files, import it from
both, and assert both blocks register and run.

**Acceptance Scenarios**:

- **Given** `blocks/helpers.py` and `blocks/analyze.py` importing it with `from helpers import prepare`, **When** the project loads, **Then** `analyze` registers and runs.
- **Given** `blocks/a.py` importing a class from `blocks/b.py`, **When** the project loads, **Then** both blocks register, and the block defined in `b.py` is registered once, from `b.py`.
- **Given** a panel folder and a plot folder each containing a helper module, **When** the panel process and the plot harness run, **Then** each imports its helper and any project type by name.

### User Story 4 - A file that fails to load says so (Priority: P2)

A scientist whose file raises on import, or whose file is refused, sees which
file it was and why, wherever they look.

**Why this priority**: A silent disappearance sends the user looking for a bug
in the wrong place. Today only the block listing carries failures, and a reload
can report `removed: []` while five blocks vanish.

**Independent Test**: Break a type file, a block file and a panel, then assert
every listing and every reload response names each file, its error type and a
one-line message.

**Acceptance Scenarios**:

- **Given** a type file that raises `ImportError` at import, **When** the Data types tab is listed, **Then** the response carries a failure record naming that file.
- **Given** five blocks that vanish because their file now raises, **When** a reload runs, **Then** the reload response reports them as removed and carries their failure record.
- **Given** a refused file name, **When** any listing runs, **Then** the failure record says the file was refused and asks the user to rename it.

### User Story 5 - A clashing file name is refused, not silently loaded (Priority: P3)

A scientist names a file `json.py` or `pandas.py`. SciStudio refuses it and
says so, instead of shadowing the library or being shadowed by it.

**Why this priority**: The damage is rare but severe and very hard to diagnose,
because the symptom appears in unrelated code. It is last because the check is
simple once the user import path exists.

**Independent Test**: Place files named after a standard-library module, an
installed package and a duplicate stem in one tier, and assert each is refused
with a rename message and registers nothing.

**Acceptance Scenarios**:

- **Given** `blocks/json.py`, **When** the project loads, **Then** the file is refused, registers nothing, and its failure record asks for a rename.
- **Given** `types/pandas.py`, **When** the project loads, **Then** the file is refused, and `import pandas` anywhere in the process still resolves to the installed package.
- **Given** `types/util.py` and `blocks/util.py` in the same tier, **When** the project loads, **Then** both are refused as a conflict.
- **Given** `types/util.py` in the project tier and `types/util.py` in the library tier, **When** the project loads, **Then** the project file is used and the library file is reported as shadowed.

### Edge Cases

- A user file that is valid Python but registers nothing loads without a failure record.
- A reset that runs while a workflow is running does not change the classes that run is already using; the run finishes against the classes it started with.
- A resident panel process whose imported module did not change is not restarted.
- A project with no `types/` or `blocks/` directory contributes no entries to the user import path.
- The standalone MCP bridge and the backend hold separate copies of the user modules; a reset in one does not reset the other.
- A pickle written under a generated module name from a previous version does not resolve; it is reported as a failure and not silently mismatched.

## 3. Functional Requirements

| FR | Name | Behavior | ADR decision |
|---|---|---|---|
| FR-001 | User import path | Every process that runs user code appends one ordered list of user directories to the end of `sys.path` and leaves it there: the process entry folder when there is one, then project `types/`, project `blocks/`, library `types/`, library `blocks/`. A directory that does not exist contributes no entry. | Section 4.1 |
| FR-002 | Import by module name | Every user file is imported with `importlib.import_module(<stem>)`, and every package-shaped user directory by its directory name. No code path executes a user file by path, and no code path invents a module name. | Section 4.2 |
| FR-003 | One class per type per process | Because each user file is imported once per process, each user data type has one class object in that process, and every in-process type check uses `isinstance`. Identity comparisons and name-based fallbacks are both removed. | Section 4.2 |
| FR-004 | Type resolution across a boundary | Data that crosses a process boundary or is read back from storage is matched to its class by its recorded type-name chain, unchanged from today. | Section 4.2 |
| FR-005 | One discovery step | One step walks the tiers and returns, per kind of extension, the candidates found in each tier together with the failures met. Blocks, types, panels, plots, legacy previewers and tutorials all read from it, and each registry keeps only the part specific to its kind. | Section 4.3 |
| FR-006 | One precedence rule | When two sources provide an item with the same identity, one rule decides for every kind and after every refresh: project, then library, then installed packages, then core. A user item may replace a package or core item of the same identity. | Section 4.4 |
| FR-007 | Shadowed items are reported | An item that loses the precedence rule is recorded as shadowed, with its origin and the origin of the winner, and is returned by the listing for its kind. | Section 4.4 |
| FR-008 | Name check before import | Before a user directory is used, each stem in it is checked: a stem in `sys.stdlib_module_names` is refused; a stem that `importlib.util.find_spec` resolves outside the user import path is refused; a stem appearing in more than one directory of the same tier is refused as a conflict, for every file with that stem. A refused file is not imported, registers nothing, and produces a failure record asking for a rename. Across tiers no refusal applies; the order of FR-001 decides. | Section 4.5 |
| FR-009 | User module reset | One entry point performs the reset: collect every module in `sys.modules` whose `__file__` lies under a directory of the current or previous user import path, submodules included; remove them, delete their stale bytecode, and call `importlib.invalidate_caches()`; replace the user import path on `sys.path` when the project changed; run discovery again and rebuild every registry from its result. | Section 4.6 |
| FR-010 | Every trigger calls the reset | A file saved through the app, a change seen by a watcher or by the standalone MCP bridge, a git branch switch or version restore, a package install or removal, the Reload action, the `reload_blocks` tool, and opening another project all call the FR-009 entry point and nothing else. Watcher-fed triggers are debounced and suppress the product's own writes. | Sections 4.6, 7 |
| FR-011 | A reset with nothing to do does nothing | The entry point compares the modification times of the user files against those recorded at the last import and returns without resetting when none changed. The comparison has a resolution that detects an edit within the same second. | Section 4.6 |
| FR-012 | Child processes receive the user import path | The worker, the panel process and the plot harness receive the user import path from the process that starts them, and apply it before importing any user module. | Sections 4.1, 7 |
| FR-013 | A resident panel process restarts when its code changes | The panel service records which user modules a resident panel process imported, and restarts that process when a reset removed one of them. A panel whose imported modules did not change keeps running. | Sections 4.6, 5.2, 7 |
| FR-014 | One failure record | Discovery and import record every refused or failed user file with its path, its origin, the error type and a one-line message. Every listing of extensions and every reload result returns this same record, and a reload's removed set is derived from the same data. | Section 4.8 |
| FR-015 | One refresh event | A reset emits one event describing its result: what was added, removed, shadowed and failed, per kind. Every frontend catalog and every agent tool reacts to that one event. | Section 7 |
| FR-016 | Identity per kind | One identity is defined per kind of extension and used by FR-006 and FR-014: the registered type name for types, the registered block type for blocks, the panel id for panels, the plot id for plots, the previewer id for legacy previewers, the tutorial key for tutorials. | Section 7 |
| FR-017 | One origin vocabulary | One set of origin labels is used on the wire for every kind: `project`, `library`, `package`, `core`. | Section 7 |
| FR-018 | Superseded machinery is removed | The generated module names, every by-path execution, the `sys.path` window, `transient_dropin_modules`, the guard's deletion of bare modules, the refusing `sys.meta_path` finder, the file path stamped on block classes, the per-kind scanners and the separate reload drivers are removed, and bytecode eviction moves into the reset. | Section 4.7 |

Three of these decide items ADR-056 Section 7 left open and are therefore
stated here rather than inherited.

**FR-006, precedence.** Module-name resolution and item precedence are separate
questions, and this spec answers them differently. Module names resolve through
`sys.path`, where user directories come last and therefore never shadow the
standard library or an installed package; FR-008 refuses the file names that
could. Item precedence is about which registered item of a given identity the
user sees, and there the project wins over the library, which wins over an
installed package, which wins over core. This keeps what panels and legacy
previewers already do, keeps ADR-053 FR-014, and keeps the personal tool
library able to replace a built-in item. It changes blocks, whose winner is
today whichever registration ran last, and types, where core and packages
currently win over user files.

**FR-010, triggers.** The reset entry point is the only way any registry is
rebuilt. Triggers differ only in how they reach it: a write through the app
calls it directly after the write completes, a watcher calls it after a
debounce interval with the product's own writes suppressed, and the standalone
MCP bridge runs its own watcher against the same directories in its own
process.

**FR-015, refresh event.** One event replaces the per-surface refresh signals.
Its payload is the result of the discovery step, so a consumer that re-renders
from it holds the same state the backend holds, with no follow-up request.

## 4. New Modules

| ID | FR | Module |
|---|---|---|
| NEW-001 | FR-001, FR-012 | src/scistudio/core/user_code/import_path.py |
| NEW-002 | FR-008 | src/scistudio/core/user_code/names.py |
| NEW-003 | FR-002, FR-003 | src/scistudio/core/user_code/loader.py |
| NEW-004 | FR-016, FR-017 | src/scistudio/core/user_code/identity.py |
| NEW-005 | FR-014 | src/scistudio/core/user_code/failures.py |
| NEW-006 | FR-005 | src/scistudio/core/user_code/discovery.py |
| NEW-007 | FR-006, FR-007 | src/scistudio/core/user_code/precedence.py |
| NEW-008 | FR-015 | src/scistudio/core/user_code/events.py |
| NEW-009 | FR-009, FR-010, FR-011 | src/scistudio/core/user_code/reset.py |
| NEW-010 | FR-001, FR-005, FR-009 | src/scistudio/core/user_code/__init__.py |
| NEW-011 | FR-001, FR-012 | tests/core/user_code/test_import_path.py |
| NEW-012 | FR-008 | tests/core/user_code/test_names.py |
| NEW-013 | FR-005, FR-006, FR-007 | tests/core/user_code/test_discovery_precedence.py |
| NEW-014 | FR-009, FR-010, FR-011 | tests/core/user_code/test_reset.py |
| NEW-015 | FR-014, FR-015 | tests/core/user_code/test_failures_and_events.py |
| NEW-016 | FR-003, FR-004, FR-012, FR-013 | tests/integration/test_user_code_identity.py |
| NEW-017 | — | tests/core/user_code/__init__.py |

### NEW-001 src/scistudio/core/user_code/import_path.py

Owns the ordered list of FR-001 and nothing else. It builds the list for a
project, installs it on `sys.path`, replaces it when the project changes, and
serialises it for a child process.

Responsible for: resolving the five ordered directories from a project
directory and the tier rules already in `core/dropins.py`; dropping entries
that do not exist; appending the list after everything already on `sys.path`
and never prepending; removing a previous project's entries when it replaces
them; reading and writing the environment variable that carries the list to
the worker, the panel process and the plot harness (FR-012); reporting the
list currently installed, which the reset uses to find the modules it must
forget.

Not responsible for: deciding what is importable by name (NEW-002), importing
anything (NEW-003), or the roots of installed packages and plugins, which stay
with `desktop/paths.py` and `core/entry_points.py`.

The entry folder of a panel or plot process is first in the list and is passed
per process; the four tier directories come from the project.

### NEW-002 src/scistudio/core/user_code/names.py

Implements the FR-008 name check as a pure function over a list of
directories. It is the rule that survives from `core/dropins.py`'s collision
guard; the mechanism there — the refusing `sys.meta_path` finder, the bare
module deletion, the probing window — does not.

Responsible for: listing the importable stems of a directory, single files and
package directories alike; refusing a stem in `sys.stdlib_module_names`;
refusing a stem that `importlib.util.find_spec` resolves to a file outside the
user import path; refusing every file of a stem that appears in more than one
directory of the same tier; returning the refusals as failure records (NEW-005)
carrying a rename message.

Not responsible for: importing, registering, or installing anything on
`sys.meta_path`. It refuses by returning a refusal, and a refused file is never
handed to NEW-003.

Refusal is per tier. A stem in both tiers is not a conflict; FR-001's order
decides, and the loser is shadowed (NEW-007), not refused.

### NEW-003 src/scistudio/core/user_code/loader.py

The only place in SciStudio that imports a user module. Every registry goes
through it.

Responsible for: importing one stem with `importlib.import_module`; returning
the module together with the classes it defines, so a caller can register only
what the module defines and not what it imported; turning any exception into a
failure record (NEW-005) without letting it escape; recording the file's
modification time at import, which FR-011 compares against later.

Not responsible for: choosing what to import (NEW-006), deciding which of two
same-named results wins (NEW-007), or forgetting modules (NEW-009).

No function here takes a file path to execute. A module that is already in
`sys.modules` is returned as it is; making it current is the reset's job.

### NEW-004 src/scistudio/core/user_code/identity.py

Holds the two vocabularies FR-016 and FR-017 define, so that precedence,
failure records, events and every wire schema use one set of terms.

Responsible for: the enumeration of extension kinds (type, block, panel, plot,
previewer, tutorial); the identity function per kind, which maps a discovered
candidate to the string that decides sameness; the origin labels `project`,
`library`, `package` and `core`, and their order.

Not responsible for: reading any file, or knowing why one origin outranks
another beyond the declared order.

### NEW-005 src/scistudio/core/user_code/failures.py

The one failure record of FR-014, replacing `DropinFailure` and the five
free-text diagnostic lists in use today.

Responsible for: the record itself — path, kind, origin, error type, one-line
message; constructing one from an exception and one from a refusal; a
collection type that a listing or a reload result can carry; the conversion to
the wire shape.

Not responsible for: deciding when something failed, or where the record is
displayed.

### NEW-006 src/scistudio/core/user_code/discovery.py

The single discovery step of FR-005. It runs the name check, imports what
survives, and returns one result covering every kind, for every tier.

Responsible for: walking the tiers for each kind of extension; calling NEW-002
before importing anything from a directory; calling NEW-003 for the files that
pass; reading the non-Python descriptors each kind needs — `panel.json` for
panels, tutorial manifests for tutorials; collecting the candidates and the
failures into one result object; recording each candidate's origin and the
modification time of the file it came from.

Not responsible for: registering anything, resolving same-name conflicts
(NEW-007), or knowing what a block, type or panel means. It returns
candidates; each registry keeps the part specific to its kind.

The result is what every registry rebuilds from, and what the refresh event
(NEW-008) carries.

### NEW-007 src/scistudio/core/user_code/precedence.py

Applies FR-006 to a discovery result, for every kind, using the identity
functions of NEW-004.

Responsible for: grouping candidates by kind and identity; selecting the
winner by origin order; returning the winners and, separately, the shadowed
candidates with the origin of the item that beat them (FR-007).

Not responsible for: the origin order itself, which is NEW-004's, or for what
a registry does with a winner.

### NEW-008 src/scistudio/core/user_code/events.py

The one refresh event of FR-015.

Responsible for: the event payload — per kind, what was added, removed,
shadowed and what failed; building it by comparing the previous discovery
result with the new one; the wire shape the WebSocket carries.

Not responsible for: emitting the event, which belongs to the API runtime, or
for how a frontend catalog reacts.

The removed set is derived from the comparison, not reported by a caller. This
is what makes the reload diff correct where today it can report `removed: []`
while blocks disappear.

### NEW-009 src/scistudio/core/user_code/reset.py

The FR-009 entry point. Every trigger in the product calls this and nothing
else.

Responsible for: recording the modification times seen at the last import and
comparing them to decide whether there is anything to do (FR-011), at a
resolution finer than one second; collecting every module in `sys.modules`
whose `__file__` lies under the current or the previous user import path,
submodules included; removing them, deleting their stale bytecode and
invalidating the import caches; asking NEW-001 to replace the user import path
when the project changed; running NEW-006 and NEW-007 and handing the result to
the registries; building the FR-015 event from the comparison.

Not responsible for: the triggers themselves, restarting a resident panel
process, or emitting the event on the wire. It reports which modules it forgot,
which the panel service uses for FR-013.

### NEW-010 src/scistudio/core/user_code/__init__.py

The public surface of the subsystem. Callers outside `core/user_code/` import
from here, not from the modules above.

Responsible for: re-exporting the reset entry point, the discovery result, the
failure record, the refresh event and the identity vocabularies.

Not responsible for: any behavior of its own.

### NEW-011 tests/core/user_code/test_import_path.py

Covers FR-001 and FR-012: the order of the list, exclusion of directories that
do not exist, the append-never-prepend rule, replacement on a project change,
and the round trip through the child-process environment.

### NEW-012 tests/core/user_code/test_names.py

Covers FR-008: a stdlib stem, an installed-package stem, a same-tier duplicate
across `types/` and `blocks/`, and a cross-tier same stem, which is not a
refusal. Asserts a refused file registers nothing and that the installed module
of the same name still resolves.

### NEW-013 tests/core/user_code/test_discovery_precedence.py

Covers FR-005, FR-006, FR-007 and FR-016: one discovery step feeding every
kind, the same winner after a full rebuild and after a reset, a user item
replacing a package or core item, and the shadowed report naming both origins.

### NEW-014 tests/core/user_code/test_reset.py

Covers FR-009, FR-010 and FR-011: forgetting a single-file module and a
package with submodules, a project switch leaving no module of the previous
project resolvable, an edit within the same second taking effect, and a reset
doing nothing when no file changed.

### NEW-015 tests/core/user_code/test_failures_and_events.py

Covers FR-014 and FR-015: one record shape from an import error and from a
refusal, the same record on every listing and reload result, and a refresh
event whose removed set is correct when files disappear.

### NEW-016 tests/integration/test_user_code_identity.py

Covers User Story 1 end to end, across processes: one class per user type in
the backend, in a worker and in a panel process; the `SimpleSaver` case of
\#2480; a pickle written in the backend read in a worker; and a resident panel
process restarted when a module it imported changed (FR-013).

### NEW-017 tests/core/user_code/__init__.py

Package marker, matching the layout of the existing test packages.

## 5. Changed Modules

| ID | FR | Action | Module |
|---|---|---|---|
| CHANGE-001 | FR-001, FR-008, FR-018 | modify | src/scistudio/core/dropins.py |
| CHANGE-002 | FR-001, FR-018 | modify | src/scistudio/desktop/paths.py |
| CHANGE-003 | FR-018 | modify | src/scistudio/core/entry_points.py |
| CHANGE-004 | FR-002, FR-005, FR-014, FR-018 | modify | src/scistudio/core/types/registry.py |
| CHANGE-005 | FR-003, FR-018 | modify | src/scistudio/core/types/base.py |
| CHANGE-006 | FR-003 | verify | src/scistudio/core/types/collection.py |
| CHANGE-007 | FR-003 | verify | src/scistudio/core/types/composite.py |
| CHANGE-008 | FR-002, FR-014, FR-018 | modify | src/scistudio/blocks/registry/__init__.py |
| CHANGE-009 | FR-002, FR-005, FR-006, FR-018 | modify | src/scistudio/blocks/registry/_scan.py |
| CHANGE-010 | FR-002, FR-018 | modify | src/scistudio/blocks/registry/_capability.py |
| CHANGE-011 | FR-003, FR-018 | modify | src/scistudio/blocks/base/ports.py |
| CHANGE-012 | FR-003 | verify | src/scistudio/blocks/io/simple_io.py |
| CHANGE-013 | FR-018 | modify | src/scistudio/blocks/io/_unified_dispatch.py |
| CHANGE-014 | FR-003 | verify | src/scistudio/blocks/io/savers/_capability.py |
| CHANGE-015 | FR-003, FR-018 | modify | src/scistudio/blocks/io/savers/_helpers.py |
| CHANGE-016 | FR-002, FR-012, FR-018 | modify | src/scistudio/engine/runners/worker.py |
| CHANGE-017 | FR-012, FR-018 | modify | src/scistudio/engine/runners/local.py |
| CHANGE-018 | FR-012, FR-018 | modify | src/scistudio/engine/runners/process_handle.py |
| CHANGE-019 | FR-002, FR-012 | modify | src/scistudio/panels/bootstrap.py |
| CHANGE-020 | FR-012, FR-013 | modify | src/scistudio/panels/process.py |
| CHANGE-021 | FR-005, FR-006, FR-007, FR-014 | modify | src/scistudio/panels/registry.py |
| CHANGE-022 | FR-010, FR-013, FR-015 | modify | src/scistudio/panels/service.py |
| CHANGE-023 | FR-010 | modify | src/scistudio/panels/watcher.py |
| CHANGE-024 | FR-005 | modify | src/scistudio/panels/validation.py |
| CHANGE-025 | FR-002, FR-012 | modify | src/scistudio/plot/_harness.py |
| CHANGE-026 | FR-012 | modify | src/scistudio/plot/runtime.py |
| CHANGE-027 | FR-005, FR-006, FR-014, FR-016 | modify | src/scistudio/tutorials/discovery.py |
| CHANGE-028 | FR-009, FR-010, FR-015 | modify | src/scistudio/api/runtime/_projects.py |
| CHANGE-029 | FR-010 | modify | src/scistudio/api/runtime/_file_writes.py |
| CHANGE-030 | FR-007, FR-014, FR-015, FR-017 | modify | src/scistudio/api/schemas.py |
| CHANGE-031 | FR-010, FR-014 | modify | src/scistudio/api/routes/blocks.py |
| CHANGE-032 | FR-010, FR-014 | modify | src/scistudio/api/routes/types.py |
| CHANGE-033 | FR-010, FR-014 | modify | src/scistudio/api/routes/panels.py |
| CHANGE-034 | FR-010 | modify | src/scistudio/api/routes/git.py |
| CHANGE-035 | FR-010 | modify | src/scistudio/api/routes/user_library.py |
| CHANGE-036 | FR-010 | modify | src/scistudio/api/routes/packages.py |
| CHANGE-037 | FR-010 | modify | src/scistudio/api/routes/tutorials.py |
| CHANGE-038 | FR-015 | modify | src/scistudio/api/ws.py |
| CHANGE-039 | FR-009, FR-010, FR-011 | modify | src/scistudio/ai/agent/mcp/runtime.py |
| CHANGE-040 | FR-014, FR-015 | modify | src/scistudio/ai/agent/mcp/tools_authoring.py |
| CHANGE-041 | FR-014 | modify | src/scistudio/ai/agent/mcp/tools_workflow/_models.py |
| CHANGE-042 | FR-002, FR-003 | modify | tests/blocks/test_dropin_type_import.py |
| CHANGE-043 | FR-009, FR-010, FR-015 | modify | tests/api/test_registry_reload_symmetry.py |
| CHANGE-044 | FR-014 | modify | tests/api/test_blocks.py |
| CHANGE-045 | FR-009, FR-014 | modify | tests/ai/test_mcp_tools_library.py |
| CHANGE-046 | FR-012, FR-018 | modify | tests/ai/test_mcp_execution_tools.py |
| CHANGE-047 | FR-006, FR-017 | modify | tests/api/test_block_origin_tiers.py |
| CHANGE-048 | FR-002, FR-018 | modify | tests/blocks/test_desktop_package_discovery.py |
| CHANGE-049 | FR-002 | modify | tests/blocks/test_registry_version_strict.py |
| CHANGE-050 | FR-002, FR-012 | modify | tests/blocks/test_tier1_dropin_subprocess.py |
| CHANGE-051 | FR-012, FR-018 | modify | tests/engine/test_local_runner.py |
| CHANGE-052 | FR-012, FR-013 | modify | tests/panels/test_miniapp_context.py |
| CHANGE-053 | FR-002, FR-003 | modify | tests/tutorials/test_core_tutorial_what_is_a_type.py |
| CHANGE-054 | FR-001, FR-006 | modify | tests/tutorials/test_scoped_library.py |
| CHANGE-055 | FR-009 | modify | src/scistudio/ai/agent/mcp/tools_library.py |

### CHANGE-001 src/scistudio/core/dropins.py

Keeps the tier vocabulary, loses the import machinery. The directory
resolvers — `user_library_dir`, `project_blocks_dir`, `project_types_dir`,
`library_root_for_project`, `_tier_dirs`, `block_scan_dirs`, `type_scan_dirs`,
`panel_scan_dirs`, `tutorial_scan_dirs`, `project_dir_from_env` — stay and
become the inputs NEW-001 and NEW-006 read.

Removed: `dropin_import_roots`, `previewer_import_roots`,
`dropin_type_roots_for_block_dirs`, `dropin_import_roots_for_block_dirs`;
`_RefusedNameFinder` with `_REFUSED_NAMES`, `_sys_path_without`,
`_bind_or_refuse`, `_root_warrant`, `_installed_origin`, `_is_within`,
`_importable_entries`, `guard_dropin_type_roots`, `guard_dropin_roots`,
`DropinTypeCollision`; `transient_dropin_modules`. `evict_cached_bytecode`
moves to NEW-009. `_importable_entries`'s file-listing behavior is reproduced
by NEW-002, which needs the same single-file and package listing.

`register_block_scan_dirs` and `register_type_scan_dirs` lose their purpose
once registries rebuild from a discovery result, and are removed with
CHANGE-004 and CHANGE-008.

### CHANGE-002 src/scistudio/desktop/paths.py

`prepended_sys_paths` is removed, together with its eleven call sites listed
across this section. `activate_pythonpath_entries` is removed as dead code; it
has no caller in `src/` or `tests/`.

Everything about installed packages and the user dependency site stays as it
is: `installed_packages_dir`, `user_python_site_dir`, `user_python_import_roots`,
`package_import_roots`, `installed_package_import_roots`,
`desktop_plugin_import_roots`, `candidate_package_dirs`,
`iter_source_package_module_candidates`. NEW-001 appends the user import path
after these roots and never reorders them.

### CHANGE-003 src/scistudio/core/entry_points.py

`prepared_plugin_import_roots` currently opens a `prepended_sys_paths` window
around every entry-point scan. With CHANGE-002 the window is gone: plugin roots
are installed once, for the life of the process, alongside the user import
path, and this function becomes a plain accessor or disappears into its five
callers. `plugin_import_roots` and the diagnostic helpers are unchanged.

### CHANGE-004 src/scistudio/core/types/registry.py

The filesystem scan is replaced by a read of the discovery result.

`_scan_filesystem_dirs` is removed entirely, with it `DROPIN_MODULE_PREFIX`,
the generated `_scistudio_type_dropin_<stem>_<mtime>_<hash>` name, the
`spec_from_file_location` call, the `sys.modules` insertion and the
`BaseException` that today only reaches a log line. `TypeSpec.module_path` now
holds the file's own module name and `TypeSpec.is_dropin` is derived from the
candidate's origin instead of a name prefix. `load_class` keeps its body and
becomes correct by construction, because `module_path` is importable.
`add_scan_dir` and `_scan_dirs` are removed; `scan_all` takes the discovery
result. `rescan` is removed, its callers move to NEW-009. Type import failures
now produce a failure record (NEW-005) rather than a warning.

### CHANGE-005 src/scistudio/core/types/base.py

`same_registered_type` is removed. Its three callers move to `isinstance`
(CHANGE-011, CHANGE-015). `TypeSignature.matches` keeps its name-chain
comparison, which FR-004 still needs for data crossing a process boundary, but
it stops being a fallback for an in-process identity failure; CHANGE-010
documents which of its uses remain.

### CHANGE-006 src/scistudio/core/types/collection.py

`verify`. `Collection.__init__`'s `isinstance(item, item_type)` homogeneity
check is one of the identity checks that fails today. Under FR-003 it must
pass unchanged. Editing it would mean a user type still has two classes in the
process, so an edit here is a signal to revise the spec, not to proceed.

### CHANGE-007 src/scistudio/core/types/composite.py

`verify`. As CHANGE-006, for `CompositeData.set`'s `isinstance(data,
expected_type)` slot check.

### CHANGE-008 src/scistudio/blocks/registry/__init__.py

`instantiate` loses its entire by-path door: the `guard_dropin_type_roots`
call, the `prepended_sys_paths` window, the `spec_from_file_location` under a
generated name, and the re-stamping of `_scistudio_file_path` and
`_scistudio_runtime_import_roots` on the class. It resolves the class from the
module the discovery step already imported.

`hot_reload` is removed; its two callers move to NEW-009. `DropinFailure` and
`dropin_failures` are replaced by the NEW-005 record and a failure accessor
covering every kind. `BlockSpec` loses `file_path`, `file_mtime` and
`runtime_import_roots`, and `module_path` holds the file's own module name.
`add_scan_dir` and `_scan_dirs` are removed with `scan`, which takes the
discovery result.

### CHANGE-009 src/scistudio/blocks/registry/_scan.py

`_scan_tier1` is removed: the generated `_scistudio_dropin_<stem>_<mtime>`
name, the `exec_module` inside a `sys.path` window, the module that never
enters `sys.modules`, and the `obj._scistudio_file_path` stamp all go. The
registration logic that survives — register only classes whose `__module__` is
the module's own — moves into the reader that consumes the discovery result.

`_reject_shadowing_type_files` and `_record_dropin_failure` are removed;
refusals and failures now arrive with the discovery result. `_register_spec`
stops overwriting unconditionally and applies the FR-006 winner instead, which
is the behavior change that makes a project block beat a library block.
`_scan_source_package_module` loses its `prepended_sys_paths` window and its
hand-rolled `sys.modules` eviction. `_scan_tier2`, `_register_entry_point_blocks`
and `_scan_package_src_dirs` keep their entry-point and package work.

### CHANGE-010 src/scistudio/blocks/registry/_capability.py

`_resolve_class` loses its `spec_from_file_location` branch and becomes an
`importlib.import_module` of `spec.module_path` for every origin.
`_capability_matches_type` keeps `TypeSignature.matches`, which compares
declared type chains rather than class identity and is the right tool for a
capability declaration; this entry records that it is deliberate and not a
leftover fallback.

### CHANGE-011 src/scistudio/blocks/base/ports.py

`port_accepts_type` drops the `same_registered_type` half of its check and
keeps `issubclass`. `validate_connection` drops the `same_registered_type`
fallback loop, which exists only because `transient_dropin_modules`
re-executed `types/*.py`. `ports_from_config_dicts`'s `_resolve_type` keeps
going through `TypeRegistry.load_class`, which is now importable by name.

`port_accepts_signature` is dead in `src/` with a TODO citing #1817; this spec
does not remove it, and #1817 remains its tracker.

### CHANGE-012 src/scistudio/blocks/io/simple_io.py

`verify`. `SimpleSaver.save`'s `isinstance(item, self.input_type)` is the exact
site of #2480, where "SaveAnnData expected AnnData, got AnnData" is raised. It
is the single clearest piece of evidence that FR-003 holds, and it must pass
unchanged. NEW-016 covers it.

### CHANGE-013 src/scistudio/blocks/io/_unified_dispatch.py

`_activated_package_import_roots` is removed. Its docstring states that it
exists because `prepended_sys_paths` reverts what discovery installed; with
CHANGE-002 there is nothing to re-activate. `runtime_block_registry` and
`runtime_type_registry` build their registries from the discovery result
instead of calling `register_*_scan_dirs` and scanning.

### CHANGE-014 src/scistudio/blocks/io/savers/_capability.py

`verify`. `_supported_save_extensions` and `_save_capability_for_id` compare
`capability.data_type` against the requested type with `is`. Under FR-003 an
identity comparison is correct, because a type has one class per process. If a
user type reaches these and fails, FR-003 did not hold.

### CHANGE-015 src/scistudio/blocks/io/savers/_helpers.py

`_matches_target_type` drops its `same_registered_type` half and keeps
`isinstance`. `_unwrap_for_save` follows it unchanged.

### CHANGE-016 src/scistudio/engine/runners/worker.py

`_prepend_runtime_import_roots` is removed, along with the
`guard_dropin_type_roots` call inside it. `main` reads the user import path
from the environment (NEW-001) instead of from the payload, and imports its
block with `import_module(module_path)` for every origin; the
`block_file_path` branch with its `spec_from_file_location` and its insertion
into `sys.modules` under the parent's generated name is removed.
`reconstruct_inputs` is unchanged: FR-004 keeps the type-name chain.

### CHANGE-017 src/scistudio/engine/runners/local.py

`_runtime_import_roots_for_block` is removed, with the
`_scistudio_runtime_import_roots` read it performs. `_spawn_worker` stops
reading `_scistudio_file_path` and stops passing either value to
`build_worker_payload`. `_worker_env` gains the user import path variable
(NEW-001) and keeps stripping desktop plugin roots from the child
`PYTHONPATH`.

### CHANGE-018 src/scistudio/engine/runners/process_handle.py

`build_worker_payload` loses the `block_file_path` and `runtime_import_roots`
parameters and the two wire keys they write. `spawn_block_process` loses the
same two parameters from its signature and its inline payload.

### CHANGE-019 src/scistudio/panels/bootstrap.py

`_import_panel` stops inserting `SCISTUDIO_PANEL_DIR` at the front of
`sys.path` and stops executing `panel.py` by path under a hand-set
`sys.modules["panel"]`. The panel folder is the first entry of the user import
path (FR-001), and the module is imported with `import_module("panel")`.
`main` reads the user import path from the environment instead of calling
`worker._prepend_runtime_import_roots` with `SCISTUDIO_PANEL_IMPORT_ROOTS`.

### CHANGE-020 src/scistudio/panels/process.py

`runtime_import_roots` is removed; the panel process receives the full user
import path, which unlike today includes the block directories.
`_process_env` writes the NEW-001 environment variable in place of
`SCISTUDIO_PANEL_IMPORT_ROOTS`. `PanelProcess` records the user modules its
child imported, so CHANGE-022 can decide whether to restart it.

### CHANGE-021 src/scistudio/panels/registry.py

`discover_panels` is replaced by a read of the discovery result; its throwaway
`TypeRegistry` and full `scan_all` go with it. `PanelRegistry.register` stops
implementing its own `TIER_ORDER` comparison and applies the FR-006 winner,
recording the loser through NEW-007 rather than into a free-text diagnostic.
`panel_sources_fingerprint` is replaced by the FR-011 change detection.
`diff_panels` and `RegistryDiff` are replaced by the FR-015 event, which
carries the same added/removed/changed information for every kind.

### CHANGE-022 src/scistudio/panels/service.py

`refresh` and `rescan` stop being independent reload paths and become
consumers of the NEW-009 result. The service keeps the per-panel module set
recorded by CHANGE-020 and restarts a resident panel process when the reset
forgot a module in that set (FR-013); a panel whose modules were untouched
keeps running. `ensure_fresh` uses the FR-011 comparison instead of the panel
fingerprint.

### CHANGE-023 src/scistudio/panels/watcher.py

`PanelSourceWatcher` stops calling `PanelService.rescan` and calls the NEW-009
entry point, which rebuilds every kind rather than panels alone. Its watched
roots widen from the panel tiers to the user import path. `DEBOUNCE_SECONDS`
and the self-write suppression it shares with `_file_writes` become the
watcher-side behavior FR-010 requires. `PanelFileWatches`, which watches the
pages of an open panel, is unaffected.

### CHANGE-024 src/scistudio/panels/validation.py

`panel_scan_scope` runs a complete `discover_panels` pass inside every block
registry scan. With one discovery step this is redundant; the wrapper is
removed and its diagnostics come from the discovery result.

### CHANGE-025 src/scistudio/plot/_harness.py

Inside `PYTHON_HARNESS`, `_load_render` stops using `spec_from_file_location`
and imports the render script by its module name, with the plot folder as the
first entry of the user import path. The harness reads that path from its
environment before importing. This is what makes a render script able to
import a helper beside it and a project type.

### CHANGE-026 src/scistudio/plot/runtime.py

The plot process spawn passes the user import path in the child environment,
as CHANGE-017 does for the worker.

### CHANGE-027 src/scistudio/tutorials/discovery.py

`discover_tutorials` and `_sources` read their candidates from the discovery
step. `_reject_duplicate_ids`, which today makes every member of a duplicated
id unavailable and picks no winner, is replaced by the FR-006 rule, and
identity becomes the tutorial id per FR-016 rather than the
`(source_kind, source_id, tutorial_id)` triple. This is a behavior change: a
tutorial id present in both core and a project is today two separately
addressable entries and becomes one, with the other shadowed. Per-tutorial
failures use the NEW-005 record instead of the free-text `unavailable_reason`
where the cause is a load failure; an unmet requirement stays a requirement
message.

### CHANGE-028 src/scistudio/api/runtime/_projects.py

`refresh_block_registry`, `refresh_type_registry` and `refresh_all_registries`
collapse into one call to NEW-009. `open_project` passes the new project so
the reset replaces the user import path. The runtime holds the last discovery
result and emits the FR-015 event.

### CHANGE-029 src/scistudio/api/runtime/_file_writes.py

`refresh_registries_and_broadcast` calls NEW-009 and emits the FR-015 event in
place of the hand-built `{added, removed, reloaded, path}` payload.
`maybe_reload_blocks_after_save`, `delete_project_path` and `move_project_path`
keep their lint gate but stop deciding for themselves which registries to
rebuild. The current asymmetry — save is lint-gated, delete is not, move is
gated only for moved-in files — is made uniform: the reset runs for any change
under the user import path, and the lint gate only decides whether to report a
lint failure alongside it.

### CHANGE-030 src/scistudio/api/schemas.py

`DropinFailureResponse` is replaced by the NEW-005 wire shape, with the origin
vocabulary of FR-017 and the kind of FR-016 added to its three existing
fields. `BlockListResponse`, `TypeListResponse`, `BlockReloadResponse`,
`TypeReloadResponse` and the panel catalog response all carry that record and
the shadowed list. `PreviewerListResponse` and `PreviewerReloadResponse` are
gone with the legacy previewers (Section 7).

### CHANGE-031 src/scistudio/api/routes/blocks.py

`POST /api/blocks/reload` calls NEW-009 and returns the failure record and the
shadowed list with its diff. `GET /api/blocks/` returns the same record. The
hand-assembled `asdict` of `DropinFailure` is replaced by the NEW-005
conversion.

### CHANGE-032 src/scistudio/api/routes/types.py

`POST /api/types/reload` calls NEW-009. `GET /api/types/` gains the failure
record and the shadowed list, which it has never carried.

### CHANGE-033 src/scistudio/api/routes/panels.py

`_refresh_panels` and the catalog, miniapp and context routes call NEW-009
instead of `PanelService.rescan`, so creating a MiniApp no longer refreshes
panels alone.

### CHANGE-034 src/scistudio/api/routes/git.py

`_refresh_registries_after_worktree_write` and `_apply_worktree_op` call
NEW-009. A branch switch or restore passes the project so the reset treats the
previous tree's modules as the previous user import path.

### CHANGE-035 src/scistudio/api/routes/user_library.py

`_refresh_registries` calls NEW-009. The library write path gains the same
lint gate the project write path has, so the two tiers behave alike.

### CHANGE-036 src/scistudio/api/routes/packages.py

`_after_package_change` calls NEW-009 after an install, update, rollback or
removal, so a package change re-runs the name check (FR-008) against the new
set of installed modules.

### CHANGE-037 src/scistudio/api/routes/tutorials.py

The tutorial step wiring calls NEW-009 when a step writes into a directory of
the user import path, in place of `refresh_all_registries`.

### CHANGE-038 src/scistudio/api/ws.py

The `blocks.reloaded` event is replaced by the FR-015 event. The name is kept
or replaced per Section 8; the payload becomes the discovery comparison for
every kind rather than block-shaped fields.

### CHANGE-039 src/scistudio/ai/agent/mcp/runtime.py

`sync_dropins` calls NEW-009, whose FR-011 comparison replaces
`dropin_revision`. `dropin_scan_dirs`, which today covers only block and type
directories, is replaced by the user import path, so the bridge sees panel and
tutorial changes too. The read-through `block_registry` and `type_registry`
properties keep their shape.

### CHANGE-040 src/scistudio/ai/agent/mcp/tools_authoring.py

The `reload_blocks` tool returns the failure record and the shadowed list with
its diff, so an agent sees what an HTTP caller sees.

### CHANGE-041 src/scistudio/ai/agent/mcp/tools_workflow/_models.py

`ListBlocksResult` and `ReloadBlocksResult` carry the failure record.

### CHANGE-042 tests/blocks/test_dropin_type_import.py

The tests that assert a generated module name, a `sys.path` window or a
by-path execution are rewritten against `import_module` and a single class per
type. The scenarios they cover are kept.

### CHANGE-043 tests/api/test_registry_reload_symmetry.py

Rewritten around one reset entry point: every trigger produces the same
rebuild, and the reload diff is derived from the discovery comparison.

### CHANGE-044 tests/api/test_blocks.py

The `dropin_failures` assertions move to the NEW-005 record, and the listing
gains assertions for the shadowed list.

### CHANGE-045 tests/ai/test_mcp_tools_library.py

The bridge's reload assertions move from `dropin_revision` and `hot_reload` to
the reset entry point.

### CHANGE-046 tests/ai/test_mcp_execution_tools.py

The user-site assertions move from `runtime_import_roots` to the user import
path variable of NEW-001.

### CHANGE-047 tests/api/test_block_origin_tiers.py

The ADR-053 tier-split assertions keep their subject and move to the FR-017
origin vocabulary. The test that asserts today's block winner is rewritten:
under FR-006 the project block beats the library block, where today the library
block wins by scanning last.

### CHANGE-048 tests/blocks/test_desktop_package_discovery.py

The `prepended_sys_paths` assertions are removed; package roots are installed
once per process.

### CHANGE-049 tests/blocks/test_registry_version_strict.py

The ADR-038 version-resolution subject is unchanged; the fixtures stop building
generated drop-in module names.

### CHANGE-050 tests/blocks/test_tier1_dropin_subprocess.py

The #706 regression is kept and rewritten: the worker imports the block by
module name from the user import path instead of by the recorded file path.

### CHANGE-051 tests/engine/test_local_runner.py

The payload assertions drop `block_file_path` and `runtime_import_roots` and
assert the child environment carries the user import path.

### CHANGE-052 tests/panels/test_miniapp_context.py

The panel process assertions move to the user import path, and gain the FR-013
restart case.

### CHANGE-053 tests/tutorials/test_core_tutorial_what_is_a_type.py

The tutorial exercises a user type end to end; its assertions move to one class
per type.

### CHANGE-054 tests/tutorials/test_scoped_library.py

The tutorial-scoped library is the fourth and fifth entries of the user import
path; the assertions move from `type_scan_dirs` to that list.

### CHANGE-055 src/scistudio/ai/agent/mcp/tools_library.py

`promote_to_user_library` calls `refresh_context_registries`, which DEL-001
removes. It calls NEW-009 instead. This is the module's only change.

## 6. Removed Modules

| ID | FR | Replaced by | Module |
|---|---|---|---|
| DEL-001 | FR-009, FR-015 | NEW-009 | src/scistudio/ai/agent/mcp/_reload.py |

### DEL-001 src/scistudio/ai/agent/mcp/_reload.py

The module exists to give the MCP side its own reload path, because an
`MCPContext` has no refresh method of its own. Its three functions are taken
over entirely: `refresh_context_registries`, which today calls
`BlockRegistry.hot_reload` and `TypeRegistry.rescan` in place and leaves panels
and previewers stale, becomes a call to NEW-009; `_block_type_names`, which
derives the added and removed sets by differencing block type names, becomes
the FR-015 comparison in NEW-008; and `broadcast_blocks_reloaded` becomes the
event emission of CHANGE-028.

`BLOCKS_RELOADED_EVENT_TYPE` moves to NEW-008, which owns the event. Its three
importers — `api/runtime/_file_writes.py`, `api/routes/git.py` and
`api/routes/user_library.py` — import it from there instead; each of those
files is already a changed module for other reasons (CHANGE-029, CHANGE-034,
CHANGE-035).

Its two callers call NEW-009 directly: `ai/agent/mcp/tools_authoring.py`
(CHANGE-040) and `ai/agent/mcp/tools_library.py` (CHANGE-055), whose only
change is that one call.

## 7. Migration

| ID | FR | From | To | Carrier |
|---|---|---|---|---|
| MIG-001 | FR-002 | Generated module names `_scistudio_dropin_<stem>_<mtime>` and `_scistudio_type_dropin_<stem>_<mtime>_<hash>` | The file's own stem as its module name | CHANGE-004 |
| MIG-002 | FR-002 | Five `spec_from_file_location` execution sites: type scan, block scan, block instantiation, capability lookup, worker | One `importlib.import_module` in NEW-003 | NEW-003 |
| MIG-003 | FR-001 | `prepended_sys_paths` windows opened and closed around each import, at eleven call sites | One user import path appended once per process | NEW-001 |
| MIG-004 | FR-012 | `BlockSpec.file_path` / `file_mtime` / `runtime_import_roots`, the `_scistudio_file_path` class stamp, and the `block_file_path` / `runtime_import_roots` worker payload keys | The user import path in the child environment, and a module name the child imports | CHANGE-018 |
| MIG-005 | FR-005 | Five per-kind scanners: `_scan_tier1`, `TypeRegistry._scan_filesystem_dirs`, `discover_panels`, the previewer scan, `discover_tutorials` | One discovery step | NEW-006 |
| MIG-006 | FR-006 | Four precedence rules: last-writer-wins for blocks, first-wins for types, `TIER_ORDER` for panels and previewers, and no cross-tier rule at all for tutorials | One rule, project before library before package before core | NEW-007 |
| MIG-007 | FR-009 | Five reload drivers: `refresh_all_registries`, the save hook, `BlockRegistry.hot_reload`, `TypeRegistry.rescan`, `sync_dropins`, plus the panel watcher's own `PanelService.rescan` | One reset entry point | NEW-009 |
| MIG-008 | FR-014 | `DropinFailure` on the block listing, plus five unrelated free-text diagnostic lists: block entry points, type entry points, panels, previewers, tutorials | One failure record on every listing and every reload result | NEW-005 |
| MIG-009 | FR-008 | The `sys.meta_path` refusing finder with its warrants, probing window and bare-module deletion | A name check that runs before import and returns refusals | NEW-002 |
| MIG-010 | FR-015 | The `blocks.reloaded` event with `{added, removed, reloaded, source}`, and `panel.files_changed` for the panel catalog | One refresh event carrying the discovery comparison for every kind | NEW-008 |
| MIG-011 | FR-002 | Objects pickled under a generated module name by a previous version | Not readable; the failure is reported rather than silently mismatched | NEW-005 |
| MIG-012 | FR-005 | Legacy previewers on the by-path machinery | Removed in 0.3.6 before this work starts, tracked by #2288 | None |

MIG-012 is a precondition, not a step this spec performs. ADR-056 Section 7
leaves the order open; this spec fixes it. The four previewer modules that
carry by-path importing — `previewers/project.py`, `previewers/session.py`,
`previewers/registry.py` and `previewers/__init__.py` — are therefore absent
from Sections 5 and 6: migrating them would be work discarded weeks later. If
0.3.6 has not removed them when this work begins, the spec is revised to add
them as changed modules.

MIG-011 has no forward path by design. A pickle records the module name of the
class it holds, and the old names contained a modification time that no longer
exists. The number of such files is small and they live inside project output
directories, where a re-run recreates them.

## 8. Public API Changes

| ID | FR | Surface | Change | Compatibility |
|---|---|---|---|---|
| API-001 | FR-015 | The `blocks.reloaded` WebSocket event | changed | Payload becomes the discovery comparison for every kind. Every consumer of `{added, removed, reloaded}` is updated with it |
| API-002 | FR-014 | `GET /api/blocks/` field `dropin_failures` | changed | Gains `kind` and `origin`; the three existing fields keep their names |
| API-003 | FR-014, FR-007 | `GET /api/types/` | changed | Gains the failure record and the shadowed list, which it has never carried. Additive |
| API-004 | FR-014, FR-007 | `POST /api/blocks/reload` and `POST /api/types/reload` | changed | Gain the failure record and the shadowed list. The `removed` set becomes correct, where it could previously be empty while blocks disappeared |
| API-005 | FR-014 | `GET /api/panels/catalog` field `diagnostics` | changed | Free-text strings become failure records. Breaking for any consumer parsing the strings |
| API-006 | FR-014 | MCP `ListBlocksResult` and `ReloadBlocksResult` | changed | Gain the failure record. Additive; the tool count is unchanged |
| API-007 | FR-018 | `BlockSpec.file_path`, `BlockSpec.file_mtime`, `BlockSpec.runtime_import_roots` | removed | Breaking for anything reading a block's source path from its spec. `module_path` is the replacement and is now importable |
| API-008 | FR-018 | `scistudio.core.types.base.same_registered_type` | removed | Breaking for a caller comparing two classes by name. `isinstance` is the replacement |
| API-009 | FR-012 | The `SCISTUDIO_PANEL_IMPORT_ROOTS` environment variable | removed | Replaced by the single user import path variable of NEW-001, which every child process reads |
| API-010 | FR-012 | `build_worker_payload` and `spawn_block_process` parameters `block_file_path` and `runtime_import_roots` | removed | Breaking for a direct caller; both are internal to the engine |
| API-011 | FR-002 | A user module's `__module__` and the class paths recorded in a pickle | changed | Becomes the file's own name. Pickles written under a generated name are not read back (MIG-011) |
| API-012 | FR-008 | User file names | changed | A file named after a standard-library module or an installed package is refused for every kind, where today only type files are. Breaking for existing block, panel and plot helper files with such names |

The ADR-052 public surface is unaffected: installed plugin packages are
imported through entry points and keep their contract. API-007, API-008 and
API-010 are Python symbols inside the backend; API-001 to API-006 are wire
surfaces the frontend and the agent read.

## 9. Documentation Changes

| ID | FR | Document | Change |
|---|---|---|---|
| DOC-001 | FR-001, FR-002, FR-008, FR-014 | docs/specs/adr-053-personal-tool-library.md | FR-012, FR-013, FR-015 and FR-016 are rewritten around the user import path, the name check and the failure record. FR-014 is kept and is now one half of the precedence rule of this spec's FR-006 |
| DOC-002 | FR-001, FR-012 | docs/specs/adr-054-panels.md | Records that the panel process and the plot harness import through the user import path, and that a resident panel process restarts when a module it imported changed |
| DOC-003 | FR-002, FR-008, FR-014 | docs/user/user-code.md | New. The user-facing rules: which directories are importable, that one user file may import another by name, which file names are refused and why, and where a failed file is reported |

All three documents are written by the owner. ADR-056 Section 6 and Section 9
assign DOC-001 and DOC-002 explicitly, and DOC-003 is a user-guide document,
which the owner also writes.

DOC-003 has no home today. `docs/user/` holds one debugging note and a
generated API reference; `docs/package-development/` covers installed packages
and says nothing about drop-in file names or cross-file imports. FR-002 and
FR-008 give users a new ability and a new refusal, and neither has a
user-facing page to land on. The path above is a proposal; the owner may place
it elsewhere, and Section 10 follows wherever it lands.

The agent's skills under `src/scistudio/_skills/` describe the same rules and
are owner-edited. They are named here so the change is visible, and are absent
from Section 10 because no path under them is edited by this work.

## 10. Impact Surface

| Path | IDs | Action |
|---|---|---|
| docs/user/user-code.md | DOC-003 | create |
| src/scistudio/core/user_code/__init__.py | NEW-010 | create |
| src/scistudio/core/user_code/discovery.py | NEW-006 | create |
| src/scistudio/core/user_code/events.py | NEW-008 | create |
| src/scistudio/core/user_code/failures.py | NEW-005 | create |
| src/scistudio/core/user_code/identity.py | NEW-004 | create |
| src/scistudio/core/user_code/import_path.py | NEW-001 | create |
| src/scistudio/core/user_code/loader.py | NEW-003 | create |
| src/scistudio/core/user_code/names.py | NEW-002 | create |
| src/scistudio/core/user_code/precedence.py | NEW-007 | create |
| src/scistudio/core/user_code/reset.py | NEW-009 | create |
| tests/core/user_code/__init__.py | NEW-017 | create |
| tests/core/user_code/test_discovery_precedence.py | NEW-013 | create |
| tests/core/user_code/test_failures_and_events.py | NEW-015 | create |
| tests/core/user_code/test_import_path.py | NEW-011 | create |
| tests/core/user_code/test_names.py | NEW-012 | create |
| tests/core/user_code/test_reset.py | NEW-014 | create |
| tests/integration/test_user_code_identity.py | NEW-016 | create |
| docs/specs/adr-053-personal-tool-library.md | DOC-001 | modify |
| docs/specs/adr-054-panels.md | DOC-002 | modify |
| src/scistudio/ai/agent/mcp/runtime.py | CHANGE-039 | modify |
| src/scistudio/ai/agent/mcp/tools_authoring.py | CHANGE-040 | modify |
| src/scistudio/ai/agent/mcp/tools_library.py | CHANGE-055 | modify |
| src/scistudio/ai/agent/mcp/tools_workflow/_models.py | CHANGE-041 | modify |
| src/scistudio/api/routes/blocks.py | CHANGE-031 | modify |
| src/scistudio/api/routes/git.py | CHANGE-034 | modify |
| src/scistudio/api/routes/packages.py | CHANGE-036 | modify |
| src/scistudio/api/routes/panels.py | CHANGE-033 | modify |
| src/scistudio/api/routes/tutorials.py | CHANGE-037 | modify |
| src/scistudio/api/routes/types.py | CHANGE-032 | modify |
| src/scistudio/api/routes/user_library.py | CHANGE-035 | modify |
| src/scistudio/api/runtime/_file_writes.py | CHANGE-029 | modify |
| src/scistudio/api/runtime/_projects.py | CHANGE-028 | modify |
| src/scistudio/api/schemas.py | CHANGE-030 | modify |
| src/scistudio/api/ws.py | CHANGE-038 | modify |
| src/scistudio/blocks/base/ports.py | CHANGE-011 | modify |
| src/scistudio/blocks/io/_unified_dispatch.py | CHANGE-013 | modify |
| src/scistudio/blocks/io/savers/_helpers.py | CHANGE-015 | modify |
| src/scistudio/blocks/registry/__init__.py | CHANGE-008 | modify |
| src/scistudio/blocks/registry/_capability.py | CHANGE-010 | modify |
| src/scistudio/blocks/registry/_scan.py | CHANGE-009 | modify |
| src/scistudio/core/dropins.py | CHANGE-001 | modify |
| src/scistudio/core/entry_points.py | CHANGE-003 | modify |
| src/scistudio/core/types/base.py | CHANGE-005 | modify |
| src/scistudio/core/types/registry.py | CHANGE-004 | modify |
| src/scistudio/desktop/paths.py | CHANGE-002 | modify |
| src/scistudio/engine/runners/local.py | CHANGE-017 | modify |
| src/scistudio/engine/runners/process_handle.py | CHANGE-018 | modify |
| src/scistudio/engine/runners/worker.py | CHANGE-016 | modify |
| src/scistudio/panels/bootstrap.py | CHANGE-019 | modify |
| src/scistudio/panels/process.py | CHANGE-020 | modify |
| src/scistudio/panels/registry.py | CHANGE-021 | modify |
| src/scistudio/panels/service.py | CHANGE-022 | modify |
| src/scistudio/panels/validation.py | CHANGE-024 | modify |
| src/scistudio/panels/watcher.py | CHANGE-023 | modify |
| src/scistudio/plot/_harness.py | CHANGE-025 | modify |
| src/scistudio/plot/runtime.py | CHANGE-026 | modify |
| src/scistudio/tutorials/discovery.py | CHANGE-027 | modify |
| tests/ai/test_mcp_execution_tools.py | CHANGE-046 | modify |
| tests/ai/test_mcp_tools_library.py | CHANGE-045 | modify |
| tests/api/test_block_origin_tiers.py | CHANGE-047 | modify |
| tests/api/test_blocks.py | CHANGE-044 | modify |
| tests/api/test_registry_reload_symmetry.py | CHANGE-043 | modify |
| tests/blocks/test_desktop_package_discovery.py | CHANGE-048 | modify |
| tests/blocks/test_dropin_type_import.py | CHANGE-042 | modify |
| tests/blocks/test_registry_version_strict.py | CHANGE-049 | modify |
| tests/blocks/test_tier1_dropin_subprocess.py | CHANGE-050 | modify |
| tests/engine/test_local_runner.py | CHANGE-051 | modify |
| tests/panels/test_miniapp_context.py | CHANGE-052 | modify |
| tests/tutorials/test_core_tutorial_what_is_a_type.py | CHANGE-053 | modify |
| tests/tutorials/test_scoped_library.py | CHANGE-054 | modify |
| src/scistudio/blocks/io/savers/_capability.py | CHANGE-014 | verify |
| src/scistudio/blocks/io/simple_io.py | CHANGE-012 | verify |
| src/scistudio/core/types/collection.py | CHANGE-006 | verify |
| src/scistudio/core/types/composite.py | CHANGE-007 | verify |
| src/scistudio/ai/agent/mcp/_reload.py | DEL-001 | delete |

76 paths: 18 created, 53 modified, 4 verified without edit, 1 deleted.

This table is the union of Sections 4, 5, 6 and 9. The gate ledger's declared
scope for the implementation is set from it, minus the owner-written documents
of Section 9, which land separately.

`docs/specs/adr-056-user-code-import.md` is this document. It is governed by
itself and is absent from the table, because no requirement of Section 3
edits it.
