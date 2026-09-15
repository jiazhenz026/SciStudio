/**
 * Behaviour contract for core.series.basic.
 *
 * Carries over what the compiled series viewer did — a Chart/Table toggle over
 * the same points — and pins #1886 item D and #2460: a series may hold values
 * that cannot be drawn (NaN, ±inf, missing). They arrive in place, row for row,
 * so the panel says how many there are and where, breaks the line at them, and
 * lists them as they are in the table. A long series is read page by page to
 * the end; nothing is sampled.
 */
import { readFileSync } from "node:fs";
import { rewriteRendererImports } from "./rendererTestModules";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.series.basic");
const PREACT = resolve(PANELS, "lib/preact-htm@3.1.1/dist/preact-standalone.module.js");
const PANEL_UI = resolve(PANELS, "sdk/1/panel-ui.js");

const dataUrl = (src: string) =>
  `data:text/javascript;base64,${Buffer.from(src).toString("base64")}`;

let loadCount = 0;

async function loadPanelModule() {
  const preactUrl = dataUrl(readFileSync(PREACT, "utf8"));
  const uiUrl = dataUrl(
    readFileSync(PANEL_UI, "utf8").replace(
      /"[^"]*preact-standalone\.module\.js"/g,
      JSON.stringify(preactUrl),
    ),
  );
  const src = rewriteRendererImports(
    readFileSync(resolve(PANEL, "panel.js"), "utf8"),
    preactUrl,
    uiUrl,
  )
    .replace(/"[^"]*preact-standalone\.module\.js"/g, JSON.stringify(preactUrl))
    .replace(/"[^"]*panel-ui\.js"/g, JSON.stringify(uiUrl));
  loadCount += 1;
  return import(/* @vite-ignore */ dataUrl(`${src}\n//# load-${loadCount}`));
}

interface PlotCall {
  data: Array<Record<string, unknown>>;
  layout: Record<string, unknown>;
}

/** Record what the panel asks Plotly to draw, without a real chart engine. */
function stubPlotly() {
  const calls: PlotCall[] = [];
  (window as unknown as { Plotly: unknown }).Plotly = {
    react: (_el: unknown, data: PlotCall["data"], layout: PlotCall["layout"]) => {
      calls.push({ data, layout });
      return Promise.resolve();
    },
    purge: () => {},
  };
  return calls;
}

