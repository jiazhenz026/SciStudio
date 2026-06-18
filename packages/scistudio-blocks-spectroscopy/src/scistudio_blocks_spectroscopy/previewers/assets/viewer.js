// Spectroscopy previewer viewer (vanilla ESM, ADR-048 frontend contract).
//
// Self-contained, dependency-free module. It reads only the canonical host
// envelope/resources API and never mutates workflow/runtime/lineage state.

const API_VERSION = "1";
const SVG_NS = "http://www.w3.org/2000/svg";

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value == null) continue;
      if (key === "style") node.setAttribute("style", value);
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value);
    }
  }
  for (const child of children) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

const CONTROL_FONT = "12px system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";

function buttonStyle(active = false) {
  return [
    `font:${CONTROL_FONT}`,
    "display:inline-flex",
    "align-items:center",
    "justify-content:center",
    "min-height:28px",
    "padding:4px 10px",
    "border-radius:4px",
    `border:1px solid ${active ? "#2b7de9" : "#b8c0cc"}`,
    `background:${active ? "#e7f1ff" : "#fff"}`,
    `color:${active ? "#174ea6" : "#1f2933"}`,
    "cursor:pointer",
    "box-sizing:border-box",
  ].join(";");
}

function selectStyle() {
  return [
    `font:${CONTROL_FONT}`,
    "min-height:28px",
    "padding:3px 28px 3px 8px",
    "border:1px solid #b8c0cc",
    "border-radius:4px",
    "background:#fff",
    "color:#1f2933",
    "box-sizing:border-box",
  ].join(";");
}

function inputStyle(width = "112px") {
  return [
    `font:${CONTROL_FONT}`,
    `width:${width}`,
    "min-height:28px",
    "padding:3px 8px",
    "border:1px solid #b8c0cc",
    "border-radius:4px",
    "background:#fff",
    "color:#1f2933",
    "box-sizing:border-box",
  ].join(";");
}

function runExport(host, spec) {
  try {
    const p = host.exportArtifact({ resourceId: spec.resourceId, filename: spec.filename, format: spec.format });
    if (p && typeof p.catch === "function") {
      p.catch((err) => host.reportError("export failed", { error: String(err) }));
    }
  } catch (err) {
    host.reportError("export failed", { error: String(err) });
  }
}

function exportControls(host, options) {
  const specs = Array.isArray(options) ? options.filter((option) => option && option.resourceId) : [];
  if (!specs.length) return null;
  const byId = new Map(specs.map((spec) => [spec.resourceId, spec]));
  const select = el("select", { style: selectStyle(), "aria-label": "Export format" });
  for (const spec of specs) {
    select.appendChild(el("option", { value: spec.resourceId, text: spec.label }));
  }
  const button = el(
    "button",
    {
      type: "button",
      style: buttonStyle(),
      onclick: () => runExport(host, byId.get(select.value) || specs[0]),
    },
    "Export",
  );
  return el(
    "div",
    { style: "display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-top:8px" },
    select,
    button,
  );
}

function patchQuery(host, patch, label) {
  try {
    if (host.session && typeof host.session.patchQuery === "function") {
      const p = host.session.patchQuery(patch);
      if (p && typeof p.catch === "function") {
        p.catch((err) => host.reportError(`${label} failed`, { error: String(err) }));
      }
    }
  } catch (err) {
    host.reportError(`${label} failed`, { error: String(err) });
  }
}

function diagnosticsPanel(messages) {
  const list = Array.isArray(messages) ? messages.filter(Boolean) : [];
  if (!list.length) return null;
  const box = el("div", {
    style:
      "font:12px sans-serif;margin:6px 0;padding:6px 8px;border-left:3px solid #e0a800;background:#fff8e1;color:#664d03",
  });
  box.appendChild(el("div", { style: "font-weight:600;margin-bottom:2px", text: "Diagnostics" }));
  for (const msg of list) box.appendChild(el("div", { text: String(msg) }));
  return box;
}

