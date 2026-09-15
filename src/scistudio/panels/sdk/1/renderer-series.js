/* Reusable core presentation. Host reads and persistence stay in the caller. */
import {
  html,
  useLayoutEffect,
  useRef,
  useState,
} from "../../lib/preact-htm@3.1.1/dist/preact-standalone.module.js";

import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
  Row,
  ScrollArea,
  Table,
} from "./panel-ui.js";

const SENTINELS = { NaN: NaN, Infinity: Infinity, "-Infinity": -Infinity };

/** One transported cell as a number: a JSON sentinel becomes the value it names, anything else not a number is NaN. */
export function toNumber(value) {
  if (typeof value === "number") return value;
  if (typeof value === "string" && value in SENTINELS) return SENTINELS[value];
  return NaN;
}

/**
 * Every row of a series read, in source order, as `{x, y, position}`.
 *
 * ``series.points`` answers with two parallel arrays: ``index`` carries the x
 * values and ``values`` the y values, one entry per source row. Row ``i`` is
 * source row ``offset + i``. Nothing is dropped: a non-finite or missing value
 * arrives in place (as a `"NaN"` / `"Infinity"` / `"-Infinity"` sentinel over
 * JSON) and stays in the result as that number. The binary transport's
 * row-wise `[x, y]` pairs are accepted too.
 */
export function readPoints(data) {
  const ys = data?.values;
  if (!Array.isArray(ys) && !ArrayBuffer.isView(ys)) return [];
  const xs =
    Array.isArray(data?.index) || ArrayBuffer.isView(data?.index)
      ? data.index
      : null;
  const offset = typeof data?.offset === "number" ? data.offset : 0;
  const points = [];
  for (let i = 0; i < ys.length; i += 1) {
    const entry = ys[i];
    const position = offset + i;
    if (Array.isArray(entry)) {
      points.push({ x: toNumber(entry[0]), y: toNumber(entry[1]), position });
      continue;
    }
    points.push({
      x: xs ? toNumber(xs[i]) : position,
      y: toNumber(entry),
      position,
    });
  }
  return points;
}

/**
 * Join consecutive `series.points` pages into one read, in order.
 *
 * A caller that follows `next_offset` from `0` holds the whole series once the
 * last page (`next_offset: null`) is joined.
 */
export function mergePages(pages) {
  const index = [];
  const values = [];
  let nonnumeric = 0;
  for (const page of pages ?? []) {
    for (const x of page?.index ?? []) index.push(x);
    for (const y of page?.values ?? []) values.push(y);
    nonnumeric += page?.nonnumeric ?? 0;
  }
  const first = pages?.[0] ?? {};
  const last = pages?.[pages.length - 1] ?? {};
  return {
    index,
    values,
    offset: typeof first.offset === "number" ? first.offset : 0,
    total: last.total ?? values.length,
    next_offset: last.next_offset ?? null,
    nonnumeric,
    truncated: last.next_offset != null,
    complete: last.next_offset == null,
  };
}

const finite = (point) => Number.isFinite(point.x) && Number.isFinite(point.y);

/**
 * Describe the rows the chart cannot draw, or null when every row is drawable.
 *
 * A complete series carries no notice at all — a caveat appears only when there
 * is something to caveat. The rows themselves are still in the table view.
 */
export function gapNotice(data) {
  const missing = readPoints(data).filter((point) => !finite(point));
  if (!missing.length) return null;
  const noun = missing.length === 1 ? "value" : "values";
  const shown = missing
    .slice(0, 8)
    .map((point) => point.position)
    .join(", ");
  const rest = missing.length > 8 ? ", …" : "";
  return `${missing.length} non-finite ${noun} (NaN, ±∞, or missing) cannot be drawn — at row ${shown}${rest}.`;
}

/**
 * Build the plotted line, breaking it where a row has no finite value.
 *
 * Plotly renders null as a gap, so a break shows the absence between two
 * points rather than a straight segment drawn over it. A run of missing rows is
 * one break.
 */
export function lineData(points) {
  const xs = [];
  const ys = [];
  let broken = false;
  for (const point of points ?? []) {
    if (!finite(point)) {
      if (xs.length && !broken) {
        xs.push(null);
        ys.push(null);
      }
      broken = true;
      continue;
    }
    broken = false;
    xs.push(point.x);
    ys.push(point.y);
  }
  if (broken && xs.length && xs[xs.length - 1] === null) {
    xs.pop();
    ys.pop();
  }
  return { xs, ys };
}

/** Above this many points the chart draws through WebGL so every point is still drawn. */
const WEBGL_POINTS = 20000;

