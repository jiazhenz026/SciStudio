/**
 * Behaviour contract for core.series.basic.
 *
 * Carries over what the compiled series viewer did — a Chart/Table toggle over
 * the same points — and pins #1886 item D: a series may hold values that cannot
 * be plotted (NaN, ±inf). The viewer dropped them silently, so a curve looked
 * continuous while samples were missing from it. The panel must say how many
 * were dropped and where, and must break the line at those positions instead of
 * drawing across them.
 */
import { readFileSync } from "node:fs";
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
  const src = readFileSync(resolve(PANEL, "panel.js"), "utf8")
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
  const api = {
    input: { ref: "s", kind: "data_ref" },
    viewState: view,
    ready: () => Promise.resolve(api),
    read: (op: string) =>
      op === "series.points"
        ? Promise.resolve(read)
        : Promise.reject(Object.assign(new Error(`no read ${op}`), { code: "not_found" })),
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
function seriesRead(points: Array<{ x: number; y: number }>, extra: Record<string, unknown> = {}) {
  return {
    index: points.map((p) => p.x),
    values: points.map((p) => p.y),
    columns: ["x", "y"],
    dtype: "<f8",
    shape: [points.length, 2],
    total: points.length,
    nonnumeric: 0,
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

describe("core.series.basic — reporting values that cannot be plotted (#1886 D)", () => {
  it("says nothing when every value is plottable", async () => {
    const { gapNotice } = await loadPanelModule();
    expect(gapNotice({ points: POINTS, total: 3, nonnumeric: 0 })).toBeNull();
    expect(gapNotice({})).toBeNull();
  });

  it("reports how many were dropped and where", async () => {
    const { gapNotice } = await loadPanelModule();
    const notice = gapNotice({
      nonnumeric: 2,
      nonfinite_positions: [3, 7],
      nonfinite_positions_complete: true,
    });
    expect(notice).toContain("2 non-finite values");
    expect(notice).toContain("3, 7");
  });

  it("says the positions are partial when the read could not list them all", async () => {
    const { gapNotice } = await loadPanelModule();
    const notice = gapNotice({
      nonnumeric: 500,
      nonfinite_positions: [1, 2, 3],
      nonfinite_positions_complete: false,
    });
    expect(notice).toContain("500 non-finite values");
    // The count stays exact even when only some positions are listed.
    expect(notice).toContain("including");
  });

  it("still reports the count when no positions are available", async () => {
    const { gapNotice } = await loadPanelModule();
    const notice = gapNotice({ nonnumeric: 1, nonfinite_positions: [] });
    expect(notice).toContain("1 non-finite value");
  });
});

describe("core.series.basic — the read contract", () => {
  it("reads the points out of the numeric transport the backend sends", async () => {
    const { readPoints } = await loadPanelModule();
    // series.points answers with `values` (x/y pairs row-wise) and `columns`.
    // The panel once looked for a `points` key that the backend never sends, so
    // every series rendered as empty — pin the real shape here.
    expect(readPoints(seriesRead(POINTS))).toEqual(POINTS);
    // The exact payload the route was observed to emit for a series whose
    // second sample is NaN: the dropped sample is absent from both arrays.
    expect(
      readPoints({
        index: [0, 2, 3],
        values: [1, 9, 16],
        columns: ["x", "y"],
        nonnumeric: 1,
        nonfinite_positions: [1],
      }),
    ).toEqual([
      { x: 0, y: 1 },
      { x: 2, y: 9 },
      { x: 3, y: 16 },
    ]);
    // A read with no values is empty rather than an error.
    expect(readPoints({})).toEqual([]);
    expect(readPoints(seriesRead([]))).toEqual([]);
    // The binary transport's row-wise JSON form is still understood.
    expect(
      readPoints({
        values: [
          [0, 1],
          [1, 4],
        ],
      }),
    ).toEqual([
      { x: 0, y: 1 },
      { x: 1, y: 4 },
    ]);
    // A value that is not a number is skipped rather than plotted.
    expect(readPoints({ index: [0, 1], values: [1, "NaN"] })).toEqual([{ x: 0, y: 1 }]);
  });
});

describe("core.series.basic — the plotted line", () => {
  it("breaks the line where samples are missing rather than drawing across", async () => {
    const { lineData } = await loadPanelModule();
    // Source values 0..3 with index 1 dropped: the plotted points are the three
    // that survived, and the line must show the absence between them.
    const { xs, ys } = lineData(
      [
        { x: 0, y: 0 },
        { x: 2, y: 2 },
        { x: 3, y: 3 },
      ],
      [1],
      [0, 2, 3],
    );
    expect(xs).toEqual([0, null, 2, 3]);
    expect(ys).toEqual([0, null, 2, 3]);
  });

  it("plots a complete series unbroken", async () => {
    const { lineData } = await loadPanelModule();
    const { xs, ys } = lineData(POINTS, [], [0, 1, 2]);
    expect(xs).toEqual([0, 1, 2]);
    expect(ys).toEqual([1, 4, 9]);
  });

  it("places a gap by its source position, not by how many points came back", async () => {
    const { lineData } = await loadPanelModule();
    /*
     * A series longer than the read's budget comes back decimated, while the
     * dropped positions stay in source coordinates. Counting returned points
     * put the break in the wrong place — or, for a gap late in a long series,
     * never reached it at all and drew the curve continuous across missing
     * data, which is the failure the gap notice exists to prevent.
     */
    const sampled = [
      { x: 0, y: 0 },
      { x: 100, y: 1 },
      { x: 200, y: 2 },
    ];
    const { xs } = lineData(sampled, [150], [0, 100, 200]);
    expect(xs).toEqual([0, 100, null, 200]);

    // A drop that falls outside every returned interval breaks nothing.
    expect(lineData(sampled, [300], [0, 100, 200]).xs).toEqual([0, 100, 200]);
    // Several drops between the same pair of points are one break.
    expect(lineData(sampled, [10, 20, 30], [0, 100, 200]).xs).toEqual([0, null, 100, 200]);
  });

  it("works out the source positions itself for a complete read", async () => {
    const { inferSourceIndices } = await loadPanelModule();
    // Three finite points with source index 1 dropped: 0, 2, 3.
    expect(inferSourceIndices(3, [1])).toEqual([0, 2, 3]);
    // Consecutive drops at the start push everything along.
    expect(inferSourceIndices(2, [0, 1])).toEqual([2, 3]);
    expect(inferSourceIndices(3, [])).toEqual([0, 1, 2]);
  });
});

describe("core.series.basic — the rendered surface", () => {
  it("charts the points, with gaps left open", async () => {
    const calls = stubPlotly();
    stubHost(seriesRead(POINTS, { total: 4, nonnumeric: 1, nonfinite_positions: [1] }));
    await loadPanelModule();
    await vi.waitFor(() => expect(calls.length).toBeGreaterThan(0));

    const trace = calls[calls.length - 1].data[0];
    expect(trace.type).toBe("scatter");
    expect(trace.mode).toBe("lines+markers");
    // Plotly joins across nulls unless told not to; the gap must stay a gap.
    expect(trace.connectgaps).toBe(false);
    expect(trace.x).toEqual([0, null, 1, 2]);
  });

  it("shows the gap notice above the chart", async () => {
    stubPlotly();
    stubHost(seriesRead(POINTS, { total: 5, nonnumeric: 2, nonfinite_positions: [1, 4] }));
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
    expect([...root().querySelectorAll("tbody tr")].length).toBe(3);

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
