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
    // Interactive panels (core.interactive.*) submit their decision here; a
    // preview panel never calls it, so the stub is harmless for both.
    writeBack: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  (0, eval)(source);
  return { api, ops, root: () => document.getElementById("root") as HTMLElement };
}

afterEach(() => {
  document.body.innerHTML = "";
});

// core.array.basic and core.collection.basic are ES modules built on the shared
// component set; they are covered by arrayPanel.test.ts and collectionPanel.test.ts,
// which load them the way the frame does instead of eval'ing a classic script.

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

// core.composite.basic is an ES module on the shared component set; it is
// covered by compositePanel.test.ts.

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

function panelHooks() {
  return (window as unknown as { __panel: Record<string, (...args: unknown[]) => unknown> })
    .__panel;
}

describe("core.interactive.data_router — parity with DataRouterModal (FR-041)", () => {
  const input = {
    input_ports: ["input_1", "input_2"],
    items_per_port: {
      input_1: [
        { index: 0, port: "input_1", ref: "input_1:0", name: "a.csv", type: "DataFrame" },
        { index: 1, port: "input_1", ref: "input_1:1", name: "b.csv", type: "DataFrame" },
      ],
      input_2: [{ index: 0, port: "input_2", ref: "input_2:0", name: "c.csv", type: "DataFrame" }],
    },
    output_ports: ["kept", "discarded"],
  };

  it("renders one drop zone per output port and one chip per unassigned item", async () => {
    const { root } = mount("core.interactive.data_router", { input });
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=router-status]")).toBeTruthy(),
    );
    expect(root().querySelector("[data-testid=router-output-kept]")).toBeTruthy();
    expect(root().querySelector("[data-testid=router-output-discarded]")).toBeTruthy();
    expect(root().querySelector('[data-testid="router-item-input_1:0"]')).toBeTruthy();
    expect(root().querySelector('[data-testid="router-item-input_2:0"]')).toBeTruthy();
  });

  it("keeps Confirm disabled until every item is assigned, then writes back {assignments}", async () => {
    const { root, api } = mount("core.interactive.data_router", { input });
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=router-confirm]")).toBeTruthy(),
    );
    const confirm = () => root().querySelector("[data-testid=router-confirm]") as HTMLButtonElement;
    expect(confirm().disabled).toBe(true);

    const panel = panelHooks();
    panel.assign("input_1:0", "kept");
    panel.assign("input_1:1", "discarded");
    panel.assign("input_2:0", "kept");
    expect(confirm().disabled).toBe(false);

    confirm().click();
    // The exact interactive_response shape the DataRouter block consumes: every
    // declared output port is present (empty [] when nothing was routed to it).
    expect(api.writeBack).toHaveBeenCalledWith({
      assignments: { kept: ["input_1:0", "input_2:0"], discarded: ["input_1:1"] },
    });
  });
});

describe("core.interactive.pair_editor — parity with PairEditorModal (FR-041)", () => {
  const input = {
    ports: ["input_1", "input_2"],
    items_per_port: {
      input_1: [
        { index: 0, name: "s0", type: "Image" },
        { index: 1, name: "s1", type: "Image" },
        { index: 2, name: "s2", type: "Image" },
      ],
      input_2: [
        { index: 0, name: "m0", type: "Image" },
        { index: 1, name: "m1", type: "Image" },
        { index: 2, name: "m2", type: "Image" },
      ],
    },
    collection_length: 3,
  };

  it("renders one row per pairing index across every port", async () => {
    const { root } = mount("core.interactive.pair_editor", { input });
    await vi.waitFor(() => expect(root().querySelector("[data-testid=pair-row-0]")).toBeTruthy());
    expect(root().querySelector("[data-testid=pair-row-2]")).toBeTruthy();
    expect(root().querySelector("[data-testid=pair-input_1-row-0]")).toBeTruthy();
    expect(root().querySelector("[data-testid=pair-input_2-row-2]")).toBeTruthy();
  });

  it("reorders within a port and writes back {reorder} as new original-index orders", async () => {
    const { root, api } = mount("core.interactive.pair_editor", { input });
    await vi.waitFor(() => expect(root().querySelector("[data-testid=pair-confirm]")).toBeTruthy());

    const panel = panelHooks();
    // Move input_1's first item (original index 0) down to row 2 → [1, 2, 0].
    panel.move("input_1", 0, 2);
    (root().querySelector("[data-testid=pair-confirm]") as HTMLButtonElement).click();

    // The exact interactive_response shape the PairEditor block consumes: each
    // port maps to its new order expressed as original item indices.
    expect(api.writeBack).toHaveBeenCalledWith({
      reorder: { input_1: [1, 2, 0], input_2: [0, 1, 2] },
    });
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
