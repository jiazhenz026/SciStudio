/**
 * ADR-054 FR-018 / FR-019 — the MiniApp tab in the store.
 *
 * The rules under test are the ones the tab union does not enforce by type:
 * the id shape and its focus-on-reopen, that a MiniApp tab survives a focus
 * change where a preview tab does not, and that it is never persisted.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { resetAppStore } from "../../testUtils";
import { useAppStore } from "../index";
import type { MiniAppTab, WorkflowTab } from "../types";

const TARGET = { workflow_id: "wf", block_id: "seg", port: "image" };

function workflowTab(id: string): WorkflowTab {
  return {
    kind: "workflow",
    id,
    workflowId: "wf",
    workflowName: "wf",
    workflowDescription: "",
    workflowVersion: "1.0.0",
    workflowMetadata: {},
    workflowNodes: [],
    workflowEdges: [],
    workflowDirty: false,
    workflowHistory: [],
    workflowFuture: [],
    selectedNodeId: null,
  };
}

beforeEach(() => {
  resetAppStore();
});

describe("openMiniAppTab (ADR-054 FR-018)", () => {
  it("opens one tab under the spec's id and focuses it", () => {
    useAppStore
      .getState()
      .openMiniAppTab({ panelId: "lab.threshold", name: "Threshold explorer", target: TARGET });
    const { tabs, activeTabId } = useAppStore.getState();
    expect(tabs).toHaveLength(1);
    expect(tabs[0].id).toBe("miniapp:lab.threshold:wf:seg:image");
    expect(activeTabId).toBe("miniapp:lab.threshold:wf:seg:image");
    expect(tabs[0]).toMatchObject({
      kind: "miniapp",
      panelId: "lab.threshold",
      source: TARGET,
      displayName: "Threshold explorer",
    });
  });

  it("focuses the existing tab instead of opening a second one on the same output", () => {
    const open = useAppStore.getState().openMiniAppTab;
    open({ panelId: "lab.threshold", name: "Threshold explorer", target: TARGET });
    useAppStore.setState({ tabs: [...useAppStore.getState().tabs, workflowTab("tab-wf")] });
    useAppStore.getState().switchTab("tab-wf");
    expect(useAppStore.getState().activeTabId).toBe("tab-wf");

    open({ panelId: "lab.threshold", name: "Threshold explorer", target: TARGET });
    expect(useAppStore.getState().tabs.filter((t) => t.kind === "miniapp")).toHaveLength(1);
    expect(useAppStore.getState().activeTabId).toBe("miniapp:lab.threshold:wf:seg:image");
  });

  it("opens a separate tab for the same MiniApp on a different output", () => {
    const open = useAppStore.getState().openMiniAppTab;
    open({ panelId: "lab.threshold", name: "Threshold explorer", target: TARGET });
    open({
      panelId: "lab.threshold",
      name: "Threshold explorer",
      target: { ...TARGET, block_id: "other" },
    });
    expect(useAppStore.getState().tabs.filter((t) => t.kind === "miniapp")).toHaveLength(2);
  });
});

describe("a MiniApp tab's lifetime in the tab list (ADR-054 FR-019)", () => {
  it("stays open when another tab becomes active", () => {
    // The contrast that makes this worth asserting: a preview tab in the same
    // list is dropped by the same switch (#2112), a MiniApp tab is not.
    useAppStore
      .getState()
      .openMiniAppTab({ panelId: "lab.threshold", name: "Threshold", target: TARGET });
    useAppStore.setState({
      tabs: [
        ...useAppStore.getState().tabs,
        {
          kind: "preview",
          id: "preview:data-1",
          target: { kind: "data_ref", ref: "data-1" },
          displayName: "data-1",
        },
        workflowTab("tab-wf"),
      ],
    });
    useAppStore.getState().switchTab("tab-wf");

    const kinds = useAppStore.getState().tabs.map((t) => t.kind);
    expect(kinds).toContain("miniapp");
    expect(kinds).not.toContain("preview");
  });

  it("is dropped from the list when closed, and never prompts", () => {
    useAppStore
      .getState()
      .openMiniAppTab({ panelId: "lab.threshold", name: "Threshold", target: TARGET });
    const id = "miniapp:lab.threshold:wf:seg:image";
    // No dirty prompt: a MiniApp holds no unsaved document. Its backend
    // context is closed by the pane's unmount, not by this call.
    expect(useAppStore.getState().closeTab(id)).toBe(true);
    expect(useAppStore.getState().tabs.some((t) => t.id === id)).toBe(false);
  });

  it("is not persisted across restarts", () => {
    useAppStore
      .getState()
      .openMiniAppTab({ panelId: "lab.threshold", name: "Threshold", target: TARGET });
    const persisted = window.localStorage.getItem("scistudio-studio-ui");
    expect(persisted).toBeTruthy();
    const tabs = (JSON.parse(persisted as string).state.tabs ?? []) as MiniAppTab[];
    expect(tabs.some((tab) => tab.kind === "miniapp")).toBe(false);
  });
});

describe("the realtime seams the /ws dispatcher calls (ADR-054 FR-013 / FR-022)", () => {
  it("remembers the workspace client id", () => {
    expect(useAppStore.getState().wsClientId).toBeNull();
    useAppStore.getState().setWsClientId("ws-abc123");
    expect(useAppStore.getState().wsClientId).toBe("ws-abc123");
  });

  it("counts file changes per panel so two events in one tick are two events", () => {
    const notify = useAppStore.getState().notifyPanelFilesChanged;
    notify("lab.threshold");
    notify("lab.threshold");
    notify("lab.other");
    expect(useAppStore.getState().panelFilesChangedSeq).toEqual({
      "lab.threshold": 2,
      "lab.other": 1,
    });
  });
});