function svgText(parent, x, y, content, anchor, size = 13, weight = "400") {
  const node = document.createElementNS(SVG_NS, "text");
  node.setAttribute("x", String(x));
  node.setAttribute("y", String(y));
  node.setAttribute("font-size", String(size));
  node.setAttribute("font-weight", weight);
  node.setAttribute("fill", "#555");
  node.setAttribute("text-anchor", anchor || "start");
  node.textContent = content;
  parent.appendChild(node);
  return node;
}

function numericBounds(seriesList) {
  const xs = [];
  const ys = [];
  for (const series of seriesList) {
    for (const point of series.points || []) {
      if (Number.isFinite(point.x) && Number.isFinite(point.y)) {
        xs.push(point.x);
        ys.push(point.y);
      }
    }
  }
  if (!xs.length) return null;
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  return {
    xMin,
    xMax: xMax === xMin ? xMin + 1 : xMax,
    yMin,
    yMax: yMax === yMin ? yMin + 1 : yMax,
  };
}

function formatTick(value) {
  if (!Number.isFinite(value)) return "";
  if (Math.abs(value - Math.round(value)) < 1e-9) return String(Math.round(value));
  const abs = Math.abs(value);
  if (abs >= 10000 || (abs > 0 && abs < 0.01)) return value.toExponential(2);
  if (abs >= 100) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(1).replace(/\.0$/, "");
  return value.toFixed(2).replace(/\.?0+$/, "");
}

function niceIntegerStep(span, count) {
  if (!Number.isFinite(span) || span <= 0) return 1;
  const raw = span / Math.max(1, count - 1);
  if (!Number.isFinite(raw) || raw <= 1) return 1;
  const power = 10 ** Math.floor(Math.log10(raw));
  const scaled = raw / power;
  const nice = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
  return Math.max(1, Math.round(nice * power));
}

function tickValues(min, max, count = 5, integer = false) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || count < 2) return [];
  if (min === max) return [min];
  const lo = Math.min(min, max);
  const hi = Math.max(min, max);
  if (integer) {
    const step = niceIntegerStep(hi - lo, count);
    const start = Math.ceil(lo / step) * step;
    const end = Math.floor(hi / step) * step;
    const ticks = [];
    for (let value = start; value <= end + step * 1e-9; value += step) {
      ticks.push(Object.is(value, -0) ? 0 : value);
      if (ticks.length > count + 4) break;
    }
    if (ticks.length) return ticks;
    const candidate = Math.round((lo + hi) / 2);
    return candidate >= lo && candidate <= hi ? [candidate] : [];
  }
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, idx) => min + step * idx);
}

function axisEditor(host, axes) {
  const xAxis = axes.x || {};
  const yAxis = axes.y || {};
  const xLabel = el("input", { type: "text", "aria-label": "X label", style: inputStyle("140px") });
  const xUnit = el("input", { type: "text", "aria-label": "X unit", style: inputStyle("76px") });
  const yLabel = el("input", { type: "text", "aria-label": "Y label", style: inputStyle("140px") });
  const yUnit = el("input", { type: "text", "aria-label": "Y unit", style: inputStyle("76px") });
  xLabel.value = xAxis.name || xAxis.label || "lambda";
  xUnit.value = xAxis.unit || "";
  yLabel.value = yAxis.name || yAxis.label || "intensity";
  yUnit.value = yAxis.unit || "";
  const apply = () => {
    patchQuery(
      host,
      {
        axis_labels: { x: xLabel.value.trim(), y: yLabel.value.trim() },
        axis_units: { x: xUnit.value.trim(), y: yUnit.value.trim() },
      },
      "axis update",
    );
  };
  for (const input of [xLabel, xUnit, yLabel, yUnit]) {
    input.addEventListener("keydown", (evt) => {
      if (evt.key === "Enter") apply();
    });
  }
  const labelStyle = `font:${CONTROL_FONT};color:#52606d;display:inline-flex;align-items:center;gap:4px`;
  return el(
    "div",
    { style: "display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:6px 0" },
    el("label", { style: labelStyle }, "X", xLabel),
    el("label", { style: labelStyle }, "unit", xUnit),
    el("label", { style: labelStyle }, "Y", yLabel),
    el("label", { style: labelStyle }, "unit", yUnit),
    el("button", { type: "button", style: buttonStyle(), onclick: apply }, "Apply"),
  );
}

