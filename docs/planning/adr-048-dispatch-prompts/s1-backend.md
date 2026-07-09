# Dispatch Prompt — S1-backend (ADR-048 SPEC 1 backend core + API)

[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-048 SPEC 1 (extensible preview system) in full; this agent owns the backend core + API + MCP-inspection sharing + backend tests.
- Task kind: feature
- Persona: implementer
- Issue: #1574 — https://github.com/zjzcpj/SciStudio/issues/1574
- Umbrella PR: #1577 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-048-spec1-preview-system
- Agent branch: feat/adr-048-preview-backend
- Agent worktree: C:/Users/<user>/Desktop/workspace/sci-wt/s1-backend
- Gate record (manager-owned, single ledger): .workflow/records/1574-track-adr-048-spec1-preview-system.json
- Checklist: docs/planning/adr-048-implementation-checklist.md

## Required Rules (read before editing)

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/implementer.md
- docs/adr/ADR-048.md (governing design)
- docs/specs/adr-048-preview-system.md (governing spec — THIS is your contract)
- docs/planning/adr-048-preview-system-scope.md (current-code map)

## Environment / worktree setup (do this first)

You MUST work in a dedicated worktree, not the main checkout:

```bash
cd "C:/Users/<user>/Desktop/workspace/SciStudio"
git fetch origin --quiet
git worktree add -b feat/adr-048-preview-backend "C:/Users/<user>/Desktop/workspace/sci-wt/s1-backend" origin/track/adr-048-spec1-preview-system
cd "C:/Users/<user>/Desktop/workspace/sci-wt/s1-backend"
```

CRITICAL — the package is editable-installed to the MAIN checkout, so to test
YOUR worktree code you MUST prefix python/pytest with PYTHONPATH:

```bash
PYTHONPATH="C:/Users/<user>/Desktop/workspace/sci-wt/s1-backend/src" python -m pytest ...
```

Do NOT use `pip install -e .`. Do NOT run `npm`/frontend tooling (frontend is a different agent).

## Scope — you own ONLY

- `src/scistudio/previewers/**` (NEW package — create it)
- `src/scistudio/api/runtime/_data.py`, `src/scistudio/api/runtime/__init__.py`,
  `src/scistudio/api/runtime/_preview_cache.py`, `src/scistudio/api/runtime/_preview_image.py`
- `src/scistudio/api/routes/data.py`
- `src/scistudio/api/schemas.py`
- `src/scistudio/ai/agent/mcp/tools_inspection/**` (only to share bounded data access OR keep tested 8 MiB compatibility)
- `tests/previewers/**`, `tests/api/test_previewers.py`, `tests/api/test_data.py`,
  `tests/api/test_runtime_import_surface.py`, `tests/ai/test_mcp_tools_inspection.py`

## You MUST NOT touch (out of scope / protected)

- `frontend/**` (S1-frontend agent owns it)
- `packages/scistudio-blocks-imaging/**` (S1-imaging agent owns it)
- PROTECTED paths (no owner core-change label exists): `src/scistudio/core/**`,
  `src/scistudio/blocks/**`, `src/scistudio/engine/**`, `src/scistudio/workflow/**`,
  `src/scistudio/utils/**`, `src/scistudio/qa/**`. You may IMPORT from these but never edit them.

If you need an out-of-scope path, STOP and report back.

## Coordination

- Work only on branch `feat/adr-048-preview-backend` in your worktree.
- Do NOT use `pip install -e .`.
- Do NOT open a PR. Do NOT run any `gate_record` command (the manager owns the single ledger).
- Commit with the AI trailers below; push your branch; report back. The manager integrates.

## TODO / deferral rule

Any deferred work needs `# TODO(#NNN): <reason>` citing issue/ADR/spec. No hidden V1/MVP deferrals. The owner directive is FULL scope — implement everything in the spec.

## Work To Do (implement docs/specs/adr-048-preview-system.md in full)

Build the core previewer subsystem `src/scistudio/previewers/`:

1. `models.py` — typed models per spec §3 "Key Entities":
   - `PreviewTarget` (kind: data_ref|collection_ref|artifact|plot_artifact; ref; recorded_type/type_chain; collection_item_type; source).
   - `PreviewerSpec` (previewer_id, owner_kind: core|package|project, owner_name, target_type, supports_collection, priority:int, capabilities:list[str], backend_provider, frontend_manifest, api_version).
   - `PreviewEnvelope` (session_id, previewer_id, target, kind: dataframe|array|series|text|artifact|composite|collection|plot|error, payload, resources, metadata, diagnostics, error). metadata MUST carry sampled/truncated/cached/derived/complete/failed flags.
   - `PreviewSession` (session_id, previewer_id, target, created_at, query, cache_key, limits).
   - Frontend manifest descriptor (previewer_id, module_url, export_name, css assets, version, api_version).
   - Typed errors: routing ambiguity, unknown previewer, missing bundle, provider exception.
2. `data_access.py` — `PreviewDataAccess` with bounded helpers: `dataframe_page`, `array_plane`, `array_tile`, `series_points`, `text_chunk`, `artifact_metadata`, `composite_slots`, `collection_sample`. Enforce row/byte/item/tile/dimension budgets. Reuse logic from the existing `_preview_cache.py` (table paging, MAX_TABLE_PAGE_SIZE=200) and `_preview_image.py` (matrix load/downsample/data-URI) but ensure bounded reads — NO full-array/full-Zarr materialization (FR-010). Keep `_get_preview_table` + monkeypatchable read re-exports intact (tests pin them — see tests/api/test_runtime_import_surface.py).
3. `registry.py` — `PreviewerRegistry`: loads core specs unconditionally; package specs via `scistudio.previewers` entry points using `importlib.metadata.entry_points(group="scistudio.previewers")` PLUS a monorepo fallback scanning `packages/scistudio-blocks-*` (mirror `src/scistudio/core/types/registry.py` `_scan_entrypoint_types` + monorepo pattern, gated by SCISTUDIO_DEV like types); project specs from active project config. Duplicate previewer_id → error/diagnostic.
4. `router.py` — `PreviewRouter`: resolution order EXACTLY per ADR-048 §3 / spec FR-003: (1) project exact Collection[T], (2) project exact T, (3) package exact Collection[T], (4) package exact T, (5) project parent, (6) package parent, (7) core collection fallback, (8) core base fallback, (9) unknown/error. Use the DataRecord `type_chain` (ordered general→specific) + `TypeRegistry` to resolve parent types. Within a tier+specificity, highest `priority` wins; remaining ties → typed ambiguity error (FR-004). Support project explicit default previewer (FR-005).
5. `session.py` — `PreviewSessionManager`: create/read/patch sessions, call the selected provider, expose bounded resource reads. In-memory session store keyed by session_id.
6. `fallbacks.py` — core fallback previewer providers, each returning a `PreviewEnvelope` (spec §6): `DataFramePreviewer`, `ArrayPreviewer` (GENERIC numeric only — shape/dtype/axes, scalar/1D chart/2D matrix, bounded N-D slicing, generic colormap/range; NO image-domain LUT/OME/channel/label semantics per FR-014), `SeriesPreviewer` (chart+table, decimation), `TextPreviewer` (bounded, truncation marker, editor-handoff metadata), `ArtifactPreviewer`, `CompositePreviewer` (slot inventory first, child routing on select), `CollectionPreviewer` (item count, sampled refs, bounded iteration), `PlotPreviewer` (display PNG/JPEG/SVG/PDF; SVG sanitized/sandboxed so scripts don't execute; multi-artifact tabs; save/export). Register all as core PreviewerSpecs.
7. `assets.py` — same-origin frontend asset serving + manifest validation: validate manifest fields, confine asset paths under the package/project asset root, reject remote URLs, check version + api_version. Provide a function the API route can use to serve validated assets.
8. `project.py` — project-local previewer discovery (backend Python providers + same-origin packaged assets) and project default previewer declaration.
9. `__init__.py` — public API + a registry/router accessor (singleton or factory) the API runtime can call.

API integration:

10. `api/runtime/_data.py`: route `ApiRuntime.preview_data(...)` through the PreviewRouter → selected provider → `PreviewEnvelope`, then adapt the envelope to the LEGACY REST dict shape so existing callers/tests keep working. The legacy `preview` dict shapes MUST be preserved EXACTLY:
    - table: `{kind:"table", columns, rows, total_rows, row_count, page, page_size, total_pages, sort_by, sort_dir}`
    - text: `{kind:"text", content, language}`
    - image/array: `{kind:"image", shape, axes, slice_axis_name, slice_axis_size, slice_index, thumbnail, src}` (core ArrayPreviewer must still produce this generic raster shape for the compat route so existing frontend + tests pass during migration)
    - chart/series: `{kind:"chart", points}`
    - composite: `{kind:"composite", slots}` (or raster image when a raster slot exists, as today)
    - artifact: `{kind:"artifact", path, mime_type}`
11. `api/routes/data.py`: KEEP `GET /api/data/{data_ref}/preview` (compat adapter). ADD session routes: `POST /api/previews/sessions`, `GET /api/previews/sessions/{id}`, `PATCH /api/previews/sessions/{id}`, `GET /api/previews/sessions/{id}/resources/{rid}`, `GET /api/previews/assets/{aid}`.
12. `api/schemas.py`: add typed Pydantic schemas for previewer spec/session/envelope/manifest; KEEP `DataPreviewResponse` unchanged.
13. `api/runtime/__init__.py`: update re-exports deliberately; KEEP every symbol `tests/api/test_runtime_import_surface.py` pins (run that test to confirm).
14. MCP inspection (`tools_inspection/`): EITHER share `PreviewDataAccess` OR keep the existing bounded `preview_data` tool and add/keep a test proving the 8 MiB response cap is intact (FR-027). Simplest acceptable path: keep MCP behavior, ensure tests/ai/test_mcp_tools_inspection.py passes.

Tests (add/extend — implementation work REQUIRES test changes):

15. `tests/previewers/test_preview_registry.py` — core/package/monorepo/project discovery, duplicate-id error, invalid spec.
16. `tests/previewers/test_preview_routing.py` — exact match, collection match, parent fallback, priority tie-break, project override, ambiguity error.
17. `tests/previewers/test_preview_data_access.py` — bounded reads (row/byte/item/tile/dimension budgets); prove large array/Zarr reads do NOT materialize the whole payload.
18. `tests/api/test_previewers.py` — session create/read/patch/resource routes; provider exception → preview error (no crash); missing ref / stale session → stable errors.
19. Keep `tests/api/test_data.py` and `tests/api/test_runtime_import_surface.py` GREEN (compat). Add envelope/metadata assertions where useful.
20. `tests/ai/test_mcp_tools_inspection.py` — MCP 8 MiB cap intact.

## Required Tests And Checks (run all, report results)

From your worktree root, with PYTHONPATH set:

```bash
WT="C:/Users/<user>/Desktop/workspace/sci-wt/s1-backend"
PYTHONPATH="$WT/src" python -m pytest tests/previewers tests/api/test_previewers.py tests/api/test_data.py tests/api/test_runtime_import_surface.py tests/ai/test_mcp_tools_inspection.py -x -q -p no:cacheprovider --no-cov -m "not requires_imaging and not requires_r and not requires_fiji"
ruff check src/scistudio/previewers src/scistudio/api tests/previewers tests/api/test_previewers.py
ruff format --check src/scistudio/previewers tests/previewers
PYTHONPATH="$WT/src" python -m mypy src/scistudio/previewers
```

Fix everything until lint/type/tests are green. (The manager runs the full `gate_record check` after integration, which also runs full_audit / import_contracts / semantic_dup — write clean, well-typed, docstringed code and keep imports inside the previewers package layered.)

## Commit + deliver (NO PR, NO gate_record)

Commit with these trailers (referencing the manager ledger):

```
feat(preview): ADR-048 SPEC 1 backend — previewer registry/router/sessions + core fallbacks + API

<body>

Refs #1574
Gate-Record: .workflow/records/1574-track-adr-048-spec1-preview-system.json
Task-Kind: feature
Issue: #1574
Assisted-by: claude-code:claude-fable-5
```

Then `git push -u origin feat/adr-048-preview-backend`.

## Output Required

- Changed file paths (full list).
- The EXACT public contract you built: paste the final `PreviewerSpec`, `PreviewEnvelope`, `PreviewTarget`, `PreviewSession`, frontend-manifest model definitions, the session API route signatures, and the `scistudio.previewers` entry-point callable protocol (so the frontend + imaging agents can align). This is mandatory.
- Test/lint/type results (commands + pass/fail counts).
- Commit SHA + branch.
- Any blocker or scope issue.

## Stop Conditions

Stop and report if: you need an out-of-scope/protected file; the spec conflicts with current code; tests can't be made green for unclear reasons; you cannot import your worktree code.
