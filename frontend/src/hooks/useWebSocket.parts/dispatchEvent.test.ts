/**
 * ADR-054 spec 4 (T-010) — where an interactive prompt goes now.
 *
 * The routing change is one line in `dispatchWorkflowEvent`, and it is the line
 * that retires the modal: the prompt still reaches the execution slice, and it
 * now also opens an Explore tab in pause mode. What this suite exists to prove
 * is the *negative* half — that nothing routes to a modal any more, because
 * there is no modal to route to. `PauseTab.test.tsx` owns what the tab then
 * does; the frontend build succeeding with the files deleted is what proves
 * nothing else imported them.
 */

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import type { WorkflowEventMessage } from "../../types/api";

import { dispatchWorkflowEvent, pauseTabNotebookPath } from "./dispatchEvent";

vi.mock("../useWebSocket", () => ({ sendWebSocketMessage: vi.fn() }));

const deps = {
  appendLog: vi.fn(),
  setInteractivePrompt: (prompt: unknown) =>
    useAppStore.getState().setInteractivePrompt(prompt as never),
  setWorkflow: vi.fn(),
};

function promptEvent(blockId = "node-1"): WorkflowEventMessage {
  return {
    type: "interactive_prompt",
    block_id: blockId,
    workflow_id: "wf-1",
    data: {
      workflow_id: "wf-1",
      block_type: "data_router",
      panel_manifest: { panel_id: "core.interactive.data_router" },
      panel_descriptor: null,
      panel_payload: {},
      input_signature: {},
    },
    timestamp: "2026-09-05T12:00:00Z",
  };
}

beforeEach(() => {
  resetAppStore();
  useAppStore.setState({ tabs: [], activeTabId: null, interactivePrompt: null, sessions: {} });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("an interactive prompt opens a pause tab (FR-024)", () => {
  it("keeps the prompt on the slice and puts an Explore tab in pause mode", () => {
    const consumed = dispatchWorkflowEvent(promptEvent(), deps);
    expect(consumed).toBe(true);

    // The prompt is still the carrier of the descriptor, the payload and the
    // workflow scoping; only where it is drawn changed.
    const prompt = useAppStore.getState().interactivePrompt;
    expect(prompt?.blockId).toBe("node-1");
    expect(prompt?.workflowId).toBe("wf-1");

    const tabs = useAppStore.getState().tabs;
    expect(tabs).toHaveLength(1);
    const [tab] = tabs;
    expect(tab.kind).toBe("explore");
    if (tab.kind !== "explore") throw new Error("the prompt did not open an Explore tab");
    expect(tab.mode).toBe("pause");
    expect(tab.pauseNodeId).toBe("node-1");
    expect(tab.notebookPath).toBe(pauseTabNotebookPath("node-1"));
    // No session, and no notebook pane until the person asks for one (FR-026).
    expect(tab.sessionId).toBeNull();
    expect(tab.notebookVisible).toBe(false);
    expect(useAppStore.getState().activeTabId).toBe(tab.id);
  });

  it("activates the tab that exists rather than opening a second one", () => {
    dispatchWorkflowEvent(promptEvent(), deps);
    dispatchWorkflowEvent(promptEvent(), deps);
    expect(useAppStore.getState().tabs).toHaveLength(1);

    // A different block is a different pause and a different tab.
    dispatchWorkflowEvent(promptEvent("node-2"), deps);
    expect(useAppStore.getState().tabs).toHaveLength(2);
  });
});

describe("the modal is gone (FR-024)", () => {
  it("has no InteractiveModals module left to route to", () => {
    const root = join(process.cwd(), "src", "App.parts");
    expect(existsSync(join(root, "InteractiveModals.tsx"))).toBe(false);
    expect(existsSync(join(root, "InteractiveModals.parts"))).toBe(false);
  });

  it("is not mounted by App any more", () => {
    // The overlay used to be mounted app-level and cover the toolbar's Stop
    // control; the tab does neither. `npm run build` is the other half of this
    // assertion — a stale import anywhere would fail it.
    const app = readFileSync(join(process.cwd(), "src", "App.tsx"), "utf8");
    expect(app).not.toContain("<InteractiveModals");
    expect(app).not.toContain('from "./App.parts/InteractiveModals"');
  });
});
