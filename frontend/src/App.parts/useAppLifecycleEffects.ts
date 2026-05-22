// Extracted from App.tsx as part of the #1422 god-file split.
//
// useAppLifecycleEffects — three cross-cutting `useEffect`s that run for
// the lifetime of the App component:
//   1. one-shot boot effect (load projects + block catalog),
//   2. workflow auto-save debouncer (workflow tabs only),
//   3. active-tab snapshot sync.
//
// The file-tab autosave loop has its own dedicated hook
// (`useFileTabsAutosave`); the keyboard-shortcut listener has
// `useAppKeyboardShortcuts`. This module owns only the App-level
// lifecycle effects so the main component reads as "wire these up"
// instead of three sequential effect declarations.
//
// Wave 1 (#1421) discipline preserved verbatim:
//   - the boot effect intentionally has an empty dep array via an inline
//     `eslint-disable-next-line` (one-shot semantic — re-running would
//     double-load the projects + block catalog and clobber a visible
//     error),
//   - every other effect's dep array is exhaustive.

import { useEffect, useRef } from "react";

import type { ProjectResponse, WorkflowResponse } from "../types/api";

export interface AppLifecycleDeps {
  currentProject: ProjectResponse | null;
  workflowDirty: boolean;
  workflowPayload: WorkflowResponse;
  refreshProjects: () => Promise<void>;
  refreshBlocks: () => Promise<void>;
  saveWorkflow: () => Promise<void>;
  setBusy: (busy: boolean) => void;
  setLastError: (message: string | null) => void;
  // tab-sync inputs
  activeTabId: string | null;
  selectedNodeId: string | null;
  workflowDescription: string;
  workflowNodes: WorkflowResponse["nodes"];
  workflowEdges: WorkflowResponse["edges"];
  syncActiveTab: () => void;
}

export function useAppLifecycleEffects(deps: AppLifecycleDeps): void {
  const {
    currentProject,
    workflowDirty,
    workflowPayload,
    refreshProjects,
    refreshBlocks,
    saveWorkflow,
    setBusy,
    setLastError,
    activeTabId,
    selectedNodeId,
    workflowDescription,
    workflowNodes,
    workflowEdges,
    syncActiveTab,
  } = deps;

  // Boot: load projects and blocks. #1421: intentional one-shot via
  // `bootedRef.current` — we DO NOT want this to re-run when callback
  // identities change.
  const bootedRef = useRef(false);
  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;
    void (async () => {
      setBusy(true);
      try {
        await Promise.all([refreshProjects(), refreshBlocks()]);
      } catch (error) {
        setLastError((error as Error).message);
      } finally {
        setBusy(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-save on dirty (workflow tabs). #1421: `saveWorkflow` is a stable
  // useCallback tied to the same reactive inputs the effect already lists.
  useEffect(() => {
    if (!currentProject || !workflowDirty) return undefined;
    const timeout = window.setTimeout(() => {
      void saveWorkflow();
    }, 800);
    return () => window.clearTimeout(timeout);
  }, [currentProject, workflowDirty, workflowPayload, saveWorkflow]);

  // Sync active tab snapshot when workflow state OR the active tab itself
  // changes. #1421: see PR #1435 commit message — `activeTabId` is in the
  // dep array because switching tabs should also push the current snapshot
  // so the newly-active tab reflects current workflow state immediately.
  useEffect(() => {
    if (activeTabId) {
      syncActiveTab();
    }
  }, [
    workflowNodes,
    workflowEdges,
    workflowDirty,
    workflowDescription,
    selectedNodeId,
    activeTabId,
    syncActiveTab,
  ]);
}
