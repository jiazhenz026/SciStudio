/* core.interactive.pair_editor — reorder items within each input port so that
 * same-row items across ports pair up correctly (parity: the compiled
 * PairEditorModal, #594).
 *
 * Interactive context. The panel_payload (api.input) carries:
 *   ports:            [portName, ...]
 *   items_per_port:   { portName: [{ index, name, type }, ...] }
 *   collection_length: shared length of every input Collection
 * Confirm submits the PairEditor block's decision unchanged:
 *   writeBack({ reorder: { inputPort: [originalIndex, ...] } })
 * where each list is the port's new order expressed as original item indices,
 * matching what the compiled modal sent. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");

  var payload = (api && api.input) || {};
  var ports = Array.isArray(payload.ports) ? payload.ports : [];
  var itemsPerPort = payload.items_per_port && typeof payload.items_per_port === "object" ? payload.items_per_port : {};
  var length = typeof payload.collection_length === "number" ? payload.collection_length : 0;

  // Pastel row-pairing colours (a same row across ports shares a colour).
  var PAIR = ["#eaf1fb", "#e9f6ee", "#f2ecfb", "#fdf1e3", "#fdecef", "#e7f6f8", "#eceafb", "#f1f7e6", "#e6f5f2", "#fdefe3"];

  // orders: port -> [originalIndex, ...] giving the current order. Seeded from
  // each item's declared index (the incoming order).
  var orders = {};
  ports.forEach(function (port) {
    orders[port] = (itemsPerPort[port] || []).map(function (item) { return item.index; });
  });
  // Lookup: port -> originalIndex -> item.
  var itemLookup = {};
  ports.forEach(function (port) {
    itemLookup[port] = {};
    (itemsPerPort[port] || []).forEach(function (item) { itemLookup[port][item.index] = item; });
  });

  var submitting = false;
  var drag = { port: null, row: -1 };

  function move(port, fromRow, toRow) {
    if (fromRow === toRow || fromRow < 0 || toRow < 0) return;
    var order = orders[port];
    if (!order || fromRow >= order.length || toRow >= order.length) return;
    var moved = order.splice(fromRow, 1)[0];
    order.splice(toRow, 0, moved);
    render();
  }

  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "text") node.textContent = props[k];
      else if (k === "class") node.className = props[k];
      else if (k === "style") node.style.cssText = props[k];
      else if (k.indexOf("on") === 0 && typeof props[k] === "function") node[k.toLowerCase()] = props[k];
      else if (k === "draggable") node.draggable = !!props[k];
      else if (props[k] === true) node.setAttribute(k, "");
      else if (props[k] != null && props[k] !== false) node.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function gridStyle() {
    return "grid-template-columns: repeat(" + Math.max(ports.length, 1) + ", minmax(0, 1fr));";
  }

  function render() {
    if (!root) return;
    root.textContent = "";
    root.appendChild(el("div", { class: "head" }, [
      el("div", { class: "title", text: "Pair Editor" }),
      el("div", { class: "hint", text: "Reorder items within each port so same-row items (same colour) are paired. Drag to reorder." }),
    ]));

    // Header row: one column per port.
    var header = el("div", { class: "grid", style: gridStyle() },
      ports.map(function (port) {
        return el("div", { class: "port-name" }, [
          document.createTextNode(port + " "),
          el("span", { class: "count", text: "(" + length + ")" }),
        ]);
      }));
    root.appendChild(header);

    // One grid row per pairing index across all ports.
    for (var row = 0; row < length; row++) {
      (function (rowIdx) {
        var color = PAIR[rowIdx % PAIR.length];
        var cells = ports.map(function (port) {
          var originalIndex = orders[port][rowIdx];
          var item = originalIndex != null ? itemLookup[port][originalIndex] : null;
          if (!item) return el("div", {});
          return el("div", {
            class: "cell" + (drag.port === port && drag.row === rowIdx ? " over" : ""),
            style: "background: " + color + ";",
            "data-testid": "pair-" + port + "-row-" + rowIdx,
            draggable: true,
            ondragstart: function (e) {
              drag = { port: port, row: rowIdx };
              e.dataTransfer.effectAllowed = "move";
              e.dataTransfer.setData("text/plain", port + ":" + rowIdx);
            },
            ondragover: function (e) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; },
            ondrop: function (e) {
              e.preventDefault();
              if (drag.port === port) move(port, drag.row, rowIdx);
              drag = { port: null, row: -1 };
            },
          }, [
            el("span", { class: "rownum", text: String(rowIdx + 1) }),
            el("span", { class: "cname", title: item.name, text: item.name }),
            el("span", { class: "ctype", text: item.type }),
          ]);
        });
        root.appendChild(el("div", { class: "grid", style: gridStyle(), "data-testid": "pair-row-" + rowIdx }, cells));
      })(row);
    }

    var confirm = el("button", {
      class: "primary",
      "data-testid": "pair-confirm",
      disabled: submitting,
      onclick: submit,
      text: "Confirm",
    });
    root.appendChild(el("div", { class: "foot" }, [confirm]));
  }

  function submit() {
    if (submitting) return;
    submitting = true;
    render();
    api.writeBack({ reorder: orders }).catch(function (err) {
      submitting = false;
      render();
      api.reportError(String((err && err.message) || err));
    });
  }

  api.ready().then(render).catch(function (err) {
    if (root) { root.textContent = ""; root.appendChild(el("div", { class: "err", role: "alert", text: String((err && err.message) || err) })); }
    api.reportError(String((err && err.message) || err));
  });

  // Deterministic test surface (jsdom drag-and-drop is unreliable).
  window.__panel = {
    move: move,
    submit: submit,
    render: render,
    getOrders: function () { return orders; },
  };
})();
