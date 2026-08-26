---
name: scistudio-write-panel
description: |
  Use when a block needs to PAUSE THE RUN AND ASK THE USER — an interactive
  block and the small window (panel) it opens: an ES module in
  ``<project>/blocks/<name>_panel/panel.mjs`` plus the block's
  InteractiveMixin / execution_mode / PanelManifest / prepare_prompt
  declaration. Covers picking a region on a trace, clicking a peak, routing
  items, confirming a segmentation — anything only a person looking at the
  specific data can decide.

  NOT for an ordinary block that computes without asking (scistudio-write-block).
  NOT for a preview figure (scistudio-write-plot). NOT for a config parameter
  the user sets before the run — that is ``config_schema``, not a panel.
---

# scistudio-write-panel

Author an interactive block: a block that pauses mid-run, opens a window onto
its own input data, takes the user's decision, and computes from it. This skill
is the **task flow**; the contract lives in
**`.scistudio/agent-reference/block-contract.md`** ("Interactive blocks") —
read it, do not guess.

An interactive block is **two files**, and both must be right:

| File | What it is |
|---|---|
| `blocks/<name>.py` | the block: `InteractiveMixin`, `execution_mode = INTERACTIVE`, a `PanelManifest`, `prepare_prompt`, and a `run` that reads the decision |
| `blocks/<name>_panel/panel.mjs` | the window: one plain ES module, no framework, no build step |

## Non-negotiable

1. **The panel MUST give the user a reachable way to BOTH confirm and cancel.**
   The run is paused on this window. A panel that renders neither leaves the
   person with no way forward and no way out of their own workflow. Two visible
   controls wired to `host.confirm(decision)` and `host.cancel()` — always,
   whatever else the window does. Nothing in the registry enforces this. You do.
2. **The module's `default` export is the panel.** `export_name` defaults to
   `"default"`; a named-only export fails to load as `export_missing`.
3. **`module_url` is always `/api/blocks/panels/<panel_id>/<file>`**, and
   `<file>` must be the file that really exists under `asset_root`. Any other
   shape fails as `import_failed`.
4. **`prepare_prompt` returns plain JSON, not the data.** Reduce the real inputs
   to a window-sized view (a downsampled trace, a summary table, a list of
   choices). The runtime rejects a payload that is not JSON-safe.
5. **One pause for the whole batch.** `prepare_prompt` receives the full input
   collections and the run pauses once. Do not ask the same question per item.

## Reuse first

Two built-in panels need no frontend code at all. Use one if it fits:

- `PanelManifest(panel_id="core.interactive.data_router")` — drag items from N
  inputs to M outputs.
- `PanelManifest(panel_id="core.interactive.pair_editor")` — reorder items to
  fix pairing across collections.

They ship with the app: leave `module_url` and `asset_root` unset. Write your
own panel only for something data-specific those two cannot express.

## Tool-call sequence

```
mcp__scistudio__list_blocks                  # reuse check — STOP if a match exists
mcp__scistudio__list_types                   # concrete port types
mcp__scistudio__scaffold_block(name="pick_baseline", category="interactive",
    input_ports={...}, output_ports={...})   # writes BOTH files; READ every warnings[]
# fill the three TODO(scaffold) markers: the payload reduction, the panel's
# content area, the compute body
mcp__scistudio__reload_blocks                # re-scan; READ its diagnostics
mcp__scistudio__validate_workflow            # once the block is a node
mcp__scistudio__open_gui                     # open the panel and click both controls
```

If your build's `scaffold_block` does not accept `category="interactive"`,
scaffold `category="process"` and add the interactive declaration plus the panel
module below by hand — the contract is the same either way.

## The minimal working panel

Copy this, then replace only the content area. Everything else is the contract.

```js
const API_VERSION = "1";

export default {
  apiVersion: API_VERSION,

  mount(container, host) {
    const payload = host.panelPayload || {};   // what prepare_prompt returned

    const root = document.createElement("div");
    root.style.cssText = "padding:16px;font-family:system-ui,sans-serif;";

    // --- your content: draw `payload`, collect the decision ---------------
    const content = document.createElement("pre");
    content.textContent = JSON.stringify(payload, null, 2);
    root.appendChild(content);

    // --- the exit: BOTH controls, always ---------------------------------
    const confirm = document.createElement("button");
    confirm.textContent = "Continue";
    confirm.addEventListener("click", () => host.confirm({ /* your JSON */ }));

    const cancel = document.createElement("button");
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => host.cancel());

    root.append(confirm, cancel);
    container.appendChild(root);

    return { unmount() { root.remove(); } };
  },
};
```

Whatever `host.confirm(...)` sends arrives in the compute phase as
`config["interactive_response"]`; `run` reads it with
`config.get("interactive_response", {})`.

A full, real example ships in the core tutorial *What is a type* — a batch
review panel with a canvas, a label list, and a Continue that refuses to finish
while a slide is unseen. Read it with `search_docs` / `get_doc` when you want a
worked one rather than a skeleton.

## Debug it yourself — do not hand the user a broken window

`reload_blocks` is the first stop: it reports why a block did not register and
whether its panel resolves. `validate_workflow` reports the same class of
problem once the block is wired into a graph. Read what they say before
changing anything.

The panel host reports one of these codes when a panel fails to open. Each maps
to one mistake:

| Code | What you did |
|---|---|
| `export_missing` | the module has no `default` export (or none matching `export_name`) |
| `not_a_panel_module` | the export has no callable `mount` or no string `apiVersion` |
| `api_version_mismatch` | the module's `apiVersion` major differs from the host's (`"1"`) |
| `import_failed` | `module_url` names a file the route does not serve — wrong shape, wrong filename, or the file is not under `asset_root` |
| `mount_failed` | `mount` threw; it must not throw for routine failures |

`remote_url_rejected` / `invalid_module_url` mean `module_url` was not a
site-relative `/api/...` path. Remote and inline URLs are never imported.

Then open the GUI (`open_gui`) and actually click both controls once. A panel
that mounts is not a panel that works.

## Mandatory rules

- `list_blocks` FIRST; reuse a built-in panel when routing or pairing fits.
- Both halves of the interactive declaration: `InteractiveMixin` **and**
  `execution_mode = ExecutionMode.INTERACTIVE`. The registry rejects one without
  the other, and also rejects a missing `prepare_prompt` or `interactive_panel`.
- `default` export, string `apiVersion`, `mount` returning `{ unmount }`.
- Confirm and cancel both reachable, on every panel.
- `prepare_prompt` returns plain JSON, sized for a window.
- After writing: `reload_blocks`, read the diagnostics, then open the GUI and
  click through the panel.

## Anti-patterns

- A panel with only a Confirm, or with its Cancel behind a state the user cannot
  reach — the run is paused and they are stuck.
- `export const panel = {...}` with no default export (`export_missing`).
- `module_url` pointing at `/api/interactive/panels/...`, at a bare filename, or
  at a file that is not the one on disk (`import_failed`).
- `asset_root` pointing anywhere but the directory beside the block `.py` that
  holds the panel file.
- Sending the raw arrays from `prepare_prompt` instead of a reduced view.
- Pausing per item instead of once for the batch.
- Declaring `InteractiveMixin` without `execution_mode=INTERACTIVE` (or vice
  versa) — the registry drops the block at scan time.
- Calling it done because the block registered. Registration says nothing about
  whether the window opens or whether the user can leave it.
