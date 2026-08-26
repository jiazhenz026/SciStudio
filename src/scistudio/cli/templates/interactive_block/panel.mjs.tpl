// The window @@BLOCK_LABEL@@ opens.
//
// One hand-written ES module: no framework, no build step, no bundler. The host
// imports this file from the block's `module_url`, calls `mount(container, host)`
// once, and tears the panel down through the `{ unmount }` handle `mount` returns.
//
// Four things below are already correct. Keep them that way — each one has a
// named failure code the panel host reports when it is broken:
//
//   1. This object is the module's **default** export. The manifest's
//      `export_name` defaults to `"default"`; exporting only a named binding
//      fails to load with `export_missing`.
//   2. `apiVersion` is a string and its major must match the host's, or the
//      panel is refused with `api_version_mismatch`.
//   3. `mount` returns `{ unmount() {...} }`. A module without a callable
//      `mount` is rejected as `not_a_panel_module`.
//   4. Confirm and cancel are BOTH on screen and both reachable.
//      `host.confirm(decision)` resumes the run with the panel's JSON answer;
//      `host.cancel()` cancels the block. A panel that renders neither leaves
//      the user staring at a paused run with no way out. Never ship one.
//
// What is left for you is the content area between the heading and the buttons:
// draw `host.panelPayload` (exactly what the block's `prepare_prompt` returned)
// and collect the decision, then return it from `readDecision()`.

const API_VERSION = "1";

/** Small DOM helper so the body below stays about the panel, not about tags. */
function el(tag, style, text) {
  const node = document.createElement(tag);
  if (style) node.style.cssText = style;
  if (text !== undefined) node.textContent = text;
  return node;
}

export default {
  apiVersion: API_VERSION,

  mount(container, host) {
    // What `prepare_prompt` built. Plain JSON — never the real data.
    const payload = host.panelPayload || {};

    const root = el(
      "div",
      "display:flex;flex-direction:column;gap:12px;padding:16px;" +
        "font-family:system-ui,sans-serif;color:#1c1917;",
    );
    root.appendChild(el("div", "font-weight:600;", "@@PANEL_HEADING@@"));

    // ---- content area ------------------------------------------------------
    // TODO(scaffold): replace this dump with the real view — a canvas, a table,
    // a list of choices — and with the controls the user decides through. Until
    // you do, the panel shows the payload so you can see what arrived.
    const content = el(
      "pre",
      "margin:0;padding:12px;border-radius:8px;background:#f5f5f4;" +
        "max-height:360px;overflow:auto;font-size:12px;white-space:pre-wrap;",
      JSON.stringify(payload, null, 2),
    );
    root.appendChild(content);

    /**
     * The JSON the block reads back.
     *
     * Whatever this returns arrives in the compute phase as
     * `config["interactive_response"]`. It must be plain JSON.
     */
    function readDecision() {
      // TODO(scaffold): return the user's actual decision.
      return { confirmed: true };
    }

    // ---- confirm / cancel --------------------------------------------------
    // Both, always. This pair is the block's only exit.
    const buttons = el("div", "display:flex;gap:8px;margin-top:4px;");
    const confirm = el(
      "button",
      "padding:6px 16px;border-radius:8px;border:1px solid #1c1917;" +
        "background:#1c1917;color:#fff;cursor:pointer;",
      "Continue",
    );
    const cancel = el(
      "button",
      "padding:6px 16px;border-radius:8px;border:1px solid #d6d3d1;" +
        "background:#fff;cursor:pointer;",
      "Cancel",
    );
    confirm.addEventListener("click", () => host.confirm(readDecision()));
    cancel.addEventListener("click", () => host.cancel());
    buttons.appendChild(confirm);
    buttons.appendChild(cancel);
    root.appendChild(buttons);

    container.appendChild(root);

    return {
      unmount() {
        root.remove();
      },
    };
  },
};
