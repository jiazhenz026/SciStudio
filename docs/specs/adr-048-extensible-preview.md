---
spec_id: adr-048-extensible-preview
title: "Extensible Preview Providers"
status: Draft
feature_branch: docs/adr-048-extensible-preview
created: 2026-06-10
input: "Owner request (2026-06-10): make Preview extensible so any data type can be previewed — package-defined renderers loaded at runtime plus user-defined matplotlib plot functions — with a provider resolution chain and core fallback viewers."
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
related_specs: []
scope:
  in:
    - The preview provider resolution chain and its fixed priority order.
    - Core fallback viewers for every base type (Array, Series, DataFrame, Text, CompositeData, Artifact).
    - The user-defined matplotlib plot-function contract, its binding model, backend execution, caching, and figure export.
    - The package-defined renderer contract, runtime dynamic loading, sandbox/trust model, and versioned renderer API.
    - Collection-aware, reference-based data access shared by user plots and package renderers.
    - Migration of the existing image viewer out of core into the imaging package as the first package renderer.
  out:
    - Implementation code. This spec is the contract; implementation is sequenced after ADR-048 is accepted.
    - Letting end users ship JavaScript renderers. End users author Python/matplotlib only.
    - Interactive (zoom/pan/hover) re-rendering of user matplotlib output. A matplotlib plot is a static figure.
    - Changing the reference-only data transport (ADR-031) or the named-axes contract (ADR-027). They are reused unchanged.
    - Real-time collaborative or multi-user preview concerns.
