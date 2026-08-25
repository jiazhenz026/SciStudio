// The window the Review Labels block opens (core tutorial 2).
//
// This is the whole panel: one hand-written ES module, no framework and no
// build step. The host mounts it with `mount(container, host)`, hands it the
// JSON view the block's prepare_prompt built (`host.panelPayload`), and takes
// the decision back through `host.confirm({...})` / `host.cancel()`. The
// object shape it implements is the PanelModule contract from ADR-051.
//
// What it shows: one slide at a time. The micrograph is drawn underneath and
// the labels are washed over it in their own hues, so a reader asked to delete
// what is not a cell can see the cells; beside it, one row per label with its
// pixel area. Clicking a label in the picture or in the list marks it for
// removal on that slide, and marked labels are outlined in red so the decision
// is visible at a glance rather than only as a dimmer colour.
//
// Continue walks to the next slide the reader has not looked at yet, and only
// once every slide has been seen does it send the decision — closing on the
// first click would end the review with slides unexamined, which is exactly
// what a batch panel must not do. It sends `{ removed: [[ids], [ids], ...] }`,
// one list per slide in the order they arrived, which is what run() reads.
//
// **One window for the whole batch, not one window per slide.** A reader who
// loaded several micrographs is making one decision about their experiment,
// and pausing the run again for every image would ask them the same question
// over and over. So the panel carries the batch and the run resumes once.

const API_VERSION = "1";

/** A stable, distinct-enough color for one label id. */
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

/** How much of the label colour sits over the micrograph underneath. */
const LABEL_ALPHA = 0.45;

function drawGrid(canvas, grid, image, removed, suspects) {
  const rows = grid.length;
  const cols = rows ? grid[0].length : 0;
  if (!rows || !cols) return;
  const scale = Math.max(1, Math.floor(420 / Math.max(rows, cols)));
  canvas.width = cols * scale;
  canvas.height = rows * scale;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#111318";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // The micrograph first, in the green a fluorescence channel is shown in, so
  // the labels above it land on the cells they were found in.
  const hasImage = Array.isArray(image) && image.length === rows;
  if (hasImage) {
    for (let y = 0; y < rows; y += 1) {
      const row = image[y] || [];
      for (let x = 0; x < cols; x += 1) {
        const value = row[x] || 0;
        ctx.fillStyle = `rgb(${Math.round(value * 0.25)}, ${value}, ${Math.round(value * 0.45)})`;
        ctx.fillRect(x * scale, y * scale, scale, scale);
      }
    }
  }

  // Then the labels, translucent when there is a picture underneath to keep
  // visible, opaque when there is not.
  ctx.globalAlpha = hasImage ? LABEL_ALPHA : 1;
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      const id = grid[y][x];
      if (!id) continue;
      ctx.fillStyle = labelColor(id, removed.has(id));
      ctx.fillRect(x * scale, y * scale, scale, scale);
    }
  }
  ctx.globalAlpha = 1;

  outlineSuspects(ctx, grid, suspects, removed, scale);
}

/**
 * How much smaller than the typical object a label has to be before the panel
 * points at it. A quarter of the median: cells vary, debris does not come
 * close. Compared against the median rather than the mean so a single speck
 * cannot drag the threshold down towards itself.
 */
const SUSPECT_FRACTION = 0.25;

/**
 * The labels worth a second look: far too small to be a cell.
 *
 * The panel says which ones it doubts rather than waiting for the reader to
 * find them. That is the difference between a review and a search — the reader
 * is being asked to confirm or reject a judgement, and a judgement they cannot
 * see is not one they can reject. Every label stays clickable; the ring is a
 * suggestion, not a filter.
 */
function suspectLabels(labels) {
  const areas = labels.map((label) => label.area).sort((a, b) => a - b);
  if (areas.length < 2) return new Set();
  const middle = areas.length % 2 ? areas[(areas.length - 1) / 2] : (areas[areas.length / 2 - 1] + areas[areas.length / 2]) / 2;
  const cutoff = middle * SUSPECT_FRACTION;
  return new Set(labels.filter((label) => label.area < cutoff).map((label) => label.id));
}

/**
 * Ring the labels the panel doubts, in red, until the reader has dealt with them.
 *
 * The ring is the ask: it marks what the panel thinks is not a cell so the
 * reader knows where to click. It goes away once that label is marked for
 * removal, because the question has been answered — a ring that stayed would
 * be pointing at a decision already made.
 *
 * Drawn as the bounding box of the label's pixels rather than traced around
 * its edge: the shape is visible underneath, and a box reads as a mark *on*
 * something rather than as another outline of it.
 */
