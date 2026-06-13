# Independent Audit — PR #1577 (ADR-048 SPEC 1 + 2 + 3 consolidated)

- **Auditor role:** no-context audit reviewer (diff + ADR-048 + the three
  companion specs only).
- **PR under review:** #1577 `[DO NOT MERGE] ADR-048: complete preview system +
  AI plot tools + developer docs (SPEC 1+2+3 consolidated)`.
- **Branch / head:** `track/adr-048-spec1-preview-system` @ `669ddcf3`.
- **Base / merge-base:** `main` @ `026dab92`.
- **Diff size reviewed:** 155 files, +27,552 / −3,025 (authoritative
  `git diff 026dab92..669ddcf3`; note `gh pr view --json files` truncates at 100
  files and `gh pr diff` 406s on >20k lines — neither is the full surface).
- **Governing sources:** `docs/adr/ADR-048.md`,
  `docs/specs/adr-048-preview-system.md`,
  `docs/specs/adr-048-ai-plot-tools.md`,
  `docs/specs/adr-048-developer-docs-refresh.md`.

## Verdict

**PASS — implementation complete and faithful, with 5 minor findings (all
non-blocking; 2 already carry tracked follow-up issues).**

The routed preview subsystem, the AI plot tooling, the imaging package
previewers, and the developer-docs rewrite are all implemented, wired
end-to-end, and covered by tests that pass. The legacy hardcoded-preview path is
fully deleted with no dangling references and no re-introduction of removed
symbols. No `V1`/`differ`/`TODO-later`-style unimplemented features were found
outside of two **properly tracked** deferrals that cite open issues.

## Scope / governance note (not a finding)

The preview-system spec originally mandated keeping the legacy one-shot
`GET /api/data/{data_ref}/preview` compatibility adapter (FR-007/FR-008,
User Story 5, SC-001, API Shape). This PR **amends ADR-048 and the spec in the
same change** to supersede that requirement and record the no-compat removal
(#1604): FR-008 is struck through, the API-Shape table drops the legacy route,
and the `governs.contracts` lists are repointed from
`ApiRuntime.preview_data`/`DataPreviewResponse` to
`routes.data.create_preview_session`/`PreviewEnvelopeModel`. The deletion is
therefore consistent with the governing documents as they stand in this PR, and
the spec's own §6 assumption explicitly allows adapter removal "by follow-up
issue." This is an in-scope, owner-directed decision, not a deviation.

## What was verified to PASS

### Backend preview subsystem (SPEC 1)
- `scistudio.previewers` package is self-contained (`models`, `registry`,
  `router`, `session`, `data_access`, `fallbacks`, `assets`, `project`,
  `_raster`, `_table_cache`). The `#1598` dependency-direction fix is real: the
  table-cache and raster pipeline moved **down** out of `api.runtime` so the
  previewer layer no longer imports up into the API layer.
- `PreviewRouter.resolve` implements ADR-048 §3 precedence exactly (project/
  package exact-collection → exact-item → parent → core collection fallback →
  core base fallback → `UnknownTargetError`), including the collection-capability
  guard that stops `Collection[Image]` mis-routing to a single-item viewer, the
  priority tie-break, the `RoutingAmbiguityError` on unresolved ties, and the
  project-default override (FR-003/FR-004/FR-005).
- Bounded data access never materialises whole arrays: Zarr is read with
  explicit per-axis slices (`handle[tuple(selector)]`, never `handle[...]`),
  TIFF is read `key=0`, every helper enforces row/byte/item/tile/dim budgets
  (FR-009/FR-010/SC-004). Non-finite cells are JSON-nulled so envelopes stay
  strict-JSON.
- All FR-011 metadata flags are mandatory on every envelope; the six core
  fallbacks + collection + plot + base catch-all exist (FR-012). Array previewer
  is strictly generic numeric (no LUT/OME/channel/label) per FR-013/FR-014.
- SVG is sanitised server-side (script/handler/external-href regex) **and**
  rendered in a frontend `<iframe sandbox="">` (FR-019, defense-in-depth).
- Same-origin asset serving is manifest-validated and path-confined under
  `asset_root`; remote/`data:`/`file:` URLs are rejected (FR-022/FR-024). The
  resource-params route bounds size/depth/item-count and strips private
  `_`-prefixed enrichment keys.
