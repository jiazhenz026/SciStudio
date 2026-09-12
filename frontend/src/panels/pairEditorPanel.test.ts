/**
 * Behaviour contract for core.interactive.pair_editor.
 *
 * Carries over what the compiled PairEditorModal did (#594) and pins the shape
 * the PairEditor block consumes: each port's new order expressed as its items'
 * original indices.
 *
 * Two #1886 fixes are pinned here because a themed frame exposed what a
 * permanently white modal hid: a port with fewer items than the others left a
 * blank cell saying nothing, and every column was headed with the *shared*
 * length rather than its own, so a short port still claimed the full count.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.interactive.pair_editor");
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

const INPUT = {
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

function stubHost(input: Record<string, unknown> = INPUT) {
  const api = {
    context: "interactive",
    input,
    ready: () => Promise.resolve(api),
    writeBack: vi.fn((_value: Record<string, unknown>) => Promise.resolve(null)),
    cancel: vi.fn(() => Promise.resolve(null)),
    reportError: vi.fn(() => Promise.resolve(null)),
  };
  (window as unknown as { scistudio: unknown }).scistudio = api;
  document.body.innerHTML = '<div id="root"></div>';
  return api;
}

const root = () => document.getElementById("root") as HTMLElement;
const testid = (name: string) => root().querySelector(`[data-testid="${name}"]`);
const confirm = () => testid("pair-confirm") as HTMLButtonElement;

/** Drag a cell onto another row of the same port. */
function dragTo(from: Element, to: Element) {
  const transfer = { getData: () => "", setData: () => {}, dropEffect: "", effectAllowed: "" };
  for (const [type, target] of [
    ["dragstart", from],
    ["drop", to],
  ] as const) {
    const event = new Event(type, { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: transfer });
    target.dispatchEvent(event);
  }
}

beforeAll(() => {
  stubHost();
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.interactive.pair_editor — reordering arithmetic", () => {
  it("moves one item to another position within a port", async () => {
    const { moveWithin } = await loadPanelModule();
    expect(moveWithin([0, 1, 2], 0, 2)).toEqual([1, 2, 0]);
    expect(moveWithin([0, 1, 2], 2, 0)).toEqual([2, 0, 1]);
  });

  it("leaves the order alone for a move that is not one", async () => {
    const { moveWithin } = await loadPanelModule();
    const order = [0, 1, 2];
    expect(moveWithin(order, 1, 1)).toBe(order);
    expect(moveWithin(order, -1, 0)).toBe(order);
    expect(moveWithin(order, 0, 9)).toBe(order);
  });

  it("starts each port in the order its items arrived", async () => {
    const { initialOrders } = await loadPanelModule();
    expect(initialOrders(INPUT.ports, INPUT.items_per_port)).toEqual({
      input_1: [0, 1, 2],
      input_2: [0, 1, 2],
    });
  });

  it("shows every item a port holds, even beyond the declared length (#1886)", async () => {
    const { rowCount } = await loadPanelModule();
    expect(rowCount(3, ["a"], { a: [{ index: 0 }, { index: 1 }, { index: 2 }] })).toBe(3);
    // An item that exists but is off-screen cannot be reordered, and would be
    // submitted wherever it happened to start.
    expect(rowCount(2, ["a"], { a: [{ index: 0 }, { index: 1 }, { index: 2 }] })).toBe(3);
    // A payload that declares no length still shows what the ports hold — the
    // case that rendered an editor with nothing in it.
    expect(rowCount(0, ["a"], { a: [{ index: 0 }] })).toBe(1);
    expect(rowCount(undefined, ["a"], { a: [{ index: 0 }, { index: 1 }] })).toBe(2);
  });
});

describe("core.interactive.pair_editor — the surface", () => {
  it("shows one row per pairing position across every port", async () => {
    stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("pair-row-0")).toBeTruthy());

    expect(testid("pair-row-2")).toBeTruthy();
    expect(testid("pair-input_1-row-0")).toBeTruthy();
    expect(testid("pair-input_2-row-2")).toBeTruthy();
    expect(testid("pair-row-3")).toBeNull();
  });

  it("heads each column with that port's own count, not the shared length", async () => {
    stubHost({
      ports: ["input_1", "input_2"],
      items_per_port: {
        input_1: [
          { index: 0, name: "s0", type: "Image" },
          { index: 1, name: "s1", type: "Image" },
          { index: 2, name: "s2", type: "Image" },
        ],
        input_2: [{ index: 0, name: "m0", type: "Image" }],
      },
      collection_length: 3,
    });
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("pair-row-0")).toBeTruthy());

    // A port holding one of three said "(3)" before, which is the mismatch the
    // editor exists to show being hidden by the editor itself.
    const counts = [...root().querySelectorAll(".pair-count")].map((n) => n.textContent);
    expect(counts).toEqual(["(3)", "(1)"]);
  });

  it("says a port has no item on a row rather than leaving it blank (#1886)", async () => {
    stubHost({
      ports: ["input_1", "input_2"],
      items_per_port: {
        input_1: [
          { index: 0, name: "s0", type: "Image" },
          { index: 1, name: "s1", type: "Image" },
        ],
        input_2: [{ index: 0, name: "m0", type: "Image" }],
      },
      collection_length: 2,
    });
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("pair-row-1")).toBeTruthy());

    const gap = testid("pair-input_2-row-1");
    expect(gap).toBeTruthy();
    expect(gap?.textContent).toContain("no item on this row");
  });

  it("submits each port's new order as its items' original indices", async () => {
    const api = stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(confirm()).toBeTruthy());

    // Move input_1's first item down to the third row → [1, 2, 0].
    dragTo(testid("pair-input_1-row-0")!, testid("pair-input_1-row-2")!);
    await vi.waitFor(() =>
      expect(testid("pair-input_1-row-0")?.textContent).toContain("s1"),
    );
    confirm().click();

    expect(api.writeBack).toHaveBeenCalledWith({
      reorder: { input_1: [1, 2, 0], input_2: [0, 1, 2] },
    });
  });

  it("reorders within one port only", async () => {
    const api = stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(confirm()).toBeTruthy());

    // Dragging across ports would change which port an item came from, which is
    // not a thing this editor can express.
    dragTo(testid("pair-input_1-row-0")!, testid("pair-input_2-row-2")!);
    confirm().click();

    expect(api.writeBack).toHaveBeenCalledWith({
      reorder: { input_1: [0, 1, 2], input_2: [0, 1, 2] },
    });
  });
});

describe("core.interactive.pair_editor — leaving without deciding", () => {
  it("draws no Cancel of its own", async () => {
    stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(confirm()).toBeTruthy());
    const labels = [...root().querySelectorAll("button")].map((b) => b.textContent?.trim());
    expect(labels).not.toContain("Cancel");
  });
});
