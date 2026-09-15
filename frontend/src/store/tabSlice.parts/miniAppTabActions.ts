/**
 * MiniApp-tab action factory for tabSlice (ADR-054 FR-018).
 *
 * A MiniApp tab is the opposite of a preview tab in the one way that matters:
 * it survives a focus change (FR-019), because the pane it renders owns a
 * `panel.py` process whose lifetime is the pane's mount. `dropInactivePreviewTabs`
 * filters on `kind !== "preview"`, so a miniapp tab is already exempt; the
 * rule is restated here because it is the whole reason this opener does not
 * simply reuse `createOpenPreviewTab`.
 */
import type { StoreApi } from "zustand";

import type { AppStore, MiniAppTab, TabSlice } from "../types";
import { backingWorkflowTabId, captureActiveTab, dropInactivePreviewTabs } from "./tabHelpers";
import { miniAppTabId } from "../../miniapps/types";

type StoreSetter = StoreApi<AppStore>["setState"];
type StoreGetter = StoreApi<AppStore>["getState"];

export function createOpenMiniAppTab(
  set: StoreSetter,
  get: StoreGetter,
): TabSlice["openMiniAppTab"] {
  return ({ panelId, name, target }) => {
    const state = get();
    const id = miniAppTabId(panelId, target);

    // FR-018 — one MiniApp on one output is one tab. Opening it again focuses
    // the tab that is already there rather than starting a second process on
    // the same data.
    if (state.tabs.some((t) => t.id === id)) {
      state.switchTab(id);
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

    const newTab: MiniAppTab = {
      kind: "miniapp",
      id,
      panelId,
      source: target,
      backingTabId: backingWorkflowTabId(state),
      displayName: name || panelId,
      openedAt: Date.now(),
    };

    set({
      // Opening a MiniApp moves focus away from any preview tab, which is
      // dropped by the same rule every other opener applies.
      tabs: dropInactivePreviewTabs([...updatedTabs, newTab], id),
      activeTabId: id,
    });
  };
}
