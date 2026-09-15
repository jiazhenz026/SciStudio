---
spec_id: adr-054-panels
title: "ADR-054 Spec — Panels: Mechanism, Core Migration, And Authoring Docs"
status: Draft
feature_branch: docs/2285-adr-054-panel
created: 2026-09-11
input: "Owner request (issue #2287): one implementation spec for ADR-054 (issue #2285, PR #2286, implementation tracked in #2288) covering, in dependency order, (1) the panel mechanism, (2) rewriting the core previewers and the built-in interactive windows as panels, and (3) developer docs and embedded-agent skills. Owner additions: the preview panel's maximize button opens the preview as a main-stage preview tab and must keep working; the post-audit decisions recorded in ADR-054 (interactive panels receive only the prepare_prompt view, per-mount tokens for panel files, React viewers kept for Python-only legacy previewers until 0.6, a host open service for collection and composite drill-down, and a CDN allowlist)."
owners:
  - "@jiazhenz026"
related_adrs:
  - 54
  - 48
  - 49
  - 51
  - 52
  - 53
  - 55
related_specs:
  - adr-048-preview-system
  - adr-051-interactive-blocks
  - adr-052-public-api-surface
  - adr-054-miniapp
  - adr-055-enterprise-support
  - adr-055-prefix-independence
scope:
  in:
    - "Phase A — the panel mechanism: `panel.json` schema and validation, discovery at the core, package, user, and project tiers, preview routing over panels and legacy previewers as one candidate set, the panel context service, the generic read route and the read-layer extensions, per-mount tokens and token-scoped serving of panel files, the SDK, and the library set, the sandboxed frame host and channel-bound bridge, the SDK with the `open` and `save` services, the content policy and CDN allowlist, backend refusal of opaque-origin state changes and the CORS restriction, the interactive-block panel checks, ADR-049 validator rows, and deprecation diagnostics for both legacy previewer forms."
    - "Phase A — keeping the maximize-to-preview-tab flow, Data-tree open, the preview tab's type-change chip, and collection and composite drill-down working with panels."
    - "Phase B — rewriting the nine core previewer views and the two built-in interactive windows as core-tier panels, deleting the two compiled interactive windows, and restricting the compiled core viewers to legacy envelopes."
    - "Phase C — a panel authoring guide, a legacy migration guide, the embedded-agent panel skill, agent reference and spec updates, the ADR-049 and ADR-055 document notes, and proposed ARCHITECTURE.md text."
  out:
    - "Editing data from a preview, and the notebook context and `sync` operation (ADR-054 §9; tracked in #2288)."
    - "Per-panel Python providers for reads (ADR-054 §5; tracked in #2288). Panel Python (`panel.py`) and the `miniapp` context are specified separately, as Phase D, in `adr-054-miniapp`."
    - "Interactive panels reading the block's inputs; they receive only the `prepare_prompt` view (ADR-054 §2)."
    - "Editing a panel's source inside the application (tracked in #2288)."
    - "Removing the legacy previewer forms, the compiled core viewers kept for them, and the backend provider and envelope path; that happens in 0.6 (tracked in #2288)."
    - "Migrating the external imaging, spectroscopy, LCMS, and package-template repositories; each migrates in its own repository (tracked in #2288)."
    - "Rewriting the tutorial copy of \"What Is A Type\"; the copy is owner-authored (FR-049)."
    - "Any change to the ADR-051 runtime, its `interactive_prompt` event, interaction memory, or the embedded agent's MCP preview tools (`src/scistudio/ai/agent/mcp/tools_inspection/_preview.py`, which read data independently of the preview service)."
