# PR #1577 ADR-048 Consolidated No-Context Audit

Issue: #1635
Target PR: #1577, head `4199de2543cb52d964f53afe4ec0342a554119c3`
Auditor: Codex, `audit_reviewer`
Date: 2026-06-13

## Verdict

**BLOCK / NEEDS-FIX before PR #1577 can merge.**

The main ADR-048 implementation surfaces are largely wired: the routed preview
session API, core fallback providers, imaging package previewers, plot job
runtime, and plot preview registration all passed the targeted checks listed
below. However, three merge-blocking gaps remain:

1. The removed legacy preview URL still returns a successful HTTP 200 response
   from the real app when the SPA fallback is mounted.
2. Live block-output collection preview wiring still flattens collection items
   before `PreviewHost`, so the collection target is not previewed first.
3. The committed viewer "e2e" evidence is API/session test evidence, not a live
   browser e2e proving every viewer can render and interact as required.

Counts: P1 = 3, P2 = 1, P3 = 1.

## Scope Guard

I treated this as a no-context audit. I used ADR-048, the three ADR-048 specs,
the PR #1577 code diff, related issue #1635 plus issue searches, and independent
test execution. A connector call accidentally returned the PR body early in the
session; I did not cite or rely on that body for findings or conclusions.

## Findings

### P1-A: Deleted legacy preview URL still succeeds through the SPA fallback

ADR-048 and SPEC 1 require the legacy one-shot route to be gone. ADR-048 says
`ApiRuntime.preview_data`, `GET /api/data/{ref}/preview`, and
`DataPreviewResponse` were removed, with the routed session API as the live
surface (`docs/adr/ADR-048.md:24-26`). SPEC 1 makes the same requirement and
says all preview reads must flow through `POST`/`GET`/`PATCH
/api/previews/sessions` (`docs/specs/adr-048-preview-system.md:250-259`), and
it explicitly disallows retained preview API shims before readiness
(`docs/specs/adr-048-preview-system.md:600-603`).

The legacy handler is deleted, but the app still returns success for the legacy
URL when the SPA is mounted. `SPAStaticFiles.lookup_path()` returns `index.html`
for any missing path (`src/scistudio/api/spa.py:24-28`), and `create_app()`
mounts it at `/` after API routes (`src/scistudio/api/app.py:317`). The comment
in `SPAStaticFiles` says `/api/*` is never intercepted (`src/scistudio/api/spa.py:19-21`),
but unmatched `/api/*` paths are intercepted in practice.

Independent reproduction after `npm --prefix frontend run build`:

```text
GET /api/data/obj-1/preview
status=200
content-type=text/html; charset=utf-8
body_prefix='<!doctype html>\n<html lang="en'
```

Impact: PR #1577 cannot claim the removed preview route is absent in the
prebuilt GUI/runtime surface. API clients and regression checks can observe a
false success instead of a 404/405, and the active e2e mock masks the production
behavior by returning a 404 sentinel for the same URL
(`frontend/e2e/support/systemMocks.ts:204-205`).

Required fix: make unmatched `/api/*` and `/ws` paths bypass SPA fallback and
return API-style 404/405, or add an equivalent catch-all API 404 before the SPA
mount. Add a regression test with static assets present that asserts
`GET /api/data/{ref}/preview` is not 200 and does not return HTML.

### P1-B: Live collection outputs are flattened before `PreviewHost`

SPEC 1 makes collection preview a P1 user story. A block output collection must
be previewed "as one collection first" and then allow item or collection-level
views (`docs/specs/adr-048-preview-system.md:168-177`). Its acceptance criteria
explicitly reject presenting `Collection[Image]` as "ten unrelated flat ref
pills" (`docs/specs/adr-048-preview-system.md:181-185`).

The live `DataPreview` path does the opposite. `extractRefEntries()` detects
`kind: "collection"` and flattens `record.items` into item-level refs
(`frontend/src/components/DataPreview.parts/refEntries.ts:56-57`). `DataPreview`
then maps those entries to `outputRefs`, picks one item `activeRef`, and always
constructs `{ kind: "data_ref", ref: activeRef }` for `PreviewHost`
(`frontend/src/components/DataPreview.tsx:67-84`). The behavior is locked in by
the frontend test that expects a collection payload to flatten into two item
refs (`frontend/src/components/DataPreview.parts/refEntries.test.ts:48-56`).

