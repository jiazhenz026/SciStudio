import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "./index";
import type { WorkflowTab } from "./types";
import type { PreviewTarget, WorkflowResponse } from "../types/api";

/** Narrow a tab to WorkflowTab for tests; throws if it's a file tab. */
function asWorkflowTab(tab: { kind?: string }): WorkflowTab {
  if (tab.kind !== "workflow") {
    throw new Error(`expected workflow tab, got kind=${tab.kind}`);
  }
  return tab as WorkflowTab;
}

// Snapshot a clean store between tests so persisted state from one test does
// not bleed into the next.
function resetStore(): void {
  useAppStore.setState({
    tabs: [],
    activeTabId: null,
    workflowId: null,
    workflowName: "Untitled",
    activeBottomTab: "config",
    unreadLogsCount: 0,
  });
}

function workflow(id: string): WorkflowResponse {
  return {
    id,
    version: "1.0.0",
    description: "",
    nodes: [],
    edges: [],
    metadata: {},
  };
}

describe("tabSlice.openTab (#796 display-name fallback)", () => {
  beforeEach(() => {
    resetStore();
  });

  it("uses workflow.id as the tab label when it is non-empty", () => {
    useAppStore.getState().openTab(workflow("my-workflow"));
    const state = useAppStore.getState();
    expect(state.tabs).toHaveLength(1);
    expect(asWorkflowTab(state.tabs[0]).workflowName).toBe("my-workflow");
    expect(state.workflowName).toBe("my-workflow");
  });

  it("falls back to the displayName parameter when workflow.id is empty", () => {
    // This reproduces the macOS-reported #796 path: a workflow YAML missing
    // the `id:` field round-trips through the API as `id: ""`. Previously
    // the tab label and top-left title rendered blank. With the fallback the
    // caller-supplied displayName (filename stem) is used instead.
    useAppStore.getState().openTab(workflow(""), "experiment-2");
    const state = useAppStore.getState();
    expect(state.tabs).toHaveLength(1);
    expect(asWorkflowTab(state.tabs[0]).workflowName).toBe("experiment-2");
    expect(state.workflowName).toBe("experiment-2");
  });

  it("falls back to 'Untitled' when both id and displayName are empty", () => {
    useAppStore.getState().openTab(workflow(""));
    const state = useAppStore.getState();
    expect(asWorkflowTab(state.tabs[0]).workflowName).toBe("Untitled");
  });

  it("de-duplicates on displayName when id is empty (same blank-id file)", () => {
    useAppStore.getState().openTab(workflow(""), "exp");
    useAppStore.getState().openTab(workflow(""), "exp");
    expect(useAppStore.getState().tabs).toHaveLength(1);
  });
});

describe("tabSlice.openTab — ADR-044 path-keyed subworkflow tabs", () => {
  beforeEach(() => {
    resetStore();
  });

  it("opens copies that share a workflow.id as DISTINCT tabs when keyed by path", () => {
    // Two imported subworkflow copies carry the same internal id but live at
    // different paths. Keyed by path (the runPrefix arg is left default), each
    // gets its own tab instead of colliding into one.
    useAppStore.getState().openTab(workflow("fig1"), "fig1", "sw1__", "subworkflows/fig1.yaml");
    useAppStore.getState().openTab(workflow("fig1"), "fig1", "sw2__", "subworkflows/fig1_1.yaml");
    const tabs = useAppStore.getState().tabs;
    expect(tabs).toHaveLength(2);
    expect(asWorkflowTab(tabs[0]).tabKey).toBe("subworkflows/fig1.yaml");
    expect(asWorkflowTab(tabs[1]).tabKey).toBe("subworkflows/fig1_1.yaml");
    // workflowId stays the real shared id so save/run are unaffected.
    expect(asWorkflowTab(tabs[1]).workflowId).toBe("fig1");
  });

  it("de-duplicates a re-opened path-keyed tab and refreshes its run prefix", () => {
    useAppStore.getState().openTab(workflow("fig1"), "fig1", "sw1__", "subworkflows/fig1.yaml");
    useAppStore.getState().openTab(workflow("fig1"), "fig1", "sw9__", "subworkflows/fig1.yaml");
    const tabs = useAppStore.getState().tabs;
    expect(tabs).toHaveLength(1);
    expect(asWorkflowTab(tabs[0]).runPrefix).toBe("sw9__");
  });

  it("still de-duplicates ordinary id-keyed opens (no tabKey) as before", () => {
    useAppStore.getState().openTab(workflow("main"));
    useAppStore.getState().openTab(workflow("main"));
    expect(useAppStore.getState().tabs).toHaveLength(1);
    expect(asWorkflowTab(useAppStore.getState().tabs[0]).tabKey).toBe("main");
  });
});

