/* core.dataframe.basic — paged, sortable DataFrame table (parity: DataFrameViewer).
 * Reads table.page. Per #1886 Part 1 the pager is a plain "rows A-B of N, page X/Y"
 * with NO truncated/incomplete badge: a paged table is complete by construction. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");
  var state = { page: 1, page_size: 50, sort_by: null, sort_dir: null, loading: false };

  function fmtCell(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
    return String(value);
  }
  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "text") node.textContent = props[k];
      else if (k === "onclick") node.onclick = props[k];
      else if (k === "disabled") { if (props[k]) node.setAttribute("disabled", ""); }
      else node.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function toggleSort(column) {
    if (state.sort_by !== column) { state.sort_by = column; state.sort_dir = "asc"; }
    else if (state.sort_dir === "asc") { state.sort_dir = "desc"; }
    else { state.sort_by = null; state.sort_dir = null; }
    state.page = 1;
    load();
  }
  function goTo(page, totalPages) {
    var next = Math.max(1, Math.min(page, totalPages));
    if (next === state.page) return;
    state.page = next;
    load();
  }

  function render(data) {
    var columns = data.columns || [];
    var rows = data.rows || [];
    var total = typeof data.total === "number" ? data.total : (data.total_rows || rows.length);
    var pageSize = data.page_size || state.page_size;
    var totalPages = data.total_pages || Math.max(1, Math.ceil(total / Math.max(pageSize, 1)));
    var page = data.page || state.page;
    var sort = data.sort || {};
    state.sort_by = sort.by || null;
    state.sort_dir = sort.direction || null;

    root.textContent = "";
    var thead = el("thead", null, [el("tr", null, columns.map(function (c) {
      var indicator = state.sort_by === c ? (state.sort_dir === "desc" ? " ▼" : " ▲") : "";
      return el("th", {
        title: state.sort_by === c ? "Sorted " + state.sort_dir + "; click to change" : "Click to sort",
        "aria-sort": state.sort_by === c ? (state.sort_dir === "desc" ? "descending" : "ascending") : "none",
        onclick: function () { toggleSort(c); },
        text: c + indicator,
      });
    }))]);
    var tbody = el("tbody", null, rows.map(function (row) {
      return el("tr", null, columns.map(function (c) { return el("td", { text: fmtCell(row[c]) }); }));
    }));
    var scroll = el("div", { class: "scroll" }, [el("table", { "data-testid": "dataframe-table" }, [thead, tbody])]);

    var start = total === 0 ? 0 : (page - 1) * pageSize + 1;
    var end = Math.min(total, page * pageSize);
    var summary = el("span", {
      "data-testid": "dataframe-summary",
      text: "rows " + start + "–" + end + " of " + total + " · page " + page + "/" + totalPages,
    });
    function pbtn(label, target, disabled, aria) {
      return el("button", { text: label, "aria-label": aria, disabled: disabled || state.loading, onclick: function () { goTo(target, totalPages); } });
    }
    var pager = el("div", null, [
      pbtn("«", 1, page <= 1, "First page"),
      pbtn("‹", page - 1, page <= 1, "Previous page"),
      pbtn("›", page + 1, page >= totalPages, "Next page"),
      pbtn("»", totalPages, page >= totalPages, "Last page"),
    ]);
    root.appendChild(scroll);
    root.appendChild(el("div", { class: "bar" }, [summary, pager]));
    api.setViewState({ page: page, page_size: pageSize, sort_by: state.sort_by, sort_dir: state.sort_dir });
  }

  function load() {
    state.loading = true;
    var params = { page: state.page, page_size: state.page_size };
    if (state.sort_by) { params.sort_by = state.sort_by; params.sort_dir = state.sort_dir || "asc"; }
    return api.read("table.page", params).then(function (data) {
      state.loading = false;
      render(data);
    }).catch(function (err) {
      state.loading = false;
      root.textContent = "";
      root.appendChild(el("div", { class: "err", role: "alert", text: "Could not read table: " + (err && err.message || err) }));
      api.reportError(String(err && err.message || err));
    });
  }

  api.ready().then(function () {
    var vs = api.viewState;
    if (vs && typeof vs === "object") {
      if (typeof vs.page === "number") state.page = vs.page;
      if (typeof vs.page_size === "number") state.page_size = vs.page_size;
      if (typeof vs.sort_by === "string") { state.sort_by = vs.sort_by; state.sort_dir = vs.sort_dir || "asc"; }
    }
    load();
  }).catch(function (err) { api.reportError(String(err && err.message || err)); });

  window.__panel = { fmtCell: fmtCell, render: render };
})();
