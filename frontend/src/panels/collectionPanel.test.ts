/**
 * Behaviour contract for core.collection.basic.
 *
 * Carries over the assertion the compiled CollectionViewer held — an item card
 * shows its source filename, never the data ref — and pins the two defects live
 * testing found in the panel that replaced it: cards labelled `data-8f2a…`, and
 * a card left permanently disabled after drilling into it. Paging to every item
 * (#1886 item B) is pinned here too: the viewer stopped at the first page and
 * flagged the rest as "sampled".
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.collection.basic");
const PREACT = resolve(PANELS, "lib/preact-htm@3.1.1/dist/preact-standalone.module.js");
const PANEL_UI = resolve(PANELS, "sdk/1/panel-ui.js");

const dataUrl = (src: string) =>
  `data:text/javascript;base64,${Buffer.from(src).toString("base64")}`;

let loadCount = 0;

/** Load the panel the way the frame does: real Preact, real component set. */
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

interface HostOptions {
  input?: Record<string, unknown>;
  reads?: Record<string, unknown | (() => unknown)>;
  open?: (ref: string) => Promise<unknown>;
}

function stubHost(opts: HostOptions = {}) {
  const ops: Array<{ op: string; params: Record<string, unknown> }> = [];
  const opened: string[] = [];
  const api = {
    input: opts.input ?? {},
    viewState: undefined as unknown,
    ready: () => Promise.resolve(api),
    read: (op: string, params: Record<string, unknown> = {}) => {
      ops.push({ op, params });
      const reads = opts.reads ?? {};
      if (!Object.prototype.hasOwnProperty.call(reads, op)) {
        return Promise.reject(Object.assign(new Error(`no read ${op}`), { code: "not_found" }));
      }
      const value = reads[op];
      return Promise.resolve(typeof value === "function" ? (value as () => unknown)() : value);
    },
    setViewState: vi.fn(),
    reportError: vi.fn(() => Promise.resolve(null)),
    open: vi.fn((ref: string) => {
      opened.push(ref);
      return opts.open ? opts.open(ref) : Promise.resolve(null);
    }),
    save: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  document.body.innerHTML = '<div id="root"></div>';
  return { api, ops, opened };
}

const root = () => document.getElementById("root") as HTMLElement;
const card = (i: number) =>
  root().querySelector(`[data-testid=collection-item-${i}]`) as HTMLButtonElement | null;

function makeItems(from: number, to: number, extra: Record<string, unknown> = {}) {
  return Array.from({ length: to - from }, (_, i) => ({
    ref: `c/item-${from + i}`,
    type_name: "Image",
    kind: "data_ref",
    ...extra,
  }));
}

beforeAll(() => {
  stubHost();
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.collection.basic — item labels", () => {
  it("prefers the backend-resolved display name", async () => {
    const { itemLabel } = await loadPanelModule();
    expect(
      itemLabel({ ref: "data-2330b123", display_name: "sample.tif", metadata: {} }),
    ).toBe("sample.tif");
  });

  it("derives the source filename from loader metadata, not the data ref", async () => {
    const { itemLabel } = await loadPanelModule();
    // The assertion the compiled viewer carried, including the Windows path the
    // loader records.
    expect(
      itemLabel({
        data_ref: "data-2330b123456789",
        metadata: {
          framework: {
            source: "C:/Users/<user>/Desktop/workspace/Example/array/random_10x30x30x30_float32.npy",
          },
        },
      }),
    ).toBe("random_10x30x30x30_float32.npy");

    expect(itemLabel({ ref: "r", metadata: { source_file: "/data/scan_01.tif" } })).toBe("scan_01.tif");
    expect(itemLabel({ ref: "r", metadata: { meta: { file_path: "/data/b/plate.csv" } } })).toBe("plate.csv");
    expect(itemLabel({ ref: "r", metadata: { user: { display_name: "Sheet 2" } } })).toBe("Sheet 2");
  });

  it("treats a package name as provenance, not a filename", async () => {
    const { itemLabel } = await loadPanelModule();
    // `framework.source` is a package id here, so it must not become the label.
    const label = itemLabel({
      ref: "data-abcdef0123",
      metadata: { framework: { source: "scistudio-blocks-spectroscopy" } },
    });
    expect(label).not.toBe("scistudio-blocks-spectroscopy");
    expect(label).toBe("data-abcde");
  });
});

describe("core.collection.basic — the rendered surface", () => {
  const input = {
    ref: "c",
    kind: "collection_ref",
    count: 2,
    item_type: "Array",
    items: [
      {
        data_ref: "data-2330b123456789",
        type_name: "Array",
        metadata: { framework: { source: "/w/Example/array/random_10x30x30x30_float32.npy" } },
      },
      { data_ref: "data-99ff00aa1122", type_name: "Array", display_name: "second.npy" },
    ],
  };

  it("labels each card with its filename and keeps the ref only as a tooltip", async () => {
    stubHost({ input });
    await loadPanelModule();
    await vi.waitFor(() => expect(card(0)).toBeTruthy());

    expect(card(0)?.textContent).toContain("random_10x30x30x30_float32.npy");
    expect(card(1)?.textContent).toContain("second.npy");
    // The raw ref is never the visible label.
    expect(root().textContent).not.toContain("data-2330b123456789");
    expect(card(0)?.getAttribute("title")).toBe("data-2330b123456789");
  });

  it("shows the item type under the name and summarises the collection", async () => {
    stubHost({ input });
    await loadPanelModule();
    await vi.waitFor(() => expect(card(0)).toBeTruthy());

    expect(card(0)?.textContent).toContain("Array");
    const summary = root().querySelector("[data-testid=collection-summary]")?.textContent ?? "";
    expect(summary).toContain("2");
    expect(summary).toContain("Array");
    expect(summary).toContain("showing 2");
  });

  it("keeps the tutorial target attributes the viewer exposed", async () => {
    stubHost({ input });
    await loadPanelModule();
    await vi.waitFor(() => expect(card(0)).toBeTruthy());
    expect(card(0)?.getAttribute("data-tutorial-target")).toBe("preview_item");
    expect(card(0)?.getAttribute("data-tutorial-target-key")).toBe("0");
  });
});

describe("core.collection.basic — drill-down", () => {
  const input = {
    ref: "c",
    count: 1,
    item_type: "Image",
    items: [{ ref: "c/item-0", type_name: "Image", display_name: "a.tif" }],
  };

  it("opens the clicked item", async () => {
    const { opened } = stubHost({ input });
    await loadPanelModule();
    await vi.waitFor(() => expect(card(0)).toBeTruthy());

    card(0)!.click();
    await vi.waitFor(() => expect(opened).toEqual(["c/item-0"]));
  });

  it("leaves the card clickable after opening it", async () => {
    const { opened } = stubHost({ input });
    await loadPanelModule();
    await vi.waitFor(() => expect(card(0)).toBeTruthy());

    card(0)!.click();
    await vi.waitFor(() => expect(opened.length).toBe(1));
    // The reader returns to this panel from the child view; a card that stayed
    // disabled could never be opened again.
    expect(card(0)?.disabled).toBe(false);
    card(0)!.click();
    await vi.waitFor(() => expect(opened.length).toBe(2));
  });

  it("reports a failed open instead of swallowing it", async () => {
    const { api } = stubHost({ input, open: () => Promise.reject(new Error("nope")) });
    await loadPanelModule();
    await vi.waitFor(() => expect(card(0)).toBeTruthy());

    card(0)!.click();
    await vi.waitFor(() => expect(api.reportError).toHaveBeenCalled());
  });
});

describe("core.collection.basic — every item is reachable (#1886 B)", () => {
  it("pages past the first batch until the collection is fully listed", async () => {
    const { ops } = stubHost({
      input: {
        ref: "c",
        count: 150,
        item_type: "Image",
        items: makeItems(0, 100),
        next_cursor: "c1",
      },
      reads: {
        "collection.items": { count: 150, items: makeItems(100, 150), next_cursor: null },
      },
    });
    await loadPanelModule();

    // The viewer this replaces stopped at 100 and showed a "sampled" badge.
    await vi.waitFor(() => expect(card(149)).toBeTruthy());
    expect(card(100)).toBeTruthy();
    expect(root().querySelector("[data-testid=collection-summary]")?.textContent).toContain(
      "showing 150",
    );
    expect(root().textContent?.toLowerCase()).not.toContain("sampled");
    expect(ops.filter((o) => o.op === "collection.items").length).toBeGreaterThan(0);
  });

  it("stops when a cursor returns no further items", async () => {
    const { ops } = stubHost({
      input: { ref: "c", count: 500, item_type: "Image", items: makeItems(0, 10), next_cursor: "c1" },
      // A cursor that keeps pointing forward while returning nothing must not
      // spin: an empty page ends the walk.
      reads: { "collection.items": { count: 500, items: [], next_cursor: "c2" } },
    });
    await loadPanelModule();
    await vi.waitFor(() => expect(card(0)).toBeTruthy());
    await new Promise((r) => setTimeout(r, 60));
    expect(ops.filter((o) => o.op === "collection.items").length).toBe(1);
  });

  it("surfaces a failed page read", async () => {
    const { api } = stubHost({
      input: { ref: "c", count: 200, item_type: "Image", items: makeItems(0, 100), next_cursor: "c1" },
      reads: {},
    });
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector(".panel-error")).toBeTruthy());
    expect(root().textContent).toContain("Could not read collection");
    expect(api.reportError).toHaveBeenCalled();
  });
});

describe("core.collection.basic — empty collection", () => {
  it("says so rather than rendering an empty grid", async () => {
    stubHost({ input: { ref: "c", count: 0, item_type: "Image", items: [] } });
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=collection-empty]")).toBeTruthy(),
    );
  });
});
