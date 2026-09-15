---
name: scistudio-write-miniapp
description: Build or improve an interactive MiniApp for exploring project data, comparing results, or adjusting parameters with visible feedback. Use for a standalone data tool; use scistudio-write-plot for a static figure and scistudio-write-block for a workflow step.
---

# scistudio-write-miniapp

## 1. What a MiniApp is

A MiniApp is a small interactive application you write for the user, opened on a
piece of their data. It is for exploration and interaction: the user moves its
controls, sees the effect at once, and tries analyses while the next step is still
unknown. Technically it is a panel folder whose page reads the data through the
panel SDK and may call functions in its own resident Python process (`panel.py`).

A MiniApp is not a workflow node: it produces no typed outputs and no lineage.
When the exploration settles into a repeatable step, the user can convert it into
an interactive workflow block; the MiniApp stays available.

| User needs | Route |
|---|---|
| To explore a result repeatedly, with visible feedback | **MiniApp**: this skill. |
| A reusable view of a data type in previews | `scistudio-write-panel` (preview panel). |
| One recorded decision during a workflow run | `scistudio-write-panel` (interactive panel) with `scistudio-write-block`. |
| A static figure of an output | `scistudio-write-plot`. |
| A computation that must be a reproducible workflow step | `scistudio-write-block`. |

## 2. Steps to write a MiniApp

For an existing MiniApp, focus on the requested change and reuse what still fits.
These are working steps, not separate approval stages.

1. **Read the first request quickly.** Read the creation brief when there is
   one, and keep its source, folder, `id`, and type. Take a quick look at the
   data (`inspect_data`), just enough to ask good questions; do not build yet.
2. **Ask with a questionnaire.** Replace the template page with a questionnaire
   built from the standard question components: what to show, which interaction,
   which settings matter. Give each question a few concrete alternative answers
   drawn from the data. Every answer is optional and every question offers
   "Decide for me". Run the questionnaire check; when it reports errors, fix
   every one and run it again until it passes. Only then tell the user in one
   sentence to fill it in and press Submit.
3. **Wait for the second round.** In the in-app agent session, SciStudio tells you
   when the user submits. Over WebMCP, call the waiting tool; if it times out, tell
   the user your watch timed out and ask them to tell you once they have
   submitted. Then read the answers; treat "Decide for me" and unanswered
   questions as yours to choose sensibly.
4. **Check what already exists.** Call `list_panels` for the data type. When the
   user wants to change an existing MiniApp, improve it; when the user wants a
   different app, write a new one.
5. **Look at the real data.** Use `get_block_output`, `inspect_data`, and
   `preview_data` to learn its type, shape, axes, units, and metadata, and what
   each dimension means.
6. **Choose the main view and interaction.** Decide how the data is shown (see
   the rules in §4), the primary controls with their starting values, and the
   visible result of using them, following the user's answers. The first view
   shows the data already loaded.
7. **Build it on the real source.** Write `panel.json` and `index.html`, and add
   `panel.py` only when the task needs Python. Wire every control to its visible
   effect, with loading, empty, and error states.
8. **Validate and open.** Call `validate_panel(path="panels/<panel_id>")` and fix
   every error, then `open_miniapp` on the intended block output and read the
   result for startup errors.
9. **Look at it and try the main interaction.** Screenshot the app, use it once
   (move the slider, click the button), screenshot again, and confirm the result
   changed on the data. Fix what fails and repeat the affected check. Leave the
   app open and tell the user what it does, which data it uses, and what you
   tested.

## 3. Anti-patterns

- Replacing the data with a summary the user did not ask for, such as a histogram
  of an image, which loses its spatial layout.
- Opening on a blank page that waits for unexplained configuration.
- Building the app straight from the first request of a new MiniApp without
  asking the questionnaire first.
- A questionnaire with required answers, no "Decide for me" option, or no Submit.
- Telling the user to fill in a questionnaire that has not passed the check.
- Hand-writing tables, pagers, loading states, or heatmaps that the prebuilt
  components already provide, or importing a component that does not exist
  (there is no `Slider` or image viewer component).