function renderInteractiveLines(container, seriesList, axes, options = {}) {
  const width = options.width || 720;
  const height = options.height || 260;
  const padL = 64;
  const padB = 44;
  const padT = 18;
  const padR = 20;
  const colors = ["#2b7de9", "#e8590c", "#2f9e44", "#9c36b5", "#0b7285", "#f08c00", "#495057"];
  const bounds = numericBounds(seriesList);

  if (!bounds) {
    container.appendChild(el("div", { style: "color:#888;font:13px sans-serif", text: "no plot data to display" }));
    return;
  }

  let view = { ...bounds };
  let mode = "pan";
  let drag = null;

  const toolbar = el("div", {
    style: `font:${CONTROL_FONT};display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0`,
  });
  const modeButtons = {};
  const syncToolbar = () => {
    for (const [key, button] of Object.entries(modeButtons)) {
      button.setAttribute("style", buttonStyle(mode === key));
    }
  };
  const addButton = (label, fn, key = null) => {
    const button = el(
      "button",
      {
        type: "button",
        style: buttonStyle(key ? mode === key : false),
        onclick: () => {
          fn();
          syncToolbar();
        },
      },
      label,
    );
    if (key) modeButtons[key] = button;
    toolbar.appendChild(button);
    return button;
  };
  addButton("Pan", () => {
    mode = "pan";
  }, "pan");
  addButton("Box zoom", () => {
    mode = "box";
  }, "box");
  addButton("Zoom in", () => zoomAt(0.75, width / 2, height / 2));
  addButton("Zoom out", () => zoomAt(1.33, width / 2, height / 2));
  addButton("Reset", () => {
    view = { ...bounds };
    redraw();
  });
  container.appendChild(toolbar);

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute(
    "style",
    "border:1px solid #d6dce5;background:#fff;cursor:crosshair;touch-action:none;max-width:100%;height:auto;display:block",
  );
  const clipId = `spectroscopy-plot-clip-${Math.random().toString(36).slice(2)}`;
  const defs = document.createElementNS(SVG_NS, "defs");
  const clipPath = document.createElementNS(SVG_NS, "clipPath");
  const clipRect = document.createElementNS(SVG_NS, "rect");
  clipPath.setAttribute("id", clipId);
  clipRect.setAttribute("x", String(padL));
  clipRect.setAttribute("y", String(padT));
  clipRect.setAttribute("width", String(width - padL - padR));
  clipRect.setAttribute("height", String(height - padT - padB));
  clipPath.appendChild(clipRect);
  defs.appendChild(clipPath);
  const plotGroup = document.createElementNS(SVG_NS, "g");
  const marker = document.createElementNS(SVG_NS, "circle");
  const zoomBox = document.createElementNS(SVG_NS, "rect");
  marker.setAttribute("r", "3");
  marker.setAttribute("fill", "#e8590c");
  marker.setAttribute("visibility", "hidden");
  marker.setAttribute("clip-path", `url(#${clipId})`);
  zoomBox.setAttribute("fill", "rgba(43,125,233,0.12)");
  zoomBox.setAttribute("stroke", "#2b7de9");
  zoomBox.setAttribute("stroke-dasharray", "4 3");
  zoomBox.setAttribute("visibility", "hidden");
  svg.appendChild(defs);
  svg.appendChild(plotGroup);
  svg.appendChild(marker);
  svg.appendChild(zoomBox);
  container.appendChild(svg);

  const readout = el("div", { style: "font:12px monospace;color:#333;height:16px;margin-top:2px", text: "" });
  container.appendChild(readout);

  function sx(x) {
    return padL + ((x - view.xMin) / (view.xMax - view.xMin || 1)) * (width - padL - padR);
  }
  function sy(y) {
    return height - padB - ((y - view.yMin) / (view.yMax - view.yMin || 1)) * (height - padT - padB);
  }
  function dataX(px) {
    return view.xMin + ((px - padL) / (width - padL - padR)) * (view.xMax - view.xMin);
  }
  function dataY(py) {
    return view.yMin + ((height - padB - py) / (height - padT - padB)) * (view.yMax - view.yMin);
  }
  function pointer(evt) {
    const rect = svg.getBoundingClientRect();
    return {
      x: ((evt.clientX - rect.left) / rect.width) * width,
      y: ((evt.clientY - rect.top) / rect.height) * height,
    };
  }
  function zoomAt(factor, px, py) {
    const cx = dataX(px);
    const cy = dataY(py);
    view = {
      xMin: cx - (cx - view.xMin) * factor,
      xMax: cx + (view.xMax - cx) * factor,
      yMin: cy - (cy - view.yMin) * factor,
      yMax: cy + (view.yMax - cy) * factor,
    };
    redraw();
  }
  function lineNode(x1, y1, x2, y2, stroke = "#b8c0cc", widthValue = "1") {
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", String(x1));
    line.setAttribute("y1", String(y1));
    line.setAttribute("x2", String(x2));
    line.setAttribute("y2", String(y2));
    line.setAttribute("stroke", stroke);
    line.setAttribute("stroke-width", widthValue);
    plotGroup.appendChild(line);
    return line;
  }
  function axis(x1, y1, x2, y2) {
    lineNode(x1, y1, x2, y2, "#a8b0bb", "1.1");
  }
  function drawTicks() {
    for (const tick of tickValues(view.xMin, view.xMax, 6, true)) {
      const x = sx(tick);
      if (x < padL - 0.5 || x > width - padR + 0.5) continue;
      lineNode(x, padT, x, height - padB, "#edf0f5");
      lineNode(x, height - padB, x, height - padB + 5, "#8f9aa8");
      svgText(plotGroup, x, height - padB + 19, formatTick(tick), "middle", 12);
    }
    for (const tick of tickValues(view.yMin, view.yMax, 5, true)) {
      const y = sy(tick);
      if (y < padT - 0.5 || y > height - padB + 0.5) continue;
      lineNode(padL, y, width - padR, y, "#edf0f5");
      lineNode(padL - 5, y, padL, y, "#8f9aa8");
      svgText(plotGroup, padL - 8, y + 4, formatTick(tick), "end", 12);
    }
  }
  function redraw() {
    plotGroup.replaceChildren();
    drawTicks();
    axis(padL, height - padB, width - padR, height - padB);
    axis(padL, padT, padL, height - padB);
    const dataGroup = document.createElementNS(SVG_NS, "g");
    dataGroup.setAttribute("clip-path", `url(#${clipId})`);
    plotGroup.appendChild(dataGroup);
    for (const [i, series] of seriesList.entries()) {
      const points = (series.points || []).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
      if (!points.length) continue;
      const path = points.map((p, idx) => `${idx === 0 ? "M" : "L"}${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`).join(" ");
      const line = document.createElementNS(SVG_NS, "path");
      line.setAttribute("d", path);
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", colors[i % colors.length]);
      line.setAttribute("stroke-width", series.selected ? "2.4" : "1.4");
      line.setAttribute("opacity", series.dimmed ? "0.35" : "1");
      dataGroup.appendChild(line);
    }
    svgText(plotGroup, width / 2, height - 8, axes.x || "lambda", "middle", 14, "600");
    const yLabel = svgText(plotGroup, 16, height / 2, axes.y || "intensity", "middle", 14, "600");
    yLabel.setAttribute("transform", `rotate(-90 16 ${height / 2})`);
  }
  function nearestPoint(px) {
    let nearest = null;
    let best = Infinity;
    for (const series of seriesList) {
      for (const point of series.points || []) {
        const dist = Math.abs(sx(point.x) - px);
        if (dist < best) {
          best = dist;
          nearest = point;
        }
      }
    }
    return nearest;
  }

  svg.addEventListener("wheel", (evt) => {
    evt.preventDefault();
    const p = pointer(evt);
    const primaryDelta = Math.abs(evt.deltaY) >= Math.abs(evt.deltaX) ? evt.deltaY : evt.deltaX;
    if (primaryDelta === 0) return;
    zoomAt(primaryDelta < 0 ? 0.82 : 1.22, p.x, p.y);
  });
  svg.addEventListener("mousedown", (evt) => {
    const p = pointer(evt);
    drag = { mode, start: p, view: { ...view } };
    if (mode === "box") {
      zoomBox.setAttribute("x", String(p.x));
      zoomBox.setAttribute("y", String(p.y));
      zoomBox.setAttribute("width", "0");
      zoomBox.setAttribute("height", "0");
      zoomBox.setAttribute("visibility", "visible");
    }
  });
  svg.addEventListener("mousemove", (evt) => {
    const p = pointer(evt);
    const nearest = nearestPoint(p.x);
    if (nearest) {
      marker.setAttribute("cx", String(sx(nearest.x)));
      marker.setAttribute("cy", String(sy(nearest.y)));
      marker.setAttribute("visibility", "visible");
      readout.textContent = `${axes.x || "x"} = ${nearest.x}    ${axes.y || "y"} = ${nearest.y}`;
    }
    if (!drag) return;
    if (drag.mode === "pan") {
      const dx = dataX(drag.start.x) - dataX(p.x);
      const dy = dataY(drag.start.y) - dataY(p.y);
      view = {
        xMin: drag.view.xMin + dx,
        xMax: drag.view.xMax + dx,
        yMin: drag.view.yMin + dy,
        yMax: drag.view.yMax + dy,
      };
      redraw();
    } else {
      zoomBox.setAttribute("x", String(Math.min(drag.start.x, p.x)));
      zoomBox.setAttribute("y", String(Math.min(drag.start.y, p.y)));
      zoomBox.setAttribute("width", String(Math.abs(p.x - drag.start.x)));
      zoomBox.setAttribute("height", String(Math.abs(p.y - drag.start.y)));
    }
  });
  window.addEventListener("mouseup", (evt) => {
    if (!drag) return;
    const p = pointer(evt);
    if (drag.mode === "box" && Math.abs(p.x - drag.start.x) > 8 && Math.abs(p.y - drag.start.y) > 8) {
      const x1 = dataX(Math.min(p.x, drag.start.x));
      const x2 = dataX(Math.max(p.x, drag.start.x));
      const y1 = dataY(Math.max(p.y, drag.start.y));
      const y2 = dataY(Math.min(p.y, drag.start.y));
      view = { xMin: x1, xMax: x2, yMin: y1, yMax: y2 };
      redraw();
    }
    zoomBox.setAttribute("visibility", "hidden");
    drag = null;
  });
  svg.addEventListener("mouseleave", () => marker.setAttribute("visibility", "hidden"));

  redraw();
}

