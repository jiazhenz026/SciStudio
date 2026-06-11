# ADR-048 Preview System Scope Report

## Summary

SPEC 1 should treat the current preview implementation as a migration from a
hardcoded REST/UI preview path into an ADR-048 routed previewer architecture.
The current backend path is concentrated in `src/scistudio/api/runtime/_data.py`
and `src/scistudio/api/routes/data.py`, with helper modules for table cache and
raster thumbnail generation. The current frontend path is concentrated in
`frontend/src/components/DataPreview.tsx`, `frontend/src/components/DataPreview.parts/**`,
`frontend/src/store/previewSlice.ts`, `frontend/src/lib/api/data.ts`, and
`frontend/src/types/api.ts`.

The highest-risk seam is that there are two existing preview contracts:

- UI/REST preview returns `DataPreviewResponse { ref, type_name, preview }`,
  where `preview.kind` drives frontend rendering.
- AI/MCP inspection preview returns `PreviewDataResult { fmt, payload,
  truncated }` and already has stronger bounded-read behavior.

SPEC 1 should define whether these remain separate adapters over a shared
previewer core, or whether one canonical preview envelope replaces both with
compatibility shims.

## Current Surfaces

### Backend REST preview path

- `src/scistudio/api/routes/data.py:65` defines
  `GET /api/data/{data_ref}/preview`.
- `src/scistudio/api/routes/data.py:66-74` accepts `slice`, `page`,
  `page_size`, `sort_by`, and `sort_dir`.
- `src/scistudio/api/routes/data.py:86-98` resolves the data record, delegates
  to `runtime.preview_data(...)`, maps unknown refs to 404, and returns
  `DataPreviewResponse(ref=record.id, type_name=record.type_name,
  preview=preview)`.
- `src/scistudio/api/schemas.py:230-235` defines the current REST response
  shape as `ref`, `type_name`, and free-form `preview`. There is no typed
  preview envelope, previewer identity, session ID, truncation flag, sampling
  flag, or metadata field in this schema.

### Backend runtime preview dispatch

- `src/scistudio/api/runtime/_data.py:134-142` implements
  `preview_data(self, data_ref, slice_index, page, page_size, sort_by,
  sort_dir)`.
- `src/scistudio/api/runtime/_data.py:159-164` resolves the `DataRecord`,
  `StorageReference`, path suffix, and registered class.
- `src/scistudio/api/runtime/_data.py:169-207` returns table previews:
  `kind`, `columns`, `rows`, `total_rows`, backward-compatible `row_count`,
  `page`, `page_size`, `total_pages`, `sort_by`, and `sort_dir`.
- `src/scistudio/api/runtime/_data.py:212-227` returns text previews:
  `kind`, `content`, and `language`.
- `src/scistudio/api/runtime/_data.py:232-287` returns array/image previews:
  `kind: image`, `shape`, `axes`, `slice_axis_name`, `slice_axis_size`,
  `slice_index`, `thumbnail`, and `src`; read failures fall back to
  `kind: artifact`.
- `src/scistudio/api/runtime/_data.py:292-298` returns series previews as
  `kind: chart` with `points`.
- `src/scistudio/api/runtime/_data.py:303-329` returns composite previews as
  either a raster slot image or `kind: composite` with `slots`.
- `src/scistudio/api/runtime/_data.py:331-335` falls through to
  `kind: artifact` with `path` and `mime_type`.

### Backend preview helpers and limits

- `src/scistudio/api/runtime/_preview_cache.py:21-38` defines
  `MAX_TABLE_PAGE_SIZE = 200` and an in-process LRU table cache.
- `src/scistudio/api/runtime/_preview_cache.py:56-111` reads and optionally
  sorts CSV/parquet tables via `pyarrow`, preserving a monkeypatchable package
  re-export path.
- `src/scistudio/api/runtime/_preview_image.py:23-46` infers type names from
  `type_chain`, format, or suffix.
- `src/scistudio/api/runtime/_preview_image.py:49-81` creates a grayscale PNG
  data URI from a 2D matrix.
- `src/scistudio/api/runtime/_preview_image.py:84-105` loads TIFF and Zarr
  preview matrices. The Zarr branch currently uses `node[...]` or
  `data_array[...]`, so SPEC 1 should not assume the REST preview path is
  already bounded for large arrays.
