# Dispatch Prompt — S1-imaging (ADR-048 SPEC 1 imaging package previewers)

[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity
- Repository: SciStudio
- Owner request: Implement ADR-048 SPEC 1 imaging migration in full — move rich Image/Label preview into `scistudio-blocks-imaging` as a package-owned previewer (backend provider + packaged frontend ESM module + `scistudio.previewers` registration), with core keeping only the generic Array fallback.
- Task kind: feature · Persona: implementer
- Issue: #1574 · Umbrella PR: #1577 `[DO NOT MERGE]` · Protected branch: main
- Umbrella branch: track/adr-048-spec1-preview-system
- Agent branch: feat/adr-048-preview-imaging (ALREADY CREATED by manager)
- Agent worktree: C:/Users/<user>/Desktop/workspace/sci-wt/s1-imaging (ALREADY CREATED)
- Gate record (manager-owned): .workflow/records/1574-track-adr-048-spec1-preview-system.json
- Checklist: docs/planning/adr-048-implementation-checklist.md

## Setup
```bash
cd "C:/Users/<user>/Desktop/workspace/sci-wt/s1-imaging"
```
The package `scistudio_blocks_imaging` is NOT pip-installed in this env. To run anything, set BOTH paths (Windows pathsep `;`):
```bash
export PP="C:/Users/<user>/Desktop/workspace/sci-wt/s1-imaging/src;C:/Users/<user>/Desktop/workspace/sci-wt/s1-imaging/packages/scistudio-blocks-imaging/src"
PYTHONPATH="$PP" python -c "import scistudio, scistudio_blocks_imaging; from scistudio.previewers.models import PreviewerSpec; print('ok')"
```
Do NOT use `pip install -e .`. Work ONLY in this worktree.

## Required Rules
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/personas/implementer.md
- docs/adr/ADR-048.md (§4, §6 ArrayPreviewer-vs-imaging boundary), docs/specs/adr-048-preview-system.md (FR-025, FR-026, SC-005, SC-009, US2, US4)

## Scope — you own ONLY
- `packages/scistudio-blocks-imaging/**` (new `previewers/` module + JS asset + pyproject entry point/package-data + tests)
You must NOT touch: `src/scistudio/**` (core/previewers/api), `frontend/**`, or any protected path. You READ from `scistudio.previewers` but never edit it. If you need an out-of-scope file, STOP and report.

## VERIFIED contracts you must conform to (read the real code first)

Read these in the umbrella (present in your worktree):
- `src/scistudio/previewers/models.py` — `PreviewerSpec`, `FrontendManifest`, `PreviewEnvelope`, `PreviewMetadata`, `PreviewRequest`, `PreviewResource`, `OwnerKind`, `EnvelopeKind`, `PreviewProvider`.
- `src/scistudio/previewers/registry.py` — entry-point + monorepo discovery (`get_previewers()` protocol).
- `src/scistudio/previewers/assets.py` — manifest validation + `asset_root` path-confinement + allowed suffixes (`.js/.mjs/.css/.svg/...`); `module_url` MUST be backend-relative `/api/previews/assets/<previewer_id>/<file>` (no remote/protocol-relative).
- `src/scistudio/previewers/data_access.py` — `PreviewDataAccess` bounded helpers (use these for image reads; never `to_memory()` a large array).
- `frontend/src/components/DataPreview.parts/previewerHostApi.ts` and `dynamicPreviewer.ts` — the **host-module API your JS module must implement**. Key contract:
  - Your JS module is an ESM with `export default { apiVersion: "1", mount(container: HTMLElement, host: PreviewHostApi): { update?(envelope), unmount() } }` (confirm the exact `export_name` + shape from `previewerHostApi.ts`).
  - `host` gives: `previewSessionId`, `envelope`, `kind`, `provider`, `session.refresh()/patchQuery(q)/getResource(id)/resources`, `assetUrl(path)`, `exportArtifact()`, `saveArtifact()`, `reportError()`. NO workflow mutation.
- **Manifest delivery seam (important):** the session envelope does NOT carry the spec manifest. The frontend host reads it from `envelope.metadata.extra["frontend_manifest"]`. So your **backend provider MUST embed** its `FrontendManifest.to_dict()` (the PreviewFrontendManifestModel shape: `previewer_id, module_url, export_name, css, version, api_version` — NO `asset_root`) into the returned envelope's `metadata.extra["frontend_manifest"]`.

## Work To Do (full scope, no v1 reduction)

### A. Backend previewer module — `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers/`
1. `__init__.py` (or `previewers.py`) exposing `get_previewers() -> list[PreviewerSpec]` returning specs for at least `Image` and `Label` (consider `Mask`, and collection support `supports_collection=True` for galleries):
   - `owner_kind=OwnerKind.PACKAGE`, `owner_name="scistudio-blocks-imaging"`, `target_type="Image"` / `"Label"`, `priority` above core, `capabilities=("slice","lut","metadata","export",...)`.
   - `backend_provider=` a callable `(PreviewRequest) -> PreviewEnvelope` (or `"scistudio_blocks_imaging.previewers:image_provider"` import string).
   - `frontend_manifest=FrontendManifest(previewer_id=..., module_url="/api/previews/assets/<id>/viewer.js", export_name=..., css=(...), version=..., api_version="1", asset_root=<abs path to the packaged assets dir>)`.
2. Provider callables (Image, Label): read bounded data via `request.data_access` (array plane/tile, OME/channel metadata, slot inventory for Label). Return `PreviewEnvelope(previewer_id=..., target=request.target, kind=EnvelopeKind.ARRAY (Image) / COMPOSITE (Label), payload={shape, axes, channels, ome, current plane data-URI or resource refs, slice axis info, display range}, resources=(slice/tile resources), metadata=PreviewMetadata(... set the 6 flags; put frontend_manifest dict into extra["frontend_manifest"]))`. Providers MUST embed an error envelope rather than raise for routine failures. Set `kind=array` so that if the dynamic JS module fails to load, the host falls back to the core Array viewer.
3. Export `get_previewers` from `scistudio_blocks_imaging/__init__.py` (top-level) so the **monorepo dev fallback** (`registry._scan_monorepo_packages` → `getattr(module, "get_previewers")`) discovers it.

### B. Frontend ESM module (packaged, served same-origin) — `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers/assets/viewer.js`
- A SELF-CONTAINED vanilla ESM module (NO npm build step, NO React dependency — render with the DOM/`<canvas>` directly) implementing the host-module contract from `previewerHostApi.ts`.
- Port the rich behavior currently in `frontend/src/components/DataPreview.parts/ImageViewer.tsx` (read it for reference): canvas render, zoom/pan, single-axis slice slider, LUT (the 9 colormaps), display min/max range. Pull pixel/slice data through `host.session.getResource(...)` / `host.envelope.payload` (the data your backend provider supplies). Add an OME/channel metadata panel for `Label`/`Image` where metadata exists.
- Keep it dependency-free and same-origin. Validate with `node --check viewer.js`.

### C. Packaging / discovery
- `packages/scistudio-blocks-imaging/pyproject.toml`: add `[project.entry-points."scistudio.previewers"]` → `imaging = "scistudio_blocks_imaging.previewers:get_previewers"` (installed-mode discovery), and ensure the JS/CSS assets ship in the wheel (hatchling package-data / force-include for `previewers/assets/*`).
- `packages/scistudio-blocks-imaging/README.md`: add a short "Package-owned Image/Label previewers" section (core owns only the generic Array fallback). [SPEC 3 will expand docs; you add the minimal accurate section now since it ships with the implementation.]

### D. Tests — `packages/scistudio-blocks-imaging/tests/test_previewer_registration.py`
- `get_previewers()` returns specs for Image + Label with `owner_kind=PACKAGE`, resolvable `backend_provider`, and a `FrontendManifest` that passes `scistudio.previewers.assets` validation (same-origin module_url, resolves to a real file under asset_root).
- Build a `PreviewerRegistry`, load core (`load_core()`) + register imaging specs (or run monorepo discovery), and assert routing via `PreviewRouter`: an `Image` target → imaging previewer; a `Label` target → imaging; a plain `Array` target → `core.array.basic`. Removing imaging → `Image` falls back to `core.array.basic` via parent-type resolution (FR-026).
- The Image provider returns a valid `PreviewEnvelope` for an Image fixture, with the 6 metadata flags set and `metadata.extra["frontend_manifest"]` present and same-origin.
- Mark integration that needs the installed plugin with `@pytest.mark.requires_imaging` if appropriate; pure-unit tests (get_previewers + registry/router with explicit registration) need no marker.

## Required checks (run from worktree; all green)
```bash
PP="C:/Users/<user>/Desktop/workspace/sci-wt/s1-imaging/src;C:/Users/<user>/Desktop/workspace/sci-wt/s1-imaging/packages/scistudio-blocks-imaging/src"
PYTHONPATH="$PP" python -m pytest packages/scistudio-blocks-imaging/tests/test_previewer_registration.py -q --no-cov -p no:cacheprovider
ruff check packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers
ruff format --check packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers
node --check packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers/assets/viewer.js
# also confirm you did not break existing imaging tests that don't need install:
PYTHONPATH="$PP" python -m pytest packages/scistudio-blocks-imaging/tests/test_types.py -q --no-cov -p no:cacheprovider
```
Fix everything until green. mypy if the package is configured for it.

## Commit + deliver (NO PR, NO gate_record)
Commit with trailers:
```
feat(preview): ADR-048 SPEC 1 imaging — package-owned Image/Label previewers + ESM viewer

<body>

Refs #1574
Gate-Record: .workflow/records/1574-track-adr-048-spec1-preview-system.json
Task-Kind: feature
Issue: #1574
Assisted-by: claude-code:claude-fable-5
```
Then `git push -u origin feat/adr-048-preview-imaging`.

## Output Required
- Changed/created file paths.
- The `get_previewers()` spec list (ids, target types, manifests) and how the provider embeds the manifest in `metadata.extra`.
- How the JS module conforms to the host-module contract (export shape + how it reads data via the host API).
- Test/lint/node-check outputs with pass counts.
- Commit SHA + branch (confirm pushed). Any blocker/scope issue (esp. if the host-module contract or assets path-confinement needs something not yet provided — STOP and report rather than editing core/frontend).

## Stop Conditions
Stop and report if: you need to edit `src/scistudio/**` or `frontend/**`; the host-module contract is insufficient; assets validation rejects a same-origin module_url you can't satisfy; tests can't be made green for unclear reasons.
