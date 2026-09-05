"""What ``scaffold_panel`` writes: the declaration, the document, the harness.

ADR-054 spec 5 FR-014 and FR-015. Three files into one directory in one tier:

* ``panel.json`` — the declaration, produced by
  :meth:`scistudio.core.panels.PanelManifest.to_declaration_dict` so the file
  the scaffold writes is the file
  :func:`scistudio.core.panels.read_panel_declaration` reads back.
* ``index.html`` — a *working* skeleton. It completes the handshake, renders the
  envelope it is given, and — when the panel is producing — carries a control
  that emits a statement the explore session's admission whitelist accepts. It
  is a panel that does something on the first open, not a placeholder that
  raises ``NotImplementedError`` in HTML.
* ``harness.html`` — the page the agent opens. It loads ``index.html``, stands in
  for the host, feeds the panel the stub data of
  :mod:`scistudio.ai.agent.mcp.tools_panels._stubs`, and shows every message in
  both directions with the emissions called out.

**Both documents embed the same generated contract block.** The ``var``
declarations come from
:func:`scistudio.ai.agent.mcp.tools_panels._contract.contract_javascript`, and
the harness's router is driven by them rather than by a switch statement it
maintains itself, so the harness cannot quietly fall behind the contract.

**Why the harness is a sibling file rather than a served page.** It has to open
from a ``file://`` URL with nothing running (the agent may be scaffolding before
the GUI is up), which means no build step, no imports and no network. It is also
served, unchanged, by the merged panel asset route once the panel is registered,
because ``.html`` is in that route's one suffix allowlist — which is why
:func:`scaffold_panel_files` can report both a path and a URL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.ai.agent.mcp.tools_panels._contract import contract_javascript
from scistudio.ai.agent.mcp.tools_panels._stubs import stub_envelopes
from scistudio.core.panels import (
    DEFAULT_PANEL_ENTRY,
    PANEL_API_VERSION,
    PANEL_DECLARATION_FILENAME,
    PanelCapability,
    PanelManifest,
)
from scistudio.panels.assets import is_safe_panel_id
from scistudio.panels.descriptor import panel_asset_base_url, read_limits_payload

__all__ = [
    "HARNESS_FILENAME",
    "ScaffoldedPanel",
    "harness_document",
    "panel_document",
    "scaffold_panel_files",
]

#: The harness's filename inside the panel directory. Fixed rather than
#: configurable: the agent is told "open the harness", and a name that varied per
#: panel would make that instruction a lookup.
HARNESS_FILENAME = "harness.html"


@dataclass(frozen=True)
class ScaffoldedPanel:
    """The three files one scaffold wrote, and where they went."""

    directory: Path
    declaration_path: Path
    document_path: Path
    harness_path: Path
    manifest: PanelManifest
    tier: str
    harness_url_path: str
    """The harness's path under the merged panel asset route, once the panel is
    registered. Joined to the running GUI's base URL by the tool."""


# ---------------------------------------------------------------------------
# The panel document
# ---------------------------------------------------------------------------

_DOCUMENT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__DISPLAY_NAME__ &mdash; SciStudio panel</title>
<!--
  Scaffolded by the SciStudio `scaffold_panel` tool (ADR-054 spec 5 FR-014).

  A panel is ONE self-contained document: markup, styles and script in this
  file. No <script src>, no <link rel=stylesheet>, no bundler, no CDN. It is
  mounted in a frame granted `allow-scripts` and nothing else, so it runs at an
  opaque origin and talks to the host only by postMessage.

  Open `harness.html` beside this file to see it render over stub data.

  Read `panel-contract.md` in the agent reference before changing the
  handshake; the contract block below is generated and should be left alone.
