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
    await waitFor(() =>
      expect(useAppStore.getState().terminalTabs.length).toBe(1),
    );
    const tab = useAppStore.getState().terminalTabs[0];
    expect(tab.title).toBe("Chat 1");
    expect(tab.state).toBe("setup");
    expect(useAppStore.getState().activeTerminalTabId).toBe(tab.id);
  });

  it("adds a new tab when the + button is clicked", async () => {
    render(<TerminalTabs />);
    await waitFor(() =>
      expect(useAppStore.getState().terminalTabs.length).toBe(1),
    );
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
    expect(useAppStore.getState().terminalTabs.length).toBe(2);
    expect(useAppStore.getState().terminalTabs[1].title).toBe("Chat 2");
  });

  it("closes a setup-state tab without confirm dialog", async () => {
    render(<TerminalTabs />);
    await waitFor(() =>
      expect(useAppStore.getState().terminalTabs.length).toBe(1),
    );
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
    expect(useAppStore.getState().terminalTabs.length).toBe(2);
    const [t1] = useAppStore.getState().terminalTabs;
    act(() =>
      fireEvent.click(screen.getByTestId(`terminal-tab-close-btn-${t1.id}`)),
    );
    expect(useAppStore.getState().terminalTabs.length).toBe(1);
    expect(screen.queryByTestId("terminal-confirm-dialog")).toBeNull();
  });

  it("prompts before closing a running tab", async () => {
    render(<TerminalTabs />);
    await waitFor(() =>
      expect(useAppStore.getState().terminalTabs.length).toBe(1),
    );
    const id = useAppStore.getState().terminalTabs[0].id;
    act(() =>
      useAppStore.getState().launchTerminalTab(id, "claude-code", "safe"),
    );
    act(() =>
      fireEvent.click(screen.getByTestId(`terminal-tab-close-btn-${id}`)),
    );
    expect(screen.getByTestId("terminal-confirm-dialog")).toBeInTheDocument();
    act(() => fireEvent.click(screen.getByTestId("terminal-confirm-ok")));
    expect(useAppStore.getState().terminalTabs.length).toBe(0);
  });

  it("renames a tab via double-click + Enter", async () => {
    render(<TerminalTabs />);
    await waitFor(() =>
      expect(useAppStore.getState().terminalTabs.length).toBe(1),
    );
    const id = useAppStore.getState().terminalTabs[0].id;
    act(() =>
      fireEvent.doubleClick(screen.getByTestId(`terminal-tab-title-${id}`)),
    );
    const input = screen.getByTestId(`terminal-tab-rename-input-${id}`);
    fireEvent.change(input, { target: { value: "My session" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() =>
      expect(useAppStore.getState().terminalTabs[0].title).toBe("My session"),
    );
  });

  it("Ctrl+T opens a new tab", async () => {
    render(<TerminalTabs />);
    await waitFor(() =>
      expect(useAppStore.getState().terminalTabs.length).toBe(1),
    );
    act(() => {
      fireEvent.keyDown(window, { key: "t", ctrlKey: true });
    });
    expect(useAppStore.getState().terminalTabs.length).toBe(2);
  });

  it("Ctrl+W closes the active tab (no confirm if not running)", async () => {
    render(<TerminalTabs />);
    await waitFor(() =>
      expect(useAppStore.getState().terminalTabs.length).toBe(1),
    );
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
    expect(useAppStore.getState().terminalTabs.length).toBe(2);
    act(() => {
      fireEvent.keyDown(window, { key: "w", ctrlKey: true });
    });
    expect(useAppStore.getState().terminalTabs.length).toBe(1);
  });

  it("Ctrl+1..9 switches to the corresponding tab", async () => {
    render(<TerminalTabs />);
    await waitFor(() =>
      expect(useAppStore.getState().terminalTabs.length).toBe(1),
    );
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
      { id: "x", title: "Chat 1", provider: "claude-code" as const, permissionMode: "safe" as const, state: "running" as const },
    ];
    const rehydrated = rehydrateTerminalTabs(persisted);
    expect(rehydrated[0].state).toBe("closed");
    expect(rehydrated[0].exitCode).toBe(-1);
  });
});
