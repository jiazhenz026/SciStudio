/**
 * Pointing a tutorial step into a panel frame (ADR-054).
 *
 * Six steps of `what-is-a-type` point at `preview_item` or `plot_export_button`.
 * Both moved inside panels in Phase B, and the host's measurement walks its own
 * document, so both stopped resolving — silently, because a target that is not
 * found degrades to a centred card with no ring rather than to an error. These
 * pin the arithmetic and the lifecycle that make them resolve again.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  forgetPanelHighlight,
  panelHighlightRect,
  reportPanelHighlight,
  requestPanelHighlight,
  resetPanelHighlights,
  subscribePanelHighlight,
} from "./panelHighlights";

/** A frame at a known place on screen, with a controllable connectedness. */
function frameAt(top: number, left: number, width = 800, height = 600): HTMLIFrameElement {
  const element = document.createElement("iframe");
  element.getBoundingClientRect = () =>
    ({
      top,
      left,
      width,
      height,
      right: left + width,
      bottom: top + height,
      x: left,
      y: top,
    }) as DOMRect;
  document.body.appendChild(element);
  return element;
}

afterEach(() => {
  resetPanelHighlights();
  document.body.innerHTML = "";
});

const STEP = Symbol("step-tracker");
const STAGE = Symbol("stage-tracker");

describe("asking a frame to measure", () => {
  it("tells listeners what is wanted, and says so again when it changes", () => {
    const seen: Array<string | null> = [];
    subscribePanelHighlight((request) => seen.push(request?.target ?? null));
    // A subscriber learns the current request on subscribing, so a frame that
    // mounts mid-step starts measuring without waiting for the next change.
    expect(seen).toEqual([null]);

    requestPanelHighlight(STEP, { target: "preview_item", key: "0" });
    requestPanelHighlight(STEP, { target: "preview_item", key: "0" }); // unchanged
    requestPanelHighlight(STEP, null);

    expect(seen).toEqual([null, "preview_item", null]);
  });

  it("tells them apart by key, so one card of a batch can be named", () => {
    const seen: Array<string | null> = [];
    subscribePanelHighlight((request) => seen.push(request?.key ?? null));
    requestPanelHighlight(STEP, { target: "preview_item", key: "0" });
    requestPanelHighlight(STEP, { target: "preview_item", key: "3" });
    expect(seen).toEqual([null, "0", "3"]);
  });

  it("keeps one tracker's request when a second tracker asks for nothing", () => {
    /*
     * `ActiveStep` runs two trackers: the step's own target, and the stage the
     * dialogue is drawn on. The stage is always in the host document, so its
     * tracker asks for nothing — and with a single shared slot it still cleared
     * the step's request, leaving the frame measuring nothing and the step
     * pointing at empty space with no error anywhere.
     */
    const seen: Array<string | null> = [];
    subscribePanelHighlight((request) => seen.push(request?.target ?? null));
    requestPanelHighlight(STEP, { target: "preview_item", key: "0" });
    requestPanelHighlight(STAGE, null);

    expect(seen).toEqual([null, "preview_item"]);
  });

  it("does not let a second tracker's target displace the first's", () => {
    const seen: Array<string | null> = [];
    subscribePanelHighlight((request) => seen.push(request?.target ?? null));
    requestPanelHighlight(STEP, { target: "preview_item", key: "0" });
    requestPanelHighlight(STAGE, { target: "workspace_stage", key: null });

    // The first asker still wanting something wins, so the answer does not
    // depend on which component happened to render second.
    expect(seen).toEqual([null, "preview_item"]);
  });

  it("hands over to the other tracker only once the first is done", () => {
    const seen: Array<string | null> = [];
    subscribePanelHighlight((request) => seen.push(request?.target ?? null));
    requestPanelHighlight(STEP, { target: "preview_item", key: "0" });
    requestPanelHighlight(STAGE, { target: "plot_export_button", key: null });
    requestPanelHighlight(STEP, null);

    expect(seen).toEqual([null, "preview_item", "plot_export_button"]);
  });
});

