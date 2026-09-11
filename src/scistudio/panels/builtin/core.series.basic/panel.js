/* core.series.basic — line chart + table of a Series (parity: SeriesViewer).
 *
 * Faithful display (#1886 item D): series.points reports where non-finite points
 * were dropped (nonfinite_positions / nonnumeric). This panel surfaces that as an
 * explicit banner — how many NaN/inf points were skipped and where — so dropped
 * samples never silently vanish. Decimation is disclosed too. */
(function () {
  "use strict";
  var api = window.scistudio;
  var root = document.getElementById("root");
  var mode = "chart";
  var data = null;

  function el(tag, props, kids) {
    var node = document.createElement(tag);
    if (props) Object.keys(props).forEach(function (k) {
      if (k === "text") node.textContent = props[k];
      else if (k === "onclick") node.onclick = props[k];
      else if (k === "style") node.setAttribute("style", props[k]);
      else node.setAttribute(k, props[k]);
    });
    (kids || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function gapSummary(d) {
    var count = d.nonnumeric || 0;
    if (!count) return null;
    var positions = d.nonfinite_positions || [];
    var complete = d.nonfinite_positions_complete !== false;
    var shown = positions.slice(0, 20).join(", ");
    var text = count + " of " + (d.total || 0) + " point" + (count === 1 ? "" : "s") + " were NaN or ∞ and were skipped";
    if (positions.length) {
      text += " (position" + (positions.length === 1 ? "" : "s") + " " + shown;
      if (!complete) text += ", first " + positions.length + " shown";
      text += ")";
    }
    return el("div", { class: "gaps", "data-testid": "series-nonfinite-gaps", role: "status", text: text });
  }
  function decimationNote(d) {
    if (!d.sampled) return null;
    return el("div", { class: "note", "data-testid": "series-decimation", text: "showing " + (d.values ? d.values.length : 0) + " of " + (d.total || 0) + " points (" + (d.decimation || "decimated") + ")" });
  }

  function drawChart(canvas, xs, ys) {
    var ctx = null;
    try { ctx = canvas.getContext && canvas.getContext("2d"); } catch (e) { ctx = null; }
    if (!ctx) return;
    var W = canvas.width = canvas.clientWidth || 600;
    var H = canvas.height = 240;
    var pad = 34;
    ctx.clearRect(0, 0, W, H);
    if (!xs.length) return;
    var xmin = Math.min.apply(null, xs), xmax = Math.max.apply(null, xs);
    var ymin = Math.min.apply(null, ys), ymax = Math.max.apply(null, ys);
    if (xmax === xmin) xmax = xmin + 1;
    if (ymax === ymin) ymax = ymin + 1;
    var sx = function (x) { return pad + (x - xmin) / (xmax - xmin) * (W - pad - 10); };
    var sy = function (y) { return H - pad - (y - ymin) / (ymax - ymin) * (H - pad - 10); };
    ctx.strokeStyle = "rgba(120,120,120,0.5)"; ctx.beginPath();
    ctx.moveTo(pad, 6); ctx.lineTo(pad, H - pad); ctx.lineTo(W - 6, H - pad); ctx.stroke();
    ctx.fillStyle = "rgba(120,120,120,0.9)"; ctx.font = "10px system-ui";
    ctx.fillText(String(ymax), 2, 12); ctx.fillText(String(ymin), 2, H - pad);
    ctx.fillText(String(xmin), pad, H - 6); ctx.fillText(String(xmax), W - 40, H - 6);
    ctx.strokeStyle = "#f06a44"; ctx.lineWidth = 1.5; ctx.beginPath();
    for (var i = 0; i < xs.length; i++) { var px = sx(xs[i]), py = sy(ys[i]); if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py); }
    ctx.stroke();
  }

  function render() {
    var xs = data.index || [];
    var ys = data.values || [];
    root.textContent = "";
    var toggle = el("div", { class: "toggle" }, [
      el("button", { text: "Chart", "aria-pressed": mode === "chart" ? "true" : "false", onclick: function () { mode = "chart"; render(); } }),
      el("button", { text: "Table", "aria-pressed": mode === "table" ? "true" : "false", onclick: function () { mode = "table"; render(); } }),
    ]);
    root.appendChild(toggle);
    var gaps = gapSummary(data); if (gaps) root.appendChild(gaps);
    var dec = decimationNote(data); if (dec) root.appendChild(dec);
    if (mode === "chart") {
      var canvas = el("canvas", { "data-testid": "series-chart", "aria-label": "Series line chart" });
      root.appendChild(canvas);
      setTimeout(function () { drawChart(canvas, xs, ys); }, 0);
      drawChart(canvas, xs, ys);
    } else {
      var body = xs.map(function (x, i) { return el("tr", null, [el("td", { text: String(x) }), el("td", { text: String(ys[i]) })]); });
      root.appendChild(el("div", { class: "scroll", "data-testid": "series-table" }, [
        el("table", null, [
          el("thead", null, [el("tr", null, [el("th", { text: "index" }), el("th", { text: "value" })])]),
          el("tbody", null, body),
        ]),
      ]));
    }
  }

  api.ready().then(function () {
    return api.read("series.points", {}).then(function (d) { data = d; render(); });
  }).catch(function (err) {
    root.textContent = "";
    root.appendChild(el("div", { class: "err", role: "alert", text: "Could not read series: " + (err && err.message || err) }));
    api.reportError(String(err && err.message || err));
  });

  window.__panel = { gapSummary: gapSummary, decimationNote: decimationNote };
})();
