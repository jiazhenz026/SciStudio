---
spec_id: adr-053-learning-center
title: "ADR-053 Learning Center — A Tutorial Runtime, A Manifest Format, And Progress That Drives One Unlock"
status: Draft
feature_branch: guided/learning-center-scenarios
created: 2026-08-07
input: "Owner-directed live session (guided): design the Learning Center system. The existing single-tutorial implementation is discarded, keeping only its scenario narrative. A tutorial becomes an on-disk directory with a manifest; the backend owns a tutorial runtime with a default manifest driver that packages may override with their own; completion is judged on the backend against product truth using a core-owned vocabulary, re-evaluated from the existing engine event bus rather than by polling; any step may write files into the tutorial project; tutorials are discovered from core, packages, the user directory, and the project, with code-driven tutorials permitted only for core and packages; tutorial projects are hidden from the recent-project surfaces and reachable only through the Learning Center; progress is stored on the backend, grouped by source, and drives exactly one unlock."
owners:
  - "@jiazhenz026"
related_adrs:
  - 34
  - 39
  - 45
  - 49
  - 51
  - 52
  - 53
related_specs:
  - adr-053-personal-tool-library
  - adr-053-work-import
  - frontend-block-palette
scope:
  in:
    - Revising ADR-053 sections 2.1, 2.2, 4.2 and 8 - discarding rather than generalising the current tutorial implementation, admitting reading-only entries, and replacing the percentage unlock threshold with a named-tutorial milestone.
    - Deleting the hardcoded single-tutorial implementation - one backend route and five frontend modules - and replacing it with a general system in the same change.
    - The tutorial package format - a directory holding a `tutorial.yaml` manifest plus an `assets/` tree, and the manifest schema.
    - A backend tutorial runtime with two drivers behind one interface - the core manifest driver, and package-supplied drivers.
    - A core-owned completion-condition vocabulary, evaluated on the backend against product truth.
    - Event-driven re-evaluation over the existing engine event bus, plus an explicit evaluate request for conditions no event covers.
    - Step-scoped actions, including writing files into the tutorial project at any step rather than only at bootstrap.
    - Four discovery sources - core, package (a new `scistudio.tutorials` entry-point group), user, and project - with code-driven tutorials permitted only for core and packages.
    - Tutorial projects - created under a dedicated parent, marked so they never appear in recent-project surfaces, and overwritten when a tutorial is restarted.
    - A tutorial-scoped library directory that tutorial projects scan and real projects do not.
    - Progress stored on the backend, grouped by source, with exactly one milestone unlock driven by the core group.
    - The Learning Center surface - a permanent toolbar entry, the first-run landing, and the unfinished-work dot.
    - The block palette tips strip (#1997), inherited from the personal tool library spec.
  out:
    - The six core tutorial scenarios themselves - their narratives, assets, copy, and step lists. Those are the Learning Center scenarios spec; this spec is the system they run on.
    - Any tutorial content shipped by a package.
    - Frontend assets supplied by a package tutorial. The shape of a tutorial step on screen stays core's.
    - A recording or authoring UI for user-level and project-level tutorials. This spec makes those tiers discoverable and runnable; the manifest is written by hand or by an agent.
    - Sandboxing drop-in execution, deferred by #1531 and unchanged here.
    - A user tier for previewers, excluded by the personal tool library spec and tracked separately. The scenarios spec depends on it; this spec does not.
    - Adding `data/processed/` to the project scaffold, which the owner is handling separately.
    - The work-import dialog, brief, and session, governed by the work-import spec. Only the unlock that routes to its entry point is specified here.
    - Provider configuration and the provider registry, governed by ADR-034.
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-053-learning-center.md
    - docs/adr/ADR-053.md
    - src/scistudio/api/routes/tutorials.py
  excludes:
    - docs/user/reference/**
    - docs/user/llms.txt
planned_governs:
  modules:
    - scistudio.tutorials
  contracts: []
  entry_points:
    - scistudio.tutorials
  files:
    - src/scistudio/tutorials/__init__.py
    - src/scistudio/tutorials/manifest.py
    - src/scistudio/tutorials/discovery.py
    - src/scistudio/tutorials/driver.py
    - src/scistudio/tutorials/conditions.py
    - src/scistudio/tutorials/session.py
    - src/scistudio/tutorials/progress.py
    - frontend/src/components/LearningCenter.tsx
  excludes: []
tests:
  - tests/tutorials/test_manifest_schema.py
  - tests/tutorials/test_discovery_tiers.py
  - tests/tutorials/test_conditions.py
  - tests/tutorials/test_session_lifecycle.py
  - tests/tutorials/test_progress.py
  - tests/api/test_tutorial_routes.py
  - tests/api/test_tutorial_project_visibility.py
  - frontend/src/components/__tests__/LearningCenter.test.tsx
  - frontend/src/components/BlockPalette.parts/__tests__/tipsStrip.test.ts
acceptance_source: adr
language_source: en
---

# ADR-053 Learning Center — A Tutorial Runtime, A Manifest Format, And Progress That Drives One Unlock

## 1. Change Summary

SciStudio has one tutorial. It is not a tutorial in any general sense: it is
eight steps of prose and five JavaScript predicates compiled into the frontend
bundle, plus a single backend route that creates one specific project and writes
one specific CSV file. Nothing about it can be reused for a second tutorial, and
nothing about it can be shipped by a package.

ADR-053 §2.1 originally recorded that this implementation would be generalised.
This spec revises that: it is **discarded and replaced**, keeping only the
scenario narrative. Generalising it would mean carrying its central assumption
forward — that a tutorial is a frontend object which judges itself by reading
the frontend's copy of the workflow. Almost every completion condition the six
designed scenarios need is a backend fact: whether a custom type registered,
whether a git branch exists, whether a run succeeded, whether a file landed in
the project. A frontend judge would need each of those mirrored into the store
before it could see them.

The system that replaces it rests on four moves.

**A tutorial becomes a directory on disk.** A `tutorial.yaml` manifest declares
what the tutorial is and what its steps say; an `assets/` tree holds the data,
the pre-written block and type sources, the interactive panel bundles, the
replay scripts, and the reading pages. The manifest is the only required file.

**Judging moves to the backend and reads product truth.** Completion conditions
are drawn from a vocabulary core owns, evaluated against the registries, the
workflow definition, the run records, git, and the filesystem. Re-evaluation is
driven by the engine event bus the product already pushes to the frontend —
`workflow.changed`, `workflow.completed`, `git.head_changed`, `blocks.reloaded`
and the rest — so no polling loop is introduced. An explicit evaluate request
covers the conditions no event reaches.

**Acting moves to the backend and stops being a bootstrap-only privilege.** Any
step may write files into the tutorial project. The scenarios need this: one
level's story turns on the tutorial itself breaking the workflow so the user
recovers it from History, and another replays a scripted agent whose every claim
must correspond to a real file appearing on disk.

**One runtime, two drivers.** The runtime knows nothing about YAML. It talks to
a driver interface: what does this step say, has it been satisfied, what does
entering it write, is the tutorial over. Core ships the manifest driver; a
package may ship its own class and keep full control of its tutorial's logic.
The manifest is still mandatory for a code-driven tutorial, because listing the
catalogue must not execute a single line of package code — napari's move to the
npe2 manifest and VS Code's decision to declare walkthroughs in `package.json`
were both made for this reason. A package's driver is imported only when the
user opens that tutorial, so a broken tutorial breaks itself and nothing else.

The capability is graded by source. Core and packages may point at a driver.
User-level and project-level tutorials may not — the schema rejects the field —
so a tutorial an agent writes into a project is structurally incapable of
carrying executable code. This deliberately does not repeat the tradeoff made
for drop-in blocks, where `{project}/blocks/*.py` is imported and executed with
sandboxing deferred to #1531: tutorial code would be reached earlier and far
more often, since merely listing the catalogue would touch it.

Three smaller decisions follow from the scenarios rather than from the
architecture. Tutorial projects are hidden from the recent-project surfaces and
reachable only through the Learning Center, so a user cannot wander into one and
mistake a disposable teaching artifact for their own work. Tutorial projects
scan an isolated library directory instead of the user's real one, because one
scenario has the user save a custom type to My Library in order to reuse it in
the next scenario, and that must not deposit a teaching type into every real
project the user opens afterwards. And progress drives exactly one thing: after
the AI scenario, the product offers to bring the user's existing work across.
ADR-053 §4.2's percentage threshold is replaced by that named milestone.

The palette tips strip (#1997) is included here because the personal tool
library spec routed it to this spec and because it belongs to the same problem:
a user cannot go looking for a feature whose existence they have never been
shown.

## 2. User Scenarios & Testing

### User Story 1 - A new user meets SciStudio and finishes the first tutorial (Priority: P1)

A scientist installs SciStudio and opens it. The Learning Center is what they
see. It lists the core tutorials in order with a short summary each, and the
first one is the obvious next click.

They start it. A project is created for them, populated with the data the
tutorial needs, and the first step appears: drag a Load block onto the canvas.
When they do, the step is satisfied and the next one appears without them
clicking anything to confirm it. Some steps write things for them — a block's
source code, a plot — and say so. One step breaks their workflow on purpose and
sends them to History to recover it.

**Why this priority:** This is the product's first impression and the only
scenario every user hits. If the catalogue does not render, or a step never
advances, nothing else in this spec matters.

**Independent test:** Start the first core tutorial from a clean install with no
prior progress. Perform each step's user action. Confirm each step advances on
its own, that the written files appear in the project, and that the tutorial
records as complete when the last step is satisfied.

**Acceptance scenarios:**

1. **Given** a first launch with no recorded progress, **When** the application
   opens, **Then** the Learning Center is shown, listing the core group in
   declared order with each tutorial's title and summary.
2. **Given** the first core tutorial is started, **When** the bootstrap
   completes, **Then** a project exists under the tutorial parent directory,
   populated with the tutorial's data assets, and the first step is displayed.
3. **Given** a step whose condition is that a Load node exists, **When** the user
   drags a Load block onto the canvas, **Then** the step is satisfied without any
   further user action and the next step is displayed.
4. **Given** a step declaring a write action, **When** that step is entered,
   **Then** the declared files exist in the project before the step's text is
   shown to the user.
5. **Given** the final step is satisfied, **When** the tutorial ends, **Then**
   the tutorial is recorded complete in the core group and the Learning Center
   shows the updated count.

### User Story 2 - A user leaves halfway and comes back (Priority: P1)

A user gets three steps into a tutorial, closes the application, and opens it
two days later. The Learning Center shows that tutorial as in progress. Opening
it puts them back on step three in the same project, with everything the
tutorial had already written still there.

Later they decide to start that tutorial over. The product tells them plainly
that restarting deletes the previous tutorial project, names the directory, and
starts fresh only after they confirm.

**Why this priority:** A tutorial that cannot survive a restart is a tutorial
users abandon. This is also the requirement that forces session state onto the
backend, so it constrains the architecture rather than decorating it.

**Independent test:** Advance a tutorial partway, restart the backend, reopen
the Learning Center, and confirm the session resumes on the same step in the
same project. Then restart the tutorial and confirm the confirmation names the
directory and that the old project is gone afterwards.

**Acceptance scenarios:**

1. **Given** a session paused on step three, **When** the backend restarts,
   **Then** reopening the tutorial resumes at step three in the same project.
2. **Given** a tutorial with a saved session, **When** the user chooses to
   restart it, **Then** a confirmation names the project directory that will be
   deleted and no deletion occurs unless it is accepted.
3. **Given** the restart is confirmed, **When** the tutorial starts, **Then** the
   previous tutorial project directory no longer exists and a new one is created
   at the same location.

### User Story 3 - A package ships tutorials for its own blocks (Priority: P1)

A package author writes two tutorials teaching their package's blocks. They add
a directory to their package, declare it under the `scistudio.tutorials` entry
point, and publish. A user who installs the package sees a new group in the
Learning Center with those two tutorials and its own count.

The author writes both as manifests. Their conditions — a node of their block
type exists, a run succeeded, a config value changed — are all in the core
vocabulary.

**Why this priority:** ADR-053 argues the Learning Center is a general hub, not
a container for six core tutorials. If a package cannot contribute, this spec
delivered a hardcoded system with extra steps.

**Independent test:** Install a fixture package declaring the entry point.
Confirm its tutorials appear as their own group with their own count, that
starting one works, and that uninstalling the package removes the group and its
progress.

**Acceptance scenarios:**

1. **Given** a package declaring `scistudio.tutorials`, **When** the catalogue is
   listed, **Then** its tutorials appear in a group named for the package with a
   count independent of the core group.
2. **Given** two installed packages both shipping a tutorial with id `intro`,
   **When** the catalogue is listed, **Then** both appear and are addressable,
   because identity is the pair of package and tutorial id.
3. **Given** a package with recorded tutorial progress, **When** it is
   uninstalled, **Then** its group and its progress are removed; **and When** it
   is reinstalled, **Then** progress starts from zero.
4. **Given** a package tutorial group at two of three complete, **When** progress
   is displayed, **Then** it does not contribute to any unlock or to the toolbar
   dot.

### User Story 4 - A package needs something the vocabulary cannot express (Priority: P2)

A package author's tutorial teaches a calibration workflow. Whether the
calibration succeeded is a fact only their code can determine — it is inside
their data type, not in any registry, workflow, or file core knows how to read.

They declare a driver in their manifest pointing at a class in their package.
The manifest still carries the id, title, summary, cover, and requirements, so
the Learning Center lists the tutorial without importing anything. When a user
opens it, the class is imported and drives the tutorial. If the import fails,
that one tutorial reports an error and the rest of the Learning Center is
unaffected.

**Why this priority:** Not needed for launch, but the vocabulary will have a
ceiling and a blocked package author has no recourse without this. It is also
the reason the manifest is mandatory even for code-driven tutorials.

**Independent test:** Install a fixture package whose tutorial declares a driver.
Confirm the catalogue lists it without importing the module — asserted by an
import hook that fails the test if the module loads during listing — and that
opening it imports and runs it. Then install a fixture whose driver raises on
import and confirm only that entry reports an error.

**Acceptance scenarios:**

1. **Given** a package tutorial declaring a driver, **When** the catalogue is
   listed, **Then** the driver module is not imported.
2. **Given** the same tutorial, **When** the user opens it, **Then** the driver
   is imported and its steps drive the session.
3. **Given** a package tutorial whose driver raises on import, **When** the user
   opens it, **Then** that tutorial reports a load failure and every other
   tutorial remains startable.
4. **Given** a user-level or project-level tutorial manifest declaring a driver,
   **When** it is discovered, **Then** it is rejected with a message naming the
   field and the tier restriction.

### User Story 5 - Finishing the AI tutorial offers to bring the user's work across (Priority: P2)

A user completes the AI scenario. The product offers to carry their existing
analysis into SciStudio. They can take it now or skip; if they skip, they are
told the entry stays permanently in the toolbar under "Bring in my work".

**Why this priority:** This is the only product behaviour progress drives, and
ADR-053 §4.2 currently specifies it as a percentage threshold, which this spec
replaces.

**Independent test:** Complete the tutorial named as the milestone and confirm
the offer appears exactly once. Skip it, confirm the guidance names the toolbar
entry, and confirm the toolbar entry works regardless of progress.

**Acceptance scenarios:**

1. **Given** the milestone tutorial is completed for the first time, **When** it
   ends, **Then** the import offer is presented.
2. **Given** the offer is skipped, **When** it closes, **Then** the user is told
   the toolbar entry is permanently available, and the offer does not reappear.
3. **Given** a user who has completed no tutorials, **When** they open the
   toolbar, **Then** "Bring in my work" is present and usable.

### User Story 6 - A user clears tutorials off their machine (Priority: P2)

A user has finished the tutorials and wants the disk space and the clutter back.
The Learning Center offers to clear tutorial progress. The confirmation states
what will be deleted and names the directories, because "clear progress" and
"delete these folders" are not the same thing in a user's head.

**Why this priority:** ADR-053 §8 records tutorial project cleanup as
undesigned. Without it, running six tutorials leaves six projects the user has
no product surface to remove — and, because tutorial projects are hidden from
the recent-project list, no product surface to even see.

**Independent test:** Complete two tutorials, clear tutorial data, and confirm
progress is empty, the tutorial project directories are gone, the isolated
library is gone, and no non-tutorial project was touched.

**Acceptance scenarios:**

1. **Given** completed tutorials with projects on disk, **When** clearing is
   requested, **Then** a confirmation lists the directories to be deleted.
2. **Given** the confirmation is accepted, **When** clearing completes, **Then**
   progress is empty, the tutorial projects are deleted, and the isolated
   tutorial library is deleted.
3. **Given** a user project stored elsewhere, **When** clearing completes,
   **Then** it is untouched and still listed in recent projects.

### User Story 7 - A user does not stumble into a tutorial project (Priority: P2)

A user finishes a tutorial and goes back to their own work. Tutorial projects do
not appear in the recent-project list, the projects dropdown, or the welcome
pane. The only way back into one is through the Learning Center. The Learning
Center says plainly that tutorial projects are temporary and not a place to do
real work.

**Why this priority:** A tutorial project is a disposable teaching artifact that
gets deleted on restart and on clearing. A user who starts real analysis inside
one will lose it.

**Independent test:** Start a tutorial, then inspect every project-listing
surface and confirm the tutorial project is absent while remaining fully
operable through the Learning Center.

**Acceptance scenarios:**

1. **Given** a tutorial project exists, **When** the projects list, dropdown, or
   welcome pane renders, **Then** it is absent from all three.
2. **Given** a tutorial project, **When** it is opened through the Learning
   Center, **Then** every project operation behaves as for any project.
3. **Given** the Learning Center is displayed, **When** the user reads it,
   **Then** it states that tutorial projects are temporary and that their own
   work belongs in their own project.

### Edge Cases

- **A manifest fails schema validation.** That tutorial is listed as unavailable
  with the validation message; every other tutorial in the same source remains
  listed and startable. One malformed file must never empty a group.
- **Two tutorials share an id within one source.** Rejected at discovery with
  both paths named. Across sources it is legal — identity is (source, id).
- **A package is uninstalled while its tutorial is running.** The session ends
  and reports why. The tutorial project is left on disk; it is removed by
  clearing like any other.
- **A required package is not installed.** The tutorial is listed but not
  startable, and says which package it needs. Listing must not depend on
  requirements being met, or a user could not discover what a package offers
  before installing it.
- **A step's condition is already true on entry.** It is satisfied immediately.
  Conditions are statements about state, not about the user having just acted;
  a user who dragged the Load block early must not be stuck telling the product
  to do something already done.
- **A step's write action targets a file the user has edited.** The tutorial
  overwrites it. Tutorial projects are disposable and the scenarios depend on
  the tutorial controlling their contents; the step text says when it writes.
- **The user deletes the tutorial project outside the product.** The session is
  invalidated on the next interaction and the tutorial is offered from the start.
- **Git is unavailable.** Tutorials whose conditions include git state are
  listed but not startable, matching the degraded mode ADR-039 §3.4 already
  defines for runs.
- **A condition is satisfied while the Learning Center is closed.** State lives
  on the backend; reopening shows the current step. No event is lost because the
  frontend was not looking.
- **The frontend disconnects mid-session.** Evaluation continues on the backend.
  On reconnect the frontend fetches the session and renders the current step.
- **A driver raises during a session.** The session ends with an error naming
  the tutorial and the exception. Progress is not marked complete.
- **A user starts a second tutorial while one is active.** The product states
  that one tutorial runs at a time and offers to leave the current one. Leaving
  keeps the session for later.

## 3. Requirements

### Functional Requirements

#### Removing the current implementation

**FR-001.** The hardcoded single-tutorial implementation MUST be removed in the
same change that introduces the general system. This is
`src/scistudio/api/routes/tutorials.py` in its current form, and the frontend
modules `src/tutorials/runFirstWorkflow/`, `src/components/TutorialPanel.tsx`,
`src/store/tutorialSlice.ts`, `src/App.parts/useRunFirstWorkflowTutorial.ts`, and
`src/lib/api/tutorials.ts`.

**FR-002.** The five frontend judging predicates in
`src/tutorials/runFirstWorkflow/content.ts` MUST NOT be preserved in any form.
They judge by reading the frontend's copy of the workflow, which is the
assumption this spec replaces; keeping them would give two judging paths that
disagree.

**FR-003.** The route `POST /api/tutorials/run-first-workflow/bootstrap` MUST be
removed rather than kept as an alias. It is not part of any published API
surface and has no consumer outside the deleted frontend modules.

**FR-004.** Removal MUST NOT be staged across releases. The current tutorial has
never shipped in a release users receive updates for, so no compatibility window
is owed and running two judging paths concurrently would create drift with no
beneficiary.

#### The tutorial package format

**FR-005.** A tutorial MUST be a directory containing a manifest file named
`tutorial.yaml`. The manifest MUST be the only file required for the tutorial to
be listed.

**FR-006.** Assets MUST live under an `assets/` subdirectory of the tutorial
directory. The reserved subdirectories are `data/` for data files, `code/` for
block, type, previewer, and plot sources written into the project, `panels/` for
built interactive-block panel bundles, `replay/` for scripted replay material,
and `pages/` for reading content.

**FR-007.** The manifest MUST declare `id`, `title`, and `summary`. It MAY
declare `cover` naming an image file in the tutorial directory, and `order` as an
integer controlling position within its group.

**FR-008.** The manifest MAY declare a `requires` block with `scistudio` as a
version specifier, `agent` as a boolean, and `packages` as a list of
distribution names. A tutorial whose requirements are unmet MUST still be listed
(FR-024).

**FR-009.** The manifest MAY declare a `bootstrap` block. Presence of
`bootstrap` is what determines whether the tutorial gets a project: a tutorial
declaring it receives a freshly created tutorial project, and a tutorial omitting
it runs without one. No separate tutorial-kind field is introduced, because the
step actions already declare what each step does and a second classification
would be able to contradict them.

**FR-010.** The manifest MUST declare exactly one of `steps` or `driver`. A
manifest declaring both, or neither, MUST be rejected with a message naming the
conflict.

**FR-011.** A step MUST declare an `id` unique within the tutorial. It MAY
declare `say` as display text, `highlight` naming a user-interface element,
`route_to` naming a tab or panel the user is taken to, `do` as an ordered list of
actions, and `done_when` as a completion condition.

**FR-012.** A step omitting `done_when` MUST advance on an explicit user action
to continue. Reading steps are the common case; requiring a synthetic condition
for them would be ceremony.

**FR-013.** The manifest MUST be validated against a published schema at
discovery. Validation failures MUST name the file, the field, and the reason.

**FR-014.** Asset paths in the manifest MUST resolve inside the tutorial
directory. A path escaping it MUST be rejected at validation, not at execution,
so a bad tutorial fails while being listed rather than while writing files into
a user's project.

**FR-015.** Destination paths for write actions MUST resolve inside the tutorial
project. The same rejection applies, on the same grounds.

#### Discovery and tiers

**FR-016.** Tutorials MUST be discovered from four sources: core, at a directory
inside the distribution; packages, via entry points; the user directory
`~/.scistudio/tutorials/`; and the open project's `tutorials/` directory.

**FR-017.** Package tutorials MUST be declared through a new entry-point group
`scistudio.tutorials`. This is the fourth live group, alongside
`scistudio.blocks`, `scistudio.types`, and `scistudio.previewers`;
`scistudio.runners` was removed by ADR-052 §7A and is not a precedent.

**FR-018.** Listing the catalogue MUST NOT import any package module. Titles,
summaries, covers, order, and requirements MUST be read from manifests alone.

**FR-019.** A tutorial's identity MUST be the pair of its source and its id. Two
packages MAY ship tutorials with the same id.

**FR-020.** The `driver` field MUST be accepted only for core and package
tutorials. A user-level or project-level manifest declaring it MUST be rejected
at validation with a message naming the field and the restriction.

**FR-021.** A package driver MUST be imported only when a user starts that
tutorial. An import failure MUST be contained to that tutorial.

**FR-022.** A malformed or rejected manifest MUST NOT prevent any other tutorial
from being listed, including others from the same source.

**FR-023.** Duplicate ids within one source MUST be rejected at discovery with
both paths named.

**FR-024.** A tutorial whose `requires` are unmet MUST be listed, marked
unavailable, and state which requirement is unmet. Discoverability is the point
of the catalogue; a user cannot decide whether to install a package whose
teaching material is invisible until after installing it.

#### The runtime and drivers

**FR-025.** The backend MUST own a tutorial runtime holding the active session:
which tutorial, which project, which step, and which steps are satisfied.

**FR-026.** Session state MUST survive a backend restart.

**FR-027.** The runtime MUST interact with tutorials only through a driver
interface. The interface MUST cover: the view of the current step, whether the
current step is satisfied given current product state, the actions to perform on
entering a step, and whether the tutorial has ended.

**FR-028.** Core MUST provide a manifest driver implementing that interface by
reading `tutorial.yaml`. It MUST be the driver for every core tutorial, every
user-level tutorial, and every project-level tutorial.

**FR-029.** A package driver MUST implement the same interface. The runtime and
every API response MUST be identical for both drivers; no response field may
reveal which driver produced it.

**FR-030.** The step view a driver returns MUST be limited to the fields FR-011
defines. A driver MUST NOT be able to introduce new rendering primitives, supply
frontend assets, or address any surface the manifest format cannot address. Core
owns what a tutorial step looks like.

**FR-031.** A package driver MUST be able to call the core condition evaluator so
it can use the vocabulary for the conditions it covers and implement only the
ones it does not.

**FR-032.** Exactly one tutorial session MUST be active at a time. Starting a
second MUST require leaving the first, and leaving MUST preserve the first
session for resumption.

**FR-033.** An exception raised by a driver MUST end the session with an error
naming the tutorial and the exception, MUST NOT mark the tutorial complete, and
MUST NOT prevent other tutorials from starting.

#### Completion conditions

**FR-034.** The completion-condition vocabulary MUST be defined and owned by
core. Tutorials reference terms; they do not define them.

**FR-035.** Conditions MUST be evaluated on the backend against product state.
No condition may be evaluated from frontend state, except `ui_event` (FR-041).

**FR-036.** The vocabulary MUST include at least:

| Term | Judges |
|---|---|
| `node_exists` | a node of a given block type is present in the workflow |
| `edge_exists` | an edge connects two given block types or node ids |
| `config_equals` | a node's configuration key holds a given value |
| `run_succeeded` | a run of the workflow, or of a given node, completed successfully |
| `port_has_output` | a given output port holds data |
| `block_registered` | a block type is present in the registry |
| `type_registered` | a data type is present in the type registry |
| `previewer_registered` | a previewer is registered for a given type |
| `plot_exists` | a plot exists, optionally bound to a given block's output |
| `file_exists` | a project-relative path exists |
| `git_branch_exists` | a branch exists in the project repository |
| `git_current_branch` | the checked-out branch is a given name |
| `library_contains` | the tutorial-scoped library holds a named block, type, or previewer |
| `interaction_completed` | an interactive block's panel was submitted |
| `page_reached` | a reading step reached a given page |
| `ui_event` | a named frontend event was reported |

**FR-037.** The vocabulary MUST support `all` and `any` combinators taking lists
of conditions. Negation is deliberately omitted: a tutorial step that advances
when something is *absent* advances by the user doing nothing, which teaches
nothing and is indistinguishable from a stuck step.

**FR-038.** An unknown term MUST be rejected at manifest validation, not at
evaluation. A tutorial that fails on step nine because of a typo is a tutorial
that failed for the user, not for its author.

**FR-039.** The active step's condition MUST be re-evaluated when any engine
event in a declared mapping is observed. The mapping MUST at minimum be:

| Event | Terms re-evaluated |
|---|---|
| `workflow.changed` | `node_exists`, `edge_exists`, `config_equals` |
| `workflow.completed`, `block.done`, `block.error` | `run_succeeded`, `port_has_output` |
| `blocks.reloaded` | `block_registered`, `type_registered`, `previewer_registered`, `library_contains` |
| `git.head_changed` | `git_branch_exists`, `git_current_branch` |
| `file.changed` | `file_exists` |
| `interactive.complete` | `interaction_completed` |

**FR-040.** The runtime MUST NOT poll for completion. Every re-evaluation MUST be
caused by an event under FR-039, an explicit request under FR-042, or entry into
a step.

**FR-041.** The frontend MUST be able to report a named user-interface event to
the backend, which MUST satisfy a matching `ui_event` condition. This is the only
completion path that originates in the frontend and exists because some product
actions — enlarging the preview panel, opening a tab — produce no backend state.

**FR-042.** The frontend MUST be able to request an explicit re-evaluation of the
active step. This covers state changes that no mapped event reaches: the
`file.changed` event is filtered to the allowlisted extensions in
`ADR036_FILE_ALLOWLIST`, so a `file_exists` condition on a data file such as a
TIFF will not be event-driven, and registry refreshes triggered by paths that do
not emit `blocks.reloaded` are likewise uncovered.

**FR-043.** A condition already satisfied when its step is entered MUST satisfy
that step immediately.

**FR-044.** Condition evaluation MUST be side-effect free. Evaluating a condition
MUST NOT create files, mutate registries, or trigger runs.

#### Step actions

**FR-045.** A step MAY declare actions performed on entry, before its text is
displayed.

**FR-046.** The action set MUST include writing an asset into the tutorial
project, copying an asset directory into the tutorial project, and replaying
scripted material into a designated surface.

**FR-047.** Write actions MUST be available at any step, not only at bootstrap.
Two designed scenarios depend on this: one has the tutorial break the workflow
mid-tutorial so the user recovers it, and one replays a scripted agent whose
every claim must be matched by a real change on disk.

**FR-048.** Actions MUST complete before the step's text is displayed. A step
that says "we have written this block for you" must not be readable before the
block exists.

**FR-049.** An action failure MUST end the session with an error naming the step
and the action, and MUST NOT silently advance.

**FR-050.** Replay actions MUST NOT be able to reach any surface other than the
one the action names. Replay is scripted content playback, not a general remote
control for the product.

#### Tutorial projects

**FR-051.** A tutorial declaring `bootstrap` MUST receive a project created under
a dedicated tutorial parent directory, defaulting to `~/SciStudio Tutorials/`.
This preserves the location the current implementation already uses.

**FR-052.** Tutorial projects MUST be recorded in the known-projects registry.
Several routes resolve a project's real path through that registry, including the
path containment check in `src/scistudio/api/routes/projects.py`, so an
unregistered tutorial project would fail those checks and could not be operated.

**FR-053.** A tutorial project MUST carry a marker distinguishing it from a user
project.

**FR-054.** Marked projects MUST be excluded from the project listing that feeds
the recent-project list, the projects dropdown, and the welcome pane. They MUST
remain fully operable through every other route.

**FR-055.** Restarting a tutorial MUST delete the previous tutorial project for
that tutorial and create a new one at the same location. The serial-suffix naming
the current implementation uses for repeat runs is removed with it.

**FR-056.** Deleting a tutorial project MUST require a confirmation naming the
directory.

**FR-057.** The Learning Center MUST state that tutorial projects are temporary
and that the user's own work belongs in their own project.

**FR-058.** A tutorial project whose directory has been removed outside the
product MUST invalidate its session on the next interaction and be offered from
the start.

#### The tutorial-scoped library

**FR-059.** Tutorial projects MUST scan a tutorial-scoped library directory in
place of the user-wide library, defaulting to a `.library/` directory under the
tutorial parent with `blocks/` and `types/` subdirectories.

**FR-060.** Real projects MUST NOT scan the tutorial-scoped library.

**FR-061.** A tutorial step teaching the save-to-library action MUST state that
performing the same action in the user's own project writes to their real
library. Otherwise the user learns an action whose real consequence they have
never observed.

**FR-062.** Clearing tutorial data MUST delete the tutorial-scoped library along
with the tutorial projects, so no orphaned teaching types survive.

#### Progress and the milestone unlock

**FR-063.** Progress MUST be stored on the backend under `~/.scistudio/`.
Browser-side storage is not acceptable: the backend must be able to read it to
evaluate the unlock and write it when a package is uninstalled, it does not
survive clearing browser data, and the desktop and web surfaces would keep
separate copies.

**FR-064.** A progress record MUST be keyed by source and tutorial id.

**FR-065.** Progress MUST be reported grouped by source, each group carrying its
own completed and total counts. No aggregate across groups is reported.

**FR-066.** A group's total growing because its source shipped new tutorials MUST
NOT be compensated for. A completed group returning to incomplete after an
upgrade is the intended reading: there is new material.

**FR-067.** Uninstalling a package MUST delete that package's progress group.
Reinstalling MUST start it from zero.

**FR-068.** Exactly one product behaviour MUST be driven by progress: completing
a named core tutorial MUST present the work-import offer, once. The named
tutorial MUST be configuration, not a constant.

**FR-069.** Only the core group MUST drive product behaviour. Package group
progress is display only and MUST NOT drive the unlock, the toolbar dot, or any
other behaviour.

**FR-070.** No capability MUST be gated on progress. The work-import toolbar
entry MUST remain permanently available regardless of progress, as work-import
FR-001 requires; the unlock decides when the product *volunteers* it.

#### The Learning Center surface

**FR-071.** The Learning Center MUST be reachable from a permanent toolbar entry.

**FR-072.** On first launch with no recorded progress, the Learning Center MUST
be what the user sees.

**FR-073.** The Learning Center MUST list tutorials grouped by source, each group
labelled with its origin and its own count, with core first.

**FR-074.** Each entry MUST show its title, summary, cover if declared, and
state: not started, in progress, complete, or unavailable with the reason.

**FR-075.** The toolbar entry MUST carry an unfinished-work indicator when the
core group is not fully complete and the user has dismissed the first-run
landing. It MUST clear when the core group is complete, and MUST NOT offer a
permanent dismissal.

**FR-076.** Opening an in-progress tutorial MUST resume its session. Opening a
completed tutorial MUST offer restarting it under FR-055 and FR-056.

**FR-077.** The Learning Center MUST offer clearing tutorial progress. The
confirmation MUST name the directories to be deleted, because the action's label
describes the user's intent while its effect is deleting directories, and the two
must not be allowed to diverge silently.

**FR-078.** The active step MUST be displayed in a surface that does not occlude
the canvas element it refers to, since most steps ask the user to act on the
canvas or the palette.

**FR-079.** Leaving a tutorial MUST be possible at any step and MUST preserve the
session.

#### The palette tips strip

**FR-080.** The block palette MUST display a single-line tips strip positioned
between the category chips and the scrolling section grid, outside the scroll
container, so that neither scrolling nor an active category filter can hide it.

**FR-081.** The strip MUST select a tip at random on mount and MUST offer a
control that advances to another tip. It MUST NOT offer permanent dismissal.

**FR-082.** The strip MUST NOT render in collapsed rail mode, MUST occupy one
truncating line, and its tip pool MUST live in a single module.

**FR-083.** The initial pool MUST prioritise the capabilities users have not been
shown they have: interactive blocks, custom previewers, custom data types, saving
a block to My Library, and splitting a long block into reusable pieces. A tip MAY
link to a Learning Center entry; the strip MUST NOT depend on one existing.

#### ADR-053 revisions

**FR-084.** ADR-053 §2.1 MUST be revised. It records that the existing
single-tutorial implementation is generalised; the decision is now that it is
discarded and replaced, with only the scenario narrative retained.

**FR-085.** ADR-053 §2.2 MUST be revised. It records that completion is granted
only by running and that reading is not progress. A reading-only summary tutorial
is part of the designed set, and it completes by being read. The revision MUST
carry the distinction rather than deleting the principle: the summary tutorial
names and organises capabilities the user has already exercised in earlier
tutorials, so it is review rather than instruction, and the principle continues
to hold for tutorials that teach.

**FR-086.** ADR-053 §4.2 MUST be revised. It sets an initial unlock threshold of
40% of the catalogue, described as configuration rather than a constant. A
percentage over a catalogue that packages can grow does not denote a fixed point
in the user's experience; the trigger becomes completion of a named core
tutorial (FR-068).

**FR-087.** ADR-053 §8 MUST be revised to follow §4.2, and MUST record that
tutorial project cleanup — which it currently lists as undesigned — is specified
here (FR-055, FR-062, FR-077).

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `TutorialManifest` | The parsed `tutorial.yaml`; the only thing read to list the catalogue | `id`, `title`, `summary`, `cover`, `order`, `requires`, `bootstrap`, and exactly one of `steps` or `driver` | Belongs to one source; validated at discovery (FR-013); never triggers a package import (FR-018) |
| `TutorialSource` | Where a tutorial came from | `kind` (`core` \| `package` \| `user` \| `project`), `package_name` for packages | Determines the progress group (FR-065) and whether `driver` is permitted (FR-020) |
| `TutorialStep` | One step of a manifest-driven tutorial | `id`, `say`, `highlight`, `route_to`, `do`, `done_when` | Rendered through the step view (FR-030); actions run on entry (FR-048) |
| `TutorialDriver` | The interface the runtime talks to | step view, satisfied check, entry actions, ended check | Core's manifest driver (FR-028) or a package class (FR-029); may call the core evaluator (FR-031) |
| `CompletionCondition` | A term from the core vocabulary, or an `all`/`any` of them | term, term-specific arguments | Evaluated on the backend against product state (FR-035); side-effect free (FR-044) |
| `TutorialSession` | The single active session | tutorial identity, project path, current step, satisfied steps, status | At most one exists (FR-032); survives backend restart (FR-026) |
| `TutorialProject` | A project created for a tutorial | project fields plus a tutorial marker | Registered in known projects (FR-052), hidden from listing surfaces (FR-054), deleted on restart and on clearing (FR-055, FR-062) |
| `TutorialProgress` | Completion state per tutorial | `(source, tutorial_id)` to completion, grouped for reporting | Backend-stored (FR-063); the core group drives the single unlock (FR-068, FR-069) |

## 4. Implementation Plan

### 4.1 Technical Approach

**Almost none of the general system exists.** What exists is one tutorial's
worth of hardcoded material: a backend route
(`src/scistudio/api/routes/tutorials.py`) that creates one named project under
`~/SciStudio Tutorials` and writes one CSV, and five frontend modules holding
eight steps of prose and five judging predicates. There is no registry, no
manifest format, no session, and no progress beyond a completion timestamp in the
frontend store. FR-001 through FR-004 remove all of it.

**What does exist, and is why this design is affordable, is the event
infrastructure.** `src/scistudio/api/ws.py` already pushes engine events to the
frontend: block lifecycle events, `workflow.started` / `completed` / `changed`,
`git.head_changed`, `interactive.prompt` / `complete`, `file.changed`, and
`blocks.reloaded`. `src/scistudio/api/routes/workflow_watcher.py` runs a watchdog
observer over the active project — recursively over `workflows/` for
`workflow.changed`, recursively over the project root for `file.changed`, and
over `.git/HEAD` and `.git/refs/heads/` for `git.head_changed`. The tutorial
runtime subscribes to the same bus. This is the whole reason FR-040 can forbid
polling.

The one limit worth stating: `file.changed` is filtered to the extensions in
`ADR036_FILE_ALLOWLIST` (`.py .r .txt .md .yaml .yml .json .csv .log`), so a
`file_exists` condition on a data file such as a TIFF or a Zarr store will not be
event-driven. FR-042's explicit evaluate request is what covers that, and it is
why that requirement exists rather than being a convenience.

**A new package `scistudio.tutorials`** holds the manifest model and schema,
discovery across the four sources, the driver interface and the core manifest
driver, the condition vocabulary and evaluator, the session, and progress
storage. It depends on the registries, the workflow model, the run records, and
the git engine — all read-only, consistent with FR-044.

**Discovery** follows the precedents already in the tree: entry-point loading as
in `src/scistudio/blocks/registry/_scan.py`, `src/scistudio/core/types/registry.py`,
and `src/scistudio/previewers/registry.py`, and drop-in directory scanning as the
block and type registries do for `~/.scistudio/` and `{project}/`. The difference
from all three is FR-018: discovery reads files and never imports the package.
The entry point's value is resolved to a directory path without loading the
module it names.

**Hiding tutorial projects** is a marker on the known-projects entry plus a
filter in the listing route (`src/scistudio/api/routes/projects.py`), not a
separate registry. `create_project` writes into `known_projects` unconditionally
and several routes resolve real paths through it, including a path containment
check; a separate registry would break those. FR-052 and FR-054 encode that.

**The tutorial-scoped library** needs no new mechanism. The registries already
accept scan directories, so a tutorial project registers the tutorial library
directory where a real project registers `~/.scistudio/`.

**The frontend** gains a Learning Center component rendering the grouped
catalogue, an active-step surface, the first-run landing, the toolbar entry and
its dot, and the palette tips strip. It holds no judging logic and no step
content: it renders the step view the backend returns, reports user-interface
events (FR-041), and can request an evaluation (FR-042).

### 4.2 Affected Files

**New — backend**

| File | Purpose |
|---|---|
| `src/scistudio/tutorials/__init__.py` | Package surface |
| `src/scistudio/tutorials/manifest.py` | Manifest model, schema, validation (FR-005..FR-015) |
| `src/scistudio/tutorials/discovery.py` | Four-source discovery, entry-point group, tier rules (FR-016..FR-024) |
| `src/scistudio/tutorials/driver.py` | Driver interface and the core manifest driver (FR-027..FR-031) |
| `src/scistudio/tutorials/conditions.py` | Vocabulary, evaluator, event mapping (FR-034..FR-044) |
| `src/scistudio/tutorials/actions.py` | Step actions (FR-045..FR-050) |
| `src/scistudio/tutorials/session.py` | Session lifecycle and persistence (FR-025, FR-026, FR-032, FR-033) |
| `src/scistudio/tutorials/projects.py` | Tutorial project creation, marking, deletion, scoped library (FR-051..FR-062) |
| `src/scistudio/tutorials/progress.py` | Progress storage, grouping, unlock (FR-063..FR-070) |
| `src/scistudio/tutorials/schema/tutorial.schema.json` | Published manifest schema (FR-013) |

**Rewritten — backend**

| File | Change |
|---|---|
| `src/scistudio/api/routes/tutorials.py` | Replaced entirely: catalogue, session lifecycle, evaluate, user-interface event, progress, clear |
| `src/scistudio/api/routes/projects.py` | Filter marked projects from the listing (FR-054) |
| `src/scistudio/api/runtime/_projects.py` | Carry the tutorial marker on creation and in the known-projects entry (FR-052, FR-053) |

**Deleted — frontend**

`src/tutorials/runFirstWorkflow/` (with its tests), `src/components/TutorialPanel.tsx`
(with its test), `src/store/tutorialSlice.ts` (with its test),
`src/App.parts/useRunFirstWorkflowTutorial.ts`, `src/lib/api/tutorials.ts`.

**New — frontend**

| File | Purpose |
|---|---|
| `src/components/LearningCenter.tsx` | Grouped catalogue, states, clear action (FR-071..FR-077) |
| `src/components/LearningCenter.parts/ActiveStep.tsx` | Active step surface (FR-078, FR-079) |
| `src/store/learningCenterSlice.ts` | Session view state only; no judging, no content |
| `src/lib/api/learningCenter.ts` | API client |
| `src/components/BlockPalette.parts/TipsStrip.tsx` | Tips strip (FR-080..FR-082) |
| `src/components/BlockPalette.parts/tips.ts` | Tip pool (FR-083) |

**Modified — frontend**

`src/components/Toolbar.tsx` for the entry and dot; `src/components/BlockPalette.tsx`
for the strip's position; `src/App.tsx` and `src/App.parts/WelcomePane.tsx` for
the first-run landing.

**Docs**

`docs/adr/ADR-053.md` §2.1, §2.2, §4.2, §8 (FR-084..FR-087);
`docs/specs/frontend-block-palette.md` for the new fixed-position region.

### 4.3 Implementation Sequence

1. **Manifest and schema.** Model, schema, validation, tier rules for `driver`.
   Testable with fixture directories and no runtime.
2. **Discovery.** Four sources, the entry-point group, duplicate and requirement
   handling. The no-import guarantee (FR-018) is asserted here.
3. **Conditions.** Vocabulary and evaluator against a constructed project. Pure
   reads, so testable without a session.
4. **Actions.** Write, copy, replay, with the containment rules of FR-015.
5. **Driver and session.** Interface, core manifest driver, session lifecycle,
   persistence, single-session rule, event subscription and the FR-039 mapping.
6. **Tutorial projects.** Creation, marking, listing filter, restart deletion,
   scoped library.
7. **Progress.** Storage, grouping, package uninstall removal, the milestone
   unlock.
8. **API routes.** Replace `routes/tutorials.py`; delete the old route in the
   same commit.
9. **Frontend.** Learning Center, active step, toolbar entry and dot, first-run
   landing; delete the five old modules in the same commit.
10. **Tips strip.** Independent of everything above and shippable at any point
    after step 9's palette work settles.
11. **ADR-053 revisions.**

Steps 1–4 are independently testable without any user interface. Step 8 is the
first point at which the product has no tutorial, and step 9 closes that window;
they should land together. Rebuilding the first core tutorial as manifest content
belongs to the scenarios spec, but a minimal fixture tutorial exercising every
vocabulary term and every action type is part of this spec's test material.

### 4.4 Verification Plan

| Area | Test | Asserts |
|---|---|---|
| Manifest | `tests/tutorials/test_manifest_schema.py` | Required fields; `steps` xor `driver`; asset and destination containment; unknown vocabulary term rejected at validation (FR-038); `driver` rejected for user and project tiers (FR-020) |
| Discovery | `tests/tutorials/test_discovery_tiers.py` | All four sources found; entry-point group read; duplicate ids within a source rejected; a malformed manifest does not empty its group (FR-022); unmet requirements still listed (FR-024) |
| No-import | `tests/tutorials/test_discovery_no_import.py` | Listing a catalogue containing a driver-declaring package tutorial imports no package module, asserted with an import hook that fails the test on load (FR-018) |
| Conditions | `tests/tutorials/test_conditions.py` | Each vocabulary term true and false against a constructed project; `all` / `any`; evaluation leaves no side effects (FR-044) |
| Events | `tests/tutorials/test_condition_events.py` | Each mapped event re-evaluates its terms; no timer or poll exists (FR-040); explicit evaluation satisfies a `file_exists` condition on a non-allowlisted extension (FR-042) |
| Actions | `tests/tutorials/test_actions.py` | Write and copy land before step text is exposed (FR-048); a path escaping the project is rejected; a failed action ends the session (FR-049) |
| Session | `tests/tutorials/test_session_lifecycle.py` | Resume across restart (FR-026); one session at a time (FR-032); a raising driver ends the session without marking completion (FR-033); an already-true condition satisfies on entry (FR-043) |
| Driver parity | `tests/tutorials/test_driver_parity.py` | A fixture package driver and a manifest tutorial produce API responses distinguishable only by content (FR-029); a driver cannot return fields outside the step view (FR-030) |
| Projects | `tests/api/test_tutorial_project_visibility.py` | Marked projects absent from the listing route but operable through others (FR-054); restart deletes and recreates (FR-055); an externally deleted project invalidates its session (FR-058) |
| Library | `tests/tutorials/test_scoped_library.py` | A tutorial project sees the scoped library; a real project does not (FR-060); clearing removes it (FR-062) |
| Progress | `tests/tutorials/test_progress.py` | Grouped counts; a growing total is not compensated (FR-066); package uninstall removes its group (FR-067); only the core group drives the unlock (FR-069) |
| Routes | `tests/api/test_tutorial_routes.py` | Catalogue, start, resume, evaluate, user-interface event, leave, clear; the removed route returns 404 (FR-003) |
| Frontend | `frontend/src/components/__tests__/LearningCenter.test.tsx` | Grouped rendering; entry states; the dot appears and clears per FR-075; the clear confirmation names directories (FR-077) |
| Tips strip | `frontend/src/components/BlockPalette.parts/__tests__/tipsStrip.test.ts` | Non-empty well-formed pool; cycling advances; absent in rail mode (FR-081, FR-082) |

Manual verification before the PR: a full pass of a fixture tutorial exercising
every action type and every vocabulary term, a backend restart mid-tutorial, a
restart-tutorial cycle, a package install and uninstall around a fixture package
tutorial, and a clear-tutorial-data cycle with a real user project present to
confirm it is untouched.

### 4.5 Risks And Rollback

**The vocabulary is too small and core becomes a bottleneck.** The most likely
way this design disappoints. Mitigated three ways: the vocabulary is explicitly
extensible by core; package authors have the driver escape hatch (FR-029); and
FR-031 lets a driver reuse the evaluator so an author needing one extra condition
does not reimplement the other ten. The intended evolution is that a condition
several packages implement identically in their drivers becomes a core term —
the escape hatch doubles as the signal for what to promote, which is the same
progression the product already uses for project-level and user-level blocks.

**Event coverage is incomplete and a step appears stuck.** A condition whose
truth changes without a mapped event leaves the user waiting with no way to
complain. FR-042 is the designed answer, but it depends on the frontend knowing
when to ask. If this proves insufficient in practice, the escalation is a
user-visible "check again" control on the step surface rather than a poll — it
keeps the cost proportional to the failure and keeps the user informed instead of
guessing.

**Deleting the current tutorial before the new one is authored.** Between step 8
and the scenarios spec landing, the product's tutorial is a fixture. FR-004
accepts this on the grounds that the current tutorial has never reached users
through a release channel. If that ceases to be true before this lands, the
sequence must change, not the design.

**Restart deletes work a user did in a tutorial project.** FR-054 keeps tutorial
projects out of every listing surface and FR-057 states plainly what they are, so
reaching one requires the Learning Center. FR-056's confirmation names the
directory. The residual risk is a user who deliberately worked inside a tutorial
project after being told not to.

**A package driver is slow, blocking, or leaks.** It runs in the backend process
like every other package contribution. FR-033 contains exceptions; it does not
contain a driver that blocks. This is the same exposure package blocks already
carry and is not made worse here, but it is worth stating rather than implying
the escape hatch is free.

**Rollback.** Every part except the tips strip is new surface plus one deletion.
Rolling back means restoring the deleted modules and route from history and
removing `scistudio.tutorials`; no data migration is involved, since progress is
a new file and tutorial projects are disposable by construction. The tips strip
is independently revertable.

## 5. Success Criteria

### Measurable Outcomes

**SC-001.** A second tutorial can be added by adding a directory and a manifest,
with no change to backend or frontend code. Demonstrated by the fixture tutorials
in the test material.

**SC-002.** Listing a catalogue containing package tutorials imports zero package
modules, asserted by test rather than by inspection.

**SC-003.** A malformed tutorial in any source leaves every other tutorial
listed and startable.

**SC-004.** A user-level or project-level manifest declaring `driver` is rejected
at validation with a message naming the field and the restriction.

**SC-005.** No polling loop exists in the tutorial runtime; every completion
transition is traceable to a mapped event, an explicit request, or step entry.

**SC-006.** A session resumes on the same step in the same project after a
backend restart.

**SC-007.** A tutorial project appears in no project-listing surface and is
operable through every other route.

**SC-008.** Clearing tutorial data removes progress, tutorial projects, and the
scoped library, and leaves user projects untouched.

**SC-009.** Package tutorial progress changes no product behaviour: not the
unlock, not the toolbar dot, not the availability of any capability.

**SC-010.** The work-import toolbar entry is reachable with zero tutorials
completed.

**SC-011.** The tips strip stays visible while the palette grid scrolls and while
any category filter is active.

**SC-012.** ADR-053 §2.1, §2.2, §4.2, and §8 no longer describe a design this
spec contradicts.

## 6. Assumptions

**A-001.** The engine event bus in `src/scistudio/api/ws.py` and the watchdog
observer in `src/scistudio/api/routes/workflow_watcher.py` remain the product's
change-notification path. If either is replaced, FR-039's mapping moves with it;
FR-040's prohibition on polling does not depend on which bus is used.

**A-002.** `~/SciStudio Tutorials/` remains an acceptable default location. It is
what the current implementation already uses, so no user-visible location changes.

**A-003.** The known-projects registry remains both the recent-project data
source and the path-resolution surface for project routes. FR-052 and FR-054
follow from that coupling; if the two are ever separated, the marker approach can
be simplified to a separate registry.

**A-004.** Package tutorials are authored by package maintainers, not by
end users through the product. This spec makes user-level and project-level
tutorials discoverable and runnable but supplies no authoring surface; a manifest
there is written by hand or by an agent.

**A-005.** The scenarios spec, not this one, decides which core tutorial is the
work-import milestone. FR-068 requires the trigger be configuration precisely so
that decision can be made there and changed later.

**A-006.** The previewer user tier is out of scope here. The scenarios spec
depends on it — one designed scenario reuses a custom type across two tutorial
projects and needs its previewer to travel — and it is excluded by the personal
tool library spec's scope. Nothing in this spec assumes it exists.

**A-007.** The two in-flight behaviour changes the scenario content depends on —
unifying History and Git restore onto the run's commit, and removing block rerun
in favour of run-from-here — land before the scenarios spec. Neither affects the
system specified here; both affect what the tutorials say.