- Presenting sampled, reduced, or transformed data as the unchanged original.
- Overwriting input data or editing workflows as a side effect of exploring.
- Reading a whole large dataset on every control change; letting an older
  calculation overwrite a newer result.
- Treating a MiniApp as a workflow step, or expecting its files to carry lineage.
- Reporting the app as working from a successful `open_miniapp` or one
  screenshot, without trying its main interaction.

## 4. Defaults, tool sequence, and failure handling

**Rules for every MiniApp.**

- **Show the data as it is.** Unless the user asks for something else, draw data
  in its own form: an image or 2-D array as an image, a table as a table, a
  series as a line, with its dimensions, orientation, and aspect ratio kept. A
  summary may sit beside the data, never in its place. For a threshold tool, show
  the image with the pixels that pass highlighted, and keep the original and the
  result distinguishable.
- **Build from the prebuilt components.** Use the `panel-ui.js` components and
  the `renderers.js` data views wherever they fit, and write custom drawing only
  for what they do not cover (for example a mask overlay on a canvas).
- **Make it look good and easy to use.** Use color with purpose (the theme tokens
  and a clear color scale or legend), give the data most of the space, label every
  control in plain language with its current value, put each control next to its
  effect, and keep instructions short. A user should understand the app without
  reading a manual.
- **Keep the user oriented.** Name the data and any selected slice or channel,
  and label display-only adjustments, calculations, and exports.

**The questionnaire.** The first page a user sees in a new MiniApp is a short
questionnaire, so the tab is never empty, the user sees that the app is being
built for them, and the request gets clearer before you build.

- Use only the standard question components; do not hand-build form controls.
- Keep it short: the few questions whose answers change what you build. Offer
  concrete alternatives based on the data (for a 2-D array: "threshold explorer",
  "slice browser", "region measurement").
- Every answer is optional, and every question has "Decide for me".
- Every questionnaire must work before the user sees it: run the questionnaire
  check, fix every error it reports, and repeat until it passes. Never hand the
  user a questionnaire that failed the check or was not checked.
