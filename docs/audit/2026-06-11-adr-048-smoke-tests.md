# ADR-048 Browser Smoke-Test Evidence (3 rounds)

Manager-coordinated live e2e of the **integrated** ADR-048 implementation
(SPEC 1 previewers + SPEC 2 plot tools + SPEC 3 docs) driven against a running
backend, per the owner's smoke-test directive.

- **Environment:** integrated backend on `http://127.0.0.1:8000` (uvicorn
  `scistudio.api.app:create_app`, `PYTHONPATH` = SPEC 3 umbrella worktree,
  `SCISTUDIO_DEV=1` so the imaging monorepo package + its `scistudio.previewers`
  entry point are discovered), built frontend (PreviewHost) served at `/`. MCP
  server listening on TCP `127.0.0.1:62081`.
- **Backend surface confirmed live:** preview session routes
  (`/api/previews/sessions`, `/{id}`, `/resources/{rid}`, `/assets/{previewer_id}/{path}`)
  present in OpenAPI; `mcp.list_tools()` = **33 tools** including all 6 plot tools.
- **App load:** the SciStudio SPA mounts cleanly (landing page renders, console
  clean apart from benign Chrome-extension noise) — confirms the SPEC 1 frontend
  build integrates.
- Driver: a dedicated e2e agent over Chrome MCP; a 7-node `load_data` workflow
  (`project adr048-e2e`) produced real DataFrame/Array/Series/Text/Artifact/
  CompositeData + a 2-item Collection on disk; ran via the UI Run button →
  `completed`.

## Round 1 — previewer per data type (SPEC 1): **PASS**

Every type routed to the correct previewer + envelope `kind` (verified through the
routed session API against real on-disk storage; core fallback viewers rendered
in the live preview panel for Array/Text/CompositeData, screenshotted):

| Target type | previewer_id | kind |
|---|---|---|
| DataFrame | `core.dataframe.basic` | dataframe (cols + 40 rows) |
| Array | `core.array.basic` | array (shape [5,64,64], PNG src, slice meta) |
| Series | `core.series.basic` | series (200 pts + table) |
| Text | `core.text.basic` | text (bounded) |
| Artifact | `core.artifact.basic` | artifact |
| CompositeData | `core.composite.basic` | composite (slot inventory) |
| Collection | `core.collection.basic` | collection (count=2, item child resources) |
| **Image** | **`imaging.image.viewer`** (package, priority 100) | array (+ `image_metadata`) |
| plain Array (control) | `core.array.basic` | array |

- The **imaging package previewer** wins for `Image` while a plain `Array` uses the
  generic core viewer (the core/package boundary works). Its `frontend_manifest`
  (`module_url=/api/previews/assets/imaging.image.viewer/viewer.js`, api_version 1)
  is embedded in `metadata.frontend_manifest` and `GET` on that asset returns 200
  (a self-contained ESM module). `Image` uses `kind=array` so it degrades to the
  core Array viewer if the dynamic module fails (FR-026).
- Session lifecycle (create → GET → PATCH page/sort → bounded `resources/tile`
  64×64) all verified (FR-007/FR-009).
- Note: the live preview panel currently fetches the **legacy** `GET
  /api/data/{ref}/preview` for core types (FR-008 compatibility adapter); both it
  and the session API delegate to the same `scistudio.previewers` subsystem.

## Round 2 — plot function + fallback (SPEC 2): **PASS**

- Scaffolded `plots/df_overview/` (plot.yaml + matplotlib `render(collection,
  context)`), `validate_plot` → valid, `run_plot_job` → **succeeded**, wrote
  `.scistudio/previews/main/df/data/df_overview/current.svg` (+ `current.json`
  status=succeeded). The SVG renders through **`core.plot.basic`** (kind=plot,
  format=svg, `sandboxed:true` per FR-019). Screenshotted.
- **Invalid plot → fallback (FR-025):** a deliberately-broken render → `run_plot_job`
  returned `status=failed` with a *sanitized* error (no crash/500); `current.json`
  recorded `status:failed`, `outputs:[]`; the prior good artifact stayed intact and
  the workflow parquet data was untouched. The `PlotPreviewer` returns graceful
  typed error envelopes (kind=error) for unsupported-format / missing-artifact.

## Round 3 — built-in agent + new MCP tools (SPEC 2): **PASS** (with one distinction)

- `tools/list` over the live MCP server returned **33 tools**, incl. all 6 new
  plot tools. All six exercised end-to-end (list_plot_targets → 7 targets;
  list_plot_examples → matplotlib/seaborn/ggplot2; scaffold_plot; read_plot_source;
  validate_plot; run_plot_job) plus the minimal scaffold→edit→run→artifact loop.
- The UI **AI Chat panel is present and functional** (Claude Code + Codex providers
  installed, screenshotted). **Distinction:** the tool walk was driven directly
  against the MCP server (same surface/`ctx` the embedded agent uses) rather than a
  live billed PTY conversation, to avoid non-deterministic quota/hang risk.

## Bug found in smoke testing — FIXED in-PR

- **FR-016 (SPEC 2): `run_plot_job` received an EMPTY collection.** `_flatten_to_refs`
  read items under a bespoke `"_collection_items"` key, but the worker/scheduler/
  checkpoint layers emit the canonical Collection wire-form `{"_collection": True,
  "items": [...], "item_type": "..."}`. Fixed (commit `aede02ad`, propagated to
  SPEC 3 `d9441db2`): read `"items"` when `"_collection"` is set; regression tests
  over the canonical wire-form + single-ref/legacy paths added. ruff + mypy clean.

## Other observations (out of ADR-048 scope / not bugs)

- Canvas LoadData inline Path field renders empty when a workflow is loaded from
  disk (the stored `config.path` is intact on the backend and runs succeed; canvas
  save did not wipe it). Pre-existing LoadData inline-editor behaviour (ADR-028/036),
  not ADR-048.
- `Image` cannot be produced via `load_data` (no ADR-043 load capability for `Image`
  — imaging Image comes from process/app blocks); Image **previewer routing + rich
  viewer + manifest** were verified via the session API on a real catalog ref typed
  as Image (the authoritative routing path).

## Not fully verified (with reason)

- A live **agent-driven** (PTY) tool walk — deliberately not run to avoid billed
  quota / PTY-hang risk; covered via the equivalent direct-MCP surface.
- DataFrame/Series **visual** panel screenshots — overlapping canvas made per-node
  selection flaky; stopped per the anti-rabbit-hole protocol and verified both fully
  via the session API on their real parquet storage instead.

## Verdict

All three rounds **PASS**. One real SPEC 2 bug (FR-016 empty-collection) was found
and fixed in-PR with regression tests. The previewer routing (incl. the package
previewer + same-origin dynamic manifest), the bounded session/data-access surface,
the preview-side plot run + failure isolation, and the 6 new MCP plot tools are all
verified working against the integrated build.
