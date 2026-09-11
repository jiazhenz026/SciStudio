/**
 * Faithful-display coverage for the core-tier builtin panels (ADR-054 Phase B,
 * #1886). Each panel's HTML+JS is loaded into jsdom with a stubbed
 * ``window.scistudio`` that answers reads from fixtures — the same contract the
 * real host and ``panel.sample.json`` provide — and the rendered DOM is asserted.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

const BUILTIN = resolve(process.cwd(), "../src/scistudio/panels/builtin");

interface MountOptions {
  input?: Record<string, unknown>;
  reads?: Record<string, unknown>;
  services?: string[];
}

function mount(panelId: string, opts: MountOptions = {}) {
  const source = readFileSync(resolve(BUILTIN, panelId, "panel.js"), "utf8");
  document.body.innerHTML = '<div id="root"></div>';
  const ops: string[] = [];
  const services = opts.services ?? ["open", "save"];
  const api: Record<string, unknown> = {
    input: opts.input ?? { ref: "r" },
    viewState: undefined,
    libBaseUrl: undefined,
    ready: () => Promise.resolve(api),
    read: (op: string) => {
      ops.push(op);
      const reads = opts.reads ?? {};
      return Object.prototype.hasOwnProperty.call(reads, op)
        ? Promise.resolve(reads[op])
        : Promise.reject(Object.assign(new Error("no read " + op), { code: "not_found" }));
    },
    setViewState: vi.fn(),
    reportError: vi.fn(() => Promise.resolve(null)),
    open: services.includes("open") ? vi.fn(() => Promise.resolve(null)) : undefined,
    save: services.includes("save") ? vi.fn(() => Promise.resolve(null)) : undefined,
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  (0, eval)(source);
  return { api, ops, root: () => document.getElementById("root") as HTMLElement };
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("core.array.basic — faithful native-resolution values (#1886 A/E)", () => {
  const reads = {
    "array.plane": {
      source_shape: [3, 3],
      source_dtype: "float64",
      dtype: "<f8",
      shape: [3, 3],
      axes: ["y", "x"],
      slice_axes: [],
      vmin: -1,
      vmax: 3,
      values: [
        [0, 1, "NaN"],
        [-1, 2, "Infinity"],
        ["-Infinity", 0.5, 3],
      ],
    },
    "array.tile": {
      source_shape: [3, 3],
      source_dtype: "float64",
      dtype: "<f8",
      shape: [3, 3],
      axes: ["y", "x"],
      slice_axes: [],
      y0: 0,
      x0: 0,
      height: 3,
      width: 3,
      values: [
        [0, 1, "NaN"],
        [-1, 2, "Infinity"],
        ["-Infinity", 0.5, 3],
      ],
    },
  };

  it("renders real cell values with NaN / ∞ / -∞ shown distinctly", async () => {
    const { root, ops } = mount("core.array.basic", {
      input: { ref: "a", kind: "data_ref" },
      reads,
    });
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=array-heatmap]")).toBeTruthy(),
    );
    const text = root().textContent ?? "";
    expect(text).toContain("NaN");
    expect(text).toContain("∞");
    expect(text).toContain("-∞");
    expect(root().querySelector("[data-testid=array-cell-0-0]")?.textContent).toBe("0");
    // The value surface is the native tile, never the strided plane overview.
    expect(ops).toContain("array.tile");
    // The plane is used only as a labelled navigation minimap.
    const mini = root().querySelector("[data-testid=array-minimap]");
    expect(mini).toBeTruthy();
    expect(root().textContent).toContain("navigation aid");
  });

  it("shows a vmin..vmax legend", async () => {
    const { root } = mount("core.array.basic", { input: { ref: "a" }, reads });
    await vi.waitFor(() => expect(root().querySelector("[data-testid=array-legend]")).toBeTruthy());
    expect(root().querySelector("[data-testid=array-legend-min]")?.textContent).toBe("-1");
    expect(root().querySelector("[data-testid=array-legend-max]")?.textContent).toBe("3");
  });
});

describe("core.collection.basic — pages to every item (#1886 B)", () => {
  it("reaches items past index 100 via the cursor path", async () => {
    const first = Array.from({ length: 100 }, (_, i) => ({
      ref: "c/item-" + i,
      type_name: "Image",
      kind: "data_ref",
    }));
    const rest = Array.from({ length: 50 }, (_, i) => ({
      ref: "c/item-" + (100 + i),
      type_name: "Image",
      kind: "data_ref",
    }));
    const { root } = mount("core.collection.basic", {
      input: {
        ref: "c",
        kind: "collection_ref",
        count: 150,
        item_type: "Image",
        items: first,
        next_cursor: "c1",
      },
      reads: {
        "collection.items": { count: 150, item_type: "Image", items: rest, next_cursor: null },
      },
    });
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=collection-item-149]")).toBeTruthy(),
    );
    expect(root().querySelector("[data-testid=collection-item-100]")).toBeTruthy();
    expect(root().querySelector("[data-testid=collection-summary]")?.textContent).toContain(
      "showing 150",
    );
  });
});

describe("core.series.basic — surfaces dropped NaN/inf points (#1886 D)", () => {
  it("names how many points were skipped and where", async () => {
    const { root } = mount("core.series.basic", {
      input: { ref: "s" },
      reads: {
        "series.points": {
          index: [0, 1, 3],
          values: [0, 1, 2],
          total: 4,
          nonnumeric: 1,
          sampled: false,
          decimation: "none",
          nonfinite_positions: [2],
          nonfinite_positions_complete: true,
        },
      },
    });
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=series-nonfinite-gaps]")).toBeTruthy(),
    );
    const gaps = root().querySelector("[data-testid=series-nonfinite-gaps]")?.textContent ?? "";
    expect(gaps).toContain("1 of 4");
    expect(gaps).toContain("2");
  });
});

describe("core.dataframe.basic — plain pager, no truncation badge (#1886 Part 1)", () => {
  it("shows rows range and page count with no incomplete badge", async () => {
    const { root } = mount("core.dataframe.basic", {
      input: { ref: "d" },
      reads: {
        "table.page": {
          columns: ["a", "b"],
          rows: [
            { a: 1, b: 2 },
            { a: 3, b: 4 },
          ],
          total: 2,
          total_rows: 2,
          page: 1,
          page_size: 50,
          total_pages: 1,
          sort: {},
        },
      },
    });
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=dataframe-summary]")).toBeTruthy(),
    );
    expect(root().querySelector("[data-testid=dataframe-summary]")?.textContent).toBe(
      "rows 1–2 of 2 · page 1/1",
    );
    expect(root().querySelector("[data-testid=preview-metadata-badges]")).toBeNull();
    expect(root().textContent).not.toContain("incomplete");
  });
});

describe("core.text.basic", () => {
  it("renders content and a truncation notice with the total size", async () => {
    const { root } = mount("core.text.basic", {
      input: { ref: "t" },
      reads: {
        "text.chunk": {
          text: "hello world",
          truncated: true,
          total_bytes: 4096,
          language: "txt",
          encoding: "utf-8",
          offset: 0,
          next_offset: 11,
        },
      },
    });
    await vi.waitFor(() => expect(root().querySelector("[data-testid=text-content]")).toBeTruthy());
    expect(root().querySelector("[data-testid=text-content]")?.textContent).toBe("hello world");
    expect(root().querySelector("[data-testid=text-truncation]")?.textContent).toContain(
      "4096 bytes",
    );
    expect(root().querySelector("[data-testid=text-load-more]")).toBeTruthy();
  });
});

describe("core.artifact.basic", () => {
  it("shows name, mime, size and an inline image", async () => {
    const { root } = mount("core.artifact.basic", {
      input: { ref: "art" },
      reads: {
        "artifact.info": { name: "pic.png", mime_type: "image/png", size: 2048 },
        "artifact.file": { name: "pic.png", mime_type: "image/png", url: "blob:pic" },
      },
    });
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=artifact-image]")).toBeTruthy(),
    );
    expect(root().querySelector("[data-testid=artifact-name]")?.textContent).toBe("pic.png");
    expect(root().querySelector("[data-testid=artifact-size]")?.textContent).toContain("2.0 KiB");
    expect(
      root().querySelector<HTMLImageElement>("[data-testid=artifact-image]")?.getAttribute("src"),
    ).toBe("blob:pic");
  });
});

describe("core.composite.basic", () => {
  it("lists slots and drills in via open", async () => {
    const { root, api } = mount("core.composite.basic", {
      input: { ref: "comp" },
      reads: {
        "composite.slots": { slots: [{ name: "raster", type_name: "Array", ref: "comp#raster" }] },
      },
    });
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=composite-slot-raster]")).toBeTruthy(),
    );
    (root().querySelector("[data-testid=composite-slot-raster]") as HTMLButtonElement).click();
    expect(api.open).toHaveBeenCalledWith("comp#raster");
  });
});

describe("core.plot.basic", () => {
  it("renders an image artifact with zoom and save controls", async () => {
    const { root, api } = mount("core.plot.basic", {
      input: { ref: "p", kind: "plot_artifact" },
      reads: {
        "artifact.info": { name: "plot.png", mime_type: "image/png", size: 100 },
        "artifact.file": {
          name: "plot.png",
          mime_type: "image/png",
          url: "blob:plot",
          data: new ArrayBuffer(8),
        },
      },
    });
    await vi.waitFor(() => expect(root().querySelector("[data-testid=plot-image]")).toBeTruthy());
    expect(
      root().querySelector<HTMLImageElement>("[data-testid=plot-image]")?.getAttribute("src"),
    ).toBe("blob:plot");
    expect(root().querySelector("[data-testid=plot-zoom-controls]")).toBeTruthy();
    (root().querySelector("[data-testid=plot-export-button]") as HTMLButtonElement).click();
    expect(api.save).toHaveBeenCalled();
  });
});

describe("core.base.fallback", () => {
  it("renders the type chain and metadata", async () => {
    const { root } = mount("core.base.fallback", {
      input: { ref: "o" },
      reads: {
        metadata: {
          type_chain: ["DataObject", "Mystery"],
          metadata: { k: "v" },
          shape: null,
          dtype: null,
        },
      },
    });
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=object-metadata]")).toBeTruthy(),
    );
    expect(root().querySelector("[data-testid=object-type]")?.textContent).toContain("Mystery");
    expect(root().querySelector("[data-testid=object-metadata]")?.textContent).toContain(
      '"k": "v"',
    );
  });
});