function SeriesChart({ points, plotly }) {
  const node = useRef(null);
  useLayoutEffect(() => {
    const Plotly = plotly;
    const element = node.current;
    if (!Plotly || !element) return;
    const { xs, ys } = lineData(points);
    const large = points.length > WEBGL_POINTS;
    Plotly.react(
      element,
      [
        {
          x: xs,
          y: ys,
          type: large ? "scattergl" : "scatter",
          mode: large ? "lines" : "lines+markers",
          marker: { color: "#f06a44" },
          line: { color: "#f06a44" },
          connectgaps: false,
        },
      ],
      {
        autosize: true,
        margin: { l: 30, r: 10, b: 30, t: 10 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
      },
      { displayModeBar: false, responsive: true },
    );
    return () => Plotly.purge(element);
  }, [points, plotly]);
  return html`<div
    class="series-chart"
    data-testid="series-chart"
    ref=${node}
  ></div>`;
}

const ROW_H = 22; // table row height, mirrored by renderers.css
const VIEWPORT = 320; // the scroll surface's max height, from panel.css
const OVERSCAN = 10;

function formatValue(v) {
  if (Number.isNaN(v)) return "NaN";
  if (v === Infinity) return "∞";
  if (v === -Infinity) return "-∞";
  return String(v);
}

/**
 * Every row, exactly, in a scrolling table. Only the rows in view are in the
 * DOM; spacer rows of exactly the missing height keep the scrollbar describing
 * the whole series.
 */
function SeriesTable({ points }) {
  const [top, setTop] = useState(0);
  const first = Math.max(0, Math.floor(top / ROW_H) - OVERSCAN);
  const last = Math.min(
    points.length,
    Math.ceil((top + VIEWPORT) / ROW_H) + OVERSCAN,
  );
  const rows = points.slice(first, last);
  return html`<${ScrollArea}
    data-testid="series-table"
    onScroll=${(event) => setTop(event.currentTarget.scrollTop)}
  >
    <${Table} class="series-values">
      <thead>
        <tr>
          <th>row</th>
          <th>x</th>
          <th>y</th>
        </tr>
      </thead>
      <tbody>
        ${first > 0
          ? html`<tr
              aria-hidden="true"
              style=${`height:${first * ROW_H}px`}
            ></tr>`
          : null}
        ${rows.map(
          (point) =>
            html`<tr key=${point.position} data-row=${point.position}>
              <td>${point.position}</td>
              <td>${formatValue(point.x)}</td>
              <td>${formatValue(point.y)}</td>
            </tr>`,
        )}
        ${last < points.length
          ? html`<tr
              aria-hidden="true"
              style=${`height:${(points.length - last) * ROW_H}px`}
            ></tr>`
          : null}
      </tbody>
    <//>
  <//>`;
}

/**
 * A series as a line chart or a table of every row. Rows without a finite value are drawn as breaks in the line, listed in a notice, and shown as they are in the table.
 *
 * @param {object} [props.data] A `series.points` result `{index, values, offset?, total?}`, several pages with their `index` and `values` joined in order, or computed `values` and `index` arrays. Every row is shown; nothing is sampled.
 * @param {boolean} [props.loading] Set while further pages are still being read; the view says how many rows of `data.total` it holds.
 * @param {"chart" | "table"} [props.mode] Which view to show.
 * @param {function} [props.onModeChange] `(mode)` when the reader switches view.
 * @param {string} [props.error] A displayable message. It takes precedence over any data, so a failed read never leaves earlier values looking current.
 * @param {object} [props.plotly] The Plotly library for chart mode; load `plotly@2.35.3` from the shared libraries. Table mode needs none.
 */
export function SeriesView({
  data,
  loading = false,
  mode = "chart",
  onModeChange = () => {},
  error,
  plotly = globalThis.Plotly,
}) {
  if (error) {
    return html`<${Panel}
      ><${ErrorState}>Could not read series: ${error}<//><//
    >`;
  }
  if (!data) {
    return html`<${Panel}><${LoadingState}>Loading series…<//><//>`;
  }

  const points = readPoints(data);
  const notice = loading ? null : gapNotice(data);

  return html`<${Panel}>
    <${Row} class="series-modes">
      <${Button}
        primary=${mode === "chart"}
        aria-pressed=${mode === "chart" ? "true" : "false"}
        onClick=${() => onModeChange("chart")}
        >Chart<//
      >
      <${Button}
        primary=${mode === "table"}
        aria-pressed=${mode === "table" ? "true" : "false"}
        onClick=${() => onModeChange("table")}
        >Table<//
      >
    <//>
    ${loading
      ? html`<${LoadingState} data-testid="series-loading-more">
          Reading rows…
          ${points.length.toLocaleString()}${typeof data.total === "number"
            ? ` of ${data.total.toLocaleString()}`
            : ""}
        <//>`
      : null}
    ${notice
      ? html`<div
          class="panel-hint"
          data-testid="series-nonfinite-gaps"
          role="status"
        >
          ${notice}
        </div>`
      : null}
    ${points.length === 0
      ? loading
        ? null
        : html`<${EmptyState} data-testid="series-empty"
            >This series has no values.<//
          >`
      : mode === "chart"
        ? html`<${SeriesChart} points=${points} plotly=${plotly} />`
        : html`<${SeriesTable} points=${points} />`}
  <//>`;
}
