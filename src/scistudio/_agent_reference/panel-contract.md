# Panel contract

A **panel** is a window onto data: a directory holding a JSON declaration and one
self-contained HTML document. The host mounts the document in a sandboxed frame
and talks to it only by `postMessage`. There is no build step, no framework, no
import — you write one file and open it.

Two capabilities, four tiers, one message contract. This page is all of them.

Write one with `scaffold_panel`; it writes the three files below and a harness
you can open in a browser. Register it with `reload_panels`. Read an existing one
with `read_panel_source`; copy a pattern with `list_panel_examples`.

## On disk

```text
<tier>/panels/<panel_id>/
    panel.json      the declaration (required, this exact name)
    index.html      the entry document (name it in `entry`)
    harness.html    written by scaffold_panel; open it to check your work
```

One level deep — a panel is an immediate child of the tier's `panels/`
directory. Anything else in the directory is an asset the document may fetch
from `asset_base_url`, and only these suffixes are served: `.html` `.js` `.mjs`
`.css` `.map` `.json` `.svg` `.png` `.jpg` `.jpeg` `.woff` `.woff2`.

## The declaration (`panel.json`)

Six required fields; the rest have defaults. A declaration missing one is refused
with a diagnostic naming the directory and the field, and the rest of the tier
still loads.

```json
{
  "panel_id": "myproj.pick_baseline",
  "display_name": "Pick baseline",
  "target_types": ["Series"],
  "capability": "producing",
  "entry": "index.html",
  "api_version": "1",
  "features": ["region", "drag"],
  "priority": 0,
  "supports_collection": false,
  "provider": "myproj.panels:baseline_provider"
}
```

| Field | Required | Meaning |
|---|---|---|
| `panel_id` | yes | Stable, unique, and the directory name. Keep it when you copy a panel down a tier — that is what makes the copy shadow the original. |
| `display_name` | yes | What a person sees in the panel palette. |
| `target_types` | yes | Recorded data type names this panel claims (`list_types`). `[]` only for a panel a block opens by name. |
| `capability` | yes | `displaying` or `producing`. Exactly these two. |
| `entry` | yes | The entry document inside the directory. Must exist. |
| `api_version` | yes | `"1"`. A panel declaring a version the host does not accept is refused before it is mounted. |
| `features` | no | Free-form advertising tags (`table`, `sort`, `export`). Not capabilities. |
| `priority` | no | Tie-break within one tier and type specificity; higher wins. |
| `supports_collection` | no | Whether the panel renders a collection of its target types. |
| `provider` | no | `module:attribute` naming a Python provider that windows the data. Omit it and the shared bounded data-access layer serves the reads. |

## Capability

Declared statically, before the panel loads. There is no negotiation by which a
mounted panel acquires a capability it did not declare.

| Capability | May do | May not |
|---|---|---|
| `displaying` | Render what it is given; ask for more of the same object. | Hand any value back. It is granted no `emit`. |
| `producing` | Everything a displaying panel may, plus `emit`. | — |

`producing` satisfies a request for `displaying`; the converse does not hold. The
capability the *mount* is granted travels in `init.capability` and is not always
the one you declared — a producing panel opened from the preview surface is
granted display only. Read `init.capability`, not your own `panel.json`.

## The message contract

Every message in both directions is one envelope:

```json
{ "scistudio_panel": 1, "token": "<per-mount token>", "type": "init", "payload": {} }
```

The frame is granted `allow-scripts` and nothing else, so it runs at an opaque
origin: neither side can check `event.origin`. The **token** replaces that check.
The host issues it in `init`; every later message in both directions carries it,
and anything whose token does not match is ignored in silence. Post to
`window.parent` with target origin `"*"` — an opaque origin cannot be named.

### Host → panel

| Type | Payload | When |
|---|---|---|
| `init` | `api_version`, `panel_id`, `capability`, `target`, `bindings`, `read_limits`, `asset_base_url`, `restored_state` | Once, after your document loads. Answer `ready`. |
| `update` | `reason`, `changed` | The data or the query changed. `changed.target` is the new envelope. |
| `read_result` | `request_id`, `window` | Answers one `read`. |
| `resource_result` | `request_id`, `resource` | Answers one `resource`. |
| `host_action_result` | `request_id`, `ok`, `detail` | Answers one `host_action`. A person cancelling a save dialog is `ok: true` with `detail.status == "declined"`. |
| `error` | `code`, `message`, `request_id` | Something failed. With a `request_id` it ends that request; without one it is a panel-level failure. |
| `state_request` | `{}` | Hand back a serialisable snapshot with `state`, or `null`. |
| `teardown` | `{}` | Stop listening. |

