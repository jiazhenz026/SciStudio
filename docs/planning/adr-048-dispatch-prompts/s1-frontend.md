# Dispatch Prompt — S1-frontend (ADR-048 SPEC 1 frontend PreviewHost)

[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity
- Repository: SciStudio
- Owner request: Implement ADR-048 SPEC 1 frontend in full — PreviewHost, same-origin dynamic ESM previewer loading, and core fallback viewers.
- Task kind: feature · Persona: implementer
- Issue: #1574 — https://github.com/zjzcpj/SciStudio/issues/1574
- Umbrella PR: #1577 `[DO NOT MERGE]` · Protected branch: main
- Umbrella branch: track/adr-048-spec1-preview-system
- Agent branch: feat/adr-048-preview-frontend (ALREADY CREATED by the manager)
- Agent worktree: C:/Users/jiazh/Desktop/workspace/sci-wt/s1-frontend (ALREADY CREATED; `frontend/node_modules` is a junction to the main checkout — do NOT run npm install)
- Gate record (manager-owned, single ledger): .workflow/records/1574-track-adr-048-spec1-preview-system.json
- Checklist: docs/planning/adr-048-implementation-checklist.md

## Setup (worktree already provisioned by manager)
```bash
cd "C:/Users/jiazh/Desktop/workspace/sci-wt/s1-frontend/frontend"
node -v && ls node_modules/.bin/vitest*   # junction already present; do NOT npm install/ci
```
Work only in this worktree, only under `frontend/**`. Do NOT use `pip install -e .`.

## Required Rules (read first)
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/personas/implementer.md
- docs/adr/ADR-048.md and docs/specs/adr-048-preview-system.md (your contract; §2 User Stories, §3 FR-020..FR-024, §4)

## Scope — you own ONLY
- `frontend/src/components/DataPreview.tsx`, `frontend/src/components/DataPreview.parts/**`
- `frontend/src/store/previewSlice.ts`, `frontend/src/store/types.ts`
- `frontend/src/types/api.ts`, `frontend/src/lib/api/data.ts`
- any new files under `frontend/src/components/DataPreview.parts/**` and their `*.test.tsx`
You must NOT touch: backend (`src/scistudio/**`), `packages/**`, or any non-frontend path. If you need one, STOP and report.

## VERIFIED backend contract (already merged into your base branch — read the real code under `src/scistudio/previewers/` and `src/scistudio/api/` to confirm)

Legacy compat route (unchanged, still used during migration):
- `GET /api/data/{ref}/preview?slice&page&page_size&sort_by&sort_dir` → `DataPreviewResponse { ref, type_name, preview }` where `preview.kind` ∈ `table|text|image|chart|composite|artifact` (exact legacy shapes preserved).

New session API (your PreviewHost uses this):
- `POST /api/previews/sessions` body `{ target: { kind, ref, recorded_type, type_chain, collection_item_type, source }, query: {} }` → `PreviewEnvelopeModel`
- `GET /api/previews/sessions/{session_id}` → `PreviewEnvelopeModel` (404 if unknown)
- `PATCH /api/previews/sessions/{session_id}` body `{ query: {...} }` → `PreviewEnvelopeModel`
- `GET /api/previews/sessions/{session_id}/resources/{resource_id}` → `{ resource_id, data }` (resource ids like `tile`, `slot:<name>`, `item:<idx>`)
- `GET /api/previews/assets/{previewer_id}/{asset_path:path}` → validated same-origin file (this is where dynamic previewer ESM modules + css are served)

`PreviewEnvelope` (see `src/scistudio/api/schemas.py` `PreviewEnvelopeModel`): `{ previewer_id, target, kind: dataframe|array|series|text|artifact|composite|collection|plot|error, payload: {}, session_id, resources: [{resource_id,kind,media_type,description,params}], metadata: { sampled, truncated, cached, derived, complete, failed, extra }, diagnostics: [], error: { code, message, detail }|null }`.

`FrontendManifest` serialized to the frontend (NO `asset_root`): `{ previewer_id, module_url, export_name, css: [], version, api_version }`. A spec with a `frontend_manifest` means: dynamically `import(module_url)` (same-origin, served by the assets route), then mount `module[export_name]` with the constrained host API you define (see below).

Core fallback previewer ids you will route to by `envelope.kind`: `core.dataframe.basic`, `core.array.basic`, `core.series.basic`, `core.text.basic`, `core.artifact.basic`, `core.composite.basic`, `core.collection.basic`, `core.plot.basic`, `core.base.fallback`.

## Work To Do (implement docs/specs/adr-048-preview-system.md frontend half in full)
1. Turn `DataPreview.tsx` into a `PreviewHost` container (add `DataPreview.parts/PreviewHost.tsx`). For the selected output target it: creates a session via `POST /api/previews/sessions`, reads the envelope, and dispatches:
   - if the resolved previewer has a `frontend_manifest` → validate it (same-origin module_url only; reject remote/CDN), dynamically `import()` it, mount `export_name` with the constrained host API; on validation/import/mount failure → render diagnostics AND fall back to the core viewer for `envelope.kind` (FR-022, FR-029, US2.3).
   - else → render the core fallback viewer for `envelope.kind`.
2. **Define and export a stable host-module API contract** (e.g. `frontend/src/components/DataPreview.parts/previewerHostApi.ts`): a documented TypeScript interface for what a dynamically-loaded previewer module exports (`export_name`) and what host API it receives — `previewSessionId`, provider metadata, current block/output identity, `requestSession`/`patchQuery`/`getResource` helpers (calling the session API only), export/save helpers, and `reportError`. It MUST NOT expose workflow-mutation primitives (FR-023). The imaging package's previewer module will implement this contract, so make it clean, minimal, versioned (carry `api_version`), and documented with a header comment + example. **Report this interface verbatim in your final message.**
3. Core fallback viewers under `DataPreview.parts/` (FR-012..FR-019), one per `EnvelopeKind`:
   - DataFrame (paginated table — reuse/rename `TableViewer`), Array (GENERIC numeric only: shape/dtype/axes, scalar/1-D chart, 2-D matrix/heatmap, bounded N-D axis selectors, generic colormap/range — split the generic raster bits out of `ImageViewer`; do NOT keep imaging-domain LUT/OME/channel/label semantics in core, those move to the imaging package), Series (chart+table, decimated), Text (bounded + truncation marker + editor handoff), Artifact (metadata + safe inline), Composite (slot inventory + child routing), Collection (gallery/list of sampled item refs + per-item child preview using the same routing), Plot (PNG/JPEG/SVG/PDF; render SVG sanitized/sandboxed so scripts don't execute; multi-artifact tabs; export/save controls), Error (typed error display).
4. `frontend/src/lib/api/data.ts`: add session helpers (`createPreviewSession`, `getPreviewSession`, `patchPreviewSession`, `getPreviewResource`, asset-URL builder). Keep `getDataPreview` (legacy) working.
5. `frontend/src/types/api.ts`: add `PreviewEnvelope`, `PreviewerManifest`, `PreviewSession`, `PreviewTarget`, resource/metadata/error types. Keep `DataPreviewResponse`/`DataPreviewQuery`.
6. `frontend/src/store/previewSlice.ts` + `store/types.ts`: cache keyed by data/collection ref + previewer_id + session_id + query (slice/page/sort/slot/item) + data version when available (FR-021). Keep frontend state UI-only (no workflow truth).
7. Dynamic modules load ONLY from backend-validated same-origin URLs (FR-022). No remote imports.
8. Tests: keep existing `DataPreview.test.tsx`, `refEntries.test.ts`, `PortInfoPanel.test.tsx` green (migrate assertions if you restructure, do not delete coverage); add `DataPreview.parts/PreviewHost.test.tsx` (session creation, core fallback mount, dynamic-manifest load failure → clean fallback + diagnostics, collection-level preview, table pagination/sort still work, plot SVG/PDF export controls render).

## Required checks (run from the worktree's `frontend/` dir; all must pass)
```bash
cd "C:/Users/jiazh/Desktop/workspace/sci-wt/s1-frontend/frontend"
npm run test          # vitest run
npm run typecheck     # tsc --noEmit
npm run lint          # eslint .
npm run format:check  # prettier --check .
npm run build         # tsc -b && vite build (catches type/bundle errors)
```
Fix everything until all are green. If `format:check` flags files you changed, run `npm run format` then re-check.

## Commit + deliver (NO PR, NO gate_record — manager owns those)
Commit with trailers:
```
feat(preview): ADR-048 SPEC 1 frontend — PreviewHost + dynamic previewer loader + core fallback viewers

<body>

Refs #1574
Gate-Record: .workflow/records/1574-track-adr-048-spec1-preview-system.json
Task-Kind: feature
Issue: #1574
Assisted-by: claude-code:claude-fable-5
```
Then `git push -u origin feat/adr-048-preview-frontend`.

## Output Required
- Changed/created file paths.
- **The exact host-module API TypeScript interface you defined** (verbatim) — the imaging package previewer module will implement it.
- How a dynamically-loaded previewer module is imported + mounted (the precise `module_url` → `import()` → `export_name` flow) and how same-origin validation + load-failure fallback work.
- Test/typecheck/lint/build outputs with pass counts.
- Commit SHA + branch (confirm pushed). Any blocker/scope issue.

## Stop Conditions
Stop and report if: you need a backend/imaging/protected file; the session API contract doesn't match the merged backend code; tests/build can't be made green for unclear reasons; node_modules junction is missing.
