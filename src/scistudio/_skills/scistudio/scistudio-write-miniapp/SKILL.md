---
name: scistudio-write-miniapp
description: Build or improve an interactive MiniApp for exploring project data, comparing results, or adjusting parameters with visible feedback. Use for a standalone data tool; use scistudio-write-plot for a static figure and scistudio-write-block for a workflow step.
---

# Write a MiniApp

A MiniApp is a small interactive app opened on a block output in SciStudio.
It has its own tab and can use a resident Python process for computation.
It can later be converted into an interactive workflow block.

## Design principles

- **Show the data in its original form.** An Image MiniApp should show the
  image. A two-dimensional Array should retain its two-dimensional layout,
  such as an image, heatmap, or matrix. Preserve meaningful axes, units,
  orientation, and aspect ratio. Do not replace spatial data with a histogram
  or summary numbers unless the user asks for that. Add summaries alongside
  the main view when they help.
- **Make the interface colorful and easy to use.** Use the provided components
  and theme colors. Give the data view most of the space. Use color to explain
  values, selections, overlays, and status; pair it with labels or legends.
  Controls should have clear names, useful defaults, and visible effects.
- **Make the first view useful.** Load the selected data and display a sensible
  initial result. Avoid a blank canvas waiting for unexplained configuration.
  Keep the primary controls next to the view they affect.
- **Keep users oriented.** Identify the data and any selected slice/channel.
  Distinguish the original view from a processed result. Label display-only
  adjustments, calculations, and exports clearly. Show loading, empty, and
  error states instead of silently doing nothing. Keep instructions short.
- **Respect the data.** Do not overwrite inputs or modify workflows as a side
  effect of exploring. Do not present sample, reduced, or transformed data as
  the unchanged original. Use real project data for the delivered app.

## Workflow

Follow these steps when building a MiniApp. For an existing app, focus on the
requested change and reuse the source, design, and implementation that still
fit. These are working steps, not separate user approval stages.

### Step 1 — Understand the task and inspect the data

- Read the creation brief. Identify the source, target directory, and what
  the user wants to see or do. Reuse the supplied source and directory.
- Inspect the actual data type, shape, and relevant metadata. Establish what
  the dimensions mean before choosing a representation.
- Use a MiniApp for repeated interaction: browsing slices, comparing results,
  selecting regions, or adjusting parameters. A static figure belongs in
  `scistudio-write-plot`; a workflow computation belongs in
  `scistudio-write-block`.
- Ask only when missing information would change the purpose or interpretation
  of the app. Otherwise choose reasonable defaults.

Continue when you know which data the app uses and which task it should help
accomplish.

### Step 2 — Choose the main view and interaction

- Choose a view that preserves the data's structure and supports the task.
  For an image threshold tool, show the image and mask with a threshold
  control. A histogram can supplement that view.
- Choose the primary controls, their initial values, and the visible result
  of using them. Plan a useful first render with the data already displayed.
