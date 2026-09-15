/* core.array.basic — bounded numeric inspection of an Array.
 *
 * Built with Preact and the shared panel component set, so it looks like the
 * rest of the application without restating its styling. The surface matches the
 * viewer it replaces: a numeric heatmap table of the ACTUAL values with per-cell
 * colour, sticky row/column headers, a min..max legend, and one index control per
 * non-displayed axis.
 *
 * Faithful display (#1886 A/E): the cells are the array's REAL values, read at
 * native resolution through array.tile and virtualized (spacer rows and padding
 * cells) so scrolling a large plane moves through real data instead of a
 * decimated stand-in. vmin/vmax come from the backend's full-plane extent.
 * NaN / +-inf arrive as sentinel strings and render as NaN / ∞ / -∞, never blank.
 */
import {
  html,
  render,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";
import {
  Card,
  ErrorState,
  Field,
  Input,
  Legend,
  LoadingState,
  Meta,
  Panel,
  ScrollArea,
  Table,
} from "../../sdk/1/panel-ui.js";

const api = window.scistudio;

const VIEWPORT = 320; // the scroll surface's max height, from panel.css
const OVERSCAN = 8; // rows/columns kept beyond the viewport
const COL_W = 44; // fixed column width, mirrored by panel.css
const ROW_H = 19; // row height before one is measured
const TILE_CAP = 256; // per-read tile bound; the backend caps it too

// ---- value formatting and colour (the viewer's exact behaviour) -------------

const SENTINELS = { NaN: "NaN", Infinity: "∞", "-Infinity": "-∞" };

function numeric(v) {
  return typeof v === "number" && isFinite(v) ? v : null;
}
export function formatCell(v) {
  if (v in SENTINELS) return SENTINELS[v];
  if (v === null || v === undefined) return "—";
  if (typeof v !== "number") return String(v);
  if (!isFinite(v)) return Number.isNaN(v) ? "NaN" : v > 0 ? "∞" : "-∞";
  if (v === 0) return "0";
  const abs = Math.abs(v);
  if (Number.isInteger(v) && abs < 1e6) return String(v);
  if (abs >= 1e5 || abs < 1e-3) return v.toExponential(2);
  return v.toFixed(3);
}
const lerp = (a, b, t) => Math.round(a + (b - a) * t);
export function heatmapColor(v, vmin, vmax) {
  const n = numeric(v);
  if (n === null || typeof vmin !== "number" || typeof vmax !== "number") return "transparent";
  if (vmin < 0 && vmax > 0) {
    // Diverging, centred at 0 so negatives stay distinct.
    const mag = Math.max(Math.abs(vmin), Math.abs(vmax)) || 1;
    const t = Math.max(-1, Math.min(1, n / mag));
    if (t < 0) {
      const k = -t;
      return `rgb(${lerp(247, 33, k)}, ${lerp(247, 102, k)}, ${lerp(247, 172, k)})`;
    }
    return `rgb(${lerp(247, 178, t)}, ${lerp(247, 24, t)}, ${lerp(247, 43, t)})`;
  }
  const span = vmax - vmin || 1;
  const s = Math.max(0, Math.min(1, (n - vmin) / span));
  return `rgb(${lerp(247, 8, s)}, ${lerp(252, 64, s)}, ${lerp(253, 129, s)})`;
}
function cellTextColor(v, vmin, vmax) {
  const n = numeric(v);
  if (n === null) return "rgb(var(--ink) / 0.4)";
  const mag =
    vmin < 0 && vmax > 0 ? Math.max(Math.abs(vmin), Math.abs(vmax)) || 1 : vmax - vmin || 1;
  const intensity = vmin < 0 && vmax > 0 ? Math.abs(n) / mag : (n - vmin) / mag;
  return intensity > 0.6 ? "#fffdf8" : "rgb(var(--ink))";
}

/** Resolve which axes are displayed as rows/columns. */
export function displayAxes(shape, axes, sliceAxes) {
  const sliced = new Set((sliceAxes || []).map((a) => a.axis));
  const remaining = shape.map((_, i) => i).filter((i) => !sliced.has(i));
  if (axes && axes.includes("y") && axes.includes("x")) {
    return { y: axes.indexOf("y"), x: axes.indexOf("x") };
  }
  if (remaining.length >= 2) {
    return { y: remaining[remaining.length - 2], x: remaining[remaining.length - 1] };
  }
  if (remaining.length === 1) return { y: remaining[0], x: remaining[0] };
  return { y: 0, x: 0 };
}

/**
 * Plane geometry, following the backend's selection: a 0-D or 1-D source has a
 * single row (a 1-D array is one row of N columns), so rows are never derived
 * from shape[y] for those.
 */
function planeMeta(plane) {
  const shape = plane.source_shape || plane.shape || [];
  const da = displayAxes(shape, plane.axes || [], plane.slice_axes || []);
  const displayed = shape.length - (plane.slice_axes || []).length;
  const twoD = displayed >= 2;
  return {
    shape,
    dtype: plane.source_dtype || plane.dtype || "?",
    axes: plane.axes || [],
    vmin: typeof plane.vmin === "number" ? plane.vmin : null,
    vmax: typeof plane.vmax === "number" ? plane.vmax : null,
    rows: twoD ? shape[da.y] || 1 : 1,
    cols: shape.length ? shape[da.x] || 1 : 1,
    scalar: shape.length === 0,
  };
}

// ---- components -------------------------------------------------------------

/**
 * One index control per non-displayed axis. The handle runs on a normalised
 * 0..1 track so it moves continuously with the pointer rather than snapping
 * between index stops; the index it resolves to loads live, and releasing snaps
 * the handle onto that index.
 */
/**
 * Fill in every non-displayed axis, from the reader's choices and the read's echo.
 *
 * The backend defaults the first non-displayed axis from ``slice_index`` when
 * ``axis_indices`` omits it, so an omission is not "leave it alone" — it is
 * "put it wherever the other slider is".
 */
export function resolveAxisIndices(sliceAxes, chosen) {
  const resolved = {};
  for (const axis of sliceAxes || []) {
    const picked = (chosen || {})[axis.axis];
    resolved[axis.axis] = typeof picked === "number" ? picked : axis.index;
  }
  return resolved;
}

/**
 * The first non-displayed axis's selection, in the backend's own axis order.
 *
 * ``Object.keys`` order is not that order once an axis is missing, and this is
 * the value the backend applies when it has to default one.
 */
export function firstAxisIndex(sliceAxes, resolved) {
  const first = (sliceAxes || [])[0];
  if (!first) return 0;
  const picked = (resolved || {})[first.axis];
  return typeof picked === "number" ? picked : first.index;
}

/**
 * Run one job at a time, keeping only the latest of those that arrive meanwhile.
 *
 * A range input emits an event per pointer move and each plane read is
 * expensive, so a drag must not become a queue of reads for positions the
 * pointer has already left. A failed job releases the queue like a successful
 * one: a read that errors must not freeze every later move.
 */
export function coalescingQueue(run) {
  let busy = false;
  let queued = null;
  const start = (value) => {
    busy = true;
    // Started now, not on the next microtask: the first move of a drag should
    // reach the reader immediately, and only what follows it needs collapsing.
    let running;
    try {
      running = run(value);
    } catch {
      running = undefined;
    }
    Promise.resolve(running)
      .then(
        () => undefined,
        () => undefined,
      )
      .then(() => {
        const next = queued;
        queued = null;
        if (next !== null) start(next);
        else busy = false;
      });
  };
  return (value) => {
    if (busy) {
      queued = value;
      return;
    }
    start(value);
  };
}

function SliceAxes({ sliceAxes, indices, onChange }) {
  // While the pointer is down the handle is left alone: re-rendering with the
  // committed index as its value would yank it to the snapped position for a
  // frame, and it would only return to the pointer on the next move. The handle
  // is synchronised to the index when the gesture ends and on outside changes.
  const dragging = useRef(new Set());
  const handles = useRef({});
  const frac = useCallback((idx, last) => (last > 0 ? idx / last : 0), []);

  useLayoutEffect(() => {
    for (const ax of sliceAxes) {
      const node = handles.current[ax.axis];
      if (!node || dragging.current.has(ax.axis)) continue;
      const last = Math.max(0, ax.size - 1);
      const next = String(frac(indices[ax.axis] ?? ax.index, last));
      if (node.value !== next) node.value = next;
    }
  }, [sliceAxes, indices, frac]);

  if (!sliceAxes.length) return null;
  return html`<div data-testid="array-slice-selectors">
    ${sliceAxes.map((ax) => {
      const last = Math.max(0, ax.size - 1);
      const value = indices[ax.axis] ?? ax.index;
      const clamp = (raw) => Math.max(0, Math.min(Math.round(isFinite(raw) ? raw : 0), last));
      const fromFrac = (f) => clamp((isFinite(f) ? f : 0) * last);
      const endDrag = (e) => {
        dragging.current.delete(ax.axis);
        // Snap the handle onto the index it committed to.
        const idx = fromFrac(parseFloat(e.currentTarget.value));
        e.currentTarget.value = String(frac(idx, last));
        onChange(ax.axis, idx);
      };
      return html`<${Field}
        key=${ax.axis}
        name=${`${ax.name} (${ax.size})`}
        readout=${`${value} / ${last}`}
        data-testid=${`array-slice-row-${ax.axis}`}
      >
        <${Input}
          class="panel-field-range"
          type="range"
          min="0"
          max="1"
          step="0.0001"
          elementRef=${(node) => {
            if (node) {
              handles.current[ax.axis] = node;
              // Uncontrolled: set the starting position once, then leave it to
              // the pointer and the layout effect above.
              if (node.dataset.init !== "1") {
                node.value = String(frac(value, last));
                node.dataset.init = "1";
              }
            }
          }}
          aria-label=${`Slice along ${ax.name}`}
          data-testid=${`array-slice-slider-${ax.axis}`}
          onPointerDown=${() => dragging.current.add(ax.axis)}
          onInput=${(e) => onChange(ax.axis, fromFrac(parseFloat(e.target.value)))}
          onPointerUp=${endDrag}
          onPointerCancel=${endDrag}
          onChange=${endDrag}
        />
        <${Input}
          number
          type="number"
          min="0"
          max=${last}
          value=${value}
          aria-label=${`Index along ${ax.name}`}
          data-testid=${`array-slice-input-${ax.axis}`}
          onInput=${(e) => onChange(ax.axis, clamp(parseFloat(e.target.value)))}
        />
      <//>`;
    })}
  </div>`;
}

/**
 * The numeric heatmap. Only the visible window is in the DOM: rows outside it
 * become two spacer rows of exactly their height and columns outside the loaded
 * band become padding cells of exactly their width, so both scrollbars describe
 * the whole plane while the cells on screen are real values.
 */
function HeatmapTable({ meta, tile, rowHeight, onScroll, scrollRef }) {
  const values = tile?.values ?? [];
  const y0 = typeof tile?.y0 === "number" ? tile.y0 : 0;
  const x0 = typeof tile?.x0 === "number" ? tile.x0 : 0;
  const wCols = values[0]?.length ?? 0;
  const yEnd = y0 + values.length;
  const xEnd = x0 + wCols;
  const leftPad = x0 * COL_W;
  const rightPad = Math.max(0, meta.cols - xEnd) * COL_W;
  const pad = (w) => html`<td class="panel-table-pad" style=${`min-width:${w}px`}></td>`;
  const padHead = (w) => html`<th class="panel-table-pad" style=${`min-width:${w}px`}></th>`;

  return html`<${ScrollArea}
    data-testid="array-2d-heatmap"
    tabindex="0"
    elementRef=${scrollRef}
    onScroll=${onScroll}
  >
    <${Table} data-testid="array-heatmap">
      <thead>
        <tr>
          <th class="panel-table-corner"></th>
          ${leftPad ? padHead(leftPad) : null}
          ${values[0]?.map((_, c) => html`<th key=${c}>${x0 + c}</th>`)}
          ${rightPad ? padHead(rightPad) : null}
        </tr>
      </thead>
      <tbody>
        ${y0 > 0 ? html`<tr aria-hidden="true" style=${`height:${y0 * rowHeight}px`}></tr>` : null}
        ${values.map(
          (row, r) => html`<tr key=${y0 + r} data-row=${y0 + r}>
            <th>${y0 + r}</th>
            ${leftPad ? pad(leftPad) : null}
            ${row.map((v, c) => {
              const nonFinite = numeric(v) === null;
              return html`<td
                key=${c}
                data-testid=${`array-cell-${y0 + r}-${x0 + c}`}
                title=${nonFinite ? "non-finite" : String(v)}
                class=${nonFinite ? "panel-table-nonfinite" : undefined}
                style=${`background:${heatmapColor(v, meta.vmin, meta.vmax)};color:${cellTextColor(v, meta.vmin, meta.vmax)}`}
              >${formatCell(v)}</td>`;
            })}
            ${rightPad ? pad(rightPad) : null}
          </tr>`,
        )}
        ${yEnd < meta.rows
          ? html`<tr aria-hidden="true" style=${`height:${(meta.rows - yEnd) * rowHeight}px`}></tr>`
          : null}
      </tbody>
    <//>
  <//>`;
}

