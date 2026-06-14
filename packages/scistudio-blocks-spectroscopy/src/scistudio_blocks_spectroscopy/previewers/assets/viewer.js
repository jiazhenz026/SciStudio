// Spectroscopy previewer viewer (vanilla ESM, ADR-048 frontend contract).
//
// Self-contained, dependency-free ES module (NO npm, NO framework). It reads
// everything through the constrained `host` API only and renders both the
// SERIES (Spectrum) and COMPOSITE (SpectralDataset) envelope kinds. If this
// module fails to load, the platform degrades to the core series/composite
// renderer (the envelope kind is chosen so that fallback is lossless).
//
// host API contract (see imaging viewer.js / previewerHostApi.ts):
//   host.envelope.payload          — the JSON payload built by the provider
//   host.kind                      — "series" / "composite" / "error"
//   host.session.patchQuery(q)     — re-render with new query (page/sort/...)
//   host.session.getResource(id)   — bounded child / resource read
//   host.exportArtifact(req)       — user-initiated figure / rows export
//   host.reportError(msg, detail)  — non-fatal error channel
//
// It causes NO workflow/runtime/lineage mutation (FR-030: previewers perform
// no scientific processing — only display).

const API_VERSION = "1";

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value == null) continue;
      if (key === "style") node.setAttribute("style", value);
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2), value);
      } else node.setAttribute(key, value);
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

function diagnosticsPanel(messages) {
  const list = Array.isArray(messages) ? messages.filter(Boolean) : [];
  if (list.length === 0) return null;
  const box = el("div", {
    style:
      "font:12px sans-serif;margin:6px 0;padding:6px 8px;border-left:3px solid #e0a800;background:#fff8e1;color:#664d03",
  });
  box.appendChild(el("div", { style: "font-weight:600;margin-bottom:2px", text: "Diagnostics" }));
  for (const msg of list) box.appendChild(el("div", { text: String(msg) }));
  return box;
}

/* -------------------------------------------------------------------------
 * Spectrum (SERIES) — interactive 2-D line plot with axis labels + units.
 * ----------------------------------------------------------------------- */

