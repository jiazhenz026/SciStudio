---
name: scistudio-write-panel
description: Create or improve a SciStudio HTML preview panel or an interactive workflow decision panel. Use scistudio-write-miniapp for a standalone data app, scistudio-write-plot for a static figure, and scistudio-write-block for the associated workflow computation.
---

# Write a Panel

A panel is an HTML page inside SciStudio's sandboxed iframe. Its context
controls what data and operations it receives. Choose the context from the
user's intended outcome before writing frontend code.

| User needs | Route and runtime contract |
|---|---|
| A reusable view of a data type in previews | **Preview panel**: a bound data reference, bounded SDK reads, and optional child navigation. |
| A decision during a workflow run | **Interactive panel**: the block's prepared JSON view, followed by one JSON decision. Pair with `scistudio-write-block`. |
| A standalone app with repeated computation and exploration | Use **`scistudio-write-miniapp`**: its own tab, data reads, and optional resident Python. |
| A static figure or workflow computation | Use `scistudio-write-plot` or `scistudio-write-block`; those tasks do not automatically need GUI checks. |

For an existing panel, preserve its identity and reuse working code. For a new
interactive decision, first check whether the built-in data router or pair
editor already fits; see `.scistudio/agent-reference/block-contract.md`.

## Build from the real task

1. Identify the source, registered type, and intended view or decision. Inspect
   actual shape, axes, units, and relevant metadata. For an interactive panel,
   agree with the block's `prepare_prompt` payload and `interactive_response`
   decision schema before connecting the controls.
2. Make the first view useful. Preserve the data's meaningful dimensions,
   orientation, and aspect ratio. Show images spatially and label any reduction,
   sampling, or transform. Give the data view most of the space, put controls
   beside their effects, and use theme colors with labels or legends.
3. Create the files below, use real SDK data, and wire controls to visible
   effects. Include loading, empty, and error states. Keep reads bounded; page
   or slice large inputs. Ignore stale responses when controls change quickly.