### Panel → host

| Type | Payload | Notes |
|---|---|---|
| `ready` | `api_version` | Completes the handshake. Send it once, from the `init` handler. Until you do, the host treats the panel as not mounted. |
| `read` | `request_id`, `query` | One bounded windowed read. `query` is a patch — `page`, `page_size`, `sort_by`, `slice`. It has no `action` key. |
| `resource` | `request_id`, `resource_id`, `params` | Follow a resource the envelope listed: a composite slot, a collection item, an array tile. |
| `host_action` | `request_id`, `action`, `params` | Chrome the frame cannot perform for itself. `action` is exactly one of `export`, `download`, `editor_handoff`. |
| `emit` | `code` | **Producing only.** The code your panel produces. See the whitelist below. |
| `error` | `message`, `detail` | Before `ready` this is a load failure and the host mounts a fallback; after `ready` it is a diagnostic. |
| `state` | `state` | The optional snapshot, in answer to `state_request`. A snapshot that will not serialise is discarded, not raised. |

`read`, `resource` and `host_action` are the three request types; each carries a
`request_id` and is answered by exactly one result type, or by an `error` with
the same id.

### `init.target` and `init.bindings`

`target` is the envelope the backend produced: `kind` (`dataframe`, `array`,
`series`, `text`, `artifact`, `composite`, `collection`, `plot`, `error`),
`payload`, `metadata`, `diagnostics`, `resources`, `error`. Render `payload`;
respect `metadata.truncated` and `metadata.sampled` rather than implying you
showed everything.

`bindings` is `null` for a displaying mount, and for a producing one a mapping of
`name -> { type, snapshot }` naming the variables you may rebind. A panel bound
to more than one is ordinary.

`read_limits` carries at least `max_rows` and `max_bytes`. Size your `read`
requests to them; the backend enforces them regardless.

## What `emit` means, and the statement whitelist

A producing panel has exactly one outbound path — `emit` — and the **meaning of
what it emits is settled by where the panel is mounted**, never by the panel
itself. There are two contexts, and they check different things.

### Mounted in an explore session — the statement whitelist

The emission is appended as a notebook cell and queued. It is parsed **before**
anything is inserted, so a refused emission leaves the notebook exactly as it
was. Only these statement forms are admitted:

- an assignment whose **every** target is a plain name — including chained
  assignment and tuple or star unpacking of plain names;
- an `import` or `from ... import`;
- an expression statement calling `scistudio.output`.

Everything else is refused with an error naming the panel and the statement.
That includes an assignment to a subscript or an attribute, an augmented
assignment, an annotated assignment, a loop, a conditional, a `def`, a `class`,
a bare expression, and an empty snippet.

```python
df = df.drop(index=[3, 7])              # admitted
baseline, corrected = fit(df)           # admitted
import numpy as np                      # admitted
scistudio.output("corrected", corrected)  # admitted

df.iloc[3] = 0                          # REFUSED - assignment to a subscript
df.attrs["x"] = 1                       # REFUSED - assignment to an attribute
df += 1                                 # REFUSED - augmented assignment
df.drop(index=[3], inplace=True)        # REFUSED - a bare expression
```

The rule exists so the notebook's source keeps describing what the kernel holds:
a panel that changes rows **rebinds the name**, it does not mutate the object the
name points at.

### Mounted by an interactive block — the emission *is* the decision

When the panel is the window an interactive block opened, the emission is not
queued: it is **run**, and what it hands back becomes
`config["interactive_response"]`. Statement forms are not restricted here, but
the namespace is: `__builtins__` is empty and exactly one name is bound,
`scistudio`, whose only attribute is `output`. There is no `open`, no
`__import__` (so an `import` statement fails), no `eval`, no module and no host
object, and any identifier beginning with `__` is refused before the code runs.

Emit exactly one `scistudio.output(...)` call, and let its keyword arguments be
the whole decision. Emitting none, or more than one, is refused with an error
naming the block and the panel.

