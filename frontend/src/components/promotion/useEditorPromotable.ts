// Entry point E1's resolver — what the code editor currently has open.
//
// Spec: docs/specs/adr-053-personal-tool-library.md §6.2 E1 ("Block source
// editor toolbar, beside the existing save / view-source affordances").
//
// Reads the active tab out of the store rather than taking it as a prop so the
// toolbar group can mount the shared action without a new prop threaded from
// `App` through `Toolbar`. The resolution itself is `promotable.ts`'s, shared
// with E2 and E5 — this hook only decides *which* thing the editor is showing.

import { useMemo } from "react";

import { useAppStore } from "../../store";

import { promotableFileTab, type PromotableItem } from "./promotable";

export function useEditorPromotable(): PromotableItem | null {
  const tabs = useAppStore((state) => state.tabs);
  const activeTabId = useAppStore((state) => state.activeTabId);
  const blocks = useAppStore((state) => state.blocks);

  return useMemo(() => {
    const active = tabs.find((tab) => tab.id === activeTabId);
    const fileTab = active && active.kind === "file" ? active : null;
    return promotableFileTab(fileTab, blocks);
  }, [tabs, activeTabId, blocks]);
}
