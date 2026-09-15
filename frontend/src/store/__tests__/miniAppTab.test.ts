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

describe("the realtime seam the /ws dispatcher calls (ADR-054 FR-013)", () => {
  it("remembers the workspace client id", () => {
    expect(useAppStore.getState().wsClientId).toBeNull();
    useAppStore.getState().setWsClientId("ws-abc123");
    expect(useAppStore.getState().wsClientId).toBe("ws-abc123");
  });
});

describe("MiniApps preserve upstream workflow-copy isolation (#2362)", () => {
  function twoCopies() {
    const first = { ...workflowTab("copy-a"), workflowDescription: "first", tabKey: "a.yaml" };
    const second = { ...workflowTab("copy-b"), workflowDescription: "second", tabKey: "b.yaml" };
    useAppStore.setState({ tabs: [first, second], activeTabId: null });
    useAppStore.getState().switchTab(first.id);
    useAppStore
      .getState()
      .openMiniAppTab({ panelId: "lab.threshold", name: "Threshold", target: TARGET });
    return useAppStore.getState().activeTabId!;
  }

  function descriptions() {
    return useAppStore
      .getState()
      .tabs.filter((tab): tab is WorkflowTab => tab.kind === "workflow")
      .map((tab) => tab.workflowDescription);
  }

  it("captures only the exact backing workflow while a MiniApp has focus", () => {
    twoCopies();
    useAppStore.setState({ workflowDescription: "first edited" });
    useAppStore.getState().syncActiveTab();
    expect(descriptions()).toEqual(["first edited", "second"]);
  });

  it("updates the backing identity when revisiting a persistent MiniApp", () => {
    const miniappId = twoCopies();
    useAppStore.getState().switchTab("copy-b");
    useAppStore.getState().switchTab(miniappId);
    useAppStore.setState({ workflowDescription: "second edited" });
    useAppStore.getState().syncActiveTab();
    expect(descriptions()).toEqual(["first", "second edited"]);
  });

  it("carries the backing identity through MiniApp and preview opens", () => {
    twoCopies();
    useAppStore.getState().openMiniAppTab({ panelId: "lab.other", name: "Other", target: TARGET });
    useAppStore.getState().openPreviewTab({ kind: "data_ref", ref: "image" }, "Image");
    useAppStore.setState({ workflowDescription: "first edited" });
    useAppStore.getState().syncActiveTab();
    expect(descriptions()).toEqual(["first edited", "second"]);
  });

  it("does not write a closed workflow's state into another copy on fallback", () => {
    twoCopies();
    useAppStore.getState().switchTab("copy-b");
    useAppStore.getState().closeTab("copy-b");
    expect(
      useAppStore.getState().tabs.find((tab) => tab.id === useAppStore.getState().activeTabId)
        ?.kind,
    ).toBe("miniapp");
    useAppStore.getState().syncActiveTab();
    expect(descriptions()).toEqual(["first"]);
  });
});

describe("syncMiniAppTabNames (#2457)", () => {
  beforeEach(() => {
    useAppStore.setState({ tabs: [], activeTabId: null });
  });

  const open = (panelId: string, name: string, port = "image") =>
    useAppStore.getState().openMiniAppTab({ panelId, name, target: { ...TARGET, port } });
  const miniApps = () =>
    useAppStore.getState().tabs.filter((tab): tab is MiniAppTab => tab.kind === "miniapp");

  it("renames every open tab on a panel to its catalogue name, keeping ids", () => {
    open("lab.threshold", "threshold the nuclei image");
    open("lab.threshold", "threshold the nuclei image", "mask");
    const ids = miniApps().map((tab) => tab.id);
    useAppStore
      .getState()
      .syncMiniAppTabNames([{ panel_id: "lab.threshold", name: "Threshold explorer" }]);
    expect(miniApps().map((tab) => tab.displayName)).toEqual([
      "Threshold explorer",
      "Threshold explorer",
    ]);
    expect(miniApps().map((tab) => tab.id)).toEqual(ids);
    // FR-018 — reopening the same target still focuses the renamed tab.
    open("lab.threshold", "stale name");
    expect(miniApps()).toHaveLength(2);
    expect(useAppStore.getState().activeTabId).toBe(ids[0]);
  });

  it("keeps the stored name of a panel the catalogue does not list", () => {
    open("lab.gone", "Gone app");
    useAppStore.getState().syncMiniAppTabNames([{ panel_id: "lab.other", name: "Other" }]);
    expect(miniApps()[0].displayName).toBe("Gone app");
    useAppStore.getState().syncMiniAppTabNames([{ panel_id: "lab.gone", name: "" }]);
    expect(miniApps()[0].displayName).toBe("Gone app");
  });

  it("writes nothing when no name changed", () => {
    open("lab.threshold", "Threshold explorer");
    const before = useAppStore.getState().tabs;
    useAppStore
      .getState()
      .syncMiniAppTabNames([{ panel_id: "lab.threshold", name: "Threshold explorer" }]);
    expect(useAppStore.getState().tabs).toBe(before);
  });
});
