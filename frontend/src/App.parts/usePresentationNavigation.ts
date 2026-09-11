import { useEffect, useRef } from "react";

import { usePresentation } from "../lib/presentation";
import { useAppStore } from "../store";
import type { LeftTab } from "./ProjectWorkspace";

/** Reveal new preview targets without taking focus on unrelated store updates. */
export function usePresentationNavigation(selectSection: (section: LeftTab) => void) {
  const mode = usePresentation();
  const selectedNodeId = useAppStore((state) => state.selectedNodeId);
  const plotTarget = useAppStore((state) => state.plotPreviewTarget);
  const previousMode = useRef(mode);
  useEffect(() => {
    if (mode === "ai") {
      selectSection("preview");
    } else if (previousMode.current === "ai") {
      selectSection("blocks");
    }
    previousMode.current = mode;
  }, [mode, selectSection]);
  useEffect(() => {
    if (mode === "ai" && (selectedNodeId || plotTarget)) selectSection("preview");
  }, [mode, selectedNodeId, plotTarget, selectSection]);
}