- `src/scistudio/api/runtime/_preview_image.py:108-125` downsamples a 2D matrix
  to a 256-pixel maximum dimension.

### AI/MCP preview path

- `src/scistudio/ai/agent/mcp/tools_inspection/read.py:168-180` exposes an
  MCP `preview_data` tool with an advisory `fmt`.
- `src/scistudio/ai/agent/mcp/tools_inspection/read.py:181-199` documents the
  current bounded-preview contract and the 8 MiB response cap.
- `src/scistudio/ai/agent/mcp/tools_inspection/read.py:213-228` dispatches by
  type chain and suffix to `_preview_dataframe`, `_preview_series`,
  `_preview_array`, `_preview_text`, or `_preview_artifact`.
- `src/scistudio/ai/agent/mcp/tools_inspection/_models.py:44-49` defines
  `PreviewDataResult` as `fmt`, `payload`, and `truncated`.
- `src/scistudio/ai/agent/mcp/tools_inspection/_preview.py:69-139` implements
  streaming table previews.
- `src/scistudio/ai/agent/mcp/tools_inspection/_preview.py:142-217` implements
  bounded array thumbnails with TIFF memmap/Zarr reads and `png_base64`
  payloads.
- `src/scistudio/ai/agent/mcp/tools_inspection/_preview.py:220-256`
  implements series, text, and artifact payloads.

### Frontend preview host and renderer

- `frontend/src/components/DataPreview.tsx:37-61` is the current preview host:
  it extracts refs from selected block outputs, delegates selection/slice state
  to `useSlicePreview`, and loads OME metadata through `useOmeMetadata`.
- `frontend/src/components/DataPreview.tsx:105-129` renders output ref pills
  and passes `preview.preview` into `PreviewRenderer`.
- `frontend/src/components/DataPreview.tsx:130-147` mounts the OME metadata
  affordance alongside the renderer.
- `frontend/src/components/DataPreview.parts/PreviewRenderer.tsx:98-117`
  switches directly on `preview.kind` for `table`, `image`, `chart`, `text`,
  `composite`, and artifact fallback.
- `frontend/src/components/DataPreview.parts/refEntries.ts:48-59` recursively
  flattens nested output payloads and collections into individual `data_ref`
  pills. There is no collection-level preview host today.
- `frontend/src/components/DataPreview.parts/useOmeMetadata.ts:10-13`
  says preview responses can include metadata, but
  `frontend/src/types/api.ts:224-228` and `src/scistudio/api/schemas.py:230-235`
  do not currently model metadata on preview responses. The hook falls back to
  `/api/data/{ref}`.

### Frontend image, table, and slice behavior

- `frontend/src/components/DataPreview.parts/ImageViewer.tsx:5-20` defines the
  current image preview props.
- `frontend/src/components/DataPreview.parts/ImageViewer.tsx:27-94` implements
  pan/zoom state.
- `frontend/src/components/DataPreview.parts/ImageViewer.tsx:96-141` implements
  client-side LUT and display min/max processing.
- `frontend/src/components/DataPreview.parts/ImageViewer.tsx:218-249`
  implements the single-axis slice slider.
- `frontend/src/components/DataPreview.parts/ImageViewer.tsx:378-449` composes
  canvas, slider, zoom controls, LUT selector, and display range controls.
- `frontend/src/components/DataPreview.parts/TableViewer.tsx:29-57` adapts the
  current table payload into table viewer state.
- `frontend/src/components/DataPreview.parts/TableViewer.tsx:74-119` performs
  page/sort follow-up requests via `api.getDataPreview`.
- `frontend/src/components/DataPreview.parts/useSlicePreview.ts:23-151` owns
  active ref, active slice, local non-zero-slice cache, 200 ms debounce, and
  stale preview fallback.

### Frontend store and API types

- `frontend/src/lib/api/data.ts:26-38` constructs `/api/data/{ref}/preview`
  URLs and maps TypeScript camel-case `pageSize`, `sortBy`, and `sortDir` to
  backend query parameters.
- `frontend/src/types/api.ts:224-240` defines `DataPreviewResponse` and
  `DataPreviewQuery`.
- `frontend/src/store/types.ts:178-183` defines `PreviewSlice` as
  `previewCache`, `previewLoading`, `cachePreview`, and `setPreviewLoading`.
