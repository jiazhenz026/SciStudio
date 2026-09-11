/* core.collection.basic — item cards with full paging (parity: CollectionViewer).
 *
 * Faithful display (#1886 item B): the collection is paged to EVERY item via the
 * cursor path — the panel keeps requesting collection.items until next_cursor is
 * null, so a collection of more than 100 items is fully reachable and nothing is
 * silently capped. Clicking an item calls open(ref) to drill in. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");
  var items = [];
  var count = 0;
  var itemType = "items";

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
  function displayName(ref) {
    if (typeof ref !== "string") return "item";
    var parts = ref.split(/[\\/#]/);
    return parts[parts.length - 1] || ref;
  }

  function render() {
    root.textContent = "";
    root.appendChild(el("div", { class: "summary", "data-testid": "collection-summary", text: count + " " + itemType + " (showing " + items.length + ")" }));
    var grid = el("div", { class: "grid", "data-testid": "collection-grid" });
    items.forEach(function (item, idx) {
      var ref = item.ref || item.data_ref;
      var btn = el("button", {
        class: "item", type: "button", "data-testid": "collection-item-" + idx,
        onclick: function () { if (!api.open || !ref) return; btn.setAttribute("disabled", ""); api.open(ref).catch(function (err) { btn.removeAttribute("disabled"); api.reportError(String(err && err.message || err)); }); },
      }, [
        el("span", { class: "name", title: ref || "", text: displayName(ref) }),
        el("span", { class: "t", text: String(item.type_name || itemType) }),
      ]);
      grid.appendChild(btn);
    });
    root.appendChild(grid);
  }

  function pageAll(cursor, guard) {
    if (!cursor || guard <= 0) { render(); return Promise.resolve(); }
    return api.read("collection.items", { cursor: cursor }).then(function (page) {
      var got = page.items || [];
      items = items.concat(got);
      render();
      var next = page.next_cursor;
      // Stop when the cursor stalls, everything is loaded, or the guard runs out.
      if (!next || !got.length || items.length >= count) return;
      return pageAll(next, guard - 1);
    });
  }

  api.ready().then(function () {
    var input = api.input || {};
    items = (input.items || []).slice();
    count = typeof input.count === "number" ? input.count : items.length;
    itemType = input.item_type || "items";
    render();
    // Guard bounds the number of pages so a broken cursor can never loop forever.
    return pageAll(input.next_cursor, Math.ceil((count + 1) / 1) + 2);
  }).catch(function (err) {
    root.textContent = "";
    root.appendChild(el("div", { class: "err", role: "alert", text: "Could not read collection: " + (err && err.message || err) }));
    api.reportError(String(err && err.message || err));
  });

  window.__panel = { displayName: displayName };
})();
