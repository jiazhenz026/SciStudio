# PR 1577 ADR-048 No-Context Audit

Date: 2026-06-13

Auditor: Codex, audit_reviewer persona

Target PR: https://github.com/zjzcpj/SciStudio/pull/1577

Tracking issue: #1635

Target head reviewed: `origin/track/adr-048-spec1-preview-system` at `d3209847ef07eb5200295f2fc32efbc5cf65c819`

Base used for comparison: `origin/main` fetched 2026-06-13 at `5adce472a5c5787564463a381ce07a6c0ebde5ee`

## Scope Boundary

This was a no-context audit. I limited review evidence to:

- ADR-048: `docs/adr/ADR-048.md`
- Corresponding specs:
  - `docs/specs/adr-048-preview-system.md`
  - `docs/specs/adr-048-ai-plot-tools.md`
  - `docs/specs/adr-048-developer-docs-refresh.md`
- The PR code and documentation diff at the target head.
- Current open issue metadata only where it indicated possibly unfinished ADR-048 work.
- Local targeted test execution against the PR head.

I did not use previous chat context or prior audit reports as evidence for the implementation judgment.

## Verdict

Block PR readiness until the P1 finding is fixed and the P2 viewer E2E evidence gap is closed.

The implementation wires the main ADR-048 surfaces: session-only preview API, frontend `PreviewHost`, core fallback previewers, imaging package previewers, plot job route, MCP plot tools, asset validation, and refreshed docs. However, the preview cache key does not satisfy ADR-048/SPEC 1 and can return the wrong N-dimensional array slice. Also, the committed viewer "E2E" evidence is API/session-level rather than live browser coverage for every viewer category, so the PR does not yet prove the end-to-end viewer requirement.

## Findings

### P1 - Preview cache keys omit required query and identity dimensions, causing stale or wrong viewer data

Requirement:

- SPEC 1 FR-021 requires preview cache keys to include the data or collection ref, previewer ID, session ID, query params, slice/page/sort state, and data version when available: `docs/specs/adr-048-preview-system.md:275-277`.
- ADR-048 requires bounded preview sessions with frontend manifests stamped on envelopes, and array previewers must support generic numeric arrays without imaging assumptions: `docs/adr/ADR-048.md:211-219`, `docs/adr/ADR-048.md:333-341`.

Evidence:

- Frontend production code calls `buildPreviewCacheKey(t, q)` without passing previewer ID, session ID, or data version: `frontend/src/components/DataPreview.tsx:218-222`.
- `buildPreviewCacheKey` only includes these query keys: `slice_index`, `page`, `page_size`, `sort_by`, `sort_dir`, `slot`, and `item`: `frontend/src/store/previewSlice.ts:16-33`.
- The key omits `axis_indices`, even though the core Array viewer sends `axis_indices` for non-displayed axes: `frontend/src/components/DataPreview.parts/coreViewers.tsx:190-195`, `frontend/src/components/DataPreview.parts/coreViewers.tsx:255-296`.
- The backend session cache key has the same omission: `src/scistudio/previewers/session.py:325-341`.
- Tests assert only a narrow `slice_index` key case and do not cover `axis_indices`, previewer ID, session ID, or data version in production wiring: `frontend/src/components/DataPreview.parts/PreviewHost.test.tsx:459-467`, `frontend/src/components/DataPreview.parts/PreviewHost.test.tsx:483-506`.

Impact:

For N-dimensional arrays, changing a non-displayed axis can produce a PATCH request with only `axis_indices`. Because both frontend and backend cache keys ignore that query dimension, two different slices can collide in the cache. That can display stale scientific data for the wrong plane. The implementation therefore does not meet FR-021 and is incomplete for the generic Array fallback promised by ADR-048.

Required fix:

- Include all rendering-affecting query dimensions, including `axis_indices`, in both frontend and backend cache keys.
- Include previewer ID, session ID, and data version when available in the production cache path, not only in optional test-only parameters.
- Add regression tests for two distinct N-D array `axis_indices` values producing distinct cache entries and distinct rendered envelopes.

### P2 - Viewer E2E evidence is API-level, not live browser E2E for every viewer category

Requirement:

- ADR-048 verification requires browser/manual checks for core fallback viewers and package/project viewer behavior: `docs/adr/ADR-048.md:450-481`.
- SPEC 1 requires manual checks for the preview tab using built-in fallback viewers, imaging package viewers, project override behavior, asset path enforcement, and plot previewer output: `docs/specs/adr-048-preview-system.md:494-541`.
- The repository E2E workflow defines live browser evidence as screenshots, console/network capture, and GUI verification, not only API/session assertions: `docs/ai-developer/skills/scistudio-e2e-test/SKILL.md`.

