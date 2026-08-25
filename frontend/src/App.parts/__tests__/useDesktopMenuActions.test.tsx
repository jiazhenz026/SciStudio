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
    goHome: vi.fn(),
    newProject: vi.fn(),
    save: vi.fn(),
    saveAs: vi.fn(),
  };
  renderHook(() => useDesktopMenuActions(handlers));
  return handlers;
}

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

  it("routes project navigation and save actions to the App handlers", () => {
    const bridge = installBridge();
    const handlers = renderMenuActions();

    bridge.fire("projects-home");
    bridge.fire("new-project");
    bridge.fire("save");
    bridge.fire("save-as");

    expect(handlers.goHome).toHaveBeenCalledTimes(1);
    expect(handlers.newProject).toHaveBeenCalledTimes(1);
    expect(handlers.save).toHaveBeenCalledTimes(1);
    expect(handlers.saveAs).toHaveBeenCalledTimes(1);
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
      useAppStore.setState({
        currentProject: {
          id: "p1",
          name: "Project",
          description: "",
          path: "C:\\Project",
          workflow_count: 1,
          workflows: ["main"],
          current_workflow_id: "main",
        },
      });
    });
    bridge.fire("bring-in-my-work");
    expect(useAppStore.getState().bringInMyWorkOpen).toBe(true);
  });

  it("unsubscribes from the bridge on unmount", () => {
    const bridge = installBridge();
    const handlers = {
      goHome: vi.fn(),
      newProject: vi.fn(),
      save: vi.fn(),
      saveAs: vi.fn(),
    };
    const hook = renderHook(() => useDesktopMenuActions(handlers));
    hook.unmount();
    expect(bridge.unsubscribe).toHaveBeenCalledTimes(1);
  });
});
