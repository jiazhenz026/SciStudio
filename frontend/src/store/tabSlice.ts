import type { StateCreator } from "zustand";

import { ApiError, api, createClientSourceId } from "../lib/api";
import type { VersionedWorkflowResponse } from "../lib/api";
import type { AppStore, FileTab, TabSlice, TabState, WorkflowTab } from "./types";

/**
 * Capture the current workflow + UI state into a WorkflowTab snapshot.
 *
 * Phase 2A (I36a): only workflow tabs need their canvas state synced back
 * from the live workflow slice. File tabs hold their own ``content`` /
 * ``dirty`` directly on the FileTab record (no separate slice), so this
 * helper is a no-op for them.
 */
function captureWorkflowTab(state: AppStore): WorkflowTab {
  return {
    kind: "workflow",
    id: state.activeTabId ?? state.workflowId ?? "main",
    workflowId: state.workflowId ?? "main",
    workflowName: state.workflowName,
    workflowDescription: state.workflowDescription,
    workflowVersion: state.workflowVersion,
    workflowMetadata: state.workflowMetadata,
    workflowNodes: state.workflowNodes,
    workflowEdges: state.workflowEdges,
    workflowDirty: state.workflowDirty,
    workflowBaseVersion: state.workflowBaseVersion,
    workflowPendingVersion: state.workflowPendingVersion,
    workflowPendingSourceId: state.workflowPendingSourceId,
    workflowConflict: state.workflowConflict,
    workflowHistory: state.workflowHistory,
    workflowFuture: state.workflowFuture,
    selectedNodeId: state.selectedNodeId,
  };
}

/**
 * Sync the active tab back into the tabs array — workflow only. File tabs
 * are stored in ``state.tabs`` directly and do not need a sync step.
 */
function captureActiveTab(state: AppStore, tab: TabState): TabState {
  if (tab.kind === "workflow") {
    return captureWorkflowTab(state);
  }
  return tab;
}

/**
 * Restore a workflow tab snapshot into the live workflow slice fields.
 *
 * For file tabs we only update ``activeTabId`` — the canvas slice is left
 * intact so toggling back to a workflow tab does not lose its state.
 */
function restoreTab(tab: TabState): Partial<AppStore> {
  if (tab.kind === "workflow") {
    return {
      workflowId: tab.workflowId,
      workflowName: tab.workflowName,
      workflowDescription: tab.workflowDescription,
      workflowVersion: tab.workflowVersion,
      workflowMetadata: tab.workflowMetadata,
      workflowNodes: tab.workflowNodes,
      workflowEdges: tab.workflowEdges,
      workflowDirty: tab.workflowDirty,
      workflowBaseVersion: tab.workflowBaseVersion ?? null,
      workflowPendingVersion: tab.workflowPendingVersion ?? tab.workflowBaseVersion ?? null,
      workflowPendingSourceId: tab.workflowPendingSourceId ?? null,
      workflowConflict: tab.workflowConflict ?? null,
      workflowHistory: tab.workflowHistory,
      workflowFuture: tab.workflowFuture,
      selectedNodeId: tab.selectedNodeId,
      activeTabId: tab.id,
    };
  }
  return { activeTabId: tab.id };
}

/** Map a file extension to the Monaco language id used in FileTab.language. */
function languageForPath(filePath: string): FileTab["language"] {
  const lower = filePath.toLowerCase();
  if (lower.endsWith(".py")) return "python";
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "yaml";
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".md")) return "markdown";
  return "text";
}

function basename(filePath: string): string {
  const parts = filePath.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || filePath;
}

function fileTabIdFor(filePath: string, readOnly: boolean): string {
  return readOnly ? `source:${filePath}` : `file:${filePath}`;
}

/**
 * Replace the existing tab matching `id` and switch to it.
 *
 * Used after a file tab's content arrives from the backend and we need
 * to replace the loading placeholder.
 */
function replaceTab(state: AppStore, id: string, next: TabState): Partial<AppStore> {
  return {
    tabs: state.tabs.map((t) => (t.id === id ? next : t)),
  };
}

function workflowStateVersion(workflow: VersionedWorkflowResponse): number | null {
  return typeof workflow.state_version === "number" ? workflow.state_version : null;
}

function fileStateVersion(response: { state_version?: number }): number | null {
  return typeof response.state_version === "number" ? response.state_version : null;
}

function nextPendingVersion(base: number | null | undefined, pending: number | null | undefined): number | null {
  if (typeof base !== "number") return pending ?? null;
  if (typeof pending !== "number") return base + 1;
  return Math.max(base + 1, pending + 1);
}

