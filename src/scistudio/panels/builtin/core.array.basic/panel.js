/* core.array.basic — native-resolution numeric inspection (parity: ArrayViewer).
 *
 * Faithful display (#1886 item A): the DEFAULT value surface is the array's REAL
 * cell values read at native resolution via array.tile — a numeric heatmap grid
 * of actual numbers with per-cell colour and a vmin..vmax legend. Every cell is
 * reachable by panning the tile window; N-D arrays keep one slider per extra
 * axis. array.plane's strided read is used ONLY as a small, clearly-labelled
 * navigation minimap, never as the value surface. Non-finite cells arrive as the
 * sentinel strings "NaN"/"Infinity"/"-Infinity" and render as NaN / ∞ / -∞
 * (never blank) (#1886 item E). */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");
  var state = { axis_indices: {}, y0: 0, x0: 0, tile: 64 };
  var meta = null;

  function isSentinel(v) { return v === "NaN" || v === "Infinity" || v === "-Infinity"; }
  function numeric(v) { return typeof v === "number" && isFinite(v) ? v : null; }
  function formatCell(v) {
    if (v === "NaN") return "NaN";
    if (v === "Infinity") return "∞";
    if (v === "-Infinity") return "-∞";
    if (v === null || v === undefined) return "—";
    if (typeof v !== "number" || !isFinite(v)) return String(v);
    if (v === 0) return "0";
    var abs = Math.abs(v);
    if (Number.isInteger(v) && abs < 1e6) return String(v);
    if (abs >= 1e5 || abs < 1e-3) return v.toExponential(2);
    return v.toFixed(3);
  }
  function lerp(a, b, t) { return Math.round(a + (b - a) * t); }
  function heatmapColor(v, vmin, vmax) {
    var n = numeric(v);
    if (n === null) return "transparent";
    if (typeof vmin !== "number" || typeof vmax !== "number") return "transparent";
    if (vmin < 0 && vmax > 0) {
      var mag = Math.max(Math.abs(vmin), Math.abs(vmax)) || 1;
      var t = Math.max(-1, Math.min(1, n / mag));
      if (t < 0) { var k = -t; return "rgb(" + lerp(247, 33, k) + "," + lerp(247, 102, k) + "," + lerp(247, 172, k) + ")"; }
      return "rgb(" + lerp(247, 178, t) + "," + lerp(247, 24, t) + "," + lerp(247, 43, t) + ")";
    }
    var span = (vmax - vmin) || 1;
    var s = Math.max(0, Math.min(1, (n - vmin) / span));
    return "rgb(" + lerp(247, 8, s) + "," + lerp(252, 64, s) + "," + lerp(253, 129, s) + ")";
  }
  function displayAxes(shape, axes, sliceAxes) {
    var sliced = {};
    (sliceAxes || []).forEach(function (a) { sliced[a.axis] = true; });
    var remaining = [];
    for (var i = 0; i < shape.length; i++) if (!sliced[i]) remaining.push(i);
    var y, x;
    if (axes && axes.indexOf("y") >= 0 && axes.indexOf("x") >= 0) { y = axes.indexOf("y"); x = axes.indexOf("x"); }
    else if (remaining.length >= 2) { y = remaining[remaining.length - 2]; x = remaining[remaining.length - 1]; }
    else if (remaining.length === 1) { y = remaining[0]; x = remaining[0]; }
    else { y = 0; x = 0; }
    return { y: y, x: x };
  }

  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "text") node.textContent = props[k];
      else if (k === "onclick") node.onclick = props[k];
      else if (k === "oninput") node.oninput = props[k];
      else if (k === "style") node.setAttribute("style", props[k]);
      else if (k === "disabled") { if (props[k]) node.setAttribute("disabled", ""); }
      else node.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function heatGrid(tileData) {
    var values = tileData.values || [];
    var y0 = typeof tileData.y0 === "number" ? tileData.y0 : state.y0;
    var x0 = typeof tileData.x0 === "number" ? tileData.x0 : state.x0;
    var cols = values[0] ? values[0].length : 0;
    var head = el("tr", null, [el("th", { class: "corner" })].concat(
      Array.from({ length: cols }, function (_, c) { return el("th", { text: String(x0 + c) }); })
    ));
    var body = values.map(function (row, r) {
      var cells = row.map(function (v, c) {
        var td = el("td", {
          "data-testid": "array-cell-" + (y0 + r) + "-" + (x0 + c),
          title: isSentinel(v) ? "non-finite (" + v + ")" : String(v),
          style: "background:" + heatmapColor(v, meta.vmin, meta.vmax),
          text: formatCell(v),
        });
        if (numeric(v) === null) td.className = "nonfinite";
        return td;
      });
      return el("tr", null, [el("th", { text: String(y0 + r) })].concat(cells));
    });
    return el("div", { class: "grid" }, [el("table", { class: "heat", "data-testid": "array-heatmap" }, [el("thead", null, [head]), el("tbody", null, body)])]);
  }

  function legend() {
    var vmin = meta.vmin, vmax = meta.vmax;
    if (typeof vmin !== "number" || typeof vmax !== "number") {
      return el("div", { class: "legend", "data-testid": "array-legend", text: "no finite values" });
    }
    var stops = [];
    for (var i = 0; i <= 8; i++) stops.push(heatmapColor(vmin + (vmax - vmin) * i / 8, vmin, vmax));
    var mid = vmin < 0 && vmax > 0 ? 0 : (vmin + vmax) / 2;
    return el("div", { class: "legend", "data-testid": "array-legend" }, [
      el("span", { "data-testid": "array-legend-min", text: formatCell(vmin) }),
      el("div", { class: "ramp", style: "background:linear-gradient(to right," + stops.join(",") + ")" }),
      el("span", { "data-testid": "array-legend-mid", text: formatCell(mid) }),
      el("span", { "data-testid": "array-legend-max", text: formatCell(vmax) }),
    ]);
  }

  function minimap(planeData) {
    var values = planeData.values || [];
    var rows = values.length, cols = values[0] ? values[0].length : 0;
    if (!rows || !cols) return null;
    var box = el("div", { class: "minimap" });
    var scale = Math.max(1, Math.round(120 / Math.max(rows, cols)));
    var canvas = el("canvas", { width: cols * scale, height: rows * scale, "data-testid": "array-minimap", title: "Overview — click to navigate; not the value surface" });
    var ctx = null;
    try { ctx = canvas.getContext && canvas.getContext("2d"); } catch (e) { ctx = null; }
    if (ctx) {
      for (var r = 0; r < rows; r++) for (var c = 0; c < cols; c++) {
        ctx.fillStyle = heatmapColor(values[r][c], meta.vmin, meta.vmax);
        ctx.fillRect(c * scale, r * scale, scale, scale);
      }
    }
    canvas.onclick = function (ev) {
      var rect = canvas.getBoundingClientRect();
      var fx = rect.width ? (ev.clientX - rect.left) / rect.width : 0;
      var fy = rect.height ? (ev.clientY - rect.top) / rect.height : 0;
      state.x0 = Math.max(0, Math.min(Math.round(fx * meta.planeW) - Math.floor(state.tile / 2), Math.max(0, meta.planeW - 1)));
      state.y0 = Math.max(0, Math.min(Math.round(fy * meta.planeH) - Math.floor(state.tile / 2), Math.max(0, meta.planeH - 1)));
      loadTile();
    };
    box.appendChild(canvas);
    box.appendChild(el("span", { text: "overview (navigation aid)" }));
    return box;
  }

  function controls() {
    function num(label, key, max) {
      return el("label", { text: label + " " }, [el("input", {
        type: "number", min: 0, max: Math.max(0, max), value: state[key],
        "aria-label": label,
        oninput: function (e) { var v = parseInt(e.target.value, 10); state[key] = isFinite(v) ? Math.max(0, Math.min(v, Math.max(0, max))) : 0; loadTile(); },
      })]);
    }
    var sizes = [16, 32, 64, 128, 256];
    var sel = el("select", { "aria-label": "Tile size", oninput: function (e) { state.tile = parseInt(e.target.value, 10) || 64; loadTile(); } },
      sizes.map(function (s) { var o = el("option", { value: s, text: s + "×" + s }); if (s === state.tile) o.setAttribute("selected", ""); return o; }));
    return el("div", { class: "controls" }, [
      num("Row", "y0", Math.max(0, meta.planeH - 1)),
      num("Col", "x0", Math.max(0, meta.planeW - 1)),
      el("label", { text: "Window " }, [sel]),
    ]);
  }

  function sliceSelectors(planeData) {
    var sliceAxes = planeData.slice_axes || [];
    if (!sliceAxes.length) return null;
    var box = el("div", { "data-testid": "array-slice-selectors", class: "controls" });
    sliceAxes.forEach(function (ax) {
      var value = state.axis_indices[ax.axis] != null ? state.axis_indices[ax.axis] : ax.index;
      function change(v) {
        var clamped = Math.max(0, Math.min(v, ax.size - 1));
        state.axis_indices[ax.axis] = clamped;
        state.y0 = 0; state.x0 = 0;
        loadPlane();
      }
      box.appendChild(el("label", { text: ax.name + " (" + ax.size + ") " }, [
        el("input", { type: "range", min: 0, max: ax.size - 1, value: value, "aria-label": "Slice along " + ax.name, oninput: function (e) { change(parseInt(e.target.value, 10)); } }),
        el("input", { type: "number", min: 0, max: ax.size - 1, value: value, "aria-label": "Index along " + ax.name, oninput: function (e) { change(parseInt(e.target.value, 10)); } }),
        el("span", { text: (value + 1) + "/" + ax.size }),
      ]));
    });
    return box;
  }

  function render(planeData, tileData) {
    root.textContent = "";
    var shape = meta.source_shape || [];
    var info = el("div", { class: "info", "data-testid": "array-info" }, [
      el("span", null, [el("b", { text: "Array" })]),
      el("span", { text: "shape [" + shape.join(", ") + "]" }),
      el("span", { text: "dtype " + (meta.dtype || "?") }),
      meta.axes && meta.axes.length ? el("span", { text: "axes [" + meta.axes.join(", ") + "]" }) : null,
    ]);
    root.appendChild(info);

    var ss = sliceSelectors(planeData);
    if (ss) root.appendChild(ss);

    var isScalar = shape.length === 0;
    if (isScalar) {
      var v = (tileData.values && tileData.values[0]) ? tileData.values[0][0] : "";
      root.appendChild(el("div", { class: "info", "data-testid": "array-scalar", text: formatCell(v) }));
    } else {
      root.appendChild(controls());
      var shown = "rows " + state.y0 + "–" + (state.y0 + (tileData.height || 0) - 1) + " of " + meta.planeH +
        " · cols " + state.x0 + "–" + (state.x0 + (tileData.width || 0) - 1) + " of " + meta.planeW;
      root.appendChild(el("div", { class: "note", "data-testid": "array-window-note", text: "native-resolution values — " + shown }));
      root.appendChild(heatGrid(tileData));
      root.appendChild(legend());
      var mm = minimap(planeData);
      if (mm) root.appendChild(mm);
    }
    if (tileData.truncated) {
      root.appendChild(el("div", { class: "note", text: "Window clipped to the read budget — pan to reach the rest." }));
    }
    api.setViewState({ axis_indices: state.axis_indices, y0: state.y0, x0: state.x0, tile: state.tile });
  }

  var lastPlane = null;
  function computeMeta(planeData) {
    var shape = planeData.source_shape || planeData.shape || [];
    var da = displayAxes(shape, planeData.axes || [], planeData.slice_axes || []);
    meta = {
      source_shape: shape,
      dtype: planeData.source_dtype || planeData.dtype || "?",
      axes: planeData.axes || [],
      vmin: typeof planeData.vmin === "number" ? planeData.vmin : null,
      vmax: typeof planeData.vmax === "number" ? planeData.vmax : null,
      planeH: shape.length ? (shape[da.y] || 1) : 1,
      planeW: shape.length ? (shape[da.x] || 1) : 1,
    };
  }

  function fail(err) {
    root.textContent = "";
    root.appendChild(el("div", { class: "err", role: "alert", text: "Could not read array: " + (err && err.message || err) }));
    api.reportError(String(err && err.message || err));
  }

  function loadTile() {
    return api.read("array.tile", { y0: state.y0, x0: state.x0, height: state.tile, width: state.tile, slice_index: state.axis_indices[Object.keys(state.axis_indices)[0]] || 0, axis_indices: state.axis_indices })
      .then(function (tileData) { render(lastPlane, tileData); })
      .catch(fail);
  }
  function loadPlane() {
    return api.read("array.plane", { slice_index: state.axis_indices[Object.keys(state.axis_indices)[0]] || 0, axis_indices: state.axis_indices })
      .then(function (planeData) { lastPlane = planeData; computeMeta(planeData); return loadTile(); })
      .catch(fail);
  }

  api.ready().then(function () {
    var vs = api.viewState;
    if (vs && typeof vs === "object") {
      if (vs.axis_indices && typeof vs.axis_indices === "object") state.axis_indices = vs.axis_indices;
      if (typeof vs.y0 === "number") state.y0 = vs.y0;
      if (typeof vs.x0 === "number") state.x0 = vs.x0;
      if (typeof vs.tile === "number") state.tile = vs.tile;
    }
    loadPlane();
  }).catch(function (err) { api.reportError(String(err && err.message || err)); });

  window.__panel = { formatCell: formatCell, heatmapColor: heatmapColor, numeric: numeric, isSentinel: isSentinel, displayAxes: displayAxes };
})();
