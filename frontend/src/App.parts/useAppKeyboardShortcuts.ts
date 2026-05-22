// Extracted from App.tsx as part of the #1422 god-file split.
//
// Global keyboard-shortcut handler attached to `window` while the App is
// mounted. Behaviour preserved verbatim from the inline `useEffect` it
// replaced — including the "skip when focused in an input/textarea/select"
// guard that lets each editor field own its own keys.
//
// Wave 1 (#1421) discipline preserved: the dependency array lists every
// stable Zustand setter / useCallback identity the handler reads, so
// react-hooks/exhaustive-deps stays satisfied without an inline disable.

import { useEffect } from "react";

import type { FileTab } from "../store/types";

export interface UseAppKeyboardShortcutsDeps {
  activeFileTab: FileTab | null;
  cancelWorkflow: () => Promise<void> | void;
  openProjectDialog: (mode: "new" | "open", overrides?: Record<string, unknown>) => void;
  redoWorkflow: () => void;
  removeNode: (nodeId: string) => void;
  runWorkflow: () => Promise<void> | void;
  saveFileTab: (tabId: string) => Promise<void>;
  saveWorkflow: () => Promise<void> | void;
  saveWorkflowAs: () => Promise<void> | void;
  selectedNodeId: string | null;
  setSelectedNodeId: (id: string | null) => void;
  toggleBottomPanel: () => void;
  toggleMinimap: () => void;
  togglePalette: () => void;
  togglePreview: () => void;
  undoWorkflow: () => void;
}

function isInputTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

function handleCtrlS(
  event: KeyboardEvent,
  activeFileTab: FileTab | null,
  saveFileTab: UseAppKeyboardShortcutsDeps["saveFileTab"],
  saveWorkflow: UseAppKeyboardShortcutsDeps["saveWorkflow"],
): void {
  event.preventDefault();
  if (activeFileTab) {
    if (!activeFileTab.readOnly) {
      void saveFileTab(activeFileTab.id).catch((error) => {
        console.warn(`saveFileTab(${activeFileTab.id}) failed:`, error);
      });
    }
  } else {
    void saveWorkflow();
  }
}

// Map of Ctrl+<key> to the bound action. Split out so the main listener's
// cyclomatic complexity stays under the eslint cap.
function buildCtrlActionMap(deps: UseAppKeyboardShortcutsDeps): Record<string, () => void> {
  return {
    z: deps.undoWorkflow,
    y: deps.redoWorkflow,
    enter: () => void deps.runWorkflow(),
    ".": () => void deps.cancelWorkflow(),
    b: deps.togglePalette,
    d: deps.togglePreview,
    j: deps.toggleBottomPanel,
    m: deps.toggleMinimap,
    o: () => deps.openProjectDialog("open"),
    // Ctrl+A: Select all handled by ReactFlow internally — register a no-op
    // entry so the global handler still calls preventDefault on it.
    a: () => {},
  };
}

export function useAppKeyboardShortcuts(deps: UseAppKeyboardShortcutsDeps): void {
  const {
    activeFileTab,
    cancelWorkflow,
    openProjectDialog,
    redoWorkflow,
    removeNode,
    runWorkflow,
    saveFileTab,
    saveWorkflow,
    saveWorkflowAs,
    selectedNodeId,
    setSelectedNodeId,
    toggleBottomPanel,
    toggleMinimap,
    togglePalette,
    togglePreview,
    undoWorkflow,
  } = deps;

  useEffect(() => {
    const ctrlActions = buildCtrlActionMap({
      activeFileTab,
      cancelWorkflow,
      openProjectDialog,
      redoWorkflow,
      removeNode,
      runWorkflow,
      saveFileTab,
      saveWorkflow,
      saveWorkflowAs,
      selectedNodeId,
      setSelectedNodeId,
      toggleBottomPanel,
      toggleMinimap,
      togglePalette,
      togglePreview,
      undoWorkflow,
    });

    const listener = (event: KeyboardEvent) => {
      const isInput = isInputTarget(event.target);
      const ctrl = event.ctrlKey || event.metaKey;
      const key = event.key.toLowerCase();

      // Escape always works.
      if (event.key === "Escape") {
        event.preventDefault();
        setSelectedNodeId(null);
        return;
      }

      // Ctrl+S always works — routes to file save when a file tab is active
      // (ADR-036 §3.7), workflow save otherwise. Ctrl+Shift+S is Save As
      // (workflow only).
      if (ctrl && key === "s") {
        if (event.shiftKey) {
          event.preventDefault();
          if (!activeFileTab) void saveWorkflowAs();
          return;
        }
        handleCtrlS(event, activeFileTab, saveFileTab, saveWorkflow);
        return;
      }

      // Skip other shortcuts when in input fields.
      if (isInput) return;

      // Dispatch Ctrl+<key> via the action map.
      if (ctrl && key in ctrlActions) {
        event.preventDefault();
        ctrlActions[key]();
        return;
      }

      // Delete / Backspace removes the selected node.
      if ((event.key === "Delete" || event.key === "Backspace") && selectedNodeId) {
        removeNode(selectedNodeId);
      }
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [
    activeFileTab,
    cancelWorkflow,
    openProjectDialog,
    redoWorkflow,
    removeNode,
    runWorkflow,
    saveFileTab,
    saveWorkflow,
    saveWorkflowAs,
    selectedNodeId,
    setSelectedNodeId,
    toggleBottomPanel,
    toggleMinimap,
    togglePalette,
    togglePreview,
    undoWorkflow,
  ]);
}
