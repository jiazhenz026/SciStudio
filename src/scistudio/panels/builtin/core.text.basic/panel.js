/* core.text.basic — bounded, paged text view (parity: TextViewer).
 * Reads text.chunk; shows encoding + language, a truncation notice with the
 * total byte size, and a "Load more" that pages forward via next_offset. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");
  var buffer = "";
  var current = null;

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

  function render() {
    root.textContent = "";
    root.appendChild(el("pre", { "data-testid": "text-content", text: buffer }));
    root.appendChild(el("div", { class: "meta", "data-testid": "text-meta", text: (current.language || "text") + " · " + (current.encoding || "utf-8") + " · " + (current.total_bytes || 0) + " bytes" }));
    if (current.truncated || (current.next_offset !== null && current.next_offset !== undefined)) {
      var loadMore = el("button", { text: "Load more", "data-testid": "text-load-more", onclick: function () { loadMore.setAttribute("disabled", ""); page(current.next_offset || 0); } });
      root.appendChild(el("div", { class: "trunc", "data-testid": "text-truncation" }, [
        el("span", { text: "Bounded preview of " + (current.total_bytes || 0) + " bytes — open in the editor for the full content." }),
        current.next_offset !== null && current.next_offset !== undefined ? loadMore : null,
      ]));
    }
  }

  function page(offset) {
    return api.read("text.chunk", { offset: offset }).then(function (chunk) {
      current = chunk;
      buffer += chunk.text || chunk.content || "";
      render();
    }).catch(function (err) {
      root.textContent = "";
      root.appendChild(el("div", { class: "err", role: "alert", text: "Could not read text: " + (err && err.message || err) }));
      api.reportError(String(err && err.message || err));
    });
  }

  api.ready().then(function () { page(0); }).catch(function (err) { api.reportError(String(err && err.message || err)); });

  window.__panel = { render: render };
})();