function renderSpectrum(container, payload, host, diagnostics) {
  const points = Array.isArray(payload.points) ? payload.points : [];
  const total = payload.total != null ? payload.total : points.length;
  const axes = payload.axes || {};
  const xAxis = axes.x || { label: "lambda" };
  const yAxis = axes.y || { label: "intensity" };

  container.appendChild(
    el("div", {
      style: "font:13px sans-serif;margin-bottom:4px;font-weight:600",
      text: `Spectrum - ${points.length} of ${total} point(s)`,
    }),
  );

  const panel = diagnosticsPanel(diagnostics);
  if (panel) container.appendChild(panel);

  renderInteractiveLines(container, [{ spectrum_id: "spectrum", points }], { x: xAxis.label, y: yAxis.label });

  container.appendChild(axisEditor(host, axes));

  const actions = exportControls(host, [
    { resourceId: "export_figure_svg", filename: "spectrum.svg", format: "svg", label: "Figure SVG" },
    { resourceId: "export_figure_png", filename: "spectrum.png", format: "png", label: "Figure PNG" },
    { resourceId: "export_figure_pdf", filename: "spectrum.pdf", format: "pdf", label: "Figure PDF" },
    { resourceId: "export_points_csv", filename: "spectrum_points.csv", format: "csv", label: "Points CSV" },
  ]);
  if (actions) container.appendChild(actions);
}

