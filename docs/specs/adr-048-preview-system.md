---
spec_id: adr-048-preview-system
title: "ADR-048 Preview System Implementation And Migration Specification"
status: Planned
feature_branch: codex/adr-048-previewers-plot-jobs
created: 2026-06-10
input: "Owner-approved ADR-048 direction: replace hardcoded data previews with routed core/package/project previewers, migrate rich image viewing to the imaging package, and keep preview-side plot rendering as a distinct artifact viewer surface."
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
related_specs:
  - adr-048-ai-plot-tools
  - adr-048-developer-docs-refresh
scope:
  in:
    - Core previewer registry, router, sessions, bounded data access, API schemas, and compatibility adapters.
    - Core fallback previewers for DataFrame, Array, Series, Text, Artifact, CompositeData, Collection, and Plot artifacts.
    - Frontend PreviewHost, previewer manifest loading, routed fallback rendering, and preview cache state changes.
    - Package-owned previewer discovery through `scistudio.previewers`.
    - Project-local previewer discovery and explicit project default previewer selection.
    - Migration of rich Image and Label preview behavior from core/frontend hardcoding into `scistudio-blocks-imaging`.
    - Compatibility coverage for the existing `/api/data/{data_ref}/preview` behavior during migration.
  out:
    - Plot job authoring tools, plot manifest scaffolding, and plot execution. Those are governed by `adr-048-ai-plot-tools`.
    - Full package and block developer documentation rewrite. That is governed by `adr-048-developer-docs-refresh`.
    - Adding domain previewers for LCMS, SRS, or other packages beyond imaging.
    - Turning previewers into workflow nodes, lineage producers, or scheduler-visible DAG work.
    - Loading remote third-party JavaScript from arbitrary URLs.
