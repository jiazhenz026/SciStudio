import { beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "./index";
import type { WorkflowResponse } from "../types/api";

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
    unreadProblemsCount: 0,
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
    expect(state.tabs[0].workflowName).toBe("my-workflow");
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
    expect(state.tabs[0].workflowName).toBe("experiment-2");
    expect(state.workflowName).toBe("experiment-2");
  });

  it("falls back to 'Untitled' when both id and displayName are empty", () => {
    useAppStore.getState().openTab(workflow(""));
    const state = useAppStore.getState();
    expect(state.tabs[0].workflowName).toBe("Untitled");
  });

  it("de-duplicates on displayName when id is empty (same blank-id file)", () => {
    useAppStore.getState().openTab(workflow(""), "exp");
    useAppStore.getState().openTab(workflow(""), "exp");
    expect(useAppStore.getState().tabs).toHaveLength(1);
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

  it("bumpUnreadProblems behaves symmetrically", () => {
    useAppStore.getState().setActiveBottomTab("ai");
    useAppStore.getState().bumpUnreadProblems();
    expect(useAppStore.getState().unreadProblemsCount).toBe(1);
    useAppStore.getState().setActiveBottomTab("problems");
    expect(useAppStore.getState().unreadProblemsCount).toBe(0);
  });
});
