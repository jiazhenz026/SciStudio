import { useCallback, useEffect, useRef, type RefObject } from "react";
import type { PanelImperativeHandle, PanelSize } from "react-resizable-panels";

import { useAppStore } from "../store";

export const DESKTOP_SIDEBAR_WIDTH = "280px";
export const AI_SIDEBAR_WIDTH = "28%";

/** Restore a readable first-open width and remember manual sizing per presentation. */
export function useWorkspaceSidebar(
  panelRef: RefObject<PanelImperativeHandle | null>,
  collapsed: boolean,
  isAi: boolean,
) {
  const mode = isAi ? "ai" : "workbench";
  const previousMode = useRef(mode);
  const widths = useRef({ ai: AI_SIDEBAR_WIDTH, workbench: DESKTOP_SIDEBAR_WIDTH });

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;
    const changedMode = previousMode.current !== mode;
    previousMode.current = mode;
    if (collapsed) {
      panel.collapse();
    } else if (panel.isCollapsed() || changedMode) {
      // expand() falls back to minSize when the panel mounted at zero. Read
      // the desired width before expand() emits that intermediate resize.
      const width = widths.current[mode];
      panel.expand();
      panel.resize(width);
    }
  }, [collapsed, mode, panelRef]);

  return useCallback(
    (size: PanelSize) => {
      if (previousMode.current !== mode) return;
      const isCollapsed = size.asPercentage <= 0.5;
      if (!isCollapsed) {
        widths.current[mode] = isAi ? `${size.asPercentage}%` : `${size.inPixels}px`;
      }
      if (isCollapsed !== useAppStore.getState().paletteCollapsed) {
        useAppStore.setState({ paletteCollapsed: isCollapsed });
      }
    },
    [isAi, mode],
  );
}
