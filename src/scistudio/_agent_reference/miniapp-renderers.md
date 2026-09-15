# Data views for panels and MiniApps

## 1. Where to look

| You need | Read |
|---|---|
| Every data view and UI component, with its props, defaults, and callbacks | `user-guide/api-reference/panels-renderers.md` (generated) |
| The SDK reads that feed the views (`array.plane`, `table.page`, `series.points`, …) | `user-guide/api-reference/panels-sdk.md` |
| How to write a MiniApp | the `scistudio-write-miniapp` skill |
| How to write a preview or interactive panel | the `scistudio-write-panel` skill |
| Checking the rendered result | [gui-debug.md](gui-debug.md) |

## 2. Rules

- **Show the real, complete data.** This is the root rule of every panel: never
  sample, downsample, decimate, crop, or otherwise show less than the complete
  original data because it is large. Let the user reach all of it by paging,
  scrolling, or moving through slices, and show exact values.
- **Draw data with the core data views first.** `renderers.js` exports the views
  SciStudio's own previews use: `ArrayView`, `DataFrameView`, `SeriesView`,
  `TextView`, `ArtifactView`, `PlotView`, `CollectionView`, `CompositeView`, and
  `MetadataView`. Write custom drawing only for what they cannot show, such as a
  mask overlay or greyed-out values below a threshold.
- **Match the view to the data and keep its form.** Show an array with `ArrayView`,
  a table with `DataFrameView`, and a series with `SeriesView`, with the data's real
  shape and axes. Never replace the data with a summary the user did not ask for;
  put summaries beside it.
- **Load one Preact and the stylesheets.** Import the views and `panel-ui.js` on the
  vendored `../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js`, because a
  second Preact instance breaks hooks. Load `../../sdk/1/panel.css` and
  `../../sdk/1/renderers.css`.
- **The page owns data and state; the views only draw.** A view never calls
  `window.scistudio`; the page reads the data, keeps the state, and passes values and
  callbacks. Importing a view mounts nothing, and several can share a page.
- **Keep state controlled.** Hold `indices`, `query`, `mode`, `zoom`, and `page` in
  the page and update them from the matching callback (`onSliceChange`,
  `onQueryChange`, `onModeChange`, `onZoom`, `onPageChange`). Pass new objects when
  values change; views do not mutate their inputs.
- **Pass `error` on failure.** Every view accepts `error`, which replaces any earlier
  data, so a failed read or computation never leaves stale values looking current.
  A view shows its loading state while its main data prop is missing.
- **Navigate large arrays, never shrink them.** Give `ArrayView` an `array.plane`
  result as `plane` and the current window as `tile`, and read the window its
  `onScroll` asks for, so every cell stays reachable at its real value. Pass local
  `data` with `shape` only when the whole array fits in the page.
- **Page tables and collections through the SDK.** `DataFrameView` asks for a page
  through `onQueryChange`; answer with `table.page` and set `loading` meanwhile.
  `CollectionView` shows Show more when you pass `hasMore` and `onLoadMore`.
- **Give `SeriesView` every point.** Pass the series' complete values, and never
  thin them to draw faster. Chart mode needs Plotly
  (`../../lib/plotly@2.35.3/dist/plotly.min.js` or the `plotly` prop); table mode
  does not.
- **Give `PlotView` what PDFs and saving need.** Pass `libBaseUrl` from
  `scistudio.libBaseUrl` to render a PDF figure. In `onSave(format)`, read that
  format's own bytes (`artifact.file` with `variant`); never relabel another format.
- **Open children only through callbacks.** `CollectionView` and `CompositeView` call
  `onOpen(ref, item)`; in a preview panel pass it on to `scistudio.open(ref)`. Items
  are not clickable without `onOpen`.
- **Clean up what the page creates.** Revoke Blob URLs made for `ArtifactView` or
  `PlotView` in `onDispose`. Do not rely on the views to release page resources.
- **There is no image viewer component.** `ArrayView` is a numeric heatmap with index
  controls for extra axes. For channels, overlays, or microscopy controls, draw on a
  canvas or with a bundled library, beside the core views.