describe("turning a frame-local box into a host one", () => {
  it("adds the frame's own position, read at the time of asking", () => {
    const frame = frameAt(100, 50);
    requestPanelHighlight(STEP, { target: "plot_export_button", key: null });
    reportPanelHighlight(
      frame,
      { target: "plot_export_button", key: null },
      { top: 10, left: 20, width: 60, height: 24 },
    );

    expect(panelHighlightRect("plot_export_button", null)).toEqual({
      top: 110,
      left: 70,
      width: 60,
      height: 24,
    });
  });

  it("follows the frame when the host scrolls, with no new report", () => {
    const frame = frameAt(100, 50);
    reportPanelHighlight(
      frame,
      { target: "x", key: null },
      { top: 10, left: 0, width: 5, height: 5 },
    );
    expect(panelHighlightRect("x", null)?.top).toBe(110);

    // The host scrolled; only the frame moved, and the panel has no way to know.
    frame.getBoundingClientRect = () => ({ top: 40, left: 50, width: 800, height: 600 }) as DOMRect;
    expect(panelHighlightRect("x", null)?.top).toBe(50);
  });

  it("answers only for the target and key that were asked about", () => {
    const frame = frameAt(0, 0);
    reportPanelHighlight(
      frame,
      { target: "preview_item", key: "0" },
      { top: 1, left: 1, width: 2, height: 2 },
    );

    expect(panelHighlightRect("preview_item", "0")).not.toBeNull();
    expect(panelHighlightRect("preview_item", "1")).toBeNull();
    expect(panelHighlightRect("plot_export_button", null)).toBeNull();
  });

  it("reports nothing for a target the frame says it does not have", () => {
    const frame = frameAt(0, 0);
    reportPanelHighlight(
      frame,
      { target: "x", key: null },
      { top: 1, left: 1, width: 2, height: 2 },
    );
    reportPanelHighlight(frame, { target: "x", key: null }, null);
    expect(panelHighlightRect("x", null)).toBeNull();
  });
});

describe("not pointing at a frame that is gone", () => {
  it("ignores a frame that has left the document", () => {
    const frame = frameAt(0, 0);
    reportPanelHighlight(
      frame,
      { target: "x", key: null },
      { top: 1, left: 1, width: 2, height: 2 },
    );
    frame.remove();
    // Otherwise a closed panel would keep a ring on screen over whatever
    // replaced it.
    expect(panelHighlightRect("x", null)).toBeNull();
  });

  it("ignores a frame that is mounted but not laid out", () => {
    const frame = frameAt(0, 0, 0, 0);
    reportPanelHighlight(
      frame,
      { target: "x", key: null },
      { top: 1, left: 1, width: 2, height: 2 },
    );
    expect(panelHighlightRect("x", null)).toBeNull();
  });

  it("forgets a frame on request", () => {
    const frame = frameAt(0, 0);
    reportPanelHighlight(
      frame,
      { target: "x", key: null },
      { top: 1, left: 1, width: 2, height: 2 },
    );
    forgetPanelHighlight(frame);
    expect(panelHighlightRect("x", null)).toBeNull();
  });

  it("drops every report when the step stops pointing at anything", () => {
    const frame = frameAt(0, 0);
    requestPanelHighlight(STEP, { target: "x", key: null });
    reportPanelHighlight(
      frame,
      { target: "x", key: null },
      { top: 1, left: 1, width: 2, height: 2 },
    );
    requestPanelHighlight(STEP, null);
    // A stale box from the previous step must not answer the next one.
    expect(panelHighlightRect("x", null)).toBeNull();
  });
});

