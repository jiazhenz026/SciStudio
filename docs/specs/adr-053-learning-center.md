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
    - One shared enumeration, error-containment, and diagnostic contract for every `scistudio.*` entry-point group, bringing the three existing groups to it rather than adding a fourth divergent one.
    - Correcting the entry-point group documentation - `docs/architecture/ARCHITECTURE.md` still lists the removed `scistudio.runners` group, and `pyproject.toml` cites an ADR-052 section that does not exist.
    - Tutorial projects - created under a dedicated parent, marked so they never appear in recent-project surfaces, and overwritten when a tutorial is restarted.
    - A tutorial-scoped library directory that tutorial projects scan and real projects do not.
    - Progress stored on the backend, grouped by source, with exactly one milestone unlock driven by the core group.
    - The Learning Center surface - a permanent toolbar entry, the first-run landing, and the unfinished-work dot.
  out:
    - The block palette tips strip, tracked by #1997. The personal tool library spec routed it here, but it shares no mechanism with the tutorial runtime, depends on no Learning Center entry existing, and #1997 already carries its placement, behaviour, tip pool, and acceptance criteria in full. It ships on its own.
    - The six core tutorial scenarios themselves - their narratives, assets, copy, and step lists. Those are the Learning Center scenarios spec; this spec is the system they run on.
    - Any tutorial content shipped by a package.
    - Frontend assets supplied by a package tutorial. The shape of a tutorial step on screen stays core's.
    - A recording or authoring UI for user-level and project-level tutorials. This spec makes those tiers discoverable and runnable; the manifest is written by hand or by an agent.
    - Sandboxing drop-in execution, deferred by #1531 and unchanged here.
    - A user tier for previewers, excluded by the personal tool library spec and tracked separately. The scenarios spec depends on it; this spec does not.
    - Format and storage choices behind a save. The scaffold gains `data/processed/` for results (owner decision, 2026-08-11) and a step names a filename whose suffix picks the format; nothing here specifies the capability resolution behind it.
    - The work-import dialog, brief, and session, governed by the work-import spec. Only the unlock that routes to its entry point is specified here.
    - Provider configuration and the provider registry, governed by ADR-034.