function drawDatasetPlot(container, plot, mode) {
  container.replaceChildren();
  const axes = { x: "lambda", y: "intensity" };
  if (mode === "heatmap") {
    const heatmap = plot.heatmap || {};
    if (!heatmap.aligned || !Array.isArray(heatmap.matrix) || !heatmap.matrix.length) {
      container.appendChild(
        el("div", {
          style: "font:12px sans-serif;color:#664d03",
          text: "heatmap unavailable until visible spectra share one lambda grid",
        }),
      );
      return;
    }
    const table = el("table", { style: "font:11px monospace;border-collapse:collapse;max-width:100%;overflow:auto" });
    for (let i = 0; i < heatmap.matrix.length; i += 1) {
      const row = heatmap.matrix[i] || [];
      const max = Math.max(...row.map((v) => Math.abs(v)), 1);
      const tr = el("tr", null, el("th", { style: "border:1px solid #ddd;padding:2px 4px", text: String(heatmap.rows[i]) }));
      for (const value of row) {
        const alpha = Math.min(1, Math.abs(value) / max);
        tr.appendChild(
          el("td", {
            style: `border:1px solid #eee;padding:2px 4px;background:rgba(43,125,233,${alpha})`,
            text: Number(value).toFixed(2),
          }),
        );
      }
      table.appendChild(tr);
    }
    container.appendChild(table);
    return;
  }

  let series = [];
  if (mode === "selected") series = ((plot.selected || {}).series || []).map((s) => ({ ...s, selected: true }));
  else if (mode === "group_mean") {
    series = ((plot.group_mean || {}).groups || []).map((g) => ({ spectrum_id: g.group, points: g.points || [] }));
  } else if (mode === "group_band") {
    series = ((plot.group_band || {}).groups || []).flatMap((g) => [
      { spectrum_id: `${g.group} mean`, points: (g.points || []).map((p) => ({ x: p.x, y: p.mean })) },
      { spectrum_id: `${g.group} min`, points: (g.points || []).map((p) => ({ x: p.x, y: p.min })), dimmed: true },
      { spectrum_id: `${g.group} max`, points: (g.points || []).map((p) => ({ x: p.x, y: p.max })), dimmed: true },
    ]);
  } else {
    series = ((plot.overlay || {}).series || []).map((s) => ({ ...s, selected: s.selected }));
  }
  renderInteractiveLines(container, series, axes, { height: 220 });
}