4. Validate the descriptor, then inspect the live view and try its main
   interaction using [Check the result](#check-the-result). Fix observed
   failures before handing the result back to the user.

Ask only for missing information that changes the purpose or scientific
interpretation. Choose reasonable UI defaults for routine implementation details.

## Files and discovery

Write `<project>/panels/<panel_id>/panel.json` and `index.html`; local JS/CSS
may accompany them. `panel_id` must equal the folder name and use lowercase
letters, digits, underscores, and dot-separated segments starting with a letter
(for example `myproj.text_view`). `core.*` is reserved.

Set `api_version` to `"1.0"`, an explicit nonempty `contexts` list, and a useful
`name` and `description`. `entry` defaults to `index.html` and must point to an
existing HTML file inside this folder. Preview panels need nonempty `types`
containing registered names, such as `Text` or `Collection[Text]`. Do not claim
core-only catch-all types `DataObject`, `Collection`, or `PlotArtifact`.
Interactive panels do not require `types`: their input is the prepared view.

Project panels are discovered from this folder. In **All Previewers**, inspect
which panel won routing and explicitly select yours when checking it; do not
assume an unchanged existing preview has loaded the new page. A block selects
its interactive panel by `PanelManifest(panel_id="myproj.pick")`, without a
legacy `module_url`. Reopen the view after an edit to check the loaded version.

## SDK and UI

Load `../../sdk/1/panel.css` and `../../sdk/1/scistudio-panel.js` from the default
entry page. Await `window.scistudio.ready()` promptly, before using the SDK.
Use the relative asset paths from the served panel; do not hardcode a port,
server root, mount token, or deployment prefix.

| Surface after `ready()` | Availability and use |
|---|---|
| `context`, `input` | Preview: a bound reference and type. Interactive: the JSON payload from `prepare_prompt`. |
| `read(op, params)` | Preview only here. Read metadata or bounded data using `text.chunk`, `table.page`, `table.xy`, `array.plane`, `array.tile`, `series.points`, `collection.items`, `composite.slots`, `artifact.info`, or `artifact.file`. Honor paging/truncation metadata. |
| `open(ref)` | Preview only. Open a returned collection/composite child through the host router; only authorized child references are accepted. |
| `writeBack(decision)` | Interactive only. Submit one plain-JSON decision; the block receives it as `config["interactive_response"]`. Validate before submitting and prevent duplicate confirmation. |
| `cancel()` | Interactive only. Withdraw without a decision. The host already supplies Cancel and the SDK forwards Escape. |
| `save({name, mime, data})` | Export through the host save service. |
| `viewState`, `setViewState(state)` | Restore/store JSON view preferences; not workflow outputs or persisted scientific results. |
| `onTheme(callback)`, `onDispose(callback)`, `reportError(message)` | Adapt theme, release subscriptions/resources, and report failures. Also show actionable errors in the page. |

`read` and `call` are absent from interactive contexts. Prepare a bounded JSON
view in `prepare_prompt`; compute declared outputs in the block after the
user's decision. Preview panels also have no Python `call`. Do not add a
`panel.py` expecting it to execute in either context, or open a MiniApp context
to bypass the interactive contract.

Use shared `../../sdk/1/panel-ui.js` components with the bundled Preact module
`../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js`. Available building
blocks include `Panel`, `Stack`, `Row`, `Card`, `Field`, `Input`, `Select`,
`Button`, `Table`, `Legend`, `Pager`, `LoadingState`, `EmptyState`, and
`ErrorState`. Use `Input type="range"` for a slider; there is no `Slider` export.

For data views, import `../../sdk/1/renderers.js` and load `renderers.css` beside
it. Read `.scistudio/agent-reference/miniapp-renderers.md` for the shared
renderer props. These renderers also work in preview/interactive panels:
callers supply SDK results or prepared JSON and own reads, state, and callbacks.
An `ArrayView` does not implement domain-specific masks or image channels.

Prefer bundled libraries. After `ready()`, `scistudio.libBaseUrl` locates them
in a hosted panel; the MiniApp skill lists the pinned library paths. If a CDN
is necessary, pin a version on `https://cdn.jsdelivr.net`,
`https://cdnjs.cloudflare.com`, or `https://unpkg.com`. The iframe has an opaque
origin and no direct network/data-fetch access (`connect-src 'none'`). Use SDK
reads and locally served assets; do not rely on project file access, cookies,
localStorage, parent DOM access, or arbitrary `fetch` calls.

## Example: a text preview

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

## Example: an interactive choice

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

## Check the result

- Call `validate_panel(path="panels/<panel_id>")`. Resolve descriptor, type,
  entry, and external-reference errors. This tool does not execute JavaScript
  or prove a successful render.
- For quick UI iteration, open the page as a top-level HTTP page with
  `panel.sample.json` beside it and the SDK/library paths available. The SDK
  enters sample mode when it is not in an iframe. A `file://` page may block
  fixture loading. Serve only the needed fixtures/assets for this check.
  Sample `reads` can be keyed by operation name or the exact serialized
  `{ref, op, params}` request. Sample `writeBack` resolves locally; child
  navigation and saving need a host. Sample mode does not test real reads,
  workflow resumption, or Python computation.
- Use **`scistudio-use-gui`** for a brief check on the actual running instance:
  preview the intended real data with this panel, or open the paired block's
  pending interaction. Inspect the first render and try the main control.
  Check its visible effect, loading/error state, and available logs. For an
  interactive decision, use a test run/representative input when confirmation
  would otherwise decide the user's scientific result; verify the decision
  reaches the block and produces its expected output.
- Available browser/Chrome tools or computer use can perform the interaction.
  For an image of the current workspace, local MCP may provide
  `screenshot_gui(target="workspace")`; it captures the SciStudio application view and
  does not click controls. Browser tabs use their own screenshot tooling.
- If the GUI or suitable tools are unavailable, finish the checks you can,
  and state exactly what remains unverified. Do not equate a successful open
  request or a screenshot with an interaction test. Fix observed failures and
  repeat only affected checks; do not send routine framework debugging back
  to the user or run unrelated suites.

Leave the intended view accessible where possible. Summarize the source,
implemented behavior, and checks performed, including material limitations.
