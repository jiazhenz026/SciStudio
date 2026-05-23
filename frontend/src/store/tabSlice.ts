import type { StateCreator } from "zustand";

import type { AppStore, TabSlice } from "./types";
import {
  createApplyFileRemoteContent,
  createConfirmFileVersion,
  createMarkFileRemoteConflict,
  createOpenFileTab,
  createSaveFileTab,
  createUpdateFileTabContent,
} from "./tabSlice.parts/fileTabActions";
import {
  createCloseTab,
  createOpenTab,
  createSwitchTab,
  createSyncActiveTab,
} from "./tabSlice.parts/workflowTabActions";

export const createTabSlice: StateCreator<AppStore, [], [], TabSlice> = (set, get) => ({
  tabs: [],
  activeTabId: null,

  openTab: createOpenTab(set, get),
  switchTab: createSwitchTab(set, get),
  closeTab: createCloseTab(set, get),
  syncActiveTab: createSyncActiveTab(set, get),

  openFileTab: createOpenFileTab(set, get),
  saveFileTab: createSaveFileTab(set, get),
  updateFileTabContent: createUpdateFileTabContent(set, get),
  confirmFileVersion: createConfirmFileVersion(set, get),
  applyFileRemoteContent: createApplyFileRemoteContent(set, get),
  markFileRemoteConflict: createMarkFileRemoteConflict(set, get),
});
