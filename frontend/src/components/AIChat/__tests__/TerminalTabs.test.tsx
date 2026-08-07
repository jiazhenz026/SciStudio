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

  // #1994 — rename used to be double-click only and therefore undiscoverable.
  // Hovering the focused tab now reveals a pencil; the pencil is the only
  // pointer target that renames, and clicking a tab body must still switch.
  //
  // The affordance must also cost nothing in layout: it is absent from the DOM
  // until revealed (so it reserves no space) and absolutely positioned when
  // present (so it cannot displace the close button). Both halves are asserted
  // below — dropping either one reintroduces a bug the owner already reported.
  describe("#1994 — hover rename affordance", () => {
    /** Render two tabs and return their ids; tab 2 ends up active. */
    async function renderTwoTabs() {
      render(<TerminalTabs />);
      await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
      act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
      const tabs = useAppStore.getState().terminalTabs;
      expect(tabs.length).toBe(2);
      expect(useAppStore.getState().activeTerminalTabId).toBe(tabs[1].id);
      return { background: tabs[0].id, focused: tabs[1].id };
    }

    /** Children that actually participate in the flex flow of a tab row. */
    function inFlowChildren(rowTestId: string): (string | null)[] {
      return Array.from(screen.getByTestId(rowTestId).children)
        .filter((c) => !c.className.includes("absolute"))
        .map((c) => c.getAttribute("data-testid"));
    }

    it("hovering the focused tab reveals the rename affordance", async () => {
      const { focused } = await renderTwoTabs();
      const row = screen.getByTestId(`terminal-tab-${focused}`);

      // Absent from the DOM before hover — that is what "reserves no space" means.
      expect(row.dataset.hovered).toBe("false");
      expect(screen.queryByTestId(`terminal-tab-rename-btn-${focused}`)).toBeNull();

      act(() => fireEvent.mouseOver(row));

      expect(screen.getByTestId(`terminal-tab-${focused}`).dataset.hovered).toBe("true");
      expect(screen.getByTestId(`terminal-tab-rename-btn-${focused}`)).toBeInTheDocument();

      // ...and it goes away again when the pointer leaves.
      act(() => fireEvent.mouseOut(row));
      expect(screen.queryByTestId(`terminal-tab-rename-btn-${focused}`)).toBeNull();
    });

    it("hovering highlights the tab background", async () => {
      const { background } = await renderTwoTabs();
      const row = screen.getByTestId(`terminal-tab-${background}`);
      expect(row.className).not.toContain("bg-stone-200/70");
      act(() => fireEvent.mouseOver(row));
      expect(screen.getByTestId(`terminal-tab-${background}`).className).toContain(
        "bg-stone-200/70",
      );
    });

    it("an unfocused tab never shows the affordance, hovered or not", async () => {
      const { background, focused } = await renderTwoTabs();
      expect(screen.queryByTestId(`terminal-tab-rename-btn-${background}`)).toBeNull();

      act(() => fireEvent.mouseOver(screen.getByTestId(`terminal-tab-${background}`)));

      // Hovered, highlighted, still no pencil: a tab you are not on offers
      // exactly one pointer target — "switch to me".
      expect(screen.getByTestId(`terminal-tab-${background}`).dataset.hovered).toBe("true");
      expect(screen.queryByTestId(`terminal-tab-rename-btn-${background}`)).toBeNull();
      expect(screen.queryByTestId(`terminal-tab-rename-btn-${focused}`)).toBeNull();

      // It appears only once that tab becomes the focused one.
      act(() => fireEvent.click(screen.getByTestId(`terminal-tab-title-${background}`)));
      expect(useAppStore.getState().activeTerminalTabId).toBe(background);
      expect(screen.getByTestId(`terminal-tab-rename-btn-${background}`)).toBeInTheDocument();
    });

    it("clicking the rename affordance starts an inline rename on that tab", async () => {
      const { background, focused } = await renderTwoTabs();
      act(() => fireEvent.mouseOver(screen.getByTestId(`terminal-tab-${focused}`)));
      act(() => fireEvent.click(screen.getByTestId(`terminal-tab-rename-btn-${focused}`)));

      const input = screen.getByTestId(`terminal-tab-rename-input-${focused}`);
      fireEvent.change(input, { target: { value: "Spectra run" } });
      fireEvent.keyDown(input, { key: "Enter" });

      await waitFor(() => {
        const tabs = useAppStore.getState().terminalTabs;
        expect(tabs.find((t) => t.id === focused)?.title).toBe("Spectra run");
      });
      // The other tab is untouched.
      expect(useAppStore.getState().terminalTabs.find((t) => t.id === background)?.title).toBe(
        "Chat 1",
      );
    });

    it("clicking the tab body switches tabs and does NOT start a rename", async () => {
      const { background, focused } = await renderTwoTabs();
      expect(useAppStore.getState().activeTerminalTabId).toBe(focused);
      const titleBefore = useAppStore.getState().terminalTabs[0].title;

      // Hover first (as a real pointer must), then click the tab body.
      act(() => fireEvent.mouseOver(screen.getByTestId(`terminal-tab-${background}`)));
      act(() => fireEvent.click(screen.getByTestId(`terminal-tab-title-${background}`)));

      // Half one: it switched.
      expect(useAppStore.getState().activeTerminalTabId).toBe(background);
      // Half two: no rename was started, and no title changed.
      expect(screen.queryByTestId(`terminal-tab-rename-input-${background}`)).toBeNull();
      expect(screen.queryByTestId(`terminal-tab-rename-input-${focused}`)).toBeNull();
      expect(useAppStore.getState().terminalTabs[0].title).toBe(titleBefore);
      expect(screen.getByTestId(`terminal-tab-title-${background}`)).toBeInTheDocument();

      // Clicking the body of the tab you are *already* on is likewise a
      // no-op, not a shortcut into rename — even though the pencil is now
      // showing on it.
      expect(screen.getByTestId(`terminal-tab-rename-btn-${background}`)).toBeInTheDocument();
      act(() => fireEvent.click(screen.getByTestId(`terminal-tab-title-${background}`)));
      expect(useAppStore.getState().activeTerminalTabId).toBe(background);
      expect(screen.queryByTestId(`terminal-tab-rename-input-${background}`)).toBeNull();
      expect(useAppStore.getState().terminalTabs[0].title).toBe(titleBefore);
    });

    it("rename always targets the tab the user is looking at", async () => {
      // The pencil can no longer reach a background tab, but double-click
      // still can, so `startRename` keeps selecting the target first. Holding
      // this invariant at the container means no future entry point can open
      // a rename over content the user is not looking at.
      const { background, focused } = await renderTwoTabs();
      expect(useAppStore.getState().activeTerminalTabId).toBe(focused);

      act(() => fireEvent.doubleClick(screen.getByTestId(`terminal-tab-title-${background}`)));

      // Switched to the background tab...
      expect(useAppStore.getState().activeTerminalTabId).toBe(background);
      // ...and the rename input is on that same tab, not the previously focused one.
      expect(screen.getByTestId(`terminal-tab-rename-input-${background}`)).toBeInTheDocument();
      expect(screen.queryByTestId(`terminal-tab-rename-input-${focused}`)).toBeNull();

      // Escape backs out with nothing renamed — the mis-click escape hatch.
      fireEvent.keyDown(screen.getByTestId(`terminal-tab-rename-input-${background}`), {
        key: "Escape",
      });
      await waitFor(() =>
        expect(screen.queryByTestId(`terminal-tab-rename-input-${background}`)).toBeNull(),
      );
      expect(useAppStore.getState().terminalTabs[0].title).toBe("Chat 1");
      expect(useAppStore.getState().activeTerminalTabId).toBe(background);
    });

    it("double-click on the tab body still renames", async () => {
      const { background } = await renderTwoTabs();
      act(() => fireEvent.doubleClick(screen.getByTestId(`terminal-tab-title-${background}`)));
      const input = screen.getByTestId(`terminal-tab-rename-input-${background}`);
      fireEvent.change(input, { target: { value: "Old habit" } });
      fireEvent.keyDown(input, { key: "Enter" });
      await waitFor(() => expect(useAppStore.getState().terminalTabs[0].title).toBe("Old habit"));
    });

    it("keyboard focus reveals the affordance so rename is not pointer-only", async () => {
      const { focused } = await renderTwoTabs();
      expect(screen.queryByTestId(`terminal-tab-rename-btn-${focused}`)).toBeNull();
      act(() => fireEvent.focus(screen.getByTestId(`terminal-tab-title-${focused}`)));
      // Focusing anything in the row mounts the pencil, so it is reachable by
      // continuing to Tab forward — rename is not mouse-only.
      expect(screen.getByTestId(`terminal-tab-rename-btn-${focused}`)).toBeInTheDocument();
    });

    it("the affordance reserves no space and never displaces the close button", async () => {
      const { focused } = await renderTwoTabs();
      const rowTestId = `terminal-tab-${focused}`;
      const closeClassBefore = screen.getByTestId(`terminal-tab-close-btn-${focused}`).className;
      const rowClassBefore = screen.getByTestId(rowTestId).className;
      const flowBefore = inFlowChildren(rowTestId);

      act(() => fireEvent.mouseOver(screen.getByTestId(rowTestId)));

      const pencil = screen.getByTestId(`terminal-tab-rename-btn-${focused}`);
      // Out of the flex flow: mounting it cannot contribute width or shift a
      // sibling. This is the whole reason it is safe to mount on hover.
      expect(pencil.className).toContain("absolute");
      // The close button is pinned to the row's right edge, so its position is
      // a function of the row alone — unchanged, hovered or not.
      const closeAfter = screen.getByTestId(`terminal-tab-close-btn-${focused}`);
      expect(closeAfter.className).toContain("absolute");
      expect(closeAfter.className).toBe(closeClassBefore);
      // Nothing in the flow changed, and the row's own box (padding included)
      // is identical — the tab did not get wider.
      expect(inFlowChildren(rowTestId)).toEqual(flowBefore);
      expect(screen.getByTestId(rowTestId).className).toBe(rowClassBefore);

      // And close still closes, without renaming anything.
      act(() => fireEvent.click(closeAfter));
      expect(useAppStore.getState().terminalTabs.map((t) => t.id)).toEqual([
        useAppStore.getState().terminalTabs[0].id,
      ]);
      expect(screen.queryByTestId(`terminal-tab-rename-input-${focused}`)).toBeNull();
    });

    it("the affordance is hidden while a rename is in progress", async () => {
      const { focused } = await renderTwoTabs();
      act(() => fireEvent.mouseOver(screen.getByTestId(`terminal-tab-${focused}`)));
      act(() => fireEvent.click(screen.getByTestId(`terminal-tab-rename-btn-${focused}`)));
      expect(screen.queryByTestId(`terminal-tab-rename-btn-${focused}`)).toBeNull();
      // The close button survives so the user is never trapped in rename.
      expect(screen.getByTestId(`terminal-tab-close-btn-${focused}`)).toBeInTheDocument();
    });

    it("the title truncates and never clips the status decorations", async () => {
      const { focused } = await renderTwoTabs();
      act(() => useAppStore.getState().launchTerminalTab(focused, "claude-code", "safe"));

      // Short title: label truncates within a bounded width, running dot lives
      // outside the truncating span so it cannot be clipped or ellipsised.
      const shortLabel = screen.getByTestId(`terminal-tab-label-${focused}`);
      expect(shortLabel.textContent).toBe("Chat 2");
      expect(shortLabel.className).toContain("truncate");
      expect(shortLabel.className).toContain("max-w-[10rem]");
      const status = screen.getByTestId(`terminal-tab-status-${focused}`);
      expect(status).toBeInTheDocument();
      expect(status.contains(shortLabel)).toBe(false);
      expect(shortLabel.contains(status)).toBe(false);

      // Long title: same bounded, truncating span; status is still its sibling
      // on the leading edge, which is also why the overlaid pencil on the
      // trailing edge can never cover it.
      const long = "Raman baseline correction for the 2026-06 cryostat run, attempt 4";
      act(() => useAppStore.getState().renameTerminalTab(focused, long));
      const longLabel = screen.getByTestId(`terminal-tab-label-${focused}`);
      expect(longLabel.textContent).toBe(long);
      expect(longLabel.className).toContain("truncate");
      expect(longLabel.className).toContain("max-w-[10rem]");
      expect(screen.getByTestId(`terminal-tab-status-${focused}`).contains(longLabel)).toBe(false);
    });
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

  it("leaves Ctrl+C / Ctrl+V to the terminal clipboard handler (#1994)", async () => {
    // The window-level shortcut listener must not claim the keys that
    // TerminalView maps to copy/paste: no tab is opened, closed or switched.
    render(<TerminalTabs />);
    await waitFor(() => expect(useAppStore.getState().terminalTabs.length).toBe(1));
    act(() => fireEvent.click(screen.getByTestId("terminal-tabs-add")));
    const tabs = useAppStore.getState().terminalTabs;
    const activeBefore = useAppStore.getState().activeTerminalTabId;
    expect(tabs.length).toBe(2);

    act(() => {
      fireEvent.keyDown(window, { key: "c", ctrlKey: true });
      fireEvent.keyDown(window, { key: "v", ctrlKey: true });
    });

    expect(useAppStore.getState().terminalTabs.length).toBe(2);
    expect(useAppStore.getState().activeTerminalTabId).toBe(activeBefore);

    // ...and the tab shortcuts still work afterwards.
    act(() => {
      fireEvent.keyDown(window, { key: "1", ctrlKey: true });
    });
    expect(useAppStore.getState().activeTerminalTabId).toBe(tabs[0].id);
    act(() => {
      fireEvent.keyDown(window, { key: "t", ctrlKey: true });
    });
    expect(useAppStore.getState().terminalTabs.length).toBe(3);
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
          provider: "kimi-code",
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
      // ADR-034 FR-022: the tab records the provider the engine reported, not
      // the former hardcoded "claude-code".
      expect(tabs[0].provider).toBe("kimi-code");
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
          provider: "qoder",
        });
      });
      expect(useAppStore.getState().activeTerminalTabId).toBe("blk-2");
      const blkTab = useAppStore.getState().terminalTabs.find((t) => t.id === "blk-2");
      expect(blkTab?.permissionMode).toBe("dangerous");
      expect(blkTab?.provider).toBe("qoder");
    });

    it("handleBlockPtyOpened is idempotent on tab_id", async () => {
      const { handleBlockPtyOpened } = await import("../TerminalTabs");
      act(() => {
        handleBlockPtyOpened({
          tab_id: "blk-3",
          block_run_id: "run-3",
          block_name: "x",
          provider: "codex",
        });
        handleBlockPtyOpened({
          tab_id: "blk-3",
          block_run_id: "run-3",
          block_name: "x",
          provider: "codex",
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
          provider: "kimi-code",
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
          provider: "qoder-cn",
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
          provider: "claude-code",
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
          provider: "claude-code",
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
          provider: "claude-code",
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
