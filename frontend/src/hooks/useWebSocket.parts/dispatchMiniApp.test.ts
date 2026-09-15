/**
 * ADR-054 MiniApps (#2354) — the dispatcher's half of the MiniApp frames.
 *
 * The handlers are tested beside this file; what is tested here is the wiring,
 * which is the half that fails silently. A frame with no branch falls through
 * to `consumeEvent`, where it is an unknown workflow event and nothing happens
 * and nothing is logged — the same outcome as the backend never having sent it.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import * as panelEvents from "../../panels/panelEvents";
import { useAppStore } from "../../store";
import type { WorkflowEventMessage } from "../../types/api";

import { dispatchWorkflowEvent } from "./dispatchEvent";

/**
 * Install spies for the MiniApp store actions and hand them back.
 *
 * The actions belong to the store slice; this replaces them for the duration of
 * a test so the assertion is about the dispatcher's wiring rather than about
 * what the store does with the call.
 */
function spyOnStoreActions() {
  const setWsClientId = vi.fn();
  const openMiniAppTab = vi.fn();
  const previous = useAppStore.getState();
  useAppStore.setState({ setWsClientId, openMiniAppTab });
  return {
    setWsClientId,
    openMiniAppTab,
    restore: () =>
      useAppStore.setState({
        setWsClientId: previous.setWsClientId,
        openMiniAppTab: previous.openMiniAppTab,
      }),
  };
}

const deps = {
  appendLog: vi.fn(),
  setInteractivePrompt: vi.fn(),
  upsertInteractivePrompt: vi.fn(),
  setWorkflow: vi.fn(),
};

function frame(body: Record<string, unknown>): WorkflowEventMessage {
  return { data: {}, timestamp: "2026-09-11T00:00:00Z", ...body } as WorkflowEventMessage;
}

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("the dispatcher routes the MiniApp frames", () => {
  it("consumes the hello frame and stores the client id", () => {
    const actions = spyOnStoreActions();

    const consumed = dispatchWorkflowEvent(
      frame({ type: "hello", client_id: "ws-0123456789abcdef" }),
      deps,
    );

    // Consumed: `hello` is not a workflow event and `consumeEvent` has nothing
    // to do with it — it carries no block, no workflow and no event data.
    expect(consumed).toBe(true);
    expect(actions.setWsClientId).toHaveBeenCalledWith("ws-0123456789abcdef");
    actions.restore();
  });

  it("consumes panel.open_miniapp and opens the tab", () => {
    const actions = spyOnStoreActions();

    const consumed = dispatchWorkflowEvent(
      frame({
        type: "panel.open_miniapp",
        workflow_id: "wf-1",
        data: {
          panel_id: "peak_explorer",
          workflow_id: "wf-1",
          block_id: "node-a",
          port: "output_1",
        },
      }),
      deps,
    );

    expect(consumed).toBe(true);
    expect(actions.openMiniAppTab).toHaveBeenCalledWith({
      panelId: "peak_explorer",
      name: "peak_explorer",
      target: { workflow_id: "wf-1", block_id: "node-a", port: "output_1" },
    });
    actions.restore();
  });

  it("consumes panel.files_changed and tells every mount of that panel", () => {
    /*
     * Forwarded straight through: FR-022's 500 ms window is the shared panel
     * host's (`PanelFrame`), not the dispatcher's (see handleMiniApp.ts).
     */
    const heard: string[] = [];
    const stop = panelEvents.subscribePanelFilesChanged("peak_explorer", () => heard.push("peak"));
    const other = panelEvents.subscribePanelFilesChanged("other_panel", () => heard.push("other"));

    const consumed = dispatchWorkflowEvent(
      frame({ type: "panel.files_changed", data: { panel_id: "peak_explorer" } }),
      deps,
    );

    expect(consumed).toBe(true);
    expect(heard).toEqual(["peak"]);
    stop();
    other();
  });

  it("consumes panel.contexts_revoked and reaches only the mounts holding them", () => {
    const heard: string[] = [];
    const stops = ["pc-a", "pc-b", "pc-c"].map((id) =>
      panelEvents.subscribePanelContextRevoked(id, () => heard.push(id)),
    );

    const consumed = dispatchWorkflowEvent(
      frame({
        type: "panel.contexts_revoked",
        data: { context_ids: ["pc-a", "pc-c"], panel_ids: ["lab.view"], reason: "panel_changed" },
      }),
      deps,
    );

    expect(consumed).toBe(true);
    expect(heard).toEqual(["pc-a", "pc-c"]);
    stops.forEach((stop) => stop());
  });
});
