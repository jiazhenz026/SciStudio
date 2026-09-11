/* core.composite.basic — slot inventory + drill-down (parity: CompositeViewer).
 * Reads composite.slots and lists each slot; clicking a slot calls open(ref) so
 * the host mounts the slot's own panel with a working Back action. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");

  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "text") node.textContent = props[k];
      else if (k === "onclick") node.onclick = props[k];
      else node.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function render(data) {
    var slots = data.slots || [];
    root.textContent = "";
    root.appendChild(el("div", { class: "summary", "data-testid": "composite-summary", text: slots.length + " slot" + (slots.length === 1 ? "" : "s") }));
    slots.forEach(function (slot) {
      var btn = el("button", {
        class: "slot", type: "button", "data-testid": "composite-slot-" + slot.name,
        onclick: function () {
          if (!api.open) return;
          btn.setAttribute("disabled", "");
          api.open(slot.ref).catch(function (err) { btn.removeAttribute("disabled"); api.reportError(String(err && err.message || err)); });
        },
      }, [
        el("span", null, [el("span", { class: "n", text: slot.name }), el("span", { class: "t", text: String(slot.type_name || "") })]),
        api.open ? el("span", { text: "Open →" }) : null,
      ]);
      root.appendChild(btn);
    });
  }

  api.ready().then(function () {
    return api.read("composite.slots", {}).then(render);
  }).catch(function (err) {
    root.textContent = "";
    root.appendChild(el("div", { class: "err", role: "alert", text: "Could not read slots: " + (err && err.message || err) }));
    api.reportError(String(err && err.message || err));
  });

  window.__panel = { render: render };
})();
