/**
 * ADR-053 spec 2 (#2001) — the store side of attaching a Bring In My Work
 * session tab (FR-022, FR-025) and opening the panel that shows it.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "../index";

function reset(): void {
  useAppStore.setState({
    terminalTabs: [],
    activeTerminalTabId: null,
    activeBottomTab: "config",
    bottomPanelCollapsed: true,
    unreadLogsCount: 3,
  });
}

describe("addWorkImportTerminalTab (#2001)", () => {
  beforeEach(reset);

  it("attaches the backend's tab id in running state with the spawned provider and mode", () => {
    useAppStore.getState().addWorkImportTerminalTab({
      tabId: "a1b2c3d4e5f6",
      title: "Bring in my work",
      provider: "claude-code",
      permissionMode: "safe",
    });

    const tabs = useAppStore.getState().terminalTabs;
    expect(tabs).toHaveLength(1);
    expect(tabs[0]).toMatchObject({
      id: "a1b2c3d4e5f6",
      title: "Bring in my work",
      provider: "claude-code",
      permissionMode: "safe",
      // The PTY already exists (contract C3), so there is no setup step to run.
      state: "running",
    });
    expect(useAppStore.getState().activeTerminalTabId).toBe("a1b2c3d4e5f6");
  });

  it("FR-025: the tab is an ordinary chat session, not an AI-block tab", () => {
    useAppStore.getState().addWorkImportTerminalTab({
      tabId: "tab-1",
      title: "Bring in my work",
      provider: "codex",
      permissionMode: "dangerous",
    });

    const tab = useAppStore.getState().terminalTabs[0];
    // "ai-block" would attach Mark-done and block-run cancel semantics that
    // have no block behind them here.
    expect(tab.source).toBe("user");
    expect(tab.blockRunId).toBeUndefined();
    expect(tab.blockStatus).toBeUndefined();
    // It is not a `user-terminal` either, so it belongs to the chat surface.
    expect(tab.provider).not.toBe("user-terminal");
  });

  it("is idempotent on tab id", () => {
    const args = {
      tabId: "tab-1",
      title: "Bring in my work",
      provider: "claude-code",
      permissionMode: "safe" as const,
    };
    useAppStore.getState().addWorkImportTerminalTab(args);
    useAppStore.getState().addWorkImportTerminalTab(args);
    expect(useAppStore.getState().terminalTabs).toHaveLength(1);
  });
});

describe("openBottomTab (#2001)", () => {
  beforeEach(reset);

  it("expands the panel and selects the tab", () => {
    useAppStore.getState().openBottomTab("ai");
    expect(useAppStore.getState().activeBottomTab).toBe("ai");
    expect(useAppStore.getState().bottomPanelCollapsed).toBe(false);
  });

  it("keeps setActiveBottomTab's unread-logs behaviour rather than reimplementing it", () => {
    useAppStore.getState().openBottomTab("logs");
    expect(useAppStore.getState().unreadLogsCount).toBe(0);
    expect(useAppStore.getState().bottomPanelCollapsed).toBe(false);
  });
});