Evidence:

- The ADR-048 E2E scenario records a pass but explicitly says it uses API/session evidence rather than browser screenshots because the acceptance surface was treated as `/api/previews/sessions` plus resource and asset routes: `docs/ai-developer/e2e/2026-06-13-adr048-pr1577-viewers.md:257-262`.
- The per-viewer evidence in that scenario points back to API tests for all viewer categories: `docs/ai-developer/e2e/2026-06-13-adr048-pr1577-viewers.md:268-277`.
- The same scenario says Chrome was available but no screenshots were captured because it verified API/session behavior rather than GUI rendering: `docs/ai-developer/e2e/2026-06-13-adr048-pr1577-viewers.md:293-297`.
- The local Playwright suite I ran is the generic system flow suite, not an ADR-048 per-viewer DOM/rendering sweep: `frontend/e2e/specs/system-flows.spec.ts:1-96`.
- The generic Playwright support mock still includes the removed legacy route `/api/data/obj-1/preview`: `frontend/e2e/support/systemMocks.ts:204-210`.

Impact:

The API tests are useful and passed locally, but they do not prove that every viewer category actually renders through the frontend host, dynamic package modules, asset resources, and user controls in a browser. This leaves an acceptance gap for the user's explicit requirement that E2E tests for every viewer can run successfully.

Required fix:

- Add or update Playwright/Chrome E2E coverage that drives the preview UI and verifies each ADR-048 viewer category: DataFrame, Array, Series, Text, Artifact, Composite, Collection, Image, Label, and Plot.
- Capture DOM assertions and screenshot evidence for dynamic package viewers and core fallback viewers.
- Remove or isolate legacy `/api/data/{ref}/preview` mocks so E2E cannot accidentally pass through a route ADR-048 deleted.

### P3 - Legacy cleanup is mostly complete in production, but stale legacy references remain in test harness/comments

Requirement:

- SPEC 1 FR-007 and FR-008 require the old one-shot `GET /api/data/{ref}/preview`, `getDataPreview`, and legacy envelope adapter path to be deleted: `docs/specs/adr-048-preview-system.md:240-244`.
- ADR-048 requires migration from the legacy API shape to routed preview sessions: `docs/adr/ADR-048.md:173-188`, `docs/adr/ADR-048.md:211-219`.

Evidence:

- Production backend route code now documents that legacy `GET /api/data/{ref}/preview` was removed and exposes session routes through `/api/previews`: `src/scistudio/api/routes/data.py:1-9`, `src/scistudio/api/routes/data.py:189-266`.
- Frontend API code documents that `getDataPreview` was removed and exposes session helpers instead: `frontend/src/lib/api/data.ts:1-4`, `frontend/src/lib/api/data.ts:69-90`.
- `DataPreview` mounts `PreviewHost` directly and no longer uses the old legacy cache path: `frontend/src/components/DataPreview.tsx:18-23`, `frontend/src/components/DataPreview.tsx:218-223`.
- Remaining stale references exist in the Playwright mock and session-manager comments: `frontend/e2e/support/systemMocks.ts:204-210`, `src/scistudio/previewers/session.py:12-13`, `src/scistudio/previewers/session.py:214-217`.

Impact:

I did not find a production route or production frontend call path still using the deleted legacy one-shot preview API. The remaining stale references are lower risk, but they undermine the "no legacy content still running/called" audit criterion and can mask regressions in future E2E work.

Required fix:

- Remove or quarantine the legacy Playwright mock route.
- Update stale comments so `render_target` is described as child/session rendering support rather than a legacy REST compatibility adapter.

## Confirmed Wiring

The following ADR-048 surfaces appear wired in the PR head:

