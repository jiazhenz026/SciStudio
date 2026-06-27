// useActiveTab — derive the active tab and its kind from the tab list.
//
// Extracted from App.tsx (ADR-036 §3.7) to keep the App orchestrator under the
// max-lines-per-function cap. Pure derivation: the active tab object, the file
// tab when the active tab is a file (else null), and the kind used for the
// toolbar swap.

import { useMemo } from "react";

import type { AnyTab, FileTab } from "../store/types";

export interface ActiveTabState {
  activeTab: AnyTab | null;
  activeFileTab: FileTab | null;
  activeTabKind: "workflow" | "file";
}

export function useActiveTab(tabs: AnyTab[], activeTabId: string | null): ActiveTabState {
  const activeTab = useMemo<AnyTab | null>(
    () => tabs.find((t) => t.id === activeTabId) ?? null,
    [tabs, activeTabId],
  );
  const activeFileTab: FileTab | null = activeTab && activeTab.kind === "file" ? activeTab : null;
  const activeTabKind: "workflow" | "file" = activeFileTab ? "file" : "workflow";
  return { activeTab, activeFileTab, activeTabKind };
}
