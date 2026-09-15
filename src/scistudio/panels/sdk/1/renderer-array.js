/* Reusable core presentation. Host reads and persistence stay in the caller. */
import {
  html,
  useCallback,
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
} from "./panel-ui.js";

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
  if (n === null || typeof vmin !== "number" || typeof vmax !== "number")
    return "transparent";
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
    vmin < 0 && vmax > 0
      ? Math.max(Math.abs(vmin), Math.abs(vmax)) || 1
      : vmax - vmin || 1;
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
    return {
      y: remaining[remaining.length - 2],
      x: remaining[remaining.length - 1],
    };
  }
  if (remaining.length === 1) return { y: remaining[0], x: remaining[0] };
  return { y: 0, x: 0 };
}

/**
 * Plane geometry, following the backend's selection: a 0-D or 1-D source has a
 * single row (a 1-D array is one row of N columns), so rows are never derived
 * from shape[y] for those.
 */
export function planeMeta(plane) {
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
      const clamp = (raw) =>
        Math.max(0, Math.min(Math.round(isFinite(raw) ? raw : 0), last));
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
          onInput=${(e) =>
            onChange(ax.axis, fromFrac(parseFloat(e.target.value)))}
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
  const pad = (w) =>
    html`<td class="panel-table-pad" style=${`min-width:${w}px`}></td>`;
  const padHead = (w) =>
    html`<th class="panel-table-pad" style=${`min-width:${w}px`}></th>`;

  return html`<${ScrollArea}
    data-testid="array-2d-heatmap"
    tabindex="0"
    elementRef=${scrollRef}
    onScroll=${onScroll}
  >
    <${Table} class="array-heatmap" data-testid="array-heatmap">
      <thead>
        <tr>
          <th class="panel-table-corner"></th>
          ${leftPad ? padHead(leftPad) : null}
          ${values[0]?.map((_, c) => html`<th key=${c}>${x0 + c}</th>`)}
          ${rightPad ? padHead(rightPad) : null}
        </tr>
      </thead>
      <tbody>
        ${y0 > 0
          ? html`<tr
              aria-hidden="true"
              style=${`height:${y0 * rowHeight}px`}
            ></tr>`
          : null}
        ${values.map(
          (row, r) =>
            html`<tr key=${y0 + r} data-row=${y0 + r}>
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
                >
                  ${formatCell(v)}
                </td>`;
              })}
              ${rightPad ? pad(rightPad) : null}
            </tr>`,
        )}
        ${yEnd < meta.rows
          ? html`<tr
              aria-hidden="true"
              style=${`height:${(meta.rows - yEnd) * rowHeight}px`}
            ></tr>`
          : null}
      </tbody>
    <//>
  <//>`;
}

function ValueLegend({ meta }) {
  if (typeof meta.vmin !== "number" || typeof meta.vmax !== "number") {
    return html`<div class="panel-legend" data-testid="array-legend">
      no finite values
    </div>`;
  }
  const stops = Array.from({ length: 9 }, (_, i) =>
    heatmapColor(
      meta.vmin + ((meta.vmax - meta.vmin) * i) / 8,
      meta.vmin,
      meta.vmax,
    ),
  );
  const mid = meta.vmin < 0 && meta.vmax > 0 ? 0 : (meta.vmin + meta.vmax) / 2;
  return html`<${Legend}
    data-testid="array-legend"
    min=${html`<span data-testid="array-legend-min"
      >${formatCell(meta.vmin)}</span
    >`}
    mid=${html`<span data-testid="array-legend-mid">${formatCell(mid)}</span>`}
    max=${html`<span data-testid="array-legend-max"
      >${formatCell(meta.vmax)}</span
    >`}
    stops=${stops}
  />`;
}

function ArraySurface({
  plane,
  tile,
  indices = {},
  onSliceChange = () => {},
  rowHeight = ROW_H,
  onScroll,
  scrollRef,
  error,
}) {
  const meta = plane ? planeMeta(plane) : null;
  const sliceAxes = plane?.slice_axes ?? [];
  if (error) {
    return html`<${Panel}
      ><${ErrorState}>Could not read array: ${error}<//><//
    >`;
  }
  // Reading a large array takes a moment; say so rather than showing an empty
  // surface until the first plane lands.
  if (!meta) {
    return html`<${Panel}
      ><${LoadingState} data-testid="array-loading">Loading array…<//><//
    >`;
  }

  const items = [
    "Array",
    `shape [${meta.shape.join(", ")}]`,
    `dtype ${meta.dtype}`,
  ];
  if (meta.axes.length) items.push(`axes [${meta.axes.join(", ")}]`);

  return html`<${Panel}>
    <${Meta} items=${items} data-testid="array-info" />
    <${SliceAxes}
      sliceAxes=${sliceAxes}
      indices=${indices}
      onChange=${onSliceChange}
    />
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
            ${meta.shape.length ? `${meta.shape.join(" × ")} | ` : ""}displaying
            ${meta.rows} × ${meta.cols}
          </div>
        `}
  <//>`;
}