function renderSpectrum(container, payload, host, diagnostics) {
  const points = Array.isArray(payload.points) ? payload.points : [];
  const total = payload.total != null ? payload.total : points.length;
  const axes = payload.axes || {};
  const xAxis = axes.x || { label: "lambda" };
  const yAxis = axes.y || { label: "intensity" };

  container.appendChild(
    el("div", {
      style: "font:13px sans-serif;margin-bottom:4px;font-weight:600",
      text: `Spectrum — ${points.length} of ${total} point(s)`,
    }),
  );

  const panel = diagnosticsPanel(diagnostics);
  if (panel) container.appendChild(panel);

  if (points.length === 0) {
    container.appendChild(el("div", { style: "color:#888;font:13px sans-serif", text: "no points to display" }));
    return;
  }

  const width = 620;
  const height = 240;
  const padL = 52;
  const padB = 28;
  const padT = 10;
  const padR = 12;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const xSpan = xMax - xMin || 1;
  const ySpan = yMax - yMin || 1;
  const sx = (x) => padL + ((x - xMin) / xSpan) * (width - padL - padR);
  const sy = (y) => height - padB - ((y - yMin) / ySpan) * (height - padT - padB);

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`).join(" ");

  const svgNs = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNs, "svg");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("style", "border:1px solid #eee;background:#fff");

  const axisLine = (x1, y1, x2, y2) => {
    const l = document.createElementNS(svgNs, "line");
    l.setAttribute("x1", String(x1));
    l.setAttribute("y1", String(y1));
    l.setAttribute("x2", String(x2));
    l.setAttribute("y2", String(y2));
    l.setAttribute("stroke", "#bbb");
    l.setAttribute("stroke-width", "1");
    return l;
  };
  svg.appendChild(axisLine(padL, height - padB, width - padR, height - padB));
  svg.appendChild(axisLine(padL, padT, padL, height - padB));

  const polyline = document.createElementNS(svgNs, "path");
  polyline.setAttribute("d", path);
  polyline.setAttribute("fill", "none");
  polyline.setAttribute("stroke", "#2b7de9");
  polyline.setAttribute("stroke-width", "1.5");
  svg.appendChild(polyline);

  const text = (x, y, content, anchor) => {
    const t = document.createElementNS(svgNs, "text");
    t.setAttribute("x", String(x));
    t.setAttribute("y", String(y));
    t.setAttribute("font-size", "11");
    t.setAttribute("fill", "#555");
    t.setAttribute("text-anchor", anchor || "start");
    t.textContent = content;
    return t;
  };
  svg.appendChild(text(width / 2, height - 4, xAxis.label || "lambda", "middle"));
  const yLabel = text(12, height / 2, yAxis.label || "intensity", "middle");
  yLabel.setAttribute("transform", `rotate(-90 12 ${height / 2})`);
  svg.appendChild(yLabel);

  // Hover coordinate / intensity readout (FR-019).
  const readout = el("div", {
    style: "font:12px monospace;color:#333;height:16px;margin-top:2px",
    text: "hover the plot for (x, y)",
  });
  const marker = document.createElementNS(svgNs, "circle");
  marker.setAttribute("r", "3");
  marker.setAttribute("fill", "#e8590c");
  marker.setAttribute("visibility", "hidden");
  svg.appendChild(marker);
  svg.addEventListener("mousemove", (evt) => {
    const rect = svg.getBoundingClientRect();
    const px = ((evt.clientX - rect.left) / rect.width) * width;
    let nearest = points[0];
    let best = Infinity;
    for (const p of points) {
      const d = Math.abs(sx(p.x) - px);
      if (d < best) {
        best = d;
        nearest = p;
      }
    }
    marker.setAttribute("cx", String(sx(nearest.x)));
    marker.setAttribute("cy", String(sy(nearest.y)));
    marker.setAttribute("visibility", "visible");
    readout.textContent = `${xAxis.label || "x"} = ${nearest.x}    ${yAxis.label || "y"} = ${nearest.y}`;
  });
  svg.addEventListener("mouseleave", () => {
    marker.setAttribute("visibility", "hidden");
  });

  container.appendChild(svg);
  container.appendChild(readout);

  const actions = el("div", { style: "margin-top:6px" });
  actions.appendChild(exportButton(host, "export_figure_svg", "spectrum.svg", "svg", "Export figure (SVG)"));
  actions.appendChild(exportButton(host, "export_figure_png", "spectrum.png", "png", "PNG"));
  actions.appendChild(exportButton(host, "export_points_csv", "spectrum_points.csv", "csv", "Export points (CSV)"));
  container.appendChild(actions);
}

/* -------------------------------------------------------------------------
 * SpectralDataset (COMPOSITE) — index table + diagnostics + plot-mode stub.
 * ----------------------------------------------------------------------- */

function renderDataset(container, payload, host, diagnostics) {
  const slots = payload.slots && typeof payload.slots === "object" ? payload.slots : {};
  const indexTable = payload.index_table || {};
  const plotModes = Array.isArray(payload.plot_modes) ? payload.plot_modes : [];
  const datasetDiag = payload.diagnostics || {};

  container.appendChild(
    el("div", {
      style: "font:13px sans-serif;margin-bottom:4px;font-weight:600",
      text: `SpectralDataset — ${Object.keys(slots).length} slot(s)`,
    }),
  );

  // Plot-mode selector stub (FR-025): the modes the explorer can offer.
  if (plotModes.length) {
    const bar = el("div", { style: "font:12px sans-serif;margin:4px 0" }, "Plot mode: ");
    const select = el("select", { style: "font:12px sans-serif" });
    for (const mode of plotModes) select.appendChild(el("option", { value: mode, text: mode }));
    select.addEventListener("change", () => {
      try {
        host.session.patchQuery({ plot_mode: select.value });
      } catch (err) {
        host.reportError("plot mode change failed", { error: String(err) });
      }
    });
    bar.appendChild(select);
    container.appendChild(bar);
  }

  // Dataset health diagnostics panel (FR-027).
  const issues = Array.isArray(datasetDiag.issues) ? datasetDiag.issues : [];
  const diagMsgs = issues.map((i) => (i && i.code ? `${i.code}: ${JSON.stringify(i)}` : String(i)));
  const panel = diagnosticsPanel([...diagMsgs, ...(Array.isArray(diagnostics) ? diagnostics : [])]);
  if (panel) container.appendChild(panel);
  if (datasetDiag.ok) {
    container.appendChild(
      el("div", { style: "font:12px sans-serif;color:#2f9e44;margin:4px 0", text: "No dataset health issues detected." }),
    );
  }

  // Paginated index table (FR-023).
  const columns = Array.isArray(indexTable.columns) ? indexTable.columns : [];
  const rows = Array.isArray(indexTable.rows) ? indexTable.rows : [];
  if (indexTable.available && columns.length) {
    const table = el("table", {
      style: "font:12px sans-serif;border-collapse:collapse;margin-top:6px;width:100%",
    });
    const thead = el("tr", null);
    for (const col of columns) {
      const th = el("th", {
        style: "border:1px solid #ddd;padding:3px 6px;background:#f6f6f6;text-align:left;cursor:pointer",
        text: col,
      });
      th.addEventListener("click", () => {
        try {
          host.session.patchQuery({ sort_by: col, sort_dir: "asc" });
        } catch (err) {
          host.reportError("sort failed", { error: String(err) });
        }
      });
      thead.appendChild(th);
    }
    table.appendChild(thead);
    for (const row of rows) {
      const tr = el("tr", null);
      for (const col of columns) {
        tr.appendChild(
          el("td", { style: "border:1px solid #eee;padding:3px 6px" }, String(row && row[col] != null ? row[col] : "")),
        );
      }
      table.appendChild(tr);
    }
    container.appendChild(table);
    container.appendChild(
      el("div", {
        style: "font:11px sans-serif;color:#888;margin-top:2px",
        text: `index: showing ${rows.length} of ${indexTable.total_rows || rows.length} row(s) (page ${indexTable.page || 1})`,
      }),
    );
  } else {
    // Slot-inventory fallback when the index table is not bounded-readable.
    const list = el("ul", { style: "font:13px sans-serif;margin:6px 0;padding-left:18px" });
    for (const [name, type] of Object.entries(slots)) {
      const li = el("li", { style: "cursor:pointer", text: `${name}: ${type}` });
      li.addEventListener("click", () => {
        try {
          host.session.getResource(`slot:${name}`);
        } catch (err) {
          host.reportError(`failed to open slot ${name}`, { error: String(err) });
        }
      });
      list.appendChild(li);
    }
    container.appendChild(list);
  }

  const actions = el("div", { style: "margin-top:6px" });
  actions.appendChild(exportButton(host, "export_figure_svg", "dataset.svg", "svg", "Export figure (SVG)"));
  actions.appendChild(
    exportButton(host, "export_selected_rows_csv", "selected_rows.csv", "csv", "Export selected rows (CSV)"),
  );
  actions.appendChild(
    exportButton(host, "export_grouped_summary_csv", "grouped_summary.csv", "csv", "Export grouped summary (CSV)"),
  );
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
        if (kind === "series") {
          renderSpectrum(root, payload, host, diagnostics);
        } else if (kind === "composite") {
          renderDataset(root, payload, host, diagnostics);
        } else if (kind === "error") {
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
