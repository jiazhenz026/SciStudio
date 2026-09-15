/**
 * Behaviour contract for core.composite.basic.
 *
 * Carries over what the compiled CompositeViewer did — list the slot inventory,
 * show each slot's name over the type it holds, route to a child only when the
 * reader selects one, and never render a child itself — and pins the defect the
 * collection panel shared: a row disabled on click and never re-enabled, so a
 * slot could not be opened twice.
 */
import { readFileSync } from "node:fs";
import { rewriteRendererImports } from "./rendererTestModules";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.composite.basic");
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

interface HostOptions {
  reads?: Record<string, unknown>;
  open?: (ref: string) => Promise<unknown>;
  withOpen?: boolean;
}

function stubHost(opts: HostOptions = {}) {
  const ops: Array<{ op: string; params: Record<string, unknown> }> = [];
  const opened: string[] = [];
  const api: Record<string, unknown> = {
    input: { ref: "c", kind: "data_ref" },
    viewState: undefined,
    ready: () => Promise.resolve(api),
    read: (op: string, params: Record<string, unknown> = {}) => {
      ops.push({ op, params });
      const reads = opts.reads ?? {};
      return Object.prototype.hasOwnProperty.call(reads, op)
        ? Promise.resolve(reads[op])
        : Promise.reject(Object.assign(new Error(`no read ${op}`), { code: "not_found" }));
    },
    setViewState: vi.fn(),
    reportError: vi.fn(() => Promise.resolve(null)),
    save: vi.fn(() => Promise.resolve(null)),
  };
  if (opts.withOpen !== false) {
    api.open = vi.fn((ref: string) => {
      opened.push(ref);
      return opts.open ? opts.open(ref) : Promise.resolve(null);
    });
  }
  (window as unknown as { scistudio: unknown }).scistudio = api;
  document.body.innerHTML = '<div id="root"></div>';
  return { api, ops, opened };
}

const root = () => document.getElementById("root") as HTMLElement;
const slot = (name: string) =>
  root().querySelector(`[data-testid=composite-slot-${name}]`) as HTMLButtonElement | null;

const SLOTS = {
  slots: [
    { name: "corrected", type_name: "SpectralDataset", ref: "d#corrected" },
    { name: "baseline", type_name: "SpectralDataset", ref: "d#baseline" },
    { name: "notes", type_name: "Text", ref: "d#notes" },
  ],
};

beforeAll(() => {
  stubHost();
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.composite.basic — the slot inventory", () => {
  it("reads every page of a composite with more slots than one read carries (#2460)", async () => {
    const { api, ops } = stubHost();
    api.read = (op: string, params: Record<string, unknown> = {}) => {
      ops.push({ op, params });
      return Promise.resolve(
        params.cursor === "p2"
          ? {
              slots: [SLOTS.slots[2]],
              count: 3,
              next_cursor: null,
              truncated: false,
              complete: true,
            }
          : {
              slots: SLOTS.slots.slice(0, 2),
              count: 3,
              next_cursor: "p2",
              truncated: true,
              complete: false,
            },
      );
    };
    await loadPanelModule();
    await vi.waitFor(() => expect(slot("notes")).toBeTruthy());
    expect(root().querySelectorAll("[data-testid^=composite-slot-]").length).toBe(3);
    expect(ops.map((o) => o.params)).toEqual([{}, { cursor: "p2" }]);
  });

  it("lists one row per slot with its name and the type it holds", async () => {
    stubHost({ reads: { "composite.slots": SLOTS } });
    await loadPanelModule();
    await vi.waitFor(() => expect(slot("corrected")).toBeTruthy());

    expect(slot("corrected")?.textContent).toContain("corrected");
    expect(slot("corrected")?.textContent).toContain("SpectralDataset");
    expect(slot("notes")?.textContent).toContain("Text");
    expect(root().querySelectorAll("[data-testid^=composite-slot-]").length).toBe(3);
  });

  it("counts the slots, pluralising like the viewer did", async () => {
    stubHost({ reads: { "composite.slots": SLOTS } });
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=composite-summary]")).toBeTruthy(),
    );
    expect(root().querySelector("[data-testid=composite-summary]")?.textContent).toContain(
      "3 slots",
    );

    document.body.innerHTML = "";
    stubHost({ reads: { "composite.slots": { slots: [SLOTS.slots[0]] } } });
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=composite-summary]")).toBeTruthy(),
    );
    expect(root().querySelector("[data-testid=composite-summary]")?.textContent).toContain(
      "1 slot",
    );
  });

  it("reads the inventory and renders no child of its own", async () => {
    const { ops } = stubHost({ reads: { "composite.slots": SLOTS } });
    await loadPanelModule();
    await vi.waitFor(() => expect(slot("corrected")).toBeTruthy());

    // The composite lists and routes; a child is rendered by the host after the
    // reader selects a slot, never inline here.
    expect(ops.map((o) => o.op)).toEqual(["composite.slots"]);
  });

  it("offers the preview hint only when the host can route", async () => {
    stubHost({ reads: { "composite.slots": SLOTS } });
    await loadPanelModule();
    await vi.waitFor(() => expect(slot("corrected")).toBeTruthy());
    expect(slot("corrected")?.textContent).toContain("Preview →");

    document.body.innerHTML = "";
    stubHost({ reads: { "composite.slots": SLOTS }, withOpen: false });
    await loadPanelModule();
    await vi.waitFor(() => expect(slot("corrected")).toBeTruthy());
    expect(slot("corrected")?.textContent).not.toContain("Preview →");
  });
});

describe("core.composite.basic — drill-down", () => {
  it("opens the selected slot by its backend ref", async () => {
    const { opened } = stubHost({ reads: { "composite.slots": SLOTS } });
    await loadPanelModule();
    await vi.waitFor(() => expect(slot("baseline")).toBeTruthy());

    slot("baseline")!.click();
    await vi.waitFor(() => expect(opened).toEqual(["d#baseline"]));
  });

  it("leaves the row selectable after opening it", async () => {
    const { opened } = stubHost({ reads: { "composite.slots": SLOTS } });
    await loadPanelModule();
    await vi.waitFor(() => expect(slot("corrected")).toBeTruthy());

    slot("corrected")!.click();
    await vi.waitFor(() => expect(opened.length).toBe(1));
    expect(slot("corrected")?.disabled).toBe(false);
    slot("corrected")!.click();
    await vi.waitFor(() => expect(opened.length).toBe(2));
  });

  it("reports a failed open instead of swallowing it", async () => {
    const { api } = stubHost({
      reads: { "composite.slots": SLOTS },
      open: () => Promise.reject(new Error("unauthorized_ref")),
    });
    await loadPanelModule();
    await vi.waitFor(() => expect(slot("notes")).toBeTruthy());

    slot("notes")!.click();
    await vi.waitFor(() => expect(api.reportError).toHaveBeenCalled());
  });
});

describe("core.composite.basic — edge cases", () => {
  it("says so when the composite has no slots", async () => {
    stubHost({ reads: { "composite.slots": { slots: [] } } });
    await loadPanelModule();
    await vi.waitFor(() =>
      expect(root().querySelector("[data-testid=composite-empty]")).toBeTruthy(),
    );
  });

  it("surfaces a failed inventory read", async () => {
    const { api } = stubHost({ reads: {} });
    await loadPanelModule();
    await vi.waitFor(() => expect(root().querySelector(".panel-error")).toBeTruthy());
    expect(root().textContent).toContain("Could not read slots");
    expect(api.reportError).toHaveBeenCalled();
  });
});