- `frontend/src/store/previewSlice.ts:5-25` caches preview responses by
  `payload.ref` only. It does not distinguish previewer ID, session, query
  params, slice, table page, or sort state.

### Package and imaging boundaries

- `src/scistudio/core/types/array.py:6-10` states that legacy image subclasses
  were removed from core and now live in `scistudio-blocks-imaging`.
- `packages/scistudio-blocks-imaging/pyproject.toml:49-53` declares
  `scistudio.blocks` and `scistudio.types` entry points only. There is no
  `scistudio.previewers` entry point today.
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/__init__.py:54-130`
  exports imaging types and blocks through `get_types`, `get_blocks`, and
  `get_block_package`.
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/types.py:19-50`
  defines `Image` and image metadata, including OME metadata.
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/types.py:84-104`
  defines `Label` as composite data with raster/polygons slots and OME metadata.
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/visualization/render.py:22-230`
  contains image rendering blocks that produce artifacts, but those are
  workflow blocks, not previewers.

### Existing discovery patterns to mirror or avoid

- `src/scistudio/blocks/registry/_scan.py:219-323` discovers
  `scistudio.blocks` entry points and supports callable package protocols.
- `src/scistudio/blocks/registry/_scan.py:325-406` has a monorepo fallback for
  `packages/scistudio-blocks-*`.
- `src/scistudio/core/types/registry.py:374-468` discovers
  `scistudio.types` entry points and monorepo/project-local types.
- `src/scistudio/cli/templates/block_package/pyproject.toml.tpl:21-22`
  scaffolds only a `scistudio.blocks` entry point.

## Proposed In-Scope Files

### Backend implementation surface

- `src/scistudio/previewers/**`: create the core previewer package, including
  registry, router, specs, fallback previewers, data-access helpers, sessions,
  and compatibility adapters.
- `src/scistudio/api/runtime/_data.py`: migrate hardcoded
  `ApiRuntime.preview_data` dispatch to the preview router or a compatibility
  wrapper around it.
- `src/scistudio/api/runtime/_preview_cache.py`: either move table paging/cache
  behind `PreviewDataAccess` or preserve it as a helper used by the
  `DataFramePreviewer`.
- `src/scistudio/api/runtime/_preview_image.py`: split generic array access
  from image-specific behavior; keep only core fallback raster utilities if
  still needed.
- `src/scistudio/api/runtime/__init__.py`: update re-exports deliberately,
  because tests pin private helper import behavior.
- `src/scistudio/api/routes/data.py`: keep current endpoint compatibility or
  add preview session/provider endpoints under the same router.
- `src/scistudio/api/schemas.py`: add typed previewer/session/envelope schemas
  while preserving old `DataPreviewResponse` as needed.
- `src/scistudio/ai/agent/mcp/tools_inspection/**`: decide whether MCP
  `preview_data` becomes a compatibility wrapper over the same backend
  previewer data-access layer, or explicitly remains a separate bounded
  inspection tool.

### Frontend implementation surface

- `frontend/src/components/DataPreview.tsx`: migrate from a hardcoded preview
  panel to a preview host that can mount routed previewers and fallbacks.
- `frontend/src/components/DataPreview.parts/**`: preserve or replace
  `PreviewRenderer`, `TableViewer`, `ImageViewer`, `useSlicePreview`,
  `useOmeMetadata`, `refEntries`, and `luts` according to the new host/provider
  boundary.
- `frontend/src/store/previewSlice.ts`: update cache keys and state model for
  sessions, previewer IDs, query params, and errors.
- `frontend/src/store/types.ts`: update `PreviewSlice` and UI state types.
- `frontend/src/types/api.ts`: add typed previewer manifest, session, envelope,
  and provider response types.
- `frontend/src/lib/api/data.ts`: add previewer/session request helpers and
  compatibility query mapping.
- `frontend/src/api/capabilities.ts` and
  `frontend/src/components/OutputPreview/OMEMetadataPanel.tsx`: consider only
  if OME metadata moves into preview sessions or image-package previewers.

### Package migration surface

