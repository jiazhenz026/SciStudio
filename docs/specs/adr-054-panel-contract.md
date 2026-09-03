---
spec_id: adr-054-panel-contract
title: "ADR-054 Panel Contract — One Panel, Two Capabilities, Two Resolutions"
status: Draft
feature_branch: docs/adr-054-panel-contract-spec
created: 2026-09-02
input: "Owner-directed live session (guided): author the panel-contract implementation spec for ADR-054 sections 3, 9, and 10.1. The owner settled the design in discussion — one panel concept with two orthogonal axes (how a panel is found; what it may do), capability declared statically before load, one merged asset route, panels the user can edit with edits saved back to the tier being edited, read-only core and package panels copied into the project, an explicit error and a revert when an edit breaks a panel, mandatory hot reload with an optional state hook, all eleven built-in panels rewritten into the new form, built-in panel documents placed on disk behind the same asset route as every other tier, and strictly self-contained documents accepting duplicated table-rendering code."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 48
  - 51
  - 52
  - 53
  - 54
related_specs:
  - adr-048-preview-system
  - adr-051-interactive-blocks
  - adr-054-notebook-dependency-analysis
  - adr-054-explore-session
  - adr-054-explore-frontend
  - adr-054-agent-enablement
  - adr-054-documentation
scope:
  in:
    - The shared panel contract — manifest, capability declaration, and API version constant — and its placement in the core layer.
    - The sandboxed-frame mounting mechanism and the message contract across the frame boundary.
    - Two resolution paths kept as they are - by data type through the routing ladder and the per-type user choice, and by block through the manifest declared on the block class.
    - Four-tier panel discovery, including a core tier that now lives on disk, and how each tier registers a panel - a package through an entry-point group that points at panel directories, the user library and the project by containing a directory.
    - Capability-aware resolution - every request to open a panel states whether it needs to display or to produce, candidates are filtered by that before the ladder and the user choice apply, and the user choice is kept per type and per capability.
    - One asset route with one path-confinement check and one suffix allowlist serving all four tiers.
    - Panel editing - reading a panel's source, writing back to the tier being edited, copying a read-only core or package panel into the project, reverting, and hot reload.
    - Rewriting the eleven built-in panels into the new form; their Python providers are unchanged.
    - Retiring the duplicate frontend envelope-kind dispatch in favour of a fallback panel named by the backend.
    - The vocabulary rename from previewer to panel, in its own commit.
    - A compatibility shim for unmigrated packages, with a removal condition named in the ADR-048 addendum.
    - The ADR-048 and ADR-051 addenda that carry the contract change and its governance transfer.
  out:
    - The explore session, the kernel, the notebook, and the dependency analysis.
    - The agent-facing teaching surface — the skill bundle and the agent reference — which belongs to the agent-enablement spec.
    - Human documentation revision, which is specified separately in adr-054-documentation.
    - Giving a plot panel the producing capability, deferred to issue 2212.
    - Any change to plot rendering, the preview cache, or plot artifact registration.
    - Any change to what a block does with a produced value; that belongs to the session.
