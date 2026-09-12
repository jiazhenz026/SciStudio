/**
 * Workflow-tab action factories for tabSlice. Extracted in #1413 / #1414.
 *
 * The ADR-045 version-vector contract is preserved verbatim — see
 * `tabSlice.versionVector.test.ts`.
 */
import type { StoreApi } from "zustand";

import type { VersionedWorkflowResponse } from "../../lib/api";
import type { AppStore, TabSlice, WorkflowTab } from "../types";
import {
  EMPTY_TAB_STATE,
  captureActiveTab,
  dropInactivePreviewTabs,
  restoreTab,
  workflowStateVersion,
} from "./tabHelpers";
import { normalizeLoadedNodes } from "../workflowSlice.parts/workflowHelpers";

type StoreSetter = StoreApi<AppStore>["setState"];
type StoreGetter = StoreApi<AppStore>["getState"];

/**
 * #2362 — a monotonic suffix for tab ids.
 *
 * The id used to be `tab-<workflowId>-<Date.now()>`, neither component of which
 * is unique: two imported copies of one subworkflow share the workflow id (that
 * is why `openTab` dedups on `tabKey` instead), and two opens in the same
 * millisecond share the timestamp. Two tabs then answered to one id, and every
 * `t.id === activeTabId` match in this file — switch, close, capture — hit both.
 *
 * The counter is process-local, which is all that is needed: workflow tabs are
 * never persisted (see `partialize` in `store/index.ts`), so no id has to
 * survive a reload.
 */
let tabSerial = 0;

function nextTabSerial(): string {
  tabSerial += 1;
  return `${Date.now()}-${tabSerial}`;
}

export function createOpenTab(set: StoreSetter, get: StoreGetter): TabSlice["openTab"] {
  return (workflow, displayName, runPrefix, tabKey) => {
    const state = get();
    // #796: pick a non-empty display name. The backend's WorkflowModel.id has a
    // default of "" — if a YAML omits the id field, workflow.id arrives empty
    // and the tab label + top-left title render blank. Fall back to the caller-
    // supplied displayName (typically the filename stem), then "Untitled".
    const effectiveName = workflow.id || displayName || "Untitled";

    // ADR-044 — dedup identity. Defaults to the workflow id (legacy behavior);
    // a subworkflow open passes its unique ref.path so copies sharing one id do
    // not collide. Compare against each tab's tabKey, falling back to workflowId
    // for tabs created/persisted before this field existed.
    const dedupeKey = tabKey || workflow.id || displayName || "";
    const existing = dedupeKey
      ? state.tabs.find((t) => t.kind === "workflow" && (t.tabKey ?? t.workflowId) === dedupeKey)
      : undefined;
    if (existing) {
      // ADR-044 — refresh the run-scope prefix when reopening from a (possibly
      // different) parent subworkflow node so the expanded view maps to the
      // current run; leave it untouched when opened directly (no prefix).
      if (runPrefix !== undefined && existing.kind === "workflow") {
        set({ tabs: state.tabs.map((t) => (t.id === existing.id ? { ...t, runPrefix } : t)) });
      }
      state.switchTab(existing.id);
      return;
    }

    if (state.tabs.length >= 50) {
      window.alert("Maximum 50 tabs reached.");
      return;
    }

    const currentActive = state.tabs.find((t) => t.id === state.activeTabId) ?? null;
    const updatedTabs = currentActive
      ? state.tabs.map((t) => (t.id === state.activeTabId ? captureActiveTab(state, t) : t))
      : [...state.tabs];

    const idForTab = workflow.id || displayName || "main";
    const tabId = `tab-${idForTab}-${nextTabSerial()}`;
    const baseVersion = workflowStateVersion(workflow as VersionedWorkflowResponse);
    const newTab: WorkflowTab = {
      kind: "workflow",
      id: tabId,
      workflowId: idForTab,
      workflowName: effectiveName,
      workflowDescription: workflow.description,
      workflowVersion: workflow.version,
      workflowMetadata: workflow.metadata,
      // #11: wrap flat (agent/hand-authored) node configs into the canonical
      // { params } shape so the config panel shows the real stored values when a
      // workflow is opened into a tab (the primary open path).
      workflowNodes: normalizeLoadedNodes(workflow.nodes),
      workflowEdges: workflow.edges,
      workflowDirty: false,
      workflowBaseVersion: baseVersion,
      workflowPendingVersion: baseVersion,
      workflowPendingSourceId: null,
      workflowConflict: null,
      workflowHistory: [],
      workflowFuture: [],
      selectedNodeId: null,
      tabKey: dedupeKey,
      runPrefix,
    };

    set({
      // #2112 — opening a workflow tab moves focus away from any preview tab.
      tabs: dropInactivePreviewTabs([...updatedTabs, newTab], newTab.id),
      ...restoreTab(newTab),
    });
  };
}