- `packages/scistudio-blocks-imaging/pyproject.toml`: add the package-owned
  previewer entry point when SPEC 1 defines the contract.
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/__init__.py`:
  export previewer registration callable(s) if the package root remains the
  package protocol surface.
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers/**`:
  create rich image/label previewer providers and manifests.
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/types.py`:
  use as target types for previewer registration; avoid changing type
  semantics unless SPEC 1 explicitly requires it.
- `packages/scistudio-blocks-imaging/tests/**`: add package-owned previewer
  registration and image fallback tests.
- `src/scistudio/cli/templates/block_package/**` and
  `docs/block-development/**`: update only if SPEC 1 includes author-facing
  previewer package documentation/scaffolding.

### Test surface

- `tests/api/test_data.py`: update compatibility tests for current REST shapes
  and add router/session/envelope tests.
- `tests/api/test_runtime_import_surface.py`: update public/private re-export
  expectations if preview helpers move.
- `tests/previewers/**`: create focused backend registry, routing,
  ambiguity, fallback, data-access, and sampling tests.
- `tests/api/test_previewers.py`: create API-level previewer tests if the
  implementation keeps route-level tests separate from unit router tests.
- `tests/ai/test_mcp_tools_inspection.py`,
  `tests/ai/test_mcp_fastmcp.py`, and
  `tests/ai/agent/mcp/test_tools_inspection_surface.py`: update only if MCP
  preview wraps the new preview data-access layer or response contract.
- `frontend/src/components/DataPreview.test.tsx`: update host/rendering tests.
- `frontend/src/components/DataPreview.parts/*.test.tsx`: add tests for
  `PreviewHost`, fallback viewers, manifest load errors, and table/image
  compatibility.
- `packages/scistudio-blocks-imaging/tests/test_previewer_registration.py`:
  create package registration tests.
- `tests/packaging/test_wheel_skills.py` or adjacent packaging tests: update
  only if previewer manifests/assets must be included in wheels.

## Out-Of-Scope

- The legacy old ADR-048 and old `adr-048-preview-providers` spec are not
  governing inputs for SPEC 1.
- Preview-side plot job execution, `plots/**` manifests, plot target discovery,
  `list_plot_targets`, `scaffold_plot`, `validate_plot`, and `run_plot_job`
  should be out of SPEC 1 unless SPEC 1 only reserves a `PlotPreviewer`
  fallback shape. Those belong in a separate plot-job implementation spec.
- `src/scistudio/blocks/code/**` runner/exchange changes should be out of
  SPEC 1 unless the spec explicitly implements plot jobs. Do not refactor
  CodeBlock just to prepare previewers.
- Workflow DAG, scheduler, lineage, and downstream dataflow semantics should be
  out of SPEC 1. Previewers must inspect existing references; they should not
  become workflow truth.
- Non-imaging domain packages, such as LCMS, should be out of initial SPEC 1
  migration except as examples for future package previewer adoption.
- IO format capability semantics should be out of scope except where package
  docs need to explain how previewers differ from IO capabilities.
- Broad frontend redesign of the right panel layout should be out of scope.
  Only change layout where the preview host/provider contract requires it.
- Generated docs and `docs/ai-developer/**` should stay out of scope unless
  the owner separately authorizes governance/documentation workflow changes.

## Test Impact

Existing tests that pin current behavior:

- `tests/api/test_data.py:55-84` covers CSV/text upload and preview.
- `tests/api/test_data.py:230-294` covers current image, series, composite,
  and artifact dispatch.
- `tests/api/test_data.py:347-423` covers plugin image type-chain dispatch
  and Zarr image payloads.
- `tests/api/test_data.py:451-624` covers image slice-axis selection and
  clamping.
- `tests/api/test_data.py:627-697` covers DataFrame pagination and sorting.
- `tests/api/test_runtime_import_surface.py:26-60` pins re-exported runtime
  helper symbols.
- `tests/api/test_runtime_import_surface.py:80-130` pins the table cache and
  monkeypatchable read helper behavior.
- `tests/api/test_runtime_import_surface.py:170-183` pins
  `ApiRuntime.preview_data` as a method on the runtime class.
- `frontend/src/components/DataPreview.test.tsx:11-34` covers lazy preview
  requests.
- `frontend/src/components/DataPreview.test.tsx:36-77` covers image zoom/LUT
  rendering.
- `frontend/src/components/DataPreview.test.tsx:107-144` covers table display.
- `frontend/src/components/DataPreview.test.tsx:150-190` covers output ref
  pill labels.
- `frontend/src/components/DataPreview.test.tsx:197-254` covers image slice
  slider rendering.
- `frontend/src/components/DataPreview.test.tsx:256-300` covers paginated table
  UI.

Tests SPEC 1 will likely need to create or update:

- Previewer registry tests for core, package, project, and monorepo discovery.
- Preview router tests for exact type, collection type, parent fallback,
  priority, ambiguity errors, and explicit project default previewers.
- Backward-compatibility API tests proving old `preview.kind` responses still
  render or are intentionally versioned.
- New API schema tests for preview sessions, previewer manifests, bounded data
  access, errors, truncation/sampling flags, and provider identity.
- Data-access tests proving large Zarr/TIFF/table previews do not materialize
  full payloads in the REST preview path.
- Frontend tests for `PreviewHost`, provider manifest validation failure,
  fallback viewer selection, and session/query caching.
- Imaging package tests proving `Image`/`Label` previewers register through the
  new package entry point and fall back to core `ArrayPreviewer` when absent.
- Packaging tests proving previewer Python modules and frontend assets/manifests
  are included in wheels.
- MCP tests if MCP `preview_data` is made to share previewer data access.

## Open Questions

- Should SPEC 1 preserve the current REST response shape as the default
  endpoint, or introduce a versioned/session endpoint and keep
  `/api/data/{ref}/preview` as a compatibility adapter?
- What is the canonical preview envelope? The current UI shape is
  `preview.kind`; the current MCP shape is `fmt/payload/truncated`; ADR-048
  mentions `PreviewEnvelope` but the exact fields are still open.
- Are collections previewed as collections first, or should the current
  frontend behavior of flattening collection items into individual ref pills
  remain the initial UI?
- How should package-owned frontend assets be built, served, fingerprinted, and
  loaded as same-origin ESM modules?
- What minimal "project-local previewer" surface is required for SPEC 1?
  Project-local Python providers are plausible; project-local React previewers
  may need a larger toolchain and should be explicitly scoped.
- Does `DataPreviewResponse` gain metadata, or should OME metadata stay behind
  `/api/data/{ref}` and package-owned image previewer provider endpoints?
- Should the first implementation move the current `ImageViewer` to the imaging
  package immediately, or first introduce the host/router while keeping the
  existing image viewer as a compatibility core viewer?
- How should preview cache keys encode previewer ID, session ID, slice/table
  query, data version, and selected provider without leaking stale previews?
- What are the hard preview budgets for REST providers by type, and should they
  match the MCP 8 MiB cap?
- How should ambiguity errors be surfaced in the frontend: blocking error,
  provider picker, or project default suggestion?

## Recommended Spec Requirements

- Define a typed backend model for `PreviewerSpec`, `PreviewRequest`,
  `PreviewSession`, `PreviewEnvelope`, `PreviewDataAccess`, preview errors, and
  frontend manifests.
- Require a compatibility plan for the current `DataPreviewResponse` outer
  shape and the current `preview.kind` payloads.
- Require deterministic routing with explicit ambiguity errors, matching
  ADR-048 resolution order.
- Require bounded data access for table, array, series, text, artifact,
  composite, and collection previews. The REST preview path must not use
  full-array/full-Zarr materialization for large arrays.
- Require core fallback previewers for DataFrame, Array, Series, Text,
  Artifact, CompositeData, and Plot artifacts, but keep rich image semantics in
  the imaging package.
- Require package-owned previewer discovery through a defined
  `scistudio.previewers` entry point or an explicitly justified alternative.
- Require same-origin frontend manifest validation and deterministic failure
  fallback before loading package/project previewer modules.
- Require frontend state to remain UI state only. Backend data references,
  selected provider, session identity, cache paths, and preview errors must be
  backend-authored.
- Require collection behavior to be explicit: either a collection fallback
  viewer or a compatibility rule that preserves flattened item selection.
- Require imaging migration criteria: core `ArrayPreviewer` still works without
  `scistudio-blocks-imaging`; package `Image`/`Label` previewers add rich image
  controls when installed.
- Require exact cache invalidation rules for preview session/query state.
- Require an explicit non-goal for plot job execution in SPEC 1, except for any
  static `PlotPreviewer` artifact display contract the owner wants to include
  early.
