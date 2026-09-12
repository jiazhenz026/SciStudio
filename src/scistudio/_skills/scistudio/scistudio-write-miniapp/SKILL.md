---
name: scistudio-write-miniapp
description: |
  Use when the user wants to LOOK AT, COMPARE, or TUNE something on their
  project's data interactively — "let me drag a threshold and see the mask",
  "show both peak tables side by side so I can click through the differences",
  "I want to scrub through the stack". The answer is a MINIAPP: a small
  HTML page in ``<project>/panels/<panel_id>/``, opened on one block
  output, optionally backed by a ``panel.py`` that holds the data in memory
  and answers calls from the page.

  Offer a MiniApp whenever the user wants to keep looking rather than be
  told once. NOT for a single answer or a static figure — a one-off number
  or chart is scistudio-write-plot. NOT for a step that belongs in the
  pipeline and produces data other blocks consume — that is
  scistudio-write-block. NOT for a block that pauses mid-run to ask the
  user one question — that is an interactive block
  (scistudio-write-block).
---

# scistudio-write-miniapp

A MiniApp is the user's own small tool: a page mounted on one block output,
alive for as long as the tab is open. It is not a workflow node, it claims no
lineage, and nothing downstream consumes it.

## When to offer one

Offer a MiniApp, without being asked, when the user's request is about
*looking*: exploring a result, comparing two of them, or turning a knob and
watching what changes. Say what you are offering in one sentence and build it
if they agree. When the request is answered once and stays answered, do not —
that is a plot or a block.

## The directory

`<project>/panels/<panel_id>/` holds everything. The `panel_id` is lowercase
dotted segments and **must equal the directory name**.

| File | Role |
|---|---|
| `panel.json` | The descriptor. Required. |
| `index.html` (or whatever `entry` names) | The page. Required. |
| `panel.py` | Optional. The Python the page calls. |
| `panel.sample.json` | Optional. Lets the page be opened outside SciStudio. |

`panel.json` keys: `id`, `api_version` (`"1.0"`), `contexts` (`["miniapp"]`),
`types` (**exactly one** for a MiniApp — the type of the output it opens on),
`name`, `description`, and optionally `version`, `entry`, `priority`. When a
MiniApp was created for you from a request, keep the `id`, `contexts`, and
`types` you were given.

## The page

Plain HTML and JavaScript. Load the SDK with
`<script src="../../sdk/1/scistudio-panel.js"></script>`; `../../sdk/1/panel.css`
and `../../sdk/1/panel-ui.js` are there too and give you the host's look for
free. `window.scistudio` then offers:

- `ready()` — **await it before your first `read` or `call`.** The host drops a
  page that has not signalled ready within ten seconds.
- `context`, `input` — what you are mounted on: the target's ref and type.
- `read(op, params)` — the data, without materialising it. Operations:
  `metadata`, `table.page`, `table.xy`, `array.plane`, `array.tile`,
  `series.points`, `text.chunk`, `artifact.info`, `artifact.file`,
  `collection.items`, `composite.slots`.
- `call(fn, args)` — your `panel.py`. Present only in a MiniApp.
- `save({name, mime, data})` — hand the user a file through the host.
- `setViewState`, `onTheme`, `onDispose`, `reportError`.

The page runs in a sandboxed frame: no cookies, no login, no same-origin
access, and nothing it writes persists. Everything it needs comes through the
SDK.

## `panel.py`

Optional, and worth adding whenever the work is too heavy or too Python-shaped
for the page — the data stays loaded between calls instead of being re-read.

- `setup(data)` runs once when the tab opens, with the target already
  reconstructed as a SciStudio data object. Hold what you need on module state.
- Every other function defined in `panel.py` whose name does not start with `_`
  is callable from the page. A name `panel.py` merely imports is not.
- `teardown()`, if defined, runs when the tab closes.
- Return JSON-safe values, or a NumPy array — the page receives that as an
  `ArrayBuffer` with its dtype and shape.
- Raising is fine and expected: the page gets the exception type and message and
  the process keeps running.

Limits worth designing around: one call at a time per tab (16 may wait), 60 s
per call, 120 s for `setup`, 64 MiB per result. Keep `setup` cheap enough that
the tab opens promptly, and keep each call small enough to feel live.

## Libraries

Prefer the local set — it is served from SciStudio itself, so it works offline
and cannot break under the user: **d3**, **plotly**, **three**, **pdfjs**,
**lucide**, **preact-htm**. Reach them under `scistudio.libBaseUrl`.

If you need something else, `https://` from `cdn.jsdelivr.net`,
`cdnjs.cloudflare.com`, or `unpkg.com` only, with the version pinned in the
URL. Any other host fails validation outright; an unpinned version is a
warning, and it means the user's tool can change under them.

## Check it, then open it

```
mcp__scistudio__validate_panel(path="panels/<panel_id>")   # errors must be empty
mcp__scistudio__open_miniapp(panel_id=..., workflow_id=..., block_id=..., port=...)
```

`validate_panel` reads the descriptor and scans the page files for external
references; its `errors` name the field to fix. Run it before you tell the user
anything is ready.

`open_miniapp` asks the open workspace to show the tab. Read its `opened`
field: when it is `False` no tab opened, `reason` says why, and you must tell
the user the MiniApp is ready and name it — never that it is on screen.

To check a page with no host running, put a `panel.sample.json` beside it with
`context`, `input`, and a `reads` / `calls` map; opening the page directly then
serves those instead of talking to the backend.

## Anti-patterns

- Calling `read` or `call` before `await scistudio.ready()`.
- More than one entry in `types`, or an `id` that differs from the directory
  name — both are refused at discovery.
- Loading a script from a host outside the allowlist, or without a pinned
  version.
- Re-reading the whole target on every call instead of loading it once in
  `setup`.
- Reporting that a MiniApp is open when `open_miniapp` returned `opened=False`.
- Building a MiniApp for something the user asked once and will not ask again.
