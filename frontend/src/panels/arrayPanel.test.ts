/**
 * Behaviour contract for core.array.basic.
 *
 * These assertions are the ones the compiled ArrayViewer carried
 * (coreViewers.test.tsx): the numeric heatmap of real values, the colour scale,
 * cell formatting, the min..max legend, per-axis slice controls, and the 0-D and
 * 1-D display forms. The panel replaces that viewer, so the user-visible
 * behaviour must not change — only the data fidelity does (#1886 A/E): the cells
 * come from native-resolution reads rather than a decimated plane, and NaN/±inf
 * render distinctly instead of blank.
 *
 * The panel is an ES module that imports Preact and the shared component set by
 * their frame-relative paths, so it is loaded here the way the frame loads it
 * (see loadPanelModule) rather than eval'd as a classic script.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.array.basic");
const PREACT = resolve(PANELS, "lib/preact-htm@3.1.1/dist/preact-standalone.module.js");
const PANEL_UI = resolve(PANELS, "sdk/1/panel-ui.js");

const dataUrl = (src: string) =>
  `data:text/javascript;base64,${Buffer.from(src).toString("base64")}`;

/**
 * Load the panel with its frame-relative imports rewritten to data URLs, so the
 * real panel source runs against the real Preact and the real component set,
 * all sharing one Preact instance (hooks require that).
 */
async function loadPanelModule() {
  const preactUrl = dataUrl(readFileSync(PREACT, "utf8"));
  const uiUrl = dataUrl(
    readFileSync(PANEL_UI, "utf8").replace(
      /"[^"]*preact-standalone\.module\.js"/g,
      JSON.stringify(preactUrl),
    ),
  );
  const panelSrc = readFileSync(resolve(PANEL, "panel.js"), "utf8")
    .replace(/"[^"]*preact-standalone\.module\.js"/g, JSON.stringify(preactUrl))
    .replace(/"[^"]*panel-ui\.js"/g, JSON.stringify(uiUrl));
  // The panel renders as a side effect of loading, and a module URL is only
  // evaluated once — give each load a distinct URL so every test drives a fresh
  // mount against its own stub host.
  loadCount += 1;
  return import(/* @vite-ignore */ dataUrl(`${panelSrc}\n//# load-${loadCount}`));
}

let loadCount = 0;

interface Reads {
  [op: string]: unknown;
}

