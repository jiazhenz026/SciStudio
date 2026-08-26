// useActiveTab — derive the active tab and its kind from the tab list.
//
// Extracted from App.tsx (ADR-036 §3.7) to keep the App orchestrator under the
// max-lines-per-function cap. Pure derivation: the active tab object, the file
// tab when the active tab is a file (else null), the preview tab when the
// active tab is a preview (else null, #2112), and the kind used for the
// toolbar swap.

import { useMemo } from "react";

import type { AnyTab, FileTab, PreviewTab } from "../store/types";

export interface ActiveTabState {
  activeTab: AnyTab | null;
  activeFileTab: FileTab | null;
  activePreviewTab: PreviewTab | null;
  activeTabKind: "workflow" | "file" | "preview";
}

export function useActiveTab(tabs: AnyTab[], activeTabId: string | null): ActiveTabState {
  const activeTab = useMemo<AnyTab | null>(
    () => tabs.find((t) => t.id === activeTabId) ?? null,
    [tabs, activeTabId],
  );
  const activeFileTab: FileTab | null = activeTab && activeTab.kind === "file" ? activeTab : null;
  const activePreviewTab: PreviewTab | null =
    activeTab && activeTab.kind === "preview" ? activeTab : null;
  const activeTabKind: "workflow" | "file" | "preview" = activeFileTab
    ? "file"
    : activePreviewTab
      ? "preview"
      : "workflow";
  return { activeTab, activeFileTab, activePreviewTab, activeTabKind };
}
