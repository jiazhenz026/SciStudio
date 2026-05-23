/**
 * File-tab action factories for tabSlice. Extracted in #1413 / #1414.
 *
 * The ADR-045 version-vector contract on FileTab
 * (`baseVersion` / `pendingVersion` / `pendingSourceId`) is preserved
 * verbatim — see `tabSlice.versionVector.test.ts`.
 */
import type { StoreApi } from "zustand";

import { ApiError, api, createClientSourceId } from "../../lib/api";
import type { AppStore, FileTab, TabSlice } from "../types";
import {
  basename,
  captureActiveTab,
  fileStateVersion,
  fileTabIdFor,
  languageForPath,
  nextPendingVersion,
  replaceTab,
  restoreTab,
} from "./tabHelpers";

type StoreSetter = StoreApi<AppStore>["setState"];
type StoreGetter = StoreApi<AppStore>["getState"];

export function createOpenFileTab(set: StoreSetter, get: StoreGetter): TabSlice["openFileTab"] {
  return (filePath, opts) => {
    const state = get();
    const readOnly = Boolean(opts?.readOnly);
    const id = fileTabIdFor(filePath, readOnly);

    const existing = state.tabs.find((t) => t.id === id);
    // #869: if the tab exists but is stuck in loading state (e.g. after
    // localStorage rehydrate strips ``content`` and sets ``loading: true``,
    // per ADR-036 §3.11), fall through to refetch instead of just focusing
    // a permanently-empty placeholder.
    const needsRefetch = Boolean(existing && existing.kind === "file" && existing.loading);
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

      const currentActive = state.tabs.find((t) => t.id === state.activeTabId) ?? null;
      const updatedTabs = currentActive
        ? state.tabs.map((t) => (t.id === state.activeTabId ? captureActiveTab(state, t) : t))
        : [...state.tabs];

      set({
        tabs: [...updatedTabs, placeholder],
        activeTabId: id,
      });
    } else {
      state.switchTab(id);
    }

    api
      .getProjectFile(project.id, filePath)
      .then((response) => {
        const after = get();
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
        const after = get();
        const remaining = after.tabs.filter((t) => t.id !== id);
        const fallback = remaining[remaining.length - 1] ?? null;
        if (fallback) {
          set({ tabs: remaining, ...restoreTab(fallback) });
        } else {
          set({ tabs: remaining, activeTabId: null });
        }
      });
  };
}

// eslint-disable-next-line complexity -- ADR-045 reconcile state machine
async function performSaveFileTab(set: StoreSetter, get: StoreGetter, id: string): Promise<void> {
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
    const response = await api.putProjectFile(project.id, tab.filePath, sentContent, {
      sourceId,
    });
    const after = get();
    const latest = after.tabs.find((t) => t.id === id);
    if (!latest || latest.kind !== "file") return;

    const contentChangedDuringSave = latest.content !== sentContent;
    const responseVersion = fileStateVersion(response);
    const nextPending = contentChangedDuringSave
      ? nextPendingVersion(responseVersion ?? latest.baseVersion, latest.pendingVersion)
      : (responseVersion ?? latest.pendingVersion ?? null);
    const next: FileTab = {
      ...latest,
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
  }
}

export function createSaveFileTab(set: StoreSetter, get: StoreGetter): TabSlice["saveFileTab"] {
  return (id) => performSaveFileTab(set, get, id);
}

export function createUpdateFileTabContent(
  set: StoreSetter,
  get: StoreGetter,
): TabSlice["updateFileTabContent"] {
  return (id, content) => {
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
  };
}

export function createConfirmFileVersion(
  set: StoreSetter,
  get: StoreGetter,
): TabSlice["confirmFileVersion"] {
  return (id, version, sourceId = null) => {
    const state = get();
    const tab = state.tabs.find((t) => t.id === id);
    if (!tab || tab.kind !== "file") return;
    const hasNewerLocalEdits =
      typeof tab.pendingVersion === "number" && tab.pendingVersion > version;
    const next: FileTab = {
      ...tab,
      baseVersion: version,
      pendingVersion: hasNewerLocalEdits ? tab.pendingVersion : version,
      pendingSourceId: tab.pendingSourceId === sourceId ? null : tab.pendingSourceId,
      dirty: hasNewerLocalEdits ? tab.dirty : false,
      conflict: null,
    };
    set({ tabs: state.tabs.map((t) => (t.id === id ? next : t)) });
  };
}

export function createApplyFileRemoteContent(
  set: StoreSetter,
  get: StoreGetter,
): TabSlice["applyFileRemoteContent"] {
  return (id, response) => {
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
  };
}

export function createMarkFileRemoteConflict(
  set: StoreSetter,
  get: StoreGetter,
): TabSlice["markFileRemoteConflict"] {
  return (id, conflict) => {
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
  };
}