function stubHost(reads: Reads, input: Record<string, unknown> = { ref: "a", kind: "data_ref" }) {
  const ops: Array<{ op: string; params: Record<string, unknown> }> = [];
  const api = {
    input,
    viewState: undefined as unknown,
    ready: () => Promise.resolve(api),
    read: (op: string, params: Record<string, unknown> = {}) => {
      ops.push({ op, params });
      return Object.prototype.hasOwnProperty.call(reads, op)
        ? Promise.resolve(reads[op])
        : Promise.reject(Object.assign(new Error(`no read ${op}`), { code: "not_found" }));
    },
    setViewState: vi.fn(),
    reportError: vi.fn(() => Promise.resolve(null)),
    open: vi.fn(() => Promise.resolve(null)),
    save: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  document.body.innerHTML = '<div id="root"></div>';
  return { api, ops, root: () => document.getElementById("root") as HTMLElement };
}

const root = () => document.getElementById("root") as HTMLElement;
const cell = (r: number, c: number) =>
  root().querySelector(`[data-testid=array-cell-${r}-${c}]`) as HTMLElement | null;

/** A 3x3 float plane carrying one of each non-finite kind. */
const PLANE_3x3 = {
  source_shape: [3, 3],
  source_dtype: "float64",
  axes: ["y", "x"],
  slice_axes: [],
  vmin: -1,
  vmax: 3,
};
const TILE_3x3 = {
  ...PLANE_3x3,
  y0: 0,
  x0: 0,
  height: 3,
  width: 3,
  values: [
    [0, 1, "NaN"],
    [-1, 2, "Infinity"],
    ["-Infinity", 0.5, 3],
  ],
};

beforeAll(async () => {
  // Module-level side effects (the panel renders on api.ready()) must not run at
  // import time with no host, so the stub is installed before the first import.
  stubHost({});
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.array.basic — pure helpers keep the viewer's behaviour", () => {
  it("heatmapColor maps signed data to a diverging scale — negatives are NOT black", async () => {
    const { heatmapColor } = await loadPanelModule();
    const negative = heatmapColor(-1, -1, 1);
    const positive = heatmapColor(1, -1, 1);
    const zero = heatmapColor(0, -1, 1);
    expect(negative).toMatch(/^rgb\(/);
    expect(negative).not.toBe("rgb(0, 0, 0)");
    expect(negative).not.toBe(positive);
    // Zero sits at the white centre of the diverging ramp.
    expect(zero).toBe("rgb(247, 247, 247)");
  });

  it("heatmapColor uses a sequential scale for all-nonnegative data", async () => {
    const { heatmapColor } = await loadPanelModule();
    const low = heatmapColor(0, 0, 10);
    const high = heatmapColor(10, 0, 10);
    expect(low).not.toBe(high);
    expect(low).toMatch(/^rgb\(/);
  });

  it("heatmapColor renders non-finite values transparent", async () => {
    const { heatmapColor } = await loadPanelModule();
    for (const v of ["NaN", "Infinity", "-Infinity", null]) {
      expect(heatmapColor(v, -1, 1)).toBe("transparent");
    }
  });

  it("formatCell keeps small integers exact and uses an exponent for extremes", async () => {
    const { formatCell } = await loadPanelModule();
    expect(formatCell(0)).toBe("0");
    expect(formatCell(42)).toBe("42");
    expect(formatCell(1.5)).toBe("1.500");
    expect(formatCell(1e6)).toBe("1.00e+6");
    expect(formatCell(1e-9)).toBe("1.00e-9");
  });

  it("formatCell shows each non-finite kind distinctly, never blank (#1886 E)", async () => {
    const { formatCell } = await loadPanelModule();
    expect(formatCell("NaN")).toBe("NaN");
    expect(formatCell("Infinity")).toBe("∞");
    expect(formatCell("-Infinity")).toBe("-∞");
    expect(formatCell(null)).toBe("—");
  });

  it("displayAxes prefers named y/x and otherwise the last two axes", async () => {
    const { displayAxes } = await loadPanelModule();
    expect(displayAxes([4, 5], ["y", "x"], [])).toEqual({ y: 0, x: 1 });
    expect(displayAxes([2, 4, 5], [], [{ axis: 0 }])).toEqual({ y: 1, x: 2 });
    expect(displayAxes([7], [], [])).toEqual({ y: 0, x: 0 });
  });
});

describe("core.array.basic — the rendered surface", () => {
  it("renders the actual numeric values as cells with heatmap backgrounds", async () => {
    stubHost({ "array.plane": PLANE_3x3, "array.tile": TILE_3x3 });
    await loadPanelModule();
    await vi.waitFor(() => expect(cell(0, 0)).toBeTruthy());

    expect(cell(0, 0)?.textContent).toBe("0");
    expect(cell(0, 1)?.textContent).toBe("1");
    expect(cell(2, 2)?.textContent).toBe("3");
    // Every finite cell is tinted; the colour comes from the value, not a class.
    expect(cell(1, 1)?.getAttribute("style")?.replace(/\s+/g, "")).toContain("background:rgb(");
  });

  it("shows NaN / ∞ / -∞ instead of empty cells (#1886 E)", async () => {
    stubHost({ "array.plane": PLANE_3x3, "array.tile": TILE_3x3 });
    await loadPanelModule();
    await vi.waitFor(() => expect(cell(0, 2)).toBeTruthy());

    expect(cell(0, 2)?.textContent).toBe("NaN");
    expect(cell(1, 2)?.textContent).toBe("∞");
    expect(cell(2, 0)?.textContent).toBe("-∞");
    expect(cell(0, 2)?.getAttribute("title")).toBe("non-finite");
  });

  it("reads values from the native-resolution tile, not the strided plane (#1886 A)", async () => {
    const { ops } = stubHost({ "array.plane": PLANE_3x3, "array.tile": TILE_3x3 });
    await loadPanelModule();
    await vi.waitFor(() => expect(cell(0, 0)).toBeTruthy());

    const tileReads = ops.filter((o) => o.op === "array.tile");
    expect(tileReads.length).toBeGreaterThan(0);
    // No decimated stand-in is presented as the data: the plane read supplies
    // geometry and the faithful extent, the tile read supplies every value.
    expect(root().querySelector("[data-testid=array-minimap]")).toBeNull();
    expect(root().textContent).not.toContain("navigation aid");
  });

  it("shows the shape, dtype and axes summary", async () => {
    stubHost({ "array.plane": PLANE_3x3, "array.tile": TILE_3x3 });
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=array-info]")).toBeTruthy(),
    );
    const info = root().querySelector("[data-testid=array-info]")?.textContent ?? "";
    expect(info).toContain("Array");
    expect(info).toContain("shape [3, 3]");
    expect(info).toContain("dtype float64");
    expect(info).toContain("axes [y, x]");
  });

  it("shows the min and max value labels on the legend", async () => {
    stubHost({ "array.plane": PLANE_3x3, "array.tile": TILE_3x3 });
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector("[data-testid=array-legend]")).toBeTruthy());
    expect(root().querySelector("[data-testid=array-legend-min]")?.textContent).toBe("-1");
    expect(root().querySelector("[data-testid=array-legend-max]")?.textContent).toBe("3");
  });
});