- Select the components and renderer from [UI and libraries](#reference-ui-and-libraries).
  Keep the interface focused on the requested task.

Continue when you can describe the main view, the main interaction, and the
result the user should see. Do not turn this into a separate design document.

### Step 3 — Build a working app on the real source

- Create or update the required files using [Files and runtime](#reference-files-and-runtime).
  Preserve the supplied descriptor identity and input type.
- Connect the view to real SDK reads. Add `panel.py` only when Python is useful
  for the requested computation. Load only the libraries the app needs.
- Wire each control to its visible effect. Include clear labels, current
  values, and loading, empty, and error states where applicable.
- Keep reads bounded and expensive updates deliberate. Prevent an old
  computation response from replacing the result of a newer interaction.

Continue when the initial view and primary interaction are implemented with
real data, rather than placeholder content.

### Step 4 — Validate and open

- Run `validate_panel(path="panels/<panel_id>")` and fix validation errors.
- Use `open_miniapp` with the intended source. Check the tool result and
  startup errors. A successful open request does not prove the page rendered.

Continue to the runtime check once the app opens without a known startup
failure.

### Step 5 — Inspect the view and try the main interaction

- Use `screenshot_gui(target="miniapp", panel_id="<panel_id>")` to inspect
  the rendered app in its visible tab. Check that
  real data is visible, its representation is appropriate, and the main
  controls fit the available space.
- Use your available computer use tools to exercise the primary interaction
  once: move the slider, click the button, or manipulate the data view. Take
  another screenshot and check the visible result and any errors reported by
  the app or available logs. For the threshold tool, change the threshold and
  verify that the mask updates on the image; a changing number alone is
  insufficient. `screenshot_gui` captures the view; it does not operate controls.
- If computer use is unavailable or cannot reach the MiniApp, complete the
  visual and computation checks you can perform and state which interaction
  remains unverified. Do not describe a screenshot as an interaction test.
- Fix observed failures and repeat the affected check. Add a computation check
  or an edge case only when a specific risk warrants it. Small representative
  inputs are sufficient for focused computation checks.

Stop checking when the requested view and interaction work and no observed
failure remains. Do not run an unrelated full test suite or repeat successful
checks after unrelated edits. Sample mode does not verify real SDK reads or
Python calls.

### Step 6 — Leave the app ready to use

Leave the app open when possible. Briefly state what it does, which data it
uses, and what you tested. State any unverified behavior directly. Do not make
the user's first trial the only test while describing the app as verified.

## Reference: Files and runtime

Write inside `<project>/panels/<panel_id>/` unless the user requests otherwise.

| File | Purpose |
| --- | --- |
| `panel.json` | Identity, supported input type, and entry page. Required. |
| `index.html` | The interface; local JavaScript and CSS files may accompany it. Required. |
| `panel.py` | Optional Python setup and callable functions. |
| `panel.sample.json` | Optional fixtures for testing the page without a host. |

The descriptor uses `api_version: "1.0"`, `contexts: ["miniapp"]`, and exactly
one entry in `types`. Its `id` must match the directory name. Preserve the
`id`, `contexts`, and `types` provided by an existing creation brief. Give the
app a short name and a description of what it does.

The HTML runs in a sandboxed iframe. Use the SciStudio SDK for data and host
services; do not depend on browser access to project files or host internals.
A MiniApp is not a workflow node and does not publish downstream outputs.

Load these relative to the default entry page:

```html
<link rel="stylesheet" href="../../sdk/1/panel.css">
<script src="../../sdk/1/scistudio-panel.js"></script>
```

Call `await window.scistudio.ready()` promptly, before reading data or calling
Python. Then use:

| SDK surface | Use |
| --- | --- |
| `input`, `context` | The bound data reference, type, and context. |
| `read(op, params)` | Bounded data access: metadata, image/array planes and tiles, table pages, series points, text, or collection items. |
| `call(fn, args)` | Call a public function in this MiniApp's `panel.py`; available only when the context provides Python calls. |
| `save({name, mime, data})` | Export a file through SciStudio. |
| `setViewState`, `onTheme`, `onDispose`, `reportError` | View state, theme changes, cleanup, and error reporting. |

Read operations include `metadata`, `array.plane`, `array.tile`, `table.page`,
`table.xy`, `series.points`, `text.chunk`, `collection.items`,
`composite.slots`, `artifact.info`, and `artifact.file`. Choose a bounded read
that fits the view; avoid transferring an entire large dataset for each edit.

Use Python when the task needs scientific libraries, reusable loaded data, or
computation unsuitable for the browser:

- `setup(data)` receives the reconstructed SciStudio data object once per
  process start. Keep reusable data in module state.
- Public functions defined in `panel.py` are callable via `call`. Imported
  functions, underscore-prefixed names, `setup`, and `teardown` are not calls.
- Return JSON-safe values or a NumPy array. Handle call failures in the UI.
- `teardown()` releases resources. Closing the tab ends its process;
  restarting it runs setup again. Switching tabs keeps it alive.

Calls run one at a time. Debounce expensive slider updates and ignore obsolete
responses so an older calculation cannot replace the newest result. Keep
startup and interaction quick; use an explicit Apply button for costly work.
Do not assume view state or Python memory survives a restart.

## Reference: UI and libraries

The component set is `../../sdk/1/panel-ui.js`, paired with `panel.css`.
It uses the bundled Preact/HTM module:

```js
import { html, render } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
import { Panel, Card, Field, Input, Button } from "../../sdk/1/panel-ui.js";
```

| Need | Available components |
| --- | --- |
| Layout | `Panel`, `Stack`, `Row`, `Spacer`, `Card`, `ScrollArea` |
| Controls | `Field`, `Input`, `Select`, `Button` |
| Data and navigation | `Table`, `Legend`, `ItemGrid`, `Item`, `ListRow`, `Pager` |
| Labels and feedback | `Meta`, `Hint`, `Label`, `Badge`, `Icon`, `LoadingState`, `EmptyState`, `ErrorState` |

`Input` accepts native input props, including `type="range"` for a slider.
`Field` accepts `name` and an optional `readout`. There is no separate Slider
or ImageViewer component in this set: compose native controls and a data
renderer rather than inventing component imports.

Use the core data-view components for the main display before building a
custom renderer. Import from `../../sdk/1/renderers.js` and also load
`../../sdk/1/renderers.css`. They use the same bundled Preact instance as
`panel-ui.js`. They accept data, controlled state, and callbacks; they do not
read the SDK or open a previewer themselves. You own data reads, computation,
and the state updates triggered by callbacks.

| Data | Component | Main inputs and interaction |
| --- | --- | --- |
| Numeric arrays | `ArrayView` | `data` as a scalar, nested array, or typed array; optional `shape`, `axes`, `dtype`; `indices` and `onSliceChange(axis, index)` |
| Tables | `DataFrameView` | `data` with `columns` and row objects; `query` and `onQueryChange(nextQuery)` for caller-owned paging/sorting |
| Series | `SeriesView` | `data` with `values`, optional `index`, and `source_indices` for decimated samples; preserve gaps; `mode` and `onModeChange`; chart mode needs bundled Plotly |
| Text | `TextView` | `text`, optional `meta`; `done=false` while more text is arriving |
| Files | `ArtifactView` | `info` and an authorized file or caller-created Blob URL in `url` |
| Saved figures | `PlotView` | `info`, `file`; controlled zoom/page/format callbacks; `onSave(format)`; PDF rendering needs `libBaseUrl` |
| Collections | `CollectionView` | `items`, optional `count`, `itemType`; `onOpen(ref, item)`; `hasMore` and `onLoadMore()` for paging, `loading` during the page request |
| Composite data | `CompositeView` | `slots`; `onOpen(ref, slot)` |
| General metadata | `MetadataView` | `meta` and optional `file` |

For example, an app can pass a computed two-dimensional result directly to
`ArrayView` and place its own controls beside it:

```js
import { ArrayView } from "../../sdk/1/renderers.js";
// result is the actual rectangular array returned by the app's computation.
render(html`<${ArrayView} data=${result} />`, document.getElementById("result"));
```

Keep original dimensions when supplying a flat array with `shape`. The numeric
`ArrayView` is not a domain-specific Image viewer: do not claim image channel,
mask overlay, or microscopy controls it does not provide. Use the appropriate
image renderer for those tasks. Read each component's exported props before
adding controls; do not invent callback names. Keep original data and computed
results in separate component instances when comparison helps the task.

Bundled libraries are served beneath `scistudio.libBaseUrl` after `ready()`:

| Library | Path beneath the library base | Use |
| --- | --- | --- |
| Preact/HTM | `preact-htm@3.1.1/dist/preact-standalone.module.js` | UI composition without a build step |
| Plotly | `plotly@2.35.3/dist/plotly.min.js` | Interactive plots and heatmaps |
| D3 | `d3@7.9.0/dist/d3.min.js` | Scales and custom data graphics |
| Three.js | `three@0.180.0/build/three.module.min.js` | 3D views |
| Lucide | `lucide@1.45.0/dist/lucide.min.js` | Icons; load before using `Icon` |
| PDF.js | `pdfjs@5.4.149/build/pdf.min.mjs` | PDF rendering |

Load only what the app needs. Prefer these local assets, which work offline.
If another dependency is necessary, pin its version and use an allowed HTTPS
host: `cdn.jsdelivr.net`, `cdnjs.cloudflare.com`, or `unpkg.com`.
