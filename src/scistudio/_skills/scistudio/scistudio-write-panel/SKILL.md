---
name: scistudio-write-panel
description: Create or improve a SciStudio HTML preview panel or an interactive workflow decision panel. Use scistudio-write-miniapp for a standalone data app, scistudio-write-plot for a static figure, and scistudio-write-block for the associated workflow computation.
---

# scistudio-write-panel

## 1. What a panel is

A panel is an HTML page that SciStudio shows inside a sandboxed iframe. It reads
data and acts only through the panel SDK, and its context decides what data and
operations it receives. Choose the context from the user's intended outcome
before writing frontend code.

| User needs | Route and runtime contract |
|---|---|
| A reusable view of a data type in previews | **Preview panel**: a bound data reference, bounded SDK reads, and optional child navigation. |
| A decision during a workflow run | **Interactive panel**: the block's prepared JSON view, followed by one JSON decision. Pair with `scistudio-write-block`. |
| A standalone app with repeated computation and exploration | Use **`scistudio-write-miniapp`**: its own tab, data reads, and optional resident Python. |
| A static figure or workflow computation | Use `scistudio-write-plot` or `scistudio-write-block`; those tasks do not automatically need GUI checks. |

For an existing panel, preserve its identity and reuse working code.

## 2. Steps to write a panel

### Write a preview panel

1. **Look at the real data.** Pick a representative output of the type with
   `get_block_output`, then `inspect_data` and `preview_data`, to learn its shape,
   axes, units, and metadata.
2. **Check what already exists.** Call `list_panels` for this data type. When
   the user wants to change an existing panel, improve that one; when the user
   wants a different view, write a new panel beside it.
3. **Create the folder.** Write `panels/<panel_id>/panel.json` with
   `"contexts": ["preview"]` and `types` naming the registered types it shows,
   plus `index.html`.
4. **Build the view from SDK reads.** Await `scistudio.ready()`, read the bound
   reference with bounded `read(op, params)` calls, and page or slice large
   data. Give the data most of the space, keep its dimensions and aspect ratio,
   and label any sampling. Add loading, empty, and error states.
5. **Add a sample.** Write `panel.sample.json` with the reads the page makes, so
   the page can be checked without a host.
6. **Validate.** Call `validate_panel(path="panels/<panel_id>")` and fix every
   error.
7. **Check it on real data.** Preview a real output in the GUI, select your
   panel in the preview column's panel list, look at the first render, and try
   its main control (see "Check the result" in §4).

### Write an interactive panel

1. **Check the built-in panels first.** For routing items from inputs to outputs
   use `core.interactive.data_router`; for fixing pairs use
   `core.interactive.pair_editor`. Write a panel only when neither fits.
2. **Agree the two payloads with the block.** Decide the plain JSON the block's
   `prepare_prompt` sends (the view) and the plain JSON decision the panel sends
   back, which the block reads as `config["interactive_response"]`. Write or
   update the block with `scistudio-write-block`.
3. **Create the folder.** Write `panels/<panel_id>/panel.json` with
   `"contexts": ["interactive"]` (no `types` needed), plus `index.html`, and point
   the block's `PanelManifest(panel_id="<panel_id>")` at it.
4. **Build the page from the view.** Await `scistudio.ready()` and render
   `scistudio.input`, the prepared view; an interactive panel has no `read`. Put
   each control next to its visible effect.
5. **Submit one decision.** Validate the user's choice, then call
   `writeBack(decision)` once and disable confirmation; use `cancel()` only to
   withdraw.
6. **Add a sample and validate.** Write `panel.sample.json` with a representative
   view, call `validate_panel(path="panels/<panel_id>")`, fix every error, and
   `reload_blocks` after changing the block.
7. **Check it in a run.** Run the workflow on representative input, open the
   paused block's window, make a decision, and confirm the block receives it and
   produces its outputs (see "Check the result" in §4).

Ask only for missing information that changes the purpose or scientific
interpretation. Choose reasonable UI defaults for routine implementation details.

## 3. Anti-patterns

- An interactive panel with no button to submit the decision.
- Replacing the data with a summary the user did not ask for, such as a histogram
  of an image, which loses its spatial layout.
- Hand-writing tables, pagers, loading states, or heatmaps that the prebuilt
  components already provide.
- Writing an interactive panel when `core.interactive.data_router` or
  `core.interactive.pair_editor` already fits.
- Reading unbounded data, or ignoring `truncated` / `complete` in a read result.
- Hardcoding a port, server root, mount token, or deployment prefix instead of
  relative SDK paths.
- Relying on `fetch`, cookies, `localStorage`, project files, or the parent page;
  the iframe has none of them.
- Claiming `DataObject`, `Collection`, or `PlotArtifact` in `types`; those are
  reserved for built-in panels.
- Calling `read` or `call` from an interactive panel, adding a `panel.py` to a
  preview or interactive panel, or opening a MiniApp to get around the
  interactive contract.