- Session-only preview routes are registered in the FastAPI app: `src/scistudio/api/app.py:272-280`.
- Preview session create/read/patch/resource/asset routes exist under `/api/previews`: `src/scistudio/api/routes/data.py:189-266`.
- `PreviewEnvelope.frontend_manifest` is stamped from the resolved previewer spec: `src/scistudio/previewers/session.py:266-272`.
- Previewer discovery loads core previewers, entry point previewers, and monorepo previewers with duplicate ID rejection: `src/scistudio/previewers/registry.py:55-72`, `src/scistudio/previewers/registry.py:103-159`.
- Collection targets are prevented from falling through to single-item previewers before collection fallback routing: `src/scistudio/previewers/router.py:49-129`.
- Core fallback previewers cover DataFrame, Array, Series, Text, Artifact, Composite, Collection, Plot, and base fallback categories: `src/scistudio/previewers/fallbacks.py:526-608`.
- Plot fallback supports PNG, JPEG, SVG, and PDF suffixes and sanitizes SVG payloads before exposing them: `src/scistudio/previewers/fallbacks.py:424-477`.
- Package frontend manifests reject external URLs and enforce asset path/suffix constraints: `src/scistudio/previewers/assets.py:63-152`.
- The imaging package registers previewers through the `scistudio.previewers` entry point and includes frontend assets in package data: `packages/scistudio-blocks-imaging/pyproject.toml:55-74`.
- Image and Label previewers live in the imaging package, with bounded data/resource providers: `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers/__init__.py:1-40`, `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers/__init__.py:211-279`, `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers/__init__.py:287-354`.
- Plot run route is registered and offloads blocking render work through `run_in_threadpool`: `src/scistudio/api/routes/plots.py:49-133`.
- `DataPreview` wires plot job execution to plot preview target rendering: `frontend/src/components/DataPreview.tsx:96-120`, `frontend/src/components/DataPreview.tsx:188-208`.
- Stale documentation pattern search for `produced_type`, old `preview_data` arguments, old one-shot route docs, `getDataPreview`, `DataPreviewResponse`, and `ApiRuntime.preview_data` did not find live stale docs in the audited doc/template surfaces. The remaining matches were intentional warnings not to use human block labels.

## Local Verification

Commands were run in the PR-head target worktree with `PYTHONPATH=src;packages/scistudio-blocks-imaging/src`.

Passed:

- `python -m pytest tests/api/test_previewers.py::test_adr048_viewer_category_sweep -q --no-cov --timeout=60`
- `python -m pytest packages/scistudio-blocks-imaging/tests/test_previewer_registration.py -q --no-cov --timeout=60`
- `python -m pytest tests/api/test_plot_preview_wiring.py tests/api/test_preview_plot_jobs.py tests/ai/test_mcp_tools_plot.py tests/ai/test_mcp_tools_inspection.py -q --no-cov --timeout=120`
- `python -m pytest tests/previewers tests/api/test_data.py tests/api/test_runtime_import_surface.py -q --no-cov --timeout=120`
- `python -m pytest tests/docs/test_block_development_docs.py tests/cli/test_install.py tests/agent_provisioning/test_skills.py tests/packaging/test_wheel_skills.py -q --no-cov --timeout=120`
- `python -m pytest tests/architecture/test_layer_deps.py tests/architecture/test_packaging.py tests/architecture/test_placement.py tests/contracts/test_runtime_import_contract.py -q --no-cov --timeout=120`
- `npm run test -- PreviewHost.test.tsx coreViewers.test.tsx DataPreview.test.tsx plotPreview.test.ts api-surface.test.ts`
- `npm run typecheck`
- `npm run test:e2e -- --reporter=list`

Notes:

- `npm ci` was required in `frontend/` before frontend test execution because local frontend dependencies were absent in the target worktree.
- The plot/MCP pytest group skipped the R rendering path when `Rscript` was not on `PATH`, which is allowed by SPEC 2 for unavailable R backends.
- The generic Playwright E2E command passed, but it did not exercise every ADR-048 viewer category through the browser UI.
- A combined pytest invocation that mixed root tests with package tests failed with a pytest `ImportPathMismatchError` for two `tests.conftest` modules. Running the same scopes separately passed.

## Current GitHub Check State

At audit time, GitHub reported the PR checks green, including CodeQL, Deferral discipline, Semantic duplication, Full Audit, Verify Workflow Compliance, type check, lint/format, Python 3.11 and 3.13 tests, architecture tests, import contracts, frontend, and wheel release smoke.

This does not close the findings above because the P1 cache-key case is not covered and the P2 per-viewer browser E2E evidence is not present.

## Open Issue Check

Relevant open issue metadata found during the audit:

- `#1635 audit(PR1577): ADR-048 consolidated implementation review` - used as the tracking issue for this audit report PR.
- `#1592 P0(preview): ADR-048 routed preview path is dead-wired...` - the code reviewed here shows `DataPreview` now mounts `PreviewHost` directly and session routes are registered.
- `#1593 P1(previewers/router): Collection[T] mis-routes...` - the router now blocks collection targets from routing to single-item previewers before collection fallback.
- `#1598 P2(previewers): core previewer subsystem imports up into scistudio.api.runtime...` - the targeted architecture/import tests passed locally.

Issue metadata alone was not treated as proof of implementation correctness; code and test evidence above drove the findings.