function outlineSuspects(ctx, grid, suspects, removed, scale) {
  const pending = [...suspects].filter((id) => !removed.has(id));
  if (pending.length === 0) return;
  const wanted = new Set(pending);
  const rows = grid.length;
  const cols = rows ? grid[0].length : 0;
  const bounds = new Map();
  for (let y = 0; y < rows; y += 1) {
    for (let x = 0; x < cols; x += 1) {
      const id = grid[y][x];
      if (!id || !wanted.has(id)) continue;
      const box = bounds.get(id);
      if (!box) bounds.set(id, { top: y, left: x, bottom: y, right: x });
      else {
        if (y < box.top) box.top = y;
        if (y > box.bottom) box.bottom = y;
        if (x < box.left) box.left = x;
        if (x > box.right) box.right = x;
      }
    }
  }
  ctx.strokeStyle = "#ef4444";
  ctx.lineWidth = 2;
  // Wide enough that the ring sits clear of a small object rather than on it.
  const pad = Math.max(4, scale);
  for (const box of bounds.values()) {
    ctx.strokeRect(
      box.left * scale - pad,
      box.top * scale - pad,
      (box.right - box.left + 1) * scale + 2 * pad,
      (box.bottom - box.top + 1) * scale + 2 * pad,
    );
  }
}

/**
 * Read the payload as a list of slides.
 *
 * The single-slide shape is accepted too, because a block that reviews one
 * image is still an ordinary case and a payload written by hand says so.
 */
function slidesOf(payload) {
  if (Array.isArray(payload.slides)) return payload.slides;
  if (Array.isArray(payload.grid)) return [payload];
  return [];
}

