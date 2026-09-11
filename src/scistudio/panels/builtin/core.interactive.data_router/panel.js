/* core.interactive.data_router — drag items from N input ports onto M output
 * ports (parity: the compiled DataRouterModal, #591).
 *
 * Interactive context. The panel_payload (api.input) carries:
 *   input_ports:    [portName, ...]
 *   items_per_port: { portName: [{ index, port, ref, name, type }, ...] }
 *   output_ports:   [portName, ...]
 * Confirm submits the DataRouter block's decision unchanged:
 *   writeBack({ assignments: { outputPort: [ref, ...] } })
 * Every declared output port is present (empty [] when nothing was routed to
 * it), matching the compiled modal so the block produces every output port. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");

  var payload = (api && api.input) || {};
  var inputPorts = Array.isArray(payload.input_ports) ? payload.input_ports : [];
  var outputPorts = Array.isArray(payload.output_ports) ? payload.output_ports : [];
  var itemsPerPort = payload.items_per_port && typeof payload.items_per_port === "object" ? payload.items_per_port : {};

  // Flatten every input item and index it by its stable ref.
  var allItems = [];
  var itemByRef = {};
  inputPorts.forEach(function (port) {
    (itemsPerPort[port] || []).forEach(function (item) {
      allItems.push(item);
      itemByRef[item.ref] = item;
    });
  });

  // assignments: output port -> [ref]. Seed every output port so the block
  // receives an (empty) Collection for a port nothing was routed to.
  var assignments = {};
  outputPorts.forEach(function (port) { assignments[port] = []; });

  var submitting = false;
  var dragOverPort = null;

  function assignedRefs() {
    var set = Object.create(null);
    Object.keys(assignments).forEach(function (port) {
      assignments[port].forEach(function (ref) { set[ref] = true; });
    });
    return set;
  }
  function unassignedItems() {
    var assigned = assignedRefs();
    return allItems.filter(function (item) { return !assigned[item.ref]; });
  }
  function assign(ref, outputPort) {
    if (!itemByRef[ref] || !Object.prototype.hasOwnProperty.call(assignments, outputPort)) return;
    unassign(ref);
    assignments[outputPort].push(ref);
    render();
  }
  function unassign(ref) {
    Object.keys(assignments).forEach(function (port) {
      assignments[port] = assignments[port].filter(function (r) { return r !== ref; });
    });
  }

  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "text") node.textContent = props[k];
      else if (k === "class") node.className = props[k];
      else if (k.indexOf("on") === 0 && typeof props[k] === "function") node[k.toLowerCase()] = props[k];
      else if (k === "draggable") node.draggable = !!props[k];
      else if (props[k] === true) node.setAttribute(k, "");
      else if (props[k] != null && props[k] !== false) node.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function chip(item) {
    return el("div", {
      class: "chip",
      "data-testid": "router-item-" + item.ref,
      draggable: true,
      ondragstart: function (e) {
        e.dataTransfer.setData("text/plain", item.ref);
        e.dataTransfer.effectAllowed = "move";
      },
    }, [
      el("span", { class: "cname", title: item.name, text: item.name }),
      el("span", { class: "ctype", text: item.type }),
    ]);
  }

  function dragOver(e) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; }

  function render() {
    if (!root) return;
    var assigned = assignedRefs();
    var unassigned = unassignedItems();
    var allAssigned = unassigned.length === 0 && allItems.length > 0;
    root.textContent = "";

    root.appendChild(el("div", { class: "head" }, [
      el("div", { class: "title", text: "Data Router" }),
      el("div", { class: "hint", text: "Drag items from input ports onto output ports. All items must be assigned." }),
    ]));

    // Left: input ports (unassigned items). Dropping here unassigns an item.
    var inputCol = el("div", {
      class: "col",
      "data-testid": "router-inputs",
      ondrop: function (e) {
        e.preventDefault();
        var ref = e.dataTransfer.getData("text/plain");
        if (ref) { unassign(ref); render(); }
      },
      ondragover: dragOver,
    }, [el("div", { class: "caption", text: "Inputs" })]);
    inputPorts.forEach(function (port) {
      var portItems = (itemsPerPort[port] || []);
      var free = portItems.filter(function (it) { return !assigned[it.ref]; });
      inputCol.appendChild(el("div", { class: "port" }, [
        el("div", { class: "port-name" }, [
          document.createTextNode(port + " "),
          el("span", { class: "count", text: "(" + free.length + "/" + portItems.length + ")" }),
        ]),
        el("div", { class: "chips" }, free.length
          ? free.map(chip)
          : [el("span", { class: "empty", text: "All items assigned" })]),
      ]));
    });

    var arrow = el("div", { class: "arrow", text: "→" });

    // Right: output ports (drop zones).
    var outputCol = el("div", { class: "col", "data-testid": "router-outputs" },
      [el("div", { class: "caption", text: "Outputs" })]);
    outputPorts.forEach(function (port) {
      var refs = assignments[port];
      outputCol.appendChild(el("div", {
        class: "port drop" + (dragOverPort === port ? " over" : ""),
        "data-testid": "router-output-" + port,
        ondragover: function (e) { dragOver(e); if (dragOverPort !== port) { dragOverPort = port; } },
        ondragleave: function () { if (dragOverPort === port) { dragOverPort = null; } },
        ondrop: function (e) {
          e.preventDefault();
          dragOverPort = null;
          var ref = e.dataTransfer.getData("text/plain");
          if (ref) assign(ref, port);
        },
      }, [
        el("div", { class: "port-name" }, [
          document.createTextNode(port + " "),
          el("span", { class: "count", text: "(" + refs.length + ")" }),
        ]),
        el("div", { class: "chips" }, refs.length
          ? refs.map(function (ref) { return itemByRef[ref] ? chip(itemByRef[ref]) : null; })
          : [el("span", { class: "empty", text: "Drop items here" })]),
      ]));
    });

    root.appendChild(el("div", { class: "body" }, [inputCol, arrow, outputCol]));

    var status = allAssigned
      ? el("span", { class: "status done", "data-testid": "router-status", text: "All items assigned" })
      : el("span", {
          class: "status todo",
          "data-testid": "router-status",
          text: unassigned.length + " item(s) not yet assigned",
        });
    var confirm = el("button", {
      class: "primary",
      "data-testid": "router-confirm",
      disabled: !allAssigned || submitting,
      onclick: submit,
      text: "Confirm",
    });
    root.appendChild(el("div", { class: "foot" }, [status, confirm]));
  }

  function submit() {
    if (submitting) return;
    submitting = true;
    render();
    api.writeBack({ assignments: assignments }).catch(function (err) {
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
    assign: assign,
    unassign: unassign,
    submit: submit,
    render: render,
    getAssignments: function () { return assignments; },
  };
})();