governs:
  modules:
    - scistudio.api.runtime
    - scistudio.api.routes.data
    - scistudio.api.schemas
  contracts:
    - scistudio.api.runtime.ApiRuntime.preview_data
    - scistudio.api.schemas.DataPreviewResponse
  entry_points:
    - scistudio.previewers
  files:
    - docs/adr/ADR-048.md
    - docs/specs/adr-048-preview-system.md
    - src/scistudio/api/runtime/**
    - src/scistudio/api/routes/data.py
    - src/scistudio/api/schemas.py
    - src/scistudio/ai/agent/mcp/tools_inspection/**
    - frontend/src/components/DataPreview.tsx
    - frontend/src/components/DataPreview.parts/**
    - frontend/src/store/previewSlice.ts
    - frontend/src/store/types.ts
    - frontend/src/types/api.ts
    - frontend/src/lib/api/data.ts
    - packages/scistudio-blocks-imaging/**
tests:
  - tests/previewers/test_preview_registry.py
  - tests/previewers/test_preview_routing.py
  - tests/previewers/test_preview_data_access.py
  - tests/api/test_previewers.py
  - tests/api/test_data.py
  - tests/api/test_runtime_import_surface.py
  - tests/ai/test_mcp_tools_inspection.py
  - frontend/src/components/DataPreview.test.tsx
  - frontend/src/components/DataPreview.parts/PreviewHost.test.tsx
  - packages/scistudio-blocks-imaging/tests/test_previewer_registration.py
acceptance_source: adr
language_source: en
---

# ADR-048 Preview System Implementation And Migration Specification

## 1. Change Summary

This spec implements the previewer half of ADR-048. SciStudio currently previews
data through hardcoded backend branches in `ApiRuntime.preview_data` and a
frontend renderer switch on `preview.kind`. That model is no longer sufficient:
packages need to own interactive viewers for package-defined data types,
projects need local preview overrides, and core should keep only generic
fallback viewers for base scientific data shapes.

The implementation must introduce a routed preview subsystem with these
properties:

- core owns routing, session lifecycle, safety limits, data access helpers, API
  compatibility, and generic fallback viewers;
- installed packages register previewers through a dedicated
  `scistudio.previewers` entry point;
- projects may register project-local previewers and project defaults;
- rich image and label viewing moves to `scistudio-blocks-imaging`;
- current REST and frontend preview behavior remains covered by compatibility
  tests while the new PreviewHost takes over;
- previewers inspect existing data references and collections without becoming
  workflow truth.

Plot jobs are intentionally not implemented here. This spec only defines the
`PlotPreviewer` that renders static plot artifacts created by the companion plot
tooling spec.

## 2. User Scenarios & Testing

### User Story 1 - Core fallback preview still works without packages (Priority: P1)

As a user with a minimal SciStudio installation, I need DataFrame, Array,
Series, Text, Artifact, CompositeData, Collection, and plot artifact previews to
remain visible without installing domain packages.

Independent Test: Start the API with only core previewers registered; create
fixtures for every base type; verify each target routes to a core previewer and
returns a bounded `PreviewEnvelope`.

Acceptance Scenarios:

1. Given a DataFrame reference, when the preview route is requested, then the
   result includes paginated rows, column metadata, total row count, and
   truncation or sampling metadata.
2. Given a 3-D Array reference, when the preview route is requested, then the
   result includes shape, dtype, axis selection metadata, and one bounded 2-D
   plane without materializing the whole array. The plane is surfaced as the
   actual numeric `matrix` plus its finite `vmin`/`vmax`, and every
   non-displayed axis is returned as an independently selectable `slice_axes`
   descriptor (driven by a per-axis `axis_indices` query field), so the
   frontend renders a value-readable numeric heatmap table — not a lossy
   grayscale image — and the full N-D array stays navigable (#1603).
3. Given a CompositeData reference, when the preview route is requested, then
   the result lists slots, slot data types, and child preview actions without
   eagerly rendering every slot.

### User Story 2 - Package previewer wins for package-defined types (Priority: P1)

As an imaging package author, I need `Image` and `Label` data to mount a rich
package-owned viewer with slice, LUT, brightness, metadata, and overlay controls
instead of core pretending that images are ordinary arrays.

Independent Test: Install or enable `scistudio-blocks-imaging`; register image
previewers through `scistudio.previewers`; verify `Image` and `Label` route to
the package previewer while plain core arrays still route to `core.array.basic`.

Acceptance Scenarios:

1. Given an `Image` reference and the imaging package installed, when the
   preview router resolves a provider, then it selects the imaging previewer.
2. Given the same payload stored as a base `Array`, when the preview router
   resolves a provider, then it selects the core `ArrayPreviewer`.
3. Given the imaging previewer frontend manifest fails validation, when the UI
   opens the preview, then the host shows diagnostics and falls back to a safe
   core preview where possible.

### User Story 3 - Project previewer overrides package defaults (Priority: P1)

As a scientist working in one project, I need a project-local viewer for a type
without forking a package or changing global SciStudio behavior.

Independent Test: Create a project-local previewer for a fixture type that is
also supported by a package previewer; verify project exact-type routing wins,
and removing the project previewer falls back to the package previewer.

Acceptance Scenarios:

1. Given a project previewer for `MyType`, when a `MyType` reference is
   previewed, then the project previewer is selected before any package
   previewer.
2. Given two project previewers tied on type and priority, when neither is set
   as the project default, then the router returns an ambiguity error.
3. Given a project default previewer declaration for `MyType`, when tied
   previewers exist, then the declared default is selected.

### User Story 4 - A block output collection is previewed as a collection (Priority: P1)

As a user who ran a block that produced ten images, I need the preview panel to
show that output as one collection first, then let me inspect individual images
or collection-level package views.

Independent Test: Build a workflow output fixture where one output port points
to `Collection[Image]`; verify PreviewHost requests the collection target, shows
collection count and item types, and routes to the imaging collection previewer
when present.

Acceptance Scenarios:

1. Given `Collection[Image]` and the imaging previewer installed, when the
   output is selected, then the previewer can show an image collection/gallery
   view instead of ten unrelated flat ref pills.
2. Given no collection-specific previewer, when the output is selected, then
   the core collection fallback lists item refs, types, and bounded samples.
3. Given the user selects one sampled collection item, when PreviewHost requests
   a child preview, then item-level routing uses the same project/package/core
   precedence rules.

### User Story 5 - Existing API clients do not break during migration (Priority: P1)

As a maintainer, I need current REST preview callers and tests to keep working
until they intentionally move to the session API.

Independent Test: Run the existing data preview API tests after routing through
the new previewer core; verify current `DataPreviewResponse` behavior is either
preserved or explicitly versioned with compatibility assertions.

Acceptance Scenarios:

1. Given a request to `GET /api/data/{data_ref}/preview`, when the target is a
   table, text, series, composite, array, or artifact, then the route returns a
   shape compatible with current frontend callers.
2. Given a request with table pagination or sort parameters, when routed through
   the new previewer, then page and sort semantics remain stable.
3. Given a request with image slice parameters during the migration window, when
   the imaging previewer is unavailable, then the compatibility route still
   returns a bounded fallback rather than crashing.

### Edge Cases

- Unknown data reference returns a stable 404 without leaking filesystem paths.
- Registered type class is missing or stale; router falls back to recorded type
  name and core artifact diagnostics.
- Two packages register the same previewer ID.
- Two previewers tie on owner tier, type specificity, and priority.
- A child type has no exact previewer but its parent type has one.
- A package previewer registers a frontend manifest but no backend provider.
- A backend provider exists but its frontend bundle is missing from the wheel.
- Large Zarr/TIFF/Parquet inputs exceed preview budgets.
- A collection has unknown total length or contains mixed item types.
- SVG plot artifact includes executable content.
- Preview session is requested after the underlying data record is deleted.

## 3. Requirements

### Functional Requirements

- FR-001: The implementation must create a core `scistudio.previewers` package
  containing registry, routing, model, session, data-access, fallback previewer,
  and API adapter modules.
- FR-002: The preview registry must load core previewers unconditionally,
  package previewers from `scistudio.previewers` entry points, and project
  previewers from the active project configuration.
- FR-003: Previewer resolution must follow ADR-048 precedence: project exact
  collection, project exact item, package exact collection, package exact item,
  project parent, package parent, core collection fallback, core base fallback,
  then unknown/error fallback.
- FR-004: Within the same precedence tier and type specificity, the router must
  select the highest priority previewer and must report ambiguity when priority
  ties remain unresolved.
- FR-005: Projects must be able to declare explicit default previewers for a
  target type to resolve otherwise ambiguous project or package matches.
- FR-006: Previewers must declare stable IDs, owner kind, target type,
  collection support, priority, capabilities, backend provider, and optional
  frontend manifest.
- FR-007: The backend must expose a typed preview session API for routed
  previewers and keep `GET /api/data/{data_ref}/preview` as a compatibility
  adapter during migration.
- FR-008: The compatibility adapter must continue to support current table
  pagination, sorting, slice index, and basic preview payload behavior until
  the frontend no longer depends on the old contract.
- FR-009: `PreviewDataAccess` must provide bounded helpers for DataFrame,
  Array, Series, Text, Artifact, CompositeData, and Collection targets.
- FR-010: Previewers must not call eager materialization helpers on large data
  unless `PreviewDataAccess` has verified the target is within budget.
- FR-011: Every preview envelope must state whether the displayed data is
  sampled, truncated, cached, derived, complete, or failed.
- FR-012: Core must provide fallback previewers for DataFrame, Array, Series,
  Text, Artifact, CompositeData, Collection, and Plot artifacts.
- FR-013: Core `ArrayPreviewer` must be generic numeric array inspection only:
  shape, dtype, axis metadata, scalar display, 1-D chart/table, 2-D matrix
  display, bounded N-D slicing, and generic colormap/range controls. The 2-D
  matrix display renders the actual numeric values as a heatmap table (each
  cell shows its number, colored by a real diverging/sequential colormap with
  a min..max value-scale legend; signed data is not clipped), and bounded N-D
  slicing exposes one index selector per non-displayed axis so the whole array
  is navigable (#1603).
- FR-014: Core `ArrayPreviewer` must not implement image-domain controls such as
  OME metadata browsing, channel merge, label overlay, or imaging LUT semantics.
- FR-015: Core `SeriesPreviewer` must provide both chart and table modes and
  must decimate or sample large chart data under a declared budget.
- FR-016: Core `TextPreviewer` must render bounded safe plain text, mark
  truncation, and expose editor handoff metadata for long text.
- FR-017: Core `CompositePreviewer` must render slot inventory first and must
  route child slot previews only when selected.
- FR-018: Core `PlotPreviewer` must display PNG, JPEG, SVG, and PDF artifacts
  and must expose save/export controls for each supported format.
- FR-019: SVG rendering must be sanitized or sandboxed so script execution and
  external resource loading do not run in the app context.
- FR-020: Frontend `PreviewHost` must mount previewers by validated manifest and
  otherwise render core fallback components.
- FR-021: Frontend preview state must key caches by data reference or collection
  reference, previewer ID, session ID, query parameters, slice/page/sort state,
  and data version when available.
- FR-022: Frontend extension modules must be loaded only from backend-validated
  same-origin URLs.
- FR-023: Previewer frontend components must receive a constrained host API and
  must not receive direct workflow mutation primitives.
- FR-024: Package-owned frontend assets must be wheel-packaged, fingerprinted or
  versioned, path-confined, and served by the backend only after manifest
  validation.
- FR-025: `scistudio-blocks-imaging` must register package previewers for
  `Image` and `Label`, including frontend assets and backend provider code.
- FR-026: Removing or disabling `scistudio-blocks-imaging` must leave base Array
  previews functional through core fallback behavior.
- FR-027: The MCP inspection `preview_data` tool must either wrap the same
  bounded data-access helpers or explicitly retain a compatibility adapter with
  tests proving its 8 MiB response cap remains intact.
- FR-028: Preview failures must not mutate workflow definitions, data objects,
  lineage records, or downstream outputs.
- FR-029: The implementation must add deterministic diagnostic payloads for
  unknown previewers, missing frontend bundles, provider exceptions, and routing
  ambiguity.
- FR-030: Previewer discovery must support monorepo package development in the
  same spirit as existing block and type registry monorepo fallbacks.

### Key Entities

`PreviewTarget` identifies what is being previewed:

| Field | Meaning |
|---|---|
| `kind` | `data_ref`, `collection_ref`, `artifact`, or `plot_artifact`. |
| `ref` | Data, collection, or artifact reference. |
| `recorded_type` | Recorded type name or type chain from storage metadata. |
| `collection_item_type` | Known item type when the target is a collection. |
| `source` | Optional workflow/node/output identity for UI display. |

`PreviewerSpec` declares a provider:

| Field | Meaning |
|---|---|
| `previewer_id` | Stable ID, for example `core.array.basic`. |
| `owner_kind` | `core`, `package`, or `project`. |
| `owner_name` | Package name, project identifier, or `scistudio`. |
| `target_type` | Fully qualified target type name. |
| `supports_collection` | Whether the previewer can inspect collections. |
| `priority` | Integer priority within one tier and specificity. |
| `capabilities` | Feature strings such as `slice`, `table`, `lut`, `export`. |
| `backend_provider` | Import path or callable reference for backend provider. |
| `frontend_manifest` | Optional same-origin manifest descriptor. |
| `api_version` | Previewer API compatibility version. |

`PreviewEnvelope` is the canonical backend response:

| Field | Meaning |
|---|---|
| `session_id` | Preview session ID or null for one-shot compatibility previews. |
| `previewer_id` | Selected previewer ID. |
| `target` | Normalized `PreviewTarget`. |
| `kind` | Canonical fallback kind: `dataframe`, `array`, `series`, `text`, `artifact`, `composite`, `collection`, `plot`, or `error`. |
| `payload` | Previewer-owned bounded payload. |
| `resources` | Session resource descriptors for follow-up reads. |
| `metadata` | Shape, type, sampling, truncation, and display metadata. |
| `diagnostics` | Non-fatal warnings and repair hints. |
| `error` | Typed error when preview failed. |

`PreviewSession` is backend-owned:

| Field | Meaning |
|---|---|
| `session_id` | Opaque session identifier. |
| `previewer_id` | Mounted previewer. |
| `target` | Target reference and type. |
| `created_at` | Creation time. |
| `query` | Normalized query state such as slice, page, sort, or selected slot. |
| `cache_key` | Preview cache key where applicable. |
| `limits` | Applied row, byte, item, tile, and response limits. |

`PreviewDataAccess` must be a narrow helper surface. It should expose bounded
methods such as `dataframe_page`, `array_plane`, `array_tile`,
`series_points`, `text_chunk`, `artifact_metadata`, `composite_slots`, and
`collection_sample`. It should not expose arbitrary storage paths to frontend
code.

### API Shape

The implementation should add a session-oriented API while retaining the old
route:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/data/{data_ref}/preview` | Backward-compatible one-shot preview adapter. |
| `POST` | `/api/previews/sessions` | Create a routed preview session for a target. |
| `GET` | `/api/previews/sessions/{session_id}` | Read current envelope and provider metadata. |
| `PATCH` | `/api/previews/sessions/{session_id}` | Update query state such as slice, page, sort, slot, or item. |
| `GET` | `/api/previews/sessions/{session_id}/resources/{resource_id}` | Fetch bounded provider resource data. |
| `GET` | `/api/previews/assets/{asset_id}` | Serve validated same-origin frontend assets. |

Session resource descriptors may include provider-defined `params`. Clients
must copy those params into the resource request as a URL-encoded JSON object in
the `params` query parameter. The backend must reject non-object, oversized, or
deeply nested params before dispatching to provider/session code, and resource
params must not override private runtime-enrichment query keys.

Exact route names may change during implementation if the API module already
has a stronger convention, but the semantics above are required.

## 4. Implementation Plan

### 4.1 Technical Approach

Build the previewer core behind the existing preview API first, then migrate the
frontend and imaging package onto the new contract. The target architecture is:

1. `PreviewerRegistry` loads core, package, and project specs.
2. `PreviewRouter` resolves a `PreviewTarget` to one spec or a typed routing
   error.
3. `PreviewSessionManager` creates backend sessions and calls providers.
4. `PreviewDataAccess` performs bounded reads and returns typed helper results.
5. REST compatibility adapts canonical `PreviewEnvelope` objects to the current
   `DataPreviewResponse` shape where needed.
6. Frontend `PreviewHost` mounts routed previewers or local fallback viewers.
7. The imaging package registers rich previewers and owns image-specific UI.

Provider code should run inside normal SciStudio server process boundaries for
metadata and bounded reads. Long-running work belongs to plot jobs or future
background preview tasks, not synchronous provider calls.

### 4.2 Affected Files

Backend core:

- Create `src/scistudio/previewers/__init__.py`.
- Create `src/scistudio/previewers/models.py`.
- Create `src/scistudio/previewers/registry.py`.
- Create `src/scistudio/previewers/router.py`.
- Create `src/scistudio/previewers/session.py`.
- Create `src/scistudio/previewers/data_access.py`.
- Create `src/scistudio/previewers/fallbacks.py`.
- Create `src/scistudio/previewers/assets.py`.
- Create `src/scistudio/previewers/project.py`.
- Update `src/scistudio/api/runtime/_data.py` to delegate preview work to the
  preview subsystem.
- Update `src/scistudio/api/runtime/_preview_cache.py` and
  `src/scistudio/api/runtime/_preview_image.py` by moving reusable bounded
  helpers behind `PreviewDataAccess` or keeping them as compatibility wrappers.
- Update `src/scistudio/api/routes/data.py` and `src/scistudio/api/schemas.py`
  for session APIs and typed schemas.
- Update `src/scistudio/ai/agent/mcp/tools_inspection/**` only to share bounded
  preview data access or preserve tested compatibility.

Frontend:

- Update `frontend/src/components/DataPreview.tsx` into a `PreviewHost`
  container.
- Add or replace `frontend/src/components/DataPreview.parts/PreviewHost.tsx`.
- Update `PreviewRenderer.tsx` into fallback-renderer logic.
- Split current `ImageViewer.tsx` into generic core array behavior and
  package-owned imaging behavior.
- Update `TableViewer.tsx`, `useSlicePreview.ts`, `useOmeMetadata.ts`,
  `refEntries.ts`, and `luts.ts` according to the new fallback/provider
  boundary.
- Update `frontend/src/lib/api/data.ts` with session and resource helpers.
- Update `frontend/src/types/api.ts`, `frontend/src/store/types.ts`, and
  `frontend/src/store/previewSlice.ts`.

Package migration:

- Update `packages/scistudio-blocks-imaging/pyproject.toml` with a
  `scistudio.previewers` entry point.
- Add `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers/**`.
- Update `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/__init__.py`
  only if the package root remains the previewer export surface.
- Add frontend asset build or packaging support for the imaging previewer.

### 4.3 Implementation Sequence

1. Add previewer models and core fallback provider interfaces without changing
   routes.
2. Add registry discovery for core previewers and unit tests for duplicate IDs,
   invalid specs, and basic package entry-point loading.
3. Add router resolution tests for exact match, collection match, parent
   fallback, priority, project override, and ambiguity.
4. Add `PreviewDataAccess` and migrate table, text, array, series, composite,
   artifact, and collection reads behind bounded helpers.
5. Route `ApiRuntime.preview_data` through the new subsystem while preserving
   the existing REST response shape.
6. Add session API schemas and routes.
7. Introduce frontend `PreviewHost` with core fallback components and session
   API usage.
8. Implement same-origin manifest validation and dynamic module loading for
   package/project previewers.
9. Move rich image viewer behavior into the imaging package and register
   `Image`/`Label` previewers.
10. Remove core image-specific behavior once imaging package coverage and core
    array fallback coverage are both green.
11. Update MCP inspection sharing or compatibility tests.
12. Run backend, frontend, package, and packaging verification before PR
    readiness.

### 4.4 Verification Plan

Backend unit tests:

- registry loads core, package, monorepo, and project previewers;
- duplicate previewer IDs fail;
- invalid manifests fail with diagnostics;
- router precedence matches ADR-048;
- ambiguity errors are typed and deterministic;
- preview data access enforces row, byte, item, tile, and dimension budgets;
- array access for large Zarr/TIFF fixtures reads bounded slices only;
- table preview preserves current pagination and sorting behavior;
- series preview decimates chart data and paginates table data;
- text preview marks truncation;
- composite preview lists slots without eager child rendering;
- plot previewer validates PNG, JPEG, SVG, and PDF artifact metadata.

API tests:

- old `/api/data/{ref}/preview` route remains compatible for current test
  fixtures;
- new session routes create, read, patch, and fetch resources;
- provider exceptions return preview errors without API crashes;
- missing refs and stale sessions return stable errors.

Frontend tests:

- `PreviewHost` creates sessions, mounts fallback viewers, and shows provider
  diagnostics;
- preview cache keys include provider/session/query state;
- collection outputs render collection-level previews;
- dynamic manifest load failure falls back cleanly;
- table pagination and sort requests still work;
- plot artifact SVG/PDF export controls render.

Package tests:

- imaging package exposes `scistudio.previewers`;
- `Image` and `Label` route to package previewers;
- package frontend assets are included in the wheel;
- core fallback previews still work when imaging previewers are absent.

Manual checks:

- run a workflow outputting ten images and confirm collection-level preview;
- interact with slice/LUT controls from the imaging package previewer;
- disable the imaging package and confirm generic array preview remains useful;
- open DataFrame, Series, Text, CompositeData, and Artifact previews;
- render SVG and PDF plot artifacts through `PlotPreviewer`.

### 4.5 Risks And Rollback

Risk: Dynamic frontend module loading introduces packaging and runtime failure
modes.

Mitigation: Require backend manifest validation, same-origin asset serving,
typed diagnostics, and core fallback rendering. Rollback by disabling external
manifests while keeping core fallback previewers.

Risk: Moving image behavior out of core can break existing workflows.

Mitigation: Land compatibility adapters and imaging package tests before
removing old image-specific code. Rollback by keeping the legacy viewer mounted
as an internal package-style provider until imaging assets stabilize.

Risk: Preview data access can accidentally materialize large arrays.

Mitigation: Put budget checks in `PreviewDataAccess`, test Zarr/TIFF bounded
reads, and ban direct `to_memory()` use inside fallback previewers except for
verified small objects.

Risk: Project-local previewers expand the authoring surface too quickly.

Mitigation: Support backend Python registration and same-origin packaged assets
first. Treat project-local React build tooling as a documented advanced path
with validation, not as implicit arbitrary script loading.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: All current data preview API tests pass through the new previewer
  subsystem or have explicit migration assertions approved by ADR-048.
- SC-002: Router tests cover project/package/core precedence, collection
  routing, parent fallback, priority, explicit defaults, and ambiguity errors.
- SC-003: Core fallback viewers exist for DataFrame, Array, Series, Text,
  Artifact, CompositeData, Collection, and Plot artifacts.
- SC-004: Large-array tests prove the REST preview path no longer reads entire
  large Zarr or TIFF payloads for a bounded preview.
- SC-005: `scistudio-blocks-imaging` registers image and label previewers
  through `scistudio.previewers`.
- SC-006: Frontend tests prove PreviewHost can mount core fallbacks and can
  degrade cleanly when a package previewer manifest fails.
- SC-007: SVG and PDF plot artifacts render through `PlotPreviewer` and expose
  save/export actions.
- SC-008: MCP inspection preview tests still enforce bounded response behavior.
- SC-009: Wheel packaging tests include previewer Python modules and frontend
  assets for package-owned previewers.
- SC-010: Manual smoke verifies the ten-image collection scenario described in
  ADR-048.

## 6. Assumptions

- The active project runtime can identify workflow node ID and output port for
  selected preview targets, even if the old UI currently flattens refs.
- Existing DataObject type registry metadata is sufficient to resolve parent
  type fallback for registered types.
- Preview frontend assets can be packaged with wheels and served same-origin by
  the SciStudio API.
- The first implementation may keep compatibility adapters while new session
  APIs are introduced, as long as the adapters are tested and scheduled for
  removal or retention by follow-up issue.
- Rerendering plot artifacts is governed by `adr-048-ai-plot-tools`; this spec
  only displays already-created plot artifacts.
