# ADR-054 Phase B — Core Preview Panel Parity Checklist (FR-040)

Slice **B2a**: the nine compiled core previewers rewritten as core-tier HTML
panels under `src/scistudio/panels/builtin/`. Each panel keeps the id of the
legacy `PreviewerSpec` in `scistudio.previewers.fallbacks.core_previewer_specs`,
so once discovered it shadows the compiled viewer through the one shared
namespace (FR-007) — verified in `tests/panels/test_builtin_panels.py`.

This file records, per panel, what the compiled viewer showed versus what the
panel shows, and how the #1886 faithful-display rulings (items A/B/D/E) are met
where relevant. The compiled viewers stay in place this slice for legacy
envelopes; their retirement is a later slice (FR-043, #2288).

Legend: ✅ at parity · ➕ improved faithful display · ⚠️ blocked / follow-up.

---

## core.dataframe.basic — replaces `DataFrameViewer` (`TableViewer.tsx`)

| Behaviour | Compiled viewer | Panel |
|---|---|---|
| Column display | columns in table order | ✅ same, from `table.page` |
| Paging | First/Prev/Next/Last + jump box | ✅ First/Prev/Next/Last buttons |
| Sort | click header cycles asc → desc → none, pushed to session | ✅ same, re-reads `table.page` with `sort_by`/`sort_dir` |
| Row summary | "N rows × M columns" | ✅ plain `rows A–B of N · page X/Y` |
| Truncation notice | `MetadataBadges` (sampled/truncated/incomplete) | ➕ **removed** per #1886 Part 1 — a paged table is complete by construction, so no truncated/incomplete badge is shown |
| View state | — | ➕ reports `{page, sort_by, sort_dir}` so maximize restores the page |

**#1886 Part 1:** no truncated/incomplete badge. Asserted in
`builtin.test.ts` ("plain pager, no truncation badge").

## core.array.basic — replaces `ArrayViewer` (flagship, #1886 item A + E)

| Behaviour | Compiled viewer | Panel |
|---|---|---|
| Value surface | numeric heatmap table of the plane's values, **downsampled** to ≤256/side (`array.plane`) | ➕ numeric heatmap of **native-resolution real values** read by `array.tile`; the strided `array.plane` read is used **only** as a small, labelled "overview (navigation aid)" minimap, never as the value surface |
| Per-cell colour | diverging (signed) / sequential (unsigned), 0 = white | ✅ same `heatmapColor` ported to JS |
| Value legend | vmin..vmax gradient + min/mid/max | ✅ same, from the plane's finite `vmin`/`vmax` |
| Reaching every cell | limited to the downsampled plane | ➕ Row/Col offset + window-size controls and a click-to-navigate minimap pan the native tile to **every** real cell |
| N-D slice axes | one slider per non-displayed axis | ✅ same `slice_axes` sliders (range + number) |
| Non-finite cells | rendered `—`/NaN/∞ from a `null` payload | ➕ backend sends sentinel strings `"NaN"`/`"Infinity"`/`"-Infinity"`; panel renders `NaN` / `∞` / `-∞` distinctly (italic, never blank) — #1886 item E |
| shape / dtype / axes | info bar | ✅ same |

**#1886 item A:** default view is native-resolution real values via tiling; the
plane overview is only a navigation minimap. **item E:** NaN/∞/-∞ shown
distinctly. Both asserted in `builtin.test.ts`. The "What Is A Type" tutorial's
Image→table-of-numbers still holds: the value surface stays a numeric grid.

## core.series.basic — replaces `SeriesViewer` (#1886 item D)

| Behaviour | Compiled viewer | Panel |
|---|---|---|
| Chart | Plotly line+markers | ✅ dependency-free canvas line chart with axis min/max labels |
| Table mode | index/value table toggle | ✅ same toggle |
| Dropped NaN/inf points | a diagnostic "skipped N nonnumeric rows" | ➕ explicit banner naming **how many** points were NaN/∞ and **where** (`nonfinite_positions`), honouring `nonfinite_positions_complete` — #1886 item D |
| Decimation | not surfaced | ➕ discloses "showing K of N points (uniform-index)" when the read was decimated |

**#1886 item D:** dropped points never silently vanish. Asserted in
`builtin.test.ts` ("surfaces dropped NaN/inf points").

## core.text.basic — replaces `TextViewer`

| Behaviour | Compiled viewer | Panel |
|---|---|---|
| Paged text | `<pre>` of the bounded chunk | ✅ same, from `text.chunk` |
| Encoding / language | — (implicit) | ➕ shows `language · encoding · total bytes` |
| Truncation notice | amber notice with total bytes + editor handoff | ✅ notice with total bytes; ➕ "Load more" pages forward via `next_offset` |

## core.artifact.basic — replaces `ArtifactViewer`

| Behaviour | Compiled viewer | Panel |
|---|---|---|
| Name / MIME / size | shown | ✅ same (size also human-readable) |
| Safe inline image | inline **data-URI** images only | ✅ image shown via the token-scoped `artifact.file` (blob) URL, no remote load |
| Non-image | metadata only | ➕ download link to the same guarded `artifact.file` URL |

## core.composite.basic — replaces `CompositeViewer`

| Behaviour | Compiled viewer | Panel |
|---|---|---|
| Slot inventory | slot name + type list | ✅ same, from `composite.slots` |
| Drill into a slot | `onOpenResource` (session child) | ✅ `open(ref)`; host mounts the slot's own panel with a Back action (PanelPreview) |

## core.collection.basic — replaces `CollectionViewer` (#1886 item B)

| Behaviour | Compiled viewer | Panel |
|---|---|---|
| Item cards | grid of item cards with display name + type | ✅ same |
| Item count reached | bounded sample (stopped at ~100) | ➕ pages through **every** item via the cursor path until `next_cursor` is null — no silent cap — #1886 item B |
| Drill into an item | `onOpenResource` | ✅ `open(ref)` with Back |
| Summary | "N type (showing M)" | ✅ same, M grows to the full count |

**#1886 item B:** reaches items past index 100. Asserted in `builtin.test.ts`
("reaches items past index 100 via the cursor path").

## core.plot.basic — replaces `PlotViewer` ⚠️ discovery blocked

| Behaviour | Compiled viewer | Panel |
|---|---|---|
| PNG/JPEG/GIF/WEBP | `<img>` | ✅ `<img src=artifact.file blob>` |
| SVG | sandboxed iframe | ✅ `<img>` (scripts never run in an image context) |
| PDF | browser iframe PDF viewer | ✅ local **PDF.js** from the library set (the browser PDF viewer will not run in a sandboxed frame; spec §6) — first page to canvas, graceful download fallback |
| Zoom / fit | 25%-step zoom layer | ✅ same zoom controls |
| Export | `onExport` save menu | ✅ `save({name, mime, data})` via the host save service |

**⚠️ Blocker (reported to the manager):** plot artifacts carry the synthetic
type `PlotArtifact` (`type_chain = ["DataObject", "PlotArtifact"]`), which is a
catalog record type, **not** a `TypeRegistry` type nor a core sentinel. Panel
descriptor validation (`scistudio/panels/descriptor.py`) therefore rejects
`types: ["PlotArtifact"]` with `FR-002: unregistered panel type 'PlotArtifact'`,
so the panel is not discovered live and does not yet shadow the compiled
`PlotViewer`. The folder is authored and its descriptor is validated in
isolation (`test_descriptor_parses_as_core_preview_panel` passes an extended
type set). Closing the gap is a one-line Phase-A enablement outside this slice's
write set (`src/scistudio/panels/builtin/**`): either allow `PlotArtifact` as a
core-tier sentinel in `descriptor.py`, or include synthetic catalog types in the
`registered_types` passed to `discover_panels`. The image path is fully
functional; live PDF.js rendering is to be confirmed in the browser-validation
step.

## core.base.fallback — replaces `ErrorViewer` and the default branch

| Behaviour | Compiled viewer | Panel |
|---|---|---|
| Type chain | — | ➕ shows the recorded type chain |
| shape / dtype | — | ➕ shown when present |
| Metadata | error display | ✅ recorded metadata JSON (host renders hard errors in its own error card) |
| Download | download capability | ➕ download via `artifact.file` when the object has stored bytes |
| Priority | -100 (last resort) | ✅ `panel.json` sets `priority: -100` |

---

## Offline (SC-007) and library use (FR-042)

Every panel references only the SDK (`../../sdk/1/scistudio-panel.js`), its own
files, and — for `core.plot.basic`'s PDF path — the local library set
(`pdfjs`). No panel references any network host;
`validate_external_references` returns no findings for all nine folders
(asserted in `tests/panels/test_builtin_panels.py`).

## Sample mode (FR-046 / #2294)

Every panel ships a `panel.sample.json` so the Panels tab (and an author or the
agent) can open its preview from the sample with no running host. Samples are
validated for shape in `tests/panels/test_builtin_panels.py` and drive the
`builtin.test.ts` render assertions.