export function createSwitchTab(set: StoreSetter, get: StoreGetter): TabSlice["switchTab"] {
  return (tabId) => {
    const state = get();
    if (tabId === state.activeTabId) return;

    const target = state.tabs.find((t) => t.id === tabId);
    if (!target) return;

    const currentActive = state.tabs.find((t) => t.id === state.activeTabId) ?? null;
    const updatedTabs = currentActive
      ? state.tabs.map((t) => (t.id === state.activeTabId ? captureActiveTab(state, t) : t))
      : state.tabs;

    set({
      // #2112 — a preview tab lives only while it is active: switching to any
      // other tab removes the one left behind. `restoreTab` is a no-op beyond
      // setting `activeTabId` for a preview target, and `captureActiveTab`
      // passes the one being dropped through unchanged.
      tabs: dropInactivePreviewTabs(updatedTabs, tabId),
      ...restoreTab(target),
    });
  };
}

export function createCloseTab(set: StoreSetter, get: StoreGetter): TabSlice["closeTab"] {
  return (tabId) => {
    const state = get();
    const tab = state.tabs.find((t) => t.id === tabId);
    if (!tab) return true;

    let isDirty: boolean;
    let displayLabel: string;
    if (tab.kind === "workflow") {
      isDirty = tabId === state.activeTabId ? state.workflowDirty : tab.workflowDirty;
      displayLabel = tab.workflowName;
    } else if (tab.kind === "file") {
      isDirty = tab.dirty;
      displayLabel = tab.displayName;
    } else {
      // #2112 — preview tabs are read-only snapshots: never dirty, never prompt.
      isDirty = false;
      displayLabel = tab.displayName;
    }

    if (isDirty) {
      const confirmed = window.confirm(`"${displayLabel}" has unsaved changes. Close anyway?`);
      if (!confirmed) return false;
    }

    const remaining = state.tabs.filter((t) => t.id !== tabId);

    if (tabId === state.activeTabId) {
      if (remaining.length > 0) {
        const closedIndex = state.tabs.findIndex((t) => t.id === tabId);
        const nextTab = remaining[Math.min(closedIndex, remaining.length - 1)];
        set({
          tabs: remaining,
          ...restoreTab(nextTab),
        });
      } else {
        set(EMPTY_TAB_STATE);
      }
    } else {
      set({ tabs: remaining });
    }
    return true;
  };
}

export function createSyncActiveTab(set: StoreSetter, get: StoreGetter): TabSlice["syncActiveTab"] {
  return () => {
    const state = get();
    if (!state.activeTabId) return;
    const activeTab = state.tabs.find((t) => t.id === state.activeTabId);
    if (activeTab?.kind === "preview") {
      // #2112 — while a preview tab owns focus, the live workflow slice still
      // belongs to the backing workflow tab (restoreTab on a preview only sets
      // activeTabId). Capture into that tab so autosave / WebSocket updates
      // landing during the preview are not lost when switching back restores
      // the snapshot. captureWorkflowTab derives `id` from activeTabId, so the
      // tab's own id must be preserved explicitly.
      //
      // #2362: address that tab by its own id. `workflowId` is not unique
      // across tabs — imported subworkflow copies share an internal id, which
      // is precisely why `openTab` dedups on `tabKey` instead — so matching on
      // it wrote this capture into every such tab, clobbering the others'
      // canvases, which autosave then committed to the wrong files.
      // `backingTabId` is absent only when the preview was opened while a
      // non-workflow tab held focus; the `workflowId` match remains for that.
      const backingTabId = activeTab.backingTabId;
      set({
        tabs: state.tabs.map((t) => {
          if (t.kind !== "workflow") return t;
          const isBacking = backingTabId
            ? t.id === backingTabId
            : t.workflowId === state.workflowId;
          return isBacking ? { ...captureActiveTab(state, t), id: t.id } : t;
        }),
      });
      return;
    }
    set({
      tabs: state.tabs.map((t) => (t.id === state.activeTabId ? captureActiveTab(state, t) : t)),
    });
  };
}