```python
selection = {"start": 402.0, "end": 431.5}
scistudio.output(baseline=selection)   # -> config["interactive_response"]
```

Writing to the whitelist above keeps one document working in both contexts,
which is why the built-in producing panels emit exactly an assignment to a plain
name and one `scistudio.output` call.

## Tiers, shadowing, and where to write

Four tiers. A panel in a lower tier shadows a panel of the same id in a higher
one, in this order:

| Tier | Where | Writable | Registered by |
|---|---|---|---|
| `project` | `<project>/panels/<panel_id>/` | yes | Existing as a directory. |
| `user` | `~/.scistudio/panels/<panel_id>/` | yes | Existing as a directory. |
| `package` | A directory an installed distribution declares in the `scistudio.panels` entry-point group | no | The entry point. Metadata only — no importable Python needed. |
| `core` | Shipped with the application | no | Existing as a directory. |

Write into `project` for a panel this project needs; `user` for one you want in
every project. **Core and package panels are read-only.** Change one by copying
its directory into a writable tier *under the same `panel_id`* — the copy then
shadows the original, and deleting the copy restores it.

Registration has exactly one trigger: **`reload_panels`**. A directory you add,
change or delete takes effect on the next rebuild and at no other moment. The
tool returns the panels it found with their tier and capability, plus every
refusal as a diagnostic; if your panel is missing, read `diagnostics` first — a
declaration missing a field names the field.

## Writing the document

- **Self-contained.** Markup, styles and script in the one file. No
  `<script src>`, no external stylesheet, no CDN, no bundler.
- **Escape nothing into the DOM.** The payload is a person's data. Use
  `textContent`, never `innerHTML`. The scaffolded skeleton does this
  throughout; keep it that way.
- **Gate every URL that comes from the payload.** If you render an artifact —
  `<img src>`, an `<iframe>` for a PDF, a link — the value has arrived over
  `postMessage` from a provider that need not be a built-in one, and
  `javascript:` in an `<iframe src>` executes *inside your panel's frame*,
  holding your own postMessage token. So it can `emit` as you. Accept only:
  - a `data:` URI whose media type you named, chosen **per element** — an
    `<img>` takes `image/png` and `image/jpeg`; a frame takes
    `application/pdf`; **neither takes `image/svg+xml` or `text/html`**,
    because a frame executes those; or
  - a root-relative path on this application's own origin, which is the only
    kind the asset route produces.

  Strip TAB, LF and CR **before** you check, because a browser strips them
  before it parses a URL: `/	/evil.example` is `//evil.example` by the time it
  is fetched. Anything else renders nothing, and says so rather than looking
  like an artifact that was never produced.

  `core.plot.basic`, `core.artifact.basic` and `core.base.fallback` all gate
  their `src` this way; read `safeAssetUrl` in the first of them for the shape.
  CodeQL will still flag the sink, because an allowlist returns the string it
  validated and the analyser follows the flow rather than the condition — that
  is expected and is not a reason to drop the gate.
- **Answer `init` with `ready`,** then render. A panel that never sends `ready`
  is treated as a failed load and the host mounts a fallback over your data.
- **Ignore what is not yours.** Drop any message whose `scistudio_panel` marker
  is missing or whose token does not match your mount.
- **A displaying panel sends no `emit`.** The host refuses it, and the harness
  will tell you.

## The harness

`scaffold_panel` writes `harness.html` beside your document. Open it — the tool
returns its path, and its URL on the running GUI once the panel is registered
(pair it with `open_gui`). It loads your document in the same sandboxed frame the
host uses, sends `init` with representative data for each declared target type,
answers every request you make, and prints both directions of the conversation
with your emissions called out.

It is not the host: it answers a `read` with the same stub window every time and
grants the capability your declaration claims. When your panel works there and
not in the application, the difference is data, not contract.

## Before authoring (rules)

1. Call `reload_panels` and **reuse** if a registered panel already covers the
   type.
2. Call `list_types`; declare `target_types` with the recorded names.
3. Call `list_panel_examples`, or `read_panel_source` on a `core.*` panel, for a
   working pattern.
4. `scaffold_panel`, then read every `warnings[]`.
5. Open the harness. A panel you have not opened is a panel you have not
   written.
6. `reload_panels`, and read `diagnostics`.