- `frontend_manifest` is framework-stamped first-class onto the envelope by the
  session manager from the resolved spec (#1579), with a legacy
  `metadata.frontend_manifest` fallback retained.
- `open_project` rebuilds the preview service so project-local previewers/
  defaults track the active project (FR-002).

### Frontend (SPEC 1)
- `PreviewHost` creates/reads/patches sessions, validates + same-origin-imports
  + mounts dynamic previewers, and falls back cleanly to the core viewer with a
  surfaced diagnostic on any validation/import/mount failure (FR-020/FR-029,
  US2.3). `dynamicPreviewer` never throws and rejects remote/`//`/scheme URLs.
- All nine `EnvelopeKind`s have a dedicated core viewer plus the dispatcher
  (`coreViewers.tsx`): dataframe, array (PyCharm-style numeric heatmap + per-axis
  slice selectors + min..max legend), series (chart/table), text (truncation +
  editor handoff), artifact, composite (slot inventory + child routing),
  collection (gallery + child routing), plot (PNG/JPEG `<img>`, PDF iframe, SVG
  sandboxed iframe, export button), and typed error.
- `TableViewer` pagination/sort migrated off the deleted REST adapter onto the
  routed session `PATCH` (FR-008-superseded). `DataPreview.tsx` mounts
  `PreviewHost` in production for the selected-output preview panel; the legacy
  envelope cache is replaced by the keyed `previewEnvelopeCache` (FR-021).

### Imaging package (SPEC 1, FR-025/FR-026)
- `scistudio_blocks_imaging.previewers:get_previewers` registers `Image`
  (`kind=array`) and `Label` (`kind=composite`) package previewers
  (`owner_kind=PACKAGE`, priority 100), each with a same-origin `FrontendManifest`
  and a backend provider that reads bounded data. Wheel packaging ships the
  `assets/viewer.js` via `artifacts` + `force-include`; entry-point and monorepo
  fallback both wired. The packaged `viewer.js` is a dependency-free vanilla-ESM
  module (LUT/range/slice/zoom/metadata) honouring the constrained host API. The
  `kind=array` choice lets a failed dynamic load degrade to the core Array viewer
  (FR-026).

### AI plot tools (SPEC 2)
- All six MCP tools (`list_plot_targets`, `scaffold_plot`, `list_plot_examples`,
  `read_plot_source`, `validate_plot`, `run_plot_job`) register with
  `tags={"category:plot", ...}` (FR-001/FR-003). R/ggplot2 paths exist
  (scaffold/runtime/examples). `run_plot_job` writes `current.*` with
  current-overwrite + `current.json` and isolates failure (FR-026/FR-027/FR-028).
- The producer→consumer dead-wire is closed (#1606): `POST /api/plots/run`
  runs the job, `register_plot_artifact` stamps a previewable `PlotArtifact`
  catalog record, and the frontend builds a `plot_artifact` target that routes to
  `core.plot.basic`. Proven end-to-end by `tests/api/test_plot_preview_wiring.py`.

### Developer docs (SPEC 3)
- No `produced_type=` remains in `docs/block-development/**` (SC-001). The
  recent-ADR impact matrix covers ADR-036 → ADR-048 (SC-010). The new
  `previewers-and-plots.md` author guide and the `scistudio-write-plot` skill
  (which requires `validate_plot` before `run_plot_job`) are present
  (SC-004/SPEC3-US4).

### Legacy removal — confirmed clean
- Deleted with no compat shim and **no dangling references**: backend
  `ApiRuntime.preview_data`, `routes.data.preview_data`, the
  `GET /api/data/{ref}/preview` route, `DataPreviewResponse`,
  `_envelope_to_legacy_preview`, `_preview_cache.py`; frontend
  `api.getDataPreview`, `DataPreviewQuery`/`DataPreviewResponse`, `ImageViewer.tsx`,
  `PreviewRenderer.tsx`, `luts.ts`, `useSlicePreview.ts`, `useOmeMetadata.ts`,
  `OMEMetadataPanel.tsx`, and the store `previewCache`/`previewLoading` slice.
  Grep confirms the only residual `ImageViewer` token is a comment example.

### Tests executed by the auditor (worktree @ 669ddcf3)
- `tests/previewers/`, `tests/api/test_previewers.py`,
  `tests/api/test_plot_preview_wiring.py`, `tests/api/test_preview_plot_jobs.py`,
  `tests/ai/test_mcp_tools_plot.py` → **105 passed, 1 skipped** (the skip is the
  R-unavailable plot path, allowed by SC-007).
- `packages/scistudio-blocks-imaging/tests/test_previewer_registration.py` →
  **14 passed**.
- Frontend vitest `PreviewHost.test`, `coreViewers.test`, `plotPreview.test`,
  `DataPreview.test`, `api-surface.test` → **5 files / 43 passed**.

Per-viewer e2e coverage is satisfied: every envelope kind is exercised by a
backend fallback test, and the interactive viewers (array, dataframe, plot,
collection, error, dynamic-mount/fallback) are exercised by frontend tests.

## Findings (minor, non-blocking)

### F1 — No production GUI entry point to *run* a plot (tracked: #1623)
The plot **render** path is fully wired and tested, but there is no production
GUI affordance that calls `runPlotJob` → `plotTargetFromRunResponse` →
`PreviewHost`; only the MCP/agent path and the API + helper functions are live.
This is deferred by a tracked `TODO(#1623)` in `frontend/src/lib/api/data.ts`
("Out of scope per #1606 — runtime reachability only"). Consequence: ADR-048 §11's
manual-verification item "creating a plot from the UI/CLI/MCP target picker …
viewing SVG/PDF output" is only reachable via MCP/CLI today, not the GUI. SPEC 2
scopes plot authoring to MCP tools + skill (not a GUI pane), so this is **not an
FR violation** — but it is a real gap against the ADR's UI framing. Recommend the
owner confirm #1623 tracks the GUI plot pane and accept the deferral.

### F2 — Stale/contradictory comment in `data.ts` TODO(#1623)
The same TODO asserts "The host element (PreviewHost) is itself not yet mounted
in production (tracked by #1592 / #1623)." This is **inaccurate**: `DataPreview.tsx`
mounts `PreviewHost` in production for the output preview panel, and #1592 is
listed as closed by this PR. Only the *plot-run pane* is unmounted. The wording
could mislead a reader into thinking the whole preview surface is dead. Recommend
correcting the comment to scope it to the plot pane.

### F3 — Stale docstrings referencing the removed "compatibility adapter"
After the no-compat deletion (#1604), several **live** helpers still describe a
"legacy REST compatibility adapter" that no longer exists:
- `session.PreviewSessionManager.render_target` — "used by the legacy REST
  compatibility adapter" (actually live: child routing in `read_resource`).
- `data_access.png_data_uri` — "feeds the REST compatibility adapter" (actually
  live: `array_previewer` + imaging `image_provider` raster `src`, FR-026).
- `data_access.composite_raster_slot` — "Used by the compatibility adapter"
  (actually live: imaging `label_provider`, with test coverage).
- `previewers/__init__.py` / `models.EnvelopeKind` docstrings — reference "the
  compatibility adapter before a runtime exists".

These are **documentation inaccuracies only — no dead code** (each symbol has a
real caller, verified by grep across `src/` + `packages/`). Recommend a docstring
cleanup pass so the surviving call-sites are described by their real consumers.

### F4 — `PreviewHostApi.saveArtifact` is a stub (tracked: #1626)
`saveArtifact` returns `Promise.reject("save not available")`, deferred by a
tracked `TODO(#1626)` ("Out of scope per #1606"). **Export** (download) is
implemented and satisfies the user-facing FR-018/SC-007 "save/export controls";
only the separate save-to-project-destination half of ADR-048 §5 is deferred.
Acceptable per governance §3.6 (tracked TODO citing an issue). Recommend the owner
confirm #1626 ownership.

### F5 — (informational) No dedicated frontend unit tests for Series/Text/Artifact/Composite viewers
The interactive viewers are unit-tested; the four simpler presentational viewers
are exercised only via the dispatcher and their backend providers
(`tests/api/test_previewers.py`). Low risk; optional to add direct render tests.

## Recommendation

Approve the implementation. None of F1–F5 block merge. Before the
`[DO NOT MERGE]` prefix is removed, the owner should (a) confirm the #1623 GUI
plot-pane and #1626 save-to-project follow-ups are accepted deferrals, and
(b) optionally take the cosmetic docstring/comment cleanup in F2/F3.
