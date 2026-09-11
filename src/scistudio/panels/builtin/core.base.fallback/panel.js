/* core.base.fallback — universal fallback (parity: ErrorViewer + default branch).
 * When no type-specific panel matches, this shows the object's type chain,
 * shape/dtype where present, and its recorded metadata, and offers a download
 * through artifact.file when the object has stored bytes. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");

  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "text") node.textContent = props[k];
      else node.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function render(meta, file) {
    var chain = meta.type_chain || [];
    var kids = [
      el("div", { class: "field", "data-testid": "object-type", text: "" }),
    ];
    kids[0].appendChild(document.createTextNode("type "));
    kids[0].appendChild(el("b", { text: chain.length ? chain[chain.length - 1] : "object" }));
    if (chain.length > 1) kids.push(el("div", { class: "field", "data-testid": "object-chain", text: "chain: " + chain.join(" → ") }));
    if (meta.shape) kids.push(el("div", { class: "field", text: "shape [" + [].concat(meta.shape).join(", ") + "]" }));
    if (meta.dtype) kids.push(el("div", { class: "field", text: "dtype " + meta.dtype }));
    kids.push(el("pre", { "data-testid": "object-metadata", text: JSON.stringify(meta.metadata || {}, null, 2) }));
    if (file && file.url) kids.push(el("a", { class: "download", href: file.url, download: file.name || "object", "data-testid": "object-download", text: "Download bytes" }));
    root.textContent = "";
    root.appendChild(el("div", { class: "card", "data-testid": "object-card" }, kids));
  }

  api.ready().then(function () {
    return api.read("metadata", {}).then(function (meta) {
      // Bytes are optional for a generic object; ignore a missing artifact.
      return api.read("artifact.file", {}).then(
        function (file) { render(meta, file); },
        function () { render(meta, null); }
      );
    });
  }).catch(function (err) {
    root.textContent = "";
    root.appendChild(el("div", { class: "err", role: "alert", text: "Could not read object: " + (err && err.message || err) }));
    api.reportError(String(err && err.message || err));
  });

  window.__panel = { render: render };
})();