function ValueLegend({ meta }) {
  if (typeof meta.vmin !== "number" || typeof meta.vmax !== "number") {
    return html`<div class="panel-legend" data-testid="array-legend">no finite values</div>`;
  }
  const stops = Array.from({ length: 9 }, (_, i) =>
    heatmapColor(meta.vmin + ((meta.vmax - meta.vmin) * i) / 8, meta.vmin, meta.vmax),
  );
  const mid = meta.vmin < 0 && meta.vmax > 0 ? 0 : (meta.vmin + meta.vmax) / 2;
  return html`<${Legend}
    data-testid="array-legend"
    min=${html`<span data-testid="array-legend-min">${formatCell(meta.vmin)}</span>`}
    mid=${html`<span data-testid="array-legend-mid">${formatCell(mid)}</span>`}
    max=${html`<span data-testid="array-legend-max">${formatCell(meta.vmax)}</span>`}
    stops=${stops}
  />`;
}

function ArrayPanel({ initialView }) {
  const [plane, setPlane] = useState(null);
  const [tile, setTile] = useState(null);
  const [error, setError] = useState(null);
  // A failed read is shown here AND reported to the host: the surrounding
  // preview shell offers the remount / core-preview recovery on that signal.
  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);
  const [indices, setIndices] = useState(initialView.axis_indices || {});
  const [rowHeight, setRowHeight] = useState(ROW_H);

  const scrollRef = useRef(null);
  const scrollPos = useRef({ top: initialView.scrollTop || 0, left: initialView.scrollLeft || 0 });
  // A tile read is cheap and scroll-driven, so only the newest response is
  // applied. A plane read is not; see `readPlane` for why it is serialised.
  const tileReq = useRef(0);

  const meta = useMemo(() => (plane ? planeMeta(plane) : null), [plane]);
  const sliceAxes = plane?.slice_axes ?? [];
  // The queue outlives any one render, so the axis order it resolves against is
  // read through a ref rather than captured when the queue was built.
  const sliceAxesRef = useRef(sliceAxes);
  sliceAxesRef.current = sliceAxes;
  /*
   * Every non-displayed axis, with the reader's choice where they made one and
   * the read's own echo where they did not. Sending a partial set left the
   * backend to fill the first non-displayed axis from `slice_index`, so moving
   * any *other* axis moved that one to the same position and showed a different
   * plane — real values from somewhere the reader had not asked for.
   */
  const axisIndices = useMemo(() => resolveAxisIndices(sliceAxes, indices), [sliceAxes, indices]);
  const firstIndex = useMemo(() => firstAxisIndex(sliceAxes, axisIndices), [sliceAxes, axisIndices]);

  /*
   * One plane read at a time, and only the latest position still wanted.
   *
   * Reading a plane is not cheap: the backend scans it to find the real extrema
   * for the legend, which for a large array is the whole plane. A range input
   * emits an event per pointer move, so a read per event put dozens of
   * whole-plane scans in flight at once — enough to saturate the reader and, on
   * a large enough array, to exhaust memory. Dropping stale *responses* did not
   * help: the work had already been started.
   */
  const planeQueue = useRef(null);
  const readPlane = useCallback(
    (selection) => {
      if (!planeQueue.current) {
        planeQueue.current = coalescingQueue((wanted) =>
          api
            .read("array.plane", {
              slice_index: firstAxisIndex(sliceAxesRef.current, wanted),
              axis_indices: wanted,
            })
            .then(
              (p) => {
                setPlane(p);
                setError(null);
              },
              (err) => fail(err),
            ),
        );
      }
      planeQueue.current(selection);
    },
    [fail],
  );

  const readTile = useCallback(() => {
    if (!meta || meta.scalar) return;
    const box = scrollRef.current;
    const maxRow = Math.max(0, meta.rows - 1);
    const maxCol = Math.max(0, meta.cols - 1);
    const firstRow = Math.max(
      0,
      Math.min(Math.floor(scrollPos.current.top / rowHeight) - OVERSCAN, maxRow),
    );
    const firstCol = Math.max(
      0,
      Math.min(Math.floor(scrollPos.current.left / COL_W) - OVERSCAN, maxCol),
    );
    const visRows = Math.ceil((box?.clientHeight || VIEWPORT) / rowHeight) + 2 * OVERSCAN;
    const visCols = Math.ceil((box?.clientWidth || 480) / COL_W) + 2 * OVERSCAN;
    const height = Math.max(1, Math.min(TILE_CAP, visRows, meta.rows - firstRow));
    const width = Math.max(1, Math.min(TILE_CAP, visCols, meta.cols - firstCol));
    const req = ++tileReq.current;
    api
      .read("array.tile", {
        y0: firstRow,
        x0: firstCol,
        height,
        width,
        slice_index: firstIndex,
        axis_indices: indices,
      })
      .then((t) => {
        if (req === tileReq.current) setTile(t);
      })
      .catch((err) => {
        if (req === tileReq.current) fail(err);
      });
  }, [meta, rowHeight, firstIndex, indices, fail]);

  // First read, and a re-read whenever the selected slice changes.
  useEffect(() => {
    readPlane(axisIndices);
  }, [indices, readPlane]);

  // The plane defines the geometry; load the window it exposes. A 0-D source has
  // exactly one cell, so read that instead of a window.
  useEffect(() => {
    if (!meta) return;
    if (meta.scalar) {
      const req = ++tileReq.current;
      api
        .read("array.tile", { y0: 0, x0: 0, height: 1, width: 1, slice_index: firstIndex, axis_indices: axisIndices })
        .then((t) => {
          if (req === tileReq.current) setTile(t);
        })
        .catch((err) => {
          if (req === tileReq.current) fail(err);
        });
      return;
    }
    readTile();
  }, [meta]); // eslint-disable-line react-hooks/exhaustive-deps

  // Measure a real row once so the spacer heights match the rendered rows.
  useLayoutEffect(() => {
    const row = scrollRef.current?.querySelector("tbody tr[data-row]");
    const measured = row instanceof HTMLElement ? row.offsetHeight : 0;
    if (measured > 0 && measured !== rowHeight) setRowHeight(measured);
  }, [tile, rowHeight]);

  // Restore the scroll offset after the geometry is known.
  useLayoutEffect(() => {
    const box = scrollRef.current;
    if (!box) return;
    if (box.scrollTop !== scrollPos.current.top) box.scrollTop = scrollPos.current.top;
    if (box.scrollLeft !== scrollPos.current.left) box.scrollLeft = scrollPos.current.left;
  }, [meta]);

  useEffect(() => {
    api.setViewState({
      axis_indices: indices,
      scrollTop: scrollPos.current.top,
      scrollLeft: scrollPos.current.left,
    });
  }, [indices, tile]);

  const onScroll = useCallback(
    (e) => {
      scrollPos.current = { top: e.currentTarget.scrollTop, left: e.currentTarget.scrollLeft };
      readTile();
    },
    [readTile],
  );

  const onSliceChange = useCallback((axis, index) => {
    scrollPos.current = { top: 0, left: 0 };
    setIndices((prev) => (prev[axis] === index ? prev : { ...prev, [axis]: index }));
  }, []);

  if (error) {
    return html`<${Panel}><${ErrorState}>Could not read array: ${error}<//><//>`;
  }
  // Reading a large array takes a moment; say so rather than showing an empty
  // surface until the first plane lands.
  if (!meta) {
    return html`<${Panel}><${LoadingState} data-testid="array-loading">Loading array…<//><//>`;
  }

  const items = ["Array", `shape [${meta.shape.join(", ")}]`, `dtype ${meta.dtype}`];
  if (meta.axes.length) items.push(`axes [${meta.axes.join(", ")}]`);

  return html`<${Panel}>
    <${Meta} items=${items} data-testid="array-info" />
    <${SliceAxes} sliceAxes=${sliceAxes} indices=${indices} onChange=${onSliceChange} />
    ${meta.scalar
      ? html`<${Card} data-testid="array-scalar">
          ${formatCell(tile?.values?.[0]?.[0] ?? "")}
        <//>`
      : html`
          <${HeatmapTable}
            meta=${meta}
            tile=${tile}
            rowHeight=${rowHeight}
            onScroll=${onScroll}
            scrollRef=${scrollRef}
          />
          <${ValueLegend} meta=${meta} />
          <div class="panel-hint" data-testid="array-grid-info">
            ${meta.shape.length ? `${meta.shape.join(" × ")} | ` : ""}displaying ${meta.rows} × ${meta.cols}
          </div>
        `}
  <//>`;
}

api
  .ready()
  .then(() => {
    const view = api.viewState && typeof api.viewState === "object" ? api.viewState : {};
    render(html`<${ArrayPanel} initialView=${view} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));

window.__panel = { formatCell, heatmapColor, displayAxes };