function stubHost(read: unknown, view: Record<string, unknown> = {}) {
  const reads: Array<Record<string, unknown>> = [];
  const pages = Array.isArray(read) ? read : null;
  const api = {
    input: { ref: "s", kind: "data_ref" },
    viewState: view,
    reads,
    ready: () => Promise.resolve(api),
    read: (op: string, params: Record<string, unknown> = {}) => {
      if (op !== "series.points")
        return Promise.reject(Object.assign(new Error(`no read ${op}`), { code: "not_found" }));
      reads.push(params);
      if (!pages) return Promise.resolve(read);
      const offset = (params.offset as number) ?? 0;
      return Promise.resolve(pages.find((page) => page.offset === offset));
    },
    setViewState: vi.fn(),
    reportError: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  document.body.innerHTML = '<div id="root"></div>';
  return api;
}

const root = () => document.getElementById("root") as HTMLElement;
const button = (label: string) =>
  [...root().querySelectorAll("button")].find((b) => b.textContent?.trim() === label) as
    | HTMLButtonElement
    | undefined;

const POINTS = [
  { x: 0, y: 1 },
  { x: 1, y: 4 },
  { x: 2, y: 9 },
];

/**
 * A series.points answer in the shape the route actually sends for JSON
 * callers: two parallel arrays, `index` carrying the x values and `values` the
 * y values. (The reader produces x/y pairs; the route splits them.) Two earlier
 * versions of this panel each assumed a different shape — first a `points` key,
 * then row-wise pairs — and rendered every series as empty, so this fixture is
 * built from what the route was observed to emit.
 */
function seriesRead(
  points: Array<{ x: number | string; y: number | string }>,
  extra: Record<string, unknown> = {},
) {
  return {
    index: points.map((p) => p.x),
    values: points.map((p) => p.y),
    columns: ["x", "y"],
    dtype: "<f8",
    shape: [points.length, 2],
    offset: 0,
    next_offset: null,
    total: points.length,
    nonnumeric: 0,
    truncated: false,
    complete: true,
    ...extra,
  };
}

beforeAll(() => {
  stubPlotly();
  stubHost(seriesRead([]));
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.series.basic — reporting values that cannot be drawn (#1886 D)", () => {
  it("says nothing when every value is drawable", async () => {
    const { gapNotice } = await loadPanelModule();
    expect(gapNotice(seriesRead(POINTS))).toBeNull();
    expect(gapNotice({})).toBeNull();
  });

  it("reports how many rows cannot be drawn and at which source rows", async () => {
    const { gapNotice } = await loadPanelModule();
    const notice = gapNotice(
      seriesRead([
        { x: 0, y: 1 },
        { x: 1, y: "NaN" },
        { x: 2, y: "-Infinity" },
      ]),
    );
    expect(notice).toContain("2 non-finite values");
    expect(notice).toContain("1, 2");
  });

  it("counts source rows from the page offset", async () => {
    const { gapNotice } = await loadPanelModule();
    const notice = gapNotice({ offset: 500, index: [500, 501], values: [1, "NaN"] });
    expect(notice).toContain("1 non-finite value");
    expect(notice).toContain("501");
  });
});

describe("core.series.basic — the read contract", () => {
  it("keeps every row, in place, with non-finite values as the numbers they name", async () => {
    const { readPoints } = await loadPanelModule();
    expect(
      readPoints(seriesRead(POINTS)).map(({ x, y }: { x: number; y: number }) => ({ x, y })),
    ).toEqual(POINTS);
    const rows = readPoints({
      offset: 10,
      index: [10, 11, 12, 13],
      values: [1, "NaN", "Infinity", null],
    });
    expect(rows.map((r: { position: number }) => r.position)).toEqual([10, 11, 12, 13]);
    expect(rows[1].y).toBeNaN();
    expect(rows[2].y).toBe(Infinity);
    expect(rows[3].y).toBeNaN();
    expect(readPoints({})).toEqual([]);
    expect(readPoints(seriesRead([]))).toEqual([]);
    // The binary transport's row-wise pairs are understood too.
    expect(
      readPoints({
        values: [
          [0, 1],
          [1, 4],
        ],
      }),
    ).toEqual([
      { x: 0, y: 1, position: 0 },
      { x: 1, y: 4, position: 1 },
    ]);
  });

  it("joins pages in order into one complete read", async () => {
    const { mergePages } = await loadPanelModule();
    const merged = mergePages([
      { offset: 0, index: [0, 1], values: [5, "NaN"], next_offset: 2, total: 3, nonnumeric: 1 },
      { offset: 2, index: [2], values: [7], next_offset: null, total: 3, nonnumeric: 0 },
    ]);
    expect(merged.index).toEqual([0, 1, 2]);
    expect(merged.values).toEqual([5, "NaN", 7]);
    expect(merged.nonnumeric).toBe(1);
    expect(merged.complete).toBe(true);
    expect(merged.total).toBe(3);
  });
});

describe("core.series.basic — the plotted line", () => {
  it("breaks the line where a row cannot be drawn rather than drawing across", async () => {
    const { lineData } = await loadPanelModule();
    const { xs, ys } = lineData([
      { x: 0, y: 0 },
      { x: 1, y: NaN },
      { x: 2, y: 2 },
      { x: 3, y: 3 },
    ]);
    expect(xs).toEqual([0, null, 2, 3]);
    expect(ys).toEqual([0, null, 2, 3]);
  });

  it("plots a complete series unbroken", async () => {
    const { lineData } = await loadPanelModule();
    const { xs, ys } = lineData(POINTS);
    expect(xs).toEqual([0, 1, 2]);
    expect(ys).toEqual([1, 4, 9]);
  });

  it("makes a run of missing rows one break, and none at the ends", async () => {
    const { lineData } = await loadPanelModule();
    const { xs } = lineData([
      { x: NaN, y: 1 },
      { x: 1, y: 1 },
      { x: 2, y: Infinity },
      { x: 3, y: NaN },
      { x: 4, y: 4 },
      { x: 5, y: NaN },
    ]);
    expect(xs).toEqual([1, null, 4]);
  });
});

describe("core.series.basic — the rendered surface", () => {
  it("charts the points, with gaps left open", async () => {
    const calls = stubPlotly();
    stubHost(
      seriesRead([
        { x: 0, y: 1 },
        { x: 1, y: "NaN" },
        { x: 2, y: 4 },
        { x: 3, y: 9 },
      ]),
    );
    await loadPanelModule();
    await vi.waitFor(() => expect(calls.length).toBeGreaterThan(0));

    const trace = calls[calls.length - 1].data[0];
    expect(trace.type).toBe("scatter");
    expect(trace.mode).toBe("lines+markers");
    // Plotly joins across nulls unless told not to; the gap must stay a gap.
    expect(trace.connectgaps).toBe(false);
    expect(trace.x).toEqual([0, null, 2, 3]);
  });

  it("reads every page to the end and charts the whole series (#2460)", async () => {
    const calls = stubPlotly();
    const api = stubHost([
      seriesRead(
        [
          { x: 0, y: 1 },
          { x: 1, y: 2 },
        ],
        { offset: 0, next_offset: 2, total: 5, truncated: true },
      ),
      seriesRead(
        [
          { x: 2, y: 3 },
          { x: 3, y: 4 },
        ],
        { offset: 2, next_offset: 4, total: 5, truncated: true },
      ),
      seriesRead([{ x: 4, y: 5 }], { offset: 4, next_offset: null, total: 5 }),
    ]);
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=series-loading-more]")).toBeNull(),
    );
    await vi.waitFor(() => expect(calls.length).toBeGreaterThan(0));
    expect(api.reads).toEqual([{}, { offset: 2 }, { offset: 4 }]);
    expect(calls[calls.length - 1].data[0].x).toEqual([0, 1, 2, 3, 4]);
  });

  it("shows the table rows as they are, non-finite included", async () => {
    stubPlotly();
    stubHost(
      seriesRead([
        { x: 0, y: 1.25 },
        { x: 1, y: "NaN" },
        { x: 2, y: "-Infinity" },
      ]),
      { mode: "table" },
    );
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelectorAll("tbody tr[data-row]").length).toBe(3));
    const cells = [...root().querySelectorAll("tbody tr[data-row]")].map((row) =>
      [...row.querySelectorAll("td")].map((cell) => cell.textContent?.trim()),
    );
    expect(cells).toEqual([
      ["0", "0", "1.25"],
      ["1", "1", "NaN"],
      ["2", "2", "-∞"],
    ]);
  });

  it("shows the gap notice above the chart", async () => {
    stubPlotly();
    stubHost(
      seriesRead([
        { x: 0, y: "NaN" },
        { x: 1, y: 1 },
        { x: 2, y: "Infinity" },
      ]),
    );
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=series-nonfinite-gaps]")).toBeTruthy(),
    );
    expect(root().querySelector("[data-testid=series-nonfinite-gaps]")?.textContent).toContain(
      "2 non-finite values",
    );
  });

  it("carries no notice for a complete series", async () => {
    stubPlotly();
    stubHost(seriesRead(POINTS, { total: 3, nonnumeric: 0 }));
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector("[data-testid=series-chart]")).toBeTruthy());
    expect(root().querySelector("[data-testid=series-nonfinite-gaps]")).toBeNull();
  });

  it("switches between the chart and the table of the same values", async () => {
    stubPlotly();
    stubHost(seriesRead(POINTS, { total: 3, nonnumeric: 0 }));
    await loadPanelModule();
    await vi.waitFor(() => expect(button("Table")).toBeTruthy());

    expect(root().querySelector("[data-testid=series-chart]")).toBeTruthy();
    expect(button("Chart")?.getAttribute("aria-pressed")).toBe("true");

    button("Table")!.click();
    await vi.waitFor(() => expect(root().querySelector("[data-testid=series-table]")).toBeTruthy());
    expect(root().querySelector("[data-testid=series-chart]")).toBeNull();
    expect(button("Table")?.getAttribute("aria-pressed")).toBe("true");
    // The table lists the same points the chart drew.
    expect([...root().querySelectorAll("tbody tr[data-row]")].length).toBe(3);

    button("Chart")!.click();
    await vi.waitFor(() => expect(root().querySelector("[data-testid=series-chart]")).toBeTruthy());
  });

  it("remembers the chosen mode", async () => {
    stubPlotly();
    const api = stubHost(seriesRead(POINTS, { total: 3, nonnumeric: 0 }), { mode: "table" });
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector("[data-testid=series-table]")).toBeTruthy());
    expect(api.setViewState).toHaveBeenCalledWith({ mode: "table" });
  });
});

describe("core.series.basic — edge cases", () => {
  it("says so when the series has nothing to plot", async () => {
    stubPlotly();
    stubHost(seriesRead([]));
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector("[data-testid=series-empty]")).toBeTruthy());
  });

  it("surfaces a failed read", async () => {
    stubPlotly();
    const api = {
      input: {},
      viewState: {},
      ready: () => Promise.resolve(api),
      read: () => Promise.reject(new Error("unsupported")),
      setViewState: vi.fn(),
      reportError: vi.fn(() => Promise.resolve(null)),
    } as Record<string, unknown>;
    (window as unknown as { scistudio: unknown }).scistudio = api;
    document.body.innerHTML = '<div id="root"></div>';
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector(".panel-error")).toBeTruthy());
    expect(root().textContent).toContain("Could not read series");
    expect(api.reportError).toHaveBeenCalled();
  });
});
