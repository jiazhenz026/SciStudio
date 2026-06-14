// Spectroscopy previewer viewer (vanilla ESM, ADR-048 frontend contract).
//
// Minimal self-contained module: no npm, no framework. It reads everything
// through the constrained `host` API only and renders both the SERIES
// (Spectrum) and COMPOSITE (SpectralDataset) envelope kinds. If this module
// fails to load, the platform degrades to the core series/composite renderer.
//
// host API used: host.envelope.payload, host.kind, host.session.getResource,
// host.exportArtifact, host.reportError.

const API_VERSION = "1";

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "style") {
        node.setAttribute("style", value);
      } else if (key === "text") {
        node.textContent = value;
      } else {
        node.setAttribute(key, value);
      }
    }
  }
  for (const child of children) {
    if (child != null) node.appendChild(child);
  }
  return node;
}

function renderSpectrum(container, payload) {
  const points = Array.isArray(payload.points) ? payload.points : [];
  const total = payload.total != null ? payload.total : points.length;
  container.appendChild(
    el("div", { style: "font:13px sans-serif;margin-bottom:6px", text: `Spectrum — ${points.length} of ${total} points` }),
  );
  if (points.length === 0) {
    container.appendChild(el("div", { style: "color:#888", text: "no points to display" }));
    return;
  }
  const width = 600;
  const height = 220;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const xSpan = xMax - xMin || 1;
  const ySpan = yMax - yMin || 1;
  const path = points
    .map((p, i) => {
      const px = ((p.x - xMin) / xSpan) * (width - 20) + 10;
      const py = height - 10 - ((p.y - yMin) / ySpan) * (height - 20);
      return `${i === 0 ? "M" : "L"}${px.toFixed(2)},${py.toFixed(2)}`;
    })
    .join(" ");
  const svgNs = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNs, "svg");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const polyline = document.createElementNS(svgNs, "path");
  polyline.setAttribute("d", path);
  polyline.setAttribute("fill", "none");
  polyline.setAttribute("stroke", "#2b7de9");
  polyline.setAttribute("stroke-width", "1.5");
  svg.appendChild(polyline);
  container.appendChild(svg);
}

function renderDataset(container, payload, host) {
  const slots = payload.slots && typeof payload.slots === "object" ? payload.slots : {};
  const names = Object.keys(slots);
  container.appendChild(
    el("div", { style: "font:13px sans-serif;margin-bottom:6px", text: `SpectralDataset — ${names.length} slot(s)` }),
  );
  const list = el("ul", { style: "font:13px sans-serif;margin:0;padding-left:18px" });
  for (const name of names) {
    const li = el("li", { text: `${name}: ${slots[name]}` });
    li.style.cursor = "pointer";
    li.addEventListener("click", () => {
      try {
        host.session.getResource(`slot:${name}`);
      } catch (err) {
        host.reportError(`failed to open slot ${name}: ${err}`);
      }
    });
    list.appendChild(li);
  }
  container.appendChild(list);
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
      try {
        if (kind === "series") {
          renderSpectrum(root, payload);
        } else if (kind === "composite") {
          renderDataset(root, payload, host);
        } else if (kind === "error") {
          root.appendChild(el("div", { style: "color:#c0392b", text: "preview unavailable" }));
        } else {
          root.appendChild(el("div", { style: "color:#888", text: `unsupported kind: ${kind}` }));
        }
      } catch (err) {
        host.reportError(`spectroscopy viewer render failed: ${err}`);
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