governs:
  modules:
    - scistudio.api.runtime
    - scistudio.core.types
  contracts: []
  files:
    - docs/specs/adr-048-extensible-preview.md
    - docs/adr/ADR-048.md
    - src/scistudio/api/runtime/_data.py
    - src/scistudio/api/routes/data.py
    - frontend/src/components/DataPreview.parts/PreviewRenderer.tsx
    - frontend/src/components/DataPreview.tsx
    - frontend/src/components/DataPreview.parts/ImageViewer.tsx
    - src/scistudio/core/types/**
    - packages/scistudio-blocks-imaging/**
  excludes:
    - tests/**
    - docs/audit/**
tests: []
acceptance_source: adr
language_source: en
---

# Extensible Preview Providers

## 1. Change Summary

Today the Preview panel is hardcoded from end to end. The backend
`preview_data()` decides what to show through an `if/elif` chain keyed on a
data object's type name and file extension, and the frontend `PreviewRenderer`
switches on a fixed set of six `preview.kind` strings (`table`, `image`,
`chart`, `text`, `composite`, `artifact`). A package can already contribute new
data **types** through the `scistudio.types` entry point, but it cannot
contribute any preview **behavior**. As a result the imaging package's `Image`
and `Label` types borrow the generic array and composite paths, there is no way
to plot scientific data, and the one rich viewer that does exist — the image
viewer with pan/zoom/LUT — lives in core even though it is an imaging-domain
concern.

This spec defines how Preview becomes extensible without leaving technical
debt. It replaces the two hardcoded dispatch points with a single **provider
resolution chain**, and it opens exactly two authoring surfaces on that chain:
**package-defined renderers** (interactive UI a package ships and the app loads
at runtime) and **user-defined plot functions** (a matplotlib function a user
writes in their own project, executed in the backend). Core keeps only basic
fallback viewers for the base types. The chain's priority order, the data each
provider receives, and the closed set of produce/render modes are all specified
here so that every future preview is a combination of already-defined parts
rather than a new special case.

This spec is derived from the owner request recorded in ADR-048 and is the
contract that the (separately sequenced) implementation must satisfy. It does
not itself change code.

## 2. User Scenarios & Testing

### User Story 1 - Core fallback viewers on a resolution chain (Priority: P1)

Every block output — of any base type — still previews after the hardcoded
dispatch is replaced by the resolution chain. When no package renderer and no
user plot apply, core's basic per-type viewer renders the output. A
`CompositeData` output shows which named slots it contains and the data type of
each slot.

**Why this priority**: This is the foundation. The chain plus the core
fallback viewers must exist before any extension surface can plug into it, and
it must preserve the previews users already rely on. Shipping only this story
is a net-neutral refactor that unlocks everything else.

**Independent Test**: Produce one output of each base type (Array, Series,
DataFrame, Text, CompositeData, Artifact) in a project with no package
renderers and no user plots, open Preview for each, and confirm each renders
with the correct core viewer and that the CompositeData viewer lists its slot
names and per-slot types.

**Acceptance Scenarios**:

1. **Given** a project with no package renderers and no user plots, **When** a
   user opens Preview for a `DataFrame` output, **Then** the core table viewer
   renders it exactly as it does today.
2. **Given** the same project, **When** a user opens Preview for a
   `CompositeData` output that contains slots `raster: Array` and
   `polygons: DataFrame`, **Then** the core composite viewer shows the two slot
   names and their data types.
3. **Given** an output whose type has no more-specific provider, **When**
   Preview resolves a provider, **Then** the resolution ends at the core viewer
   for that type's base type and never errors with "no preview available".

### User Story 2 - User plots their own data with matplotlib (Priority: P2)

A user writes a matplotlib plot function in their own project and binds it to a
block's output. Opening Preview for that output runs the function in the
backend and shows the resulting figure in the same place the output's preview
appears. The figure can be saved/exported.

**Why this priority**: This is the headline new capability — plotting, which
scientific data work requires — and it is the cheaper of the two extension
surfaces because it reuses the existing backend code-execution and image-render
paths. It delivers standalone value the moment the chain (P1) exists.

**Independent Test**: In a project, add a plot function bound to a specific
block output, open Preview for that output, and confirm the rendered figure
matches the function; then trigger save/export and confirm a figure artifact is
produced. No application rebuild or restart is required between writing the
function and seeing the figure.

**Acceptance Scenarios**:

1. **Given** a block output and a user plot function bound to it, **When** the
   user opens Preview for that output, **Then** the backend executes the
   function and Preview shows the returned figure.
2. **Given** a displayed user-plot figure, **When** the user saves/exports it,
   **Then** a figure artifact is produced and retrievable.
3. **Given** a user plot function that raises an error, **When** Preview runs
   it, **Then** the error is surfaced to the user and the provider chain falls
   back to the next applicable provider rather than crashing the panel.

### User Story 3 - A package ships a renderer for its data type (Priority: P3)

A package author ships an interactive renderer bound to a data type the package
defines. After the package is installed, the application loads the renderer at
runtime — no frontend rebuild — and outputs of that type render with the
package's UI. The current core image viewer is migrated into the imaging
package as the first such renderer; core keeps only a basic array viewer.

**Why this priority**: This is the most powerful and the heaviest surface
(runtime module loading plus a sandbox). It is also the one that cleans up the
core/plugin boundary by moving the image viewer where it belongs. It depends on
the chain (P1) and is exercised end to end by the imaging migration.

**Independent Test**: Install a package that registers a renderer for one of
its types, reload the app (no rebuild), open Preview for an output of that type,
and confirm the package renderer is shown. Then disable/remove the renderer and
confirm Preview falls back to the core viewer for that type's base type.

**Acceptance Scenarios**:

1. **Given** an installed package that registers a renderer for type `Image`,
   **When** a user opens Preview for an `Image` output, **Then** the package
   renderer is loaded at runtime and renders the output.
2. **Given** no installed renderer for a type, **When** a user opens Preview
   for an output of that type, **Then** the chain falls back to the core basic
   viewer.
3. **Given** a package renderer running in the host, **When** it attempts to
   read host credentials or reach into the host DOM outside the sandbox bridge,
   **Then** the attempt is denied by the sandbox.
4. **Given** the migrated imaging renderer, **When** the imaging package is not
   installed, **Then** core contains no imaging-specific viewer code and an
   `Array` still previews through the core array viewer.

### User Story 4 - Plot a whole collection together (Priority: P4)

A user's plot function receives the entire collection behind an output, not a
single object, so that data such as ten spectra stored as a ten-object
collection can be drawn together in one figure.

**Why this priority**: It is a refinement of the user-plot surface that the
owner called out explicitly. It is valuable but builds directly on P2 and the
collection-aware data access shared with P3.

**Independent Test**: Produce a block output that is a collection of N `Series`
objects, bind a user plot that iterates the collection and overlays each
series, open Preview, and confirm all N series appear in a single figure.

**Acceptance Scenarios**:

1. **Given** a block output that resolves to a collection of N objects,
   **When** the bound user plot runs, **Then** the function receives all N
   objects and the figure contains all N.
2. **Given** a block output that resolves to a single object, **When** a user
   plot runs, **Then** the function receives a collection of length 1, so the
   single-object and multi-object cases use one code path.

### Edge Cases

- A type has both a package renderer and a user plot bound to the same output:
  resolution priority decides; the user plot (output binding) wins.
- A package renderer declares a renderer-API version the host does not support:
  the renderer is skipped and the chain falls back, with a recorded
  incompatibility reason.
- A user plot or package renderer requests an object that no longer exists in
  the collection (stale reference): the data-access API returns a not-found
  result the provider must handle; Preview does not 500.
- A very large collection is bound to a user plot: the function still receives
  the whole collection by reference and is responsible for sampling; the
  contract documents this rather than silently truncating.
- Two user plots are bound, one to the output and one to the output's type:
  the output binding wins per the priority order.

## 3. Requirements

### Functional Requirements

- **FR-001**: Preview MUST resolve which provider renders a given block output
  through a single resolution chain evaluated in this fixed priority order,
  most specific first: (1) a user plot bound to that output; (2) a user plot
  bound to that output's type within the project; (3) a package renderer bound
  to that output's type; (4) the core basic viewer for the output's base type.
- **FR-002**: The resolution chain MUST fall through to the next tier whenever
  a higher tier has no applicable provider, and MUST always terminate at a core
  viewer so that no resolvable output is left without a preview.
- **FR-003**: Core MUST provide a basic viewer for each base type: `Array`,
  `Series`, `DataFrame`, `Text`, `CompositeData`, and `Artifact`.
- **FR-004**: The core `CompositeData` viewer MUST display the composite's
  named slots and the data type of each slot. It is a structural inspector, not
  a deep render of slot contents.
- **FR-005**: Core MUST NOT contain viewers specific to a package-defined
  domain type. Domain viewers MUST be contributed by their package.
- **FR-006**: A user MUST be able to define a plot as a Python function in their
  own project whose body uses matplotlib, conforming to a fixed signature that
  receives the bound output as a collection and returns a matplotlib figure.
- **FR-007**: A user plot MUST be bindable to a specific block output (primary
  binding) and MAY be bindable to a data type within the project (secondary
  binding), with the priority defined in FR-001.
- **FR-008**: A user plot MUST execute in the backend under the same isolation
  the runtime uses to execute block code, and MUST run lazily at preview time
  (on demand), not as part of normal workflow execution.
- **FR-009**: The result of a user plot MUST be a figure that Preview displays
  and that the user can save/export as an artifact.
- **FR-010**: When a user plot raises, Preview MUST surface the error and the
  chain MUST fall back to the next applicable provider; the panel MUST NOT
  crash.
- **FR-011**: A package MUST be able to register a renderer bound to a data
  type through a declared extension point, distinct from the existing
  `scistudio.types` and `scistudio.blocks` entry points.
- **FR-012**: A registered package renderer MUST be loaded by the frontend at
  runtime after the package is installed, with no frontend rebuild required
  (install-and-go).
- **FR-013**: A package renderer MUST run inside a sandbox that prevents it from
  accessing host credentials, host storage, or the host DOM except through a
  declared, typed host bridge.
- **FR-014**: A package renderer MUST declare the renderer-API version it
  targets. The host MUST refuse to load a renderer whose version it does not
  support and MUST fall back per FR-002, recording the incompatibility reason.
- **FR-015**: Preview MUST operate over the entire collection behind an output.
  A single object MUST be presented to providers as a collection of length one
  so that single- and multi-object cases share one contract.
- **FR-016**: Providers MUST receive the data as a reference, not as a
  pre-serialized payload. A user plot receives the in-process collection the
  way a block does; a package renderer receives the collection's reference and
  reads through the data-access API.
- **FR-017**: The data-access API MUST let a renderer enumerate the objects in a
  collection and read each object's data and metadata on demand, so a renderer
  pulls only what it needs.
- **FR-018**: The existing image viewer MUST be migrated from core into the
  imaging package as a package renderer bound to `Image`, and core MUST retain
  only a basic `Array` viewer after the migration.

### Key Entities

- **PreviewProvider**: The unit the chain resolves to. Attributes: `binding`
  (output id, type name, or base type), `source` (`user-plot`,
  `package-renderer`, or `core-viewer`), `produce_mode` (`backend-figure` or
  `reference-read`), `render_mode` (`image`, `core-viewer`, or
  `package-component`). Relationship: many providers may apply to one output;
  the chain selects the highest-priority applicable one.
- **ProviderResolution**: The result of evaluating the chain for one output.
  Attributes: `output_ref`, `selected_provider`, `fallback_reason` (when a
  higher tier was skipped). Relationship: one resolution per output per preview
  request.
- **UserPlotFunction**: A user-authored Python function. Attributes: `binding`
  (output id or type), `signature` (receives a `Collection` and a plot context,
  returns a figure), `source_location` (project file). Relationship: produces a
  `FigureArtifact`.
- **PlotContext**: The non-data argument passed to a user plot. Attributes:
  rendering hints such as size/theme and any declared helpers. Relationship:
  supplied by the runtime at execution time.
- **PackageRendererRegistration**: A package's declaration that a renderer
  serves a type. Attributes: `type_name`, `module_ref` (the loadable renderer
  module), `api_version`. Relationship: resolved by the chain at tier 3.
- **PreviewDataAccess**: The reference-plus-API contract a provider uses to read
  data. Attributes: `collection_ref`, `enumerate()` over object refs,
  `read(object_ref)` for data/metadata. Relationship: shared by user plots
  (in-process) and package renderers (over the API).
- **FigureArtifact**: The saved output of a user plot. Attributes: `format`
  (raster/vector), `source_output_ref`. Relationship: produced by a
  `UserPlotFunction`, exportable by the user.

## 4. Implementation Plan

### 4.1 Technical Approach

The two hardcoded dispatch points — the backend `preview_data()` `if/elif`
chain and the frontend `PreviewRenderer` switch — are replaced by one
**resolution chain** that both sides consult. For a given output the chain
returns a `ProviderResolution` naming the selected provider and how to render
it. Because the chain is the only dispatch, every preview path is one of the
four tiers in FR-001, and the produce/render modes are a closed set, every
future preview is a combination of defined parts rather than a new branch.

There are two execution paths behind the chain, unified by the resolution:

- **Backend figure path** (user plots, and any package renderer that chooses to
  render server-side): the runtime executes Python that returns a matplotlib
  figure; the figure is rendered to an image and Preview displays it through the
  same image path that exists today. User plot execution reuses the block
  execution isolation (subprocess) so running user code carries no new trust
  model — it is the trust model the runtime already has for block and package
  code. Execution is lazy: it happens when Preview is opened for the output and
  the result is cached as a figure artifact keyed by the output and inputs.
- **Frontend renderer path** (package renderers, and the core viewers): the
  backend hands the frontend the collection's reference and the selected
  provider; the frontend renders. Core viewers are built in. Package renderers
  are pre-built JavaScript modules the host loads at runtime via dynamic import
  and runs inside a sandbox (an isolated frame) that exposes only a typed host
  bridge: the data-access API and rendering hints. The renderer reads data by
  pulling object refs and per-object data/metadata through that bridge over the
  existing data HTTP API; it never receives a large pre-serialized payload and
  cannot reach host credentials, storage, or DOM directly. Each renderer
  declares the renderer-API version it targets so the host can refuse
  incompatible modules and fall back.

Data is passed by reference throughout. A SciStudio collection is already a
reference under the ADR-031 reference-only data contract, so "give the provider
the reference and let it read what it needs" is the natural contract: a backend
user plot receives the in-process `Collection` exactly as a block does, and a
frontend package renderer receives the collection ref and reads through the
data-access API. Preview is collection-level: a single object is wrapped as a
length-one collection so providers have one shape to handle.

The renderer registration uses a new extension point (sibling to
`scistudio.types` and `scistudio.blocks`) keyed by data type, so a package
declares "type X → renderer module" the same way it declares its types and
blocks today. The core/plugin boundary is enforced by migrating the existing
image viewer out of core into the imaging package as the first registered
renderer; this both proves the runtime-loading mechanism end to end and removes
imaging-domain UI from core.

### 4.2 Affected Files

| File or surface | Action | Rationale |
|---|---|---|
| `src/scistudio/api/runtime/_data.py` | modify | Replace the `if/elif` preview dispatch with provider-chain resolution; keep core base-type producers. |
| `src/scistudio/api/routes/data.py` | modify | Preview endpoint returns the resolved provider; add collection enumerate/read access for renderers. |
| API preview response schema (`src/scistudio/api/**/schemas.py`) | modify | `DataPreviewResponse` carries the resolved provider descriptor instead of a fixed `kind`. |
| Preview provider resolver (new core module under `src/scistudio/api/runtime/` or `src/scistudio/core/`) | create | Single place that evaluates the FR-001 chain. |
| User-plot runner (new module) | create | Executes a project plot function under block isolation and caches the figure artifact. |
| Renderer registry + entry-point group `scistudio.preview_renderers` (new) | create | Type → renderer registration discovered like `scistudio.types`. |
| `frontend/src/components/DataPreview.parts/PreviewRenderer.tsx` | modify | Replace the `kind` switch with provider-driven rendering: core viewer, image, or sandboxed package renderer host. |
| `frontend/src/components/DataPreview.tsx` | modify | Drive panel from the resolved provider; route figure results through the image path. |
| Renderer host/loader + sandbox bridge (new frontend module) | create | Dynamic-import + sandbox + typed host bridge (data access, hints) with API versioning. |
| Core base-type viewers (`frontend/src/components/DataPreview.parts/` — array/series/text/composite; `TableViewer` already exists) | create/modify | Basic viewers for the FR-003 base types; composite slot inspector per FR-004. |
| `frontend/src/components/DataPreview.parts/ImageViewer.tsx` | delete (move) | Migrated into the imaging package per FR-018. |
| `packages/scistudio-blocks-imaging/**` | modify | Register and ship the `Image` renderer (the migrated viewer) and its renderer-API version. |
| User project plot config/template | create | The fixed plot-function signature and a fill-in scaffold users edit. |
| `docs/adr/ADR-048.md`, `docs/specs/adr-048-extensible-preview.md` | create | This decision and contract. |

New modules are listed by role; their final paths are fixed during
implementation and are not yet created (this task is docs-only).

### 4.3 Implementation Sequence

1. **Resolution chain + core viewers (US1)**: introduce the provider chain and
   move the current behavior behind it as core base-type viewers, preserving
   today's previews. Net-neutral.
2. **User plot backend execution (US2)**: the plot-function contract, output
   binding, lazy isolated execution, figure caching, and save/export.
3. **Collection-aware data access (supports US3/US4)**: enumerate/read API over
   a collection reference, and the length-one wrapping of single objects.
4. **Renderer registration + runtime loader + sandbox (US3)**: the
   `scistudio.preview_renderers` entry point, dynamic import, sandbox bridge,
   and API versioning.
5. **Migrate the image viewer into imaging (US3, dogfood)**: register it as the
   `Image` renderer; remove imaging-specific viewer code from core; keep a
   basic core `Array` viewer.
6. **Collection-together plotting (US4)**: the user plot receives the whole
   collection; verify multi-object overlay.

Steps 4–5 are the heaviest. They sit behind the chain from step 1, so steps 1–3
deliver value without waiting on the runtime loader.

### 4.4 Verification Plan

- **Backend tests**: provider resolution honors the FR-001 priority and
  fall-through; core base-type producers (incl. the composite slot inspector);
  user-plot execution runs under isolation and caches a figure; collection
  enumerate/read access; renderer registration discovery and version gating.
- **Frontend tests**: provider-driven rendering replaces the `kind` switch;
  core viewers render each base type; the renderer host loads a module, applies
  the sandbox bridge, and falls back on unsupported API version; figure results
  route through the image path.
- **End-to-end (Chrome smoke)**: a user plot bound to a real block output
  renders and exports; the migrated imaging `Image` renderer loads at runtime
  and renders; removing it falls back to the core array viewer. (Per the
  repository rule that UI-touching work needs a live smoke test, not only unit
  tests.)
- **Checks**: `ruff`/`mypy`, frontend lint/typecheck/test/build, ADR-042 full
  audit, and the workflow-gate docs/closure checks for this spec and ADR-048.
- **Security check**: confirm a package renderer cannot read host credentials,
  host storage, or host DOM outside the sandbox bridge.

### 4.5 Risks And Rollback

- **Running package JavaScript in the host (highest risk)**: mitigated by the
  sandbox (isolated frame + typed bridge) and renderer-API versioning. If the
  sandbox is not ready, tiers 1–2 (core viewers and user plots) still ship; the
  package-renderer tier stays behind the chain and is disabled.
- **Running user Python**: rides the existing block-execution isolation, so it
  introduces no new trust surface beyond what the runtime already accepts for
  block and package code.
- **Large collections**: reference-based access avoids a payload blow-up; user
  plots receive the whole collection and are documented as responsible for
  sampling rather than silently truncated.
- **Renderer-API churn**: versioning lets the host reject incompatible
  renderers and fall back, so an API change degrades to a core viewer rather
  than a broken panel.
- **Image viewer migration**: regression risk is bounded because core retains a
  basic array viewer; if the imaging renderer is absent, `Array` still
  previews.
- **Rollback**: the resolution chain can default to core viewers only, which
  reproduces today's behavior, so the extension surfaces can be disabled
  without removing the chain.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: With no package renderers and no user plots installed, every base
  type (Array, Series, DataFrame, Text, CompositeData, Artifact) previews
  through a core viewer with no regression relative to the current six preview
  kinds.
- **SC-002**: A user can add a matplotlib plot bound to a block output and see
  its figure in Preview without rebuilding or restarting the application.
- **SC-003**: Installing a package that registers a renderer for a type and
  reloading the app shows that renderer for the type's outputs with no frontend
  rebuild.
- **SC-004**: Disabling or removing a provider causes Preview to fall back to
  the next tier deterministically, ending at a core viewer.
- **SC-005**: A collection of N objects can be drawn together in a single figure
  by one user plot function.
- **SC-006**: The image viewer is served from the imaging package, and core
  contains no imaging-specific viewer code, while an `Array` still previews
  through the core array viewer.
- **SC-007**: A package renderer cannot access host credentials, host storage,
  or host DOM outside the sandbox bridge.

## 6. Assumptions

- A SciStudio collection is a reference under the ADR-031 reference-only data
  contract, so passing a reference and reading through the data-access API is
  feasible without a new transport. (Source: existing-system)
- Block execution runs in subprocess isolation (ADR-017/020/021/022), which
  user-plot execution reuses. (Source: adr)
- A data HTTP API exists (`/api/data/...`) and can be extended with
  collection enumerate/read access for renderers. (Source: existing-system)
- End users author Python/matplotlib, not JavaScript; only package authors ship
  JavaScript renderers. (Source: owner)
- Named axes (ADR-027) and the metadata store (ADR-032) remain the source of a
  type's preview-relevant metadata. (Source: existing-system)
- This spec is docs-only; implementation is sequenced after ADR-048 is
  accepted. (Source: owner)
