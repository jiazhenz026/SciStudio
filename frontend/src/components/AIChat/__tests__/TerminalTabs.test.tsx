/**
 * Tests for the multi-tab terminal container: add / close / rename / switch
 * plus Ctrl+T / Ctrl+W / Ctrl+1..9 keyboard shortcuts.
 *
 * SetupScreen and TerminalView are mocked out so this suite focuses on the
 * tab-strip mechanics and the keyboard listener.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../../store";

// Mock SetupScreen so we don't fetch /api/ai/status during tab-strip tests.
vi.mock("../SetupScreen", () => ({
  SetupScreen: ({ tabId }: { tabId: string }) => (
    <div data-testid={`mock-setup-${tabId}`}>setup-{tabId}</div>
  ),
}));
// Mock TerminalView so xterm.js never loads.
vi.mock("../TerminalView", () => ({
  TerminalView: ({ tabId }: { tabId: string }) => (
    <div data-testid={`mock-terminal-view-${tabId}`}>view-{tabId}</div>
  ),
}));

import { TerminalTabs } from "../TerminalTabs";

function resetStore() {
  useAppStore.setState({
    terminalTabs: [],
    activeTerminalTabId: null,
    currentProject: {
      id: "p",
      name: "p",
      description: "",
      path: "/p",
      current_workflow_id: null,
      workflows: [],
      workflow_count: 0,
    },
  });
}

beforeEach(() => {
  resetStore();
});

afterEach(() => {
  cleanup();
});

describe("TerminalTabs", () => {
  it("auto-creates an initial tab on first mount", async () => {
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    const tab = useAppStore.getState().terminalTabs[0];
    expect(tab.title).toBe("Chat 1");
    expect(tab.state).toBe("setup");
    expect(useAppStore.getState().activeTerminalTabId).toBe(tab.id);
  });

  it("auto-creates a user terminal when the terminal surface is active", async () => {
    render(<TerminalTabs surface="terminal" />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    const tab = useAppStore.getState().terminalTabs[0];
    expect(tab.title).toBe("Terminal 1");
    expect(tab.provider).toBe("user-terminal");
    expect(tab.permissionMode).toBe("safe");
    expect(tab.state).toBe("running");
    expect(screen.queryByTestId("terminal-tabs-add-user-terminal")).toBeNull();
  });

  it("adds a new tab when the + button is clicked", async () => {
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
    expect(useAppStore.getState().terminalTabs.length).toBe(2);
    expect(useAppStore.getState().terminalTabs[1].title).toBe("Chat 2");
  });

  it("opens a user terminal tab from the terminal button", async () => {
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add-user-terminal")));
    const tab = useAppStore.getState().terminalTabs[1];
    expect(tab.title).toBe("Terminal 1");
    expect(tab.provider).toBe("user-terminal");
    expect(tab.permissionMode).toBe("safe");
    expect(tab.state).toBe("running");
    expect(useAppStore.getState().activeTerminalTabId).toBe(tab.id);
  });

  it("closes a setup-state tab without confirm dialog", async () => {
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
    expect(useAppStore.getState().terminalTabs.length).toBe(2);
    const [t1] = useAppStore.getState().terminalTabs;
    act(() => fireEvent.click(screen.getByTestId(`terminal-tab-close-btn-${t1.id}`)));
    expect(useAppStore.getState().terminalTabs.length).toBe(1);
    expect(screen.queryByTestId("terminal-confirm-dialog")).toBeNull();
  });

  it("prompts before closing a running tab", async () => {
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    const id = useAppStore.getState().terminalTabs[0].id;
    act(() => useAppStore.getState().launchTerminalTab(id, "claude-code", "safe"));
    act(() => fireEvent.click(screen.getByTestId(`terminal-tab-close-btn-${id}`)));
    expect(screen.getByTestId("terminal-confirm-dialog")).toBeInTheDocument();
    act(() => fireEvent.click(screen.getByTestId("terminal-confirm-ok")));
    expect(useAppStore.getState().terminalTabs.length).toBe(0);
  });

  it("renames a tab via double-click + Enter", async () => {
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    const id = useAppStore.getState().terminalTabs[0].id;
    act(() => fireEvent.doubleClick(screen.getByTestId(`terminal-tab-title-${id}`)));
    const input = screen.getByTestId(`terminal-tab-rename-input-${id}`);
    fireEvent.change(input, { target: { value: "My session" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() => expect(useAppStore.getState().terminalTabs[0].title).toBe("My session"));
  });

  it("Ctrl+T opens a new tab", async () => {
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    act(() => {
      fireEvent.keyDown(window, { key: "t", ctrlKey: true });
    });
    expect(useAppStore.getState().terminalTabs.length).toBe(2);
  });

  it("Ctrl+W closes the active tab (no confirm if not running)", async () => {
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
    expect(useAppStore.getState().terminalTabs.length).toBe(2);
    act(() => {
      fireEvent.keyDown(window, { key: "w", ctrlKey: true });
    });
    expect(useAppStore.getState().terminalTabs.length).toBe(1);
  });

  it("Ctrl+1..9 switches to the corresponding tab", async () => {
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
    const tabs = useAppStore.getState().terminalTabs;
    expect(tabs.length).toBe(3);
    act(() => {
      fireEvent.keyDown(window, { key: "1", ctrlKey: true });
    });
    expect(useAppStore.getState().activeTerminalTabId).toBe(tabs[0].id);
    act(() => {
      fireEvent.keyDown(window, { key: "3", ctrlKey: true });
    });
    expect(useAppStore.getState().activeTerminalTabId).toBe(tabs[2].id);
  });

  it("rehydrate downgrades a running tab to closed with exitCode -1", async () => {
    // Simulate persisted state with a "running" tab.
    const { rehydrateTerminalTabs } = await import("../../../store/terminalTabsSlice");
    const persisted = [
      {
        id: "x",
        title: "Chat 1",
        provider: "claude-code" as const,
        permissionMode: "safe" as const,
        state: "running" as const,
      },
    ];
    const rehydrated = rehydrateTerminalTabs(persisted);
    expect(rehydrated[0].state).toBe("closed");
    expect(rehydrated[0].exitCode).toBe(-1);
  });

  it("rehydrate drops stale user-terminal invalid-provider tabs", async () => {
    const { rehydrateTerminalTabs } = await import("../../../store/terminalTabsSlice");
    const rehydrated = rehydrateTerminalTabs([
      {
        id: "bad-terminal",
        title: "Terminal 1",
        provider: "user-terminal",
        permissionMode: "safe",
        state: "closed",
        exitCode: -2,
        errorMessage: "Invalid provider 'user-terminal'; expected one of ('claude-code', 'codex').",
      },
    ]);

    expect(rehydrated).toEqual([]);
  });

  // ADR-035 §3.10 — engine-initiated AI Block tabs.
  describe("ADR-035 — engine-initiated AI Block tabs", () => {
    it("handleBlockPtyOpened auto-creates a tab with source=ai-block", async () => {
      const { handleBlockPtyOpened } = await import("../TerminalTabs");
      act(() => {
        handleBlockPtyOpened({
          tab_id: "blk-1",
          block_run_id: "run-1",
          block_name: "extract_metadata",
          permission_mode: "safe",
        });
      });
      const tabs = useAppStore.getState().terminalTabs;
      expect(tabs.length).toBe(1);
      expect(tabs[0].id).toBe("blk-1");
      expect(tabs[0].source).toBe("ai-block");
      expect(tabs[0].state).toBe("running"); // skips SetupScreen
      expect(tabs[0].blockStatus).toBe("paused");
      expect(tabs[0].blockRunId).toBe("run-1");
      expect(tabs[0].title).toBe("🤖 extract_metadata");
    });

    it("handleBlockPtyOpened sets the new tab as active", async () => {
      const { handleBlockPtyOpened } = await import("../TerminalTabs");
      // Pre-existing user tab.
      act(() => {
        useAppStore.getState().addTerminalTab();
      });
      act(() => {
        handleBlockPtyOpened({
          tab_id: "blk-2",
          block_run_id: "run-2",
          block_name: "extract",
          permission_mode: "bypass",
        });
      });
      expect(useAppStore.getState().activeTerminalTabId).toBe("blk-2");
      const blkTab = useAppStore.getState().terminalTabs.find((t) => t.id === "blk-2");
      expect(blkTab?.permissionMode).toBe("dangerous");
    });

    it("handleBlockPtyOpened is idempotent on tab_id", async () => {
      const { handleBlockPtyOpened } = await import("../TerminalTabs");
      act(() => {
        handleBlockPtyOpened({
          tab_id: "blk-3",
          block_run_id: "run-3",
          block_name: "x",
        });
        handleBlockPtyOpened({
          tab_id: "blk-3",
          block_run_id: "run-3",
          block_name: "x",
        });
      });
      expect(useAppStore.getState().terminalTabs.filter((t) => t.id === "blk-3").length).toBe(1);
    });

    it("handleBlockPtyClosed updates blockStatus on the matching tab", async () => {
      const { handleBlockPtyOpened, handleBlockPtyClosed } = await import("../TerminalTabs");
      act(() => {
        handleBlockPtyOpened({
          tab_id: "blk-4",
          block_run_id: "run-4",
          block_name: "x",
        });
      });
      act(() => {
        handleBlockPtyClosed({ tab_id: "blk-4", status: "done" });
      });
      const t = useAppStore.getState().terminalTabs.find((x) => x.id === "blk-4");
      expect(t?.blockStatus).toBe("done");
    });

    it("handleBlockPtyClosed maps legacy result=completed to status=done", async () => {
      const { handleBlockPtyOpened, handleBlockPtyClosed } = await import("../TerminalTabs");
      act(() => {
        handleBlockPtyOpened({
          tab_id: "blk-5",
          block_run_id: "run-5",
          block_name: "x",
        });
      });
      act(() => {
        handleBlockPtyClosed({ tab_id: "blk-5", result: "completed" });
      });
      expect(useAppStore.getState().terminalTabs.find((t) => t.id === "blk-5")?.blockStatus).toBe(
        "done",
      );
    });

    it("handleBlockPtyClosed keeps the tab open per ADR-035 §3.9", async () => {
      const { handleBlockPtyOpened, handleBlockPtyClosed } = await import("../TerminalTabs");
      act(() => {
        handleBlockPtyOpened({
          tab_id: "blk-6",
          block_run_id: "run-6",
          block_name: "x",
        });
      });
      act(() => {
        handleBlockPtyClosed({ tab_id: "blk-6", status: "error" });
      });
      // Tab still present, still in running state — block is done but the tab survives.
      const t = useAppStore.getState().terminalTabs.find((x) => x.id === "blk-6");
      expect(t).toBeDefined();
      expect(t?.state).toBe("running");
      expect(t?.blockStatus).toBe("error");
    });

    it("handleBlockPtyClosed on unknown tab_id is a no-op", async () => {
      const { handleBlockPtyClosed } = await import("../TerminalTabs");
      // Should not throw; should not create a tab.
      act(() => {
        handleBlockPtyClosed({ tab_id: "nonexistent", status: "done" });
      });
      expect(useAppStore.getState().terminalTabs.length).toBe(0);
    });

    it("handleBlockPtyOpened with missing tab_id logs a warning", async () => {
      const { handleBlockPtyOpened } = await import("../TerminalTabs");
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
      act(() => {
        handleBlockPtyOpened({
          tab_id: "",
          block_run_id: "run-x",
        });
      });
      expect(warnSpy).toHaveBeenCalled();
      expect(useAppStore.getState().terminalTabs.length).toBe(0);
      warnSpy.mockRestore();
    });

    it("close-while-running on AI-Block tab prompts confirm and shows AI-Block message", async () => {
      const { handleBlockPtyOpened } = await import("../TerminalTabs");
      render(<TerminalTabs />);
      // Wait for the auto-created initial tab so we see only our AI Block tab too.
      await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
      act(() => {
        handleBlockPtyOpened({
          tab_id: "blk-confirm",
          block_run_id: "run-confirm",
          block_name: "x",
        });
      });
      // Click close on the AI Block tab.
      act(() => fireEvent.click(screen.getByTestId("terminal-tab-close-btn-blk-confirm")));
      const dialog = screen.getByTestId("terminal-confirm-dialog");
      expect(dialog).toBeInTheDocument();
      expect(dialog.textContent).toContain("AI Block");
      // Dismiss; tab remains.
      act(() => fireEvent.click(screen.getByTestId("terminal-confirm-cancel")));
      expect(useAppStore.getState().terminalTabs.some((t) => t.id === "blk-confirm")).toBe(true);
    });

    it("rehydrate marks AI-Block running tabs as cancelled", async () => {
      const { rehydrateTerminalTabs } = await import("../../../store/terminalTabsSlice");
      const persisted = [
        {
          id: "blk-r",
          title: "🤖 extract",
          provider: "claude-code" as const,
          permissionMode: "safe" as const,
          state: "running" as const,
          source: "ai-block" as const,
          blockRunId: "run-r",
          blockStatus: "paused" as const,
        },
      ];
      const out = rehydrateTerminalTabs(persisted);
      expect(out[0].state).toBe("closed");
      expect(out[0].blockStatus).toBe("cancelled");
    });
  });
});