governs:
  modules:
    - scistudio.panels
    - scistudio.api.routes.panels
    - scistudio.previewers
    - scistudio.blocks.base.interactive
    - scistudio.blocks.registry
    - scistudio.api.routes.data
    - scistudio.api.routes.blocks
    - scistudio.api.app
    - scistudio.core.dropins
  contracts:
    - scistudio.previewers.models.PreviewerSpec
    - scistudio.previewers.models.FrontendManifest
    - scistudio.previewers.data_access.PreviewDataAccess
    - scistudio.blocks.base.interactive.PanelManifest
    - scistudio.blocks.base.interactive.InteractiveMixin
  entry_points:
    - scistudio.panels
    - scistudio.previewers
  files:
    - src/scistudio/panels/**
    - src/scistudio/api/routes/panels.py
    - frontend/src/panels/**
    - docs/specs/adr-054-panels.md
    - docs/specs/adr-048-preview-system.md
    - docs/specs/adr-051-interactive-blocks.md
    - docs/specs/adr-055-enterprise-support.md
    - docs/adr/ADR-049.md
    - docs/package-development/previewers.md
    - docs/package-development/index.md
    - docs/package-development/architecture.md
    - docs/package-development/blocks.md
    - docs/package-development/publishing.md
    - src/scistudio/previewers/registry.py
    - src/scistudio/previewers/router.py
    - src/scistudio/previewers/choices.py
    - src/scistudio/previewers/project.py
    - src/scistudio/previewers/data_access.py
    - src/scistudio/previewers/assets.py
    - src/scistudio/previewers/fallbacks.py
    - src/scistudio/core/dropins.py
    - src/scistudio/blocks/base/interactive.py
    - src/scistudio/blocks/registry/_capability.py
    - src/scistudio/api/app.py
    - src/scistudio/api/routes/data.py
    - src/scistudio/api/routes/blocks.py
    - src/scistudio/_agent_reference/block-contract.md
    - src/scistudio/_agent_reference/public-api.md
    - src/scistudio/_agent_reference/package-discovery.md
    - src/scistudio/_skills/scistudio/SKILL.md
    - src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md
    - src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md
    - src/scistudio/agent_provisioning/skills.py
    - src/scistudio/agent_provisioning/_orchestrate.py
    - src/scistudio/_skills/scistudio/scistudio-use-gui/SKILL.md
    - src/scistudio/_skills/scistudio/scistudio-write-panel/SKILL.md
    - src/scistudio/tutorials/core/what-is-a-type/**
    - scripts/audit/check_package_contract_tables.py
    - frontend/src/components/DataPreview.tsx
    - frontend/src/components/DataPreview.parts/PreviewHost.tsx
    - frontend/src/components/DataPreview.parts/dynamicPreviewer.ts
    - frontend/src/components/DataPreview.parts/previewerHostApi.ts
    - frontend/src/components/DataPreview.parts/coreViewers.tsx
    - frontend/src/components/DataPreview.parts/TableViewer.tsx
    - frontend/src/components/DataPreview.parts/PlotViewer.tsx
    - frontend/src/App.parts/InteractiveModals.tsx
    - frontend/src/App.parts/InteractiveModals.parts/DynamicPanel.tsx
    - frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts
    - frontend/src/App.parts/ProjectWorkspace.tsx
    - frontend/src/store/tabSlice.parts/previewTabActions.ts
    - frontend/src/components/DataRouterModal.tsx
    - frontend/src/components/PairEditorModal.tsx
  excludes:
    - docs/user/reference/**
    - docs/user/llms.txt
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/package-development/panels.md
  excludes: []
tests:
  - tests/panels/test_panel_descriptor.py
  - tests/panels/test_panel_skill_examples.py
  - tests/ai/test_mcp_tools_qa.py
  - tests/agent_provisioning/test_skills.py
  - tests/agent_provisioning/test_orchestrate.py
  - tests/panels/test_panel_registry.py
  - tests/panels/test_panel_routing.py
  - tests/panels/test_panel_contexts.py
  - tests/panels/test_panel_read.py
  - tests/panels/test_panel_tokens.py
  - tests/api/test_panel_routes.py
  - tests/api/test_panel_security.py
  - tests/api/test_app.py
  - tests/api/test_interactive_panels.py
  - tests/blocks/test_interactive_mixin.py
  - tests/previewers/test_preview_routing.py
  - tests/previewers/test_preview_data_access.py
  - frontend/src/panels/PanelFrame.test.tsx
  - frontend/src/panels/bridge.test.ts
  - frontend/src/components/DataPreview.parts/PreviewHost.test.tsx
acceptance_source: adr
language_source: en
---

# ADR-054 Spec — Panels: Mechanism, Core Migration, And Authoring Docs

## 1. Change Summary

This spec implements ADR-054. It came from a manual owner request tracked as
issue #2287, and it is the implementation spec for Phases A to C of that ADR;
Phase D, panel Python and MiniApps, is specified in `adr-054-miniapp`. The
implementation itself is tracked in #2288.

ADR-054 makes every surface for previewing data or deciding on it a **panel**: a
user-customizable HTML page, mounted in a sandboxed frame, that reads the data it
needs, writes the user's answer back where its context allows, and — in a
notebook context a later ADR may define — syncs one kernel variable. The ADR
fixed the model and left the contracts to this spec: the `panel.json` schema, the
SDK messages and channel, the read shapes and budgets, the token-scoped routes
and content policy, the library set and CDN allowlist, tier conflicts, and theme
tokens. The spec follows ADR-054 as revised after its no-context audit.

The work lands in three phases, in dependency order, each as one or more PRs:

| Phase | Delivers | Depends on |
|---|---|---|
| A. Mechanism | Backend `scistudio.panels` package and routes, read-layer extensions, tokens, security controls, frontend panel host and bridge, the SDK, interactive checks, validator rows, legacy deprecation | ADR-054 |
| B. Core migration | The nine core previewers and the two built-in interactive windows rewritten as core-tier panels; the two compiled interactive windows deleted; the compiled core viewers restricted to legacy envelopes | Phase A |
| C. Docs and skills | Panel authoring guide, legacy migration guide, embedded-agent panel skill, agent reference and spec updates, ADR-049 and ADR-055 notes, proposed ARCHITECTURE.md text | Phases A and B |
| D. Panel Python and MiniApps | Specified in `adr-054-miniapp`: `panel.py` and `call`, the `miniapp` context, and the MiniApp workspace, entries, promotion, and conversion | Phase A |

Four existing user flows are carried across explicitly because they depend on how
a preview is mounted: the preview panel's maximize button, which opens the
current preview as a transient main-stage preview tab (#2112); opening a data
file from the Data tree into that tab, with its type-change chip; and drilling
from a collection output's item cards, or a composite object's slots, into the
item's or slot's own view and back.

What does not change: previewers stay read-only; ADR-051's runtime, its
`interactive_prompt` event, and ADR-051 Addendum 1 stay as they are; the
interactive window stays a full-screen modal; the ADR-048 §3 routing ladder,
ambiguity rule, and per-type user choice carry over. Both legacy previewer forms
— `mount(container, host)` modules and Python-only previewers — keep working,
deprecated, through 0.5.x.

### Phase A Owner Decisions (2026-09-11)

Phase A preserves the existing Previewers sidebar entry and includes panel
candidates in that catalog. Phase D (#2354) performs the MiniApps/All Previewers
transition. SDK sample mode (FR-046) belongs to A; it does not require an
intermediate Panels tab, card sample-opening flow, or directory promotion.

The existing ADR-055 identity and prefix seams apply now: verify the default and
replacement fake guards at root and proxy-prefixed mounts. Fake-guard evidence
is not real JupyterHub verification.

TODO(#2294): Replace the temporary compiled windows for
`core.interactive.data_router` and `core.interactive.pair_editor` with core-tier
HTML panels in Phase B; remove their explicit compatibility exceptions then.
Out of scope per the Phase A/B split; follow-up:
https://github.com/jiazhenz026/SciStudio/issues/2294.
Other missing ids and context mismatches remain errors.

Owner clarification preserves the existing refusal to override core ids:
FR-002's `core.*` reservation remains strict for non-core tiers. A customized
core preview uses a new non-core id and the same concrete type, selected through
the routing ladder or per-type user choice. Same-id shadowing applies only to
non-core ids; this does not expand the implementation's override behavior.

## 2. User Scenarios & Testing

### User Story 1 - A custom preview panel renders for its type (Priority: P1)

A user, or the agent on their behalf, writes a folder with `panel.json` and
`index.html` into `<project>/panels/`, declaring `"contexts": ["preview"]` and
`"types": ["Image"]`. Selecting an `Image` output shows that page in the preview
panel, reading plane data through the SDK.

**Why this priority**: This is the customization the ADR exists for.

**Independent Test**: Place a fixture panel in a temporary project, reload, open
a preview of an `Image` output, and assert the frame loads the panel's entry file
through a token-scoped URL and that a `read` of `array.plane` returns the stored
values.

**Acceptance Scenarios**:

1. **Given** a valid project-tier panel for `Image`, **When** the user previews an
   `Image` output, **Then** the panel is chosen over package and core panels for
   `Image` and mounted in a frame whose `sandbox` is exactly `allow-scripts`.
2. **Given** the mounted panel calls `scistudio.read("array.plane", {slice: 3})`,
   **When** the host forwards it, **Then** the panel receives the plane's values
   as binary with dtype, shape, and truncation flags.
3. **Given** the preview context, **When** the panel looks for `writeBack`,
   **Then** the SDK does not expose it and a raw `writeBack` message is refused.

### User Story 2 - An interactive block opens its panel and returns one decision (Priority: P1)

A block declares `interactive_panel = PanelManifest(panel_id="lcms.blank_pick")`
with no `module_url`, and the panel folder declares `"contexts": ["interactive"]`.
When the workflow reaches the block, the modal opens the panel, which receives
the block's `prepare_prompt` view, and the user's confirmation resumes the block.

**Why this priority**: The second context ADR-054 unifies; the compute phase must
receive the decision exactly as it does today.

**Independent Test**: Run a fixture interactive block against a fixture panel
whose page writes back a fixed value, and assert the compute phase receives that
value in `interactive_response` and lineage records it.

**Acceptance Scenarios**:

1. **Given** the block pauses, **When** the modal mounts the panel, **Then** the
   panel's `input` is the event's `panel_payload`, and every `read` is refused.
2. **Given** the panel calls `writeBack(value)`, **When** the host sends it,
   **Then** the existing `interactive_complete` message carries it, the modal
   closes, and a second `writeBack` is refused.
3. **Given** the user presses the host's Cancel, **When** the modal closes,
   **Then** the existing `cancel_block` path runs and the panel context closes.

### User Story 3 - A faulty or hostile page cannot reach the application or change backend state (Priority: P1)

A panel's script tries to call `/api/...`, send a body-less `POST` to a
state-changing route, read `window.parent.document`, message another panel,
navigate its frame away, or loop forever.

**Why this priority**: These controls are what make the permission model and the
read-only previewer real (ADR-054 §4).

**Independent Test**: A fixture panel attempts each action; assert every attempt
fails or is torn down, the backend records no state change, and the host stays
responsive enough to show an error and remount (the loop case is measured on the
supported Electron build and browsers and recorded).

**Acceptance Scenarios**:

1. **Given** a mounted panel, **When** it calls `fetch` to any URL, **Then** the
   content policy blocks it.
2. **Given** a mounted panel, **When** it triggers a `POST /api/blocks/reload`
   by a form-less or image-less route (for example a no-cors request that slipped
   past a misconfigured policy), **Then** the backend refuses it because its
   origin is opaque.
3. **Given** a mounted panel, **When** it touches `window.parent.document` or the
   host's storage, **Then** the browser throws.
4. **Given** a mounted panel, **When** it navigates its own frame to another
   address, **Then** the host disposes the frame and closes its context.
5. **Given** two mounted panels, **When** one posts a message to the other,
   **Then** the receiving SDK ignores it because it listens only to its channel.

### User Story 4 - Maximize, Data-tree open, type change, and drill-down keep working (Priority: P1)

The user maximizes a preview, opens a data file from the Data tree, changes the
type a file was opened as, or clicks an item card of a collection output.

**Why this priority**: These flows mount previews outside the simple case
(#2112) or navigate within them; a panel host that handles only one mount breaks
them.

**Independent Test**: With a panel that reports a view state, maximize and
assert the preview tab mounts the same panel for the same target with that view
state; open a file from the Data tree and change its type, and assert the tab
re-resolves; open a collection output, click an item card, and assert the item's
panel mounts with a working back action.

**Acceptance Scenarios**:

1. **Given** a preview panel showing slice 3 at 2× zoom, **When** the user clicks
   maximize, **Then** a preview tab opens on the same target with the same panel
   id, and the panel receives the view state it last reported.
2. **Given** a panel that reports no view state, **When** the user maximizes,
   **Then** the tab opens with the entry's `initialQuery`, as today.
3. **Given** a preview tab, **When** focus moves to another tab, **Then** the tab
   is dropped as today and its frame and panel context are disposed.
4. **Given** a file opened from the Data tree as `Image`, **When** the user
   changes it to `Array` with the tab's type chip, **Then** the tab re-resolves
   and mounts the panel for `Array`.
5. **Given** a collection output of ten `Image` items, **When** the user clicks
   item 3 in the collection panel, **Then** the host mounts the panel the ladder
   picks for `Image` in the same area, and back returns to the cards.

### User Story 5 - Panels load behind Lab authentication and a user prefix (Priority: P2)

A scientist uses SciStudio through the ADR-055 Lab deployment, where every
request is authenticated by SciStudio's session cookie and the service lives
under a JupyterHub user prefix.

**Why this priority**: Without per-mount tokens a sandboxed page's module
scripts, fonts, and library imports carry no login and fail (ADR-054 §4).

**Independent Test**: Under the prefix-aware test harness with session
authentication enabled, mount a panel that uses a module script, a font, and a
library from the local set; assert all load; assert the same URLs are refused
after the context closes and that the token cannot read an API route.

**Acceptance Scenarios**:

1. **Given** an authenticated user under `/user/alice/scistudio/`, **When** a
   panel mounts, **Then** its entry, relative module imports, fonts, SDK, and
   library files load through the token-scoped path.
2. **Given** a closed context, **When** its token is reused, **Then** every
   request is refused.

### User Story 6 - Built-in previews and windows are panels and work offline (Priority: P2)

Every core preview and both built-in interactive windows are core-tier panels and
render with no network connection.

**Why this priority**: Phase B; it depends on Phase A.

**Independent Test**: For each core panel, run its parity checklist (FR-040)
against a fixture of its kind with the frame's network disabled.

**Acceptance Scenarios**:

1. **Given** a `DataFrame` output, **When** it is previewed, **Then**
   `core.dataframe.basic` pages and sorts it through `table.page`.
2. **Given** a Data Router block pauses, **When** its modal opens, **Then**
   `core.interactive.data_router` renders and returns the same response shape the
   block consumes today.
3. **Given** a PDF plot artifact, **When** it is previewed, **Then**
   `core.plot.basic` renders it with the local PDF renderer.

### User Story 7 - A misdeclared panel is refused with a clear diagnostic (Priority: P2)

An author declares a panel with an empty or unknown `contexts`, a `preview` panel
without `types`, an unserved `api_version` major, or a block that names a panel
not declaring `interactive`; or a project panel shadows an interactive panel's id
without declaring `interactive`.

**Why this priority**: Declaring contexts is what turns a silent hang into an
error (ADR-054 §3).

**Independent Test**: Register one fixture per case and assert the discovery
diagnostic, the block rejection, the open-time refusal, and the matching validator
finding.

**Acceptance Scenarios**:

1. **Given** a block naming a `preview`-only panel, **When** blocks are scanned,
   **Then** the block is refused with a message naming the block, the panel id,
   and the missing context.
2. **Given** a project panel that shadows an interactive panel's id without
   `interactive`, **When** the block pauses, **Then** the modal shows an error
   naming both panels and offers Cancel.

### User Story 8 - Both legacy previewer forms keep working, deprecated, through 0.5.x (Priority: P2)

The imaging and spectroscopy packages' `FrontendManifest` previewers, the LCMS
package's `module_url` panels, and Python-only previewers such as the tutorial's
`image_preview.py` behave as today.

**Why this priority**: The owner chose a transition over a break (ADR-054 §8).

**Independent Test**: Load fixture packages and a fixture project drop-in that use
each legacy form and assert they render and respond as today, each emitting one
deprecation diagnostic naming the replacement.

**Acceptance Scenarios**:

1. **Given** a package `PreviewerSpec` with a `FrontendManifest`, **When** its
   type is previewed, **Then** the legacy loader mounts it and a deprecation
   diagnostic is recorded.
2. **Given** a Python-only project previewer returning a `plot` envelope, **When**
   its type is previewed, **Then** the retained compiled viewer renders it and a
   deprecation diagnostic is recorded.
3. **Given** a legacy previewer and a panel share an id at the same tier, **When**
   routing runs, **Then** the panel is used and the legacy previewer is reported
   as shadowed.

### User Story 9 - A user adjusts a built-in panel by copying it (Priority: P3)

A user copies `core.dataframe.basic` into `<project>/panels/lab.dataframe/`,
changes its descriptor id to `lab.dataframe`, retains the `DataFrame` type claim,
and edits its page.

**Why this priority**: Built-ins become adjustable (ADR-054 §6) through a
separately named panel and the existing type-routing or user-choice mechanism.

**Independent Test**: Copy a core panel directory into a project under a new
non-core id, change its page, reload, and assert the project copy resolves for
the declared type while the original core id remains available.

**Acceptance Scenarios**:

1. **Given** a project panel with a new non-core id and the concrete type of a
   core panel, **When** that type is previewed and resolves to the project panel,
   **Then** the project panel is mounted and the core panel keeps its own id.
2. **Given** a project panel that retains a `core.*` id, **When** discovery runs,
   **Then** the descriptor is refused by FR-002.

### User Story 10 - The agent writes a working panel (Priority: P3)

The embedded agent, asked for a custom view of a data type, writes a panel using
the `scistudio-write-panel` skill.

**Why this priority**: Phase C; most panels are expected to be agent-written.

**Independent Test**: An e2e scenario asks the agent for a panel for a fixture
type; assert the folder validates, references only the local set or allowlisted
CDNs, and renders.

**Acceptance Scenarios**:

1. **Given** the skill is provisioned, **When** the agent writes a panel, **Then**
   the folder passes validation and the agent can check it by opening the page
   directly with `panel.sample.json` (FR-046).

### Edge Cases

- No panel matches the previewed type: `core.base.fallback` is mounted.
- Two panels tie on tier, type specificity, and `priority`: routing returns the
  existing ambiguity error, shown in place of a panel.
- A read exceeds its budget: the result is truncated or sampled and says so
  (ADR-048 §7).
- A panel reads a reference outside its context: the backend answers 403 and the
  SDK rejects the promise with `forbidden`.
- A panel calls `open` on something that is not a child of the target: the host
  refuses it with `forbidden`.
- A panel loads a script from a CDN not on the allowlist: the content policy
  blocks it and the panel fails in its own frame.
- A token expires while a long-open panel requests a new file: the host renews the
  context's token on activity; a closed context's token is never renewed.
- The panel throws after `ready`: the host shows the error with a remount action.
- The theme changes while a panel is mounted: the host sends new tokens.
- The same target is open in the preview panel and a preview tab: each mount has
  its own frame, channel, context, and token.
- The engine restarts during an interactive pause: the pause is lost, as today;
  the panel context closes with the block.
- A plot artifact is a PDF: the browser's built-in PDF viewer does not run inside
  a sandboxed frame, so `core.plot.basic` uses the local PDF renderer.
- An artifact is larger than the inline limit: the panel reads it through
  `artifact.file`: the host consumes a distinct context-target artifact grant and
  transfers bounded bytes to the SDK; the frame uses a local blob URL.
- The panel relies on `localStorage`, `alert`, or pop-ups: unavailable at an
  opaque origin without `allow-modals` or `allow-popups`; the SDK documents this
  and offers view state (FR-018) instead of storage.
- `save` exceeds the size limit: the host refuses it and reports the limit.
- `SCISTUDIO_CORS_ORIGINS` contains `*` or `null`: the backend refuses to start
  and names the setting.

## 3. Requirements

### Functional Requirements

**Phase A — descriptor and discovery**

- **FR-001**: A panel is a directory `<tier root>/<panel-id>/` containing
  `panel.json` and the entry page named by `entry` (default `index.html`), plus
  any static files the page references.
- **FR-002**: `panel.json` MUST be a JSON object with: `id` (required; lowercase
  dotted segments; equal to the directory name; the `core.` prefix is reserved for
  the core tier), `api_version` (required; `"MAJOR.MINOR"`), `contexts`
  (required; non-empty list drawn from `preview` and `interactive`, and
  `miniapp` as specified in `adr-054-miniapp`), `types`
  (required when `contexts` contains `preview`; each entry a registered type name
  or `Collection[<type>]`; the sentinel types `DataObject` and `Collection` are
  allowed only at the core tier), and optional `priority` (integer, default `0`),
  `name`, `description`, `version`, and `entry`.
- **FR-003**: Discovery MUST refuse a panel whose `panel.json` is missing,
  unparsable, violates FR-002, or declares an `api_version` major the host does
  not serve, recording a diagnostic with the panel path and the rule. Unknown keys
  MUST be tolerated with an informational diagnostic.
- **FR-004**: Panels MUST be discovered at four tiers: core
  (`src/scistudio/panels/builtin/`), package (a `scistudio.panels` entry point
  returning panel directory paths), user (`~/.scistudio/panels/`), and project
  (`<project>/panels/`). The user and project roots MUST come from
  `scistudio.core.dropins` alongside the previewer roots, including the tutorial
  library swap (`library_root_for_project`).
- **FR-005**: Discovery MUST run at startup, on the existing reload action
  (`POST /api/previews/reload`), and on project switch, and MUST surface panels
  and their diagnostics in the previewer catalog listing and the Previewers list
  — which `adr-054-miniapp` moves from its sidebar tab to the preview column's
  All Previewers button — with tier, contexts, types, priority, and shadowing.

**Phase A — routing**

- **FR-006**: Preview routing MUST treat panels declaring `preview` and legacy
  `PreviewerSpec` records as one candidate set and apply the ADR-048 §3 ladder —
  exact `Collection[T]` and exact `T` as separate rungs, parent types, the core
  sentinel fallbacks, `priority` within a tier and specificity, and the ambiguity
  error — with the per-type user choice (`previewer-choices.json`) accepting panel
  ids.
- **FR-007**: Panel ids and legacy previewer ids MUST share one namespace. At the
  same tier a panel shadows a legacy previewer with the same id and the legacy
  previewer is reported as shadowed; across tiers the higher tier wins for
  non-core ids. FR-002 continues to refuse `core.*` descriptors outside core.
- **FR-008**: When no candidate matches, routing MUST return `core.base.fallback`.

**Phase A — contexts and reads**

- **FR-009**: `POST /api/panels/contexts` MUST open a context and return
  `context_id`, the resolved panel (`id`, `api_version`), the context kind, the
  operations and services it provides, its `input`, and the token of FR-025. A
  `preview` context is opened from a preview target (`{kind, ref}` as the preview
  session API accepts today) and an optional view state; for a collection target
  its `input` is the item count, item type, and the first page of item references
  with a cursor. An `interactive` context is opened from `{workflow_id, block_id}`
  and the panel id; the service MUST confirm the block is waiting on an
  interactive decision. `DELETE /api/panels/contexts/{context_id}` closes it.
- **FR-010**: A context MUST record the references it authorizes: for `preview`,
  the target and the slots or items reachable from it; for `interactive`, none.
  Contexts are backend runtime state, never persisted, and close with their mount,
  their preview tab, or their block's resume or cancel.
- **FR-011**: `POST /api/panels/contexts/{context_id}/read` MUST accept
  `{ref, op, params}`, refuse with 403 any `ref` the context does not authorize,
  and support:

  | `op` | Result |
  |---|---|
  | `metadata` | type chain, metadata, and shape and dtype where applicable |
  | `table.page` | columns, rows, total, page, sort |
  | `table.xy` | x and y columns as numbers |
  | `array.plane` | values, dtype, shape, axes, slice axes, vmin and vmax of the full plane |
  | `array.tile` | values, dtype, tile bounds |
  | `series.points` | decimated index and values, with the decimation method |
  | `text.chunk` | text, encoding, offset, next offset |
  | `artifact.info` | name, MIME type, size |
  | `artifact.file` | backend: a distinct context-target grant URL, including preview-cache plot artifacts; SDK: artifact metadata, an `ArrayBuffer` in `data`, and a frame-local blob URL in `url` |
  | `composite.slots` | slot names, types, and child references |
  | `collection.items` | a page of item references with types, and the next cursor |

  Every result MUST carry the sampled, truncated, and complete flags of ADR-048
  §7 and respect the panel read budgets, which the Phase A PR sets and records.
- **FR-012**: `array.plane`, `array.tile`, and `series.points` MUST support
  `format: "binary"`, answering `application/octet-stream` with little-endian
  values and dtype, shape, and flags in response headers; the host MUST hand the
  body to the panel as a transferred `ArrayBuffer`. JSON remains available.
- **FR-013**: Read handlers MUST run off the API event loop (ADR-048 §8).
- **FR-014**: `PreviewDataAccess` MUST gain what FR-011 needs and it lacks today:
  decimation for `series_points` (which returns every point), an offset for
  `text_chunk` (which reads only the head), a cursor for `collection_sample`
  (which stops at `max_items`), file access for artifacts over the inline limit,
  and binary output for array reads (tiles are JSON float lists today).

**Phase A — frame, channel, SDK, and services**

- **FR-015**: The host MUST mount every panel in an `iframe` whose `sandbox`
  attribute is exactly `allow-scripts`, whose `referrerpolicy` is `no-referrer`,
  and whose `src` is the panel's token-scoped entry URL.
- **FR-016**: Context creation MUST return an unpredictable 256-bit
  `bootstrap_proof`, stable across renewal. The backend MUST prepend trusted
  bootstrap code before all panel entry markup. That code creates a private
  bootstrap `MessageChannel` and sends `{v: 1, id: "bootstrap", type: "bootstrap",
  proof}` with exactly one port to the parent. The host MUST accept at most one
  bootstrap from the intended iframe with the matching context proof. After the
  first load and a valid bootstrap, the host creates the canonical
  `MessageChannel` and transfers its `init` and one canonical port through the
  retained bootstrap port, never through the iframe's current `contentWindow`.
  The bootstrap forwards initialization once in its original document; a
  replacement document cannot receive it. All subsequent operations use only
  the canonical port. Messages
  have the form `{v: <api major>, id, type, payload}`. Panel-to-host types:
  `ready`, `read`, `writeBack`, `open`, `save`, `viewState`, `resize`,
  `reportError`. Host-to-panel types: `init` (context kind, operations and
  services, `input`, theme tokens, view state, API version, base path), `result`,
  `error`, `theme`, `dispose`. A type the context does not provide MUST be
  answered with `error` code `unsupported`; `sync` is reserved and always answered
  that way in this spec. The SDK MUST ignore messages that do not arrive on its
  port.
- **FR-017**: The SDK MUST be one dependency-free script served at a
  token-scoped, version-major path, exposing `window.scistudio` with `ready()`,
  `context`, `input`, `read(op, params)`, `writeBack(value)` and `open(ref)`
  (defined only where the context provides them), `save({name, mime, data})`,
  `setViewState(state)`, `onTheme(cb)`, `onDispose(cb)`, and
  `reportError(message)`, promise-based where they await the host.
- **FR-018**: A panel MAY report a JSON-safe view state with `setViewState`. The
  host MUST keep the latest one per mount and pass it in `init` when the same
  target is remounted in a preview tab.
- **FR-019**: The host MUST provide operations per ADR-054 §2: `preview` provides
  `read` and `open`; `interactive` provides one `writeBack`. The backend MUST
  independently refuse reads outside the context (FR-011) and accept an
  interactive decision only for the block its context was opened for.
- **FR-020**: `open(ref)` MUST be accepted only for a child of the preview
  context's target. The host MUST call guarded
  `POST /api/panels/contexts/{context_id}/open` with `{ref}`; the backend
  authorizes the child and returns a `PreviewEnvelopeModel` from the shared
  panel/legacy routing pipeline. The host mounts the selected renderer in the
  same area and retains the existing drill-down stack and Back action. The
  child preview session retains independent backend-frozen authority, including
  composite ancestry, so closing the parent context does not invalidate it.
  Session get, query patch and resource reads MUST validate that authority;
  changed project, registry or source data invalidates the child session.
  Client query patches MUST NOT replace its backend-owned private fields.
- **FR-021**: `save` MUST write only where the user chooses — the desktop's native
  dialog or a browser download — under a configurable size limit (100 MiB by
  default), and never into the project without that choice. `save` is available
  in every context.

**Phase A — interactive integration**

- **FR-022**: The interactive context's `input` MUST be the `panel_payload` of the
  `interactive_prompt` event the host already receives. The event, the engine, and
  the ADR-051 runtime MUST NOT change.
- **FR-023**: A `PanelManifest` whose `module_url` is empty MUST be resolved
  against the panel registry by `panel_id`. The block registry's interactive check
  MUST refuse a block whose panel does not resolve or does not declare
  `interactive`, and MUST re-check on reload. The host MUST check again when it
  opens the panel and, if the resolved (possibly shadowing) panel lacks
  `interactive`, show an error naming both panels with Cancel. A `PanelManifest`
  with a `module_url` MUST keep using the legacy loader (FR-036).
- **FR-024**: The host MUST map `writeBack` to the existing `interactive_complete`
  message and its Cancel to the existing `cancel_block` message. Panel completion
  carries top-level `context_id`, `workflow_id` and `block_id`. After claiming
  the context once and successfully dispatching the existing completion event,
  the server sends `panel_accepted` with those same top-level identity fields.
  A refused claim or failed dispatch sends `panel_error` with the same identity
  fields and `error: {code, message}`. The host MUST match all three identity
  fields and await acceptance before success-driven modal close, context
  teardown or interaction-memory persistence. Rejection and the 30-second
  acknowledgement timeout MUST surface as errors without recording acceptance;
  cancellation/unmount aborts the wait. The acknowledgement confirms claim and
  dispatch; the existing engine event, decision payload, interaction-memory
  toggle and JSON-safety rules remain unchanged.

**Phase A — serving and security**

- **FR-025**: Each context MUST carry a token: random, at least 128 bits,
  authorizing `GET` of that panel's files, the SDK, and the local library set only,
  renewed while the context is active, and invalid once the context closes.
- **FR-026**: Panel files, the SDK, and the library set MUST be served at
  `/api/panels/t/{token}/assets/{panel_id}/{path}`,
  `/api/panels/t/{token}/sdk/{major}/scistudio-panel.js`, and
  `/api/panels/t/{token}/lib/{name}@{version}/{path}`, built from the configured
  base path (adr-055-prefix-independence), with the path confinement of
  `scistudio.previewers.assets.resolve_asset`. The installed ADR-055 identity
  guard MUST delegate the literal `/api/panels/t/` subtree through
  `register_self_authenticating_prefix`; these routes validate their own token
  without a session cookie. Catalog, context, read, renewal and close operations
  remain behind the installed guard. No Lab-specific middleware is added.
- **FR-027**: Token-scoped responses MUST allow cross-origin reads
  (`Access-Control-Allow-Origin: *`, no credentials) and carry
  `Referrer-Policy: no-referrer`; their file-type allowlist MUST add `.html`,
  `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.ttf`, `.otf`, and `.wasm` to today's
  set. No other API route may send permissive CORS headers.
  The static mount token MUST NOT authorize artifact data. The backend's
  `artifact.file` result uses a separate grant bound to one context-authorized
  target; the host validates the local grant route and consumes it with no
  redirects, enforcing a 100 MiB limit against declared size and streamed bytes.
  Body consumption has its own 30-second deadline after response headers.
  It transfers the bytes over the context's MessageChannel. The SDK creates a
  frame-local blob URL, revokes the previous artifact URL on replacement and all
  remaining URLs on disposal. Context close aborts host transfers and revokes
  backend grants. The frame does not fetch the grant URL; `connect-src 'none'`
  remains unchanged. This transfer contract does not establish Phase B PDF.js
  rendering or companion-asset parity (#2294).
- **FR-028**: Panel HTML responses MUST carry a Content-Security-Policy with
  `connect-src 'none'`; `script-src`, `style-src`, and `font-src` limited to the
  token-scoped path, `'unsafe-inline'`, and the CDN allowlist hosts; and
  `img-src` limited to the token-scoped path, `data:`, and `blob:`.
- **FR-029**: The host MUST dispose a panel frame, and close its context, when the
  frame loads any document other than its panel entry. The first load event is
  not proof of entry identity: without FR-016's valid document-bound bootstrap,
  the host MUST withhold input and initialization. The existing ten-second
  readiness deadline includes a missing entry handshake. A navigation before
  initialization destroys the original document's bootstrap port, so the new
  document receives no input; subsequent frame loads dispose the mount.
- **FR-030**: The backend MUST refuse `POST`, `PUT`, `PATCH`, and `DELETE`
  requests whose `Origin` header is `null`, on every route.
- **FR-031**: The backend MUST refuse to start when `SCISTUDIO_CORS_ORIGINS`
  contains `*` or `null`, naming the setting.
- **FR-032**: The local library set MUST live in `src/scistudio/panels/lib/` with
  an `index.json` listing each library's name, version, files, license, and
  SHA-256. The initial set is Plotly (the version the frontend already pins), D3,
  three.js, and PDF.js. A superseded version MUST stay served for at least one
  minor release after its replacement ships.
- **FR-033**: The CDN allowlist MUST be a SciStudio-owned list, initially
  `cdn.jsdelivr.net`, `cdnjs.cloudflare.com`, and `unpkg.com`, used by FR-028 and
  by the validator (FR-038).
- **FR-034**: The host MUST send the resolved `--ss-*` token values and the light
  or dark mode in `init` and on every change, and the SDK MUST apply them as CSS
  custom properties on the page's root (#1849).

**Phase A — failures and legacy**

- **FR-035**: If a panel does not signal `ready` within 10 seconds, or throws
  before it, the host MUST show an error naming the panel with a remount action;
  in a preview it MUST also offer the core panel for the type, and in an
  interactive modal it MUST offer Cancel. The host MUST NOT fall back silently.
- **FR-036**: The `FrontendManifest` module path and the `PanelManifest`
  `module_url` path MUST keep working through 0.5.x through the existing loaders.
  Registering either MUST record a deprecation diagnostic naming the panel
  replacement and emit a `DeprecationWarning`; the frontend MUST log one warning
  per legacy module load. These paths MUST gain no feature of the panel model.
- **FR-037**: A `PreviewerSpec` with a backend provider and no frontend manifest
  MUST keep rendering through 0.5.x, its envelope drawn by the compiled core
  viewers retained for that purpose (FR-043), and MUST record a deprecation
  diagnostic. A legacy module that fails to load MUST degrade to the compiled
  viewer for its envelope kind, as today.
- **FR-038**: The ADR-049 contract tables MUST gain panel rows — descriptor
  schema, contexts and types rule, sentinel-type and `core.` reservations, API
  major, block-to-panel `interactive` rule, file confinement, and external
  references limited to the CDN allowlist with a warning for unpinned versions —
  and MUST record that PV-12-001's same-origin rule does not apply to panels.
  The checks MUST run where discovery and block scanning already validate,
  enforced by `scripts/audit/check_package_contract_tables.py`.

**Phase A — preview mounting**

- **FR-039**: The preview panel and the preview tab MUST mount panels through the
  same host component. Maximize MUST open the preview tab on the frozen target
  with the resolved panel id and the mount's latest view state; the tab MUST keep
  its `preview:<ref>` dedup and drop rule; dropping or closing a tab MUST dispose
  its frames and close its contexts; Data-tree open and the type-change chip MUST
  re-resolve the panel for the chosen type. A maximized child MUST carry its
  `previewSessionId` so its independent frozen authority survives parent-frame
  teardown, including for composite slots absent from the top-level catalog.

**Phase B — core migration**

- **FR-040**: Each core previewer MUST be rewritten as a core-tier panel with the
  same id and a parity checklist covering the behaviour of the view it replaces:

  | Panel id | Replaces | Parity scope |
  |---|---|---|
  | `core.dataframe.basic` | `DataFrameViewer` (`TableViewer.tsx`) | paging, sort, column display, truncation notice |
  | `core.array.basic` | `ArrayViewer` | plane display, slice axes, contrast and LUT over values, tiles, metadata |
  | `core.series.basic` | `SeriesViewer` | decimated line plot, axis labels |
  | `core.text.basic` | `TextViewer` | paged text, encoding, truncation notice |
  | `core.artifact.basic` | `ArtifactViewer` | name, MIME type, size, safe display through `artifact.file` |
  | `core.composite.basic` | `CompositeViewer` | slot list; `open` into a slot |
  | `core.collection.basic` | `CollectionViewer` | item cards with paging; `open` into an item |
  | `core.plot.basic` | `PlotViewer` | PNG, JPEG, SVG as an image (scripts never run), PDF via PDF.js, fit, zoom, export via `save` |
  | `core.base.fallback` | `ErrorViewer` and the default branch | metadata and error display |

- **FR-041**: `core.interactive.data_router` and `core.interactive.pair_editor`
  MUST be rewritten as core-tier panels declaring `interactive`, producing the
  response shapes the Data Router and Pair Editor blocks consume today, with no
  change to the blocks.
- **FR-042**: Core panels MUST reference only the SDK, their own files, and the
  local library set.
- **FR-043**: Once every Phase B panel passes its parity checklist, the frontend
  MUST delete `DataRouterModal`, `PairEditorModal`, and the `PANEL_REGISTRY` of
  built-in interactive windows, and MUST stop using the compiled core viewers for
  anything but envelopes from legacy previewers (FR-037). The compiled viewers are
  removed in 0.6 with the legacy forms (#2288).

**Phase C — docs and skills**

- **FR-044**: A new `docs/package-development/panels.md` MUST cover the folder
  layout, `panel.json`, contexts and permissions, every SDK call, service, and
  read operation, the library set, the CDN allowlist and the offline caveat, view
  state, the frame's limits, testing with `panel.sample.json`, the
  `scistudio.panels` entry point, and the tiers. `previewers.md` MUST be reduced to
  both legacy forms and a migration guide until 0.6, and the other
  package-development pages that mention previewers or `PanelManifest` MUST point
  to `panels.md`.
- **FR-045**: A new embedded-agent skill
  `src/scistudio/_skills/scistudio/scistudio-write-panel/SKILL.md`, added to the
  provisioned skill names in `src/scistudio/agent_provisioning/skills.py`, MUST
  teach the
  agent to write, validate, and check a panel, preferring the local library set and
  staying within the CDN allowlist; the skills index, the `scistudio-write-block`
  and `scistudio-inspect-data` skills, and the `_agent_reference` pages MUST
  reference it where they mention previewers or panels. This supersedes the scope
  of #2013 and #2197.
  Owner-guided refinement (#2295): provision `scistudio-use-gui` as a general
  GUI operation guide using `open_gui` and the client's available browser or
  computer-use tools. The guide teaches access, navigation, controls, and
  observation; panel verification belongs in the calling authoring skills.
  Panel authoring skills MUST route to it for a short live view and main
  interaction check when creating or repairing preview panels, interactive
  panels, or MiniApps. At the routing layer, plot,
  workflow, and ordinary run-debugging skills MUST NOT automatically invoke GUI
  checks. An explicit user request to operate the GUI remains supported. Missing
  computer-use capability MUST be reported as a specific verification limit;
  a screenshot alone MUST NOT be described as an interaction test.
  The `open_gui` description and returned hint MUST point to this guide and
  available browser/Chrome/computer-use tools, preserve the complete instance
  URL, and explain that the tool returns an address without opening or
  operating the GUI. The panel skill MUST distinguish preview reads from
  interactive prepared views and one-shot decisions, route standalone apps to
  `scistudio-write-miniapp`, and include executable preview/interactive examples.
  Both authoring skills MUST distinguish descriptor checks, sample-mode checks,
  live rendering, and actual interaction evidence. When available, local MCP
  `screenshot_gui` captures the SciStudio application workspace/MiniApp; browser tabs use their own
  screenshot tooling.
- **FR-046**: When a panel page is opened directly rather than in a frame, the SDK
  MUST serve `context` and `input` from `panel.sample.json` beside the page and
  answer `read` from its `reads` map, so an author or the agent can check a page
  with no running host.
- **FR-047**: `docs/specs/adr-048-preview-system.md` and
  `docs/specs/adr-051-interactive-blocks.md` MUST state which of their frontend
  contracts this spec replaces and link here; `docs/specs/adr-055-enterprise-support.md`
  MUST record the token-authenticated exception of FR-026; `docs/adr/ADR-049.md`
  MUST carry the contract rows of FR-038.
- **FR-048**: The Phase C PR MUST propose updated text for ARCHITECTURE.md §9.6,
  §12.2.3, §5.3.1, and the project layout table; the change requires the
  `admin-approved:architecture-doc` label.
- **FR-049**: The Phase C PR MUST prepare the code assets of the "What Is A Type"
  tutorial as panel folders replacing `panel.mjs` and `image_preview.py`; the
  tutorial copy is supplied by the owner.
- **FR-050**: The panel contract reference MUST be generated from source
  (ADR-052 Addendum 1): `scripts/docs/build_panel_reference.py` renders
  `panels-sdk.md` (the SDK, the operations per context, the read operations, the
  error codes, and the library set), `panels-renderers.md` (the stylesheets and
  the `panel-ui.js` and `renderers.js` components with their props), and
  `panel-descriptor.md` (the `panel.json` keys and rules and the
  `panel.sample.json` shape) into `src/scistudio/_user_guide/api-reference/`,
  stamped `provisional` with the panel API version, and
  `tests/docs/test_panel_reference.py` MUST fail when the committed pages are
  stale. The guides and skills of FR-044 and FR-045 link to these pages for
  signatures, props, keys, and read parameters instead of restating them.

### Key Entities

- **PanelDescriptor** — the parsed `panel.json`: `id`, `api_version`,
  `contexts`, `types`, `priority`, `name`, `description`, `version`, `entry`.
  One per panel directory.
- **PanelRecord** — a registry entry: descriptor, tier, owner (core, package
  name, user, project), directory, diagnostics, shadowed-by. A routing candidate
  alongside legacy `PreviewerSpec` records.
- **PanelContext** — backend runtime state for one mount: `context_id`, kind,
  panel id, target or `{workflow_id, block_id}`, authorized references (none for
  `interactive`), operations and services, decision-used flag, token, created and
  last-active times. Owned by one frame; closed with it.
- **PanelToken** — the per-context credential of FR-025: value, context,
  scope (panel files, SDK, library set), expiry.
- **ReadRequest / ReadResult** — `{ref, op, params}` and the typed result of
  FR-011 with its flags.
- **PanelMessage** — the envelope of FR-016, carried over the context's port.
- **ViewState** — a JSON-safe object a panel reports and receives on remount.
- **LibraryEntry** — one row of `lib/index.json`: name, version, files, license,
  SHA-256.
- **CdnAllowlist** — the host list of FR-033.

## 4. Implementation Plan

### 4.1 Technical Approach

**Backend.** A new package `scistudio.panels` holds the descriptor model and
parser, discovery over the four tiers, the registry, the context service with its
tokens, and the read service. Discovery reuses the tier roots and the tutorial
swap in `scistudio.core.dropins`. Routing is not reimplemented: the ADR-048
router gains panel records as candidates. The read service maps FR-011 operations
onto `PreviewDataAccess`, extended per FR-014, running in a thread pool. A new
`api/routes/panels.py` serves contexts, reads, and the token-scoped files. The
session middleware learns the token exception; a small middleware refuses
opaque-origin state changes; app start refuses a wildcard or `null` CORS setting.
The engine and the ADR-051 runtime are untouched.

**Frontend.** A new `frontend/src/panels/` holds `PanelFrame` (the sandboxed
frame, channel handoff, ready timeout, navigation teardown, error card, disposal),
the bridge (message dispatch over the port), and a per-context operations table.
`PreviewHost` mounts `PanelFrame` for panel candidates, keeps its drill-down stack
for `open`, and keeps the legacy loader and the compiled viewers for legacy
candidates; the preview tab mounts the same component. The interactive modal
mounts `PanelFrame` for panels resolved by id and keeps `DynamicPanel` for
`module_url` manifests.

**SDK.** A single dependency-free script, versioned by API major, implementing
FR-017 and FR-046.

**Data flow.**

```text
panel page ══port══▶ PanelFrame/bridge ──fetch (session)──▶ /api/panels/contexts/{id}/read
     ▲                      │                                        │
     └── result (buffer) ◀──┘◀────────── JSON or binary ◀────────────┘ PreviewDataAccess

panel page ──GET (token in path)──▶ /api/panels/t/{token}/{assets|sdk|lib}/...
```

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/panels/**` | create | Descriptor, discovery, registry, contexts, tokens, reads, SDK, library set, CDN allowlist, core panels (`builtin/`) |
| `src/scistudio/api/routes/panels.py` | create | Context, read, and token-scoped file routes |
| `src/scistudio/api/app.py` | modify | Mount panels router; token exception; opaque-origin refusal; CORS start check |
| `src/scistudio/core/dropins.py` | modify | Panel tier roots |
| `src/scistudio/previewers/router.py`, `registry.py`, `choices.py`, `project.py` | modify | Panels as routing candidates; shared namespace; choices accept panel ids |
| `src/scistudio/previewers/data_access.py` | modify | FR-014 extensions |
| `src/scistudio/previewers/assets.py` | modify | Shared confinement and extended allowlist |
| `src/scistudio/api/routes/data.py` | modify | Reload and catalog include panels; deprecation diagnostics |
| `src/scistudio/blocks/base/interactive.py`, `src/scistudio/blocks/registry/_capability.py` | modify | Empty-`module_url` resolution and the `interactive` check; deprecate `module_url` |
| `scripts/audit/check_package_contract_tables.py`, `docs/adr/ADR-049.md` | modify | Panel contract rows; PV-12-001 note |
| `frontend/src/panels/**` | create | `PanelFrame`, bridge, operations |
| `frontend/src/components/DataPreview.parts/PreviewHost.tsx` | modify | Mount panels; `open` via drill-down stack; legacy paths retained |
| `frontend/src/components/DataPreview.tsx`, `frontend/src/store/tabSlice.parts/previewTabActions.ts`, `frontend/src/App.parts/ProjectWorkspace.tsx` | modify | Maximize carries panel id and view state; disposal on drop |
| `frontend/src/App.parts/InteractiveModals.tsx` and `.parts/**` | modify | Mount panels by id; keep `DynamicPanel` for legacy |
| `frontend/src/components/DataRouterModal.tsx`, `frontend/src/components/PairEditorModal.tsx` | delete | Phase B, after parity |
| `frontend/src/components/DataPreview.parts/coreViewers.tsx`, `TableViewer.tsx`, `PlotViewer.tsx` | modify | Phase B: used only for legacy envelopes (removed in 0.6, #2288) |
| `docs/package-development/panels.md` | create | Phase C guide |
| `docs/package-development/previewers.md`, `index.md`, `architecture.md`, `blocks.md`, `publishing.md` | modify | Phase C |
| `src/scistudio/_skills/scistudio/scistudio-write-panel/SKILL.md` | create | Phase C skill |
| `src/scistudio/_skills/scistudio/SKILL.md`, `scistudio-write-block/SKILL.md`, `scistudio-inspect-data/SKILL.md`, `src/scistudio/_agent_reference/*.md` | modify | Phase C references |
| `docs/specs/adr-048-preview-system.md`, `docs/specs/adr-051-interactive-blocks.md`, `docs/specs/adr-055-enterprise-support.md` | modify | FR-047 |
| `src/scistudio/tutorials/core/what-is-a-type/**` | modify | FR-049 code assets |
| `scripts/docs/build_panel_reference.py`, `scripts/docs/build_reference.py`, `src/scistudio/_user_guide/api-reference/panels-sdk.md`, `panels-renderers.md`, `panel-descriptor.md`, `tests/docs/test_panel_reference.py` | create or generate | FR-050 generated panel contract reference |
| `tests/panels/**`, `tests/api/test_panel_routes.py`, `tests/api/test_panel_security.py`, `tests/api/test_app.py`, `frontend/src/panels/*.test.*` | create or modify | Coverage for Phases A and B |

### 4.3 Implementation Sequence

| Task | Title | Story | Files | Depends on | Verification |
|---|---|---|---|---|---|
| T-001 | Descriptor model, parser, FR-002/003 validation | US7 | `src/scistudio/panels/` | — | `test_panel_descriptor.py` |
| T-002 | Tier discovery and registry; reload and catalog listing | US1, US9 | `panels/`, `core/dropins.py`, `routes/data.py` | T-001 | `test_panel_registry.py` |
| T-003 | Routing over panels and legacy previewers; namespace; choices | US1, US8 | `previewers/router.py`, `registry.py`, `choices.py` | T-002 | `test_panel_routing.py`, `test_preview_routing.py` |
| T-004 | Read-layer extensions of FR-014 | US1, US6 | `previewers/data_access.py` | — | `test_preview_data_access.py` |
| T-005 | Context service, tokens, generic read route | US1, US2, US5 | `panels/`, `routes/panels.py` | T-002, T-004 | `test_panel_contexts.py`, `test_panel_read.py`, `test_panel_tokens.py` |
| T-006 | Token-scoped file routes, session exception, CSP, allowlist, CORS headers | US3, US5 | `routes/panels.py`, `app.py`, `panels/lib/` | T-005 | `test_panel_routes.py` |
| T-007 | Opaque-origin refusal and CORS start check | US3 | `app.py` | — | `test_panel_security.py`, `test_app.py` |
| T-008 | Interactive checks at discovery and open; legacy and Python-only deprecation | US2, US7, US8 | `_capability.py`, registries | T-002 | `test_interactive_mixin.py`, registry tests |
| T-009 | Validator contract rows and PV-12-001 note | US7 | `check_package_contract_tables.py`, `ADR-049.md` | T-001, T-008 | contract-table check |
| T-010 | SDK script, including sample mode | US1, US10 | `panels/sdk/` | T-006 | SDK tests |
| T-011 | `PanelFrame`, channel handoff, bridge, teardown, error card | US1, US3 | `frontend/src/panels/` | T-005, T-010 | `PanelFrame.test.tsx`, `bridge.test.ts` |
| T-012 | Preview mounting, `open` drill-down, maximize, preview tab, Data-tree open | US4 | preview host and tab files | T-011 | `PreviewHost.test.tsx`, tab tests |
| T-013 | Interactive modal mounting and write back | US2 | `InteractiveModals*` | T-008, T-011 | `test_interactive_panels.py`, modal tests |
| T-014 | Core preview panels with parity checklists | US6 | `panels/builtin/` | T-012 | per-panel parity tests |
| T-015 | Core interactive panels | US6 | `panels/builtin/` | T-013 | Data Router and Pair Editor tests |
| T-016 | Delete compiled interactive windows; restrict compiled viewers to legacy envelopes | US6, US8 | frontend | T-014, T-015 | full frontend suite |
| T-017 | Panel guide, legacy migration guide, page updates | US10 | `docs/package-development/` | T-016 | full audit |
| T-018 | Agent skill and references | US10 | `_skills/`, `_agent_reference/` | T-017 | e2e scenario |
| T-019 | Spec, ADR-049, and ADR-055 notes; ARCHITECTURE.md proposal; tutorial assets | — | specs, ADR-049, tutorial assets | T-017 | full audit; owner review |

PR boundaries follow the phases: T-001 to T-010 (backend, security, SDK),
T-011 to T-013 (frontend host), T-014 to T-016 (core migration), T-017 to T-019
(docs and skills). T-007 may land first on its own because it hardens the backend
independently of panels.

### 4.4 Verification Plan

- Backend unit and API tests listed in the frontmatter, run through
  `gate_record check`.
- Frontend tests for the frame attributes, channel handoff, message filtering,
  operations per context, navigation teardown, disposal, drill-down, and
  preview-tab behaviour.
- Security tests for every US3 attempt, the opaque-origin refusal, and the CORS
  start check.
- Prefix and authentication tests for US5 using the adr-055-prefix-independence
  harness with session authentication enabled.
- Parity checklists for each Phase B panel, recorded in the Phase B PR.
- An e2e scenario under `docs/ai-developer/e2e/` covering a custom preview panel,
  an interactive panel, maximize, drill-down, offline core panels, and the
  forever-looping panel on the supported Electron build.
- Wheel release smoke confirming `panels/builtin/`, `panels/lib/`, and the SDK
  ship in the wheel.
- The ADR-049 contract-table check and full audit for the docs.

### 4.5 Risks And Rollback

- **Parity gaps in rewritten viewers.** Mitigated by per-panel checklists and by
  deleting the compiled interactive windows only after parity (T-016).
- **Read cost at native resolution.** Mitigated by binary transport and budgets;
  measured in the e2e scenario (SC-006).
- **Token handling.** Tokens are unguessable, scoped to static files, sent with
  `no-referrer`, and die with their context; a leaked token exposes only a panel's
  files while it is open.
- **Hardening that affects existing users.** FR-030 and FR-031 change backend
  behaviour for everyone; T-007 carries its own tests and changelog entry and can
  be reverted independently.
- **Confidentiality.** A panel can still navigate or load allowlisted scripts;
  the frame teardown and allowlist narrow this and ADR-054 §4 states the limit.
- **Two loaders and two rendering paths until 0.6.** Deprecation diagnostics make
  every remaining legacy use visible; removal is tracked in #2288.
- **Rollback.** Phase A is additive; Phase B is reverted together with any panel
  found wanting, restoring the compiled windows.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: All nine core previews and both built-in interactive windows render
  as core-tier panels and pass their parity checklists.
- **SC-002**: After Phase B, no compiled component renders a built-in interactive
  window, and the compiled core viewers render only envelopes from legacy
  previewers.
- **SC-003**: In the security tests, 100% of a panel's attempts to read or change
  backend state directly, access the host document, read an unauthorized
  reference, or message another panel fail, and every frame navigation is torn
  down.
- **SC-004**: A fixture interactive block completes pause, decision, and compute
  through a panel with the decision recorded in lineage, and a second write back
  is refused.
- **SC-005**: Fixtures of both legacy forms load and behave as before in 0.4 and
  0.5, each producing exactly one deprecation diagnostic.
- **SC-006**: A 256 × 256 plane read reaches a panel in no more than 1.2 times the
  time the current preview session takes for the same plane, measured in the e2e
  scenario.
- **SC-007**: With the frame's network unavailable, every core panel renders.
- **SC-008**: Maximizing a preview opens a tab with the same panel id and the last
  reported view state in 100% of the preview-tab tests.
- **SC-009**: Under a prefixed, session-authenticated test deployment, a panel's
  entry, module imports, fonts, SDK, and library files all load, and all are
  refused after its context closes.
- **SC-010**: In the e2e scenario, the embedded agent produces a panel that
  validates and renders using only the skill and the guide.

## 6. Assumptions

- ADR-054 as revised after its no-context audit is the governing decision; this
  spec follows it where they differ. (source: adr)
- `PreviewDataAccess` covers every canonical type's bounded read apart from the
  gaps FR-014 lists. (source: existing-system)
- The built-in interactive blocks already declare `panel_id` with an empty
  `module_url` (`core.interactive.data_router`), so resolving an empty `module_url`
  through the registry keeps existing declarations valid. (source:
  existing-system)
- The host already receives the `panel_payload` in the `interactive_prompt` event,
  so the interactive context needs no engine change. (source: existing-system)
- The browser's built-in PDF viewer does not run inside a sandboxed frame, and
  whether a sandboxed frame runs out of process depends on the browser; both are
  verified on the supported Electron build. (source: inferred)
- The route shapes, the 10-second ready timeout, the 100 MiB save limit, the
  initial library set, the initial CDN allowlist, and the SC-006 target are spec
  decisions open to owner revision. (source: spec)
- Every public Python symbol this spec changes is `provisional` (ADR-052 §5);
  `panel.json` and the SDK enter at the same tier. (source: adr)
- The external packages migrate in their own repositories against the Phase A
  contracts. (source: owner)
