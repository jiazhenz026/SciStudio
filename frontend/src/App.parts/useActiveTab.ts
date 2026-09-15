// useActiveTab — derive the active tab and its kind from the tab list.
//
// Extracted from App.tsx (ADR-036 §3.7) to keep the App orchestrator under the
// max-lines-per-function cap. Pure derivation: the active tab object, the file
// tab when the active tab is a file (else null), the preview tab when the
// active tab is a preview (else null, #2112), the MiniApp tab when the active
// tab is a MiniApp (else null, ADR-054 FR-018), and the kind used for the
// toolbar swap.

import { useMemo } from "react";

import type { AnyTab, FileTab, MiniAppTab, PreviewTab } from "../store/types";

export interface ActiveTabState {
  activeTab: AnyTab | null;
  activeFileTab: FileTab | null;
  activePreviewTab: PreviewTab | null;
  /** ADR-054 FR-018 — the focused MiniApp tab, when one is focused. */
  activeMiniAppTab: MiniAppTab | null;
  activeTabKind: "workflow" | "file" | "preview" | "miniapp";
}

export function useActiveTab(tabs: AnyTab[], activeTabId: string | null): ActiveTabState {
  const activeTab = useMemo<AnyTab | null>(
    () => tabs.find((t) => t.id === activeTabId) ?? null,
    [tabs, activeTabId],
  );
  const activeFileTab: FileTab | null = activeTab && activeTab.kind === "file" ? activeTab : null;
  const activePreviewTab: PreviewTab | null =
    activeTab && activeTab.kind === "preview" ? activeTab : null;
  const activeMiniAppTab: MiniAppTab | null =
    activeTab && activeTab.kind === "miniapp" ? activeTab : null;
  /*
   * The fallback is "workflow", so every kind that is not derived above is
   * reported as a focused canvas to the toolbar swap. ADR-054 FR-018 adds
   * `miniapp` here for that reason: without it a MiniApp tab would put the
   * workflow toolbar over a surface that has no canvas underneath it.
   */
  const activeTabKind: ActiveTabState["activeTabKind"] = activeFileTab
    ? "file"
    : activePreviewTab
      ? "preview"
      : activeMiniAppTab
        ? "miniapp"
        : "workflow";
  return { activeTab, activeFileTab, activePreviewTab, activeMiniAppTab, activeTabKind };
}
