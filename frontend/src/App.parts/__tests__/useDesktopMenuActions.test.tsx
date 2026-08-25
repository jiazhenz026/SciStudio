import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppStore } from "../../store";
import { resetAppStore } from "../../testUtils";
import type { ScistudioDesktopMenuAction } from "../../types/desktop";
import { useDesktopMenuActions } from "../useDesktopMenuActions";

type MenuListener = (action: ScistudioDesktopMenuAction) => void;

function installBridge() {
  let listener: MenuListener | null = null;
  const unsubscribe = vi.fn();
  window.scistudioDesktop = {
    platform: "win32",
    versions: { electron: "42.0.0", chrome: "130.0.0" },
    relaunch: vi.fn(),
    onMenuAction: (callback: MenuListener) => {
      listener = callback;
      return unsubscribe;
    },
  };
  return {
    fire: (action: ScistudioDesktopMenuAction) => {
      expect(listener).not.toBeNull();
      act(() => listener!(action));
    },
    unsubscribe,
  };
}

function renderMenuActions() {
  const handlers = {
    save: vi.fn(),
    saveAs: vi.fn(),
  };
  renderHook(() => useDesktopMenuActions(handlers));
  return handlers;
}

const DEMO_PROJECT = {
  id: "p1",
  name: "Project",
  description: "",
  path: "C:\\Project",
  workflow_count: 1,
  workflows: ["main"],
  current_workflow_id: "main",
};

describe("useDesktopMenuActions", () => {
  beforeEach(() => {
    resetAppStore();
  });

  afterEach(() => {
    delete window.scistudioDesktop;
  });

  it("is a no-op when the desktop bridge is absent (browser build)", () => {
    delete window.scistudioDesktop;
    expect(() => renderMenuActions()).not.toThrow();
  });

  it("routes save actions to the App handlers", () => {
    const bridge = installBridge();
    const handlers = renderMenuActions();

    bridge.fire("save");
    bridge.fire("save-as");

    expect(handlers.save).toHaveBeenCalledTimes(1);
    expect(handlers.saveAs).toHaveBeenCalledTimes(1);
  });

  it("suppresses save-as while a file tab is active (ADR-036 §3.7)", () => {
    const bridge = installBridge();
    const handlers = renderMenuActions();

    act(() => {
      useAppStore.setState({
        tabs: [
          {
            kind: "file",
            id: "file-1",
            filePath: "C:\\Project\\notes.md",
            displayName: "notes.md",
            language: "markdown",
            content: "",
            contentLoadedAt: 0,
            dirty: false,
            readOnly: false,
          },
        ],
        activeTabId: "file-1",
      });
    });
    bridge.fire("save-as");
    expect(handlers.saveAs).not.toHaveBeenCalled();

    act(() => {
      useAppStore.setState({ tabs: [], activeTabId: null });
    });
    bridge.fire("save-as");
    expect(handlers.saveAs).toHaveBeenCalledTimes(1);
  });

  it("projects-home closes the active project; new-project opens the dialog", () => {
    const bridge = installBridge();
    renderMenuActions();

    act(() => {
      useAppStore.setState({ currentProject: DEMO_PROJECT });
    });
    bridge.fire("projects-home");
    expect(useAppStore.getState().currentProject).toBeNull();

    bridge.fire("new-project");
    const { projectDialogOpen, projectDialog } = useAppStore.getState();
    expect(projectDialogOpen).toBe(true);
    expect(projectDialog.mode).toBe("new");
  });

  it("opens the Package Manager and Learning Center through the store", () => {
    const bridge = installBridge();
    renderMenuActions();

    bridge.fire("package-manager");
    expect(useAppStore.getState().packageManagerOpen).toBe(true);

    bridge.fire("learning-center");
    expect(useAppStore.getState().learningCenterOpen).toBe(true);
  });

  it("opens Bring In My Work only when a project is open", () => {
    const bridge = installBridge();
    renderMenuActions();

    bridge.fire("bring-in-my-work");
    expect(useAppStore.getState().bringInMyWorkOpen).toBe(false);

    act(() => {
      useAppStore.setState({ currentProject: DEMO_PROJECT });
    });
    bridge.fire("bring-in-my-work");
    expect(useAppStore.getState().bringInMyWorkOpen).toBe(true);
  });

  it("unsubscribes from the bridge on unmount", () => {
    const bridge = installBridge();
    const hook = renderHook(() => useDesktopMenuActions({ save: vi.fn(), saveAs: vi.fn() }));
    hook.unmount();
    expect(bridge.unsubscribe).toHaveBeenCalledTimes(1);
  });
});