Backend API coverage for `core.collection.basic` exists, but the normal right
pane selection flow for block outputs never sends a `collection_ref` target for
the selected collection output. A package collection previewer therefore cannot
be selected first, and the core collection fallback is not the first live view
for a collection-producing block.

Impact: ADR-048's collection story is only wired at the backend/session layer,
not in the primary UI path users exercise after running a block. This also
explains why API tests can pass while the actual UX remains non-conformant.

Required fix: represent collection outputs as selectable collection targets in
`DataPreview` and pass `{ kind: "collection_ref", ... }` or an equivalent typed
collection target into `PreviewHost` before exposing item-level drill-down.
Replace the flattening regression test with one that asserts collection-first
behavior and add browser evidence for the live right pane.

### P1-C: Viewer e2e evidence is not a live browser e2e for every viewer

ADR-048 calls for manual/browser verification of collection preview, image
package controls, core array fallback, target-picker plot creation, and plot
artifact viewing (`docs/adr/ADR-048.md:472-479`). SPEC 1 also lists manual
checks to open DataFrame, Series, Text, CompositeData, Artifact, image package,
array fallback, collection, and plot artifact previews
(`docs/specs/adr-048-preview-system.md:535-541`).

The committed scenario is marked `status: "passed"`, but its own results state
that it records API/session evidence from committed tests rather than browser
screenshots (`docs/ai-developer/e2e/2026-06-13-adr048-pr1577-viewers.md:257-262`)
and later says no Chrome screenshots were produced
(`docs/ai-developer/e2e/2026-06-13-adr048-pr1577-viewers.md:293-297`).

There is also a concrete evidence mismatch: the report says Collection was
observed by the same category sweep
(`docs/ai-developer/e2e/2026-06-13-adr048-pr1577-viewers.md:275`), but
`tests/api/test_previewers.py::test_adr048_viewer_category_sweep` omits
Collection from both `cases` and `observed`
(`tests/api/test_previewers.py:182-206`, `tests/api/test_previewers.py:228-238`).
Collection is covered by a separate API test
(`tests/api/test_previewers.py:455-485`), not by the claimed sweep.

Impact: the backend session routing evidence is useful, but it does not prove
that every viewer renders and interacts in the browser. It also would not catch
the P1-A production fallback bug, because the e2e mock forces the removed route
to return 404 while the actual prebuilt app returns 200 HTML.

Required fix: add an executable browser/Playwright or Chrome e2e scenario that
drives the built app and captures evidence for every viewer category:
DataFrame, Array, Series, Text, Artifact, CompositeData, Collection, Image,
Label, and Plot. The run should include package asset loading, core fallback
behavior, plot artifact rendering/export, and a sentinel proving the removed
legacy route is not a successful API response. Alternatively, downgrade the
current scenario status and block readiness until such evidence exists.

### P2-A: Plot preview exposes export only; host `saveArtifact` still rejects

SPEC 1 requires `PlotPreviewer` to expose save/export controls for PNG, JPEG,
SVG, and PDF artifacts (`docs/specs/adr-048-preview-system.md:284-285`) and its
success criteria repeat that SVG/PDF plot artifacts must expose save/export
actions (`docs/specs/adr-048-preview-system.md:586-587`).

The frontend renders a single "Export / Save" plot button, but it only calls the
session export resource path (`frontend/src/components/DataPreview.parts/coreViewers.tsx:797-802`).
The host API method that previewers would call for save semantics is still a
stub: `PreviewHost.saveArtifact` has `TODO(#1626)` and returns
`Promise.reject(new Error("save not available"))`
(`frontend/src/components/DataPreview.parts/PreviewHost.tsx:327-334`).

Open issue #1626 tracks the missing backend save-to-project flow and notes that
the preview cache is intentionally not a result path. That is a valid split, but
the current PR still does not fully satisfy the save/export requirement.

Required fix: either land the explicit save-to-project contract and wire
`saveArtifact`, or narrow ADR/SPEC readiness language so PR #1577 only claims
download/export support and leaves save semantics to #1626.

### P3-A: The active system-flow mock still contains legacy preview-path logic

`frontend/e2e/support/systemMocks.ts:204-205` still matches
`/api/data/obj-1/preview`. It intentionally returns 404, so it is not a
compatibility shim, but it is still an active legacy-path branch in the e2e
harness. After P1-A is fixed in production, this should either become a generic
unknown-API assertion or be covered by a real app-level regression test so the
mock cannot drift from runtime behavior again.

