/**
 * Behaviour contract for core.interactive.data_router.
 *
 * Carries over what the compiled DataRouterModal did (#591) and pins the shape
 * the DataRouter block consumes: every declared output port present, empty when
 * nothing was routed to it, so the block produces every output it declared.
 *
 * Cancel is deliberately absent from this panel. The window around the frame
 * offers it, outside the frame, so that no panel can fail to provide a way out;
 * a panel that needs to withdraw from code calls `api.cancel()`.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const PANELS = resolve(process.cwd(), "../src/scistudio/panels");
const PANEL = resolve(PANELS, "builtin/core.interactive.data_router");
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
const confirm = () => testid("router-confirm") as HTMLButtonElement;

/** jsdom has no DataTransfer, so carry the ref on a stub the handler reads. */
function drop(target: Element, ref: string) {
  const event = new Event("drop", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "dataTransfer", {
    value: { getData: () => ref, setData: () => {}, dropEffect: "", effectAllowed: "" },
  });
  target.dispatchEvent(event);
}

beforeAll(() => {
  stubHost();
});

afterEach(() => {
  document.body.innerHTML = "";
  vi.resetModules();
});

describe("core.interactive.data_router — routing arithmetic", () => {
  it("seeds every declared output port, so none is missing from the decision", async () => {
    const { emptyAssignments } = await loadPanelModule();
    expect(emptyAssignments(["kept", "discarded"])).toEqual({ kept: [], discarded: [] });
    expect(emptyAssignments(undefined)).toEqual({});
  });

  it("moves an item rather than copying it to a second port", async () => {
    const { assignTo } = await loadPanelModule();
    const once = assignTo({ kept: [], discarded: [] }, "a", "kept");
    const twice = assignTo(once, "a", "discarded");
    // Leaving the old entry behind would send one item to two outputs.
    expect(twice).toEqual({ kept: [], discarded: ["a"] });
  });

  it("ignores a port the block never declared", async () => {
    const { assignTo } = await loadPanelModule();
    const start = { kept: [] };
    expect(assignTo(start, "a", "invented")).toBe(start);
  });

  it("puts an item back in play when it is unassigned", async () => {
    const { assignTo, unassignRef, unassigned } = await loadPanelModule();
    const items = [{ ref: "a" }, { ref: "b" }];
    const routed = assignTo({ kept: [], discarded: [] }, "a", "kept");
    expect(unassigned(items, routed)).toEqual([{ ref: "b" }]);
    expect(unassigned(items, unassignRef(routed, "a"))).toEqual(items);
  });
});

describe("core.interactive.data_router — the surface", () => {
  it("shows one drop zone per output port and one chip per waiting item", async () => {
    stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("router-status")).toBeTruthy());

    expect(testid("router-output-kept")).toBeTruthy();
    expect(testid("router-output-discarded")).toBeTruthy();
    expect(testid("router-item-input_1:0")).toBeTruthy();
    expect(testid("router-item-input_2:0")).toBeTruthy();
    expect(testid("router-status")?.textContent).toContain("3 item(s) not yet assigned");
  });

  it("keeps Confirm out of reach until every item is routed", async () => {
    stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(confirm()).toBeTruthy());
    expect(confirm().disabled).toBe(true);

    drop(testid("router-output-kept")!, "input_1:0");
    drop(testid("router-output-discarded")!, "input_1:1");
    await vi.waitFor(() => expect(testid("router-status")?.textContent).toContain("1 item(s)"));
    expect(confirm().disabled).toBe(true);

    drop(testid("router-output-kept")!, "input_2:0");
    await vi.waitFor(() => expect(confirm().disabled).toBe(false));
    expect(testid("router-status")?.textContent).toBe("All items assigned");
  });

  it("submits the shape the block consumes, empty ports included", async () => {
    const api = stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(confirm()).toBeTruthy());

    drop(testid("router-output-kept")!, "input_1:0");
    drop(testid("router-output-kept")!, "input_1:1");
    drop(testid("router-output-kept")!, "input_2:0");
    await vi.waitFor(() => expect(confirm().disabled).toBe(false));
    confirm().click();

    expect(api.writeBack).toHaveBeenCalledWith({
      assignments: { kept: ["input_1:0", "input_1:1", "input_2:0"], discarded: [] },
    });
  });

  it("takes an item back when it is dropped on the inputs again", async () => {
    stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(testid("router-inputs")).toBeTruthy());

    drop(testid("router-output-kept")!, "input_1:0");
    await vi.waitFor(() => expect(testid("router-status")?.textContent).toContain("2 item(s)"));

    drop(testid("router-inputs")!, "input_1:0");
    await vi.waitFor(() => expect(testid("router-status")?.textContent).toContain("3 item(s)"));
  });
});

describe("core.interactive.data_router — leaving without deciding", () => {
  it("draws no Cancel of its own", async () => {
    stubHost();
    await loadPanelModule();
    await vi.waitFor(() => expect(confirm()).toBeTruthy());

    /*
     * The way out belongs to the window around the frame, where a panel cannot
     * fail to provide it or hide it. A second one in here would be a duplicate
     * control, and would suggest the guarantee lives in the panel.
     */
    const labels = [...root().querySelectorAll("button")].map((b) => b.textContent?.trim());
    expect(labels).not.toContain("Cancel");
  });
});
