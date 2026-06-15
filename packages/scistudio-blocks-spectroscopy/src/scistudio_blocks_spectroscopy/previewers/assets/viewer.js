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

function exportButton(host, resourceId, filename, format, label) {
  return el(
    "button",
    {
      style: "font:12px sans-serif;margin:2px 4px 2px 0;padding:3px 8px;cursor:pointer",
      onclick: () => {
        try {
          const p = host.exportArtifact({ resourceId, filename, format });
          if (p && typeof p.catch === "function") {
            p.catch((err) => host.reportError("export failed", { error: String(err) }));
          }
        } catch (err) {
          host.reportError("export failed", { error: String(err) });
        }
      },
    },
    label,
  );
}

function patchQuery(host, patch, label) {
  try {
    if (host.session && typeof host.session.patchQuery === "function") host.session.patchQuery(patch);
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

function svgText(parent, x, y, content, anchor) {
  const node = document.createElementNS(SVG_NS, "text");
  node.setAttribute("x", String(x));
  node.setAttribute("y", String(y));
  node.setAttribute("font-size", "11");
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

function renderInteractiveLines(container, seriesList, axes, options = {}) {
  const width = options.width || 620;
  const height = options.height || 240;
  const padL = 52;
  const padB = 28;
  const padT = 12;
  const padR = 16;
  const colors = ["#2b7de9", "#e8590c", "#2f9e44", "#9c36b5", "#0b7285", "#f08c00", "#495057"];
  const bounds = numericBounds(seriesList);

  if (!bounds) {
    container.appendChild(el("div", { style: "color:#888;font:13px sans-serif", text: "no plot data to display" }));
    return;
  }

  let view = { ...bounds };
  let mode = "pan";
  let drag = null;

  const toolbar = el("div", { style: "font:12px sans-serif;margin:4px 0" });
  const addButton = (label, fn) => toolbar.appendChild(el("button", { style: "margin-right:4px", onclick: fn }, label));
  addButton("Pan", () => {
    mode = "pan";
  });
  addButton("Box zoom", () => {
    mode = "box";
  });
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
  svg.setAttribute("style", "border:1px solid #ddd;background:#fff;cursor:crosshair;touch-action:none");
  const plotGroup = document.createElementNS(SVG_NS, "g");
  const marker = document.createElementNS(SVG_NS, "circle");
  const zoomBox = document.createElementNS(SVG_NS, "rect");
  marker.setAttribute("r", "3");
  marker.setAttribute("fill", "#e8590c");
  marker.setAttribute("visibility", "hidden");
  zoomBox.setAttribute("fill", "rgba(43,125,233,0.12)");
  zoomBox.setAttribute("stroke", "#2b7de9");
  zoomBox.setAttribute("stroke-dasharray", "4 3");
  zoomBox.setAttribute("visibility", "hidden");
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
    const xHalf = ((view.xMax - view.xMin) * factor) / 2;
    const yHalf = ((view.yMax - view.yMin) * factor) / 2;
    view = { xMin: cx - xHalf, xMax: cx + xHalf, yMin: cy - yHalf, yMax: cy + yHalf };
    redraw();
  }
  function axis(x1, y1, x2, y2) {
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", String(x1));
    line.setAttribute("y1", String(y1));
    line.setAttribute("x2", String(x2));
    line.setAttribute("y2", String(y2));
    line.setAttribute("stroke", "#bbb");
    plotGroup.appendChild(line);
  }
  function redraw() {
    plotGroup.replaceChildren();
    axis(padL, height - padB, width - padR, height - padB);
    axis(padL, padT, padL, height - padB);
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
      plotGroup.appendChild(line);
    }
    svgText(plotGroup, width / 2, height - 4, axes.x || "lambda", "middle");
    const yLabel = svgText(plotGroup, 12, height / 2, axes.y || "intensity", "middle");
    yLabel.setAttribute("transform", `rotate(-90 12 ${height / 2})`);
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
    zoomAt(evt.deltaY < 0 ? 0.82 : 1.22, p.x, p.y);
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

  const actions = el("div", { style: "margin-top:6px" });
  actions.appendChild(exportButton(host, "export_figure_svg", "spectrum.svg", "svg", "Export figure (SVG)"));
  actions.appendChild(exportButton(host, "export_figure_png", "spectrum.png", "png", "PNG"));
  actions.appendChild(exportButton(host, "export_figure_pdf", "spectrum.pdf", "pdf", "PDF"));
  actions.appendChild(exportButton(host, "export_points_csv", "spectrum_points.csv", "csv", "Export points (CSV)"));
  container.appendChild(actions);
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
  const modeSelect = el("select", { style: "font:12px sans-serif" });
  for (const mode of plotModes) modeSelect.appendChild(el("option", { value: mode, text: mode }));
  modeSelect.value = controls.plot_mode || plot.mode || "overlay";
  modeSelect.addEventListener("change", () => {
    drawDatasetPlot(plotHost, plot, modeSelect.value);
    patchQuery(host, { plot_mode: modeSelect.value }, "plot mode change");
  });

  const groupSelect = el("select", { style: "font:12px sans-serif" }, el("option", { value: "", text: "no group" }));
  const colorSelect = el("select", { style: "font:12px sans-serif" }, el("option", { value: "", text: "no color" }));
  for (const col of groupable) {
    groupSelect.appendChild(el("option", { value: col, text: col }));
    colorSelect.appendChild(el("option", { value: col, text: col }));
  }
  groupSelect.value = controls.group_by || "";
  colorSelect.value = controls.color_by || "";
  groupSelect.addEventListener("change", () => patchQuery(host, { group_by: groupSelect.value || null }, "group change"));
  colorSelect.addEventListener("change", () => patchQuery(host, { color_by: colorSelect.value || null }, "color change"));

  const searchInput = el("input", {
    type: "search",
    placeholder: "search index",
    style: "font:12px sans-serif;padding:2px 4px",
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

  const actions = el("div", { style: "margin-top:6px" });
  actions.appendChild(exportButton(host, "export_figure_svg", "dataset.svg", "svg", "Export figure (SVG)"));
  actions.appendChild(exportButton(host, "export_figure_png", "dataset.png", "png", "PNG"));
  actions.appendChild(exportButton(host, "export_figure_pdf", "dataset.pdf", "pdf", "PDF"));
  actions.appendChild(exportButton(host, "export_visible_spectra_csv", "visible_spectra.csv", "csv", "Export visible spectra (CSV)"));
  actions.appendChild(exportButton(host, "export_selected_rows_csv", "selected_rows.csv", "csv", "Export selected rows (CSV)"));
  actions.appendChild(exportButton(host, "export_grouped_summary_csv", "grouped_summary.csv", "csv", "Export grouped summary (CSV)"));
  container.appendChild(actions);
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