- Calling `writeBack` twice, or retrying it after a failure.
- Importing a component that does not exist (there is no `Slider`; use
  `Input type="range"`).
- Declaring a panel done from a successful `validate_panel` or a screenshot,
  without trying its main interaction.

## 4. Defaults, tool sequence, and failure handling

**Rules for every panel.**

- **Always give an interactive panel a way out.** The user must be able to submit
  the decision from the page, with a clearly labelled button such as **Submit**
  or **Confirm**, enabled as soon as a valid choice exists. Without it the run
  stays paused and the user is stuck in the window.
- **Show the data as it is.** Unless the user asks for something else, draw data
  in its own form: an image or 2-D array as an image (`ArrayView` for an array),
  a table as a table, a series as a line, with its dimensions, orientation, and
  aspect ratio kept. A summary such as a histogram may sit beside the data, never
  in its place. For a threshold, for example, show the array with the pixels that
  pass highlighted, so the spatial picture stays visible.
- **Build from the prebuilt components.** Use the `panel-ui.js` components and
  the `renderers.js` data views wherever they fit, and write custom drawing code
  only for what they do not cover. They already handle theme, loading, errors,
  paging, and large data.
- **Make it look good and easy to use.** Use color with purpose (the theme tokens
  and a clear color scale or legend), give the data most of the space, label
  every control in plain language, put each control next to its effect, and keep
  the main action obvious. A user should understand the panel without reading
  instructions.

**Files and discovery.** A panel is `panels/<panel_id>/` with `panel.json` and an
entry page (`index.html` by default); local JS and CSS may sit beside them.
`panel_id` equals the folder name, uses lowercase dotted segments that start with
a letter (for example `myproj.text_view`), and must not start with `core.`. Set
`api_version` to `"1.0"`, a nonempty `contexts` list, and a clear `name` and
`description`. A preview panel needs `types`, such as `Text` or
`Collection[Text]`; when several panels claim the same type, the higher
`priority` wins. Project panels are discovered from the folder; after an edit,
reopen the view to load the new version, and select your panel in the preview
column's panel list instead of assuming it won routing.

**SDK.** Load `../../sdk/1/panel.css` and `../../sdk/1/scistudio-panel.js` from the
entry page, and await `window.scistudio.ready()` before anything else. What each
context receives:

| Context | Input | Operations | Services |
|---|---|---|---|
| `preview` | `input.ref`, the bound data | `read(op, params)` with bounded operations such as `text.chunk`, `table.page`, `array.plane`, `series.points`, `collection.items`, `composite.slots` | `open(ref)` for a child item or slot, `save` |
| `interactive` | `input`, the JSON view from `prepare_prompt` | `writeBack(decision)` once; `cancel()` to withdraw | `save` |

Every context also has `viewState` / `setViewState` for view preferences (not
results), `onTheme`, `onDispose`, and `reportError`. Show errors in the page as
well as reporting them. Ignore stale responses when a control changes quickly.

**UI and data views.** Build controls with `../../sdk/1/panel-ui.js` (`Panel`,
`Stack`, `Row`, `Card`, `Field`, `Input`, `Select`, `Button`, `Table`, `Legend`,
`Pager`, `LoadingState`, `EmptyState`, `ErrorState`) on the bundled Preact module
`../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js`. Draw data with the
views in `../../sdk/1/renderers.js` and `../../sdk/1/renderers.css`; the page
supplies their data from SDK reads or the prepared view.

**Libraries and network.** Prefer the bundled libraries (d3, plotly, three,
pdfjs, lucide, preact-htm), found by relative path or `scistudio.libBaseUrl`.
When a CDN is necessary, pin a version on `https://cdn.jsdelivr.net`,
`https://cdnjs.cloudflare.com`, or `https://unpkg.com`. The iframe has an opaque
origin and no network or data fetch (`connect-src 'none'`).

**Tool sequence.**

```
list_panels(data_type)                     # what exists already
get_block_output / inspect_data / preview_data   # the real data or view
# write panels/<panel_id>/panel.json, index.html, panel.sample.json
validate_panel(path="panels/<panel_id>")
# check in the GUI (preview) or in a run (interactive)
```

**Check the result.**

- `validate_panel` checks the descriptor, types, entry, and external references.
  It does not run JavaScript or prove that the page renders.
- For quick iteration, open the page as a top-level HTTP page with
  `panel.sample.json` beside it; outside an iframe the SDK answers from the
  sample. A `file://` page may block loading the sample. Sample mode does not test
  real reads, child navigation, saving, or workflow resumption.
- Then check the real thing with `scistudio-use-gui`: preview real data with the
  panel, or open the paused block's window in a test run. Look at the first
  render, try the main control, and check its visible effect and error states.
  For an interactive panel, confirm the decision reaches the block and the block
  produces its outputs; use representative input when a real decision would
  change the user's result.
- `screenshot_gui(target="workspace")` shows the desktop window over local MCP; it
  does not click anything.

