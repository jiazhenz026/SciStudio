/* core.series.basic — a series as a chart or a table of its values.
 *
 * Built with Preact and the shared panel component set, charting with the
 * vendored Plotly build. The surface matches the viewer it replaces: a
 * Chart/Table toggle, a line-and-marker plot of the points, and the same values
 * as a two-column table.
 *
 * Faithful display (#1886 item D): a series may hold values that cannot be
 * plotted — NaN and ±inf. The viewer dropped them silently, so a curve looked
 * continuous while samples were missing from it. The reading layer now reports
 * how many were dropped and where, and this panel says so above the chart and
 * breaks the line at those positions rather than joining across them.
 */
import {
  html,
  render,
  useCallback,
  useEffect,
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
} from "../../sdk/1/panel-ui.js";

const api = window.scistudio;

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
  const where = complete ? `at index ${shown}${rest}` : `including index ${shown}${rest}`;
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
 * Where each returned point sat in the source, when the read did not say.
 *
 * A complete read returns every finite point in order, so a point's source
 * position is its own position plus the dropped ones before it. A decimated
 * read cannot be reconstructed this way, which is why it reports the positions
 * itself.
 */
export function inferSourceIndices(count, gaps) {
  const ordered = [...(gaps ?? [])].sort((a, b) => a - b);
  const out = [];
  let source = 0;
  let g = 0;
  for (let i = 0; i < count; i += 1) {
    while (g < ordered.length && ordered[g] === source) {
      source += 1;
      g += 1;
    }
    out.push(source);
    source += 1;
  }
  return out;
}

/**
 * Build the plotted line, breaking it where samples are missing.
 *
 * Plotly renders null as a gap, so a break between two points shows the absence
 * between them rather than a straight segment drawn over it.
 *
 * The dropped positions are *source* positions, and for a series longer than
 * the read's budget the points are a sample of the source — so counting
 * returned points to find a gap puts it in the wrong place, or never reaches it
 * at all, and the curve is drawn continuous across data that is missing. Each
 * point's own source position is what the two are compared in.
 */
export function lineData(points, positions, sourceIndices) {
  const xs = [];
  const ys = [];
  const rows = points ?? [];
  const gaps = [...(positions ?? [])].sort((a, b) => a - b);
  const sources =
    Array.isArray(sourceIndices) && sourceIndices.length === rows.length
      ? sourceIndices
      : inferSourceIndices(rows.length, gaps);
  let g = 0;
  rows.forEach((point, i) => {
    if (i > 0) {
      const previous = sources[i - 1];
      // Both lists ascend, so the cursor only moves forward.
      while (g < gaps.length && gaps[g] <= previous) g += 1;
      if (g < gaps.length && gaps[g] < sources[i]) {
        xs.push(null);
        ys.push(null);
      }
    }
    xs.push(point.x);
    ys.push(point.y);
  });
  return { xs, ys };
}

function SeriesChart({ points, positions, sourceIndices }) {
  const node = useRef(null);
  useLayoutEffect(() => {
    const Plotly = window.Plotly;
    const element = node.current;
    if (!Plotly || !element) return;
    const { xs, ys } = lineData(points, positions, sourceIndices);
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
  }, [points, positions, sourceIndices]);
  return html`<div class="series-chart" data-testid="series-chart" ref=${node}></div>`;
}

function SeriesTable({ points }) {
  return html`<${ScrollArea} data-testid="series-table">
    <${Table} class="series-values">
      <thead>
        <tr><th>x</th><th>y</th></tr>
      </thead>
      <tbody>
        ${points.map(
          (point, index) => html`<tr key=${index}>
            <td>${point.x}</td>
            <td>${point.y}</td>
          </tr>`,
        )}
      </tbody>
    <//>
  <//>`;
}

function SeriesPanel({ initialView }) {
  const [mode, setMode] = useState(initialView.mode === "table" ? "table" : "chart");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const fail = useCallback((err) => {
    const message = err?.message || String(err);
    setError(message);
    api.reportError(message);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .read("series.points", {})
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err) => {
        if (!cancelled) fail(err);
      });
    return () => {
      cancelled = true;
    };
  }, [fail]);

  useEffect(() => {
    api.setViewState({ mode });
  }, [mode]);

  if (error) {
    return html`<${Panel}><${ErrorState}>Could not read series: ${error}<//><//>`;
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
        onClick=${() => setMode("chart")}
      >Chart<//>
      <${Button}
        primary=${mode === "table"}
        aria-pressed=${mode === "table" ? "true" : "false"}
        onClick=${() => setMode("table")}
      >Table<//>
    <//>
    ${notice
      ? html`<div class="panel-hint" data-testid="series-nonfinite-gaps" role="status">${notice}</div>`
      : null}
    ${points.length === 0
      ? html`<${EmptyState} data-testid="series-empty">This series has no plottable values.<//>`
      : mode === "chart"
        ? html`<${SeriesChart}
            points=${points}
            positions=${data.nonfinite_positions}
            sourceIndices=${data.source_indices}
          />`
        : html`<${SeriesTable} points=${points} />`}
  <//>`;
}

api
  .ready()
  .then(() => {
    const view = api.viewState && typeof api.viewState === "object" ? api.viewState : {};
    render(html`<${SeriesPanel} initialView=${view} />`, document.getElementById("root"));
  })
  .catch((err) => api.reportError(String(err?.message || err)));