export default {
  apiVersion: API_VERSION,

  mount(container, host) {
    const payload = host.panelPayload || {};
    const slides = slidesOf(payload).map((slide) => {
      const labels = Array.isArray(slide.labels) ? slide.labels : [];
      return {
        grid: Array.isArray(slide.grid) ? slide.grid : [],
        image: Array.isArray(slide.image) ? slide.image : null,
        labels,
        removed: new Set(),
        // Computed once: the areas do not change while the panel is open, so
        // neither does which of them the panel doubts.
        suspects: suspectLabels(labels),
      };
    });
    if (slides.length === 0) {
      slides.push({ grid: [], image: null, labels: [], removed: new Set(), suspects: new Set() });
    }
    let current = 0;
    // Which slides the reader has actually had in front of them. Continue
    // walks through what is left of this before it ends the review.
    const seen = new Set([0]);

    const root = el(
      "div",
      "display:flex;gap:16px;padding:16px;font-family:system-ui,sans-serif;color:#1c1917;align-items:flex-start;",
    );

    const left = el("div", "flex:0 0 auto;");
    left.appendChild(
      el("div", "font-weight:600;margin-bottom:8px;", "Click anything that is not a cell."),
    );
    const canvas = el("canvas", "border-radius:8px;display:block;cursor:crosshair;");
    left.appendChild(canvas);

    // The slide strip. Present whatever the batch size, so a reader never has
    // to work out whether there is more than one image in front of them.
    const strip = el("div", "display:flex;align-items:center;gap:8px;margin-top:10px;");
    const previous = el(
      "button",
      "padding:4px 10px;border-radius:6px;border:1px solid #d6d3d1;background:#fff;cursor:pointer;",
      "‹ Previous",
    );
    const position = el("div", "flex:1 1 auto;text-align:center;color:#57534e;font-size:13px;");
    const next = el(
      "button",
      "padding:4px 10px;border-radius:6px;border:1px solid #d6d3d1;background:#fff;cursor:pointer;",
      "Next image ›",
    );
    strip.appendChild(previous);
    strip.appendChild(position);
    strip.appendChild(next);
    left.appendChild(strip);
    root.appendChild(left);

    const right = el("div", "flex:1 1 auto;min-width:220px;");
    const heading = el("div", "font-weight:600;margin-bottom:8px;");
    right.appendChild(heading);
    const list = el(
      "div",
      "display:flex;flex-direction:column;gap:4px;max-height:360px;overflow:auto;",
    );
    right.appendChild(list);

    const buttons = el("div", "display:flex;gap:8px;margin-top:12px;");
    const confirm = el(
      "button",
      "padding:6px 16px;border-radius:8px;border:1px solid #1c1917;background:#1c1917;color:#fff;cursor:pointer;",
      "Continue",
    );
    const cancel = el(
      "button",
      "padding:6px 16px;border-radius:8px;border:1px solid #d6d3d1;background:#fff;cursor:pointer;",
      "Cancel",
    );
    buttons.appendChild(confirm);
    buttons.appendChild(cancel);
    right.appendChild(buttons);
    root.appendChild(right);

    function totalRemoved() {
      return slides.reduce((sum, slide) => sum + slide.removed.size, 0);
    }

    /** Rebuild the label list for the slide on screen. */
    function fillList() {
      const slide = slides[current];
      list.replaceChildren();
      for (const label of slide.labels) {
        const gone = slide.removed.has(label.id);
        const row = el(
          "div",
          "display:flex;align-items:center;gap:8px;padding:4px 8px;border-radius:6px;cursor:pointer;border:1px solid #e7e5e4;",
        );
        row.style.opacity = gone ? "0.45" : "1";
        row.style.textDecoration = gone ? "line-through" : "none";
        const swatch = el("i", "width:12px;height:12px;border-radius:3px;flex:0 0 auto;");
        swatch.style.background = labelColor(label.id, gone);
        row.appendChild(swatch);
        row.appendChild(el("span", "flex:1 1 auto;", `label ${label.id}`));
        row.appendChild(el("span", "color:#78716c;", `${label.area} px`));
        row.addEventListener("click", () => toggle(label.id));
        list.appendChild(row);
      }
    }

    /** The first slide the reader has not looked at, or ``null`` if none is left. */
    function nextUnseen() {
      for (let index = 0; index < slides.length; index += 1) {
        if (!seen.has(index)) return index;
      }
      return null;
    }

    function refresh() {
      const slide = slides[current];
      drawGrid(canvas, slide.grid, slide.image, slide.removed, slide.suspects);
      heading.textContent = `${slide.labels.length} labels`;
      position.textContent =
        slides.length > 1 ? `Image ${current + 1} of ${slides.length}` : "One image";
      previous.disabled = current === 0;
      next.disabled = current === slides.length - 1;
      for (const button of [previous, next]) button.style.opacity = button.disabled ? "0.4" : "1";
      const count = totalRemoved();
      const pending = nextUnseen();
      // The button says which of its two jobs it is about to do. Ending the
      // review while a slide has never been on screen is the one outcome this
      // panel exists to prevent, so Continue walks there first and only
      // finishes once nothing is left unseen.
      // Still "Continue" while there is more to see, because it is the same
      // button doing the same job — the count is what says it will not finish
      // yet. Naming it "Next image" would collide with the slide strip's own
      // next button sitting a few pixels away.
      confirm.textContent =
        pending === null
          ? count
            ? `Continue (remove ${count})`
            : "Continue (keep all)"
          : `Continue (${slides.length - seen.size} image${slides.length - seen.size === 1 ? "" : "s"} left)`;
      fillList();
    }

    function toggle(id) {
      const { removed } = slides[current];
      if (removed.has(id)) removed.delete(id);
      else removed.add(id);
      refresh();
    }

    function show(index) {
      current = Math.min(Math.max(index, 0), slides.length - 1);
      seen.add(current);
      refresh();
    }

    previous.addEventListener("click", () => show(current - 1));
    next.addEventListener("click", () => show(current + 1));

    canvas.addEventListener("click", (event) => {
      const { grid } = slides[current];
      const rows = grid.length;
      const cols = rows ? grid[0].length : 0;
      if (!rows || !cols) return;
      const bounds = canvas.getBoundingClientRect();
      const x = Math.floor(((event.clientX - bounds.left) / bounds.width) * cols);
      const y = Math.floor(((event.clientY - bounds.top) / bounds.height) * rows);
      const row = grid[Math.min(y, rows - 1)];
      const id = row ? row[Math.min(x, cols - 1)] : 0;
      if (id) toggle(id);
    });

    confirm.addEventListener("click", () => {
      const pending = nextUnseen();
      if (pending !== null) {
        show(pending);
        return;
      }
      host.confirm({
        removed: slides.map((slide) => Array.from(slide.removed).sort((a, b) => a - b)),
      });
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
