# Interactive panel example — the Data Router window

This folder is the **verbatim source of the built-in panel behind the Data
Router block** (`core.interactive.data_router`) — the window that opens while
the block is paused. Read it together with the
[interactive block example](../../blocks/interactive-data-router/): the block
file decides *what the panel is offered* and *what happens with the answer*;
this folder is *how the decision looks and is submitted*.

## The contract, visible in the files

| File | What it shows |
|---|---|
| [panel.json](panel.json) | The descriptor: `contexts: ["interactive"]` claims the interactive context. No `types` — an interactive panel is bound by the block's `PanelManifest`, not by data type. |
| [index.html](index.html) | The page: markup, the drag-and-drop styling, the SDK script. |
| [panel.js](panel.js) | The panel: renders `api.input` — the plain-JSON view from the block's `prepare_prompt` (`input_ports`, `items_per_port`, `output_ports`) — and submits the decision exactly once with `api.writeBack({ assignments })`. |
| [panel.sample.json](panel.sample.json) | A representative view, so the page can be opened standalone outside the iframe. |

## What to notice in `panel.js`

- **No reads.** An interactive panel renders the prepared view and submits one
  decision; it has no `read` (and no `panel.py`). Everything it needs must
  already be in `api.input` — which is why `prepare_prompt` exists.
- **One decision, once.** `api.writeBack` is called a single time, from the
  **Confirm** button, and the button disables while submitting. The SDK
  consumes the one-shot submission even on failure: the page shows the error
  and does not blindly retry. (The dialog around the iframe offers
  **Cancel** — withdrawing is the host's, not the panel's.)
- **The decision is plain JSON.** `writeBack({ assignments })` mirrors exactly
  what the block's `run` reads from `config["interactive_response"]`.

## Try it

Run a workflow containing a Data Router node; when the run pauses, this page
is what the block-owned window shows. Drag every item to an output and press
**Confirm** — the block resumes with your `assignments`.
