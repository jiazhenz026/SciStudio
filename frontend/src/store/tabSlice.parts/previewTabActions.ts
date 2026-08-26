/**
 * Preview-tab action factory for tabSlice (#2112).
 *
 * A preview tab renders a frozen {@link PreviewTarget} through the same
 * `PreviewHost` the right-sidebar DataPreview uses. It is transient by
 * design: no dirty state, never persisted, and removed the moment focus
 * moves to another tab (see `dropInactivePreviewTabs` in `tabHelpers.ts`).
 */
import type { StoreApi } from "zustand";

import type { AppStore, PreviewTab, TabSlice } from "../types";
import { captureActiveTab, dropInactivePreviewTabs } from "./tabHelpers";

type StoreSetter = StoreApi<AppStore>["setState"];
type StoreGetter = StoreApi<AppStore>["getState"];

export function createOpenPreviewTab(
  set: StoreSetter,
  get: StoreGetter,
): TabSlice["openPreviewTab"] {
  return (target, displayName, initialQuery) => {
    const state = get();
    const id = `preview:${target.ref}`;

    // Same-ref re-open focuses the existing tab (mirrors openFileTab's
    // id-keyed dedup): the target is frozen at open time, so a duplicate tab
    // could only ever show the same snapshot.
    const existing = state.tabs.find((t) => t.id === id);
    if (existing) {
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

    const newTab: PreviewTab = {
      kind: "preview",
      id,
      target,
      displayName: displayName || target.ref,
      initialQuery,
      openedAt: Date.now(),
    };

    // The new tab becomes active, so any previously active preview tab is
    // dropped with the rest of the switch-away rule.
    set({
      tabs: dropInactivePreviewTabs([...updatedTabs, newTab], id),
      activeTabId: id,
    });
  };
}