-->
<style>
  :root {
    --ink: #1c211b;
    --ember: #f06a44;
    --line: rgba(28, 33, 27, 0.12);
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    background: transparent;
    color: var(--ink);
    font: 12px/1.45 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  body { padding: 8px; }
  .stack { display: flex; flex-direction: column; gap: 8px; }
  .card {
    border: 1px solid var(--line);
    border-radius: 12px;
    background: #fff;
    padding: 12px;
  }
  h1 { margin: 0 0 4px; font-size: 13px; }
  .muted { color: rgba(28, 33, 27, 0.6); }
  table { border-collapse: collapse; width: 100%; font-size: 11px; }
  th, td { border-bottom: 1px solid var(--line); padding: 3px 6px; text-align: left; }
  pre {
    margin: 0;
    max-height: 220px;
    overflow: auto;
    font: 11px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  label { font-size: 11px; }
  button {
    font: inherit;
    border: 1px solid var(--ember);
    background: var(--ember);
    color: #fff;
    border-radius: 8px;
    padding: 4px 12px;
    cursor: pointer;
  }
  .error {
    border: 1px solid rgba(179, 38, 30, 0.3);
    background: rgba(179, 38, 30, 0.08);
    color: #b3261e;
    border-radius: 12px;
    padding: 12px;
  }
</style>
</head>
<body>
<div class="stack" id="root">
  <p class="muted">Waiting for the host&hellip;</p>
</div>

<script>
(function () {
  "use strict";

  /* ---------------------------------------------------------------------- */
  /* GENERATED contract block. Regenerated by `scaffold_panel`; every panel   */
  /* document carries its own copy because a panel is self-contained.        */
  /* ---------------------------------------------------------------------- */

__CONTRACT_BLOCK__

  var PANEL_ID = __PANEL_ID_JSON__;
  var CAPABILITY = __CAPABILITY_JSON__;
  var EMIT_TARGET = __EMIT_TARGET_JSON__;

  var token = null;
  var context = null;
  var envelope = null;
  var torndown = false;
  var requestSeq = 0;
  var pending = Object.create(null);

  function post(type, payload) {
    if (token === null || torndown) return false;
    if (PANEL_TO_HOST_TYPES.indexOf(type) === -1) return false;
    try {
      window.parent.postMessage(
        { scistudio_panel: PANEL_MESSAGE_MARKER, token: token, type: type, payload: payload },
        "*"
      );
      return true;
    } catch (err) {
      return false;
    }
  }

  function reportError(message, detail) {
    post("error", { message: String(message), detail: detail || null });
  }

  /* One bounded request/response round trip. Every request type carries a
     request_id and is answered by exactly one result type. */
  function request(type, body) {
    return new Promise(function (resolve, reject) {
      requestSeq += 1;
      var id = "r" + requestSeq;
      pending[id] = { resolve: resolve, reject: reject };
      var payload = { request_id: id };
      Object.keys(body).forEach(function (key) { payload[key] = body[key]; });
      if (!post(type, payload)) {
        delete pending[id];
        reject(new Error("the host could not be reached"));
      }
    });
  }

  function settle(id, value) {
    var waiting = pending[id];
    if (!waiting) return false;
    delete pending[id];
    waiting.resolve(value);
    return true;
  }

  function failRequest(id, message) {
    var waiting = pending[id];
    if (!waiting) return false;
    delete pending[id];
    waiting.reject(new Error(message));
    return true;
  }

  function envelopeOf(value) {
    var empty = { kind: "", payload: {}, metadata: {}, diagnostics: [], error: null };
    if (!value || typeof value !== "object") return empty;
    return {
      kind: typeof value.kind === "string" ? value.kind : "",
      payload: value.payload && typeof value.payload === "object" ? value.payload : {},
      metadata: value.metadata && typeof value.metadata === "object" ? value.metadata : {},
      diagnostics: Array.isArray(value.diagnostics) ? value.diagnostics : [],
      error: value.error && typeof value.error === "object" ? value.error : null
    };
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  /* -------------------------------------------------------------------- */
  /* TODO: replace this renderer with the one your panel needs. It renders  */
  /* whatever the envelope carries so the skeleton is useful on first open. */
  /* -------------------------------------------------------------------- */

  function renderPayload(container, payload) {
    if (Array.isArray(payload.rows) && Array.isArray(payload.columns)) {
      var table = document.createElement("table");
      var head = document.createElement("tr");
      payload.columns.forEach(function (name) { head.appendChild(el("th", null, name)); });
      table.appendChild(head);
      payload.rows.slice(0, 20).forEach(function (row) {
        var tr = document.createElement("tr");
        (row || []).forEach(function (cell) { tr.appendChild(el("td", null, cell)); });
        table.appendChild(tr);
      });
      container.appendChild(table);
      return;
    }
    var pre = document.createElement("pre");
    pre.textContent = JSON.stringify(payload, null, 2);
    container.appendChild(pre);
  }

  function render() {
    var root = document.getElementById("root");
    root.textContent = "";
    var current = envelope || envelopeOf(null);

    if (current.error) {
      var box = el("div", "error");
      box.setAttribute("role", "alert");
      box.appendChild(el("p", null, current.error.message || "The preview failed."));
      root.appendChild(box);
      return;
    }

    var card = el("div", "card");
    card.appendChild(el("h1", null, __DISPLAY_NAME_JSON__));
    card.appendChild(el("p", "muted", "kind: " + (current.kind || "unknown")));
    renderPayload(card, current.payload);
    root.appendChild(card);

    current.diagnostics.forEach(function (line) {
      root.appendChild(el("p", "muted", line));
    });

    if (CAPABILITY === "producing") {
      root.appendChild(producingControls());
    }
  }

  /* -------------------------------------------------------------------- */
  /* The outbound path. A producing panel's ONLY outbound path is `emit`,   */
  /* and where the panel is mounted settles what the emission means.        */
  /*                                                                        */
  /* In an explore session it is appended as a cell, and every statement    */
  /* must be an assignment to plain names, an import, or a                  */
  /* `scistudio.output` call: `df = df.drop(...)` is admitted,              */
  /* `df.iloc[0] = 1` is refused. At an interactive block's pause it is run  */
  /* in a namespace holding only `scistudio.output`, and exactly one call   */
  /* to it carries the decision. Emitting both statements works in both.    */
  /* -------------------------------------------------------------------- */

  function producingControls() {
    var box = el("div", "card");
    box.appendChild(
      el("p", "muted", "Emits: " + EMIT_TARGET + " = {...} then scistudio.output(" + EMIT_TARGET + "=" + EMIT_TARGET + ")")
    );

    var controls = el("div", "controls");
    var startLabel = el("label", null, "start ");
    var start = document.createElement("input");
    start.type = "number";
    start.id = "panel-start";
    start.value = "400";
    start.step = "1";
    startLabel.appendChild(start);

    var endLabel = el("label", null, "end ");
    var end = document.createElement("input");
    end.type = "number";
    end.id = "panel-end";
    end.value = "430";
    end.step = "1";
    endLabel.appendChild(end);

    var emit = el("button", null, "Emit selection");
    emit.type = "button";
    emit.id = "panel-emit";
    emit.addEventListener("click", function () {
      var value = { start: Number(start.value), end: Number(end.value) };
      // Two statements, and both contexts accept them. In a session the
      // assignment rebinds a plain name, which is what keeps the notebook's
      // source a description of what the kernel holds; at an interactive
      // block's pause the single scistudio.output() call IS the decision.
      var code =
        EMIT_TARGET + " = " + JSON.stringify(value) + "\\n" +
        "scistudio.output(" + EMIT_TARGET + "=" + EMIT_TARGET + ")";
      if (!post("emit", { code: code })) {
        reportError("the emission could not be sent", { code: code });
      }
    });

    controls.appendChild(startLabel);
    controls.appendChild(endLabel);
    controls.appendChild(emit);
    box.appendChild(controls);
    return box;
  }

  /* -------------------------------------------------------------------- */
  /* The handshake                                                         */
  /* -------------------------------------------------------------------- */

  function onMessage(event) {
    var data = event.data;
    if (!data || typeof data !== "object") return;
    if (data.scistudio_panel !== PANEL_MESSAGE_MARKER) return;
    if (typeof data.type !== "string") return;
    if (HOST_TO_PANEL_TYPES.indexOf(data.type) === -1) return;
    var payload = data.payload && typeof data.payload === "object" ? data.payload : {};

    if (token === null) {
      if (data.type !== "init" || typeof data.token !== "string" || data.token === "") return;
      token = data.token;
      context = payload;
      envelope = envelopeOf(payload.target);
      post("ready", { api_version: PANEL_API_VERSION });
      render();
      return;
    }

    if (data.token !== token) return;

    switch (data.type) {
      case "update":
        if (payload.changed && typeof payload.changed === "object" && "target" in payload.changed) {
          envelope = envelopeOf(payload.changed.target);
          render();
        }
        break;
      case "read_result":
        settle(payload.request_id, payload.window);
        break;
      case "resource_result":
        settle(payload.request_id, payload.resource);
        break;
      case "host_action_result":
        if (payload.ok === false) {
          failRequest(payload.request_id, "the host declined the action");
        } else {
          settle(payload.request_id, payload.detail);
        }
        break;
      case "error": {
        var id = payload.request_id;
        if (typeof id === "string" && failRequest(id, payload.message || "the request failed")) break;
        envelope = {
          kind: envelope ? envelope.kind : "",
          payload: envelope ? envelope.payload : {},
          metadata: envelope ? envelope.metadata : {},
          diagnostics: envelope ? envelope.diagnostics : [],
          error: { code: payload.code || "host_error", message: payload.message || "" }
        };
        render();
        break;
      }
      case "state_request":
        // Optional. Return a serialisable snapshot to survive a remount.
        post("state", { state: null });
        break;
      case "teardown":
        torndown = true;
        window.removeEventListener("message", onMessage);
        break;
      default:
        break;
    }
  }

  // `request` is here for the three request types the skeleton does not yet
  // send: request("read", { query: { page: 2 } }) asks the host for another
  // window, request("resource", { resource_id: id, params: null }) follows a
  // child, and request("host_action", { action: "export", params: null }) asks
  // for chrome this frame cannot perform for itself. Each resolves when its
  // matching `*_result` arrives.
  void request;

  window.addEventListener("message", onMessage);
})();
</script>
</body>
</html>
"""


def panel_document(manifest: PanelManifest, *, emit_target: str = "selection") -> str:
    """Return the scaffolded ``index.html`` for *manifest*.

    Args:
        manifest: The declaration the document is written against.
        emit_target: The plain name a producing skeleton rebinds when its emit
            control is used. Named rather than hard-coded because the whole
            point of the whitelist is that a panel rebinds a *name*.

    Returns:
        One self-contained HTML document.
    """
    display_name = manifest.display_name or manifest.panel_id
    return (
        _DOCUMENT_TEMPLATE.replace("__CONTRACT_BLOCK__", contract_javascript())
        .replace("__PANEL_ID_JSON__", json.dumps(manifest.panel_id))
        .replace("__CAPABILITY_JSON__", json.dumps(manifest.capability.value))
        .replace("__EMIT_TARGET_JSON__", json.dumps(emit_target))
        .replace("__DISPLAY_NAME_JSON__", json.dumps(display_name))
        .replace("__DISPLAY_NAME__", display_name)
    )


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------

_HARNESS_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Harness &mdash; __DISPLAY_NAME__</title>
<!--
  Scaffolded by the SciStudio `scaffold_panel` tool (ADR-054 spec 5 FR-015).

  This page stands in for the host so you can open your panel and look at it
  before anything is registered. Open it directly in a browser:

      file://<this directory>/harness.html

  It loads `index.html` in a sandboxed frame, sends `init` with stub data for
  each declared target type, answers every request the panel makes, and prints
  both directions of the conversation. An emission is called out at the top,
  because that is the thing you came to check.

  It is NOT the host. It answers a read with the same stub window every time and
  it grants whatever capability the declaration claims. When the panel works
  here and not in the application, the difference is data, not contract.

  The contract block below is generated from the same module the scaffold
  generates the panel document from; edit the module, re-scaffold, do not
  hand-patch it here.
-->
<style>
  :root { --ink: #1c211b; --line: rgba(28,33,27,0.14); --ember: #f06a44; }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: #f7f6f3;
    color: var(--ink);
    font: 12px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  header { padding: 12px 16px; border-bottom: 1px solid var(--line); background: #fff; }
  header h1 { margin: 0 0 2px; font-size: 14px; }
  header p { margin: 0; color: rgba(28,33,27,0.6); }
  main { display: grid; grid-template-columns: minmax(320px, 1fr) minmax(320px, 1fr); gap: 16px; padding: 16px; }
  section { background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 12px; }
  section h2 { margin: 0 0 8px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }
  iframe { width: 100%; height: 420px; border: 1px dashed var(--line); border-radius: 8px; background: #fff; }
  .controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
  button, select {
    font: inherit; border: 1px solid var(--line); background: #fff; color: inherit;
    border-radius: 8px; padding: 3px 10px; cursor: pointer;
  }
  #emissions:empty::after { content: "No emission yet."; color: rgba(28,33,27,0.5); }
  .emission {
    border: 1px solid var(--ember); border-left-width: 4px; border-radius: 8px;
    padding: 8px 10px; margin-bottom: 8px; background: #fff7f4;
    font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    white-space: pre-wrap; word-break: break-word;
  }
  ol { margin: 0; padding-left: 18px; max-height: 320px; overflow: auto; }
  li { margin-bottom: 4px; }
  code { font: 11px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .dir-out { color: #0f766e; }
  .dir-in { color: #7c3aed; }
  .bad { color: #b3261e; }
</style>
</head>
<body>
<header>
  <h1>__DISPLAY_NAME__ &mdash; panel harness</h1>
  <p><code>__PANEL_ID__</code> &middot; capability <code>__CAPABILITY__</code> &middot;
     API version <code>__API_VERSION__</code></p>
</header>
<main>
  <section>
    <h2>Panel</h2>
    <div class="controls">
      <label>target type
        <select id="harness-type"></select>
      </label>
      <button type="button" id="harness-reinit">Re-init</button>
      <button type="button" id="harness-state">Ask for state</button>
      <button type="button" id="harness-teardown">Teardown</button>
    </div>
    <iframe id="harness-frame" title="panel under test" sandbox="allow-scripts" src="__ENTRY__"></iframe>
  </section>
  <section>
    <h2>Emissions</h2>
    <div id="emissions"></div>
    <h2 style="margin-top:16px">Conversation</h2>
    <ol id="transcript"></ol>
  </section>
</main>

<script>
(function () {
  "use strict";

  /* ---------------------------------------------------------------------- */
  /* GENERATED contract block — the same one the panel document carries.     */
  /* The router below is driven by these names, so a contract that gains a   */
  /* message type gains it here too the next time the panel is scaffolded.   */
  /* ---------------------------------------------------------------------- */

__CONTRACT_BLOCK__

  var PANEL_ID = __PANEL_ID_JSON__;
  var CAPABILITY = __CAPABILITY_JSON__;
  var ASSET_BASE_URL = __ASSET_BASE_URL_JSON__;
  var READ_LIMITS = __READ_LIMITS_JSON__;
  var STUBS = __STUBS_JSON__;
  var BINDINGS = __BINDINGS_JSON__;
  var TOKEN = "harness-" + Math.random().toString(36).slice(2, 10);

  var frame = document.getElementById("harness-frame");
  var typeSelect = document.getElementById("harness-type");
  var emissionsBox = document.getElementById("emissions");
  var transcript = document.getElementById("transcript");
  var typeNames = Object.keys(STUBS);
  var currentType = typeNames[0];

  /* What the test (and your own browser tooling) reads. Everything the harness
     saw, in order, plus the emissions on their own because that is the
     assertion worth making. */
  var record = {
    panel_id: PANEL_ID,
    token: TOKEN,
    ready: false,
    ready_api_version: null,
    emissions: [],
    messages: [],
    errors: []
  };
  window.__scistudio_panel_harness__ = record;

  function stamp(direction, type, payload) {
    record.messages.push({ direction: direction, type: type, payload: payload });
    var item = document.createElement("li");
    var tag = document.createElement("code");
    tag.className = direction === "out" ? "dir-out" : "dir-in";
    tag.textContent = (direction === "out" ? "host -> panel  " : "panel -> host  ") + type;
    item.appendChild(tag);
    var body = document.createElement("div");
    var text = JSON.stringify(payload);
    body.textContent = text.length > 240 ? text.slice(0, 240) + "\\u2026" : text;
    item.appendChild(body);
    transcript.appendChild(item);
    transcript.scrollTop = transcript.scrollHeight;
  }

  function send(type, payload) {
    if (HOST_TO_PANEL_TYPES.indexOf(type) === -1) {
      record.errors.push("the harness tried to send an unknown type: " + type);
      return;
    }
    var target = frame.contentWindow;
    if (!target) return;
    target.postMessage(
      { scistudio_panel: PANEL_MESSAGE_MARKER, token: TOKEN, type: type, payload: payload },
      "*"
    );
    stamp("out", type, payload);
  }

  function initPayload() {
    return {
      api_version: PANEL_API_VERSION,
      panel_id: PANEL_ID,
      capability: CAPABILITY,
      target: STUBS[currentType],
      bindings: CAPABILITY === "producing" ? BINDINGS : null,
      read_limits: READ_LIMITS,
      asset_base_url: ASSET_BASE_URL,
      restored_state: null
    };
  }

  /* The host's answer to one request. The reply type is looked up rather than
     branched on, so a request type added to the contract is answered here
     without this function being rewritten. */
  function answer(type, payload) {
    var resultType = PANEL_REQUEST_RESULT_TYPES[type];
    if (!resultType) return false;
    var requestId = payload && typeof payload.request_id === "string" ? payload.request_id : null;
    if (requestId === null) {
      send("error", { code: "bad_request", message: "the request carried no request_id", request_id: null });
      return true;
    }
    if (resultType === "read_result") {
      send("read_result", { request_id: requestId, window: STUBS[currentType] });
    } else if (resultType === "resource_result") {
      send("resource_result", { request_id: requestId, resource: { stub: true, resource_id: payload.resource_id } });
    } else {
      var known = PANEL_HOST_ACTIONS.indexOf(payload.action) !== -1;
      send("host_action_result", {
        request_id: requestId,
        ok: known,
        detail: known ? { status: "stubbed", action: payload.action } : "the harness does not service that action"
      });
    }
    return true;
  }

  function showEmission(code) {
    record.emissions.push(code);
    var box = document.createElement("div");
    box.className = "emission";
    box.textContent = code;
    emissionsBox.appendChild(box);
  }

  window.addEventListener("message", function (event) {
    var data = event.data;
    if (!data || typeof data !== "object") return;
    if (data.scistudio_panel !== PANEL_MESSAGE_MARKER) return;
    if (data.token !== TOKEN) return;
    if (typeof data.type !== "string") return;
    if (event.source !== frame.contentWindow) return;
    var payload = data.payload && typeof data.payload === "object" ? data.payload : {};

    if (PANEL_TO_HOST_TYPES.indexOf(data.type) === -1) {
      record.errors.push("the panel sent a type the contract does not carry: " + data.type);
      stamp("in", data.type + " (unknown)", payload);
      return;
    }
    stamp("in", data.type, payload);

    if (data.type === "ready") {
      record.ready = true;
      record.ready_api_version = payload.api_version || null;
      return;
    }
    if (data.type === "emit") {
      if (CAPABILITY !== "producing") {
        record.errors.push("a displaying panel emitted code; the host would refuse it");
      }
      showEmission(String(payload.code));
      return;
    }
    if (data.type === "error") {
      record.errors.push(String(payload.message));
      return;
    }
    answer(data.type, payload);
  });

  typeNames.forEach(function (name) {
    var option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    typeSelect.appendChild(option);
  });
  typeSelect.value = currentType;
  typeSelect.addEventListener("change", function () {
    currentType = typeSelect.value;
    send("update", { reason: "harness_type_change", changed: { target: STUBS[currentType] } });
  });

  document.getElementById("harness-reinit").addEventListener("click", function () {
    frame.src = frame.src;
  });
  document.getElementById("harness-state").addEventListener("click", function () {
    send("state_request", {});
  });
  document.getElementById("harness-teardown").addEventListener("click", function () {
    send("teardown", {});
  });

  frame.addEventListener("load", function () {
    record.ready = false;
    send("init", initPayload());
  });
})();
</script>
</body>
</html>
"""


def harness_document(manifest: PanelManifest, *, emit_target: str = "selection") -> str:
    """Return the standalone ``harness.html`` for *manifest* (FR-015).

    Args:
        manifest: The declaration the harness reads its target types, capability
            and entry document from.
        emit_target: The plain name the producing skeleton rebinds. The harness
            offers it as the one binding, so ``init.bindings`` names something
            the emitted statement actually refers to.

    Returns:
        One self-contained HTML document that opens from a ``file://`` URL.
    """
    display_name = manifest.display_name or manifest.panel_id
    stubs = stub_envelopes(manifest.target_types, panel_id=manifest.panel_id)
    bindings: dict[str, Any] = {
        emit_target: {"type": (manifest.target_types[0] if manifest.target_types else "DataObject"), "snapshot": None}
    }
    return (
        _HARNESS_TEMPLATE.replace("__CONTRACT_BLOCK__", contract_javascript())
        .replace("__PANEL_ID_JSON__", json.dumps(manifest.panel_id))
        .replace("__CAPABILITY_JSON__", json.dumps(manifest.capability.value))
        .replace("__ASSET_BASE_URL_JSON__", json.dumps(panel_asset_base_url(manifest.panel_id)))
        .replace("__READ_LIMITS_JSON__", json.dumps(read_limits_payload()))
        .replace("__STUBS_JSON__", json.dumps(stubs))
        .replace("__BINDINGS_JSON__", json.dumps(bindings))
        .replace("__ENTRY__", manifest.entry)
        .replace("__PANEL_ID__", manifest.panel_id)
        .replace("__CAPABILITY__", manifest.capability.value)
        .replace("__API_VERSION__", manifest.api_version)
        .replace("__DISPLAY_NAME__", display_name)
    )


# ---------------------------------------------------------------------------
# Writing the three files
# ---------------------------------------------------------------------------


def scaffold_panel_files(
    root: Path,
    *,
    panel_id: str,
    display_name: str,
    target_types: tuple[str, ...],
    capability: PanelCapability,
    tier: str,
    emit_target: str = "selection",
    overwrite: bool = False,
) -> ScaffoldedPanel:
    """Write the declaration, the document and the harness under *root*.

    Args:
        root: The tier's ``panels/`` root. Created when it does not exist.
        panel_id: The panel's stable id; also its directory name.
        display_name: The name a person sees in the panel palette.
        target_types: The recorded type names the panel claims.
        capability: What the panel may do.
        tier: The tier name, recorded on the result for the caller's report.
        emit_target: The plain name a producing skeleton rebinds.
        overwrite: Whether to replace an existing directory's three files.

    Returns:
        The :class:`ScaffoldedPanel` describing what was written.

    Raises:
        ValueError: The panel id is not usable as one path segment.
        FileExistsError: The directory already holds a declaration and
            *overwrite* is false. Refusing is the right default: a panel
            directory is a person's source, and a scaffold that silently
            replaced it would be the one tool in the set that destroys work.
    """
    if not is_safe_panel_id(panel_id):
        raise ValueError(
            f"panel id {panel_id!r} cannot be used as a directory name: it must be a single path segment "
            f"with no separator, drive letter, or '..'"
        )

    directory = root / panel_id
    declaration_path = directory / PANEL_DECLARATION_FILENAME
    if declaration_path.exists() and not overwrite:
        raise FileExistsError(
            f"a panel already exists at {directory}. Read it with read_panel_source, or pass overwrite=true "
            f"to replace its declaration, document and harness."
        )

    manifest = PanelManifest(
        panel_id=panel_id,
        display_name=display_name or panel_id,
        target_types=tuple(target_types),
        capability=capability,
        entry=DEFAULT_PANEL_ENTRY,
        api_version=PANEL_API_VERSION,
    )

    directory.mkdir(parents=True, exist_ok=True)
    document_path = directory / manifest.entry
    harness_path = directory / HARNESS_FILENAME

    declaration_path.write_text(
        json.dumps(manifest.to_declaration_dict(), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    document_path.write_text(panel_document(manifest, emit_target=emit_target), encoding="utf-8", newline="\n")
    harness_path.write_text(harness_document(manifest, emit_target=emit_target), encoding="utf-8", newline="\n")

    return ScaffoldedPanel(
        directory=directory,
        declaration_path=declaration_path,
        document_path=document_path,
        harness_path=harness_path,
        manifest=manifest,
        tier=tier,
        harness_url_path=f"{panel_asset_base_url(panel_id)}{HARNESS_FILENAME}",
    )
