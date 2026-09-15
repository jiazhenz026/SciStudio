# Preview panel example — the built-in Array panel

This folder is the **verbatim source of SciStudio's built-in Array preview
panel** (`core.array.basic`), the panel the preview column shows when you
select an `Array` (or any `Array` subclass, such as the
[Image type](../../types/image/)) and choose the Array panel.

It is shipped here so you can read a real, working preview panel — every line
below runs in the product. To author your own panel, create a new folder under
your project's `panels/` with an id of your own (`core.` ids are reserved for
built-ins); this one is the reference.

## The contract, visible in the files

| File | What it shows |
|---|---|
| [panel.json](panel.json) | The descriptor: `contexts: ["preview"]` claims the preview context, `types: ["Array"]` claims the type (a panel for the exact type beats a panel for its parent), and `entry` names the page. |
| [index.html](index.html) | The page shell: loads the panel stylesheet, the SDK (`../../sdk/1/scistudio-panel.js`), and the module. |
| [panel.js](panel.js) | The panel: awaits `api.ready()`, then reads the bound reference with **bounded reads only** — `array.plane` for the visible plane and its true extrema, `array.tile` for the scroll window — and renders the prebuilt `ArrayView`, which owns slice controls, the heatmap, and paging. |
| [panel.sample.json](panel.sample.json) | A recorded sample: open `index.html` as a top-level HTTP page and the SDK answers from the sample, so the layout can be checked without a host. Sample mode does not test real reads. |

## What to notice in `panel.js`

- **Bounded reads, never the whole array.** A preview panel may only ask for
  what it shows: the plane for the legend and slice geometry, a tile for the
  scrolled window. There is no read here that scales with the array's size.
- **One expensive read at a time.** `coalescingQueue` collapses a slider drag
  into at most one in-flight plane read plus the latest position — a read per
  pointer event would queue dozens of whole-plane scans.
- **View persistence.** `api.setViewState` remembers the chosen slice indices
  and scroll offset, so reopening the preview shows the plane you left.
- **Errors surface twice.** A failed read is shown in the page *and* reported
  via `api.reportError`, which lets the surrounding preview shell offer its
  recovery.

Relative paths (`../../sdk/1/...`, `../../lib/...`) are correct for any folder
directly under a project's `panels/` directory; that is the layout this
example expects.