/** Normalize client-computed numeric data without transposition or sampling. */
export function arrayGeometry(data, declaredShape, axes = [], indices = {}) {
  const sequence = (value) =>
    Array.isArray(value) ||
    (ArrayBuffer.isView(value) && !(value instanceof DataView));
  const infer = (value) => {
    if (!sequence(value)) return [];
    const child = value.length ? infer(value[0]) : [];
    for (const row of value) {
      if (JSON.stringify(infer(row)) !== JSON.stringify(child))
        throw new Error("Array data must be rectangular.");
    }
    return [value.length, ...child];
  };
  const inferred = infer(data);
  const shape = declaredShape ?? inferred;
  if (
    !Array.isArray(shape) ||
    shape.some((n) => !Number.isSafeInteger(n) || n < 0)
  ) {
    throw new Error(
      "Array shape must contain non-negative integer dimensions.",
    );
  }
  const flat = [];
  const flatten = (value) => {
    if (sequence(value)) for (const child of value) flatten(child);
    else flat.push(value);
  };
  flatten(data);
  if (shape.reduce((n, size) => n * size, 1) !== flat.length)
    throw new Error("Array shape does not match its values.");
  const display = displayAxes(shape, axes, []);
  const sliceAxes = shape
    .map((size, axis) => ({
      axis,
      size,
      name: axes[axis] || `axis_${axis}`,
      index: indices[axis] ?? 0,
    }))
    .filter(({ axis }) => axis !== display.y && axis !== display.x);
  for (const slice of sliceAxes) {
    if (
      !Number.isInteger(slice.index) ||
      slice.index < 0 ||
      slice.index >= slice.size
    )
      throw new Error("Array slice index is outside its dimension.");
  }
  const strides = shape.map((_, axis) =>
    shape.slice(axis + 1).reduce((n, size) => n * size, 1),
  );
  const offset = sliceAxes.reduce(
    (n, slice) => n + slice.index * strides[slice.axis],
    0,
  );
  const rows = shape.length >= 2 ? shape[display.y] : 1;
  const cols = shape.length ? shape[display.x] : 1;
  const valueAt = (row, col) =>
    flat[
      offset +
        (shape.length >= 2 ? row * strides[display.y] : 0) +
        (shape.length ? col * strides[display.x] : 0)
    ];
  let vmin = null;
  let vmax = null;
  for (let row = 0; row < rows; row += 1)
    for (let col = 0; col < cols; col += 1) {
      const value = numeric(valueAt(row, col));
      if (value !== null) {
        vmin = vmin === null ? value : Math.min(vmin, value);
        vmax = vmax === null ? value : Math.max(vmax, value);
      }
    }
  return {
    plane: { source_shape: shape, axes, slice_axes: sliceAxes, vmin, vmax },
    valueAt,
    rows,
    cols,
  };
}

const EMPTY_AXES = [];
const EMPTY_INDICES = {};

function LocalArrayView({
  data,
  shape,
  axes = EMPTY_AXES,
  dtype = "number",
  indices = EMPTY_INDICES,
  onSliceChange = () => {},
}) {
  const scrollRef = useRef(null);
  const [scroll, setScroll] = useState({ top: 0, left: 0 });
  const [rowHeight, setRowHeight] = useState(ROW_H);
  const geometry = useMemo(() => {
    try {
      return arrayGeometry(data, shape, axes, indices);
    } catch (error) {
      return { error: error.message };
    }
  }, [data, shape, axes, indices]);
  useLayoutEffect(() => {
    const measured =
      scrollRef.current?.querySelector("tbody tr[data-row]")?.offsetHeight;
    if (measured > 0 && measured !== rowHeight) setRowHeight(measured);
  });
  const plane = geometry.plane;
  if (!plane) return html`<${ArraySurface} error=${geometry.error} />`;
  if (!geometry.rows || !geometry.cols)
    return html`<${Panel}
      ><div class="panel-hint">This array has no values.</div><//
    >`;
  const y0 = Math.max(
    0,
    Math.min(geometry.rows - 1, Math.floor(scroll.top / rowHeight) - OVERSCAN),
  );
  const x0 = Math.max(
    0,
    Math.min(geometry.cols - 1, Math.floor(scroll.left / COL_W) - OVERSCAN),
  );
  const height = Math.min(
    TILE_CAP,
    geometry.rows - y0,
    Math.ceil((scrollRef.current?.clientHeight || VIEWPORT) / rowHeight) +
      2 * OVERSCAN,
  );
  const width = Math.min(
    TILE_CAP,
    geometry.cols - x0,
    Math.ceil((scrollRef.current?.clientWidth || 480) / COL_W) + 2 * OVERSCAN,
  );
  const values = Array.from({ length: height }, (_, row) =>
    Array.from({ length: width }, (_, col) =>
      geometry.valueAt(y0 + row, x0 + col),
    ),
  );
  return html`<${ArraySurface}
    plane=${{ ...plane, source_dtype: dtype }}
    tile=${{ values, y0, x0 }}
    indices=${indices}
    onSliceChange=${(axis, index) => {
      setScroll({ top: 0, left: 0 });
      if (scrollRef.current) {
        scrollRef.current.scrollTop = 0;
        scrollRef.current.scrollLeft = 0;
      }
      onSliceChange(axis, index);
    }}
    rowHeight=${rowHeight}
    scrollRef=${scrollRef}
    onScroll=${(event) =>
      setScroll({
        top: event.currentTarget.scrollTop,
        left: event.currentTarget.scrollLeft,
      })}
  />`;
}

/** Raw numeric data, or caller-owned plane/tile windows for bounded remote reads. */
export function ArrayView(props) {
  return props.data !== undefined
    ? html`<${LocalArrayView} ...${props} />`
    : html`<${ArraySurface} ...${props} />`;
}
