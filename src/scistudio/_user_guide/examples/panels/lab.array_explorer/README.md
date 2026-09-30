# MiniApp example — an Array explorer

A complete **MiniApp** — a standalone panel with its own tab, opened on one
block output — in three files. It shows the current plane of an `Array` as a
colored value table with slice controls for extra axes, and greys out values
at or below a threshold the user moves with a slider, while
[`panel.py`](panel.py) counts how many values are above the threshold **across
the whole array**. The page reads only the visible plane; the full-array
statistic comes from Python. This is the tested pattern behind the shipped
`scistudio-write-miniapp` agent skill.

## Where it goes

Copy this folder into your project's `panels/` directory as
`panels/lab.array_explorer/` — the relative paths in `index.html`
(`../../sdk/1/...`, `../../lib/...`) resolve from there. Then open it from a
block output's **Open MiniApp** action.

## The three files

| File | What it shows |
|---|---|
| [panel.json](panel.json) | The descriptor: `contexts: ["miniapp"]`, exactly one entry in `types` (`Array` — the data it opens on), a short `name` and `description`. The `id` must equal the folder name. |
| [panel.py](panel.py) | The resident Python process. `setup(data)` runs once when the MiniApp opens and keeps the array in memory; every other top-level function is callable from the page as `api.call("<name>", {...})`. |
| [index.html](index.html) | The page: awaits `api.ready()`, reads with `api.read("array.plane", ...)`, calls `api.call("fraction_above", ...)`, and renders with the prebuilt panel components. |

## What to notice

- **Bounded reads on the page, real compute in Python.** The table shows one
  plane from `read`; the percentage is computed in `panel.py` over every
  element — the page never loads the whole array.
- **One call at a time.** Calls run serially; the page debounces the slider
  and re-reads its latest value after each call, so a fast drag costs one call
  plus the newest position, not a queue.
- **Loading and error states** come from the prebuilt components
  (`LoadingState`, `ErrorState`), and failures also go to `api.reportError`.
- **The iframe sandbox.** The page has no network, no fetch, no storage; the
  SDK (`window.scistudio`) is the only door to data and Python.

A MiniApp produces no typed outputs and no lineage — it is for exploration.
When the exploration settles into a repeatable step, convert it into an
interactive block (see the [Data Router block](../../blocks/interactive-data-router/)).
