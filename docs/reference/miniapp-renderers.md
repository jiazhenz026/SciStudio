---
title: "MiniApp Core Renderer Components"
status: Active
owners:
    - "@jiazhenz026"
related_adrs:
    - 54
language_source: en
---

# MiniApp Core Renderer Components

## Contract

SDK major 1 exposes nine Preact presentation components through
`../../sdk/1/renderers.js`. Load `../../sdk/1/panel.css` and
`../../sdk/1/renderers.css`. Use the vendored Preact instance at
`../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js`; mixing Preact
instances breaks hooks. Individual `renderer-*.js` modules are also importable.
The core preview panels use these same components.

Components consume values, controlled state, and callbacks. They never read
`window.scistudio`, select a previewer by ID, open a context, or mount an iframe.
Importing the module does not mount UI. Callers own data acquisition, bounded
remote reads, computed results, persistence, downloads, and drill-down behavior.
Components only keep presentation details such as scroll geometry, draft
page-input text, and PDF rendering status. Multiple instances may coexist.

## Props

All components accept `error` (a displayable message). Absent required data
shows the existing loading surface. Pass new data/state objects when values
change; inputs are not mutated.

| Export           | Data props                                                                                                                                                                       | Controlled state and callbacks                                                                                                                                                             |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ArrayView`      | `data`: scalar, rectangular nested arrays, or typed numeric array; optional `shape`, `axes`, `dtype`. Flat data plus `shape` uses row-major indexing. Shape must match the data. | `indices`: axis-index map; `onSliceChange(axis, index)`. Caller updates indices. Original dimensions are preserved; the view selects a plane.                                              |
| `DataFrameView`  | `data`: `{columns: string[], rows: Record<string, unknown>[], total?, total_rows?, page?, page_size?, total_pages?, sort?: {by, direction}}`                                     | `query`: `{page, pageSize, sortBy?, sortDir?}`; `onQueryChange(nextQuery)` requests page/sort; `loading` marks an in-flight read. Caller supplies requested rows and echoed sorting.       |
| `SeriesView`     | `data`: `{values, index?, nonnumeric?, nonfinite_positions?, nonfinite_positions_complete?}` as returned by `series.points`, or computed numeric values/index arrays             | `mode`: `chart` or `table`; `onModeChange(mode)`. Chart uses injected `plotly` or `globalThis.Plotly`.                                                                                     |
| `TextView`       | `text`: literal document/computed string; optional `meta`: `{total_bytes?, encoding?}`                                                                                           | `done` defaults to true; false shows that further text is arriving.                                                                                                                        |
| `ArtifactView`   | `info`: `{name?, path?, mime_type?, size?}`; `url`: authorized file URL or caller-owned Blob/data URL                                                                            | `imageFailed`, `onImageError()` let the caller show failed-image status.                                                                                                                   |
| `PlotView`       | `info`: `{name?, mime_type?, formats?}`; `file`: `{mime_type?, url?, data?: ArrayBuffer}`                                                                                        | `zoom`, `onZoom(next)`; `saveFormat`, `onSaveFormatChange(format)`; `page`, `onPageChange(page)`; `saving`, `onSave(format)`. Save is disabled without a callback. PDF needs `libBaseUrl`. |
| `CollectionView` | `items`: `{ref?, data_ref?, display_name?, type_name?, metadata?}[]`; optional `count`, `itemType`                                                                               | `loading` indicates more items; `onOpen(ref, item)` receives selection. Caller owns pagination/navigation.                                                                                 |
| `CompositeView`  | `slots`: `{name, type_name?, ref?}[]`                                                                                                                                            | `onOpen(ref, slot)` receives selection.                                                                                                                                                    |
| `MetadataView`   | `meta`: `{type_chain?, shape?, dtype?, metadata?}`; optional `file`: `{name?, path?, mime_type?, size?, url?}`                                                                   | `imageFailed`, `onImageError()`                                                                                                                                                            |

`ArrayView` also accepts caller-owned `plane` and `tile` instead of `data` for
bounded remote arrays. `plane` uses `array.plane` response geometry
(`source_shape`, `source_dtype`, `axes`, `slice_axes`, `vmin`, `vmax`); `tile`
uses `{values: rowsOfValues, y0, x0}`. Pass `rowHeight`, a Preact `scrollRef`, and
`onScroll(event)` to drive bounded tile reads. The core shell implements this
read orchestration; raw local data is virtualized automatically. The displayed
extent and non-finite values retain the existing numeric heatmap semantics.

For chart mode, load `../../lib/plotly@2.35.3/dist/plotly.min.js` before rendering
`SeriesView`. Table mode requires no Plotly. For PDF plots, pass
`scistudio.libBaseUrl` to `PlotView`; PDF.js and its worker load from the pinned
local library. Image plots need no extra library. `onSave` receives the chosen
format; obtain that variant's actual bytes, never relabel another format's bytes.
Revoke caller-created Blob URLs on cleanup.

## Example: computed array with summary

Include the two stylesheets above, the SDK when Python calls are needed, and a
root element. This module composes the existing heatmap and text views without
creating another preview or changing the data shape:

```javascript
import {
    html,
    render,
    useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
import { ArrayView, TextView } from "../../sdk/1/renderers.js";

function Results({ values, shape }) {
    const [indices, setIndices] = useState({});
    return html`<div>
        <${ArrayView}
            data=${values}
            shape=${shape}
            indices=${indices}
            onSliceChange=${(axis, index) =>
                setIndices((old) => ({ ...old, [axis]: index }))}
        />
        <${TextView} text=${`Result shape: [${shape.join(", ")}]`} />
    </div>`;
}

// Use the actual result dimensions; a vector remains a vector.
const values = new Float64Array([1, 2, 3, 4]);
render(
    html`<${Results} values=${values} shape=${[4]} />`,
    document.getElementById("root"),
);
```

## Coverage and boundaries

The nine core families are Array, DataFrame, Series, Text, Artifact,
PlotArtifact, Collection, CompositeData, and DataObject fallback. Plugin-provided
Image viewers are outside this core inventory. Interactive pair/router panels
retain their separate write-back contracts. Read authority and the MiniApp's
ephemeral computation model remain as specified by ADR-054.

Behavior tests exercise all nine without a SciStudio host, controlled callbacks,
raw multidimensional data, and the existing core-shell suites. Browser/PDF
compositor evidence remains a separate live GUI validation responsibility.