governs:
  modules:
    - scistudio.previewers
    - scistudio.blocks.base.interactive
    - scistudio.api.routes.data
    - scistudio.api.routes.blocks
    - scistudio.core.dropins
    - scistudio.core.entry_points
  contracts:
    - scistudio.previewers.models.PreviewerSpec
    - scistudio.previewers.models.FrontendManifest
    - scistudio.previewers.models.PreviewEnvelope
    - scistudio.blocks.base.interactive.PanelManifest
  entry_points:
    - scistudio.previewers
  files:
    - docs/specs/adr-054-panel-contract.md
    - src/scistudio/previewers/**
    - src/scistudio/blocks/base/interactive.py
    - src/scistudio/api/routes/data.py
    - src/scistudio/api/routes/blocks.py
    - src/scistudio/api/schemas.py
    - src/scistudio/core/dropins.py
    - src/scistudio/core/entry_points.py
    - frontend/src/components/DataPreview.parts/**
    - frontend/src/App.parts/InteractiveModals.parts/**
    - frontend/src/App.parts/InteractiveModals.tsx
    - frontend/src/components/PreviewerPalette.parts/**
    - frontend/src/components/PreviewerPalette.tsx
    - frontend/src/components/promotion/**
    - frontend/src/store/previewSlice.ts
    - frontend/src/store/previewerCatalogSlice.ts
    - frontend/src/store/usePreviewerCatalog.ts
    - tests/previewers/**
    - tests/architecture/test_layer_deps.py
    - tests/adr052_contract/**
    - docs/adr/ADR-048.md
    - docs/adr/ADR-051.md
  excludes:
    - docs/architecture/**
    - docs/package-development/**
    - docs/user/**
    - src/scistudio/_skills/**
    - src/scistudio/_agent_reference/**
    - src/scistudio/plot/runtime.py
    - docs/audit/**
    - docs/planning/**
planned_governs:
  modules:
    - scistudio.core.panels
    - scistudio.panels
  contracts:
    - scistudio.core.panels.PanelManifest
    - scistudio.core.panels.PanelCapability
  entry_points:
    - scistudio.panels
  files:
    - src/scistudio/core/panels.py
    - src/scistudio/panels/**
    - src/scistudio/api/routes/panels.py
    - frontend/src/panels/**
  excludes: []
tests:
  - tests/previewers/test_preview_routing.py
  - tests/previewers/test_preview_security.py
  - tests/previewers/test_previewer_dropins.py
  - tests/previewers/test_previewer_choice.py
  - tests/api/test_previewers.py
  - tests/api/test_previewer_discovery.py
  - tests/api/test_interactive_panels.py
  - tests/architecture/test_layer_deps.py
  - tests/adr052_contract/test_surface_inventory.py
  - tests/panels/test_panel_contract.py
  - tests/panels/test_panel_capability_gate.py
  - tests/panels/test_panel_tiers.py
  - tests/panels/test_panel_editing.py
  - tests/panels/test_panel_asset_route.py
  - tests/panels/test_builtin_panels.py
  - tests/panels/test_compat_shim.py
  - tests/panels/test_panel_registration.py
  - tests/panels/test_panel_resolution.py
acceptance_source: adr
language_source: en
---

# ADR-054 Panel Contract — One Panel, Two Capabilities, Two Resolutions

## 1. Change Summary

SciStudio has two dynamic panel loading paths. The previewer loader validates a
manifest, imports an ES module from a backend-validated same-origin URL, reads a
named export, checks an API version, and mounts it with a read-only host API.
The interactive-block panel loader performs the same sequence against a
different asset route and hands the module a way to confirm or cancel. Two
copies of the load sequence, two API version constants, two asset routes, and
two different behaviours when a module fails to load.

This spec replaces both with one contract. A panel declares one of two
capabilities: **displaying**, which renders what it is given and has no outbound
path, and **producing**, which renders what it is given and can hand a value
back. What is called a previewer today is the degenerate case — a panel resolved
by the type of the data, declaring only the displaying capability. No separate
kind of thing survives the change.

The change is larger than merging two copies of one sequence. Both paths today
import an ES module into the application's own React tree; ADR-054 §3.2
specifies a single self-contained HTML document mounted in a sandboxed frame and
reachable only through message passing. The mounting mechanism changes, so every
existing previewer and every package panel migrates or crosses a compatibility
shim, and the eleven panels SciStudio ships built in are rewritten into the new
form. Their Python providers are untouched; what changes is the frontend
document each one renders through.

Two consequences follow from putting the built-in panels on disk rather than in
the frontend bundle. A person can finally change them — the table view they look
at every day becomes a directory they can copy into their project and edit,
which the compiled-in form made impossible. And the frontend's own dispatch from
envelope kind to viewer component disappears, because the backend router has
already chosen a panel and the host can simply mount it.

The work is scoped to the contract and its migration. The explore session, the
kernel, and the notebook depend on this contract and are specified separately;
human documentation is revised in `adr-054-documentation`; giving a plot panel
the producing capability is deferred to issue 2212.

## 2. User Scenarios & Testing

### User Story 1 - One panel serves both display and production (Priority: P1)

A package author writes a region picker for a spectrum. A person opens a
spectrum from the workflow canvas and the picker renders it read-only. Later,
inside a session, the same picker renders the same spectrum and the region the
person drags becomes a line of code. The author wrote one panel and never chose
which situation it belonged to.

**Why this priority**: This is the contract's reason to exist. Every other story
in this spec is a property of the mechanism that makes this one possible, and
none of them is worth building if a panel still has to be written twice.

**Independent Test**: Write one panel directory declaring the producing
capability. Mount it from the preview surface and confirm it renders and has no
outbound path. Mount it from a producing position and confirm the same document
renders and its produced value arrives at the host. No second copy of the panel
exists.

**Acceptance Scenarios**:

1. **Given** a panel declaring the producing capability and a data object of its
   target type, **When** the person opens that object from the canvas,
   **Then** the panel renders it and the host grants no outbound message type.
2. **Given** the same panel mounted in a producing position, **When** the person
   completes an interaction, **Then** the value reaches the host through the
   single outbound path and nowhere else.
3. **Given** a panel declaring only the displaying capability, **When** it is
   mounted in a producing position, **Then** the host refuses the mount with a
   readable error rather than granting an outbound path the panel never claimed.

### User Story 2 - A person changes a built-in panel (Priority: P2)

A person finds a control in the built-in table view unhelpful. They open the
panel, change it, save, and the panel they are looking at redraws with the
change. Reopening the project later still shows their version, and a colleague
who receives the project sees it too.

**Why this priority**: The editing capability is what the unification buys the
person rather than the developer, and it is worth little if it applies only to
third-party panels while the ones they actually use every day stay compiled in.
It ranks below Story 1 because it presupposes the contract.

**Independent Test**: Edit the built-in table panel from a project, save, and
observe the mounted panel redraw without reopening anything. Confirm the edited
copy is a file inside the project directory and that the original is unchanged.

**Acceptance Scenarios**:

1. **Given** a built-in panel and an open project, **When** the person edits it,
   **Then** a copy is created in the project and the original core file is not
   written.
2. **Given** an edited project panel, **When** the person saves,
   **Then** the mounted panel is torn down and remounted from the new document
   without the person reopening the view.
3. **Given** a panel already belonging to the project, **When** the person edits
   and saves it, **Then** it is written back in place with no second copy made.
4. **Given** a project containing an edited panel, **When** the project is
   opened on another machine, **Then** the edited panel resolves in preference
   to the built-in one.

### User Story 3 - A broken panel never costs the reader their data (Priority: P3)

A panel fails — a package ships a broken document, or a person saves an edit
with a syntax error. The person still sees their data, can read what went wrong,
and has a way out.

**Why this priority**: Editing panels makes breakage ordinary rather than
exceptional, so the failure path is part of the feature rather than a
defensive extra. It ranks below Story 2 because it is that story's safety net.

**Independent Test**: Break a panel document deliberately. Confirm the data is
still displayed through the fallback panel, the diagnostic names the panel and
the failure, and a revert control restores the shadowed original.

**Acceptance Scenarios**:

1. **Given** a panel whose document fails to load, **When** it is mounted,
   **Then** the host renders its own error surface and the fallback panel the
   envelope names, and the data remains visible.
2. **Given** an edited panel that fails to load, **When** the error surface is
   shown, **Then** it offers a revert that deletes the shadowing copy and
   restores the panel that was shadowed.
3. **Given** a panel that never completes the handshake, **When** the host's
   wait elapses, **Then** it is treated as a load failure rather than left
   blank.

### User Story 4 - An unmigrated package keeps working (Priority: P4)

A person has `scistudio-blocks-imaging` installed at a version written against
the old contract. After upgrading SciStudio their images still preview.

**Why this priority**: Package authors cannot be made to migrate on the same day
the contract changes, and a version of SciStudio that silently stops rendering
a published package's data is not shippable. It ranks below the failure path
because it is bounded in time — the shim is removed once the packages migrate.

**Independent Test**: Install a package built against the ADR-048 module form,
open data it previews, and confirm it renders. Then confirm the same package
cannot obtain a session binding or an outbound path.

**Acceptance Scenarios**:

1. **Given** a package previewer in the old ES-module form, **When** its data is
   opened, **Then** it renders through the compatibility shim.
2. **Given** the same package, **When** it is mounted in a session context,
   **Then** it receives neither variable bindings nor an outbound path.
3. **Given** the shim, **When** the ADR-048 addendum's removal condition is met,
   **Then** the shim's removal is a deletion rather than a redesign.

### User Story 5 - A maintainer finds one mechanism (Priority: P5)

Someone reading the tree a year from now finds one loader, one version constant,
one asset route, and one word for the concept.

**Why this priority**: ADR-054 §9 exists because the predictable failure of this
kind of unification is a third implementation appearing beside the two it was
meant to replace. It ranks last because it is verified by inspection rather than
by use, not because it is optional.

**Independent Test**: Search the tree for the loader, the version constant, and
the asset route. Each returns one definition. Search for the retired vocabulary
outside historical documents and the compatibility shim; it returns nothing.

**Acceptance Scenarios**:

1. **Given** the merged implementation, **When** the tree is searched for a
   panel API version constant, **Then** exactly one definition is found.
2. **Given** the merged implementation, **When** the two former loader modules
   are looked for, **Then** neither exists.
3. **Given** the rename, **When** the layer enumeration and the frozen public
   symbol inventory are checked, **Then** both name the panel subsystem and pass.

### Edge Cases

- **Two tiers declare the same panel id.** The lower tier shadows the higher
  one, which is the mechanism the editing story depends on. A collision *within*
  one tier is a discovery error reported through the same surface that reports a
  refused drop-in today.
- **A person copies a built-in panel, then SciStudio updates and the built-in
  changes.** The copy keeps winning. The person is not told, because a
  notification on every update for every shadowed panel is noise; the discovery
  surface shows which tier each panel resolved from, which is where the answer
  belongs.
- **A panel is mounted in two places when it is edited.** Every mounted instance
  reloads, because the document on disk is the single definition and leaving one
  view stale is harder to explain than reloading both.
- **The optional state hook returns something that will not serialise.** The
  host discards it and remounts clean rather than failing the reload. Losing an
  in-progress selection is recoverable; failing to reload after a save is not.
- **A produced value is in flight when a reload is triggered.** The value is
  delivered if it has already left the panel, and the reload proceeds. A panel
  cannot both be reloading and be the authority on a value it has not yet sent.
- **A panel document exceeds a reasonable size.** The asset route applies the
  same bound it applies to any served asset, and an oversized document is a load
  failure with a readable diagnostic.
- **A panel declares a target type nothing registers.** It is discovered,
  listed, and never routed to. The discovery surface shows it, which is how a
  package author learns their target type name is wrong.

## 3. Requirements

### Functional Requirements

**The contract itself**

- **FR-001**: The panel contract — the manifest shape, the capability
  declaration, and the API version constant — MUST be defined in the core layer.
  Its consumers span the block layer, the panel subsystem, and the API layer,
  and no layer above core may be imported by the others.
- **FR-002**: A panel MUST be a directory containing a declaration file and a
  single self-contained entry document.
- **FR-003**: The declaration MUST carry the panel's id, its display name, the
  data types it targets, its declared capability, and the name of its entry
  document. A declaration missing any of these MUST be refused at discovery
  with a diagnostic naming the panel directory and the missing field.
- **FR-004**: Exactly one API version constant MUST exist, shared by the host
  and the panels it loads. A panel declaring a version the host does not accept
  MUST be refused before it is mounted.
- **FR-005**: A panel's capability MUST be declared statically in its
  declaration file and MUST be resolved before the panel loads. There MUST be no
  runtime negotiation by which a mounted panel acquires a capability it did not
  declare.
- **FR-006**: The capability set MUST contain exactly two members, displaying
  and producing. A producing panel MUST also be mountable for display.

**Mounting and the message contract**

- **FR-007**: A panel MUST be mounted inside a sandboxed frame and MUST be
  reachable from the host only through message passing.
- **FR-008**: A panel frame MUST be mounted with the sandbox attribute
  granting `allow-scripts` and nothing else. Each withheld permission is
  withheld for a reason: `allow-same-origin`, because with it the framed
  document shares the application's origin and can reach the parent document,
  its storage, and the API with the person's credentials, which would make
  the frame no boundary at all; `allow-forms`, because a panel submits
  nothing; `allow-popups` and `allow-top-navigation`, because a panel must
  not open or navigate anything outside itself; `allow-modals`, because a
  panel must not block the application with a dialog; `allow-downloads`,
  because saving a file is host chrome. The frame therefore runs at an opaque
  origin: the host addresses it by its window reference, every message in
  both directions carries a per-mount token the host issued at mount, and a
  message without the token MUST be ignored.
- **FR-009**: The host MUST perform a handshake before treating a panel as
  mounted: it sends the API version and the opening snapshot, and the panel
  answers that it is ready. A panel that does not answer within a bounded wait
  MUST be treated as a load failure.
- **FR-010**: The host MUST supply, across the frame boundary, what the panel is
  displaying, a bounded windowed read, an update channel carrying the reason and
  what changed, and an error channel.
- **FR-011**: A displaying panel MUST NOT be granted any outbound message type.
  The restriction MUST be enforced by the host rather than by the panel's own
  restraint.
- **FR-012**: A producing panel's only outbound path MUST be the emission of
  code. The meaning of what it emits is settled by the context it runs in and
  MUST NOT be interpreted by the panel loading machinery.
- **FR-013**: The message contract MUST allow a panel to be bound to more than
  one variable, because a panel that compares two objects is an ordinary case.
- **FR-014**: A panel that fails to load, fails to validate, fails the version
  gate, or fails the handshake MUST produce one behaviour: the host renders its
  own error surface carrying a diagnostic that names the panel and the failure,
  and mounts the fallback panel so the data remains visible.
- **FR-015**: The fallback panel MUST be named by the backend in the response
  the host is already reading. The frontend MUST NOT carry its own mapping from
  a response's kind to a panel.

**Discovery and the four tiers**

- **FR-016**: A panel addressed by the type of the data MUST resolve through the
  existing routing ladder together with the existing per-type user choice. This
  spec changes neither.
- **FR-017**: A panel addressed by the block that opens it MUST resolve through
  the manifest declared on the block class, discovered exactly as its block is
  and inheriting the block tiers.
- **FR-018**: Panels MUST be discovered from four tiers: a core set shipped with
  the application, a package set discovered through entry points, the user
  library, and the open project.
- **FR-019**: A panel in a lower tier MUST shadow a panel of the same id in a
  higher one, in the order project, user library, package, core.
- **FR-020**: For the duration of the migration, the existing previewer
  directories in the user library and the project MUST continue to be
  discovered.

**Serving**

- **FR-021**: One asset route MUST serve all four tiers, using one path
  confinement check and one suffix allowlist, differing only in the root
  directory each tier resolves to. The route MUST answer read-only
  cross-origin requests, because a panel at an opaque origin fetches bulk
  assets from it directly, and no other route MUST answer such requests,
  which is what keeps the asset route the only thing a panel can reach
  without the host.
- **FR-022**: The two existing asset routes MUST continue to serve their
  existing clients for the duration of the migration.
- **FR-023**: The endpoints that list panels, rebuild the registry, and record
  the per-type user choice MUST be brought under the panel naming alongside the
  asset route, and MUST keep their current behaviour.

**Editing**

- **FR-024**: A person MUST be able to read the source of any resolved panel,
  whichever tier it came from.
- **FR-025**: Saving an edit MUST write back to the tier the panel was resolved
  from. The system MUST NOT ask the person where to save.
- **FR-026**: Core and package panels are read-only. Editing one MUST copy it
  into the open project, and MUST NOT write to the core or package location.
- **FR-027**: A copy made by FR-026 MUST keep the panel's id, so that the tier
  ordering of FR-019 is what makes the copy take effect.
- **FR-028**: When an edited panel fails to load, the host MUST report the
  failure explicitly and offer to revert. It MUST NOT silently fall back to the
  panel that was shadowed, because a silent fallback reads as an edit that was
  never saved.
- **FR-029**: Reverting MUST delete the shadowing copy, restoring whichever
  panel it was shadowing.
- **FR-030**: Saving a panel MUST reload it: every mounted instance of that panel
  is torn down and remounted from the new document, without the person
  reopening the view.
- **FR-031**: The contract MUST offer an optional state hook by which a panel
  hands the host a serialisable snapshot before teardown and receives it on
  remount. A panel that does not implement it MUST remount clean, and a snapshot
  that cannot be serialised MUST be discarded rather than failing the reload.
- **FR-032**: The reload trigger MUST fire for panel files written by the agent
  on the person's behalf, not only for files written by the person directly.

**The built-in panels**

- **FR-033**: The eleven built-in panels — the nine core previewers and the two
  core interactive panels — MUST be rewritten as panel directories in the new
  form. Their Python providers MUST be unchanged.
- **FR-034**: Built-in panel documents MUST be strictly self-contained. Where
  several built-in panels render similar structures, the duplication is accepted
  and MUST NOT be resolved by a shared runtime import.
- **FR-035**: The host's error surface and diagnostics banner are host chrome
  rather than panels, and MUST remain able to render when the frame mechanism
  itself is unavailable.
- **FR-036**: The frontend dispatch from a response's kind to a viewer component
  MUST be deleted, superseded by FR-015.
- **FR-037**: A built-in panel MUST be shadowable from the user library and the
  project on the same terms as any other panel.

**Vocabulary**

- **FR-038**: The concept MUST be named panel throughout the code. The retired
  word MUST survive only as the name of the displaying capability, in historical
  documents, and in the compatibility shim.
- **FR-039**: The rename MUST be a separate commit from the behaviour change.
- **FR-040**: The architecture layer enumeration MUST be updated to name the
  renamed subsystem.
- **FR-041**: The frozen public-symbol inventory and the stability markers on the
  renamed public symbols MUST be updated, and the spec MUST state how the
  renamed symbols' stability markers are derived.

**Compatibility**

- **FR-042**: A previewer written against the ADR-048 module form MUST continue
  to load through a compatibility shim.
- **FR-043**: The shim MUST NOT grant variable bindings or an outbound path. A
  package obtains the new capabilities by migrating to the contract.
- **FR-044**: The shim's removal condition MUST be stated in the ADR-048
  addendum rather than left to a later judgement.

**Registration and capability-aware resolution**

- **FR-045**: A package MUST register panels through the `scistudio.panels`
  entry-point group. The entry point MUST resolve to one or more panel
  directories inside the package, each in the on-disk form of FR-002. A package
  MUST NOT need to construct a Python object to register a panel. The existing
  `scistudio.previewers` group and its `get_previewers()` factory MUST continue
  to be discovered for the duration of the migration (FR-020, FR-042).
- **FR-046**: The user library and the open project MUST register a panel by
  containing its directory under their panels root. A directory added, changed,
  or removed MUST take effect after a registry rebuild, and the rebuild endpoint
  of FR-023 MUST be the one way to trigger it. The project's default-panel
  declaration, `.scistudio/previewers.json` today, MUST be carried over under
  the panel naming with its current behaviour.
- **FR-047**: A panel's declaration MAY name a Python provider that windows
  data of its target types. When it does not, the host MUST serve the panel's
  windowed reads from the shared bounded data-access layer. When it does, the
  provider MUST be resolved from the tier the panel was discovered in, and a
  provider that fails to import MUST be a discovery diagnostic naming the panel
  rather than a load failure at mount.
- **FR-048**: Every request to open a panel MUST state the capability it
  requires, displaying or producing. Resolution by data type MUST filter the
  candidates to those declaring at least the required capability before the
  routing ladder and the user choice apply. A producing panel satisfies a
  displaying request (FR-006).
- **FR-049**: The per-type user choice MUST be recorded per type and per
  required capability, so that the panel a person prefers for looking at a
  frame and the one they prefer for producing from it can differ. When a
  producing request finds no producing panel for the type, resolution MUST fall
  back to the displaying resolution and the host MUST mount the result with no
  outbound path.
- **FR-050**: A panel declared on a block class (FR-017) MUST declare the
  producing capability. The check MUST happen when the block is discovered,
  with a diagnostic naming the block and the panel, rather than when the block
  first pauses.
- **FR-051**: The existing free-form `capabilities` tuple on a previewer
  specification, which carries feature tags such as table and sort, MUST be
  renamed `features` in the rename commit of FR-039, so that the word
  capability names only the declared displaying or producing capability.

### Key Entities

- **PanelManifest** — the declaration a panel carries, whether it is read from a
  declaration file on disk or declared on a block class. Attributes: panel id,
  display name, target types, declared capability, entry document name, API
  version, optional provider reference (FR-047). Relationships: names one
  PanelDocument; is produced by all four tiers; is the type that moves from the
  block layer into core.
- **PanelCapability** — a closed set of two members, displaying and producing,
  declared by a PanelManifest and resolved before load. Relationships: determines
  which outbound message types the host grants a mounted panel.
- **PanelDocument** — the self-contained entry document a panel directory
  contains, served through the asset route and mounted in a sandboxed frame.
  Relationships: named by exactly one PanelManifest; addressed by one URL whose
  shape is identical across the four tiers.
- **PanelTier** — where a panel was discovered: core, package, user library, or
  project. Attributes: a root directory and an ordering position; the package
  tier's roots come from the entry-point group (FR-045). Relationships:
  determines shadowing under FR-019 and the write target under FR-025.
- **PanelRequest** — what asks for a panel: a target, addressed by data type or
  by block, and the capability the request requires. Relationships: input to
  resolution under FR-048; selects the user choice under FR-049; determines the
  outbound path the host grants under FR-011 and FR-012.
- **PanelOverride** — a copy of a read-only panel written into the project so it
  can be edited. Attributes: the id it keeps, the tier it shadows.
  Relationships: created by FR-026, made effective by FR-019, deleted by FR-029.
- **PanelBinding** — what a producing panel is bound to when it runs in a
  session: a mapping from variable name to its type and current snapshot.
  Relationships: supplied across the message contract under FR-013; its
  consumers are specified by the explore-session spec, not here.

## 4. Implementation Plan

### 4.1 Technical Approach

**Where the contract lives.** The manifest, the capability declaration, and the
version constant go into the core layer as a new module. The reason is a
layering constraint rather than a preference: the block layer declares a
manifest on a block class, the panel subsystem serves and validates manifests
from above it, and the API layer routes them from above that. SciStudio has
answered this question once already — `core/origins.py` records that it sits in
core because its consumers span layers and no layer above core may be imported
by the others, which is also why the tier roots live in `core/dropins.py`
instead of inside the block or type registries. Leaving the shared type inside
the panel subsystem would force the block layer to import upward, and the
pressure to relieve that produces a second manifest type in the block layer,
which is the duplication this whole change exists to remove.

**The mounting mechanism is new, not merged.** This is the largest single risk
in the work and the reason the sequence in §4.3 puts it early. Both current
paths import an ES module into the application's React tree; the new one creates
a sandboxed frame, serves a self-contained document into it, and speaks to it
by message passing. Nothing about the existing loaders is reusable except the
manifest validation and the same-origin check. The frame boundary is what makes
the failure story in Story 3 tractable — a runaway loop, a leaked global
handler, or a thrown exception stays inside the panel that caused it — and it is
also what makes hot reload clean, because tearing down a frame and building a
new one leaves no cached module behind, where reloading an ES module would
require cache-busting the URL and would silently serve stale code when that was
forgotten.

**The sandbox is one permission.** The frame is granted script execution
and nothing else. Granting same-origin access as well would let a panel's
script walk into the parent document, read the application's storage, and
call the API with the person's credentials, which is the failure the frame
exists to prevent; every other permission has no legitimate use in a panel.
The cost is that the frame runs at an opaque origin: it cannot fetch from the
application except where the application says so, which is the asset route
and only the asset route, and messages between host and frame cannot rely on
an origin check, so each mount issues a token that every message carries.

**The two resolutions stay as they are.** Routing by data type keeps the ladder
and the per-type user choice. Routing by block keeps the manifest on the block
class. These are two different questions with two correct answers, and the
unification is of the loading, versioning, serving, and failure behaviour that
neither of them had a reason to own separately. Expressing the difference as a
parameter of one implementation is the rule ADR-054 §9.1 states; expressing it
as two implementations is the outcome it forbids.

**Registration is a directory; resolution is a request.** A panel is
registered by existing as a directory in a tier: a package points its entry
point at the directories it ships, and the user library and the project contain
theirs. No tier constructs a Python object to register a panel, which is what
lets the agent and the person register one by writing files. Python enters only
when a panel names a provider for a type the shared data-access layer cannot
window, and that reference is resolved from the panel's own tier. Opening a
panel is a request that states what it needs: a target and a capability. The
capability filters the candidates before the ladder and the user choice see
them, so the same type can resolve to a plain table in the workflow preview and
to a table editor in a session without the two choices fighting over one slot.
Without the filter, a person who chose a displaying panel as their default for
frames would find a session unable to produce from a frame at all.

**One asset route, four roots.** The route resolves a panel id to a root
directory, joins the requested file, confirms the result has not escaped the
root, and checks the suffix against one allowlist. Only the root differs by
tier. Placing the built-in documents on disk under the panel subsystem rather
than in the frontend bundle is what makes the four tiers the same shape, and it
is the precondition for Story 2: copying a built-in panel into a project is a
directory copy, where extracting a compiled component would not be possible at
all.

**The frontend's routing table disappears.** The backend router has already
chosen a panel by the time the host has a response to render, so the host mounts
what it was told to mount. The only case that needed a local mapping was the
fallback, and that is answered by having the backend name the fallback panel in
the response it is already sending. This deletes a duplicated routing decision
rather than moving it.

**Editing is copy-on-write over the existing tier ordering.** No new mechanism is
required: writing a copy into the project and letting the ordering shadow the
original is what the tiers already do. What is new is the surface — reading a
panel's source, writing it back, and reverting — and the reload that follows a
save. The reload trigger must fire for files the agent writes, which is not
automatic: the repository already contains watcher behaviour that suppresses
files written by the product itself, and an agent-written panel must not fall
into that category. This is called out in the sequence as a task with its own
verification rather than left as an implementation detail.

**The rename runs first.** ADR-054 §9.3 requires the rename to be a separate
commit from the behaviour change and requires both to land in the same release;
it does not fix their order. Running the rename first is the cheaper order,
because it touches roughly fifty backend files and fifty frontend files and
would otherwise conflict with every behavioural step ahead of it. Every later
step is then written against the final vocabulary, and no step has to be
rewritten when the rename lands.

**Compatibility is bounded at the point it is introduced.** The shim exists so
that a published package can cross a mounting-mechanism change without its users
losing their previews. It wraps the old module form and grants nothing new. Its
removal condition is written into the ADR-048 addendum in the same change that
introduces it, because a shim whose removal is left to a later judgement becomes
a second implementation with a friendly name.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `docs/specs/adr-054-panel-contract.md` | create | This spec. |
| `docs/adr/ADR-048-addendum*.md` | create | Contract change, governance transfer, and the shim's removal condition (FR-044). |
| `docs/adr/ADR-051-addendum2.md` | create | The panel-side half of the same contract change. |
| `src/scistudio/core/panels.py` | create | The shared contract (FR-001). |
| `src/scistudio/panels/**` | create | The renamed subsystem plus the on-disk built-in panel documents (FR-033); directory registration, the entry-point group, the optional provider, and capability-aware resolution (FR-045 to FR-050). |
| `src/scistudio/previewers/**` | delete | Renamed into `panels/` (FR-038). |
| `src/scistudio/api/routes/panels.py` | create | The merged asset route and the editing endpoints (FR-021, FR-024 to FR-029). |
| `src/scistudio/api/routes/blocks.py` | modify | Its panel asset route folds into the merged one (FR-021, FR-022). |
| `src/scistudio/api/routes/data.py` | modify | Listing, rebuild, and per-type choice endpoints move under panel naming (FR-023). |
| `src/scistudio/api/schemas.py` | modify | Response shapes gain the fallback panel id (FR-015) and follow the rename. |
| `src/scistudio/blocks/base/interactive.py` | modify | The manifest type moves to core; this module imports it (FR-001). |
| `src/scistudio/core/dropins.py` | modify | Panel tier roots for the user library and the project (FR-018), keeping the previewer roots for the migration (FR-020). |
| `src/scistudio/core/entry_points.py` | modify | The `scistudio.panels` entry-point group alongside the retained previewer group (FR-045). |
| `frontend/src/panels/**` | create | The frame host, the merged host API, the single loader, and the state hook (FR-007 to FR-014, FR-031). |
| `frontend/src/components/DataPreview.parts/dynamicPreviewer.ts` | delete | Superseded by the single loader (FR-039, Story 5). |
| `frontend/src/components/DataPreview.parts/previewerHostApi.ts` | delete | Superseded by the merged host API. |
| `frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts` | delete | Superseded by the single loader. |
| `frontend/src/App.parts/InteractiveModals.parts/DynamicPanel.tsx` | delete | Superseded by the single frame host. |
| `frontend/src/components/DataPreview.parts/coreViewers.tsx` | modify | Its viewers become panel documents; its error surface and diagnostics banner remain as host chrome (FR-033, FR-035, FR-036). |
| `frontend/src/components/DataPreview.parts/PlotViewer.tsx` | delete | Becomes a panel document. |
| `frontend/src/components/DataPreview.parts/PreviewHost.tsx` | modify | Merges with the panel host. |
| `frontend/src/App.parts/InteractiveModals.tsx` | modify | Its built-in panel registry is replaced by tier resolution (FR-037). |
| `frontend/src/components/PreviewerPalette*` | modify | Follows the rename. |
| `frontend/src/components/promotion/**` | modify | The promotable kind follows the rename. |
| `frontend/src/store/preview*` | modify | Follows the rename. |
| `tests/previewers/**` | delete | Moves to `tests/panels/**`. |
| `tests/panels/**` | create | The contract, capability gate, tiers, editing, asset route, built-in panels, and shim. |
| `tests/architecture/test_layer_deps.py` | modify | Subsystem enumeration (FR-040). |
| `tests/adr052_contract/**` | modify | Frozen public-symbol inventory and stability markers (FR-041). |
| `tests/api/test_previewers.py`, `test_previewer_discovery.py`, `test_interactive_panels.py` | modify | Follow the merged route and naming. |
| `src/scistudio/tutorials/core/what-is-a-type/assets/code/review_labels.py` | modify | Carries a hard-coded panel URL that the merged route changes. |

### 4.3 Implementation Sequence

| Task | Title | Story | Depends on | Verification |
|---|---|---|---|---|
| T-001 | Rename the subsystem and its vocabulary, in one commit that changes no behaviour | US5 | — | Full suite green before and after; the diff contains no logic change |
| T-002 | Move the contract into the core layer | US1 | T-001 | Layer dependency test; the block layer imports downward only |
| T-003 | Define the on-disk panel form and discover it across four tiers | US1 | T-002 | Tier resolution and shadowing tests |
| T-004 | Merge the asset route, retaining the two existing routes | US1, US4 | T-003 | Path confinement and suffix allowlist tests against all four roots |
| T-005 | Build the frame host and the message contract | US1 | T-002 | Handshake, version gate, and bounded-wait tests |
| T-006 | Enforce the capability gate in the host | US1 | T-005 | A displaying panel is granted no outbound type |
| T-007 | Replace both loaders with the single one and delete the retired modules | US5 | T-005, T-006 | One loader and one version constant remain |
| T-008 | Name the fallback panel in the backend response and delete the frontend dispatch | US3 | T-004, T-007 | Broken panel still shows data through the named fallback |
| T-009 | Rewrite the eleven built-in panels as panel documents | US2, US3 | T-003, T-007 | Each renders its provider's response; each is shadowable |
| T-010 | Add reading, writing, copy-on-write, and revert | US2, US3 | T-003, T-009 | Save target by tier; copy keeps id; revert deletes the copy |
| T-011 | Add hot reload and the optional state hook | US2 | T-010 | Reload after save without reopening; agent-written files trigger it |
| T-012 | Add the compatibility shim | US4 | T-007 | An old-form previewer renders and gains no new capability |
| T-013 | Update the layer enumeration and the frozen symbol inventory | US5 | T-001, T-002 | Architecture and contract tests pass |
| T-014 | Write the ADR-048 and ADR-051 addenda | US4, US5 | T-012 | The removal condition is stated, not deferred |
| T-015 | Add the entry-point group, directory registration, and the optional provider | US1, US4 | T-003 | A fixture package registers a panel with a directory and no Python object; a project directory takes effect after rebuild; a broken provider is a discovery diagnostic |
| T-016 | Make resolution capability-aware and record the user choice per type and capability | US1 | T-003, T-006 | A producing request skips displaying-only panels; falls back to display with no outbound path; a block declaring a displaying-only panel is refused at discovery |

### 4.4 Verification Plan

Automated coverage is organised by the property being defended rather than by
module. The capability gate is tested from the host's side, by confirming a
displaying panel is never granted an outbound message type, because a test that
only checks the declaration would pass against an implementation that trusts the
panel. Path confinement is tested against all four tier roots, since the merged
route's single check is the only thing standing between a panel id and an
arbitrary filesystem read. The failure path is tested with genuinely broken
documents rather than mocked failures, covering a malformed document, a version
mismatch, and a panel that never answers the handshake.

The migration is verified in both directions: a package built against the old
module form renders through the shim and is confirmed to gain no new capability,
and a panel written against the new contract is confirmed to need no shim.

The rename commit is verified by running the full suite before and after and
confirming the diff contains no behavioural change, which is the property that
makes it reviewable at its size.

Manual verification covers the two things a test cannot settle: that a person
can edit a built-in panel and see the change without reopening anything, and
that a panel edited by the agent triggers the same reload as a panel edited by
hand.

Lint, type, and format checks run as usual. The architecture drift audit and the
frozen public-symbol inventory are expected to fail until T-013, which is why it
is sequenced rather than left to the end.

### 4.5 Risks And Rollback

**The mounting mechanism is new.** Message passing replaces direct calls for
every panel at once, and the eleven built-in panels are rewritten against a
mechanism that has no production history in this codebase. The mitigation is
ordering: the frame host and its message contract land before any built-in panel
is rewritten, and the plot panel — a single image and a format control — is
rewritten first as the simplest complete exercise of the path.

**The rename is large and mechanical.** Roughly a hundred files change names
without changing behaviour. The mitigation is that it lands first, alone, with
the full suite green on both sides, so that a later failure is attributable to
behaviour rather than to the rename.

**The frozen public-symbol inventory and the stability markers.** Renaming public
symbols is indistinguishable from removing them and adding new ones, so the
inventory and the markers must be updated deliberately. The risk is silently
resetting a stability guarantee that packages depend on; the mitigation is that
FR-041 requires the spec to state how the renamed symbols' markers are derived
rather than leaving it to the implementer.

**Packages outside this repository.** The imaging package ships previewers
written against the old form. The shim is what keeps their users working, and
its removal condition is written down in the same change that introduces it.

**Rollback.** Each task in §4.3 is independently revertible up to T-007, after
which the two old loaders no longer exist and rollback means reverting the merge
commit. The compatibility shim is the escape hatch for anything discovered after
release: a package that breaks against the new contract keeps rendering through
the shim while the defect is fixed.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: Exactly one panel API version constant exists in the tree, and
  exactly one loader. Measured by searching the tree for both.
- **SC-002**: The two retired loader modules and the retired host API module do
  not exist. Measured by their absence.
- **SC-003**: All eleven built-in panels are mounted through the frame
  mechanism. Measured by each having a panel directory and no built-in panel
  rendering through a compiled-in component.
- **SC-004**: A person can copy a built-in panel into a project, edit it, save,
  and see the mounted panel redraw without reopening the view. Measured by
  manual verification against the built-in table panel.
- **SC-005**: An edit made by the agent triggers the same reload as an edit made
  by hand. Measured by manual verification.
- **SC-006**: Every panel load failure path — malformed document, version
  mismatch, unanswered handshake — leaves the data visible and produces a
  diagnostic naming the panel and the failure. Measured by tests covering all
  three.
- **SC-007**: A displaying panel is granted no outbound message type, verified
  from the host's side rather than from the declaration. Measured by test.
- **SC-008**: The merged asset route confines paths and enforces the suffix
  allowlist identically for all four tier roots. Measured by test against each
  root.
- **SC-009**: A previewer built against the ADR-048 module form renders through
  the shim and receives neither variable bindings nor an outbound path. Measured
  by test.
- **SC-010**: The frontend contains no mapping from a response kind to a panel.
  Measured by the absence of the dispatch and the presence of the backend-named
  fallback in the response schema.
- **SC-011**: The rename commit changes no behaviour. Measured by the full suite
  passing on both sides of it with no test modified in that commit.
- **SC-012**: The architecture layer test, the architecture drift audit, and the
  frozen public-symbol inventory all pass. Measured by CI.
- **SC-013**: The shim's removal condition is stated in the ADR-048 addendum.
  Measured by reading it.
- **SC-014**: A package registers a panel through the entry-point group with a
  directory and no Python object, and a project registers one by containing a
  directory. Measured by a fixture package and a fixture project.
- **SC-015**: A producing request for a type with both kinds of panel mounts
  the producing one; a producing request for a type with only displaying
  panels mounts the displaying one with no outbound path. Measured by test.
- **SC-016**: A block declaring a displaying-only panel is refused at
  discovery with a diagnostic naming the block. Measured by test.

## 6. Assumptions

- **A-001**: The rename runs before the behavioural work rather than after it.
  ADR-054 §9.3 requires the two to be separate commits in the same release and
  does not fix their order; running the rename first avoids conflicting with
  every behavioural step. _Source: inferred._
- **A-002**: A panel bound to several variables is specified here because it is
  part of the message contract, while what consumes those bindings is specified
  by the explore-session spec. _Source: adr._
- **A-003**: Built-in panel documents live under the panel subsystem in the
  Python package rather than in the frontend bundle, so that all four tiers have
  the same shape on disk and copying a built-in panel is a directory copy.
  _Source: owner._
- **A-004**: Built-in panels that render similar structures each carry their own
  rendering code. The shared behaviour is already the host API; what duplicates
  is the part a person forking a panel most wants to change, and a shared
  runtime import would break the property that a panel document can be opened
  directly in a browser to see whether it works. _Source: owner._
- **A-005**: A plot moves across unchanged as a panel resolved by type and
  declaring only the displaying capability. Its Python side is untouched, and
  giving it the producing capability is deferred to issue 2212. _Source: owner._
- **A-006**: The per-type user choice and the routing ladder are carried over
  without redesign. This spec changes what is mounted and how, not which panel
  is chosen. _Source: spec._
- **A-007**: The watcher behaviour that suppresses files written by the product
  itself must be confirmed not to suppress agent-written panel files. This is
  stated as an assumption because it has not been verified in the code, and
  T-011 carries its verification. _Source: inferred._
- **A-008**: The asset route sends no cross-origin read headers today; it
  gains them for its own responses only, so a panel at an opaque origin can
  fetch assets and nothing else. _Source: inferred._
- **A-009**: The compatibility shim covers the previewer module form only. No
  equivalent shim is provided for the interactive-panel module form, because its
  only consumers are in this repository and the tutorial asset that carries a
  hard-coded panel URL is updated as part of §4.2. _Source: inferred._
- **A-010**: A panel needs no Python by default, because the shared
  data-access layer windows every core type. A package type the layer cannot
  window ships a provider named in the panel's declaration. _Source: adr._
