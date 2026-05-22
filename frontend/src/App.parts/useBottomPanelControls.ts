// Extracted from App.tsx as part of the #1422 god-file split.
//
// useBottomPanelControls — owns the imperative `ResizablePanel` handle for
// the bottom panel + the cross-component callbacks that drive it
// (`handleNodeSelect`, `handleErrorClick`, `handleBottomTabChange`,
// `handleCanvasPaneClick`). Lifted out of App.tsx so the bottom-panel
// expand/collapse contract lives in one place — the inline version was
// scattered across five different useCallback declarations next to
// unrelated state.

import { useCallback, useRef } from "react";
import type { PanelImperativeHandle } from "react-resizable-panels";

import type { BottomTab } from "../types/ui";

export interface BottomPanelControlsDeps {
  bottomPanelPinned: boolean;
  setSelectedNodeId: (id: string | null) => void;
  setActiveBottomTab: (tab: BottomTab) => void;
}

export interface BottomPanelControls {
  bottomPanelRef: React.RefObject<PanelImperativeHandle | null>;
  expandBottomPanel: () => void;
  handleCanvasPaneClick: () => void;
  handleNodeSelect: (nodeId: string | null) => void;
  handleErrorClick: (blockId: string) => void;
  handleBottomTabChange: (tab: BottomTab) => void;
}

export function useBottomPanelControls(deps: BottomPanelControlsDeps): BottomPanelControls {
  const { bottomPanelPinned, setSelectedNodeId, setActiveBottomTab } = deps;

  const bottomPanelRef = useRef<PanelImperativeHandle>(null);

  const expandBottomPanel = useCallback(() => {
    bottomPanelRef.current?.expand();
  }, []);

  const handleCanvasPaneClick = useCallback(() => {
    if (bottomPanelPinned) return;
    bottomPanelRef.current?.collapse();
  }, [bottomPanelPinned]);

  // #793: handleNodeSelect intentionally keeps the "config" switch —
  // selecting a node IS an explicit user request to see that node's
  // config, and also re-expands the bottom panel so the implicit tab
  // switch is visible.
  const handleNodeSelect = useCallback(
    (nodeId: string | null) => {
      setSelectedNodeId(nodeId);
      if (nodeId) {
        setActiveBottomTab("config");
        expandBottomPanel();
      }
    },
    [expandBottomPanel, setSelectedNodeId, setActiveBottomTab],
  );

  // Clicking an error badge selects the node and opens the Logs tab.
  const handleErrorClick = useCallback(
    (blockId: string) => {
      setSelectedNodeId(blockId);
      setActiveBottomTab("logs");
      expandBottomPanel();
    },
    [expandBottomPanel, setSelectedNodeId, setActiveBottomTab],
  );

  // #1421: `activeBottomTab` is intentionally NOT a dep — the callback
  // only reads from its `tab` parameter and the setters, never from the
  // value of `activeBottomTab`.
  const handleBottomTabChange = useCallback(
    (tab: BottomTab) => {
      setActiveBottomTab(tab);
      expandBottomPanel();
    },
    [expandBottomPanel, setActiveBottomTab],
  );

  return {
    bottomPanelRef,
    expandBottomPanel,
    handleCanvasPaneClick,
    handleNodeSelect,
    handleErrorClick,
    handleBottomTabChange,
  };
}