## Positive Coverage

Aside from the findings above, the main ADR-048 module graph appears wired.

Independent routed-session sweep on the PR head passed for:

- `dataframe: core.dataframe.basic -> dataframe`
- `array: core.array.basic -> array`, including `resources/tile`
- `series: core.series.basic -> series`
- `text: core.text.basic -> text`
- `artifact: core.artifact.basic -> artifact`
- `composite: core.composite.basic -> composite`
- `collection: core.collection.basic -> collection`
- `image: imaging.image.viewer -> array`, including `viewer.js` asset response
- `label: imaging.label.viewer -> composite`, including `viewer.js` asset response
- `plot: core.plot.basic -> plot`, including sanitized SVG with no `<script>`

Static review also found the expected plot tool surface wired through MCP
import side effects, six plot tools, plot job execution, preview-cache output,
`/api/plots/run`, and `ApiRuntime.register_plot_artifact` feeding the core
`PlotPreviewer`.

## Verification Run

Target worktree:
`C:\Users\jiazh\Desktop\workspace\sci-wt\pr1577-audit-target-nc-final`

Commands run:

```powershell
$env:PYTHONPATH="$(Resolve-Path src);$(Resolve-Path packages/scistudio-blocks-imaging/src)"
Remove-Item Env:\SCISTUDIO_DEV -ErrorAction SilentlyContinue
python -m pytest tests/api/test_previewers.py tests/api/test_plot_preview_wiring.py tests/api/test_preview_plot_jobs.py tests/previewers/test_preview_registry.py tests/previewers/test_preview_routing.py tests/previewers/test_preview_data_access.py tests/previewers/test_preview_security.py tests/previewers/test_preview_session_manifest.py tests/previewers/test_preview_session_cache_key.py tests/previewers/test_table_cache_surface.py tests/ai/test_mcp_tools_plot.py tests/ai/test_mcp_tools_inspection.py tests/docs/test_block_development_docs.py -q --no-cov --timeout=60
```

Result: passed, with one expected skip because `Rscript` is not on PATH.

```powershell
$env:PYTHONPATH="$(Resolve-Path src);$(Resolve-Path packages/scistudio-blocks-imaging/src)"
python -m pytest packages/scistudio-blocks-imaging/tests/test_previewer_registration.py -q --no-cov --timeout=60
```

Result: 16 passed.

```powershell
npm --prefix frontend ci
npm --prefix frontend test -- src/components/DataPreview.test.tsx src/components/DataPreview.parts/PreviewHost.test.tsx src/components/DataPreview.parts/coreViewers.test.tsx src/lib/api/__tests__/plotPreview.test.ts src/lib/api/__tests__/api-surface.test.ts
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend run test:e2e -- --project=chromium
```

Results: selected vitest suite passed (5 files, 45 tests), typecheck passed, and
production build passed with only the existing chunk-size warning. The existing
Playwright suite exited 0 with 5 passing tests, including 3 expected-fail tests;
it is not an ADR-048 viewer-matrix e2e.

Independent app-level TestClient sweep with built SPA assets present:

```text
ADR048 independent routed-session sweep
PASS dataframe: core.dataframe.basic -> dataframe
PASS array: core.array.basic -> array
PASS series: core.series.basic -> series
PASS text: core.text.basic -> text
PASS artifact: core.artifact.basic -> artifact
PASS composite: core.composite.basic -> composite
PASS image: imaging.image.viewer -> array
PASS label: imaging.label.viewer -> composite
PASS plot: core.plot.basic -> plot
PASS collection: core.collection.basic -> collection
legacy GET /api/data/obj-1/preview: status=200 content-type=text/html; charset=utf-8 body_prefix='<!doctype html>\n<html lang="en'
```

Issue check: #1635 is the active audit issue for this exact PR1577 review.
Open issue #1626 tracks the `saveArtifact` gap. I also searched for open issues
covering the SPA fallback legacy-preview behavior and did not find an existing
tracked issue.

## Recommendation

Do not merge PR #1577 until P1-A, P1-B, and P1-C are fixed and re-audited. The
core implementation is close, but readiness requires the deleted API URL to stop
returning a successful SPA response, collection outputs to enter `PreviewHost`
as collection targets first, and real browser e2e evidence for the viewer matrix
rather than API/session test evidence labeled as e2e.
