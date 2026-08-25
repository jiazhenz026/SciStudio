// Desktop application menu dispatch.
//
// desktop/menu.js forwards menu clicks to the renderer over IPC; the preload
// bridge exposes them as window.scistudioDesktop.onMenuAction. This hook maps
// each action id onto the same handlers the toolbar uses, so the native menu
// and the in-app buttons can never drift apart. In the browser build the
// bridge is absent and the hook is a no-op.

import { useEffect, useRef } from "react";

import { useAppStore } from "../store";

export interface DesktopMenuHandlers {
  /** File > Projects Home — close the active project (back to WelcomePane). */
  goHome: () => void;
  /** File > New Project… */
  newProject: () => void;
  /** File > Save — tab-aware save, same as the toolbar Save button. */
  save: () => void;
  /** File > Save As… */
  saveAs: () => void;
}

export function useDesktopMenuActions(handlers: DesktopMenuHandlers): void {
  // The IPC subscription is registered once; the ref keeps the latest handler
  // identities without re-subscribing on every render.
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  useEffect(() => {
    const bridge = window.scistudioDesktop;
    if (!bridge?.onMenuAction) return undefined;
    return bridge.onMenuAction((action) => {
      const store = useAppStore.getState();
      switch (action) {
        case "projects-home":
          handlersRef.current.goHome();
          break;
        case "new-project":
          handlersRef.current.newProject();
          break;
        case "save":
          handlersRef.current.save();
          break;
        case "save-as":
          handlersRef.current.saveAs();
          break;
        case "bring-in-my-work":
          // Mirrors the toolbar button's disabled state (ADR-053 spec 2
          // FR-002): the import dialog writes into the open project, so it
          // cannot open without one.
          if (store.currentProject) store.setBringInMyWorkOpen(true);
          break;
        case "package-manager":
          store.setPackageManagerOpen(true);
          break;
        case "learning-center":
          store.openLearningCenter();
          break;
      }
    });
  }, []);
}
