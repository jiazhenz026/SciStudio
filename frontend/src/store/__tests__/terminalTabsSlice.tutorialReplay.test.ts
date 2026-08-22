/**
 * ADR-053 FR-061a / #2083 — the store side of adopting a tutorial replay tab.
 *
 * The scripted session is registered on the backend under the tab id the
 * session response names; adoption folds it into the tab strip as a running
 * tab with the `tutorial-replay` source, and rehydration drops such tabs
 * entirely because their byte source cannot survive the page.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useAppStore } from "../index";
import { rehydrateTerminalTabs } from "../terminalTabsSlice";
import type { TerminalTab } from "../types";

function reset(): void {
  useAppStore.setState({
    terminalTabs: [],
    activeTerminalTabId: null,
  });
}

describe("adoptTutorialReplayTab (#2083)", () => {
  beforeEach(reset);

  it("attaches the backend's tab id as a running tutorial-replay tab", () => {
    useAppStore.getState().adoptTutorialReplayTab({
      tabId: "replay-tab-1",
      title: "Scripted AI session",
    });

    const tabs = useAppStore.getState().terminalTabs;
    expect(tabs).toHaveLength(1);
    expect(tabs[0]).toMatchObject({
      id: "replay-tab-1",
      title: "Scripted AI session",
      // A valid WS query value; the join branch attaches to the registered
      // scripted session before any spawn decision is reached.
      provider: "user-terminal",
      permissionMode: "safe",
      // The byte source already exists server-side; there is no setup step.
      state: "running",
      source: "tutorial-replay",
    });
    expect(useAppStore.getState().activeTerminalTabId).toBe("replay-tab-1");
  });

  it("carries no AI-block affordances", () => {
    useAppStore.getState().adoptTutorialReplayTab({ tabId: "t", title: "Scripted AI session" });
    const tab = useAppStore.getState().terminalTabs[0];
    // Mark-done and the status badge key on "ai-block"; a replay must show neither.
    expect(tab.source).not.toBe("ai-block");
    expect(tab.blockRunId).toBeUndefined();
    expect(tab.blockStatus).toBeUndefined();
  });

  it("is idempotent on tab id", () => {
    const args = { tabId: "t1", title: "Scripted AI session" };
    useAppStore.getState().adoptTutorialReplayTab(args);
    useAppStore.getState().adoptTutorialReplayTab(args);
    expect(useAppStore.getState().terminalTabs).toHaveLength(1);
  });
});

describe("rehydrateTerminalTabs with tutorial-replay tabs (#2083)", () => {
  it("drops them: the scripted session died with the page's WebSocket", () => {
    const tabs: TerminalTab[] = [
      {
        id: "replay-tab",
        title: "Scripted AI session",
        provider: "user-terminal",
        permissionMode: "safe",
        state: "running",
        source: "tutorial-replay",
      },
      {
        id: "chat-tab",
        title: "Chat 1",
        provider: "claude-code",
        permissionMode: "safe",
        state: "running",
        source: "user",
      },
    ];

    const rehydrated = rehydrateTerminalTabs(tabs);

    // The replay tab is gone — a persisted copy would be a dead terminal, or
    // worse: joining its stale id would spawn a real shell. The ordinary chat
    // tab survives, downgraded to closed as reloads always do.
    expect(rehydrated.map((tab) => tab.id)).toEqual(["chat-tab"]);
    expect(rehydrated[0].state).toBe("closed");
  });
});
