/* Reusable core presentation. Host reads and persistence stay in the caller. */
import {
  html,
  useLayoutEffect,
  useRef,
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

/**
 * Describe the samples the reading layer could not plot.
 *
 * Returns null when nothing was dropped, so a complete series carries no notice
 * at all — a caveat must appear only when there is something to caveat.
 */
export function gapNotice(data) {
  const count = data?.nonnumeric ?? 0;
  if (!count) return null;
  const positions = data?.nonfinite_positions ?? [];
  const complete = data?.nonfinite_positions_complete !== false;
  const noun = count === 1 ? "value" : "values";
  if (!positions.length) {
    return `${count} non-finite ${noun} (NaN or ±∞) are not plotted.`;
  }
  const shown = positions.slice(0, 8).join(", ");
  const rest = positions.length > 8 ? `, …` : "";
  const where = complete
    ? `at index ${shown}${rest}`
    : `including index ${shown}${rest}`;
  return `${count} non-finite ${noun} (NaN or ±∞) are not plotted — ${where}.`;
}

/**
 * Read the series read's points.
 *
 * ``series.points`` answers as two parallel arrays: ``index`` carries the x
 * values and ``values`` the y values, one entry each per plotted point. (The
 * route splits the reader's x/y pairs into that shape for JSON callers.) An
 * older numeric transport sent the pairs row-wise, so a pair of numbers is
 * still accepted per entry.
 */
export function readPoints(data) {
  const ys = data?.values;
  if (!Array.isArray(ys)) return [];
  const xs = Array.isArray(data?.index) ? data.index : null;
  const points = [];
  for (let i = 0; i < ys.length; i += 1) {
    const entry = ys[i];
    // Row-wise pairs (the binary transport's JSON form).
    if (Array.isArray(entry)) {
      const [x, y] = entry;
      if (typeof x === "number" && typeof y === "number") points.push({ x, y });
      continue;
    }
    const x = xs ? xs[i] : i;
    if (typeof entry !== "number" || typeof x !== "number") continue;
    points.push({ x, y: entry });
  }
  return points;
}

/**
 * Build the plotted line, breaking it where samples are missing.
 *
 * Plotly renders null as a gap, so inserting one at each dropped position shows
 * the curve as it is rather than drawing a straight segment over the absence.
 */
export function lineData(points, positions) {
  const xs = [];
  const ys = [];
  const gaps = new Set(positions ?? []);
  const sorted = [...(points ?? [])];
  let index = 0;
  for (const point of sorted) {
    // Positions are indices into the source values; emit a break before any
    // sample whose source index was dropped.
    while (gaps.has(index)) {
      xs.push(null);
      ys.push(null);
      index += 1;
    }
    xs.push(point.x);
    ys.push(point.y);
    index += 1;
  }
  return { xs, ys };
}

function SeriesChart({ points, positions, plotly }) {
  const node = useRef(null);
  useLayoutEffect(() => {
    const Plotly = plotly;
    const element = node.current;
    if (!Plotly || !element) return;
    const { xs, ys } = lineData(points, positions);
    Plotly.react(
      element,
      [
        {
          x: xs,
          y: ys,
          type: "scatter",
          mode: "lines+markers",
          marker: { color: "#f06a44" },
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
  }, [points, positions, plotly]);
  return html`<div
    class="series-chart"
    data-testid="series-chart"
    ref=${node}
  ></div>`;
}

function SeriesTable({ points }) {
  return html`<${ScrollArea} data-testid="series-table">
    <${Table} class="series-values">
      <thead>
        <tr>
          <th>x</th>
          <th>y</th>
        </tr>
      </thead>
      <tbody>
        ${points.map(
          (point, index) =>
            html`<tr key=${index}>
              <td>${point.x}</td>
              <td>${point.y}</td>
            </tr>`,
        )}
      </tbody>
    <//>
  <//>`;
}

export function SeriesView({
  data,
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
  const notice = gapNotice(data);

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
      ? html`<${EmptyState} data-testid="series-empty"
          >This series has no plottable values.<//
        >`
      : mode === "chart"
        ? html`<${SeriesChart}
            points=${points}
            positions=${data.nonfinite_positions}
            plotly=${plotly}
          />`
        : html`<${SeriesTable} points=${points} />`}
  <//>`;
}
