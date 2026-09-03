import type { StateCreator } from "zustand";

import type { AppStore, TabSlice } from "./types";
import {
  createApplyFileRemoteContent,
  createConfirmFileVersion,
  createMarkFileRemoteConflict,
  createOpenBlockSourceTab,
  createOpenPanelSourceTab,
  createOpenTypeSourceTab,
  createOpenFileTab,
  createOpenUserLibraryFileTab,
  createSaveFileTab,
  createUpdateFileTabContent,
} from "./tabSlice.parts/fileTabActions";
import {
  createCloseTab,
  createOpenTab,
  createSwitchTab,
  createSyncActiveTab,
} from "./tabSlice.parts/workflowTabActions";
import { createOpenPreviewTab } from "./tabSlice.parts/previewTabActions";

export const createTabSlice: StateCreator<AppStore, [], [], TabSlice> = (set, get) => ({
  tabs: [],
  activeTabId: null,

  openTab: createOpenTab(set, get),
  switchTab: createSwitchTab(set, get),
  closeTab: createCloseTab(set, get),
  syncActiveTab: createSyncActiveTab(set, get),

  openFileTab: createOpenFileTab(set, get),
  openBlockSourceTab: createOpenBlockSourceTab(set, get),
  // ADR-053 FR-068 — the type-side read-only source tab.
  openTypeSourceTab: createOpenTypeSourceTab(set, get),
  // ADR-053 FR-032 — the user library's own editable tab.
  openUserLibraryFileTab: createOpenUserLibraryFileTab(set, get),
  // ADR-054 FR-024/FR-025 — a panel's entry document, editable in every tier.
  openPanelSourceTab: createOpenPanelSourceTab(set, get),
  // #2112 — transient preview tab (frozen PreviewTarget, never persisted).
  openPreviewTab: createOpenPreviewTab(set, get),
  saveFileTab: createSaveFileTab(set, get),
  updateFileTabContent: createUpdateFileTabContent(set, get),
  confirmFileVersion: createConfirmFileVersion(set, get),
  applyFileRemoteContent: createApplyFileRemoteContent(set, get),
  markFileRemoteConflict: createMarkFileRemoteConflict(set, get),
});