describe("the key a step addresses an element by", () => {
  it("is the argument the target is keyed on, or null", async () => {
    const { tutorialTargetKey } = await import("../components/LearningCenter.parts/targets");
    // `preview_item` is keyed by position in the batch.
    expect(tutorialTargetKey("preview_item", { index: "2" })).toBe("2");
    // `plot_export_button` annotates one element, so it has no key.
    expect(tutorialTargetKey("plot_export_button", {})).toBeNull();
    // A keyed target with the argument missing matches any of its elements.
    expect(tutorialTargetKey("preview_item", {})).toBeNull();
  });

  it("still builds the selector the host document is searched with", async () => {
    const { tutorialTargetSelector } = await import("../components/LearningCenter.parts/targets");
    // The key goes through `CSS.escape`, which escapes a leading digit — hence
    // `\32 ` for "2". The frame matches on the raw value instead, which is why
    // the key travels to it unescaped rather than as a finished selector.
    expect(tutorialTargetSelector("preview_item", { index: "2" })).toBe(
      '[data-tutorial-target="preview_item"][data-tutorial-target-key="\\32 "]',
    );
    expect(tutorialTargetSelector("run_button")).toBe('[data-tutorial-target="run_button"]');
  });
});

describe("the panels that carry these targets still mark them", () => {
  it("keeps the marks the tutorial names", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const sdk = resolve(process.cwd(), "../src/scistudio/panels/sdk/1");

    const collection = readFileSync(resolve(sdk, "renderer-collection.js"), "utf8");
    expect(collection).toContain('data-tutorial-target="preview_item"');
    // Keyed by position, so a step can ring the first card rather than the grid.
    expect(collection).toContain("data-tutorial-target-key");

    const plot = readFileSync(resolve(sdk, "renderer-plot.js"), "utf8");
    expect(plot).toContain('data-tutorial-target="plot_export_button"');
  });

  it("measures only while a step is pointing into the frame", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const sdk = readFileSync(
      resolve(process.cwd(), "../src/scistudio/panels/sdk/1/scistudio-panel.js"),
      "utf8",
    );
    // The loop is started by the host's request and cancelled with it, so a
    // panel nobody points at runs no per-frame work.
    expect(sdk).toContain('data.type === "highlight"');
    expect(sdk).toContain("cancelAnimationFrame");
  });
});

describe("the bridge only accepts a well-formed report", () => {
  it("passes a numeric box through and rejects anything else", async () => {
    const { createPanelBridge } = await import("./bridge");
    const channel = new MessageChannel();
    const highlightRect = vi.fn();
    const context = {
      context_id: "c",
      kind: "preview" as const,
      operations: ["read"],
      services: [],
      input: { ref: "r" },
      panel: { id: "p", name: "p", api_version: "1.0" },
      entry_url: "",
      sdk_url: "",
      lib_base_url: "",
    };
    createPanelBridge(channel.port1, context as never, {
      read: () => Promise.resolve(null),
      open: () => Promise.resolve(null),
      writeBack: () => Promise.resolve(null),
      save: () => Promise.resolve(null),
      viewState: () => {},
      resize: () => {},
      highlightRect,
      ready: () => {},
      failure: () => {},
    });

    channel.port2.postMessage({ v: 1, id: "1", type: "ready", payload: null });
    channel.port2.postMessage({
      v: 1,
      id: "2",
      type: "highlightRect",
      payload: { target: "preview_item", key: "0", rect: { top: 1, left: 2, width: 3, height: 4 } },
    });
    channel.port2.postMessage({
      v: 1,
      id: "3",
      type: "highlightRect",
      payload: { target: "preview_item", key: "0", rect: { top: "nope" } },
    });
    channel.port2.start();
    await vi.waitFor(() => expect(highlightRect).toHaveBeenCalledTimes(2));

    expect(highlightRect.mock.calls[0]).toEqual([
      { target: "preview_item", key: "0" },
      { top: 1, left: 2, width: 3, height: 4 },
    ]);
    // A box that is not numbers is "no box", not a box of NaN.
    expect(highlightRect.mock.calls[1][1]).toBeNull();
  });
});