function renderDataset(container, payload, host, diagnostics) {
  const slots = payload.slots && typeof payload.slots === "object" ? payload.slots : {};
  const indexTable = payload.index_table || {};
  const plotModes = Array.isArray(payload.plot_modes) ? payload.plot_modes : ["overlay"];
  const datasetDiag = payload.diagnostics || {};
  const controls = payload.controls || {};
  const plot = payload.plot || {};
  const columns = Array.isArray(indexTable.columns) ? indexTable.columns : [];
  const rows = Array.isArray(indexTable.rows) ? indexTable.rows : [];
  const groupable = Array.isArray(controls.groupable_columns)
    ? controls.groupable_columns
    : columns.filter((c) => c !== "spectrum_id");
  const filterable = Array.isArray(controls.filterable_columns) ? controls.filterable_columns : columns;
  const activeFilters = Array.isArray(controls.active_filters) ? controls.active_filters : [];
  const firstFilter = activeFilters.length ? activeFilters[0] : {};
  let selected = new Set(Array.isArray(controls.selected_ids) ? controls.selected_ids.map(String) : []);
  let search = "";

  container.appendChild(
    el("div", {
      style: "font:13px sans-serif;margin-bottom:4px;font-weight:600",
      text: `SpectralDataset - ${Object.keys(slots).length} slot(s)`,
    }),
  );

  const controlBar = el("div", {
    style: "font:12px sans-serif;display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:4px 0",
  });
  const modeSelect = el("select", { style: selectStyle() });
  for (const mode of plotModes) modeSelect.appendChild(el("option", { value: mode, text: mode }));
  modeSelect.value = controls.plot_mode || plot.mode || "overlay";
  modeSelect.addEventListener("change", () => {
    drawDatasetPlot(plotHost, plot, modeSelect.value);
    patchQuery(host, { plot_mode: modeSelect.value }, "plot mode change");
  });

  const groupSelect = el("select", { style: selectStyle() }, el("option", { value: "", text: "no group" }));
  const colorSelect = el("select", { style: selectStyle() }, el("option", { value: "", text: "no color" }));
  for (const col of groupable) {
    groupSelect.appendChild(el("option", { value: col, text: col }));
    colorSelect.appendChild(el("option", { value: col, text: col }));
  }
  groupSelect.value = controls.group_by || "";
  colorSelect.value = controls.color_by || "";
  groupSelect.addEventListener("change", () => patchQuery(host, { group_by: groupSelect.value || null }, "group change"));
  colorSelect.addEventListener("change", () => patchQuery(host, { color_by: colorSelect.value || null }, "color change"));

  const filterSelect = el("select", { style: selectStyle() }, el("option", { value: "", text: "no filter" }));
  for (const col of filterable) filterSelect.appendChild(el("option", { value: col, text: col }));
  filterSelect.value = firstFilter.column || "";
  const filterInput = el("input", {
    type: "search",
    placeholder: "filter value",
    value: firstFilter.value || "",
    style: `${selectStyle()};width:120px;padding-right:8px`,
  });
  const applyFilter = () =>
    patchQuery(
      host,
      {
        filter_column: filterSelect.value || null,
        filter_value: filterSelect.value && filterInput.value ? filterInput.value : null,
      },
      "filter update",
    );
  filterInput.addEventListener("keydown", (evt) => {
    if (evt.key === "Enter") applyFilter();
  });
  const filterButton = el("button", { type: "button", style: buttonStyle(), onclick: applyFilter }, "Apply");
  const clearFilterButton = el("button", {
    type: "button",
    style: buttonStyle(),
    onclick: () => {
      filterSelect.value = "";
      filterInput.value = "";
      patchQuery(host, { filter_column: null, filter_value: null, filters: null }, "filter clear");
    },
  }, "Clear");

  const searchInput = el("input", {
    type: "search",
    placeholder: "search index",
    style: `${selectStyle()};padding-right:8px`,
    oninput: () => {
      search = searchInput.value.toLowerCase();
      drawTable();
    },
  });
  controlBar.appendChild(el("span", null, "Plot"));
  controlBar.appendChild(modeSelect);
  controlBar.appendChild(el("span", null, "Group"));
  controlBar.appendChild(groupSelect);
  controlBar.appendChild(el("span", null, "Color"));
  controlBar.appendChild(colorSelect);
  controlBar.appendChild(el("span", null, "Filter"));
  controlBar.appendChild(filterSelect);
  controlBar.appendChild(filterInput);
  controlBar.appendChild(filterButton);
  controlBar.appendChild(clearFilterButton);
  controlBar.appendChild(searchInput);
  container.appendChild(controlBar);

  const plotHost = el("div", { style: "margin:6px 0" });
  container.appendChild(plotHost);
  drawDatasetPlot(plotHost, plot, modeSelect.value);

  const tableHost = el("div", null);
  container.appendChild(tableHost);

  function selectedList() {
    return Array.from(selected).sort();
  }
  function rowMatches(row) {
    if (!search) return true;
    return columns.some((col) => String(row && row[col] != null ? row[col] : "").toLowerCase().includes(search));
  }
  function drawTable() {
    tableHost.replaceChildren();
    if (indexTable.available && columns.length) {
      const table = el("table", { style: "font:12px sans-serif;border-collapse:collapse;margin-top:6px;width:100%" });
      const head = el("tr", null);
      head.appendChild(el("th", { style: "border:1px solid #ddd;padding:3px 6px;background:#f6f6f6", text: "select" }));
      for (const col of columns) {
        const th = el("th", {
          style: "border:1px solid #ddd;padding:3px 6px;background:#f6f6f6;text-align:left;cursor:pointer",
          text: col,
        });
        th.addEventListener("click", () => patchQuery(host, { sort_by: col, sort_dir: "asc" }, "sort"));
        head.appendChild(th);
      }
      table.appendChild(head);
      for (const row of rows.filter(rowMatches)) {
        const sid = String(row && row.spectrum_id != null ? row.spectrum_id : "");
        const tr = el("tr", { style: selected.has(sid) ? "background:#e7f5ff" : "" });
        const checkbox = el("input", { type: "checkbox" });
        checkbox.checked = selected.has(sid);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) selected.add(sid);
          else selected.delete(sid);
          drawTable();
          patchQuery(host, { selected_ids: selectedList() }, "selection update");
        });
        tr.appendChild(el("td", { style: "border:1px solid #eee;padding:3px 6px" }, checkbox));
        for (const col of columns) {
          tr.appendChild(
            el("td", { style: "border:1px solid #eee;padding:3px 6px" }, String(row && row[col] != null ? row[col] : "")),
          );
        }
        table.appendChild(tr);
      }
      tableHost.appendChild(table);
      tableHost.appendChild(
        el("div", {
          style: "font:11px sans-serif;color:#888;margin-top:2px",
          text: `index: showing ${rows.length} of ${indexTable.total_rows || rows.length} row(s) (page ${indexTable.page || 1})`,
        }),
      );
      return;
    }
    const list = el("ul", { style: "font:13px sans-serif;margin:6px 0;padding-left:18px" });
    for (const [name, type] of Object.entries(slots)) {
      const li = el("li", { style: "cursor:pointer", text: `${name}: ${type}` });
      li.addEventListener("click", () => {
        try {
          if (host.session && typeof host.session.getResource === "function") host.session.getResource(`slot:${name}`);
        } catch (err) {
          host.reportError(`failed to open slot ${name}`, { error: String(err) });
        }
      });
      list.appendChild(li);
    }
    tableHost.appendChild(list);
  }
  drawTable();

  const issues = Array.isArray(datasetDiag.issues) ? datasetDiag.issues : [];
  const diagMsgs = issues.map((i) => (i && i.code ? `${i.code}: ${JSON.stringify(i)}` : String(i)));
  const panel = diagnosticsPanel([...diagMsgs, ...(Array.isArray(diagnostics) ? diagnostics : [])]);
  if (panel) container.appendChild(panel);
  if (datasetDiag.ok) {
    container.appendChild(
      el("div", { style: "font:12px sans-serif;color:#2f9e44;margin:4px 0", text: "No dataset health issues detected." }),
    );
  }

  const actions = exportControls(host, [
    { resourceId: "export_figure_svg", filename: "dataset.svg", format: "svg", label: "Figure SVG" },
    { resourceId: "export_figure_png", filename: "dataset.png", format: "png", label: "Figure PNG" },
    { resourceId: "export_figure_pdf", filename: "dataset.pdf", format: "pdf", label: "Figure PDF" },
    {
      resourceId: "export_visible_spectra_csv",
      filename: "visible_spectra.csv",
      format: "csv",
      label: "Visible spectra CSV",
    },
    { resourceId: "export_selected_rows_csv", filename: "selected_rows.csv", format: "csv", label: "Selected rows CSV" },
    {
      resourceId: "export_grouped_summary_csv",
      filename: "grouped_summary.csv",
      format: "csv",
      label: "Grouped summary CSV",
    },
  ]);
  if (actions) container.appendChild(actions);
}

export default {
  apiVersion: API_VERSION,
  mount(container, host) {
    const root = el("div", { style: "padding:8px" });
    container.appendChild(root);

    function draw(envelope) {
      root.replaceChildren();
      const payload = (envelope && envelope.payload) || {};
      const kind = (envelope && envelope.kind) || host.kind;
      const diagnostics = (envelope && envelope.diagnostics) || [];
      try {
        if (kind === "series") renderSpectrum(root, payload, host, diagnostics);
        else if (kind === "composite") renderDataset(root, payload, host, diagnostics);
        else if (kind === "error") {
          const msg = envelope && envelope.error && envelope.error.message;
          root.appendChild(el("div", { style: "color:#c0392b;font:13px sans-serif", text: msg || "preview unavailable" }));
        } else {
          root.appendChild(el("div", { style: "color:#888;font:13px sans-serif", text: `unsupported kind: ${kind}` }));
        }
      } catch (err) {
        host.reportError("spectroscopy viewer render failed", { error: String(err) });
      }
    }

    draw(host.envelope);

    return {
      update(envelope) {
        draw(envelope);
      },
      unmount() {
        root.replaceChildren();
      },
    };
  },
};
