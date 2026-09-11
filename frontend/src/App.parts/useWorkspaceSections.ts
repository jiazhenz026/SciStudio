import { useCallback, useState } from "react";

import { useAppStore } from "../store";
import type { LeftTab } from "./ProjectWorkspace";
import { usePresentationNavigation } from "./usePresentationNavigation";

export function useWorkspaceSections() {
  const [leftTab, setLeftTab] = useState<LeftTab>("blocks");
  const selectLeftTab = useCallback((tab: LeftTab) => {
    setLeftTab(tab);
    if (useAppStore.getState().paletteCollapsed) useAppStore.getState().togglePalette();
  }, []);
  const handleActivitySelect = useCallback(
    (tab: LeftTab) => {
      if (tab === leftTab && !useAppStore.getState().paletteCollapsed) {
        useAppStore.getState().togglePalette();
      } else {
        selectLeftTab(tab);
      }
    },
    [leftTab, selectLeftTab],
  );
  usePresentationNavigation(selectLeftTab);
  return { leftTab, selectLeftTab, handleActivitySelect };
}