export const createTabSlice: StateCreator<AppStore, [], [], TabSlice> = (set, get) => ({
  tabs: [],
  activeTabId: null,

  openTab: (workflow, displayName) => {
    const state = get();
    // #796: pick a non-empty display name. The backend's WorkflowModel.id has a
    // default of "" — if a YAML omits the id field, workflow.id arrives empty
    // and the tab label + top-left title render blank. Fall back to the caller-
    // supplied displayName (typically the filename stem), then "Untitled".
    const effectiveName = workflow.id || displayName || "Untitled";

    // Use workflow.id when present for tab-de-duplication; otherwise fall back
    // to the display name so two opens of the same blank-id file still de-dupe.
    const dedupeKey = workflow.id || displayName || "";
    const existing = dedupeKey
      ? state.tabs.find((t) => t.kind === "workflow" && t.workflowId === dedupeKey)
      : undefined;
    if (existing) {
      // Switch to it instead of opening a duplicate
      state.switchTab(existing.id);
      return;
    }

    // Guard: enforce maximum tab limit (#598)
    if (state.tabs.length >= 50) {
      window.alert("Maximum 50 tabs reached.");
      return;
    }

    // Save current tab state before switching
    const currentActive = state.tabs.find((t) => t.id === state.activeTabId) ?? null;
    const updatedTabs = currentActive
      ? state.tabs.map((t) => (t.id === state.activeTabId ? captureActiveTab(state, t) : t))
      : [...state.tabs];

    // Create new tab. Use the effective name as the workflowId fallback so
    // downstream API calls (save/run) have something to address.
    const idForTab = workflow.id || displayName || "main";
    const tabId = `tab-${idForTab}-${Date.now()}`;
    const baseVersion = workflowStateVersion(workflow as VersionedWorkflowResponse);
    const newTab: WorkflowTab = {
      kind: "workflow",
      id: tabId,
      workflowId: idForTab,
      workflowName: effectiveName,
      workflowDescription: workflow.description,
      workflowVersion: workflow.version,
      workflowMetadata: workflow.metadata,
      workflowNodes: workflow.nodes,
      workflowEdges: workflow.edges,
      workflowDirty: false,
      workflowBaseVersion: baseVersion,
      workflowPendingVersion: baseVersion,
      workflowPendingSourceId: null,
      workflowConflict: null,
      workflowHistory: [],
      workflowFuture: [],
      selectedNodeId: null,
    };

    set({
      tabs: [...updatedTabs, newTab],
      ...restoreTab(newTab),
    });
  },

  switchTab: (tabId) => {
    const state = get();
    if (tabId === state.activeTabId) return;

    const target = state.tabs.find((t) => t.id === tabId);
    if (!target) return;

    // Save current tab state
    const currentActive = state.tabs.find((t) => t.id === state.activeTabId) ?? null;
    const updatedTabs = currentActive
      ? state.tabs.map((t) => (t.id === state.activeTabId ? captureActiveTab(state, t) : t))
      : state.tabs;

    set({
      tabs: updatedTabs,
      ...restoreTab(target),
    });
  },

  closeTab: (tabId) => {
    const state = get();
    const tab = state.tabs.find((t) => t.id === tabId);
    if (!tab) return true;

    // If this is the active tab, check for the latest dirty state
    let isDirty: boolean;
    let displayLabel: string;
    if (tab.kind === "workflow") {
      isDirty = tabId === state.activeTabId ? state.workflowDirty : tab.workflowDirty;
      displayLabel = tab.workflowName;
    } else {
      isDirty = tab.dirty;
      displayLabel = tab.displayName;
    }

    if (isDirty) {
      const confirmed = window.confirm(
        `"${displayLabel}" has unsaved changes. Close anyway?`,
      );
      if (!confirmed) return false;
    }

    const remaining = state.tabs.filter((t) => t.id !== tabId);

    if (tabId === state.activeTabId) {
      // Need to switch to another tab or clear
      if (remaining.length > 0) {
        // Switch to the tab that was next to this one
        const closedIndex = state.tabs.findIndex((t) => t.id === tabId);
        const nextTab = remaining[Math.min(closedIndex, remaining.length - 1)];
        set({
          tabs: remaining,
          ...restoreTab(nextTab),
        });
      } else {
        // No tabs left — reset to empty state
        set({
          tabs: [],
          activeTabId: null,
          workflowId: null,
          workflowName: "Untitled",
          workflowDescription: "",
          workflowVersion: "1.0.0",
          workflowMetadata: {},
          workflowNodes: [],
          workflowEdges: [],
          workflowDirty: false,
          workflowBaseVersion: null,
          workflowPendingVersion: null,
          workflowPendingSourceId: null,
          workflowConflict: null,
          workflowHistory: [],
          workflowFuture: [],
          selectedNodeId: null,
        });
      }
    } else {
      set({ tabs: remaining });
    }
    return true;
  },

  syncActiveTab: () => {
    const state = get();
    if (!state.activeTabId) return;
    set({
      tabs: state.tabs.map((t) =>
        t.id === state.activeTabId ? captureActiveTab(state, t) : t,
      ),
    });
  },

  /**
   * ADR-036 §3.10 — open (or focus) a file editor tab.
   *
   * Dedup key:
   *   readOnly=true  → "source:<filePath>"
   *   readOnly=false → "file:<filePath>"
   *
   * If a tab with that id is already open, switch to it. Otherwise insert
   * a placeholder FileTab in ``loading: true`` state immediately (so the
   * UI can render the tab strip without waiting on the network), then
   * fetch via GET /api/projects/{id}/file and replace the placeholder
   * with the resolved content on success.
   */
  openFileTab: (filePath, opts) => {
    const state = get();
    const readOnly = Boolean(opts?.readOnly);
    const id = fileTabIdFor(filePath, readOnly);

    const existing = state.tabs.find((t) => t.id === id);
    // #869: if the tab exists but is stuck in loading state (e.g. after
    // localStorage rehydrate strips ``content`` and sets ``loading: true``,
    // per ADR-036 §3.11), fall through to refetch instead of just focusing
    // a permanently-empty placeholder.
    const needsRefetch = Boolean(
      existing && existing.kind === "file" && existing.loading,
    );
    if (existing && !needsRefetch) {
      state.switchTab(id);
      return;
    }

    const project = state.currentProject;
    if (!project) {
      window.alert("Open a project before opening files.");
      return;
    }

    if (!existing) {
      // Only enforce the tab cap when actually creating a new tab — a
      // refetch reuses the existing placeholder slot.
      if (state.tabs.length >= 50) {
        window.alert("Maximum 50 tabs reached.");
        return;
      }

      const language = languageForPath(filePath);
      const display = basename(filePath) + (readOnly ? " (source)" : "");
      const placeholder: FileTab = {
        kind: "file",
        id,
        filePath,
        displayName: display,
        language,
        content: "",
        contentLoadedAt: 0,
        baseVersion: null,
        pendingVersion: null,
        pendingSourceId: null,
        conflict: null,
        dirty: false,
        readOnly,
        loading: true,
      };

      // Save the currently-active tab snapshot, then append the placeholder
      // and switch to it.
      const currentActive = state.tabs.find((t) => t.id === state.activeTabId) ?? null;
      const updatedTabs = currentActive
        ? state.tabs.map((t) => (t.id === state.activeTabId ? captureActiveTab(state, t) : t))
        : [...state.tabs];

      set({
        tabs: [...updatedTabs, placeholder],
        activeTabId: id,
      });
    } else {
      // #869 refetch path: focus the existing loading placeholder; the
      // GET below will replace it with populated content on success.
      state.switchTab(id);
    }

    // Fire the GET in the background; once it resolves, replace the
    // placeholder (or stale rehydrated tab — #869) with a populated
    // FileTab. Keep the loading-state UI resilient to errors so the user
    // can close the tab on failure.
    api
      .getProjectFile(project.id, filePath)
      .then((response) => {
        const after = get();
        // Only replace if the tab still exists (user may have closed it).
        const current = after.tabs.find((t) => t.id === id);
        if (!current || current.kind !== "file") return;
        const populated: FileTab = {
          ...current,
          content: response.content,
          contentLoadedAt: response.mtime,
          baseVersion: fileStateVersion(response),
          pendingVersion: fileStateVersion(response),
          pendingSourceId: null,
          conflict: null,
          loading: false,
        };
        set(replaceTab(after, id, populated));
      })
      .catch((err) => {
        const message = err instanceof ApiError ? err.message : String(err);
        window.alert(`Failed to open ${filePath}: ${message}`);
        // Drop the placeholder so the user is not left with a broken tab.
        const after = get();
        const remaining = after.tabs.filter((t) => t.id !== id);
        const fallback = remaining[remaining.length - 1] ?? null;
        if (fallback) {
          set({ tabs: remaining, ...restoreTab(fallback) });
        } else {
          set({ tabs: remaining, activeTabId: null });
        }
      });
  },

  /**
   * ADR-036 §3.10 — save a file tab to disk.
   *
   * Read-only tabs are a no-op (source views must not be saved). On
   * success, ``dirty`` clears and ``contentLoadedAt`` advances to the
   * server's new mtime.
   */
  saveFileTab: async (id) => {
    const state = get();
    const tab = state.tabs.find((t) => t.id === id);
    if (!tab || tab.kind !== "file") return;
    if (tab.readOnly) return;

    const project = state.currentProject;
    if (!project) return;

    // Snapshot the content we are about to PUT. After the await we will
    // compare against the latest tab content; if it has diverged the user
    // typed during the in-flight request and we MUST preserve their newer
    // edits (mtime advances, dirty stays true so the next debounce saves
    // again). See audit 2026-05-14 P1 #1.
    const sentContent = tab.content;
    const sourceId = createClientSourceId("file");
    set(
      replaceTab(state, id, {
        ...tab,
        pendingVersion: nextPendingVersion(tab.baseVersion, tab.pendingVersion),
        pendingSourceId: sourceId,
        conflict: null,
      }),
    );

    try {
      const response = await api.putProjectFile(project.id, tab.filePath, sentContent, { sourceId });
      const after = get();
      const latest = after.tabs.find((t) => t.id === id);
      // Tab may have been closed during the await — drop the result.
      if (!latest || latest.kind !== "file") return;

      const contentChangedDuringSave = latest.content !== sentContent;
      const responseVersion = fileStateVersion(response);
      const nextPending = contentChangedDuringSave
        ? nextPendingVersion(responseVersion ?? latest.baseVersion, latest.pendingVersion)
        : responseVersion ?? latest.pendingVersion ?? null;
      const next: FileTab = {
        ...latest,
        // Only clear dirty if the user did NOT edit during the in-flight
        // PUT. Otherwise leave dirty=true so the autosave debounce picks
        // up the newer content on its next tick.
        dirty: contentChangedDuringSave ? true : false,
        contentLoadedAt: response.mtime,
        baseVersion: responseVersion ?? latest.baseVersion ?? null,
        pendingVersion: nextPending,
        pendingSourceId: null,
        conflict: null,
      };
      set(replaceTab(after, id, next));
    } catch (err) {
      const message = err instanceof ApiError ? err.message : String(err);
      window.alert(`Failed to save ${tab.filePath}: ${message}`);
      // Leave dirty=true so the user can retry.
    }
  },

  /**
   * ADR-036 §3.10 — update a file tab's in-memory content + dirty flag.
   *
   * Read-only tabs ignore updates so accidental edits to a source view
   * don't silently mark it dirty. The CodeEditor in Phase 2B (I36b)
   * already passes ``readOnly`` into Monaco so this branch should only
   * fire if a future caller bypasses the editor.
   */
  updateFileTabContent: (id, content) => {
    const state = get();
    const tab = state.tabs.find((t) => t.id === id);
    if (!tab || tab.kind !== "file") return;
    if (tab.readOnly) return;
    if (tab.content === content) return;

    const next: FileTab = {
      ...tab,
      content,
      dirty: true,
      pendingVersion: nextPendingVersion(tab.baseVersion, tab.pendingVersion),
      conflict: null,
    };
    set({ tabs: state.tabs.map((t) => (t.id === id ? next : t)) });
  },

  confirmFileVersion: (id, version, sourceId = null) => {
    const state = get();
    const tab = state.tabs.find((t) => t.id === id);
    if (!tab || tab.kind !== "file") return;
    const hasNewerLocalEdits = typeof tab.pendingVersion === "number" && tab.pendingVersion > version;
    const next: FileTab = {
      ...tab,
      baseVersion: version,
      pendingVersion: hasNewerLocalEdits ? tab.pendingVersion : version,
      pendingSourceId: tab.pendingSourceId === sourceId ? null : tab.pendingSourceId,
      dirty: hasNewerLocalEdits ? tab.dirty : false,
      conflict: null,
    };
    set({ tabs: state.tabs.map((t) => (t.id === id ? next : t)) });
  },

  applyFileRemoteContent: (id, response) => {
    const state = get();
    const tab = state.tabs.find((t) => t.id === id);
    if (!tab || tab.kind !== "file") return;
    const version = fileStateVersion(response);
    const next: FileTab = {
      ...tab,
      content: response.content,
      contentLoadedAt: response.mtime,
      baseVersion: version ?? tab.baseVersion ?? null,
      pendingVersion: version ?? tab.baseVersion ?? null,
      pendingSourceId: null,
      conflict: null,
      dirty: false,
      loading: false,
    };
    set({ tabs: state.tabs.map((t) => (t.id === id ? next : t)) });
  },

  markFileRemoteConflict: (id, conflict) => {
    const state = get();
    const tab = state.tabs.find((t) => t.id === id);
    if (!tab || tab.kind !== "file") return;
    const hasLocalEdits =
      tab.dirty ||
      (typeof tab.baseVersion === "number" &&
        typeof tab.pendingVersion === "number" &&
        tab.pendingVersion > tab.baseVersion);
    const next: FileTab = {
      ...tab,
      dirty: hasLocalEdits,
      conflict,
      loading: false,
    };
    set({ tabs: state.tabs.map((t) => (t.id === id ? next : t)) });
  },
});