**When something fails.** `validate_panel` errors name the key or file at fault;
fix them all and validate again. A panel missing from `list_panels` failed
discovery; its `invalid` entry says why. When the GUI or suitable tools are not
available, finish the checks you can and state exactly what remains unverified.

## 5. Contracts and routing

**Contracts (MUST follow).**

- Panel SDK, read operations, and error codes:
  `user-guide/api-reference/panels-sdk.md`.
- UI components and data views: `user-guide/api-reference/panels-renderers.md`.
- `panel.json` and `panel.sample.json`: `user-guide/api-reference/panel-descriptor.md`.
- Tool names and arguments: the live MCP tool schemas.

**Agent reference.**

- Interactive block declarations, `prepare_prompt`, and `interactive_response`:
  `.scistudio/agent-reference/block-contract.md`.

**Related skills.**

- `scistudio-write-block`: the block behind an interactive panel.
- `scistudio-write-miniapp`: a standalone app with its own Python.
- `scistudio-use-gui`: checking the panel in the running GUI.
- `scistudio-inspect-data`: learning the data a preview panel will show.

## 6. Examples

Each example is a complete panel folder: `panel.json`, `index.html`, and
`panel.sample.json`.

### Example: a text preview

These three files form a minimal panel in `panels/myproj.text_view/`. Extend
it for the task; this small example displays just the first bounded text chunk.

`panel.json`:

```json
{"id":"myproj.text_view","api_version":"1.0","contexts":["preview"],"types":["Text"],"name":"Text view","entry":"index.html"}
```

`index.html`:

```html
<!doctype html>
<meta charset="utf-8">
<title>Text view</title>
<link rel="stylesheet" href="../../sdk/1/panel.css">
<script src="../../sdk/1/scistudio-panel.js"></script>
<p id="status" role="status">Loading…</p>
<pre id="text" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>
<script>
const api = window.scistudio;
const status = document.getElementById("status");
api.ready().then(async () => {
  const chunk = await api.read("text.chunk", {});
  document.getElementById("text").textContent = chunk.text ?? chunk.content ?? "";
  status.textContent = chunk.truncated ? "First chunk only" : "Complete text";
}).catch(error => {
  status.textContent = error.message || String(error);
  api.reportError(status.textContent).catch(() => {});
});
</script>
```

`panel.sample.json`:

```json
{"context":"preview","input":{"ref":"sample-text","kind":"data_ref","recorded_type":"Text"},"reads":{"text.chunk":{"text":"A sample trace description.","truncated":false}}}
```

### Example: an interactive choice

Create `panels/myproj.pick/`. Its block prepares a JSON view such as
`{"question":"Accept this candidate?"}` and consumes the decision
`{"accepted":true}` after confirmation. Add data-specific displays and choices
from that prepared view. Use the block skill and block contract to implement
and validate the paired workflow block.

`panel.json`:

```json
{"id":"myproj.pick","api_version":"1.0","contexts":["interactive"],"name":"Review candidate","entry":"index.html"}
```

`index.html`:

```html
<!doctype html>
<meta charset="utf-8">
<title>Review candidate</title>
<link rel="stylesheet" href="../../sdk/1/panel.css">
<script src="../../sdk/1/scistudio-panel.js"></script>
<p id="question">Loading…</p>
<button id="confirm" disabled>Accept candidate</button>
<p id="status" role="status"></p>
<script>
const api = window.scistudio;
const confirm = document.getElementById("confirm");
const status = document.getElementById("status");
function showError(error) {
  status.textContent = error.message || String(error);
  api.reportError(status.textContent).catch(() => {});
}
api.ready().then(() => {
  document.getElementById("question").textContent = api.input.question;
  confirm.disabled = false;
  confirm.onclick = async () => {
    if (confirm.disabled) return;
    confirm.disabled = true;
    try {
      await api.writeBack({accepted: true});
      status.textContent = "Decision submitted";
    } catch (error) {
      showError(error);
      // The SDK consumes the one-shot submission even on failure.
      // Keep confirmation disabled; do not blindly retry a decision.
    }
  };
}).catch(showError);
</script>
```

`panel.sample.json`:

```json
{"context":"interactive","input":{"question":"Accept this candidate?"}}
```

## 7. Available tools

The live MCP tool list is the source of truth; these are the tools this task
uses.

| Tool | What it does | When to use it |
|---|---|---|
| `list_panels` | Lists existing panels with their kind, optionally for one data type, and folders that failed discovery. | Before writing, to reuse a panel; when a panel does not appear. |
| `validate_panel` | Checks one panel folder the way discovery does. | After every change to a panel. |
| `get_block_output` / `inspect_data` / `preview_data` | Resolve and describe real data. | Before building a preview panel, to learn the data. |
| `reload_blocks` | Rescans the block and type registries. | After changing the block behind an interactive panel. |
| `run_workflow` / `get_run_status` | Start a run and follow it. | To reach an interactive block's window in a test run. |
| `screenshot_gui` | Captures the desktop workspace (local MCP only). | To see the rendered panel. |
| `open_gui` | Returns the address of the running GUI. | Before checking the panel in a browser. |