describe("tabSlice preview tabs (#2112 transient preview tab)", () => {
  beforeEach(() => {
    resetStore();
  });

  const previewTarget: PreviewTarget = { kind: "data_ref", ref: "data-123" };

  function activePreviewTab() {
    const state = useAppStore.getState();
    const tab = state.tabs.find((t) => t.id === state.activeTabId);
    if (!tab || tab.kind !== "preview") throw new Error("expected active preview tab");
    return tab;
  }

  it("opens and activates a preview tab holding the frozen target", () => {
    useAppStore.getState().openPreviewTab(previewTarget, "beads.tif", { page: 1 });
    const tab = activePreviewTab();
    expect(tab.id).toBe("preview:data-123");
    expect(tab.target).toEqual(previewTarget);
    expect(tab.displayName).toBe("beads.tif");
    expect(tab.initialQuery).toEqual({ page: 1 });
  });

  it("falls back to the ref as the display name", () => {
    useAppStore.getState().openPreviewTab(previewTarget);
    expect(activePreviewTab().displayName).toBe("data-123");
  });

  it("carries the open-as descriptor so the tab can say — and change — its type", () => {
    useAppStore.getState().openPreviewTab(previewTarget, "beads.tif", undefined, {
      path: "data/beads.tif",
      extension: ".tif",
      typeName: "Image",
      remembered: true,
    });
    expect(activePreviewTab().openAs).toEqual({
      path: "data/beads.tif",
      extension: ".tif",
      typeName: "Image",
      remembered: true,
    });
  });

  it("leaves openAs unset for a tab opened by maximizing the sidebar preview", () => {
    useAppStore.getState().openPreviewTab(previewTarget, "beads.tif");
    expect(activePreviewTab().openAs).toBeUndefined();
  });

  it("de-duplicates on the ref: re-maximizing focuses the existing tab", () => {
    useAppStore.getState().openPreviewTab(previewTarget, "first");
    useAppStore.getState().openPreviewTab(previewTarget, "second");
    const state = useAppStore.getState();
    expect(state.tabs.filter((t) => t.kind === "preview")).toHaveLength(1);
    expect(activePreviewTab().displayName).toBe("first");
  });

  it("switching to another tab removes the preview tab (阅后即焚)", () => {
    useAppStore.getState().openTab(workflow("main"));
    const workflowTabId = useAppStore.getState().activeTabId;
    useAppStore.getState().openPreviewTab(previewTarget, "beads.tif");
    expect(useAppStore.getState().tabs).toHaveLength(2);

    useAppStore.getState().switchTab(workflowTabId ?? "");

    const state = useAppStore.getState();
    expect(state.tabs).toHaveLength(1);
    expect(state.tabs.some((t) => t.kind === "preview")).toBe(false);
    // The workflow tab restored normally.
    expect(state.workflowName).toBe("main");
  });

  it("switching between two previews keeps only the focused one", () => {
    useAppStore.getState().openTab(workflow("main"));
    useAppStore.getState().openPreviewTab(previewTarget, "a");
    useAppStore.getState().openPreviewTab({ kind: "data_ref", ref: "data-456" }, "b");
    const state = useAppStore.getState();
    const previews = state.tabs.filter((t) => t.kind === "preview");
    expect(previews).toHaveLength(1);
    expect(previews[0].id).toBe("preview:data-456");
    expect(state.activeTabId).toBe("preview:data-456");
  });

  it("opening a workflow tab retires the active preview tab", () => {
    useAppStore.getState().openPreviewTab(previewTarget, "beads.tif");
    useAppStore.getState().openTab(workflow("main"));
    const state = useAppStore.getState();
    expect(state.tabs.some((t) => t.kind === "preview")).toBe(false);
    expect(asWorkflowTab(state.tabs[0]).workflowName).toBe("main");
  });

  it("closes without a dirty prompt and restores the neighbouring tab", () => {
    const confirmSpy = vi.spyOn(window, "confirm");
    try {
      useAppStore.getState().openTab(workflow("main"));
      useAppStore.getState().openPreviewTab(previewTarget, "beads.tif");
      const previewId = useAppStore.getState().activeTabId ?? "";

      const closed = useAppStore.getState().closeTab(previewId);

      expect(closed).toBe(true);
      expect(confirmSpy).not.toHaveBeenCalled();
      const state = useAppStore.getState();
      expect(state.tabs.some((t) => t.kind === "preview")).toBe(false);
      expect(state.workflowName).toBe("main");
    } finally {
      confirmSpy.mockRestore();
    }
  });

  it("is excluded from persistence", () => {
    useAppStore.setState({
      tabs: [
        {
          kind: "preview",
          id: "preview:data-123",
          target: previewTarget,
          displayName: "beads.tif",
        },
      ],
      activeTabId: "preview:data-123",
    });
    const persisted = JSON.parse(localStorage.getItem("scistudio-studio-ui") ?? "{}");
    const tabs = persisted?.state?.tabs ?? [];
    expect(tabs.some((t: { id: string }) => t.id === "preview:data-123")).toBe(false);
  });

  it("keeps the backing workflow tab snapshot in sync while a preview is active", () => {
    useAppStore.getState().openTab(workflow("main"));
    const workflowTabId = useAppStore.getState().activeTabId ?? "";
    useAppStore.getState().openPreviewTab(previewTarget, "beads.tif");

    // An autosave / WebSocket update lands while the preview owns focus: the
    // live workflow slice changes underneath the preview tab.
    useAppStore.setState({
      workflowDirty: true,
      workflowNodes: [{ id: "n1", type: "block", position: { x: 0, y: 0 }, data: {} } as never],
    });
    useAppStore.getState().syncActiveTab();

    // The backing workflow tab's snapshot must reflect the live change...
    const backing = useAppStore.getState().tabs.find((t) => t.id === workflowTabId);
    expect(asWorkflowTab(backing ?? {}).workflowDirty).toBe(true);
    // ...and its identity must not be clobbered by the capture.
    expect(asWorkflowTab(backing ?? {}).id).toBe(workflowTabId);

    // Switching back restores the synced snapshot, not the pre-preview one.
    useAppStore.getState().switchTab(workflowTabId);
    const state = useAppStore.getState();
    expect(state.workflowDirty).toBe(true);
    expect(state.workflowNodes).toHaveLength(1);
  });
});