<!-- TODO(#2295): replace with the component names, submit API, waiting tool,
     and questionnaire check from the questionnaire PR once it lands. -->

**Files.** A MiniApp is `panels/<panel_id>/`:

| File | Purpose |
|---|---|
| `panel.json` | `id` (equal to the folder name), `api_version: "1.0"`, `contexts: ["miniapp"]`, exactly one entry in `types`, a short `name`, and a `description`. Required. |
| `index.html` | The page; local JS and CSS may sit beside it. Required. |
| `panel.py` | Python setup and callable functions. Optional. |
| `panel.sample.json` | Fixtures for checking the page without a host. Optional. |

**SDK.** Load `../../sdk/1/panel.css` and `../../sdk/1/scistudio-panel.js`, and
await `window.scistudio.ready()` before anything else. A MiniApp receives
`input.ref` (the chosen block output), `read(op, params)` for bounded reads
(`array.plane`, `array.tile`, `table.page`, `series.points`, `collection.items`,
and others), `call(fn, args)` when the folder has a `panel.py`, and `save` to
export a file, plus `setViewState`, `onTheme`, `onDispose`, and `reportError`.
The page runs in a sandboxed iframe with no network or file access.

**Python (`panel.py`).** Use it when the task needs scientific libraries, data
kept loaded between interactions, or computation unsuited to the browser.

- `setup(data)` runs once when the process starts and receives the chosen output
  as a SciStudio data object (for an `Array`, `data.to_numpy()` gives the values).
  Keep what is expensive to load in a module-level name.
- Every function defined in `panel.py` whose name does not start with `_`, other
  than `setup` and `teardown`, is callable as `scistudio.call("<name>", {...})`,
  with the object's keys as keyword arguments. Imported functions are not
  callable.
- Return JSON-safe values, or a NumPy array, which reaches the page as
  `{data, dtype, shape}` with `data` as an `ArrayBuffer`. A function that raises
  rejects the call with the exception type as `code`; show it in the page.
- `teardown()` releases resources. Closing the tab ends the process; Restart runs
  `setup` again. Do not rely on view state or Python memory surviving a restart.
- Calls run one at a time. Debounce slider updates, ignore responses that a newer
  request has replaced, and use an **Apply** button for slow work.

**UI and libraries.** Build controls with `../../sdk/1/panel-ui.js` on the
bundled Preact module `../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js`
(`Input type="range"` for a slider; `Field` with `readout` for its value). Draw
data with `../../sdk/1/renderers.js` and `renderers.css`: `ArrayView` (a numeric
heatmap with index controls for extra axes), `DataFrameView`, `SeriesView`,
`TextView`, `ArtifactView`, `PlotView`, `CollectionView`, `CompositeView`, and
`MetadataView`. The page supplies their data and owns their state. Prefer the
bundled libraries (plotly, d3, three, pdfjs, lucide) under `scistudio.libBaseUrl`;
when a CDN is necessary, pin a version on `cdn.jsdelivr.net`,
`cdnjs.cloudflare.com`, or `unpkg.com`.

**Tool sequence.**

```
list_panels(data_type)                            # existing MiniApps for this type
get_block_output / inspect_data / preview_data    # the real data
# write panels/<panel_id>/panel.json, index.html, panel.py
validate_panel(path="panels/<panel_id>")
open_miniapp(panel_id, workflow_id, block_id, port)
screenshot_gui(target="miniapp", panel_id="<panel_id>")
# operate the main control with your browser or computer-use tools, then screenshot again
```

**Checking and failure handling.**

- `validate_panel` checks the folder, not the running page. `open_miniapp`
  reports whether the tab was asked to open; startup errors from `setup` show in
  the tab, and the process output is kept under `.scistudio/panels/logs/`.
- `screenshot_gui(target="miniapp")` captures the visible MiniApp over local MCP;
  it does not click. Operate controls with your browser, side-panel, or
  computer-use tools following `scistudio-use-gui`.
- A MiniApp missing from `list_panels` failed discovery; its `invalid` entry says
  why.
- Sample mode (`panel.sample.json` with the page opened outside SciStudio) helps
  iterate on layout, but does not test real reads or Python calls.
- When interaction tools cannot reach the app, finish the checks you can and state
  exactly which interaction remains untested.

## 5. Contracts and routing

**Contracts (MUST follow).**

- Panel SDK, read operations, `call`, and error codes:
  `user-guide/api-reference/panels-sdk.md`.
- UI components and data views: `user-guide/api-reference/panels-renderers.md`.
- `panel.json` and `panel.sample.json`: `user-guide/api-reference/panel-descriptor.md`.
- Tool names and arguments: the live MCP tool schemas.

**Agent reference.**

- Reading and constructing data values in `panel.py`:
  `.scistudio/agent-reference/data-types.md`.

**User guide.**

- How the user creates, runs, restarts, and converts a MiniApp:
  `user-guide/miniapps.md`.

**Related skills.**

- `scistudio-write-panel`: a preview panel or an interactive panel.
- `scistudio-write-block`: turning a settled MiniApp into an interactive block.
- `scistudio-use-gui`: operating the app to check its interaction.
- `scistudio-inspect-data`: learning the data before choosing the view.

## 6. Examples

**An array explorer with a threshold (tested).** It opens on an `Array`, shows the
current plane as a colored value table with slice controls for extra axes, and
greys out values at or below a threshold the user moves with a slider, while
`panel.py` counts how many values are above it across the whole array.

`panels/lab.array_explorer/panel.json`:

```json
{
  "id": "lab.array_explorer",
  "api_version": "1.0",
  "name": "Array explorer",
  "description": "Move a threshold across an array and watch the fraction above it, computed in panel.py against the real data.",
  "contexts": ["miniapp"],
  "types": ["Array"],
  "entry": "index.html"
}
```

`panels/lab.array_explorer/panel.py`:

```python
"""A MiniApp that holds one Array in memory and answers questions about it."""

import numpy as np

_state: dict[str, object] = {}


def setup(data):
    """Called once when the MiniApp opens, with the target reconstructed."""
    array = np.asarray(getattr(data, "to_memory", lambda: data)())
    _state["array"] = array


def summary():
    """Shape, dtype and range of the array."""
    a = _state["array"]
    return {
        "shape": list(a.shape),
        "dtype": str(a.dtype),
        "min": float(np.nanmin(a)),
        "max": float(np.nanmax(a)),
    }


def fraction_above(threshold: float):
    """The fraction of elements above `threshold`, recomputed per slider move."""
    a = _state["array"]
    finite = np.isfinite(a)
    total = int(finite.sum())
    above = int((finite & (a > threshold)).sum())
    return {"above": above, "total": total, "fraction": (above / total) if total else 0.0}
```

`panels/lab.array_explorer/index.html`:

```html
<link rel="stylesheet" href="../../sdk/1/panel.css" />
<style>
  /* Fixed column geometry for the value table. */
  .panel-table { table-layout: fixed; }
  .panel-table td,
  .panel-table thead th { width: 52px; min-width: 52px; max-width: 52px; overflow: hidden; text-overflow: ellipsis; text-align: right; font-variant-numeric: tabular-nums; }
  .panel-table th.panel-table-corner,
  .panel-table tbody th { width: 40px; min-width: 40px; max-width: 40px; text-align: right; opacity: 0.6; }
  .ax-threshold { font-variant-numeric: tabular-nums; }
  .ax-result { font-variant-numeric: tabular-nums; opacity: 0.85; }
</style>
<div id="root"></div>
<script src="../../sdk/1/scistudio-panel.js"></script>
<script type="module">
  import {
    html, render, useCallback, useEffect, useMemo, useRef, useState,
  } from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
  import {
    Card, ErrorState, Field, Input, Legend, LoadingState, Meta, Panel, ScrollArea, Table,
  } from "../../sdk/1/panel-ui.js";

  const api = window.scistudio;

  // ---- value formatting and heatmap colour.
  const SENTINELS = { NaN: "NaN", Infinity: "∞", "-Infinity": "-∞" };
  const numeric = (v) => (typeof v === "number" && isFinite(v) ? v : null);
  function formatCell(v) {
    if (v in SENTINELS) return SENTINELS[v];
    if (v === null || v === undefined) return "—";
    if (typeof v !== "number") return String(v);
    if (!isFinite(v)) return Number.isNaN(v) ? "NaN" : v > 0 ? "∞" : "-∞";
    if (v === 0) return "0";
    const abs = Math.abs(v);
    if (Number.isInteger(v) && abs < 1e6) return String(v);
    if (abs >= 1e5 || abs < 1e-3) return v.toExponential(2);
    return v.toFixed(3);
  }
  const lerp = (a, b, t) => Math.round(a + (b - a) * t);
  function heatmapColor(v, vmin, vmax) {
    const n = numeric(v);
    if (n === null || typeof vmin !== "number" || typeof vmax !== "number") return "transparent";
    if (vmin < 0 && vmax > 0) {
      const mag = Math.max(Math.abs(vmin), Math.abs(vmax)) || 1;
      const t = Math.max(-1, Math.min(1, n / mag));
      if (t < 0) { const k = -t; return `rgb(${lerp(247, 33, k)}, ${lerp(247, 102, k)}, ${lerp(247, 172, k)})`; }
      return `rgb(${lerp(247, 178, t)}, ${lerp(247, 24, t)}, ${lerp(247, 43, t)})`;
    }
    const span = vmax - vmin || 1;
    const s = Math.max(0, Math.min(1, (n - vmin) / span));
    return `rgb(${lerp(247, 8, s)}, ${lerp(252, 64, s)}, ${lerp(253, 129, s)})`;
  }
  function cellTextColor(v, vmin, vmax) {
    const n = numeric(v);
    if (n === null) return "rgb(var(--ink) / 0.4)";
    const mag = vmin < 0 && vmax > 0 ? Math.max(Math.abs(vmin), Math.abs(vmax)) || 1 : vmax - vmin || 1;
    const intensity = vmin < 0 && vmax > 0 ? Math.abs(n) / mag : (n - vmin) / mag;
    return intensity > 0.6 ? "#fffdf8" : "rgb(var(--ink))";
  }

  // ---- N-D slice controls: one index per non-displayed axis (re-reads the plane).
  function SliceAxes({ sliceAxes, indices, onChange }) {
    if (!sliceAxes.length) return null;
    return sliceAxes.map((ax) => {
      const last = Math.max(0, ax.size - 1);
      const value = indices[ax.axis] ?? ax.index;
      const clamp = (raw) => Math.max(0, Math.min(Math.round(isFinite(raw) ? raw : 0), last));
      return html`<${Field} key=${ax.axis} name=${`${ax.name} (${ax.size})`} readout=${`${value} / ${last}`}>
        <${Input} class="panel-field-range" type="range" min="0" max=${last} step="1" value=${value}
          aria-label=${`Slice along ${ax.name}`}
          onInput=${(e) => onChange(ax.axis, clamp(parseFloat(e.target.value)))} />
        <${Input} number type="number" min="0" max=${last} value=${value}
          aria-label=${`Index along ${ax.name}`}
          onInput=${(e) => onChange(ax.axis, clamp(parseFloat(e.target.value)))} />
      <//>`;
    });
  }

  function App() {
    const [summary, setSummary] = useState(null);
    const [plane, setPlane] = useState(null);
    const [indices, setIndices] = useState({});
    const [sliderPct, setSliderPct] = useState(50);
    const [frac, setFrac] = useState(null);
    const [error, setError] = useState(null);
    const planeReq = useRef(0);

    const fail = useCallback((e) => { const m = e?.message || String(e); setError(m); api.reportError(m); }, []);

    // Summary once (drives the threshold range and the facts strip).
    useEffect(() => { api.call("summary", {}).then(setSummary).catch(fail); }, [fail]);

    // Read the plane on mount and whenever a slice index changes.
    useEffect(() => {
      const req = ++planeReq.current;
      const keys = Object.keys(indices);
      const slice = keys.length ? indices[keys[0]] : 0;
      api.read("array.plane", { slice_index: slice, axis_indices: indices })
        .then((p) => { if (req === planeReq.current) { setPlane(p); setError(null); } })
        .catch((e) => { if (req === planeReq.current) fail(e); });
    }, [indices, fail]);

    const lo = summary ? summary.min : 0;
    const hi = summary ? summary.max : 1;
    const threshold = lo + ((hi - lo) * sliderPct) / 100;

    // Fraction above, recomputed in panel.py over the FULL array. One call at a
    // time; if the slider moved again meanwhile, re-read its latest value.
    const inflight = useRef(false);
    const pct = useRef(sliderPct);
    pct.current = sliderPct;
    const runFraction = useCallback(async () => {
      if (inflight.current || !summary) return;
      inflight.current = true;
      try {
        let sent;
        do {
          sent = pct.current;
          const th = lo + ((hi - lo) * sent) / 100;
          setFrac(await api.call("fraction_above", { threshold: th }));
        } while (sent !== pct.current);
      } catch (e) { fail(e); } finally { inflight.current = false; }
    }, [summary, lo, hi, fail]);
    useEffect(() => { runFraction(); }, [sliderPct, runFraction]);

    if (error) return html`<${Panel}><${ErrorState}>Could not read array: ${error}<//><//>`;
    if (!summary || !plane) return html`<${Panel}><${LoadingState}>Loading array…<//><//>`;

    const vmin = typeof plane.vmin === "number" ? plane.vmin : lo;
    const vmax = typeof plane.vmax === "number" ? plane.vmax : hi;
    const values = plane.values || [];
    const rows = values.length, cols = rows ? values[0].length : 0;
    const sliceAxes = plane.slice_axes ?? [];

    const items = ["Array", `shape [${summary.shape.join(", ")}]`, `dtype ${summary.dtype}`,
      `range ${formatCell(summary.min)} … ${formatCell(summary.max)}`];

    const stops = Array.from({ length: 9 }, (_, i) => heatmapColor(vmin + ((vmax - vmin) * i) / 8, vmin, vmax));

    return html`<${Panel}>
      <${Meta} items=${items} />
      <${SliceAxes} sliceAxes=${sliceAxes} indices=${indices}
        onChange=${(axis, idx) => setIndices((p) => (p[axis] === idx ? p : { ...p, [axis]: idx }))} />

      <${Field} name="Threshold" readout=${html`<span class="ax-threshold">${formatCell(threshold)}</span>`}>
        <${Input} class="panel-field-range" type="range" min="0" max="100" step="1" value=${sliderPct}
          aria-label="Threshold"
          onInput=${(e) => setSliderPct(Number(e.target.value))} />
      <//>
      <div class="ax-result">${frac
        ? `${frac.above.toLocaleString()} of ${frac.total.toLocaleString()} above — ${(frac.fraction * 100).toFixed(2)}%`
        : "…"}</div>

      <${ScrollArea}>
        <${Table}>
          <thead><tr><th class="panel-table-corner"></th>
            ${values[0]?.map((_, c) => html`<th key=${c}>${c}</th>`)}
          </tr></thead>
          <tbody>
            ${values.map((row, r) => html`<tr key=${r}><th>${r}</th>
              ${row.map((v, c) => {
                const n = numeric(v);
                const above = n !== null && n > threshold;
                // Above the threshold: the value's heatmap colour. At or below it:
                // greyed, so dragging the threshold lights up the kept region.
                const bg = above ? heatmapColor(v, vmin, vmax) : "rgba(127,127,127,0.16)";
                const fg = above ? cellTextColor(v, vmin, vmax) : "rgb(var(--ink) / 0.45)";
                return html`<td key=${c} title=${n === null ? "non-finite" : String(v)}
                  style=${`background:${bg};color:${fg}`}>${formatCell(v)}</td>`;
              })}
            </tr>`)}
          </tbody>
        <//>
      <//>
      <${Legend} min=${formatCell(vmin)} mid=${formatCell(vmin < 0 && vmax > 0 ? 0 : (vmin + vmax) / 2)} max=${formatCell(vmax)} stops=${stops} />
      <div class="panel-hint">
        ${summary.shape.join(" × ")}${plane.sampled || plane.truncated ? ` | showing a sampled ${rows} × ${cols} view (percentage is over every element)` : ` | displaying ${rows} × ${cols}`}
      </div>
    <//>`;
  }

  api.ready()
    .then(() => render(html`<${App} />`, document.getElementById("root")))
    .catch((e) => api.reportError(String(e?.message || e)));
</script>
```

What it shows: the page reads only the visible plane with `read("array.plane")`,
while the full-array statistic comes from `panel.py`; one `call` runs at a time
and re-reads the slider's latest value when it moved meanwhile; loading and
error states come from the prebuilt components; and it colors the cells itself
only because `ArrayView` cannot grey out the values below a threshold.

## 7. Available tools

The live MCP tool list is the source of truth; these are the tools this task
uses.

| Tool | What it does | When to use it |
|---|---|---|
| `list_panels` | Lists existing panels with their kind, optionally for one data type, and folders that failed discovery. | Before writing, to find an existing MiniApp; when one does not appear. |
| `get_block_output` / `inspect_data` / `preview_data` | Resolve and describe real data. | Before choosing the view. |
| `validate_panel` | Checks one panel folder the way discovery does. | After every change to the folder. |
| `open_miniapp` | Asks the open workspace to open a MiniApp tab on a block output. | After validation, to show the app on real data. |
| `screenshot_gui` | Captures the visible MiniApp or the workspace (local MCP only). | Before and after trying the main interaction. |
| `open_gui` | Returns the address of the running GUI. | Before operating the app in a browser. |