governs:
  modules:
    - scistudio.tutorials
  contracts: []
  entry_points:
    - scistudio.tutorials
  files:
    - docs/specs/adr-053-learning-center.md
    - docs/adr/ADR-053.md
    - pyproject.toml
    - src/scistudio/api/routes/tutorials.py
    - src/scistudio/api/routes/projects.py
    - src/scistudio/api/routes/ai_pty/**
    - src/scistudio/api/runtime/_projects.py
    - src/scistudio/api/runtime/models.py
    - src/scistudio/blocks/registry/_scan.py
    - src/scistudio/core/types/registry.py
    - src/scistudio/previewers/registry.py
    - src/scistudio/core/dropins.py
    - src/scistudio/core/entry_points.py
    - src/scistudio/tutorials/__init__.py
    - src/scistudio/tutorials/manifest.py
    - src/scistudio/tutorials/discovery.py
    - src/scistudio/tutorials/driver.py
    - src/scistudio/tutorials/conditions.py
    - src/scistudio/tutorials/actions.py
    - src/scistudio/tutorials/session.py
    - src/scistudio/tutorials/projects.py
    - src/scistudio/tutorials/progress.py
    - src/scistudio/tutorials/schema/tutorial.schema.json
    - src/scistudio/tutorials/core/**
    - frontend/src/store/tutorialSlice.ts
    - frontend/src/components/TutorialPanel.tsx
    - frontend/src/components/Toolbar.tsx
    - frontend/src/components/WelcomeScreen.tsx
    - frontend/src/App.tsx
    - frontend/src/App.parts/WelcomePane.tsx
    - frontend/src/App.parts/useRunFirstWorkflowTutorial.ts
    - frontend/src/tutorials/runFirstWorkflow/content.ts
    - frontend/src/lib/api/tutorials.ts
    - frontend/src/components/LearningCenter.tsx
    - frontend/src/components/LearningCenter.parts/ActiveStep.tsx
    - frontend/src/store/learningCenterSlice.ts
    - frontend/src/lib/api/learningCenter.ts
  excludes:
    - docs/user/reference/**
    - docs/user/llms.txt
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - tests/packages/test_entry_point_symmetry.py
  - tests/tutorials/test_manifest_schema.py
  - tests/tutorials/test_discovery_tiers.py
  - tests/tutorials/test_conditions.py
  - tests/tutorials/test_session_lifecycle.py
  - tests/tutorials/test_progress.py
  - tests/api/test_tutorial_routes.py
  - tests/api/test_tutorial_project_visibility.py
  - frontend/src/components/__tests__/LearningCenter.test.tsx
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
`workflow.changed`, `workflow_completed`, `git.head_changed`, `blocks.reloaded`
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
User-level and project-level tutorials may not — the schema rejects the field.
Rejecting the field is not sufficient on its own: a tutorial may ship source
files as assets and write them anywhere in its project, so a project-level
tutorial could drop a `.py` file into `blocks/` and have the product import it on
the next refresh. The grading therefore covers assets and destinations as well as
the driver field (FR-020a), and only with both does a tutorial an agent writes
into a project become incapable of carrying executable code. This deliberately
does not repeat the tradeoff made for drop-in blocks, where `{project}/blocks/*.py`
is imported and executed with sandboxing deferred to #1531: tutorial code would be
reached earlier and far more often, since merely listing the catalogue would touch
it.

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

One piece of work is inherited rather than chosen. Adding `scistudio.tutorials`
means adding a fourth entry-point group to three that do not agree with each
other: `scistudio.types` propagates an enumeration failure the other two absorb,
the three accept three different payload shapes, only `scistudio.previewers`
records a load failure anywhere a user could see it, and only it prepares
`sys.path` for plugin import roots. A fourth group written to match any one of
them would make the disagreement the convention. §3's entry-point symmetry
requirements state one contract and bring all four to it — the same argument the
personal tool library spec makes about the refresh path, applied to discovery.

The palette tips strip (#1997) was routed here by the personal tool library
spec and is routed back out. It addresses the same problem — a user cannot go
looking for a feature whose existence they have never been shown — but it shares
no mechanism with anything specified here, the draft requirement for it already
said it must not depend on a Learning Center entry existing, and #1997 already
carries its placement, behaviour, tip pool, and acceptance criteria in full. Keeping it here
would have coupled a strip that ships in an afternoon to a system that ships in
eleven steps.

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
`workflows/` for workflow YAML written into the project (#2063), and `pages/`
for reading content. `workflows/` is graded executable-adjacent under FR-020a:
a workflow YAML names a code block's script path and working directory, so it
is configuration the product acts on to execute, not data.

**FR-007.** The manifest MUST declare `id`, `title`, and `summary`. It MAY
declare `cover` naming an image file in the tutorial directory, and `order` as an
integer controlling position within its group.

**FR-007a.** The manifest MUST declare a `manifest_version` integer, and a
manifest whose version the running core does not support MUST be listed as
unavailable naming the version it requires, on the same path as an unmet
requirement (FR-024). The format is published for package authors to write
against (FR-013) and ships inside distributions core does not control, so the
first breaking change to it arrives as a manifest that parses into the wrong
shape rather than as one that announces itself. A version field is the only thing
that lets discovery tell "written for a newer core" apart from "malformed", and
the two owe the user different messages.

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
`route_to` naming a tab or panel the user is taken to, `prefill` seeding a
dialog the user is about to open (FR-011b), `do` as an ordered list of
actions, `done_when` as a completion condition, and `pages` as an ordered list
of reading pages the step presents, each naming a file under `assets/pages/`
the way a `page_reached` condition names one — with or without its extension.
A declared page MUST exist when the manifest is loaded, on FR-014's grounds: a
reading step whose page is missing fails the author at listing, not the reader
on the page turn.

**FR-011c.** A step MAY declare `title` as a short heading for the step card.
A step without one MUST fall back to the tutorial's own title. Heading every
step with the tutorial's name tells the reader the one thing they already know
and nothing about where they are.

**FR-011b.** A step MAY declare `prefill` as a list of single-key mappings, each
naming one dialog and the values it opens holding. A step that names a value and
then presents a dialog offering a different one has the tutorial and the product
saying different things, and makes the reader retype something the tutorial
already decided.

The target set and each target's required values MUST be closed, core-owned, and
declared in exactly one place, on the same grounds as `highlight`'s: a prefill
only does anything once the frontend seeds the dialog it names, so a target
without a matching consumer is a manifest line that silently does nothing. A
target outside the set, a missing required value, a value the target does not
take, or the same target seeded twice in one step MUST be rejected at
validation.

A prefill MUST be a default and not a decision: what it seeds stays editable,
and a reader who supplies something else MUST NOT be blocked, because the step's
`done_when` judges the world rather than the dialog.

A target that seeds a block's settings rather than a dialog MUST fill only a
field the reader has left empty, and MUST NOT overwrite a value they supplied.
A step using one MUST judge something the reader did rather than the field it
seeded; a step that judges its own prefill judges the tutorial's work and
completes itself.

**FR-012.** A step omitting `done_when` MUST advance on an explicit user action
to continue. Reading steps are the common case; requiring a synthetic condition
for them would be ceremony. Under FR-054a every step advances this way; what
distinguishes a reading step is that it is ready to continue from the moment it
is entered, having no condition to meet.

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
`scistudio.blocks`, `scistudio.types`, and `scistudio.previewers`. A fifth group,
`scistudio.runners`, was removed and is not a precedent; the authority for its
removal is not restated here, because the citation that `pyproject.toml` carries
for it — "ADR-052 §7A" — names a section ADR-052 does not have, which FR-035
requires correcting. Repeating it here would republish the same unverifiable
authority this spec is removing.

**FR-018.** Listing the catalogue MUST NOT import any package module. Titles,
summaries, covers, order, and requirements MUST be read from manifests alone.

**FR-019.** A tutorial's identity MUST be the pair of its source and its id. Two
packages MAY ship tutorials with the same id.

**FR-020.** The `driver` field MUST be accepted only for core and package
tutorials. A user-level or project-level manifest declaring it MUST be rejected
at validation with a message naming the field and the restriction.

**FR-020a.** Rejecting `driver` alone does not make a tier incapable of carrying
executable code, and the tier restriction MUST therefore extend to assets and
destinations. A user-level or project-level manifest MUST be rejected at
validation when it carries an asset under `assets/code/`, `assets/panels/`,
`assets/replay/`, or `assets/workflows/`; when it declares a `replay` action; or
when a write or copy action's destination resolves under a directory the product
imports, executes, or reads as configuration for something it executes. That
restricted destination set is declared in exactly one place
(`scistudio.tutorials.actions.EXECUTED_PROJECT_PATHS`) and is wider than the
four directories originally named here as a floor: beside `blocks/`, `types/`,
`previewers/`, and `plots/` it covers `workflows/` and `tutorials/` — both
configuration this runtime acts on — the agent-surface directories every project
is provisioned with (`.claude/`, `.codex/`, `.agents/`, `.qoder/`,
`.kimi-code/`, `.scistudio/`, `.git/`), and the root files agents auto-load
(`.mcp.json`, `CLAUDE.md`, `AGENTS.md`). Without this, a project-level tutorial could place a `.py` file
under `blocks/` through an ordinary write action (FR-057) and have it imported and
executed on the next registry refresh, which is exactly the exposure the tier
grading exists to avoid. The rejection MUST name the tier, the field, and the
restriction.

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

#### Entry-point symmetry

Adding a fourth entry-point group to three that already disagree with each other
would make the disagreement the convention. These requirements state one contract
and bring all four groups to it.

The divergence is verified. Enumeration is wrapped in `try`/`except` for
`scistudio.blocks` (`src/scistudio/blocks/registry/_scan.py`) and
`scistudio.previewers` (`src/scistudio/previewers/registry.py`) but not for
`scistudio.types`, which calls `importlib.metadata.entry_points(group=...)` bare
at `src/scistudio/core/types/registry.py` and propagates a failure that the other
two absorb. The three accept three different payload shapes: a class or a
callable, a callable returning a list or tuple, and a factory callable. Only the
previewer registry records a load failure as a diagnostic anything can surface;
the other two log and move on, so a user whose package silently contributed
nothing has no way to find out. Only the previewer registry prepares `sys.path`
for plugin roots. All four statements were re-verified against `main` on
2026-08-08.

The timing is favourable rather than accidental. The *other* half of the same
problem — which drop-in directories each process sees, and which registries a
package install or a branch switch refreshes — was just consolidated:
`src/scistudio/core/dropins.py` is now the single answer, held in place by
`tests/api/test_registry_provisioning_parity.py` and
`tests/api/test_registry_reload_symmetry.py`. That work stopped at drop-in
directories and did not touch entry points; `dropins.py` contains no entry-point
handling at all. These requirements finish the job on the discovery side, with a
settled precedent for what "one answer" looks like and a test file to extend
rather than invent.

**FR-025.** Enumeration and loading for every `scistudio.*` entry-point group
MUST go through one shared helper. Each registry keeps its own registration
logic; none keeps its own enumeration, error handling, or diagnostic reporting.

**FR-026.** Failure to enumerate a group MUST be contained identically for every
group: logged, reported as a diagnostic, and treated as an empty group.
Enumerating one group MUST NOT be able to raise into a caller, which
`scistudio.types` can do today.

**FR-027.** Failure to load one entry point MUST be contained to that entry
point for every group. The remaining entry points in the group MUST still load.

**FR-028.** A load or registration failure MUST be recorded as a diagnostic the
product can surface, for every group. Logging alone is not sufficient: the
observable outcome of a silent failure is a package that installed successfully
and contributed nothing, which the user cannot distinguish from a package that
had nothing to contribute.

**FR-029.** The accepted payload shape MUST be one contract across the groups
that contribute objects: a callable returning the contributed objects.
`scistudio.blocks` MAY continue to accept a bare class because that form is
already published and packages depend on it; that allowance MUST be documented as
a compatibility affordance in one place rather than reproduced as a per-group
convention, and MUST NOT be extended to any group added later.

**FR-029a.** `scistudio.tutorials` MUST be exempt from FR-029 and MUST declare a
metadata-only payload: the entry point's value resolves to a directory containing
tutorial directories, and resolution MUST NOT call `EntryPoint.load()` or
otherwise import the module the value names. The exemption is required rather
than convenient — the callable contract is implemented by importing the target,
and FR-018 forbids importing a package module while listing the catalogue, so a
tutorial group satisfying both is impossible. The exemption MUST be recorded
beside FR-029 in the shared helper's documentation, with its reason, so it reads
as a second contract rather than as one group ignoring the first. Enumeration,
error containment (FR-026, FR-027), diagnostics (FR-028), and import-root
preparation (FR-030) apply to `scistudio.tutorials` unchanged.

**FR-030.** Plugin import-root preparation MUST be applied uniformly. If
`sys.path` preparation is required for one group to import a plugin's modules, it
is required for all of them. Today only `scistudio.previewers` prepares import
roots around its entry-point scan; `scistudio.blocks` and `scistudio.types` do
prepare them elsewhere — around drop-in execution and source-package import — so
the gap is specific to the entry-point path rather than to those registries as a
whole. The observable consequence is that the same package can resolve for
previewers and fail for blocks.

**FR-031.** Package install, package uninstall, branch switch, and the
working-tree rewrites that now trigger a registry refresh — restore, merge, and
cherry-pick, added by ADR-038 Addendum 1 — MUST reach every group, including
`scistudio.tutorials`. This half of the symmetry problem is already solved:
`src/scistudio/core/dropins.py` is the single answer to which drop-in
directories a process sees, and `tests/api/test_registry_provisioning_parity.py`
and `tests/api/test_registry_reload_symmetry.py` hold it in place. Tutorials MUST
join that path and extend those tests rather than adding a fourth independent
one.

**FR-032.** The previewer companion fallback — scanning the `scistudio.blocks`
and `scistudio.types` groups for a conventional `get_previewers()` when a package
declares no `scistudio.previewers` group — is the one permitted asymmetry. It
compensates for installed metadata missing a group that was added later, which is
a previewer-specific history rather than a design choice. It MUST NOT be extended
to `scistudio.tutorials`, and its reason MUST be recorded where it lives so it is
not read as the pattern to copy.

**FR-033.** A test MUST assert that all four groups behave identically under
enumeration failure, single-entry-point load failure, and refresh, so that a
fifth group cannot be added divergently without failing.

**FR-034.** The set of live entry-point groups MUST be documented in exactly one
place, and `docs/architecture/ARCHITECTURE.md` §12.4 MUST be corrected. Its table
still lists `scistudio.runners`, which `pyproject.toml` removed; a package author
reading the architecture document today is told to use a group that does not
exist.

**FR-035.** The removal note for `scistudio.runners` in `pyproject.toml` MUST
stop citing "ADR-052 §7A". ADR-052 has no §7A and does not mention runners
anywhere; the removal is real but its recorded authority is not, and a citation
that cannot be followed is worse than none.

#### The runtime and drivers

**FR-036.** The backend MUST own a tutorial runtime holding the active session:
which tutorial, which project, which step, and which steps are satisfied.

**FR-037.** Session state MUST survive a backend restart.

**FR-038.** The runtime MUST interact with tutorials only through a driver
interface. The interface MUST cover: the view of the current step, whether the
current step is satisfied given current product state, the actions to perform on
entering a step, and whether the tutorial has ended.

**FR-039.** Core MUST provide a manifest driver implementing that interface by
reading `tutorial.yaml`. It MUST be the driver for every core tutorial, every
user-level tutorial, and every project-level tutorial.

**FR-040.** A package driver MUST implement the same interface. The runtime and
every API response MUST be identical for both drivers; no response field may
reveal which driver produced it.

**FR-041.** The step view a driver returns MUST be limited to the fields FR-011
defines. A driver MUST NOT be able to introduce new rendering primitives, supply
frontend assets, or address any surface the manifest format cannot address. Core
owns what a tutorial step looks like.

**FR-042.** A package driver MUST be able to call the core condition evaluator so
it can use the vocabulary for the conditions it covers and implement only the
ones it does not.

**FR-043.** Exactly one tutorial session MUST be active at a time. Starting a
second MUST require leaving the first, and leaving MUST preserve the first
session for resumption.

**FR-044.** An exception raised by a driver MUST end the session with an error
naming the tutorial and the exception, MUST NOT mark the tutorial complete, and
MUST NOT prevent other tutorials from starting.

#### Completion conditions

**FR-045.** The completion-condition vocabulary MUST be defined and owned by
core. Tutorials reference terms; they do not define them.

**FR-046.** Conditions MUST be evaluated on the backend against product state.
No condition may be evaluated from frontend state, except `ui_event` (FR-052).
The evaluation context additionally includes the session-supplied entry time of
the current step (#2066): the session records when each step was entered and
hands that time in per evaluation, because it describes the reader's position
in the tutorial rather than the state of the product, and only the session
knows it.

**FR-047.** The vocabulary MUST include at least:

| Term | Judges |
|---|---|
| `node_exists` | a node of a given block type is present in the workflow |
| `edge_exists` | an edge connects two given block types or node ids |
| `config_equals` | a node's configuration key holds a given value |
| `config_matches` | a node's configuration key matches a glob, compared as a path |
| `run_succeeded` | a run of the workflow — or of a given node, or of any node of a given block type — completed successfully; `since_step_entry: true` counts only runs started since the current step was entered |
| `run_failed` | the most recent run ended without succeeding; `since_step_entry: true` reads only runs started since the current step was entered |
| `port_has_output` | a given output port holds data, on a named node or on any node of a given block type |
| `block_registered` | a block type is present in the registry |
| `type_registered` | a data type is present in the type registry |
| `previewer_registered` | a previewer is registered for a given type |
| `plot_exists` | a plot exists, optionally bound to a given block's output by node id or block type |
| `plot_rendered` | a rendered figure exists for a plot, addressed like `plot_exists` |
| `file_exists` | a project-relative path exists |
| `git_branch_exists` | a branch exists in the project repository |
| `git_current_branch` | the checked-out branch is a given name |
| `library_contains` | the tutorial-scoped library holds a named block, type, or previewer |
| `interaction_completed` | an interactive block's panel was submitted, on a named node or on any node of a given block type |
| `page_reached` | a reading step reached a given page |
| `ui_event` | a named frontend event was reported, optionally for a named target |

Where a term addresses a node, `node_id` and `block_type` are alternative
selectors for it: `block_type` alone reads "any node of that type", the two
filter conjunctively when both are given, and a term whose meaning requires a
node (`port_has_output`, `interaction_completed`) requires one of them at
validation. This is the same selector convention `node_exists`, `config_equals`,
and `config_matches` already use, extended in #2062 so the level designs can
address "the Load block" without knowing the node id a reader's drag produced.

The two run terms additionally accept `since_step_entry: true` (#2066), which
scopes the records they read to runs started since the current step was
entered, judged against the entry time FR-046's evaluation context supplies. A
step whose text says "press Run" can then wait for the run the reader performs
*on this step* instead of being satisfied by one they performed three steps
ago. FR-054 is untouched: at entry no run has started since entry, so the
scoped condition is simply false until the reader runs.

`plot_rendered` names a backend fact — display artifacts exist in the preview
cache under `.scistudio/previews/<workflow_id>/<node_id>/<output_port>/
<plot_id>/` — and deliberately coexists with the `ui_event` of the same name
(#2066). They answer different questions: the reported event says the reader
*saw* the figure render on their screen, the term says a figure *exists* as
product truth, whoever caused it and whether or not anyone was watching. The
welcome tutorial waits on the event and keeps meaning what it meant; a level
that cares about the artifact waits on the term.

**FR-048.** The vocabulary MUST support `all` and `any` combinators taking lists
of conditions. Negation is deliberately omitted: a tutorial step that advances
when something is *absent* advances by the user doing nothing, which teaches
nothing and is indistinguishable from a stuck step.

**FR-049.** An unknown term MUST be rejected at manifest validation, not at
evaluation. A tutorial that fails on step nine because of a typo is a tutorial
that failed for the user, not for its author.

**FR-050.** The active step's condition MUST be re-evaluated when any engine
event in a declared mapping is observed. The mapping MUST at minimum be:

| Event | Terms re-evaluated |
|---|---|
| `workflow.changed` | `node_exists`, `edge_exists`, `config_equals`, `config_matches` |
| `workflow_completed`, `block_done` | `run_succeeded`, `run_failed`, `port_has_output`, `plot_rendered` |
| `block_error` | `run_succeeded`, `run_failed`, `port_has_output` |
| `blocks.reloaded` | `block_registered`, `type_registered`, `previewer_registered`, `library_contains` |
| `git.head_changed` | `git_branch_exists`, `git_current_branch` |
| `file.changed` | `file_exists`, `plot_exists` |
| `interactive_complete` | `interaction_completed` |

`plot_rendered` rides the run events rather than `file.changed` because a
figure lands as an image, and image formats are outside the watcher's ADR-036
extension allowlist — no file event will ever announce one. A render the
reader triggers from the plot card is covered by the frontend's own `ui_event`
report and by FR-053's explicit re-check.

The two naming conventions in that table are the product's, not a typo. Engine
lifecycle events are declared in `src/scistudio/engine/events.py` with
underscores — `WORKFLOW_COMPLETED = "workflow_completed"`, `BLOCK_DONE`,
`BLOCK_ERROR`, `INTERACTIVE_COMPLETE` — while the events added later at the API
and watcher layer use dots: `WORKFLOW_CHANGED = "workflow.changed"`,
`GIT_HEAD_CHANGED = "git.head_changed"`, `BLOCKS_RELOADED = "blocks.reloaded"`,
and `FILE_CHANGED_EVENT_TYPE = "file.changed"`. The runtime MUST subscribe using
the declared constants rather than string literals, so this table cannot drift
from the bus without the import failing.

**FR-051.** The runtime MUST NOT poll for completion. Every re-evaluation MUST be
caused by an event under FR-050, an explicit request under FR-053, or entry into
a step.

**FR-052.** The frontend MUST be able to report a named user-interface event to
the backend, which MUST satisfy a matching `ui_event` condition. This is the only
completion path that originates in the frontend and exists because some product
actions — enlarging the preview panel, opening a tab — produce no backend state.

A report MAY carry the target the event acted on, and each event name declares
the one argument it may carry, on FR-089b's precedent for highlight entities
(#2063): `node_selected` and `block_source_viewed` take `block_type`,
`plot_rendered` takes `plot_id`, and `preview_expanded` — a singleton surface —
takes none. The pairing is core-owned and declared in exactly one place
(`scistudio.tutorials.conditions.UI_EVENT_SPECS`), read by manifest validation
and by the report route alike, so a condition naming an argument its event does
not carry is rejected at validation rather than waiting forever on a report no
emitter sends. A bare name remains a complete report and a complete condition:
an untargeted condition is satisfied by any report of its name, targeted or
not, while a targeted condition waits for a report carrying that target.

**FR-053.** The frontend MUST be able to request an explicit re-evaluation of the
active step. This covers state changes that no mapped event reaches: the
`file.changed` event is filtered to the allowlisted extensions in
`ADR036_FILE_ALLOWLIST`, so a `file_exists` condition on a data file such as a
TIFF will not be event-driven, and registry refreshes triggered by paths that do
not emit `blocks.reloaded` are likewise uncovered.

**FR-054.** A condition already satisfied when its step is entered MUST satisfy
that step immediately.

**FR-054a.** A satisfied step MUST NOT advance the session on its own. Advancing
MUST require an explicit user action to continue, for every step alike — the
ones with a `done_when` and the reading ones of FR-012. The step view MUST
report whether the current step's condition holds, so a client can present the
continue control as live or inert without re-deriving the judgment that spec
§4.1 places on the backend, and the backend MUST refuse to advance a step that
is neither satisfied nor a reading step.

This reverses the original design, in which a condition that came true advanced
the session with no confirmation. Automatic advance replaces the text the reader
is in the middle of with the next step's, and there is no way back to it: the
tutorial takes an action the reader did not ask for, at the moment they are
least able to follow it. Judging stays automatic and continuous — FR-050's
mapped events and FR-053's explicit re-check both keep the reported state
current — and only the move is the user's.

**FR-055.** Condition evaluation MUST be side-effect free. Evaluating a condition
MUST NOT create files, mutate registries, or trigger runs.

#### Step actions

**FR-056.** A step MAY declare actions performed on entry, before its text is
displayed.

**FR-057.** The action set MUST include writing an asset into the tutorial
project, copying an asset directory into the tutorial project, and replaying
scripted material into a designated surface.

**FR-058.** Write actions MUST be available at any step, not only at bootstrap.
Two designed scenarios depend on this: one has the tutorial break the workflow
mid-tutorial so the user recovers it, and one replays a scripted agent whose
every claim must be matched by a real change on disk.

**FR-059.** Actions MUST complete before the step's text is displayed. A step
that says "we have written this block for you" must not be readable before the
block exists.

**FR-059a.** Where an action writes into a directory the product's registries
scan, those registries MUST be re-scanned before the step's text is displayed,
and connected clients MUST be told to refresh. "The block exists" is a claim
about the product holding the block, not about a file being on disk: a step that
writes `blocks/x.py` and then says to find it in the palette is unfollowable
while the palette does not list it, which satisfies FR-059's letter and defeats
its purpose. A write outside those directories MUST NOT trigger a re-scan —
a `.py` file under `data/` is teaching material, and an ordinary copy step must
not pay for a scan it cannot benefit from.

A write landing under the project's `workflows/` MUST reach the open canvas the
same way (#2063): the canvas renders the frontend's copy of the graph, so the
runtime broadcasts the same `workflow.changed` frame an external on-disk edit
produces, before the step's text is displayed. The filesystem watcher is not an
answer here — it is not running headless, and FR-059a's ordering is
a property of the entry sequence, not of an observer's timing.

**FR-060.** An action failure MUST end the session with an error naming the step
and the action, and MUST NOT silently advance.

**FR-061.** Replay actions MUST NOT be able to reach any surface other than the
one the action names. Replay is scripted content playback, not a general remote
control for the product.

**FR-061a.** The set of surfaces a replay action may name MUST be closed, owned
by core, and declared in one place, and a manifest naming a surface outside it
MUST be rejected at validation. FR-061 constrains replay to "the surface the action
names" and is unimplementable and untestable until that set exists. The initial
set MUST contain exactly one member: the AI Chat terminal. Its byte stream today
comes from a PTY session over the WebSocket in
`src/scistudio/api/routes/ai_pty/`, consumed by
`frontend/src/components/AIChat/TerminalView.tsx`; a replay MUST be delivered as a
scripted session through that same path, so the tab strip, the terminal component,
and the tab lifecycle stay the product's real ones and only the byte source
changes. A replay MUST NOT accept user input back into the scripted session.

**FR-061b.** A replay MUST be expressible as an ordered sequence of segments,
each of which MAY carry its own write or copy actions, and a segment's actions
MUST complete before the next segment's bytes are delivered. A scripted agent
that claims to have written a block has to be matched by the block existing at the
moment the claim is readable, which a single opaque stream played to completion
cannot guarantee.

**FR-061c.** Ending a session mid-replay MUST terminate the scripted session and
leave no replay session object behind, on the same path a real PTY session uses
for termination.

#### Tutorial projects

**FR-062.** A tutorial declaring `bootstrap` MUST receive a project created under
a dedicated tutorial parent directory, defaulting to `~/SciStudio Tutorials/`.
This preserves the location the current implementation already uses.

**FR-062a.** Starting a tutorial whose project directory already exists, with no
session record for it, MUST adopt that directory rather than fail or replace it.
The session store and the tutorial parent directory are separate state and can
disagree: a `clear` whose directory removal failed, a hand-deleted session file,
a home directory restored from a backup without `~/.scistudio`. Each leaves the
tutorial listed as never started beside a directory that is still on disk, and
creating unconditionally raises through the start route — the user presses the
only button offered and gets an Internal Server Error. Adopting rather than
replacing, because the directory holds whatever work the user did last time and
FR-066 makes deleting it something they ask for by restarting. A directory that
is not a SciStudio project MUST still be refused, naming what it found.

**FR-063.** Tutorial projects MUST be recorded in the known-projects registry.
Several routes resolve a project's real path through that registry, including the
path containment check in `src/scistudio/api/routes/projects.py`, so an
unregistered tutorial project would fail those checks and could not be operated.

**FR-064.** A tutorial project MUST carry a marker distinguishing it from a user
project.

**FR-065.** Marked projects MUST be excluded from the project listing that feeds
the recent-project list, the projects dropdown, and the welcome pane. They MUST
remain fully operable through every other route.

**FR-066.** Restarting a tutorial MUST delete the previous tutorial project for
that tutorial and create a new one at the same location. The serial-suffix naming
the current implementation uses for repeat runs is removed with it.

**FR-067.** Deleting a tutorial project MUST require a confirmation naming the
directory.

**FR-068.** The Learning Center MUST state that tutorial projects are temporary
and that the user's own work belongs in their own project.

**FR-069.** A tutorial project whose directory has been removed outside the
product MUST invalidate its session on the next interaction and be offered from
the start.

#### The tutorial-scoped library

**FR-070.** Tutorial projects MUST scan a tutorial-scoped library directory in
place of the user-wide library, defaulting to a `.library/` directory under the
tutorial parent with `blocks/` and `types/` subdirectories.

**FR-071.** Real projects MUST NOT scan the tutorial-scoped library.

**FR-072.** A tutorial step teaching the save-to-library action MUST state that
performing the same action in the user's own project writes to their real
library. Otherwise the user learns an action whose real consequence they have
never observed.

**FR-073.** Clearing tutorial data MUST delete the tutorial-scoped library along
with the tutorial projects, so no orphaned teaching types survive.

#### Progress and the milestone unlock

**FR-074.** Progress MUST be stored on the backend under `~/.scistudio/`.
Browser-side storage is not acceptable: the backend must be able to read it to
evaluate the unlock and write it when a package is uninstalled, it does not
survive clearing browser data, and the desktop and web surfaces would keep
separate copies.

**FR-075.** A progress record MUST be keyed by source and tutorial id.

**FR-076.** Progress MUST be reported grouped by source, each group carrying its
own completed and total counts. No aggregate across groups is reported.

**FR-077.** A group's total growing because its source shipped new tutorials MUST
NOT be compensated for. A completed group returning to incomplete after an
upgrade is the intended reading: there is new material.

**FR-078.** Uninstalling a package MUST delete that package's progress group.
Reinstalling MUST start it from zero.

**FR-079.** Exactly one product behaviour MUST be driven by progress: completing
a named core tutorial MUST present the work-import offer, once. The named
tutorial MUST be configuration, not a constant.

**FR-080.** Only the core group MUST drive product behaviour. Package group
progress is display only and MUST NOT drive the unlock, the toolbar dot, or any
other behaviour.

**FR-081.** No capability MUST be gated on progress. The work-import toolbar
entry MUST remain permanently available regardless of progress, as work-import
FR-001 requires; the unlock decides when the product *volunteers* it. That entry
has shipped (`src/scistudio/api/routes/work_import.py`,
`frontend/src/components/BringInMyWorkDialog.tsx`), so the unlock routes to an
existing surface rather than one this spec has to define.

#### The Learning Center surface

**FR-082.** The Learning Center MUST be reachable from a permanent toolbar entry.

**FR-083.** On first launch with no recorded progress, the Learning Center MUST
be what the user sees.

**FR-084.** The Learning Center MUST list tutorials grouped by source, each group
labelled with its origin and its own count, with core first. Groups are
presented as tabs, one source per tab; a tab's tutorials, the selected
tutorial's detail, and that source's progress occupy separate regions, so
selecting a tutorial and starting it are distinct gestures. Selecting MUST NOT
start a tutorial, because starting one can create or delete a project on disk.

**FR-084a.** Tutorials that only ever ask the reader to read on MUST be listed
in a Reading tab of their own rather than in their source's tab, and that tab
MUST be present regardless of whether any such tutorial is installed. Which tutorials
those are MUST be derived from their declared steps, not from a manifest field:
the manifest already declares what each step waits on, and a second
classification could contradict it. A tutorial is a reading one when every step
either waits on an explicit continue or waits on a term that judges only the
reader's own progress through the material. The Reading tab MUST NOT carry a
count of its own, because its tutorials may come from several sources at once
and FR-076 forbids reporting a count across them.

The reading surface itself is core-owned, like every step surface (FR-041): a
reading step is rendered as a card presenting its declared `pages` in order,
with each page's content served by the existing pages route — the same route
whose serving records `page_reached` — so what a manifest contributes is names
and prose, never markup or a rendering primitive of its own.

**FR-085.** Each entry MUST show its title, summary, cover if declared, and
state: not started, in progress, complete, or unavailable with the reason. An
unavailable entry MUST remain selectable so that its reason can be read.

**FR-086.** The toolbar entry MUST carry an unfinished-work indicator when the
core group is not fully complete and the user has dismissed the first-run
landing. It MUST clear when the core group is complete, and MUST NOT offer a
permanent dismissal.

**FR-087.** Opening an in-progress tutorial MUST resume its session. Opening a
completed tutorial MUST offer restarting it under FR-066 and FR-067.

**FR-088.** The Learning Center MUST offer clearing tutorial progress. The
confirmation MUST name the directories to be deleted, because the action's label
describes the user's intent while its effect is deleting directories, and the two
must not be allowed to diverge silently.

**FR-089.** The active step MUST be displayed in a surface that does not occlude
the element it refers to, since most steps ask the user to act on the canvas or
the palette.

**FR-089a.** A step that declares a `highlight` MUST point at that element
directly: the named element is outlined where it sits, and the step's surface is
placed beside it rather than over it. The outline MUST NOT intercept pointer
events — it guides the reader and never confines them, because a target that
resolves to the wrong element or has not rendered would otherwise leave the user
unable to click anything at all, with no exit but abandoning the tutorial.

Two heavier forms were built and rejected in use. A permanent ember ring drawn
on the canvas was too intrusive over the user's own work (2026-08-10). Dimming
the rest of the window to leave only the target lit was worse (2026-08-11):
taking the whole product down to say one thing is up reads as the product having
stopped working, and it hides the surroundings the tutorial is teaching the
reader to navigate. Pointing at one element is a small claim and MUST be made
with a correspondingly small mechanism.

**FR-089b.** A `highlight` MUST be able to name one element among many of its
kind, and its vocabulary MUST require the argument that picks it. Pointing at
the containing surface — the palette, the canvas — is guidance only when the
step is about that surface; for a step whose content is *which* block or *which*
node, it names the haystack. Each target that addresses an entity therefore
declares a required argument (`block_type` for a palette entry or a canvas node,
`plot_id` for a plot card), a manifest naming such a target without its argument
MUST be rejected at validation, and the frontend MUST annotate every candidate
element with both the target name and that argument's value.

**FR-089c.** A step that declares no `highlight`, and a step whose target is not
on screen, MUST dock the step surface in the bottom-right corner and MUST NOT
draw an outline anywhere. An outline around nothing points at nothing, and a
target may legitimately be absent — a control that appears only once a run is
selected, a panel not yet open. The corner
rather than the center: a step with no target is prose to be read while looking
at the workspace it describes, and centering it puts a block of text in the
middle of the user's own canvas that must be dealt with before anything else.

**FR-090.** Leaving a tutorial MUST be possible at any step and MUST preserve the
session.

**FR-090a.** Finishing a tutorial MUST open the Learning Center and MUST close
the tutorial's project. A card reporting "complete" over the workspace is a dead
end: it names the outcome and leaves the reader with nothing to do next, while
the catalogue is where the next tutorial is. The project is closed for a
separate reason — a tutorial project looks like any other workspace once the
card is gone, and restarting the tutorial deletes it (FR-066), so leaving it
open invites the reader to keep working somewhere their work will not survive.

#### ADR-053 revisions

**FR-091.** ADR-053 §2.1 MUST be revised. It records that the existing
single-tutorial implementation is generalised; the decision is now that it is
discarded and replaced, with only the scenario narrative retained.

**FR-092.** ADR-053 §2.2 MUST be revised. It records that completion is granted
only by running and that reading is not progress. A reading-only summary tutorial
is part of the designed set, and it completes by being read. The revision MUST
carry the distinction rather than deleting the principle: the summary tutorial
names and organises capabilities the user has already exercised in earlier
tutorials, so it is review rather than instruction, and the principle continues
to hold for tutorials that teach. The revision MUST reach §1.1 and the §2 and
§2.2 headings as well as the section body: the §1.1 problem table states that
completion is granted only for a completed run, and both headings state the
same, so revising the body alone would leave two normative answers in one
document.

**FR-093.** ADR-053 §4.2 MUST be revised. It sets an initial unlock threshold of
40% of the catalogue, described as configuration rather than a constant. A
percentage over a catalogue that packages can grow does not denote a fixed point
in the user's experience; the trigger becomes completion of a named core
tutorial (FR-079).

**FR-094.** ADR-053 §8 MUST be revised to follow §4.2, and MUST record that
tutorial project cleanup — which it currently lists as undesigned — is specified
here (FR-066, FR-073, FR-088).

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `TutorialManifest` | The parsed `tutorial.yaml`; the only thing read to list the catalogue | `id`, `title`, `summary`, `cover`, `order`, `requires`, `bootstrap`, and exactly one of `steps` or `driver` | Belongs to one source; validated at discovery (FR-013); never triggers a package import (FR-018) |
| `TutorialSource` | Where a tutorial came from | `kind` (`core` \| `package` \| `user` \| `project`), `package_name` for packages | Determines the progress group (FR-076) and whether `driver` is permitted (FR-020) |
| `TutorialStep` | One step of a manifest-driven tutorial | `id`, `say`, `highlight`, `route_to`, `do`, `done_when` | Rendered through the step view (FR-041); actions run on entry (FR-059) |
| `TutorialDriver` | The interface the runtime talks to | step view, satisfied check, entry actions, ended check | Core's manifest driver (FR-039) or a package class (FR-040); may call the core evaluator (FR-042) |
| `CompletionCondition` | A term from the core vocabulary, or an `all`/`any` of them | term, term-specific arguments | Evaluated on the backend against product state (FR-046); side-effect free (FR-055) |
| `TutorialSession` | The single active session | tutorial identity, project path, current step, satisfied steps, status | At most one exists (FR-043); survives backend restart (FR-037) |
| `TutorialProject` | A project created for a tutorial | project fields plus a tutorial marker | Registered in known projects (FR-063), hidden from listing surfaces (FR-065), deleted on restart and on clearing (FR-066, FR-073) |
| `TutorialProgress` | Completion state per tutorial | `(source, tutorial_id)` to completion, grouped for reporting | Backend-stored (FR-074); the core group drives the single unlock (FR-079, FR-080) |

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
frontend: block lifecycle events, `workflow_started` / `workflow_completed`,
`workflow.changed`, `git.head_changed`, `interactive_prompt`, `file.changed`,
and `blocks.reloaded`. `interactive_complete` travels the other way, frontend to
backend, and reaches the runtime on the bus rather than through the outbound
set. `src/scistudio/api/routes/workflow_watcher.py` runs a watchdog
observer over the active project — recursively over `workflows/` for
`workflow.changed`, recursively over the project root for `file.changed`, and
over `.git/HEAD` and `.git/refs/heads/` for `git.head_changed`. The tutorial
runtime subscribes to the same bus. This is the whole reason FR-051 can forbid
polling.

The one limit worth stating: `file.changed` is filtered to the extensions in
`ADR036_FILE_ALLOWLIST` (`.py .r .txt .md .yaml .yml .json .csv .log`), so a
`file_exists` condition on a data file such as a TIFF or a Zarr store will not be
event-driven. FR-053's explicit evaluate request is what covers that, and it is
why that requirement exists rather than being a convenience.

**A new package `scistudio.tutorials`** holds the manifest model and schema,
discovery across the four sources, the driver interface and the core manifest
driver, the condition vocabulary and evaluator, the session, and progress
storage. It depends on the registries, the workflow model, the run records, and
the git engine — all read-only, consistent with FR-055.

**Discovery** follows the precedents already in the tree: entry-point loading as
in `src/scistudio/blocks/registry/_scan.py`, `src/scistudio/core/types/registry.py`,
and `src/scistudio/previewers/registry.py`, and drop-in directory scanning as the
block and type registries do for `~/.scistudio/` and `{project}/`. The difference
from all three is FR-018: discovery reads files and never imports the package.
The entry point's value is resolved to a directory path without loading the
module it names.

**Entry-point symmetry** is the one piece of work here that changes existing
code paths rather than adding new ones. The shared helper FR-025 requires owns
enumeration, per-entry-point error containment, diagnostic reporting, and
`sys.path` preparation; each registry keeps its own registration logic and loses
its own copy of everything above it. The concrete deltas are: wrap enumeration
for `scistudio.types`, which is the only group that can raise into its caller;
give the block and type registries the diagnostic list the previewer registry
already keeps, so a package that contributed nothing is distinguishable from a
package that had nothing to contribute; apply plugin import-root preparation to
all groups rather than to previewers alone; and state the accepted payload shape
once, with the bare-class form kept as a documented compatibility affordance for
`scistudio.blocks` only. The previewer companion fallback stays where it is and
is documented as history rather than pattern (FR-032). The refresh half of the
symmetry problem — install, uninstall, and branch switch reaching every registry
— is being consolidated by the personal tool library spec; FR-031 requires
tutorials to join that path rather than to build a fourth.

**Hiding tutorial projects** is a marker on the known-projects entry plus a
filter in the listing route (`src/scistudio/api/routes/projects.py`), not a
separate registry. `create_project` writes into `known_projects` unconditionally
and several routes resolve real paths through it, including a path containment
check; a separate registry would break those. FR-063 and FR-065 encode that.

**The tutorial-scoped library** needs no new mechanism. The registries already
accept scan directories, so a tutorial project registers the tutorial library
directory where a real project registers `~/.scistudio/`.

**The frontend** gains a Learning Center component rendering the grouped
catalogue, an active-step surface, the first-run landing, and the toolbar entry
and its dot. It holds no judging logic and no step content: it renders the step
view the backend returns, reports user-interface events (FR-052), and can request
an evaluation (FR-053).

### 4.2 Affected Files

**New — backend**

| File | Purpose |
|---|---|
| `src/scistudio/tutorials/__init__.py` | Package surface |
| `src/scistudio/tutorials/manifest.py` | Manifest model, schema, validation (FR-005..FR-015) |
| `src/scistudio/tutorials/discovery.py` | Four-source discovery, entry-point group, tier rules (FR-016..FR-024) |
| `src/scistudio/tutorials/driver.py` | Driver interface and the core manifest driver (FR-038..FR-042) |
| `src/scistudio/tutorials/conditions.py` | Vocabulary, evaluator, event mapping (FR-045..FR-055) |
| `src/scistudio/tutorials/actions.py` | Step actions (FR-056..FR-061) |
| `src/scistudio/tutorials/session.py` | Session lifecycle and persistence (FR-036, FR-037, FR-043, FR-044) |
| `src/scistudio/tutorials/projects.py` | Tutorial project creation, marking, deletion, scoped library (FR-062..FR-073) |
| `src/scistudio/tutorials/progress.py` | Progress storage, grouping, unlock (FR-074..FR-081) |
| `src/scistudio/tutorials/schema/tutorial.schema.json` | Published manifest schema (FR-013) |
| `src/scistudio/core/entry_points.py` | Shared enumeration, error containment, diagnostics, and import-root preparation for every `scistudio.*` group (FR-025..FR-030) |

The shared helper lives under `core/`. Three things decide the location. It is
imported by the block, type, and previewer registries, so it has to sit where all
three can reach it without a cycle — the reason `PackageInfo` lives in
`blocks/base/` rather than with the code that uses it — and import-linter permits
every consumer to reach `scistudio.core`, which needs nothing from `blocks`,
`engine`, `api`, `ai`, or `workflow` in return. `core/dropins.py` is already the
settled precedent for one answer shared by those same three registries, so
discovery's answer sits beside provisioning's. And "package" already denotes an
installed plugin distribution here, whose install, update, rollback, and delete
code lives in `desktop/package_installer.py`, `desktop/package_manager.py`, and
`desktop/package_ota.py`; a `scistudio.packages` holding only discovery plumbing
would invite that unrelated code to migrate into it later. A new top-level
`scistudio.packages` and a single `scistudio/entry_points.py` were the
alternatives; the choice among the three changes no requirement in §3.

**Rewritten — backend**

| File | Change |
|---|---|
| `src/scistudio/api/routes/tutorials.py` | Replaced entirely: catalogue, session lifecycle, evaluate, user-interface event, progress, clear |
| `src/scistudio/api/routes/projects.py` | Filter marked projects from the listing (FR-065) |
| `src/scistudio/api/runtime/_projects.py` | Carry the tutorial marker on creation and in the known-projects entry (FR-063, FR-064) |
| `src/scistudio/blocks/registry/_scan.py` | Enumerate and load through the shared helper; gain diagnostics; keep the bare-class allowance as the documented exception (FR-025, FR-028, FR-029) |
| `src/scistudio/core/types/registry.py` | Enumerate and load through the shared helper; stop propagating enumeration failures; gain diagnostics (FR-025, FR-026, FR-028) |
| `src/scistudio/previewers/registry.py` | Enumerate and load through the shared helper; keep the companion fallback with its reason recorded (FR-025, FR-032) |
| `src/scistudio/core/dropins.py` | Add the tutorial drop-in tier alongside blocks and types, and the tutorial-scoped library directory (FR-016, FR-031, FR-070..FR-073) |

`core/dropins.py` is named per kind throughout — `BLOCKS_DIR_NAME` and
`TYPES_DIR_NAME`, `user_blocks_dir` / `user_types_dir`, `project_blocks_dir` /
`project_types_dir`, `block_scan_dirs` / `type_scan_dirs`,
`register_block_scan_dirs` / `register_type_scan_dirs` — so a third drop-in kind
cannot be added without editing it. FR-031 requires tutorials to join that path
rather than build a fourth, which makes this file part of the change rather than
a file the change happens to touch.

**Deleted — frontend**

`src/tutorials/runFirstWorkflow/` (with its tests), `src/components/TutorialPanel.tsx`
(with its test), `src/store/tutorialSlice.ts` (with its test),
`src/App.parts/useRunFirstWorkflowTutorial.ts`, `src/lib/api/tutorials.ts`.

**New — frontend**

| File | Purpose |
|---|---|
| `src/components/LearningCenter.tsx` | Tabbed catalogue shell, clear action (FR-082..FR-088) |
| `src/components/LearningCenter.parts/TutorialList.tsx` | A tab's tutorials (FR-084, FR-084a) |
| `src/components/LearningCenter.parts/TutorialDetail.tsx` | The selected tutorial and the restart confirmation (FR-085, FR-087) |
| `src/components/LearningCenter.parts/GroupProgress.tsx` | One source's count and the running session's position (FR-076, FR-090) |
| `src/components/LearningCenter.parts/ProgressRing.tsx` | That count, drawn |
| `src/components/LearningCenter.parts/ActiveStep.tsx` | Active step surface (FR-089, FR-090) |
| `src/components/LearningCenter.parts/TargetHighlight.tsx` | The ring drawn around the step's target (FR-089a) |
| `src/components/LearningCenter.parts/useHighlightRect.ts` | Following the target element as it moves (FR-089a) |
| `src/components/LearningCenter.parts/placeCard.ts` | Placing the step card beside the target, or centered (FR-089, FR-089c) |
| `src/store/learningCenterSlice.ts` | Session view state and the tab split; no judging, no content |
| `src/lib/api/learningCenter.ts` | API client |

**Modified — frontend**

`src/components/Toolbar.tsx` for the entry and dot; `src/App.tsx` and
`src/App.parts/WelcomePane.tsx` for the first-run landing.

**Docs**

`docs/adr/ADR-053.md` §1.1, §2, §2.1, §2.2, §4.2, §8 (FR-091..FR-094);
`docs/architecture/ARCHITECTURE.md` §12.4 to drop the removed `scistudio.runners`
row and add `scistudio.tutorials` (FR-034); `pyproject.toml` to correct the
removal note's citation (FR-035).

### 4.3 Implementation Sequence

0. **Entry-point symmetry.** The shared helper, and the three existing registries
   moved onto it. This lands *before* `scistudio.tutorials` exists, so the fourth
   group is written against a settled contract rather than retrofitted onto one.
   It is independently reviewable and independently revertable, and it is the
   only step here that changes behaviour users already depend on.
1. **Manifest and schema.** Model, schema, validation, tier rules for `driver`.
   Testable with fixture directories and no runtime.
2. **Discovery.** Four sources, the entry-point group, duplicate and requirement
   handling. The no-import guarantee (FR-018) is asserted here.
3. **Conditions.** Vocabulary and evaluator against a constructed project. Pure
   reads, so testable without a session.
4. **Actions.** Write, copy, replay, with the containment rules of FR-015.
5. **Driver and session.** Interface, core manifest driver, session lifecycle,
   persistence, single-session rule, event subscription and the FR-050 mapping.
6. **Tutorial projects.** Creation, marking, listing filter, restart deletion,
   scoped library.
7. **Progress.** Storage, grouping, package uninstall removal, the milestone
   unlock.
8. **API routes.** Replace `routes/tutorials.py`; delete the old route in the
   same commit.
9. **Frontend.** Learning Center, active step, toolbar entry and dot, first-run
   landing; delete the five old modules in the same commit.
10. **ADR-053 revisions.**

Step 0 should ship on its own. It touches three registries every package
depends on and shares nothing with the rest of the sequence beyond the contract
it establishes, so bundling it into the Learning Center change would put a
regression in package discovery and a new feature in the same review.

Steps 1–4 are independently testable without any user interface. Step 8 is the
first point at which the product has no tutorial, and step 9 closes that window;
they should land together. Rebuilding the first core tutorial as manifest content
belongs to the scenarios spec, but a minimal fixture tutorial exercising every
vocabulary term and every action type is part of this spec's test material.

### 4.4 Verification Plan

| Area | Test | Asserts |
|---|---|---|
| Entry-point symmetry | `tests/packages/test_entry_point_symmetry.py` | All four groups behave identically under enumeration failure, single-entry-point load failure, and refresh (FR-033); no group propagates an enumeration failure (FR-026); every group records a diagnostic on load failure (FR-028); the bare-class allowance applies to `scistudio.blocks` only (FR-029); the tutorial group is exempt from the callable payload and is resolved without import (FR-018, FR-029a) |
| Drop-in parity | `tests/api/test_registry_provisioning_parity.py`, `tests/api/test_registry_reload_symmetry.py` | Extended, not duplicated: the tutorial drop-in tier resolves the same user and project directories as blocks and types, and every event that refreshes the block registry reaches tutorial discovery (FR-031) |
| Manifest | `tests/tutorials/test_manifest_schema.py` | Required fields; `steps` xor `driver`; asset and destination containment; unknown vocabulary term rejected at validation (FR-049); `driver` rejected for user and project tiers (FR-020) |
| Discovery | `tests/tutorials/test_discovery_tiers.py` | All four sources found; entry-point group read; duplicate ids within a source rejected; a malformed manifest does not empty its group (FR-022); unmet requirements still listed (FR-024) |
| No-import | `tests/tutorials/test_discovery_no_import.py` | Listing a catalogue containing a driver-declaring package tutorial imports no package module, asserted with an import hook that fails the test on load (FR-018) |
| Conditions | `tests/tutorials/test_conditions.py` | Each vocabulary term true and false against a constructed project; `all` / `any`; evaluation leaves no side effects (FR-055) |
| Events | `tests/tutorials/test_condition_events.py` | Each mapped event re-evaluates its terms; no timer or poll exists (FR-051); explicit evaluation satisfies a `file_exists` condition on a non-allowlisted extension (FR-053) |
| Actions | `tests/tutorials/test_actions.py` | Write and copy land before step text is exposed (FR-059); a path escaping the project is rejected; a failed action ends the session (FR-060) |
| Replay | `tests/tutorials/test_replay.py` | A replay action naming a surface outside the declared set is rejected at validation (FR-061); a replay segment's bound actions complete before the next segment is delivered (FR-061b); a replay stream reaches only the surface the action names (FR-061) |
| Tier assets | `tests/tutorials/test_tier_asset_rules.py` | A user-level or project-level manifest is rejected when it declares an executable asset, a replay action, or a destination under an executed directory (FR-020a) |
| Session | `tests/tutorials/test_session_lifecycle.py` | Resume across restart (FR-037); one session at a time (FR-043); a raising driver ends the session without marking completion (FR-044); an already-true condition satisfies on entry (FR-054) |
| Driver parity | `tests/tutorials/test_driver_parity.py` | A fixture package driver and a manifest tutorial produce API responses distinguishable only by content (FR-040); a driver cannot return fields outside the step view (FR-041) |
| Projects | `tests/api/test_tutorial_project_visibility.py` | Marked projects absent from the listing route but operable through others (FR-065); restart deletes and recreates (FR-066); an externally deleted project invalidates its session (FR-069) |
| Library | `tests/tutorials/test_scoped_library.py` | A tutorial project sees the scoped library; a real project does not (FR-071); clearing removes it (FR-073) |
| Progress | `tests/tutorials/test_progress.py` | Grouped counts; a growing total is not compensated (FR-077); package uninstall removes its group (FR-078); only the core group drives the unlock (FR-080) |
| Routes | `tests/api/test_tutorial_routes.py` | Catalogue, start, resume, evaluate, user-interface event, leave, clear; the removed route returns 404 (FR-003) |
| Frontend | `frontend/src/components/__tests__/LearningCenter.test.tsx` | Per-source tabs and their own counts; the Reading tab and its lack of one (FR-084a); entry states; selecting does not start; the dot appears and clears per FR-086; the clear confirmation names directories (FR-088) |

Manual verification before the PR: a full pass of a fixture tutorial exercising
every action type and every vocabulary term, a backend restart mid-tutorial, a
restart-tutorial cycle, a package install and uninstall around a fixture package
tutorial, and a clear-tutorial-data cycle with a real user project present to
confirm it is untouched.

### 4.5 Risks And Rollback

**The vocabulary is too small and core becomes a bottleneck.** The most likely
way this design disappoints. Mitigated three ways: the vocabulary is explicitly
extensible by core; package authors have the driver escape hatch (FR-040); and
FR-042 lets a driver reuse the evaluator so an author needing one extra condition
does not reimplement the other ten. The intended evolution is that a condition
several packages implement identically in their drivers becomes a core term —
the escape hatch doubles as the signal for what to promote, which is the same
progression the product already uses for project-level and user-level blocks.

**Event coverage is incomplete and a step appears stuck.** A condition whose
truth changes without a mapped event leaves the user waiting with no way to
complain. FR-053 is the designed answer, but it depends on the frontend knowing
when to ask. If this proves insufficient in practice, the escalation is a
user-visible "check again" control on the step surface rather than a poll — it
keeps the cost proportional to the failure and keeps the user informed instead of
guessing.

**Deleting the current tutorial before the new one is authored.** Between step 8
and the scenarios spec landing, the product's tutorial is a fixture. FR-004
accepts this on the grounds that the current tutorial has never reached users
through a release channel. If that ceases to be true before this lands, the
sequence must change, not the design.

**Restart deletes work a user did in a tutorial project.** FR-065 keeps tutorial
projects out of every listing surface and FR-068 states plainly what they are, so
reaching one requires the Learning Center. FR-067's confirmation names the
directory. The residual risk is a user who deliberately worked inside a tutorial
project after being told not to.

**A package driver is slow, blocking, or leaks.** It runs in the backend process
like every other package contribution. FR-044 contains exceptions; it does not
contain a driver that blocks. This is the same exposure package blocks already
carry and is not made worse here, but it is worth stating rather than implying
the escape hatch is free.

**Entry-point symmetry regresses package discovery.** This is the only work here
that changes a path every installed package already travels, and its failure mode
is a package that used to load and now does not. Three things bound it: it ships
alone (step 0), the parity test in FR-033 fails loudly rather than degrading
quietly, and the one behaviour with a genuine compatibility obligation — the bare
class form accepted by `scistudio.blocks` — is preserved rather than normalised
away. The residual risk is a package relying on an undocumented accident of one
registry's current error handling, which the shared helper would change.

**Rollback.** Every part except the entry-point symmetry work is new surface plus
one deletion.
Rolling back means restoring the deleted modules and route from history and
removing `scistudio.tutorials`; no data migration is involved, since progress is
a new file and tutorial projects are disposable by construction. Step 0 is
independently revertable.

## 5. Success Criteria

### Measurable Outcomes

**SC-001.** A second tutorial can be added by adding a directory and a manifest,
with no change to backend or frontend code. Demonstrated by the fixture tutorials
in the test material.

**SC-002.** Listing a catalogue containing package tutorials imports zero package
modules, asserted by test rather than by inspection.

**SC-003.** All four `scistudio.*` entry-point groups produce the same
observable behaviour under enumeration failure, under a single entry point
failing to load, and under refresh — asserted by one parity test that a fifth
group cannot be added divergently without failing.

**SC-004.** A malformed tutorial in any source leaves every other tutorial
listed and startable.

**SC-005.** A user-level or project-level manifest declaring `driver` is rejected
at validation with a message naming the field and the restriction.

**SC-006.** No polling loop exists in the tutorial runtime; every completion
transition is traceable to a mapped event, an explicit request, or step entry.

**SC-007.** A session resumes on the same step in the same project after a
backend restart.

**SC-008.** A tutorial project appears in no project-listing surface and is
operable through every other route.

**SC-009.** Clearing tutorial data removes progress, tutorial projects, and the
scoped library, and leaves user projects untouched.

**SC-010.** Package tutorial progress changes no product behaviour: not the
unlock, not the toolbar dot, not the availability of any capability.

**SC-011.** The work-import toolbar entry is reachable with zero tutorials
completed.

**SC-012.** A user-level or project-level tutorial cannot place an executable
file anywhere the product imports or executes it, asserted by test against the
asset, action, and destination rules rather than by the `driver` field alone.

**SC-013.** Every replayed surface appears in the closed surface set, and every
replay segment's file writes are on disk before that segment is readable.

**SC-014.** ADR-053 §1.1, §2, §2.1, §2.2, §4.2, and §8 no longer describe a
design this spec contradicts.

## 6. Assumptions

**A-001.** The engine event bus in `src/scistudio/api/ws.py` and the watchdog
observer in `src/scistudio/api/routes/workflow_watcher.py` remain the product's
change-notification path. If either is replaced, FR-050's mapping moves with it;
FR-051's prohibition on polling does not depend on which bus is used.

**A-002.** `~/SciStudio Tutorials/` remains an acceptable default location. It is
what the current implementation already uses, so no user-visible location changes.

**A-003.** The known-projects registry remains both the recent-project data
source and the path-resolution surface for project routes. FR-063 and FR-065
follow from that coupling; if the two are ever separated, the marker approach can
be simplified to a separate registry.

**A-004.** Package tutorials are authored by package maintainers, not by
end users through the product. This spec makes user-level and project-level
tutorials discoverable and runnable but supplies no authoring surface; a manifest
there is written by hand or by an agent.

**A-005.** The scenarios spec, not this one, decides which core tutorial is the
work-import milestone. FR-079 requires the trigger be configuration precisely so
that decision can be made there and changed later.

**A-006.** The previewer user tier is out of scope here. The scenarios spec
depends on it — one designed scenario reuses a custom type across two tutorial
projects and needs its previewer to travel — and it is excluded by the personal
tool library spec's scope. Nothing in this spec assumes it exists.

**A-007.** The recovery-path behaviour the scenario content depends on has
landed and is no longer an assumption. ADR-038 Addendum 1 (#2033) withdrew Re-run
entirely, widened the History tab's Restore from one workflow YAML to the run's
full recorded tree so it matches the Git tab's, added advisory input and
environment checks ahead of a restore, and made restore, merge, and cherry-pick
refresh the block registry. "Run from here" is explicitly unaffected. None of
this changes the system specified here; it changes what the tutorials say, and
the scenarios draft has been updated against it.

**A-008.** The personal tool library's user-visible surfaces have *not* landed.
Its plumbing has: the drop-in consolidation, the drop-in type import fix, and
refresh symmetry are all on `main`. Its surfaces are not — `map_block_origin`
still collapses `tier1` to `custom`, and there is no types route and no types
palette. The scenarios spec depends on those surfaces; this spec does not.
