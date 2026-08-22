// The window the Review Labels block opens (core tutorial 2).
//
// This is the whole panel: one hand-written ES module, no framework and no
// build step. The host mounts it with `mount(container, host)`, hands it the
// JSON view the block's prepare_prompt built (`host.panelPayload`), and takes
// the decision back through `host.confirm({...})` / `host.cancel()`. The
// object shape it implements is the PanelModule contract from ADR-051.
//
// What it shows: the label map as a coloured grid (0 = background, each label
// its own hue) beside one row per label with its pixel area. Clicking a label
// in the picture or in the list marks it for removal; Apply sends
// `{ removed: [ids] }`, which is exactly what the block's run() reads.

const API_VERSION = "1";

/** A stable, distinct-enough colour for one label id. */
function labelColor(id, removed) {
  const hue = (id * 137) % 360;
  const light = removed ? "28%" : "60%";
  return `hsl(${hue} 75% ${light})`;
}

function el(tag, style, text) {
  const node = document.createElement(tag);
  if (style) node.style.cssText = style;
  if (text !== undefined) node.textContent = text;
  return node;
}

function drawGrid(canvas, grid, removed) {
  const rows = grid.length;
  const cols = rows ? grid[0].length : 0;
  if (!rows || !cols) return;
  const scale = Math.max(1, Math.floor(420 / Math.max(rows, cols)));
  canvas.width = cols * scale;
  canvas.height = rows * scale;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#111318";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      const id = grid[y][x];
      if (!id) continue;
      ctx.fillStyle = labelColor(id, removed.has(id));
      ctx.fillRect(x * scale, y * scale, scale, scale);
    }
  }
}

export default {
  apiVersion: API_VERSION,

  mount(container, host) {
    const payload = host.panelPayload || {};
    const grid = Array.isArray(payload.grid) ? payload.grid : [];
    const labels = Array.isArray(payload.labels) ? payload.labels : [];
    const removed = new Set();

    const root = el(
      "div",
      "display:flex;gap:16px;padding:16px;font-family:system-ui,sans-serif;color:#1c1917;align-items:flex-start;",
    );

    const left = el("div", "flex:0 0 auto;");
    left.appendChild(
      el("div", "font-weight:600;margin-bottom:8px;", "Click anything that is not a cell, then press Apply."),
    );
    const canvas = el("canvas", "border-radius:8px;display:block;cursor:crosshair;");
    left.appendChild(canvas);
    root.appendChild(left);

    const right = el("div", "flex:1 1 auto;min-width:220px;");
    right.appendChild(el("div", "font-weight:600;margin-bottom:8px;", `${labels.length} labels`));
    const list = el("div", "display:flex;flex-direction:column;gap:4px;max-height:360px;overflow:auto;");
    right.appendChild(list);

    const buttons = el("div", "display:flex;gap:8px;margin-top:12px;");
    const apply = el(
      "button",
      "padding:6px 16px;border-radius:8px;border:1px solid #1c1917;background:#1c1917;color:#fff;cursor:pointer;",
      "Apply",
    );
    const cancel = el(
      "button",
      "padding:6px 16px;border-radius:8px;border:1px solid #d6d3d1;background:#fff;cursor:pointer;",
      "Cancel",
    );
    buttons.appendChild(apply);
    buttons.appendChild(cancel);
    right.appendChild(buttons);
    root.appendChild(right);

    const rowsById = new Map();

    function refresh() {
      drawGrid(canvas, grid, removed);
      for (const [id, row] of rowsById) {
        const gone = removed.has(id);
        row.style.opacity = gone ? "0.45" : "1";
        row.style.textDecoration = gone ? "line-through" : "none";
        row.querySelector("i").style.background = labelColor(id, gone);
      }
      apply.textContent = removed.size ? `Apply (remove ${removed.size})` : "Apply (keep all)";
    }

    function toggle(id) {
      if (removed.has(id)) removed.delete(id);
      else removed.add(id);
      refresh();
    }

    for (const label of labels) {
      const row = el(
        "div",
        "display:flex;align-items:center;gap:8px;padding:4px 8px;border-radius:6px;cursor:pointer;border:1px solid #e7e5e4;",
      );
      const swatch = el("i", "width:12px;height:12px;border-radius:3px;flex:0 0 auto;");
      row.appendChild(swatch);
      row.appendChild(el("span", "flex:1 1 auto;", `label ${label.id}`));
      row.appendChild(el("span", "color:#78716c;", `${label.area} px`));
      row.addEventListener("click", () => toggle(label.id));
      rowsById.set(label.id, row);
      list.appendChild(row);
    }

    canvas.addEventListener("click", (event) => {
      const rows = grid.length;
      const cols = rows ? grid[0].length : 0;
      if (!rows || !cols) return;
      const bounds = canvas.getBoundingClientRect();
      const x = Math.floor(((event.clientX - bounds.left) / bounds.width) * cols);
      const y = Math.floor(((event.clientY - bounds.top) / bounds.height) * rows);
      const id = grid[Math.min(y, rows - 1)] ? grid[Math.min(y, rows - 1)][Math.min(x, cols - 1)] : 0;
      if (id) toggle(id);
    });

    apply.addEventListener("click", () => {
      host.confirm({ removed: Array.from(removed).sort((a, b) => a - b) });
    });
    cancel.addEventListener("click", () => host.cancel());

    refresh();
    container.appendChild(root);

    return {
      unmount() {
        root.remove();
      },
    };
  },
};