describe("core.array.basic — display forms", () => {
  it("renders a scalar value for a 0-D array", async () => {
    stubHost({
      "array.plane": { source_shape: [], source_dtype: "float64", axes: [], slice_axes: [] },
      "array.tile": { y0: 0, x0: 0, height: 1, width: 1, values: [[7.5]] },
    });
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector("[data-testid=array-scalar]")).toBeTruthy());
    expect(root().querySelector("[data-testid=array-scalar]")?.textContent?.trim()).toBe("7.500");
  });

  it("renders a 1-D array as a single row with no vertical scroll", async () => {
    const plane = {
      source_shape: [120],
      source_dtype: "float64",
      axes: ["axis_0"],
      slice_axes: [],
      vmin: 0,
      vmax: 119,
    };
    const { ops } = stubHost({
      "array.plane": plane,
      "array.tile": { ...plane, y0: 0, x0: 0, height: 1, width: 3, values: [[0, 1, 2]] },
    });
    await loadPanelModule();
    await vi.waitFor(() => expect(cell(0, 0)).toBeTruthy());

    // One row: the backend's plane for a 1-D source is 1 x N, so a row read must
    // never be requested beyond it (that raised "Tile offsets must be within the
    // displayed plane").
    expect(root().querySelectorAll("tbody tr[data-row]").length).toBe(1);
    for (const read of ops.filter((o) => o.op === "array.tile")) {
      expect(read.params.y0).toBe(0);
      expect(Number(read.params.height)).toBeLessThanOrEqual(1);
    }
    expect(root().querySelector("[data-testid=array-grid-info]")?.textContent).toContain("120");
  });
});

describe("core.array.basic — per-axis slice controls", () => {
  const ND_PLANE = {
    source_shape: [10, 4, 5],
    source_dtype: "float64",
    axes: [],
    slice_axes: [{ axis: 0, name: "axis_0", size: 10, index: 0 }],
    vmin: 0,
    vmax: 1,
  };
  const ND_TILE = { ...ND_PLANE, y0: 0, x0: 0, height: 2, width: 2, values: [[0, 1], [1, 0]] };

  it("renders one control per non-displayed axis", async () => {
    stubHost({ "array.plane": ND_PLANE, "array.tile": ND_TILE });
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=array-slice-selectors]")).toBeTruthy(),
    );
    expect(root().querySelector("[data-testid=array-slice-row-0]")).toBeTruthy();
    expect(root().querySelector("[data-testid=array-slice-slider-0]")).toBeTruthy();
    expect(root().querySelector("[data-testid=array-slice-input-0]")).toBeTruthy();
    expect(root().querySelector("[data-testid=array-slice-row-0]")?.textContent).toContain(
      "axis_0 (10)",
    );
  });

  it("drives the handle on a continuous track, not index stops", async () => {
    stubHost({ "array.plane": ND_PLANE, "array.tile": ND_TILE });
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=array-slice-slider-0]")).toBeTruthy(),
    );
    const slider = root().querySelector("[data-testid=array-slice-slider-0]") as HTMLInputElement;
    // A normalised 0..1 track with a fine step: the browser cannot quantise the
    // thumb to index stops, which is what made dragging feel notched.
    expect(slider.min).toBe("0");
    expect(slider.max).toBe("1");
    expect(Number(slider.step)).toBeLessThanOrEqual(0.001);
  });

  it("re-reads the plane for the index the pointer lands on", async () => {
    const { ops } = stubHost({ "array.plane": ND_PLANE, "array.tile": ND_TILE });
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=array-slice-slider-0]")).toBeTruthy(),
    );
    const slider = root().querySelector("[data-testid=array-slice-slider-0]") as HTMLInputElement;
    slider.value = "0.5"; // half way along a size-10 axis -> index 5 (0..9)
    slider.dispatchEvent(new Event("input", { bubbles: true }));

    await vi.waitFor(() => {
      const planeReads = ops.filter((o) => o.op === "array.plane");
      expect(planeReads[planeReads.length - 1]?.params.axis_indices).toEqual({ 0: 5 });
    });
  });

  it("accepts a typed index and reads that slice", async () => {
    const { ops } = stubHost({ "array.plane": ND_PLANE, "array.tile": ND_TILE });
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=array-slice-input-0]")).toBeTruthy(),
    );
    const box = root().querySelector("[data-testid=array-slice-input-0]") as HTMLInputElement;
    box.value = "7";
    box.dispatchEvent(new Event("input", { bubbles: true }));

    await vi.waitFor(() => {
      const planeReads = ops.filter((o) => o.op === "array.plane");
      expect(planeReads[planeReads.length - 1]?.params.axis_indices).toEqual({ 0: 7 });
    });
  });
});

describe("core.array.basic — failure is surfaced, never silent", () => {
  it("reports a failed read instead of rendering an empty surface", async () => {
    const { api } = stubHost({});
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector(".panel-error")).toBeTruthy());
    expect(root().textContent).toContain("Could not read array");
    expect(api.reportError).toHaveBeenCalled();
  });
});