describe("uiSlice unread counters (#793 no auto-tab-switch)", () => {
  beforeEach(() => {
    resetStore();
  });

  it("bumpUnreadLogs increments when active tab is not 'logs'", () => {
    useAppStore.getState().setActiveBottomTab("ai");
    useAppStore.getState().bumpUnreadLogs();
    useAppStore.getState().bumpUnreadLogs();
    expect(useAppStore.getState().unreadLogsCount).toBe(2);
    // The active tab is NOT yanked to "logs".
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
  });

  it("bumpUnreadLogs is a no-op while the user is viewing the Logs tab", () => {
    useAppStore.getState().setActiveBottomTab("logs");
    useAppStore.getState().bumpUnreadLogs();
    useAppStore.getState().bumpUnreadLogs();
    expect(useAppStore.getState().unreadLogsCount).toBe(0);
  });

  it("setActiveBottomTab('logs') clears unreadLogsCount", () => {
    useAppStore.getState().setActiveBottomTab("ai");
    useAppStore.getState().bumpUnreadLogs();
    useAppStore.getState().bumpUnreadLogs();
    expect(useAppStore.getState().unreadLogsCount).toBe(2);
    useAppStore.getState().setActiveBottomTab("logs");
    expect(useAppStore.getState().unreadLogsCount).toBe(0);
  });

  // ``bumpUnreadProblems`` was removed alongside the Problems tab. The
  // surviving Logs counter alone covers the unread-rendered-row contract.
});
